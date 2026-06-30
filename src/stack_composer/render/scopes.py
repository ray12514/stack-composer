from __future__ import annotations

import posixpath
import shutil
from pathlib import Path
from typing import Any

import yaml
from jinja2 import Environment, FileSystemLoader, StrictUndefined

from stack_composer.render.plan import vendor_scope_for_provider


def make_jinja_environment(template_dir: Path) -> Environment:
    env = Environment(
        loader=FileSystemLoader(str(template_dir)),
        undefined=StrictUndefined,
        autoescape=False,
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=True,
    )
    env.filters["to_yaml"] = to_yaml
    env.globals["to_yaml"] = to_yaml
    env.globals["path_join"] = path_join
    env.globals["spack_spec"] = spack_spec
    env.globals["compiler_providers_for_scope"] = compiler_providers_for_scope
    return env


def to_yaml(value: Any) -> str:
    return yaml.safe_dump(value, sort_keys=False, default_flow_style=False).rstrip()


def path_join(*parts: str) -> str:
    return posixpath.join(*parts)


def spack_spec(parts: dict[str, Any]) -> str:
    spec = parts["name"]
    if parts.get("version"):
        spec += "@" + str(parts["version"])
    variants = parts.get("variants") or []
    if variants:
        spec += " " + " ".join(str(variant) for variant in variants)
    return spec


def compiler_providers_for_scope(
    profile: dict[str, Any], stack: dict[str, Any], scope: str
) -> list[dict[str, Any]]:
    return [
        provider
        for provider in profile.get("compiler_providers") or []
        if vendor_scope_for_provider(stack, provider) == scope
    ]


def required_scopes(profile: dict[str, Any], rendered_lanes: list[dict[str, Any]]) -> list[str]:
    scopes: set[str] = set()
    for lane in rendered_lanes:
        scopes.update(scope_names_for_lane(lane, profile))
    return sorted(scopes, key=scope_sort_key)


def render_template_tree(src: Path, dst: Path, env: Environment, ctx: dict[str, Any]) -> None:
    for path in sorted(p for p in src.rglob("*") if p.is_file()):
        relative = path.relative_to(src)
        output_relative = relative.with_suffix("") if path.suffix == ".j2" else relative
        output_path = dst / output_relative
        output_path.parent.mkdir(parents=True, exist_ok=True)
        if path.suffix != ".j2":
            shutil.copyfile(path, output_path)
            continue
        template_name = path.relative_to(Path(env.loader.searchpath[0])).as_posix()
        rendered = env.get_template(template_name).render(ctx)
        output_path.write_text(rendered, encoding="utf-8")


def scopes_for_lane(
    lane: dict[str, Any], stack: dict[str, Any], profile: dict[str, Any]
) -> list[str]:
    del stack
    return ["../../../configs/" + scope for scope in scope_names_for_lane(lane, profile)]


def scope_names_for_lane(lane: dict[str, Any], profile: dict[str, Any]) -> list[str]:
    scopes = [
        "common",
        os_scope(profile),
        "target/" + lane["target"],
        lane["vendor_scope"],
    ]
    mpi_scope_name = mpi_scope(lane)
    if mpi_scope_name:
        scopes.append(mpi_scope_name)
    gpu_scope_name = gpu_scope(lane)
    if gpu_scope_name:
        scopes.append(gpu_scope_name)
    return scopes


# RHEL-compatible distributions share a single curated os/rhel<major> scope.
# cluster-inspector reports the concrete distro id (rocky, almalinux, ...); the
# template carries the family scope, so normalize here.
_RHEL_FAMILY = {"rhel", "rocky", "almalinux", "alma", "centos", "ol", "oraclelinux"}


def os_scope(profile: dict[str, Any]) -> str:
    os_data = profile["os"]
    name = os_data["name"]
    if name in _RHEL_FAMILY:
        name = "rhel"
    return f"os/{name}{os_data['major']}"


def mpi_scope(lane: dict[str, Any]) -> str | None:
    # Only platform MPI needs an externals scope. Build-from-source MPI is pinned
    # as the provider preference in the common scope and built by Spack.
    provider = lane.get("mpi_provider")
    if not provider or lane.get("mpi_source") != "platform":
        return None
    return "mpi/" + provider


def gpu_scope(lane: dict[str, Any]) -> str | None:
    arch = lane.get("gpu_arch")
    if not arch:
        return None
    if arch.startswith("gfx"):
        return "gpu/amd-rocm"
    if arch.startswith("sm_"):
        return "gpu/nvidia-cuda"
    return None


def scope_sort_key(scope: str) -> tuple[int, str]:
    order = {
        "common": 0,
        "os": 1,
        "target": 2,
        "vendor": 3,
        "mpi": 4,
        "gpu": 5,
    }
    head = scope.split("/", 1)[0]
    return (order.get(head, 99), scope)
