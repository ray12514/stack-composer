"""`stack-composer show` — render a system's buildable menu.

Reads a profile (and, optionally, the site defaults and a stack) and prints,
summary-first: the compilers, the MPI providers grouped with the compilers they
tie to, the GPU arches, the targets, and the lanes you would build under the
current defaults. Never a wall of text — one line per MPI provider.
"""

from __future__ import annotations

from collections import OrderedDict
from pathlib import Path
from typing import Any

import click

from stack_composer.model.profile import load_profile
from stack_composer.model.stack import load_defaults, load_stack, merge_defaults
from stack_composer.render.plan import _BASELINE_TARGET, plan_lanes, runtime_nodes
from stack_composer.render.platform_modules import platform_module_prereqs_for_lane

_BUILTIN_DEFAULTS = {
    "schema_version": 1,
    "compilers": "all",
    "mpi": {"provider": "openmpi", "source": "build"},
    "gpu": {"archs": "all"},
    "target": "native",
}


def run(
    *,
    profile: str,
    templates: str | None,
    template_set_name: str | None,
    defaults_path: str | None,
    stack_path: str | None,
) -> None:
    profile_data, profile_issues = load_profile(Path(profile))
    if profile_issues:
        raise click.ClickException("; ".join(i.message for i in profile_issues))

    defaults = _load_defaults(defaults_path, templates, template_set_name)

    # Build the "you would build" probe: a real stack if given, else one build
    # per kind so the lane counts are visible.
    if stack_path:
        raw_stack, stack_issues = load_stack(Path(stack_path))
        if stack_issues:
            raise click.ClickException("; ".join(i.message for i in stack_issues))
        probe = merge_defaults(defaults, raw_stack)
        probe.setdefault("name", "show")
    else:
        probe = merge_defaults(
            defaults,
            {
                "name": "show",
                "builds": [
                    {"name": "cpu", "kind": "cpu", "specs": ["_"]},
                    {"name": "mpi", "kind": "mpi", "specs": ["_"]},
                    {"name": "gpu", "kind": "gpu", "specs": ["_"]},
                ],
            },
        )
    lanes, _, _, _ = plan_lanes(profile_data, probe)

    out = render_menu(profile_data, defaults, lanes)
    click.echo(out)


def _load_defaults(
    defaults_path: str | None, templates: str | None, template_set_name: str | None
) -> dict[str, Any]:
    path: Path | None = None
    if defaults_path:
        path = Path(defaults_path)
    elif templates and template_set_name:
        path = Path(templates) / template_set_name / "defaults.yaml"
    if path is None:
        return dict(_BUILTIN_DEFAULTS)
    data, issues = load_defaults(path)
    if issues:
        raise click.ClickException("; ".join(i.message for i in issues))
    return data


def render_menu(
    profile: dict[str, Any], defaults: dict[str, Any], lanes: list[dict[str, Any]]
) -> str:
    lines: list[str] = []
    system = profile.get("system", {}).get("name", "?")
    os_data = profile.get("os", {})
    os_label = f"{os_data.get('name', '?')}{os_data.get('major', '')}"
    native = _native_target(profile)
    targets = f"{native} (native)" if native else "(no cpu node)"
    targets += f", {_BASELINE_TARGET} (baseline)"
    families = provider_families(profile)
    family_label = ", ".join(families) if families else "none"
    lines.append(f"{system} · {os_label} · provider families: {family_label}")
    lines.append(f"targets: {targets}")
    lines.append("")

    compilers = compiler_entries(profile)
    lines.append(f"compilers ({len(compilers)} available)")
    for compiler in compilers:
        modules = _fmt_modules(compiler.get("modules") or [])
        lines.append(
            f"  {compiler.get('name', '?'):<8} {compiler.get('version') or '(version n/a)':<12} "
            f"family={compiler.get('provider_family', '?'):<8} modules={modules}"
        )
    lines.append("")

    lines.extend(mpi_lines(profile))
    lines.append("")

    gpu = gpu_arches(profile)
    toolkits = gpu_toolkit_lines(profile)
    lines.append(f"gpu arches   {', '.join(gpu) if gpu else 'none'}")
    if toolkits:
        lines.append("gpu toolkits")
        lines.extend(f"  {line}" for line in toolkits)
    lines.append("")

    system_external_rows = system_external_lines(profile)
    lines.append(f"system externals ({len(system_external_rows)} candidates)")
    if system_external_rows:
        lines.extend(f"  {line}" for line in system_external_rows)
    else:
        lines.append("  none")
    lines.append("")

    lines.append(
        "you would build  "
        f"(defaults: compilers={_fmt_sel(defaults.get('compilers', 'all'))}"
        f" · mpi={(defaults.get('mpi') or {}).get('provider', 'n/a')}"
        f" · target={defaults.get('target', 'native')})"
    )
    by_kind: dict[str, list[str]] = OrderedDict((k, []) for k in ("cpu", "mpi", "gpu"))
    for lane in lanes:
        by_kind.setdefault(lane["kind"], []).append(lane["compiler"])
    for kind, lane_compilers in by_kind.items():
        detail = " · ".join(sorted(set(lane_compilers))) if lane_compilers else ""
        lines.append(f"  {kind} → {len(lane_compilers)} lanes    {detail}".rstrip())
    if lanes:
        lines.append("")
        lines.append("resolved lanes")
        for lane in sorted(lanes, key=lambda item: item["name"]):
            modules, issues = platform_module_prereqs_for_lane(lane, profile)
            module_text = _fmt_modules(modules)
            issue_text = f"  unresolved={len(issues)}" if issues else ""
            mpi = lane.get("mpi_provider") or "none"
            lines.append(
                f"  {lane['name']:<28} kind={lane['kind']:<3} compiler={lane['compiler']:<8} "
                f"mpi={mpi:<10} scope={lane['vendor_scope']} modules={module_text}{issue_text}"
            )
    return "\n".join(lines)


