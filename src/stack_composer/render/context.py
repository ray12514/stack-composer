from __future__ import annotations

from types import MappingProxyType
from typing import Any

from stack_composer.render.release import ReleaseVars, release_vars_dict


def build_render_context(
    *,
    base_context: dict[str, Any],
    rendered_lanes: list[dict[str, Any]],
    skipped_builds: list[dict[str, str]],
    applied_narrowing: dict[str, Any] | None,
    release_vars: ReleaseVars,
    renderer_identity: dict[str, str],
) -> MappingProxyType:
    profile = base_context["profile"]
    context = {
        "profile": profile,
        "stack": base_context["stack"],
        "defaults": base_context["defaults"],
        "package_repos": base_context["package_repos"],
        "spec_sources": base_context["spec_sources"],
        "rendered_lanes": rendered_lanes,
        "skipped_builds": skipped_builds,
        "applied_narrowing": applied_narrowing,
        "release_vars": release_vars_dict(release_vars, profile["system"]["name"]),
        "renderer_identity": renderer_identity,
    }
    return MappingProxyType(context)
