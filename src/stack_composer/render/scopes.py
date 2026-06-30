from __future__ import annotations

import posixpath
import shutil
from pathlib import Path
from typing import Any

import yaml
from jinja2 import Environment, FileSystemLoader, StrictUndefined

from stack_composer.render.plan import vendor_scope_for_provider
from stack_composer.render.spack_specs import is_renderable_external_name_version

_COMPILER_COMMANDS = {
    "aocc": {"c": "clang", "cxx": "clang++", "fortran": "flang"},
    "cce": {"c": "craycc", "cxx": "craycxx", "fortran": "crayftn"},
    "gcc": {"c": "gcc", "cxx": "g++", "fortran": "gfortran"},
    "intel": {"c": "icx", "cxx": "icpx", "fortran": "ifx"},
    "llvm": {"c": "clang", "cxx": "clang++", "fortran": "flang"},
    "nvhpc": {"c": "nvc", "cxx": "nvc++", "fortran": "nvfortran"},
    "rocmcc": {"c": "amdclang", "cxx": "amdclang++", "fortran": "amdflang"},
}


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
    env.globals["compiler_external_packages"] = compiler_external_packages
    env.globals["common_external_packages"] = common_external_packages
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


def compiler_external_packages(
    profile: dict[str, Any], stack: dict[str, Any], scope: str
) -> list[dict[str, Any]]:
    packages: dict[str, dict[str, Any]] = {}
    for provider in compiler_providers_for_scope(profile, stack, scope):
        name = provider.get("name")
        version = provider.get("version")
        if not is_renderable_external_name_version(name, version):
            continue
        package = packages.setdefault(
            name, {"name": name, "buildable": False, "externals": []}
        )
        package["externals"].append(compiler_external(provider))
    return list(packages.values())


def compiler_external(provider: dict[str, Any]) -> dict[str, Any]:
    name = provider["name"]
    languages = ",".join(provider.get("languages") or [])
    external: dict[str, Any] = {
        "spec": f"{name}@{provider['version']} languages='{languages}'",
        "prefix": provider["prefix"],
        "modules": provider.get("modules") or [],
    }
    compilers = compiler_commands(provider)
    if compilers:
        external["extra_attributes"] = {"compilers": compilers}
    return external


def compiler_commands(provider: dict[str, Any]) -> dict[str, str] | None:
    explicit = provider.get("compilers")
    if explicit:
        return {
            "c": explicit["c"],
            "cxx": explicit["cxx"],
            "fortran": explicit["fortran"],
        }
    commands = _COMPILER_COMMANDS.get(provider["name"])
    if not commands:
        return None
    return {
        "c": path_join(provider["prefix"], "bin", commands["c"]),
        "cxx": path_join(provider["prefix"], "bin", commands["cxx"]),
        "fortran": path_join(provider["prefix"], "bin", commands["fortran"]),
    }


def common_external_packages(
    profile: dict[str, Any], stack: dict[str, Any]
) -> list[dict[str, Any]]:
    external_policy = stack.get("externals") or {}
    fabric_policy = external_policy.get("fabric_userspace", "prefer_platform")
    packages: dict[str, dict[str, Any]] = {}

    fabric_names: set[str] = set()
    fabric_by_name: dict[str, list[dict[str, Any]]] = {}
    if fabric_policy in {"prefer_platform", "mixed"}:
        for userspace in (profile.get("fabric") or {}).get("userspace") or []:
            fabric_by_name.setdefault(userspace["name"], []).append(userspace)
        for name, entries in fabric_by_name.items():
            ranked = sorted(entries, key=lambda entry: fabric_userspace_sort_key(profile, entry))
            selected = ranked if fabric_policy == "mixed" else ranked[:1]
            for userspace in selected:
                add_external(packages, userspace)
            fabric_names.add(name)

    for external in profile.get("system_externals") or []:
        if external_policy.get(external["name"]) != "system":
            continue
        if fabric_policy == "prefer_platform" and external["name"] in fabric_names:
            continue
        add_external(packages, external)

    return list(packages.values())


def add_external(packages: dict[str, dict[str, Any]], external: dict[str, Any]) -> None:
    package = packages.setdefault(
        external["name"], {"name": external["name"], "buildable": False, "externals": []}
    )
    spec = f"{external['name']}@{external['version']}"
    if external.get("variants"):
        spec += f" {external['variants']}"
    package["externals"].append(
        {
            "spec": spec,
            "prefix": external["prefix"],
            "modules": external.get("modules") or [],
        }
    )


def fabric_userspace_sort_key(profile: dict[str, Any], entry: dict[str, Any]) -> tuple[int, str]:
    prefix = entry.get("prefix", "")
    is_cray_platform = (
        (profile.get("fabric") or {}).get("type") == "slingshot"
        and prefix.startswith("/opt/cray/")
    )
    return (0 if is_cray_platform else 1, entry.get("name", ""))


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
