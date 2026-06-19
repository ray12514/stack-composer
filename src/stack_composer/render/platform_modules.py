from __future__ import annotations

from typing import Any

from stack_composer.errors import Issue


def platform_module_prereqs_for_lane(
    lane: dict[str, Any], profile: dict[str, Any]
) -> tuple[list[str], list[Issue]]:
    """Modules a lane will need at runtime because it consumes site-external
    providers. Derives from the profile's vendor_cray / compilers_external /
    mpi / gpu_toolkit_modules blocks per v6 § Template Render Context.

    Returns (modules, issues). Issues are emitted when a lane's resolved
    compiler/MPI/GPU-toolkit axis has no corresponding profile facts — i.e.,
    v6 render invariant: 'a generated site-external lane's platform-module
    prerequisites cannot be resolved'.
    """
    issues: list[Issue] = []
    modules: list[str] = []
    seen: set[str] = set()

    def extend(values: list[str]) -> None:
        for value in values:
            if value and value not in seen:
                modules.append(value)
                seen.add(value)

    lane_path = f"lane[{lane['name']}]"
    extend(_compiler_modules(lane, profile, lane_path, issues))
    extend(_mpi_modules(lane, profile, lane_path, issues))
    extend(_gpu_toolkit_modules(lane, profile, lane_path, issues))
    return modules, issues


def _compiler_modules(
    lane: dict[str, Any], profile: dict[str, Any], lane_path: str, issues: list[Issue]
) -> list[str]:
    compiler = lane.get("compiler")
    if not compiler:
        return []
    vendor_cray = profile.get("vendor_cray") or {}
    cray_block = vendor_cray.get(compiler)
    if isinstance(cray_block, dict):
        return list(cray_block.get("modules") or [])
    for external in profile.get("compilers_external") or []:
        if external.get("name") == compiler:
            return list(external.get("modules") or [])
    issues.append(
        Issue(
            "error",
            "unresolved-platform-module",
            f"{lane_path}.compiler",
            f"compiler {compiler!r} is not declared in profile.vendor_cray "
            "or profile.compilers_external",
        )
    )
    return []


def _mpi_modules(
    lane: dict[str, Any], profile: dict[str, Any], lane_path: str, issues: list[Issue]
) -> list[str]:
    provider = lane.get("mpi_provider")
    if not provider:
        return []
    if provider == "cray-mpich":
        flavors = ((profile.get("vendor_cray") or {}).get("cray_mpich") or {}).get("flavors") or {}
        flavor = flavors.get(lane.get("compiler", ""))
        if isinstance(flavor, dict):
            return list(flavor.get("modules") or [])
        issues.append(
            Issue(
                "error",
                "unresolved-platform-module",
                f"{lane_path}.mpi_provider",
                f"cray-mpich flavor for compiler {lane.get('compiler')!r} is missing "
                "from profile.vendor_cray.cray_mpich.flavors",
            )
        )
        return []
    for entry in profile.get("mpi") or []:
        if entry.get("name") == provider:
            return list(entry.get("modules") or [])
    issues.append(
        Issue(
            "error",
            "unresolved-platform-module",
            f"{lane_path}.mpi_provider",
            f"mpi provider {provider!r} is not declared in profile.mpi",
        )
    )
    return []


def _gpu_toolkit_modules(
    lane: dict[str, Any], profile: dict[str, Any], lane_path: str, issues: list[Issue]
) -> list[str]:
    arch = lane.get("gpu_arch")
    if not arch:
        return []
    toolkits = profile.get("gpu_toolkit_modules") or {}
    if arch.startswith("gfx"):
        module = (toolkits.get("rocm") or {}).get("module")
        if module:
            return [module]
        issues.append(
            Issue(
                "error",
                "unresolved-platform-module",
                f"{lane_path}.gpu_arch",
                f"AMD lane gpu_arch={arch!r} has no rocm toolkit module declared "
                "in profile.gpu_toolkit_modules",
            )
        )
        return []
    if arch.startswith("sm_"):
        if lane.get("compiler") == "nvhpc":
            module = (toolkits.get("nvhpc") or {}).get("module")
        else:
            module = (toolkits.get("cudatoolkit") or {}).get("module")
        if module:
            return [module]
        issues.append(
            Issue(
                "error",
                "unresolved-platform-module",
                f"{lane_path}.gpu_arch",
                f"NVIDIA lane gpu_arch={arch!r} has no cudatoolkit/nvhpc toolkit "
                "module declared in profile.gpu_toolkit_modules",
            )
        )
        return []
    issues.append(
        Issue(
            "error",
            "unresolved-platform-module",
            f"{lane_path}.gpu_arch",
            f"unrecognized gpu_arch {arch!r}; expected gfx* or sm_*",
        )
    )
    return []
