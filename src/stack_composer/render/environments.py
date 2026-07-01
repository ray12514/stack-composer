from __future__ import annotations

from pathlib import Path
from typing import Any

from jinja2 import Environment

from stack_composer.errors import ValidationFailed
from stack_composer.model.package_set import expand_specs_for_lane
from stack_composer.render.platform_modules import platform_module_prereqs_for_lane
from stack_composer.render.scopes import scopes_for_lane


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
    lane_ctx = dict(ctx)
    lane_ctx.update(
        {
            "lane": lane,
            "specs": expand_specs_for_lane(ctx["spec_sources"][lane["source_build"]], lane),
            "scopes": scopes_for_lane(lane, ctx["stack"], ctx["profile"]),
            "view_root": lane["view_root"],
            "platform_module_prereqs": prereqs,
            "lane_packages": packages_for_lane(lane),
        }
    )
    src = template_dir / "environments" / lane["kind"] / "spack.yaml.j2"
    dst = pending / lane["env_path"] / "spack.yaml"
    dst.parent.mkdir(parents=True, exist_ok=True)
    template_name = src.relative_to(template_dir).as_posix()
    dst.write_text(env.get_template(template_name).render(lane_ctx), encoding="utf-8")


def packages_for_lane(lane: dict[str, Any]) -> dict[str, Any]:
    packages: dict[str, Any] = {"all": {"require": [f"%{lane['compiler']}"]}}
    mpi_requirement = mpi_requirement_for_lane(lane)
    if mpi_requirement:
        packages["mpi"] = {"buildable": False, "require": [mpi_requirement]}
    return packages


def mpi_requirement_for_lane(lane: dict[str, Any]) -> str | None:
    provider = lane.get("mpi_provider")
    if not provider or lane.get("mpi_source") != "platform":
        return None
    return f"{provider} %{lane['compiler']}"
