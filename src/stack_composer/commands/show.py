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
from stack_composer.render.mpi import mpi_toolchain_name_for_profile
from stack_composer.render.plan import _BASELINE_TARGET, plan_lanes, runtime_nodes
from stack_composer.render.platform_modules import platform_module_prereqs_for_lane

# Fallback for `show` when no --defaults/--templates is given (bare-profile mode).
# Must mirror the shipped templates/v6/defaults.yaml so the preview matches render.
_BUILTIN_DEFAULTS = {
    "schema_version": 1,
    "compilers": "baseline",
    "mpi": {"provider": "openmpi", "source": "auto"},
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
    stack_name = "generated defaults-only preview"
    if stack_path:
        raw_stack, stack_issues = load_stack(Path(stack_path))
        if stack_issues:
            raise click.ClickException("; ".join(i.message for i in stack_issues))
        probe = merge_defaults(defaults, raw_stack)
        probe.setdefault("name", "show")
        stack_name = str(probe.get("name") or Path(stack_path).stem)
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
    lanes, _, _, plan_issues = plan_lanes(profile_data, probe)

    out = render_menu(profile_data, defaults, lanes, stack_name=stack_name, issues=plan_issues)
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
    profile: dict[str, Any],
    defaults: dict[str, Any],
    lanes: list[dict[str, Any]],
    *,
    stack_name: str,
    issues: list[Any],
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
    platform_families = provider_platform_families(profile)
    if platform_families:
        lines.append(f"platform families: {', '.join(platform_families)}")
    lines.append(f"targets: {targets}")
    lines.append(f"preview stack: {stack_name}")
    lines.append("")

    compilers = compiler_entries(profile)
    lines.append(f"compilers ({len(compilers)} available)")
    for compiler in compilers:
        modules = _fmt_modules(compiler.get("modules") or [])
        family = compiler.get("provider_family", "?")
        platform_family = compiler.get("platform_family")
        if platform_family:
            family = f"{family}/{platform_family}"
        lines.append(
            f"  {compiler.get('name', '?'):<8} {compiler.get('version') or '(version n/a)':<12} "
            f"family={family:<16} modules={modules}"
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
    if issues:
        lines.append("")
        lines.append(f"planning issues ({len(issues)})")
        for issue in issues:
            lines.append(f"  [{issue.severity}] {issue.code}: {issue.message}")
    if lanes:
        lines.append("")
        lines.append("resolved lanes")
        for lane in sorted(lanes, key=lambda item: item["name"]):
            modules, issues = platform_module_prereqs_for_lane(lane, profile)
            module_text = _fmt_modules(modules)
            issue_text = f"  unresolved={len(issues)}" if issues else ""
            mpi = lane.get("mpi_provider") or "none"
            toolchain = lane.get("toolchain") or "none"
            lines.append(
                f"  {lane['name']:<28} kind={lane['kind']:<3} compiler={lane['compiler']:<8} "
                f"mpi={mpi:<10} toolchain={toolchain:<16} scope={lane['vendor_scope']} "
                f"modules={module_text}{issue_text}"
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


def provider_platform_families(profile: dict[str, Any]) -> list[str]:
    families = {
        provider.get("platform_family")
        for provider in (profile.get("compiler_providers") or [])
        + (profile.get("mpi_providers") or [])
        if provider.get("platform_family")
    }
    return sorted(families)


def compiler_entries(profile: dict[str, Any]) -> list[dict[str, Any]]:
    entries: OrderedDict[tuple[Any, ...], dict[str, Any]] = OrderedDict()
    for provider in profile.get("compiler_providers") or []:
        name = provider.get("name")
        if not name:
            continue
        key = (
            name,
            provider.get("version"),
            provider.get("provider_family"),
            provider.get("platform_family"),
            provider.get("prefix"),
            tuple(provider.get("modules") or []),
        )
        entries[key] = provider
    return list(entries.values())


def mpi_lines(profile: dict[str, Any]) -> list[str]:
    grouped: OrderedDict[str, list[dict[str, Any]]] = OrderedDict()
    for entry in profile.get("mpi_providers") or []:
        name = entry.get("name")
        if not name:
            continue
        grouped.setdefault(name, []).append(entry)

    if not grouped:
        return ["mpi   none on system — built from source per defaults"]
    lines = [f"mpi ({len(grouped)} providers)"]
    for name, entries in grouped.items():
        version_groups = mpi_variant_groups(entries)
        distinct_versions = {str(entry.get("version") or "") for entry in entries}
        # Ambiguous provider names get one line per version/family group, each
        # with its version-qualified toolchain identity, so the conflict is
        # legible here instead of only failing later at render time.
        ambiguous = len(distinct_versions) > 1
        for group in version_groups:
            if len(group) == 1:
                lines.extend(mpi_entry_lines(profile, name, group[0]))
            else:
                lines.extend(mpi_variant_group_lines(profile, name, group))
        if ambiguous:
            lines.append(
                f"    !! {len(distinct_versions)} versions of {name!r} on this system: "
                "set mpi.version on the stack build to select one"
            )
    return lines


def mpi_variant_groups(entries: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    groups: OrderedDict[tuple[Any, ...], list[dict[str, Any]]] = OrderedDict()
    for entry in entries:
        key = (
            entry.get("name"),
            entry.get("version"),
            entry.get("provider_family"),
            entry.get("platform_family"),
        )
        groups.setdefault(key, []).append(entry)
    return list(groups.values())


def mpi_entry_lines(profile: dict[str, Any], name: str, entry: dict[str, Any]) -> list[str]:
    version = str(entry.get("version") or "(n/a)")
    family = entry.get("provider_family") or "?"
    compilers = mpi_entry_compilers(entry)
    compiler_text = f"compilers: {', '.join(compilers)}" if compilers else ""
    toolchain_text = ""
    if compilers:
        names = ", ".join(
            mpi_toolchain_name_for_profile(profile, compiler, name, str(entry.get("version")))
            for compiler in compilers
        )
        toolchain_text = f"toolchains: {names}"
    modules = _fmt_modules(entry.get("modules") or [])
    parts = [f"  {name:<10} {version:<12} family={family:<8}"]
    if compiler_text:
        parts.append(compiler_text)
    if toolchain_text:
        parts.append(toolchain_text)
    parts.append(f"modules={modules}")
    lines = [" ".join(parts).rstrip() + "   [platform]"]
    for compiler, flavor in (entry.get("flavors") or {}).items():
        lines.append(f"    {compiler:<8} modules={_fmt_modules(flavor.get('modules') or [])}")
    return lines


def mpi_variant_group_lines(
    profile: dict[str, Any], name: str, entries: list[dict[str, Any]]
) -> list[str]:
    first = entries[0]
    version = str(first.get("version") or "(n/a)")
    family = first.get("provider_family") or "?"
    compiler_refs = sorted({ref for entry in entries for ref in mpi_entry_compiler_refs(entry)})
    compiler_text = f"compilers: {_fmt_limited(compiler_refs)}" if compiler_refs else ""
    toolchain_text = ""
    if compiler_refs:
        names = [
            mpi_toolchain_name_for_profile(profile, compiler, name, str(first.get("version")))
            for compiler in compiler_refs
        ]
        toolchain_text = f"toolchains: {_fmt_limited(names)}"
    module_count = len({module for entry in entries for module in entry.get("modules") or []})
    prefix_count = len({entry.get("prefix") for entry in entries if entry.get("prefix")})
    parts = [
        f"  {name:<10} {version:<12} family={family:<8}",
        f"variants={len(entries)}",
    ]
    if compiler_text:
        parts.append(compiler_text)
    if toolchain_text:
        parts.append(toolchain_text)
    parts.append(f"prefixes={prefix_count}")
    parts.append(f"modules={module_count}")
    parts.append("[platform]")
    return [" ".join(parts).rstrip()]


def mpi_entry_compilers(entry: dict[str, Any]) -> list[str]:
    compilers = {
        str(compiler).split("@", 1)[0]
        for compiler in (entry.get("compatibility") or {}).get("compilers") or []
    }
    compilers |= {str(compiler).split("@", 1)[0] for compiler in entry.get("flavors") or {}}
    if entry.get("compiler"):
        compilers.add(str(entry["compiler"]).split("@", 1)[0])
    return sorted(compilers)


def mpi_entry_compiler_refs(entry: dict[str, Any]) -> list[str]:
    refs = {str(compiler) for compiler in entry.get("flavors") or {}}
    refs |= {
        str(compiler)
        for compiler in (entry.get("compatibility") or {}).get("compilers") or []
    }
    if entry.get("compiler"):
        refs.add(str(entry["compiler"]))
    return sorted(refs)


def gpu_arches(profile: dict[str, Any]) -> list[str]:
    arches = {
        (node.get("gpu") or {}).get("arch_target")
        for node in (profile.get("node_types") or {}).values()
        if (node.get("gpu") or {}).get("arch_target")
    }
    return sorted(a for a in arches if a)


def gpu_toolkit_lines(profile: dict[str, Any]) -> list[str]:
    # Each family lists every installed generation; show them all so a manual
    # user sees the full inventory the render selects one from.
    lines: list[str] = []
    for name, toolkits in sorted((profile.get("gpu_toolkit_modules") or {}).items()):
        if not isinstance(toolkits, list):
            continue
        for toolkit in toolkits:
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


def _fmt_limited(values: list[str], limit: int = 6) -> str:
    if len(values) <= limit:
        return ", ".join(values)
    shown = ", ".join(values[:limit])
    return f"{shown}, +{len(values) - limit} more"
