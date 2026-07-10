from __future__ import annotations

import re
import shutil
from pathlib import Path
from typing import Any

from stack_composer import __version__
from stack_composer.errors import Issue, ValidationFailed
from stack_composer.model.profile import load_profile
from stack_composer.model.stack import load_defaults
from stack_composer.render.fabric import (
    selected_common_scope_fabric_userspace,
    unselected_fabric_userspace,
)
from stack_composer.render.gpu import cuda_external_packages, rocm_external_packages
from stack_composer.render.mpi import (
    compiler_provider_ref,
    merge_mpi_variant_records,
    mpi_toolchain_name_for_profile,
    select_compiler_provider,
    select_flavor_compiler,
)
from stack_composer.render.plan import (
    preferred_baseline_compiler_provider,
    resolve_mpi,
)
from stack_composer.render.platform import (
    classify_system_externals,
    is_platform_selected_external,
    platform_family,
)
from stack_composer.render.release import ReleaseVars
from stack_composer.render.scopes import (
    add_external,
    compiler_external,
    compiler_toolchain_entries,
    mpi_provider_externals,
    mpi_provider_variants,
    mpi_toolchain_compilers,
    mpi_toolchains,
)
from stack_composer.render.spack_specs import (
    is_absolute_prefix,
    is_renderable_external_name_version,
)
from stack_composer.render.versioning import version_key
from stack_composer.yaml_io import write_yaml

_TOKEN_RE = re.compile(r"[^A-Za-z0-9_.+-]+")


def render_static_catalog(
    *,
    profile_path: Path,
    templates_root: Path,
    template_set_name: str,
    release_vars: ReleaseVars,
) -> Path:
    """Render include-ready Spack config scopes from a Cluster Inspector profile.

    This is intentionally separate from the full environment renderer: no stack
    model, no deployment roots, no lane materialization, and no probing.
    """
    profile, profile_issues = load_profile(profile_path)
    defaults_path = templates_root / template_set_name / "defaults.yaml"
    defaults, defaults_issues = load_defaults(defaults_path)
    issues = [*profile_issues, *defaults_issues]
    if issues:
        raise ValidationFailed(issues)

    system = str((profile.get("system") or {}).get("name") or "unknown-system")
    workspace = Path(release_vars.output_root) / system / "static" / release_vars.release_tag
    if workspace.exists() and not release_vars.overwrite:
        raise ValidationFailed(
            [
                Issue(
                    "error",
                    "static-output-exists",
                    str(workspace),
                    "static catalog output already exists; pass --overwrite to replace it",
                )
            ]
        )

    pending = workspace.with_name(workspace.name + ".rendering")
    if pending.exists():
        shutil.rmtree(pending)
    pending.mkdir(parents=True, exist_ok=True)

    catalog = build_static_catalog(
        profile=profile,
        defaults=defaults,
        workspace=pending,
        published_workspace=workspace,
        release_vars=release_vars,
        template_set_name=template_set_name,
    )
    write_static_catalog(pending, catalog)

    if workspace.exists():
        shutil.rmtree(workspace)
    pending.rename(workspace)
    return workspace


