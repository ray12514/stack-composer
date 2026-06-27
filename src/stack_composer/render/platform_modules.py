from __future__ import annotations

from typing import Any

from stack_composer.errors import Issue


def platform_module_prereqs_for_lane(
    lane: dict[str, Any], profile: dict[str, Any]
) -> tuple[list[str], list[Issue]]:
    """Modules a lane will need at runtime because it consumes site-external
    providers. Derives from the profile's compiler_providers / mpi_providers /
    gpu_toolkit_modules blocks.

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
    for provider in profile.get("compiler_providers") or []:
        if provider.get("name") == compiler:
            return list(provider.get("modules") or [])
    issues.append(
        Issue(
            "error",
            "unresolved-platform-module",
            f"{lane_path}.compiler",
            f"compiler {compiler!r} is not declared in profile.compiler_providers",
        )
    )
    return []


def _mpi_modules(
    lane: dict[str, Any], profile: dict[str, Any], lane_path: str, issues: list[Issue]
) -> list[str]:
    provider = lane.get("mpi_provider")
    if not provider:
        return []
    # Build-from-source MPI has no platform module prerequisite; it is built by
    # Spack and pinned as the provider preference in the common scope.
    if lane.get("mpi_source") != "platform":
        return []
    entry = next(
        (p for p in profile.get("mpi_providers") or [] if p.get("name") == provider), None
    )
    if entry is None:
        issues.append(
            Issue(
                "error",
                "unresolved-platform-module",
                f"{lane_path}.mpi_provider",
                f"mpi provider {provider!r} is not declared in profile.mpi_providers",
            )
        )
        return []
    flavors = entry.get("flavors")
    if isinstance(flavors, dict):
        flavor = flavors.get(lane.get("compiler", ""))
        if isinstance(flavor, dict):
            return list(flavor.get("modules") or [])
        issues.append(
            Issue(
                "error",
                "unresolved-platform-module",
                f"{lane_path}.mpi_provider",
                f"{provider} flavor for compiler {lane.get('compiler')!r} is missing "
                "from profile.mpi_providers[].flavors",
            )
        )
        return []
    return list(entry.get("modules") or [])


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
        module = (toolkits.get("cudatoolkit") or {}).get("module")
        if module:
            return [module]
        issues.append(
            Issue(
                "error",
                "unresolved-platform-module",
                f"{lane_path}.gpu_arch",
                f"NVIDIA lane gpu_arch={arch!r} has no CUDA toolkit "
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
