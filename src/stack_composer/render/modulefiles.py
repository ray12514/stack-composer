from __future__ import annotations

import posixpath
from collections import Counter
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
    """Render Tcl front-door modulefiles.

    Spack still generates package modulefiles. The stack-owned front door is a
    compiler init module plus one short lane module per published lane. The init
    module establishes the compiler/foundation layer and exposes lane modules;
    each lane module exposes only that lane's package-module root.
    """
    modules = stack.get("modules") or {}
    if modules.get("exposure", "front_door") != "front_door":
        return
    module_root = modules.get("module_root")
    if not module_root:
        return
    init_module = modules.get("init_module")
    core_by_compiler = {
        lane["compiler"]: lane
        for lane in lanes
        if lane.get("kind") == "cpu" and lane.get("lane") == "core"
    }
    public_lanes = [
        lane
        for lane in lanes
        if lane.get("publish", True) and not is_compiler_init_lane(lane)
    ]
    public_names = lane_public_names(public_lanes)

    for compiler in sorted({lane["compiler"] for lane in lanes if lane.get("publish", True)}):
        if not init_module:
            continue
        fake_lane = {"name": f"{compiler}-init", "compiler": compiler}
        prereqs, issues = platform_module_prereqs_for_lane(fake_lane, profile)
        if issues:
            raise ValidationFailed(issues)
        lane_root = lane_module_root_for_compiler(compiler, lanes)
        content = compiler_init_module_text(
            init_module_name=compiler_init_module_name(init_module, compiler),
            module_root=module_root,
            compiler=compiler,
            release_tag=release_tag,
            prereqs=prereqs,
            core_lane=core_by_compiler.get(compiler),
            lane_module_root=lane_root,
        )
        path = pending / "modulefiles" / compiler_init_module_name(init_module, compiler)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    for lane in public_lanes:
        if not lane.get("publish", True):
            continue
        prereqs, issues = platform_module_prereqs_for_lane(lane, profile)
        if issues:
            raise ValidationFailed(issues)
        public_name = public_names[lane["name"]]
        content = lane_module_text(
            module_root=module_root,
            lane=lane,
            public_name=public_name,
            release_tag=release_tag,
            prereqs=prereqs,
            conflicts=[
                f"{module_root}/{name}"
                for lane_name, name in sorted(public_names.items())
                if lane_name != lane["name"]
                and lane_by_name(public_lanes, lane_name)["compiler"] == lane["compiler"]
            ],
        )
        path = pending / "modulefiles" / lane["compiler"] / "lanes" / module_root / public_name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")


def is_compiler_init_lane(lane: dict[str, Any]) -> bool:
    return lane.get("kind") == "cpu" and lane.get("lane") == "core"


def compiler_init_module_name(init_module: str, compiler: str) -> str:
    return f"{init_module}_{compiler}"


def lane_module_root_for_compiler(compiler: str, lanes: list[dict[str, Any]]) -> str:
    lane = next(lane for lane in lanes if lane["compiler"] == compiler)
    return posixpath.join(posixpath.dirname(lane["package_module_root"]), "lanes")


def lane_public_names(lanes: list[dict[str, Any]]) -> dict[str, str]:
    by_compiler: dict[str, list[dict[str, Any]]] = {}
    for lane in lanes:
        by_compiler.setdefault(lane["compiler"], []).append(lane)

    names: dict[str, str] = {}
    for compiler_lanes in by_compiler.values():
        preferred = {lane["name"]: preferred_lane_name(lane) for lane in compiler_lanes}
        counts = Counter(preferred.values())
        fallback = {
            lane["name"]: fallback_lane_name(lane)
            for lane in compiler_lanes
            if counts[preferred[lane["name"]]] > 1
        }
        fallback_counts = Counter(fallback.values())
        for lane in compiler_lanes:
            name = preferred[lane["name"]]
            if counts[name] > 1:
                name = fallback[lane["name"]]
            if fallback_counts.get(name, 0) > 1:
                name = lane["lane"]
            names[lane["name"]] = name
    return names


def preferred_lane_name(lane: dict[str, Any]) -> str:
    if lane.get("kind") in {"mpi", "gpu"}:
        return lane["kind"]
    return fallback_lane_name(lane)


def fallback_lane_name(lane: dict[str, Any]) -> str:
    return str(lane.get("source_build") or lane["lane"])


def lane_by_name(lanes: list[dict[str, Any]], name: str) -> dict[str, Any]:
    return next(lane for lane in lanes if lane["name"] == name)


def compiler_init_module_text(
    *,
    init_module_name: str,
    module_root: str,
    compiler: str,
    release_tag: str,
    prereqs: list[str],
    core_lane: dict[str, Any] | None,
    lane_module_root: str,
) -> str:
    lines = [
        "#%Module1.0",
        f'module-whatis "{tcl_quote(module_root)} compiler environment: {tcl_quote(compiler)}"',
        "",
    ]
    for prereq in prereqs:
        lines.append(f"prereq {prereq}")
    if prereqs:
        lines.append("")
    lines.extend(
        [
            f'setenv STACK_RELEASE "{tcl_quote(release_tag)}"',
            f'setenv STACK_COMPILER "{tcl_quote(compiler)}"',
            f'setenv STACK_INIT_MODULE "{tcl_quote(init_module_name)}"',
            "",
        ]
    )
    if core_lane is not None:
        lines.extend(view_path_lines(core_lane["view_root"]))
        lines.append("")
    lines.append(f'prepend-path MODULEPATH "{tcl_quote(lane_module_root)}"')
    lines.append("")
    return "\n".join(lines)


def view_path_lines(view_root: str) -> list[str]:
    return [
        f'prepend-path PATH "{tcl_quote(posixpath.join(view_root, "bin"))}"',
        f'prepend-path CPATH "{tcl_quote(posixpath.join(view_root, "include"))}"',
        f'prepend-path LIBRARY_PATH "{tcl_quote(posixpath.join(view_root, "lib"))}"',
        f'prepend-path LIBRARY_PATH "{tcl_quote(posixpath.join(view_root, "lib64"))}"',
        f'prepend-path LD_LIBRARY_PATH "{tcl_quote(posixpath.join(view_root, "lib"))}"',
        f'prepend-path LD_LIBRARY_PATH "{tcl_quote(posixpath.join(view_root, "lib64"))}"',
    ]


def lane_module_text(
    *,
    module_root: str,
    lane: dict[str, Any],
    public_name: str,
    release_tag: str,
    prereqs: list[str],
    conflicts: list[str],
) -> str:
    whatis = (
        f"{tcl_quote(module_root)} lane: "
        f"{tcl_quote(lane['compiler'])} {tcl_quote(public_name)}"
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
            f'setenv STACK_LANE "{tcl_quote(public_name)}"',
            f'setenv STACK_LANE_ID "{tcl_quote(lane["lane"])}"',
            f'setenv STACK_VIEW "{tcl_quote(lane["view_root"])}"',
            "",
        ]
    )
    lines.append(f'prepend-path MODULEPATH "{tcl_quote(lane["package_module_root"])}"')
    lines.append("")
    return "\n".join(lines)


def tcl_quote(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')