def build_static_catalog(
    *,
    profile: dict[str, Any],
    defaults: dict[str, Any],
    workspace: Path,
    published_workspace: Path,
    release_vars: ReleaseVars,
    template_set_name: str,
) -> dict[str, Any]:
    scopes: list[dict[str, Any]] = []
    reports: dict[str, Any] = {
        "compiler_scopes": [],
        "mpi_scopes": [],
        "gpu_scopes": [],
        "common_externals": [],
        "platform_externals": [],
        "not_rendered": [],
    }

    compiler_scopes, compiler_default = build_compiler_scopes(profile, workspace)
    scopes.extend(compiler_scopes)
    reports["compiler_scopes"] = [scope_report(scope) for scope in compiler_scopes]

    common_scope, common_report, common_not_rendered = build_common_scope(
        profile, defaults, workspace
    )
    if common_scope:
        scopes.append(common_scope)
    reports["common_externals"] = common_report
    reports["not_rendered"].extend(common_not_rendered)

    platform_scope, platform_report, platform_not_rendered = build_platform_scope(
        profile, workspace
    )
    if platform_scope:
        scopes.append(platform_scope)
    reports["platform_externals"] = platform_report
    reports["not_rendered"].extend(platform_not_rendered)

    mpi_scopes = build_mpi_scopes(profile, workspace)
    scopes.extend(mpi_scopes)
    reports["mpi_scopes"] = [scope_report(scope) for scope in mpi_scopes]

    gpu_scopes = build_gpu_scopes(profile, workspace)
    scopes.extend(gpu_scopes)
    reports["gpu_scopes"] = [scope_report(scope) for scope in gpu_scopes]

    recommended_mpi_provider, _recommended_mpi_source = resolve_mpi(
        profile, defaults, {}
    )
    recommendations = recommendations_for(
        defaults=defaults,
        preferred_mpi_provider=recommended_mpi_provider,
        compiler_scopes=compiler_scopes,
        compiler_default=compiler_default,
        mpi_scopes=mpi_scopes,
        gpu_scopes=gpu_scopes,
    )
    manifest = {
        "schema_version": 1,
        "kind": "static-platform-catalog",
        "system": profile.get("system") or {},
        "template_set": template_set_name,
        "release": release_vars.release_tag,
        "rendered_at": release_vars.rendered_at,
        "renderer": {
            "name": "stack-composer",
            "version": __version__,
        },
        "source": {
            "repo": release_vars.source_repo.url,
            "commit": release_vars.source_repo.commit,
            "dirty": release_vars.source_repo.dirty,
        },
        "scope_root": str(published_workspace / "scopes"),
        "recommendations": recommendations,
        "scopes": [manifest_scope(scope) for scope in scopes],
    }
    plan = {
        "schema_version": 1,
        "system": (profile.get("system") or {}).get("name"),
        "release": release_vars.release_tag,
        "recommendations": recommendations,
        **reports,
    }
    return {"manifest": manifest, "plan": plan, "scopes": scopes}


def build_compiler_scopes(
    profile: dict[str, Any], workspace: Path
) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    scopes = []
    rendered_providers: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for provider in profile.get("compiler_providers") or []:
        name = provider.get("name")
        version = provider.get("version")
        prefix = provider.get("prefix")
        if not (
            is_renderable_external_name_version(name, version)
            and is_absolute_prefix(prefix)
        ):
            continue
        key = (str(name), str(version))
        if key in seen:
            continue
        seen.add(key)
        scope_rel = Path("scopes") / "compilers" / path_token(name) / path_token(version)
        packages = {
            str(name): {
                "buildable": False,
                "externals": [compiler_external(provider)],
            }
        }
        toolchain_name = path_token(f"{name}-{version}")
        toolchains = {toolchain_name: compiler_toolchain_entries(provider)}
        scope = {
            "kind": "compiler",
            "name": str(name),
            "version": str(version),
            "compiler_ref": compiler_provider_ref(provider),
            "path": scope_rel,
            "absolute_path": workspace / scope_rel,
            "packages": packages,
            "toolchains": toolchains,
            "modules": provider.get("modules") or [],
        }
        scopes.append(scope)
        rendered_providers.append(provider)
    gcc_candidates = [
        provider for provider in rendered_providers if provider.get("name") == "gcc"
    ]
    default_provider = (
        preferred_baseline_compiler_provider(gcc_candidates)
        if gcc_candidates
        else (rendered_providers[0] if rendered_providers else None)
    )
    return scopes, default_provider