def provider_families(profile: dict[str, Any]) -> list[str]:
    families = {
        provider.get("provider_family")
        for provider in (profile.get("compiler_providers") or [])
        + (profile.get("mpi_providers") or [])
        if provider.get("provider_family")
    }
    return sorted(families)


def compiler_entries(profile: dict[str, Any]) -> list[dict[str, Any]]:
    entries: OrderedDict[str, dict[str, Any]] = OrderedDict()
    for provider in profile.get("compiler_providers") or []:
        name = provider.get("name")
        if not name:
            continue
        entries[name] = provider
    return list(entries.values())


def mpi_lines(profile: dict[str, Any]) -> list[str]:
    providers: OrderedDict[str, dict[str, Any]] = OrderedDict()
    for entry in profile.get("mpi_providers") or []:
        name = entry.get("name")
        if not name:
            continue
        slot = providers.setdefault(
            name,
            {
                "versions": set(),
                "families": set(),
                "compilers": set(),
                "modules": [],
                "flavor_modules": OrderedDict(),
            },
        )
        if entry.get("version"):
            slot["versions"].add(entry["version"])
        if entry.get("provider_family"):
            slot["families"].add(entry["provider_family"])
        for module in entry.get("modules") or []:
            if module not in slot["modules"]:
                slot["modules"].append(module)
        for compiler in (entry.get("compatibility") or {}).get("compilers") or []:
            slot["compilers"].add(compiler)
        for compiler, flavor in (entry.get("flavors") or {}).items():
            slot["compilers"].add(compiler)
            slot["flavor_modules"][compiler] = list(flavor.get("modules") or [])
        if entry.get("compiler"):
            slot["compilers"].add(entry["compiler"])

    if not providers:
        return ["mpi   none on system — built from source per defaults"]
    lines = [f"mpi ({len(providers)} providers)"]
    for name, slot in providers.items():
        versions = ", ".join(sorted(slot["versions"])) or "(n/a)"
        families = ", ".join(sorted(slot["families"])) or "?"
        compilers = (
            f"compilers: {', '.join(sorted(slot['compilers']))}" if slot["compilers"] else ""
        )
        modules = _fmt_modules(slot["modules"])
        lines.append(
            f"  {name:<10} {versions:<12} family={families:<8} {compilers} "
            f"modules={modules}".rstrip()
            + "   [platform]"
        )
        for compiler, modules_for_flavor in slot["flavor_modules"].items():
            lines.append(f"    {compiler:<8} modules={_fmt_modules(modules_for_flavor)}")
    return lines


def gpu_arches(profile: dict[str, Any]) -> list[str]:
    arches = {
        (node.get("gpu") or {}).get("arch_target")
        for node in (profile.get("node_types") or {}).values()
        if (node.get("gpu") or {}).get("arch_target")
    }
    return sorted(a for a in arches if a)


def gpu_toolkit_lines(profile: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    for name, toolkit in sorted((profile.get("gpu_toolkit_modules") or {}).items()):
        if not isinstance(toolkit, dict):
            continue
        version = toolkit.get("version") or "(version n/a)"
        module = toolkit.get("module")
        prefix = toolkit.get("prefix")
        details = [f"{name} {version}"]
        if module:
            details.append(f"module={module}")
        if prefix:
            details.append(f"prefix={prefix}")
        components = toolkit.get("spack_components") or []
        if components:
            packages = [component.get("package", "?") for component in components]
            details.append(f"components={len(packages)}: {', '.join(packages)}")
        lines.append(" ".join(details))
    return lines


def system_external_lines(profile: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    for external in profile.get("system_externals") or []:
        name = external.get("name", "?")
        version = external.get("version") or "(version n/a)"
        family = external.get("provider_family") or "?"
        prefix = external.get("prefix") or "?"
        variants = external.get("variants")
        modules = _fmt_modules(external.get("modules") or [])
        detection = external.get("detection") or {}
        detected_by = ""
        if detection:
            confidence = detection.get("confidence", "?")
            source = detection.get("source", "?")
            detected_by = f" detected={confidence}/{source}"
        variant_text = f" variants={variants}" if variants else ""
        lines.append(
            f"{name:<10} {version:<12} family={family:<8} prefix={prefix}"
            f"{variant_text} modules={modules}{detected_by}"
        )
    return lines


def _native_target(profile: dict[str, Any]) -> str | None:
    cpu_nodes = runtime_nodes(profile, want_gpu=False)
    if cpu_nodes:
        return cpu_nodes[0][1].get("cpu", {}).get("preferred")
    gpu_nodes = runtime_nodes(profile, want_gpu=True)
    if gpu_nodes:
        return gpu_nodes[0][1].get("cpu", {}).get("preferred")
    return None


def _fmt_sel(value: Any) -> str:
    if value == "all":
        return "all"
    if isinstance(value, list):
        return "[" + ", ".join(value) + "]"
    return str(value)


def _fmt_modules(modules: list[str]) -> str:
    return ", ".join(modules) if modules else "none"
