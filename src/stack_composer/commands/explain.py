from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import IO, Any

import click
import yaml

from stack_composer.errors import ValidationFailed
from stack_composer.model.contract import load_contract
from stack_composer.model.profile import load_profile
from stack_composer.model.stack import load_stack, load_stack_defaults, merge_defaults
from stack_composer.render.plan import (
    compiler_candidates,
    lane_candidates_for_build,
    matching_node_types,
)


def run(
    *,
    profile: str,
    templates: str,
    stack_path: str | None,
    template_set_name: str | None,
    output_format: str,
    stream: IO[str] | None = None,
) -> None:
    out = stream or sys.stdout
    profile_data, profile_issues = load_profile(Path(profile))
    if profile_issues:
        raise ValidationFailed(profile_issues)

    raw_stack: dict[str, Any] | None = None
    if stack_path:
        raw_stack, stack_issues = load_stack(Path(stack_path))
        if stack_issues:
            raise ValidationFailed(stack_issues)
        template_set_name = template_set_name or (raw_stack.get("templates") or {}).get("set")

    if not template_set_name:
        raise click.ClickException(
            "explain requires --template-set when --stack is omitted, "
            "or a stack.yaml that pins templates.set"
        )

    template_set_dir = Path(templates) / template_set_name
    contract, contract_issues = load_contract(template_set_dir / "contract.yaml")
    if contract_issues:
        raise ValidationFailed(contract_issues)

    stack: dict[str, Any] | None = None
    if raw_stack is not None:
        defaults, defaults_issues = load_stack_defaults(template_set_dir / "stack-defaults.yaml")
        if defaults_issues:
            raise ValidationFailed(defaults_issues)
        stack = merge_defaults(defaults, raw_stack)

    facts = summarize_profile_facts(profile_data)
    menu = {
        "profile": profile_data["system"]["name"],
        "template_set": template_set_name,
        "build_classes": sorted((contract.get("build_classes") or {}).keys()),
        "toolchains": resolvable_toolchains(profile_data, contract),
        "node_selectors": resolvable_node_selectors(profile_data, contract),
        "compilers": facts["compiler_names"],
        "mpi_providers": facts["mpi_provider_names"],
        "gpu_arches": facts["gpu_arches"],
    }
    if stack is not None:
        menu["per_system_narrowing"] = narrowing_menu(profile_data, stack, contract)

    if output_format == "yaml":
        yaml.safe_dump(menu, out, sort_keys=False, default_flow_style=False)
    elif output_format == "json":
        json.dump(menu, out, indent=2, sort_keys=False)
        out.write("\n")
    else:
        write_human(menu, out)


def summarize_profile_facts(profile: dict[str, Any]) -> dict[str, Any]:
    compilers: list[str] = []
    seen: set[str] = set()
    vendor_cray = profile.get("vendor_cray") or {}
    for name in ("gcc", "cce", "aocc", "intel", "nvhpc", "rocmcc"):
        if vendor_cray.get(name) is not None and name not in seen:
            compilers.append(name)
            seen.add(name)
    for entry in profile.get("compilers_external") or []:
        name = entry.get("name")
        if name and name not in seen:
            compilers.append(name)
            seen.add(name)

    mpi_providers: list[str] = []
    if vendor_cray.get("cray_mpich"):
        mpi_providers.append("cray-mpich")
    for entry in profile.get("mpi") or []:
        name = entry.get("name")
        if name and name not in mpi_providers:
            mpi_providers.append(name)

    gpu_arches = sorted(
        {
            (node.get("gpu") or {}).get("arch_target")
            for node in (profile.get("node_types") or {}).values()
            if node.get("gpu")
        }
        - {None}
    )

    return {
        "compiler_names": compilers,
        "mpi_provider_names": mpi_providers,
        "gpu_arches": gpu_arches,
    }


def resolvable_toolchains(
    profile: dict[str, Any], contract: dict[str, Any]
) -> list[str]:
    resolvable: list[str] = []
    profile_has_cray_mpich = bool((profile.get("vendor_cray") or {}).get("cray_mpich"))
    profile_has_site_mpi = bool(profile.get("mpi"))
    toolkits = profile.get("gpu_toolkit_modules") or {}
    for name, toolchain in sorted((contract.get("toolchains") or {}).items()):
        if not compiler_candidates(profile, toolchain):
            continue
        mpi_policy = toolchain.get("mpi", "none")
        if mpi_policy == "cray-mpich" and not profile_has_cray_mpich:
            continue
        if mpi_policy not in ("none", "cray-mpich") and not (
            profile_has_cray_mpich or profile_has_site_mpi
        ):
            continue
        gpu_policy = toolchain.get("gpu_toolkit", "none")
        if gpu_policy in ("cudatoolkit", "nvhpc") and not toolkits.get(gpu_policy):
            continue
        if gpu_policy == "rocm" and not toolkits.get("rocm"):
            continue
        if gpu_policy == "prefer_platform" and not toolkits:
            continue
        resolvable.append(name)
    return resolvable


def resolvable_node_selectors(
    profile: dict[str, Any], contract: dict[str, Any]
) -> list[str]:
    resolvable: list[str] = []
    for name, selector in sorted((contract.get("node_selectors") or {}).items()):
        if matching_node_types(profile, selector.get("match", "")):
            resolvable.append(name)
    return resolvable


def narrowing_menu(
    profile: dict[str, Any], stack: dict[str, Any], contract: dict[str, Any]
) -> dict[str, dict[str, list[str]]]:
    menu: dict[str, dict[str, list[str]]] = {}
    for build in stack.get("builds") or []:
        if build.get("class") not in (contract.get("build_classes") or {}):
            continue
        if build.get("toolchain") not in (contract.get("toolchains") or {}):
            continue
        if build.get("nodes") not in (contract.get("node_selectors") or {}):
            continue
        lanes, _, _ = lane_candidates_for_build(profile, stack, contract, build)
        menu[build["name"]] = {
            "compilers": sorted({lane["compiler"] for lane in lanes if lane.get("compiler")}),
            "mpi": sorted({lane["mpi_provider"] for lane in lanes if lane.get("mpi_provider")}),
            "gpu_selectors": sorted(
                {lane["gpu_selector"] for lane in lanes if lane.get("gpu_selector")}
            ),
        }
    return menu


def write_human(menu: dict[str, Any], out: IO[str]) -> None:
    out.write(f"profile:       {menu['profile']}\n")
    out.write(f"template_set:  {menu['template_set']}\n")
    out.write("\n")
    write_section(out, "build_classes", menu["build_classes"])
    write_section(out, "toolchains", menu["toolchains"])
    write_section(out, "node_selectors", menu["node_selectors"])
    write_section(out, "compilers", menu["compilers"])
    write_section(out, "mpi_providers", menu["mpi_providers"])
    write_section(out, "gpu_arches", menu["gpu_arches"])
    if "per_system_narrowing" in menu:
        out.write("per_system_narrowing:\n")
        for build_name, axes in menu["per_system_narrowing"].items():
            out.write(f"  {build_name}:\n")
            for axis in ("compilers", "mpi", "gpu_selectors"):
                values = axes.get(axis) or []
                out.write(f"    {axis}: {', '.join(values) if values else '(none)'}\n")


def write_section(out: IO[str], heading: str, values: list[str]) -> None:
    out.write(f"{heading}:\n")
    if not values:
        out.write("  (none)\n")
    for value in values:
        out.write(f"  - {value}\n")
    out.write("\n")
