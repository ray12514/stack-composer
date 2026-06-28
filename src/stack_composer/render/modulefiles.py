from __future__ import annotations

from pathlib import Path
from typing import Any

from stack_composer.errors import ValidationFailed
from stack_composer.render.platform_modules import platform_module_prereqs_for_lane


def render_front_door_modules(
    *,
    pending: Path,
    profile: dict[str, Any],
    stack: dict[str, Any],
    lanes: list[dict[str, Any]],
    release_tag: str,
) -> None:
    """Render Tcl lane selector modulefiles.

    Spack still generates package modulefiles. These selectors are the
    stack-owned front door: one module per rendered lane that validates platform
    prereqs and prepends the lane package-module roots.
    """
    modules = stack.get("modules") or {}
    if modules.get("exposure", "front_door") != "front_door":
        return
    module_root = modules.get("module_root")
    if not module_root:
        return
    core_by_compiler = {
        lane["compiler"]: lane
        for lane in lanes
        if lane.get("kind") == "cpu" and lane.get("lane") == "core"
    }
    selector_names = {
        lane["name"]: selector_name(module_root, lane)
        for lane in lanes
        if lane.get("publish", True)
    }
    for lane in lanes:
        if not lane.get("publish", True):
            continue
        prereqs, issues = platform_module_prereqs_for_lane(lane, profile)
        if issues:
            raise ValidationFailed(issues)
        content = front_door_module_text(
            module_root=module_root,
            lane=lane,
            release_tag=release_tag,
            prereqs=prereqs,
            conflicts=[
                name
                for lane_name, name in sorted(selector_names.items())
                if lane_name != lane["name"]
            ],
            module_roots=module_roots_for_lane(lane, core_by_compiler.get(lane["compiler"])),
        )
        path = pending / "modulefiles" / module_root / lane["compiler"] / lane["lane"]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")


def selector_name(module_root: str, lane: dict[str, Any]) -> str:
    return f"{module_root}/{lane['compiler']}/{lane['lane']}"


def module_roots_for_lane(
    lane: dict[str, Any], core_lane: dict[str, Any] | None
) -> list[str]:
    roots: list[str] = []
    if core_lane is not None:
        roots.append(core_lane["package_module_root"])
    if lane["package_module_root"] not in roots:
        roots.append(lane["package_module_root"])
    return roots


def front_door_module_text(
    *,
    module_root: str,
    lane: dict[str, Any],
    release_tag: str,
    prereqs: list[str],
    conflicts: list[str],
    module_roots: list[str],
) -> str:
    whatis = (
        f"{tcl_quote(module_root)} lane: "
        f"{tcl_quote(lane['compiler'])} {tcl_quote(lane['lane'])}"
    )
    lines = [
        "#%Module1.0",
        f'module-whatis "{whatis}"',
        "",
    ]
    for conflict in conflicts:
        lines.append(f"conflict {conflict}")
    if conflicts:
        lines.append("")
    for prereq in prereqs:
        lines.append(f"prereq {prereq}")
    if prereqs:
        lines.append("")
    lines.extend(
        [
            f'setenv STACK_RELEASE "{tcl_quote(release_tag)}"',
            f'setenv STACK_COMPILER "{tcl_quote(lane["compiler"])}"',
            f'setenv STACK_LANE "{tcl_quote(lane["lane"])}"',
            f'setenv STACK_VIEW "{tcl_quote(lane["view_root"])}"',
            "",
        ]
    )
    for root in module_roots:
        lines.append(f'prepend-path MODULEPATH "{tcl_quote(root)}"')
    lines.append("")
    return "\n".join(lines)


def tcl_quote(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')
