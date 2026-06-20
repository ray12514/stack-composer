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
            "toolchain": toolchain_for_lane(ctx["profile"], lane),
            "view_root": lane["view_root"],
            "platform_module_prereqs": prereqs,
        }
    )
    src = template_dir / "environments" / lane["kind"] / "spack.yaml.j2"
    dst = pending / lane["env_path"] / "spack.yaml"
    dst.parent.mkdir(parents=True, exist_ok=True)
    template_name = src.relative_to(template_dir).as_posix()
    dst.write_text(env.get_template(template_name).render(lane_ctx), encoding="utf-8")

def toolchain_for_lane(profile: dict[str, Any], lane: dict[str, Any]) -> dict[str, Any]:
    compiler = {"name": lane["compiler"], "version": None, "spec": "%" + lane["compiler"]}
    vendor_cray = profile.get("vendor_cray") or {}
    if vendor_cray.get(lane["compiler"]):
        compiler["version"] = vendor_cray[lane["compiler"]].get("version")
    mpi = None
    if "craympich" in lane["lane"]:
        mpi = {
            "name": "cray-mpich",
            "version": vendor_cray.get("cray_mpich", {}).get("version"),
            "provider": "cray-mpich",
            "spec": "^cray-mpich",
        }
    gpu_toolkit = None
    arch = lane.get("gpu_arch")
    toolkits = profile.get("gpu_toolkit_modules") or {}
    if arch and arch.startswith("gfx") and toolkits.get("rocm"):
        rocm = toolkits["rocm"]
        gpu_toolkit = {
            "name": "rocm",
            "version": rocm.get("version"),
            "prefix": rocm.get("prefix"),
            "spec": "+rocm",
        }
    elif arch and arch.startswith("sm_") and toolkits.get("cudatoolkit"):
        cuda = toolkits["cudatoolkit"]
        gpu_toolkit = {
            "name": "cudatoolkit",
            "version": cuda.get("version"),
            "prefix": cuda.get("prefix"),
            "spec": "+cuda",
        }
    return {"compiler": compiler, "mpi": mpi, "gpu_toolkit": gpu_toolkit}
