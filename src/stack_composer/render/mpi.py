"""Resolved MPI identity, shared by lane planning and scope rendering.

One module answers "which mpi_providers entry does this provider name mean on
this profile" and "what toolchain name does this compiler/provider pairing
get", so the spec decoration in plan.py and the rendered toolchains.yaml keys
in scopes.py cannot drift apart.
"""

from __future__ import annotations

import re
from copy import deepcopy
from typing import Any

from stack_composer.render.spack_specs import (
    is_absolute_prefix,
    is_compiler_fragment,
    is_renderable_external_name_version,
)
from stack_composer.render.versioning import version_key

_TOKEN_RE = re.compile(r"[^A-Za-z0-9]+")


def is_renderable_mpi_provider(provider: dict[str, Any]) -> bool:
    """True when a probed MPI entry can produce at least one safe external spec.

    This keeps MPI selection generic: provider shape decides renderability, not
    vendor names. Per-compiler flavor MPIs and single-prefix MPIs share this
    one predicate.
    """
    if not is_renderable_external_name_version(provider.get("name"), provider.get("version")):
        return False
    flavors = provider.get("flavors")
    if isinstance(flavors, dict):
        return any(
            is_compiler_fragment(compiler)
            and isinstance(flavor, dict)
            and is_absolute_prefix(flavor.get("prefix"))
            for compiler, flavor in flavors.items()
        )
    if not is_absolute_prefix(provider.get("prefix")):
        return False
    compiler = provider.get("compiler")
    return not compiler or is_compiler_fragment(compiler)


def platform_mpi_candidates(profile: dict[str, Any], provider_name: str) -> list[dict[str, Any]]:
    return [
        provider
        for provider in profile.get("mpi_providers") or []
        if provider.get("name") == provider_name and is_renderable_mpi_provider(provider)
    ]


def slug_token(value: object) -> str:
    """Return a Spack-spec-token-safe identifier fragment.

    Toolchain names are referenced as `%name` in root specs, so do not retain
    punctuation that is meaningful to Spack's spec parser (`.`, `-`, `@`, `/`).
    """
    return _TOKEN_RE.sub("", str(value)).lower()


def mpi_toolchain_name(
    compiler_name: str,
    provider_name: str,
    compiler_version: str | None = None,
    mpi_version: str | None = None,
) -> str:
    """The toolchain key for one compiler/provider pairing.

    Names are version-qualified whenever the profile gives versions. This
    keeps the `%toolchain` token stable and unambiguous on systems with several
    compiler or MPI versions, without forcing callers to learn the slug rules.
    """
    compiler = slug_token(compiler_name)
    if compiler_version:
        compiler += slug_token(compiler_version)
    mpi = slug_token(provider_name)
    if mpi_version:
        mpi += slug_token(mpi_version)
    return f"{compiler}_{mpi}"


def compiler_fragment_name_version(compiler: str) -> tuple[str, str | None]:
    if "@" not in compiler:
        return compiler, None
    name, version = compiler.split("@", 1)
    return name, version


def compiler_provider_ref(provider: dict[str, Any]) -> str:
    return f"{provider['name']}@{provider['version']}"


def compiler_ref_name(compiler: str) -> str:
    name, _version = compiler_fragment_name_version(compiler)
    return name


def compiler_ref_axis(compiler: str) -> str:
    name, version = compiler_fragment_name_version(compiler)
    if not version:
        return name
    return slug_token(name) + slug_token(version)


def select_compiler_provider(profile: dict[str, Any], compiler: str) -> dict[str, Any] | None:
    """Select the compiler provider named by a lane or MPI compiler fragment.

    A compiler fragment may be bare (`gcc`) or versioned (`gcc@13.3.0`). Exact
    fragments resolve exactly; bare fragments use profile order, matching the
    current compiler selection policy.
    """
    wanted_name, wanted_version = compiler_fragment_name_version(compiler)
    candidates = [
        provider
        for provider in profile.get("compiler_providers") or []
        if provider.get("name") == wanted_name
        and is_renderable_external_name_version(provider.get("name"), provider.get("version"))
    ]
    if wanted_version:
        return next(
            (
                provider
                for provider in candidates
                if compiler_version_matches(str(provider.get("version")), wanted_version)
            ),
            None,
        )
    return candidates[0] if candidates else None


def compiler_version_matches(provider_version: str, requested_version: str) -> bool:
    if provider_version == requested_version:
        return True
    return provider_version.startswith(requested_version + ".")


def compiler_version_at_least(provider_version: str, baseline_version: str) -> bool:
    return version_key(provider_version) >= version_key(baseline_version)


def mpi_flavor_compiler_policy(provider: dict[str, Any] | None) -> str:
    """How a platform MPI flavor compiler fragment constrains a lane compiler.

    Generic MPI providers default to exact-ish compiler matching. Cray MPICH
    product-tree flavor paths advertise a compiler baseline for that family
    (`ofi/gnu/12.3`), not an exact lane compiler pin.
    """
    if not provider:
        return "exact"
    if provider.get("name") == "cray-mpich" and provider.get("provider_family") == "platform":
        return "family_min_version"
    return "exact"


def compiler_ref_satisfies_flavor(
    compiler: str, flavor_compiler: str, provider: dict[str, Any] | None
) -> bool:
    compiler_name, compiler_version = compiler_fragment_name_version(compiler)
    flavor_name, flavor_version = compiler_fragment_name_version(flavor_compiler)
    if compiler_name != flavor_name:
        return False
    if flavor_version is None:
        return True
    if compiler_version is None:
        return True
    if mpi_flavor_compiler_policy(provider) == "family_min_version":
        return compiler_version_at_least(compiler_version, flavor_version)
    return compiler_version_matches(compiler_version, flavor_version)


