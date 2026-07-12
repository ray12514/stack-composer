from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from jinja2 import Environment

from stack_composer.errors import ValidationFailed
from stack_composer.model.package_set import expand_specs_for_lane
from stack_composer.render.platform_modules import platform_module_prereqs_for_lane
from stack_composer.render.scopes import scopes_for_lane

_SPEC_NAME_SPLIT = re.compile(r"[@ +~%^]")


def spec_package_name(spec: str) -> str:
    return _SPEC_NAME_SPLIT.split(spec.strip(), maxsplit=1)[0]


def render_lane_environment(
    *,
    template_dir: Path,
    pending: Path,
    env: Environment,
    ctx: dict[str, Any],
    lane: dict[str, Any],
) -> None:
    prereqs, prereq_issues = platform_module_prereqs_for_lane(lane, ctx["profile"])
    if prereq_issues:
        raise ValidationFailed(prereq_issues)
    specs = expand_specs_for_lane(ctx["spec_sources"][lane["source_build"]], lane)
    lane_ctx = dict(ctx)
    lane_ctx.update(
        {
            "lane": lane,
            "specs": specs,
            "scopes": scopes_for_lane(lane, ctx["stack"], ctx["profile"]),
            "view_root": lane["view_root"],
            # The projected view package-module generation reads (use_view):
            # explicit roots get clean {name}/{version} names, everything else
            # falls back to a hash-qualified projection and generates no module.
            "module_view_root": lane["view_root"] + "-modules",
            "view_projection_names": sorted({spec_package_name(spec) for spec in specs}),
            "platform_module_prereqs": prereqs,
        }
    )
    src = template_dir / "environments" / lane["kind"] / "spack.yaml.j2"
    dst = pending / lane["env_path"] / "spack.yaml"
    dst.parent.mkdir(parents=True, exist_ok=True)
    template_name = src.relative_to(template_dir).as_posix()
    dst.write_text(env.get_template(template_name).render(lane_ctx), encoding="utf-8")