def build_mpi_scopes(profile: dict[str, Any], workspace: Path) -> list[dict[str, Any]]:
    scopes: list[dict[str, Any]] = []
    grouped: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for provider in profile.get("mpi_providers") or []:
        if not is_renderable_external_name_version(provider.get("name"), provider.get("version")):
            continue
        name = str(provider.get("name"))
        version = str(provider.get("version"))
        family = str(provider.get("provider_family") or "")
        grouped.setdefault((name, version, family), []).append(provider)

    seen_paths: set[str] = set()
    for (name, version, family), records in sorted(
        grouped.items(), key=lambda item: (item[0][0], version_key(item[0][1]))
    ):
        provider = merge_mpi_variant_records(records)
        for compiler_provider in mpi_scope_compilers(profile, provider):
            compiler_ref = compiler_provider_ref(compiler_provider)
            toolchain = mpi_toolchain_name_for_profile(profile, compiler_ref, name, version)
            lane = {
                "compiler": compiler_provider["name"],
                "compiler_ref": compiler_ref,
                "mpi_provider": name,
                "mpi_version": version,
                "mpi_source": "platform",
                "toolchain": toolchain,
            }
            packages = mpi_packages_mapping(profile, provider, [lane])
            toolchains = toolchains_mapping(mpi_toolchains(profile, [lane], name))
            if not packages:
                continue
            compiler_axis = compiler_scope_axis(compiler_provider)
            scope_rel = (
                Path("scopes")
                / "mpi"
                / path_token(name)
                / path_token(version)
                / compiler_axis
            )
            if scope_rel.as_posix() in seen_paths:
                continue
            seen_paths.add(scope_rel.as_posix())
            scopes.append(
                {
                    "kind": "mpi",
                    "name": name,
                    "version": version,
                    "provider_family": family,
                    "compiler_ref": compiler_ref,
                    "toolchain": toolchain,
                    "path": scope_rel,
                    "absolute_path": workspace / scope_rel,
                    "packages": packages,
                    "toolchains": toolchains,
                    "modules": sorted(
                        module
                        for package in packages.values()
                        for ext in package.get("externals", [])
                        for module in ext.get("modules", [])
                    ),
                }
            )
    return scopes


def mpi_scope_compilers(
    profile: dict[str, Any], provider: dict[str, Any]
) -> list[dict[str, Any]]:
    compilers: dict[str, dict[str, Any]] = {}
    for compiler in mpi_toolchain_compilers(provider):
        compiler_provider = (
            select_flavor_compiler(profile, compiler, provider)
            if provider.get("flavors")
            else select_compiler_provider(profile, compiler)
        )
        if compiler_provider:
            compilers[compiler_provider_ref(compiler_provider)] = compiler_provider
    return sorted(
        compilers.values(),
        key=lambda provider: (str(provider.get("name")), version_key(str(provider.get("version")))),
    )


def mpi_packages_mapping(
    profile: dict[str, Any],
    provider: dict[str, Any],
    lanes: list[dict[str, Any]],
) -> dict[str, Any]:
    packages: dict[str, Any] = {}
    name = provider.get("name")
    externals = mpi_provider_externals(profile, provider, lanes)
    if not externals:
        return {}
    package: dict[str, Any] = {"buildable": False, "externals": externals}
    variants = mpi_provider_variants(str(name))
    if variants:
        package["variants"] = variants
    packages[str(name)] = package
    packages["mpi"] = {"buildable": False, "require": [str(name)]}
    return packages


def build_gpu_scopes(profile: dict[str, Any], workspace: Path) -> list[dict[str, Any]]:
    scopes = []
    for family, output_name, builder in (
        ("cudatoolkit", "cuda", cuda_external_packages),
        ("rocm", "rocm", rocm_external_packages),
    ):
        for toolkit in sorted(
            (profile.get("gpu_toolkit_modules") or {}).get(family) or [],
            key=lambda item: version_key(str(item.get("version") or "")),
        ):
            version = toolkit.get("version")
            if not version:
                continue
            packages = packages_mapping(builder(toolkit))
            if not packages:
                continue
            scope_rel = Path("scopes") / "gpu" / output_name / path_token(version)
            scopes.append(
                {
                    "kind": "gpu",
                    "name": output_name,
                    "version": str(version),
                    "path": scope_rel,
                    "absolute_path": workspace / scope_rel,
                    "packages": packages,
                    "toolchains": {},
                    "modules": [toolkit["module"]] if toolkit.get("module") else [],
                }
            )
    return scopes


