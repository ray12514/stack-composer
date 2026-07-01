"""Resolved MPI identity, shared by lane planning and scope rendering.

One module answers "which mpi_providers entry does this provider name mean on
this profile" and "what toolchain name does this compiler/provider pairing
get", so the spec decoration in plan.py and the rendered toolchains.yaml keys
in scopes.py cannot drift apart.
"""

from __future__ import annotations

import re
from typing import Any

from stack_composer.render.spack_specs import (
    is_absolute_prefix,
    is_compiler_fragment,
    is_renderable_external_name_version,
)

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


def mpi_provider_is_ambiguous(profile: dict[str, Any], provider_name: str) -> bool:
    """More than one profile entry answers to this provider name."""
    return len(platform_mpi_candidates(profile, provider_name)) > 1


def slug_token(value: object) -> str:
    """Return a Spack-spec-token-safe identifier fragment.

    Toolchain names are referenced as `%name` in root specs, so do not preserve
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


def select_compiler_provider(
    profile: dict[str, Any], compiler: str
) -> dict[str, Any] | None:
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
            (provider for provider in candidates if provider.get("version") == wanted_version),
            None,
        )
    return candidates[0] if candidates else None


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
    compiler_name, _ = compiler_fragment_name_version(compiler)
    return mpi_toolchain_name(compiler_name, provider_name, None, mpi_version)


def select_platform_mpi(
    profile: dict[str, Any], provider_name: str, version: str | None
) -> tuple[dict[str, Any] | None, str | None, str | None]:
    """Pick the one mpi_providers entry a platform lane binds to.

    Returns (record, error_code, error_message). More than one candidate with
    nothing to tell them apart is an input-authoring defect, never a silent
    first-match pick.
    """
    candidates = platform_mpi_candidates(profile, provider_name)
    if not candidates:
        return None, None, None
    if version:
        matching = [c for c in candidates if c.get("version") == version]
        if len(matching) == 1:
            return matching[0], None, None
        available = ", ".join(sorted({str(c.get("version")) for c in candidates}))
        return (
            None,
            "mpi_version_unresolved",
            f"requested platform MPI {provider_name}@{version} is not on this "
            f"system; profile reports version(s): {available}",
        )
    if len(candidates) > 1:
        available = ", ".join(sorted({str(c.get("version")) for c in candidates}))
        return (
            None,
            "mpi_ambiguous",
            f"platform MPI {provider_name!r} is ambiguous: the profile reports "
            f"versions {available}; set mpi.version to select one",
        )
    return candidates[0], None, None
