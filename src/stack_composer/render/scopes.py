from __future__ import annotations

import posixpath
import shutil
from pathlib import Path
from typing import Any

import yaml
from jinja2 import Environment, FileSystemLoader, StrictUndefined

from stack_composer.render.mpi import (
    mpi_toolchain_name_for_profile,
    select_compiler_provider,
)
from stack_composer.render.plan import vendor_scope_for_provider
from stack_composer.render.spack_specs import (
    external_spec,
    is_absolute_prefix,
    is_compiler_fragment,
    is_renderable_external_name_version,
)

_COMPILER_COMMANDS = {
    "aocc": {"c": "clang", "cxx": "clang++", "fortran": "flang"},
    "cce": {"c": "craycc", "cxx": "craycxx", "fortran": "crayftn"},
    "gcc": {"c": "gcc", "cxx": "g++", "fortran": "gfortran"},
    "intel": {"c": "icx", "cxx": "icpx", "fortran": "ifx"},
    "llvm": {"c": "clang", "cxx": "clang++", "fortran": "flang"},
    "nvhpc": {"c": "nvc", "cxx": "nvc++", "fortran": "nvfortran"},
    "rocmcc": {"c": "amdclang", "cxx": "amdclang++", "fortran": "amdflang"},
}
_MPI_PROVIDER_VARIANTS = {"cray-mpich": "+wrappers"}


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
    env.globals["mpi_external_packages"] = mpi_external_packages
    env.globals["mpi_toolchains"] = mpi_toolchains
    env.globals["gpu_external_packages"] = gpu_external_packages
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
        "spec": external_spec(name, provider["version"], f"languages='{languages}'"),
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


def mpi_external_packages(profile: dict[str, Any], provider_name: str) -> list[dict[str, Any]]:
    packages: dict[str, dict[str, Any]] = {}
    for provider in profile.get("mpi_providers") or []:
        if provider.get("name") != provider_name:
            continue
        if not is_renderable_external_name_version(provider.get("name"), provider.get("version")):
            continue
        variants = _MPI_PROVIDER_VARIANTS.get(provider_name)
        for external in mpi_provider_externals(provider):
            package = packages.setdefault(
                provider_name,
                {
                    "name": provider_name,
                    "buildable": False,
                    "variants": variants,
                    "externals": [],
                },
            )
            package["externals"].append(external)
    return list(packages.values())


def mpi_provider_externals(provider: dict[str, Any]) -> list[dict[str, Any]]:
    if provider.get("flavors"):
        externals = []
        for compiler, flavor in sorted(provider.get("flavors", {}).items()):
            if not is_compiler_fragment(compiler) or not is_absolute_prefix(flavor.get("prefix")):
                continue
            externals.append(
                {
                    "spec": external_spec(provider["name"], provider["version"], f"%{compiler}"),
                    "prefix": flavor["prefix"],
                    "modules": flavor.get("modules") or [],
                }
            )
        return externals

    if not is_absolute_prefix(provider.get("prefix")):
        return []
    compiler = provider.get("compiler")
    if compiler and not is_compiler_fragment(compiler):
        return []
    suffix = f"%{compiler}" if compiler else ""
    return [
        {
            "spec": external_spec(provider["name"], provider["version"], suffix),
            "prefix": provider["prefix"],
            "modules": provider.get("modules") or [],
        }
    ]


def mpi_toolchains(
    profile: dict[str, Any], rendered_lanes: list[dict[str, Any]], provider_name: str
) -> list[dict[str, Any]]:
    toolchains: list[dict[str, Any]] = []
    for provider in profile.get("mpi_providers") or []:
        if provider.get("name") != provider_name:
            continue
        if not is_renderable_external_name_version(provider.get("name"), provider.get("version")):
            continue
        for compiler in mpi_toolchain_compilers(provider):
            compiler_provider = compiler_provider_for(profile, compiler)
            if not compiler_provider:
                continue
            entries = compiler_toolchain_entries(compiler_provider)
            entries.append(
                {
                    "spec": f"%mpi={provider['name']}@{provider['version']}",
                    "when": "%mpi",
                }
            )
            toolchains.append(
                {
                    "name": mpi_toolchain_name_for_profile(
                        profile,
                        compiler,
                        provider_name,
                        str(provider["version"]),
                    ),
                    "entries": entries,
                }
            )
    toolchains.extend(
        lane_mpi_toolchains(profile, rendered_lanes, provider_name, emitted=toolchains)
    )
    return toolchains


