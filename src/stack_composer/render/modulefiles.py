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
    lanes: list[dict[str, Any]],
    release_tag: str,
    module_plan: dict[str, Any],
) -> None:
    """Render Tcl front-door modulefiles from an already-built module plan.

    Spack still generates package modulefiles. The stack-owned front door is a
    compiler init module plus one short lane module per published lane. The init
    module establishes the compiler/foundation layer and exposes lane modules;
    each lane module exposes only that lane's package-module root.

    The plan is required, never rebuilt here: the same object must feed this
    emitter and reports/render-plan.yaml, or the report can lie about the
    modulefiles on disk.
    """
    if not module_plan["enabled"]:
        return

    core_by_compiler = {
        lane["compiler"]: lane
        for lane in lanes
        if lane.get("kind") == "core"
    }
    public_lanes = [
        lane
        for lane in lanes
        if lane.get("publish", True) and not is_compiler_init_lane(lane)
    ]

    for init_entry in module_plan["init_modules"]:
        compiler = init_entry["compiler"]
        content = compiler_init_module_text(
            init_module_name=init_entry["name"],
            module_root=module_plan["module_root"],
            compiler=compiler,
            release_tag=release_tag,
            prereqs=init_entry["prereqs"],
            core_lane=core_by_compiler.get(compiler),
            lane_module_root=init_entry["lane_module_root"],
        )
        path = pending / init_entry["file"]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    for lane_entry in module_plan["lane_modules"]:
        lane = lane_by_name(public_lanes, lane_entry["lane"])
        content = lane_module_text(
            module_root=module_plan["module_root"],
            lane=lane,
            public_name=lane_entry["public_name"],
            release_tag=release_tag,
            prereqs=lane_entry["prereqs"],
            conflicts=lane_entry["conflicts"],
        )
        path = pending / lane_entry["file"]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")


def build_front_door_module_plan(
    *,
    profile: dict[str, Any],
    stack: dict[str, Any],
    lanes: list[dict[str, Any]],
    release_tag: str,
) -> dict[str, Any]:
    """Describe stack-owned module exposure for the current front-door model.

    Spack owns package modulefiles. Stack Composer owns the presentation layer
    that lets a user reach those package modules: compiler init modules and lane
    selector modules. This plan is the explicit contract shared by reports and
    the modulefile emitter.
    """
    modules = stack.get("modules") or {}
    exposure = modules.get("exposure", "front_door")
    module_root = modules.get("module_root")
    plan: dict[str, Any] = {
        "exposure": exposure,
        "enabled": False,
        "module_root": module_root,
        "release": release_tag,
        "init_modules": [],
        "lane_modules": [],
    }
    if exposure != "front_door" or not module_root:
        return plan

    core_by_compiler = {
        lane["compiler"]: lane
        for lane in lanes
        if lane.get("kind") == "core"
    }
    public_lanes = [
        lane
        for lane in lanes
        if lane.get("publish", True) and not is_compiler_init_lane(lane)
    ]
    public_names = lane_public_names(public_lanes)

    for compiler in sorted({lane["compiler"] for lane in lanes if lane.get("publish", True)}):
        fake_lane = {"name": f"{compiler}-init", "compiler": compiler}
        prereqs, issues = platform_module_prereqs_for_lane(fake_lane, profile)
        if issues:
            raise ValidationFailed(issues)
        name = compiler_init_module_name(module_root, compiler)
        core_lane = core_by_compiler.get(compiler)
        plan["init_modules"].append(
            {
                "name": name,
                "compiler": compiler,
                "file": posixpath.join("modulefiles", name),
                "prereqs": prereqs,
                "core_lane": core_lane["name"] if core_lane else None,
                "core_view_root": core_lane["view_root"] if core_lane else None,
                "lane_module_root": lane_module_root_for_compiler(compiler, lanes),
            }
        )

    for lane in public_lanes:
        prereqs, issues = platform_module_prereqs_for_lane(lane, profile)
        if issues:
            raise ValidationFailed(issues)
        public_name = public_names[lane["name"]]
        display = compiler_display(lane["compiler"])
        conflicts = [
            posixpath.join(module_root, display, name)
            for lane_name, name in sorted(public_names.items())
            if lane_name != lane["name"]
            and lane_by_name(public_lanes, lane_name)["compiler"] == lane["compiler"]
        ]
        plan["lane_modules"].append(
            {
                "lane": lane["name"],
                "lane_id": lane["lane"],
                "compiler": lane["compiler"],
                "kind": lane["kind"],
                "public_name": public_name,
                "file": posixpath.join(
                    "modulefiles",
                    lane["compiler"],
                    "lanes",
                    module_root,
                    display,
                    public_name,
                ),
                "prereqs": prereqs,
                "conflicts": conflicts,
                "view_root": lane["view_root"],
                "package_module_root": lane["package_module_root"],
            }
        )

    plan["enabled"] = bool(plan["init_modules"] or plan["lane_modules"])
    return plan


