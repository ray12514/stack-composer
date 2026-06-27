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
from stack_composer.render.plan import (
    _BASELINE_TARGET,
    plan_lanes,
    profile_compilers,
    runtime_nodes,
)

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
    lines.append(f"{system} · {os_label} · targets: {targets}")
    lines.append("")

    compilers = compiler_versions(profile)
    lines.append(f"compilers ({len(compilers)} available)")
    for name, versions in compilers.items():
        lines.append(f"  {name:<8} {', '.join(versions) if versions else '(version n/a)'}")
    lines.append("")

    lines.extend(mpi_lines(profile))
    lines.append("")

    gpu = gpu_arches(profile)
    lines.append(f"gpu   {', '.join(gpu) if gpu else 'none'}")
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
    return "\n".join(lines)


def compiler_versions(profile: dict[str, Any]) -> OrderedDict[str, list[str]]:
    versions: OrderedDict[str, list[str]] = OrderedDict()
    for name in profile_compilers(profile):
        versions[name] = []
    vendor_cray = profile.get("vendor_cray") or {}
    for name in versions:
        if vendor_cray.get(name) and vendor_cray[name].get("version"):
            versions[name].append(vendor_cray[name]["version"])
    for compiler in profile.get("compilers_external") or []:
        name = compiler.get("name")
        if name in versions and compiler.get("version"):
            versions[name].append(compiler["version"])
    return versions


def mpi_lines(profile: dict[str, Any]) -> list[str]:
    providers: OrderedDict[str, dict[str, set]] = OrderedDict()
    for entry in profile.get("mpi") or []:
        name = entry.get("name")
        if not name:
            continue
        slot = providers.setdefault(name, {"versions": set(), "compilers": set()})
        if entry.get("version"):
            slot["versions"].add(entry["version"])
        if entry.get("compiler"):
            slot["compilers"].add(entry["compiler"])
    vendor_cray = profile.get("vendor_cray") or {}
    if vendor_cray.get("cray_mpich"):
        slot = providers.setdefault("cray-mpich", {"versions": set(), "compilers": set()})
        if vendor_cray["cray_mpich"].get("version"):
            slot["versions"].add(vendor_cray["cray_mpich"]["version"])

    if not providers:
        return ["mpi   none on system — built from source per defaults"]
    total = sum(1 for _ in profile.get("mpi") or [])
    head = f"mpi ({total} module variants → {len(providers)} providers)" if total else "mpi"
    lines = [head]
    for name, slot in providers.items():
        versions = ", ".join(sorted(slot["versions"])) or "(n/a)"
        compilers = (
            f"compilers: {', '.join(sorted(slot['compilers']))}" if slot["compilers"] else ""
        )
        lines.append(f"  {name:<10} {versions:<20} {compilers}".rstrip() + "   [platform]")
    return lines


def gpu_arches(profile: dict[str, Any]) -> list[str]:
    arches = {
        (node.get("gpu") or {}).get("arch_target")
        for node in (profile.get("node_types") or {}).values()
        if (node.get("gpu") or {}).get("arch_target")
    }
    return sorted(a for a in arches if a)


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
