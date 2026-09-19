"""Resolved compiler-external selection, computed once so templates only print.

Which compiler externals land in which vendor scope is a selection decision
(provider family -> scope, plus renderability). It used to run inside the
vendor `compiler_packages` macro via the `compiler_external_packages` global.
This module resolves it once, keyed by the vendor scope each lane uses, so the
macro becomes a dumb printer reading `compiler_plan[scope]`.
"""

from __future__ import annotations

from typing import Any

from stack_composer.render.records import Lane
from stack_composer.render.scopes import compiler_external_packages


def build_compiler_plan(
    profile: dict[str, Any],
    stack: dict[str, Any],
    rendered_lanes: list[Lane],
) -> dict[str, list[dict[str, Any]]]:
    """Resolve compiler externals for every vendor scope a lane renders into.

    Returns `{vendor_scope: [packages]}`. Only scopes a lane uses appear —
    there is nothing to render for a scope no lane occupies.
    """
    scopes = sorted(
        {str(lane["vendor_scope"]) for lane in rendered_lanes if lane.get("vendor_scope")}
    )
    return {scope: compiler_external_packages(profile, stack, scope) for scope in scopes}