def is_compiler_init_lane(lane: dict[str, Any]) -> bool:
    return lane.get("kind") == "core"


# Known compiler display casings for the public cse/<Compiler>/<Lane> names.
_COMPILER_DISPLAY = {
    "gcc": "GCC",
    "cce": "CCE",
    "aocc": "AOCC",
    "nvhpc": "NVHPC",
    "intel": "Intel",
    "oneapi": "oneAPI",
    "rocmcc": "ROCmCC",
    "clang": "Clang",
}


def compiler_display(compiler: str) -> str:
    if compiler in _COMPILER_DISPLAY:
        return _COMPILER_DISPLAY[compiler]
    return compiler.upper() if len(compiler) <= 4 else compiler.capitalize()


def compiler_init_module_name(module_root: str, compiler: str) -> str:
    return posixpath.join(module_root, compiler_display(compiler))


def lane_module_root_for_compiler(compiler: str, lanes: list[dict[str, Any]]) -> str:
    lane = next(lane for lane in lanes if lane["compiler"] == compiler)
    return posixpath.join(posixpath.dirname(lane["package_module_root"]), "lanes")


_KIND_DISPLAY = {"serial": "Serial", "mpi": "MPI", "gpu": "GPU", "core": "Core"}


def lane_public_names(lanes: list[dict[str, Any]]) -> dict[str, str]:
    """Public lane names: the capitalized kind, qualified by the distinguishing
    fact only when the same compiler surface has more than one lane of that
    kind (two MPIs -> MPI-<impl>; two GPU archs -> GPU-<arch>), never by
    contents. Same rule toolchain names follow."""
    by_compiler: dict[str, list[dict[str, Any]]] = {}
    for lane in lanes:
        by_compiler.setdefault(lane["compiler"], []).append(lane)

    names: dict[str, str] = {}
    for compiler_lanes in by_compiler.values():
        chains = {lane["name"]: name_candidates(lane) for lane in compiler_lanes}
        level = {lane["name"]: 0 for lane in compiler_lanes}
        for _ in range(max(len(chain) for chain in chains.values())):
            picked = {
                name: chains[name][min(lvl, len(chains[name]) - 1)]
                for name, lvl in level.items()
            }
            counts = Counter(picked.values())
            colliding = [name for name, value in picked.items() if counts[value] > 1]
            if not colliding:
                break
            for name in colliding:
                level[name] += 1
        for lane in compiler_lanes:
            chain = chains[lane["name"]]
            names[lane["name"]] = chain[min(level[lane["name"]], len(chain) - 1)]
    return names


def kind_display(lane: dict[str, Any]) -> str:
    kind = str(lane.get("kind") or "")
    return _KIND_DISPLAY.get(kind, kind or str(lane["lane"]))


def name_candidates(lane: dict[str, Any]) -> list[str]:
    """Qualification chain: bare kind, then the distinguishing facts in order,
    then the always-unique internal lane id."""
    base = kind_display(lane)
    kind = lane.get("kind")
    chain = [base]
    arch = lane.get("gpu_arch")
    provider = lane.get("mpi_provider")
    if kind == "gpu":
        if arch:
            chain.append(f"{base}-{arch}")
        if provider:
            chain.append(f"{base}-{provider_token(provider)}")
        if arch and provider:
            chain.append(f"{base}-{provider_token(provider)}-{arch}")
    elif kind == "mpi" and provider:
        chain.append(f"{base}-{provider_token(provider)}")
    else:
        build = lane.get("source_build")
        if build and str(build) != str(kind):
            chain.append(f"{base}-{build}")
    chain.append(str(lane["lane"]))
    return chain


def provider_token(provider: object) -> str:
    return str(provider).replace("-", "")


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
        f'module-whatis "{tcl_quote(module_root)} compiler surface: '
        f'{tcl_quote(compiler_display(compiler))}"',
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
        f"{tcl_quote(compiler_display(lane['compiler']))} {tcl_quote(public_name)}"
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
