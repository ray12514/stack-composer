from __future__ import annotations

from types import MappingProxyType
from typing import Any

from stack_composer.render.records import AppliedNarrowing, Lane, SkippedBuild
from stack_composer.render.release import ReleaseVars, release_vars_dict


def build_render_context(
    *,
    base_context: dict[str, Any],
    rendered_lanes: list[Lane],
    skipped_builds: list[SkippedBuild],
    applied_narrowing: AppliedNarrowing | None,
    module_plan: dict[str, Any],
    mpi_plan: dict[str, Any],
    gpu_plan: dict[str, Any],
    common_plan: dict[str, Any],
    compiler_plan: dict[str, Any],
    release_vars: ReleaseVars,
    renderer_identity: dict[str, str],
) -> MappingProxyType[str, Any]:
    profile = base_context["profile"]
    context = {
        "profile": profile,
        "stack": base_context["stack"],
        "deployment": base_context["deployment"],
        "defaults": base_context["defaults"],
        "package_repos": base_context["package_repos"],
        "spec_sources": base_context["spec_sources"],
        "rendered_lanes": rendered_lanes,
        "skipped_builds": skipped_builds,
        "applied_narrowing": applied_narrowing,
        "module_plan": module_plan,
        "mpi_plan": mpi_plan,
        "gpu_plan": gpu_plan,
        "common_plan": common_plan,
        "compiler_plan": compiler_plan,
        "release_vars": release_vars_dict(release_vars, profile["system"]["name"]),
        "renderer_identity": renderer_identity,
    }
    return MappingProxyType(context)