def build_common_scope(
    profile: dict[str, Any], defaults: dict[str, Any], workspace: Path
) -> tuple[dict[str, Any] | None, list[dict[str, Any]], list[dict[str, Any]]]:
    external_policy = defaults.get("externals") or {}
    fabric_policy = external_policy.get("fabric_userspace", "prefer_platform")
    packages: dict[str, dict[str, Any]] = {}
    selected_fabric = selected_common_scope_fabric_userspace(profile, fabric_policy)
    for userspace in selected_fabric:
        add_external(packages, userspace)

    for external in profile.get("system_externals") or []:
        name = external.get("name")
        if external_policy.get(name) != "system":
            continue
        if is_platform_selected_external(profile, external):
            continue
        add_external(packages, external)

    not_rendered = unselected_fabric_userspace(profile, selected_fabric)
    if not packages:
        return None, [], not_rendered

    scope_rel = Path("scopes") / "common"
    scope = {
        "kind": "common",
        "name": "common",
        "path": scope_rel,
        "absolute_path": workspace / scope_rel,
        "packages": packages_mapping(list(packages.values())),
        "toolchains": {},
        "modules": [],
    }
    rendered = [
        plan_entry_from_package(name, pkg)
        for name, pkg in scope["packages"].items()
    ]
    return scope, rendered, not_rendered


def build_platform_scope(
    profile: dict[str, Any], workspace: Path
) -> tuple[dict[str, Any] | None, list[dict[str, Any]], list[dict[str, Any]]]:
    selected, ignored = classify_system_externals(profile)
    packages: dict[str, dict[str, Any]] = {}
    for external in selected:
        if is_platform_selected_external(profile, external):
            add_external(packages, external)
    if not packages:
        return None, [], ignored
    family = platform_family(profile) or "platform"
    scope_rel = Path("scopes") / "platform" / path_token(family)
    scope = {
        "kind": "platform",
        "name": family,
        "path": scope_rel,
        "absolute_path": workspace / scope_rel,
        "packages": packages_mapping(list(packages.values())),
        "toolchains": {},
        "modules": [],
    }
    rendered = [plan_entry_from_package(name, pkg) for name, pkg in scope["packages"].items()]
    return scope, rendered, ignored


def write_static_catalog(workspace: Path, catalog: dict[str, Any]) -> None:
    for scope in catalog["scopes"]:
        path = scope["absolute_path"]
        if scope.get("packages"):
            write_yaml(path / "packages.yaml", {"packages": scope["packages"]})
        if scope.get("toolchains"):
            write_yaml(path / "toolchains.yaml", {"toolchains": scope["toolchains"]})
    write_yaml(workspace / "manifest.yaml", catalog["manifest"])
    write_yaml(workspace / "reports" / "static-plan.yaml", catalog["plan"])
    write_readme(workspace / "README.md", catalog["manifest"])


