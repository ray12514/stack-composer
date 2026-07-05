"""Resolved common-scope selection, computed once so templates only print.

The common Spack scope carries the workspace-wide externals (fabric userspace +
policy-allowed system externals), the default MPI provider preference, and the
target preference. Those decisions used to run inside the common template
(the `common_external_packages` global plus inline `rendered_lanes` filtering).
This module makes them once so the template becomes a dumb printer.
"""

from __future__ import annotations

from typing import Any

from stack_composer.render.scopes import common_external_packages


def build_common_plan(
    profile: dict[str, Any],
    stack: dict[str, Any],
    rendered_lanes: list[dict[str, Any]],
) -> dict[str, Any]:
    """Resolve the common scope's externals, default MPI provider, and target.

    `default_mpi_provider` preserves the existing "first lane's provider"
    behavior — relocated here so it is visible and testable, not changed.
    """
    lane_providers = [
        lane["mpi_provider"] for lane in rendered_lanes if lane.get("mpi_provider")
    ]
    return {
        "externals": common_external_packages(profile, stack),
        "default_mpi_provider": lane_providers[0] if lane_providers else None,
        "target_prefer": rendered_lanes[0]["target"] if rendered_lanes else None,
    }
