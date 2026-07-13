from __future__ import annotations

from typing import Any

from stack_composer.render.fabric import (
    observed_fabric_userspace,
    selected_common_scope_fabric_userspace,
    unselected_fabric_userspace,
)
from stack_composer.render.platform import platform_plan
from stack_composer.render.release import ReleaseVars


def render_plan_report(
    *,
    profile: dict[str, Any],
    stack: dict[str, Any],
    deployment: dict[str, Any],
    lanes: list[dict[str, Any]],
    skipped_builds: list[dict[str, str]],
    applied_narrowing: dict[str, Any] | None,
    release_vars: ReleaseVars,
    module_plan: dict[str, Any],
    shared_exposure_plan: dict[str, Any],
    rendered_scopes: list[str],
) -> dict[str, Any]:
    """Return the explicit decision report for one render.

    This report is the first public artifact of the simplified renderer seam.
    It describes what the resolver already decided before file emitters write
    Spack YAML, modulefiles, or manifests.
    """
    return {
        "schema_version": 1,
        "system": {
            "name": profile["system"]["name"],
            "family": profile["system"].get("family"),
        },
        "stack": {
            "name": stack["name"],
            "templates": stack.get("templates"),
        },
        "release": {
            "release_tag": release_vars.release_tag,
            "rendered_at": release_vars.rendered_at,
            "source_repo": {
                "url": release_vars.source_repo.url,
                "commit": release_vars.source_repo.commit,
                "dirty": release_vars.source_repo.dirty,
            },
        },
        "deployment_roots": deployment.get("roots", {}),
        "rendered_scopes": rendered_scopes,
        "lanes": [lane_report(lane) for lane in lanes],
        "platform_plan": platform_plan(profile, stack),
        "network_plan": network_plan(profile, stack, lanes),
        "module_plan": module_plan,
        "shared_exposure": shared_exposure_plan,
        "skipped_builds": skipped_builds,
        "applied_narrowing": applied_narrowing,
    }


def lane_report(lane: dict[str, Any]) -> dict[str, Any]:
    report = {
        "name": lane["name"],
        "lane": lane["lane"],
        "kind": lane["kind"],
        "source_build": lane["source_build"],
        "compiler": lane["compiler"],
        "target": lane["target"],
        "runtime_node_type": lane["runtime_node_type"],
        "env_path": lane["env_path"],
        "view_root": lane["view_root"],
        "package_module_root": lane["package_module_root"],
        "spec_source": lane["spec_source"],
        "publish": lane.get("publish", True),
    }
    for key in (
        "compiler_ref",
        "compiler_axis",
        "compiler_version",
        "vendor_scope",
        "mpi_provider",
        "mpi_source",
        "mpi_version",
        "toolchain",
        "gpu_selector",
        "gpu_arch",
    ):
        if key in lane:
            report[key] = lane[key]
    return report


def network_plan(
    profile: dict[str, Any], stack: dict[str, Any], lanes: list[dict[str, Any]]
) -> dict[str, Any]:
    """Summarize MPI/toolchain and fabric/runtime decisions."""
    providers: dict[tuple[str, str | None, str | None], dict[str, Any]] = {}
    for lane in lanes:
        provider = lane.get("mpi_provider")
        if not provider:
            continue
        key = (
            str(provider),
            lane.get("mpi_version"),
            lane.get("mpi_source"),
        )
        entry = providers.setdefault(
            key,
            {
                "provider": provider,
                "version": lane.get("mpi_version"),
                "source": lane.get("mpi_source"),
                "toolchains": [],
            },
        )
        toolchain = lane.get("toolchain")
        if toolchain and not any(item["name"] == toolchain for item in entry["toolchains"]):
            entry["toolchains"].append(
                {
                    "name": toolchain,
                    "compiler": lane["compiler"],
                    "compiler_ref": lane.get("compiler_ref"),
                }
            )
    provider_entries = sorted(
        providers.values(),
        key=lambda item: (
            str(item["provider"]),
            str(item.get("version") or ""),
            str(item.get("source") or ""),
        ),
    )
    for entry in provider_entries:
        entry["toolchains"].sort(key=lambda item: item["name"])

    fabric_mode = (stack.get("externals") or {}).get("fabric_userspace", "prefer_platform")
    selected_fabric = selected_common_scope_fabric_userspace(profile, fabric_mode)
    return {
        "mpi_providers": provider_entries,
        "fabric_userspace": {
            "mode": fabric_mode,
            "observed": observed_fabric_userspace(profile),
            "rendered_common_externals": selected_fabric,
            "not_rendered": unselected_fabric_userspace(profile, selected_fabric),
        },
    }