def lane_mpi_toolchains(
    profile: dict[str, Any],
    rendered_lanes: list[dict[str, Any]],
    provider_name: str,
    emitted: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Guarantee every lane's decorated toolchain name is defined in-scope.

    The profile-driven loop above only covers compiler-tagged provider entries
    (the flavor catalog). Lanes referencing this provider without such an entry
    still decorate their specs: build-sourced lanes pin the provider unversioned
    (Spack resolves the version; the scope's packages.yaml keeps the provider
    singular), platform lanes pin their disambiguated version. The name comes
    from lane["toolchain"] — the very string the specs carry — so the reference
    and the definition cannot drift. Names already emitted are skipped.
    """
    emitted_names = {toolchain["name"] for toolchain in emitted}
    toolchains: list[dict[str, Any]] = []
    for lane in rendered_lanes:
        if lane.get("mpi_provider") != provider_name or not lane.get("toolchain"):
            continue
        name = lane["toolchain"]
        if name in emitted_names:
            continue
        compiler_provider = compiler_provider_for(profile, lane["compiler"])
        if not compiler_provider:
            continue
        emitted_names.add(name)
        entries = compiler_toolchain_entries(compiler_provider)
        mpi_spec = provider_name
        if lane.get("mpi_source") == "platform" and lane.get("mpi_version"):
            mpi_spec = f"{provider_name}@{lane['mpi_version']}"
        entries.append({"spec": f"%mpi={mpi_spec}", "when": "%mpi"})
        toolchains.append({"name": name, "entries": entries})
    return toolchains


def mpi_toolchain_compilers(provider: dict[str, Any]) -> list[str]:
    if provider.get("flavors"):
        return sorted(
            compiler
            for compiler, flavor in provider.get("flavors", {}).items()
            if is_compiler_fragment(compiler) and is_absolute_prefix(flavor.get("prefix"))
        )
    compiler = provider.get("compiler")
    if compiler and is_compiler_fragment(compiler):
        return [compiler]
    return sorted((provider.get("compatibility") or {}).get("compilers") or [])


def compiler_provider_for(profile: dict[str, Any], compiler: str) -> dict[str, Any] | None:
    return select_compiler_provider(profile, compiler)


def compiler_name_from_fragment(compiler: str) -> str:
    return compiler.split("@", 1)[0]


def compiler_name(provider: dict[str, Any]) -> str:
    return str(provider["name"])


def compiler_spec(provider: dict[str, Any]) -> str:
    return external_spec(provider["name"], provider["version"])


def compiler_toolchain_entries(provider: dict[str, Any]) -> list[dict[str, str]]:
    entries = []
    languages = provider.get("languages") or ["c", "c++", "fortran"]
    language_virtuals = {
        "c": "c",
        "c++": "cxx",
        "cxx": "cxx",
        "fortran": "fortran",
    }
    spec = compiler_spec(provider)
    for language in languages:
        virtual = language_virtuals.get(str(language).lower())
        if virtual:
            entries.append({"spec": f"%{virtual}={spec}", "when": f"%{virtual}"})
    return entries


def gpu_external_packages(profile: dict[str, Any], toolkit: str) -> list[dict[str, Any]]:
    if toolkit == "rocm":
        return rocm_external_packages((profile.get("gpu_toolkit_modules") or {}).get("rocm") or {})
    if toolkit == "cuda":
        return cuda_external_packages(
            (profile.get("gpu_toolkit_modules") or {}).get("cudatoolkit") or {}
        )
    return []


def rocm_external_packages(rocm: dict[str, Any]) -> list[dict[str, Any]]:
    packages: dict[str, dict[str, Any]] = {}
    version = rocm.get("version")
    module = rocm.get("module")
    for component in rocm.get("spack_components") or []:
        add_external(
            packages,
            {
                "name": component.get("package"),
                "version": version,
                "prefix": component.get("prefix"),
                "modules": [module] if module else [],
            },
        )
    return list(packages.values())


def cuda_external_packages(cuda: dict[str, Any]) -> list[dict[str, Any]]:
    packages: dict[str, dict[str, Any]] = {}
    add_external(
        packages,
        {
            "name": "cuda",
            "version": cuda.get("version"),
            "prefix": cuda.get("prefix"),
            "modules": [cuda["module"]] if cuda.get("module") else [],
        },
    )
    return list(packages.values())


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
    name = external.get("name")
    version = external.get("version")
    prefix = external.get("prefix")
    if not (
        is_renderable_external_name_version(name, version)
        and is_absolute_prefix(prefix)
    ):
        return
    package = packages.setdefault(
        name, {"name": name, "buildable": False, "externals": []}
    )
    spec = external_spec(name, version)
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
    # Every MPI lane includes its provider scope: platform lanes for the
    # externals, build-sourced lanes for the toolchain that decorates their
    # specs (the toolchain must be defined in an included scope or Spack
    # rejects the %name reference at concretize time).
    provider = lane.get("mpi_provider")
    if not provider:
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
