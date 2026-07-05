"""Resolved MPI selection, computed once so templates only print.

The MPI externals and toolchains a workspace exposes are a policy decision:
which platform release, which flavor bound to which lane compiler, which
toolchains name the binding. That decision used to run inside the Jinja
templates (via `mpi_external_packages` / `mpi_toolchains` globals). This module
makes it once, up front, keyed by provider name, so the templates become dumb
printers reading `mpi_plan[provider]` and the same resolved data can feed the
render-plan report.
"""

from __future__ import annotations

from typing import Any

from stack_composer.render.scopes import mpi_external_packages, mpi_toolchains


def build_mpi_plan(
    profile: dict[str, Any], rendered_lanes: list[dict[str, Any]]
) -> dict[str, dict[str, Any]]:
    """Resolve MPI packages and toolchains for every provider a lane uses.

    Returns `{provider_name: {"packages": [...], "toolchains": [...]}}`. Only
    providers with a rendered lane appear — there is nothing to render for a
    provider no lane consumes.
    """
    provider_names = sorted(
        {
            str(lane["mpi_provider"])
            for lane in rendered_lanes
            if lane.get("mpi_provider")
        }
    )
    plan: dict[str, dict[str, Any]] = {}
    for name in provider_names:
        plan[name] = {
            "packages": mpi_external_packages(profile, name, rendered_lanes),
            "toolchains": mpi_toolchains(profile, rendered_lanes, name),
        }
    return plan