def select_flavor_compiler(
    profile: dict[str, Any], flavor_compiler: str, provider: dict[str, Any] | None
) -> dict[str, Any] | None:
    """The rendered compiler an MPI flavor binds to under its flavor policy.

    A product-tree flavor key advertises a compiler baseline (`gcc@12.3`).
    Return the newest rendered compiler provider of that family that satisfies
    the baseline (family_min_version for Cray MPICH, exact otherwise), or None
    when no compiler of that family is present. None means the flavor is an
    orphan on this system and must not be emitted as a dangling external.
    """
    flavor_name, _flavor_version = compiler_fragment_name_version(flavor_compiler)
    satisfying = [
        candidate
        for candidate in profile.get("compiler_providers") or []
        if candidate.get("name") == flavor_name
        and is_renderable_external_name_version(candidate.get("name"), candidate.get("version"))
        and compiler_ref_satisfies_flavor(
            compiler_provider_ref(candidate), flavor_compiler, provider
        )
    ]
    if not satisfying:
        return None
    return max(satisfying, key=lambda candidate: version_key(str(candidate["version"])))


def mpi_toolchain_name_for_profile(
    profile: dict[str, Any],
    compiler: str,
    provider_name: str,
    mpi_version: str | None = None,
) -> str:
    compiler_provider = select_compiler_provider(profile, compiler)
    if compiler_provider:
        return mpi_toolchain_name(
            str(compiler_provider["name"]),
            provider_name,
            str(compiler_provider["version"]),
            mpi_version,
        )
    compiler_name, compiler_version = compiler_fragment_name_version(compiler)
    return mpi_toolchain_name(
        compiler_name, provider_name, compiler_version, mpi_version
    )


def compatible_compiler_refs(
    profile: dict[str, Any],
    flavor_compiler: str,
    provider: dict[str, Any] | None,
) -> list[str]:
    """Return observed compilers allowed to consume one physical MPI flavor."""
    return sorted(
        {
            compiler_provider_ref(candidate)
            for candidate in profile.get("compiler_providers") or []
            if is_renderable_external_name_version(
                candidate.get("name"), candidate.get("version")
            )
            and compiler_ref_satisfies_flavor(
                compiler_provider_ref(candidate), flavor_compiler, provider
            )
        },
        key=lambda ref: (
            compiler_fragment_name_version(ref)[0],
            version_key(compiler_fragment_name_version(ref)[1] or ""),
        ),
    )


def select_platform_mpi(
    profile: dict[str, Any],
    provider_name: str,
    version: str | None,
    version_policy: str | None = None,
) -> tuple[dict[str, Any] | None, str | None, str | None]:
    """Pick the provider/version identity a platform lane binds to.

    Returns (record, error_code, error_message). More than one candidate with
    nothing to tell them apart is an input-authoring defect, never a silent
    first-match pick — unless the site declared version_policy: newest.
    """
    candidates = platform_mpi_candidates(profile, provider_name)
    if not candidates:
        return None, None, None
    if version:
        matching = [c for c in candidates if c.get("version") == version]
        if matching:
            return merge_mpi_variant_records(matching), None, None
        available = ", ".join(sorted({str(c.get("version")) for c in candidates}))
        return (
            None,
            "mpi_version_unresolved",
            f"requested platform MPI {provider_name}@{version} is not on this "
            f"system; profile reports version(s): {available}",
        )
    versions = sorted({str(candidate.get("version")) for candidate in candidates})
    if len(versions) == 1:
        return merge_mpi_variant_records(candidates), None, None
    if len(candidates) > 1:
        # Platform families (e.g. Cray PE) publish one coherent product tree,
        # so newest is always safe there; site externals opt in through the
        # declared defaults policy.
        if version_policy == "newest" or all(
            candidate.get("provider_family") == "platform" for candidate in candidates
        ):
            selected_version = max(versions, key=version_key)
            selected = [
                candidate
                for candidate in candidates
                if str(candidate.get("version")) == selected_version
            ]
            return merge_mpi_variant_records(selected), None, None
        available = ", ".join(versions)
        return (
            None,
            "mpi_ambiguous",
            f"platform MPI {provider_name!r} is ambiguous: the profile reports "
            f"versions {available}; set mpi.version to select one, or declare "
            f"mpi.version_policy: newest in defaults",
        )
    return candidates[0], None, None


def merge_mpi_variant_records(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Represent one provider/version with all compiler variants attached.

    Generic Linux profiles often report one MPI version several times: one
    physical install per compiler. Lane planning only needs the provider
    identity, version, and compatible compiler set. Render-time scope code then
    selects the physical variant by lane compiler.
    """
    if len(records) == 1:
        return records[0]
    merged = deepcopy(records[0])
    compilers: set[str] = set()
    modules: list[str] = []
    flavors: dict[str, Any] = {}
    for record in records:
        compiler = record.get("compiler")
        if compiler and is_compiler_fragment(str(compiler)):
            compilers.add(str(compiler))
        compilers.update(
            str(compiler_ref)
            for compiler_ref in (record.get("compatibility") or {}).get("compilers") or []
            if is_compiler_fragment(str(compiler_ref))
        )
        if isinstance(record.get("flavors"), dict):
            flavors.update(record["flavors"])
        for module in record.get("modules") or []:
            if module not in modules:
                modules.append(module)
    if compilers:
        compatibility = dict(merged.get("compatibility") or {})
        compatibility["compilers"] = sorted(compilers)
        merged["compatibility"] = compatibility
    if flavors:
        merged["flavors"] = flavors
    if modules:
        merged["modules"] = modules
    return merged