def write_readme(path: Path, manifest: dict[str, Any]) -> None:
    recommended = manifest.get("recommendations") or {}
    includes = recommended.get("include") or []
    catalog_root = Path(str(manifest["scope_root"])).parent
    lines = [
        f"# Static Spack platform catalog: {manifest['system'].get('name', 'unknown')}",
        "",
        "This catalog is generated from Cluster Inspector profile facts. It is meant for",
        "manual Spack environments that want maintainer-provided platform configuration",
        "without using the full curated stack renderer.",
        "",
        "Recommended include block:",
        "",
        "```yaml",
        "spack:",
        "  include:",
    ]
    lines.extend(
        f"  - {item if Path(item).is_absolute() else catalog_root / item}"
        for item in includes
    )
    lines.extend(
        [
            "  specs:",
            "  - hdf5 +mpi",
            "```",
            "",
            "See `manifest.yaml` for all scopes and defaults.",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def recommendations_for(
    *,
    defaults: dict[str, Any],
    preferred_mpi_provider: str | None,
    compiler_scopes: list[dict[str, Any]],
    compiler_default: dict[str, Any] | None,
    mpi_scopes: list[dict[str, Any]],
    gpu_scopes: list[dict[str, Any]],
) -> dict[str, Any]:
    compiler_scope = select_compiler_scope(defaults, compiler_scopes, compiler_default)
    mpi_scope = select_mpi_scope(
        preferred_mpi_provider, mpi_scopes, compiler_scope
    )
    gpu_recommendations = select_gpu_scopes(gpu_scopes)

    include = []
    include.append("scopes/common")
    if compiler_scope:
        include.append(scope_path_str(compiler_scope))
    if mpi_scope:
        include.append(scope_path_str(mpi_scope))
    include.extend(scope_path_str(scope) for scope in gpu_recommendations)

    return {
        "include": include,
        "compiler": recommendation_entry(compiler_scope),
        "mpi": recommendation_entry(mpi_scope),
        "gpu": [recommendation_entry(scope) for scope in gpu_recommendations],
    }


def select_compiler_scope(
    defaults: dict[str, Any],
    compiler_scopes: list[dict[str, Any]],
    compiler_default: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if not compiler_scopes:
        return None
    requested = defaults.get("compilers")
    if isinstance(requested, list) and requested:
        for name in requested:
            match = next((scope for scope in compiler_scopes if scope["name"] == name), None)
            if match:
                return match
    if compiler_default:
        ref = compiler_provider_ref(compiler_default)
        match = next((scope for scope in compiler_scopes if scope.get("compiler_ref") == ref), None)
        if match:
            return match
    return compiler_scopes[0]


def select_mpi_scope(
    preferred_provider: str | None,
    mpi_scopes: list[dict[str, Any]],
    compiler_scope: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if not mpi_scopes:
        return None
    candidates = [
        scope
        for scope in mpi_scopes
        if not preferred_provider or scope["name"] == preferred_provider
    ]
    if not candidates:
        candidates = mpi_scopes
    if compiler_scope:
        compiler_ref = compiler_scope.get("compiler_ref")
        matching = [scope for scope in candidates if scope.get("compiler_ref") == compiler_ref]
        if matching:
            candidates = matching
    # When the preferred provider is not reported, the platform-provided MPI
    # wins by provider-family fact (never by vendor name), matching the lane
    # renderer's selection order.
    platform = [scope for scope in candidates if scope.get("provider_family") == "platform"]
    if platform:
        candidates = platform
    return max(candidates, key=lambda scope: version_key(str(scope.get("version") or "")))


def select_gpu_scopes(gpu_scopes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_name: dict[str, list[dict[str, Any]]] = {}
    for scope in gpu_scopes:
        by_name.setdefault(scope["name"], []).append(scope)
    return [
        max(scopes, key=lambda scope: version_key(str(scope.get("version") or "")))
        for _name, scopes in sorted(by_name.items())
    ]


def packages_mapping(packages: list[dict[str, Any]]) -> dict[str, Any]:
    mapped: dict[str, Any] = {}
    for package in packages:
        name = package.get("name")
        if not name:
            continue
        body = {
            key: value
            for key, value in package.items()
            if key != "name" and value not in (None, [])
        }
        mapped[str(name)] = body
    return mapped


def toolchains_mapping(toolchains: list[dict[str, Any]]) -> dict[str, Any]:
    return {toolchain["name"]: toolchain["entries"] for toolchain in toolchains}


def manifest_scope(scope: dict[str, Any]) -> dict[str, Any]:
    entry = {
        "kind": scope["kind"],
        "path": scope_path_str(scope),
    }
    for key in ("name", "version", "compiler_ref", "toolchain"):
        if scope.get(key):
            entry[key] = scope[key]
    return entry


def scope_report(scope: dict[str, Any]) -> dict[str, Any]:
    entry = manifest_scope(scope)
    modules = scope.get("modules") or []
    if modules:
        entry["modules"] = modules
    return entry


def recommendation_entry(scope: dict[str, Any] | None) -> dict[str, Any] | None:
    if not scope:
        return None
    return manifest_scope(scope)


def scope_path_str(scope: dict[str, Any]) -> str:
    return scope["path"].as_posix()


def compiler_scope_axis(provider: dict[str, Any]) -> str:
    return path_token(f"{provider['name']}-{provider['version']}")


def path_token(value: object) -> str:
    token = _TOKEN_RE.sub("-", str(value)).strip("-")
    return token or "unknown"


def plan_entry_from_package(name: str, package: dict[str, Any]) -> dict[str, Any]:
    externals = package.get("externals") or []
    return {
        "name": name,
        "externals": [
            {
                key: value
                for key, value in external.items()
                if key in {"spec", "prefix", "modules"} and value not in (None, [])
            }
            for external in externals
        ],
    }
