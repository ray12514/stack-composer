from __future__ import annotations

import posixpath
from typing import Any

from stack_composer.errors import Issue

PAYLOAD_KINDS = ("serial", "mpi", "gpu")


def build_shared_exposure_plan(
    *,
    stack: dict[str, Any],
    lanes: list[dict[str, Any]],
    spec_sources: dict[str, dict[str, Any]],
) -> tuple[dict[str, Any], list[Issue]]:
    """Plan lane-agnostic payload exposure.

    A package set may declare `lane_agnostic:` package names: packages with no
    MPI implementation that are compiler/performance-sensitive (so not Core)
    but usable from serial and MPI code alike. They are built exactly once, in
    the compiler column's serial lane, and exposed — module visibility only,
    never a rebuild — in every payload lane of that column. The serial lane's
    environment emits their modulefiles into a per-compiler shared module root
    (a sibling of the lane package-module roots); every payload lane module
    prepends that root alongside its own.

    Under direct exposure every package module already lands in the one
    published root, so the declaration is trivially satisfied and the plan
    stays disabled.

    A compiler column with declaring mpi/gpu lanes but no serial lane gets a
    recorded warning, not an error: a stack that skips the serial kind never
    builds those packages — the declaration is vacuous there, exactly like any
    other kind the stack does not use.
    """
    exposure = (stack.get("modules") or {}).get("exposure", "front_door")
    plan: dict[str, Any] = {"enabled": False, "by_compiler": {}, "warnings": []}
    issues: list[Issue] = []

    declaring: dict[str, list[tuple[dict[str, Any], list[str]]]] = {}
    for lane in lanes:
        if lane.get("kind") not in PAYLOAD_KINDS:
            continue
        source = spec_sources.get(lane["source_build"]) or {}
        packages = source.get("lane_agnostic") or []
        if packages:
            declaring.setdefault(lane["compiler"], []).append((lane, list(packages)))
    if not declaring or exposure == "direct":
        return plan, issues

    for compiler, entries in sorted(declaring.items()):
        owners = [(lane, pkgs) for lane, pkgs in entries if lane["kind"] == "serial"]
        if not owners:
            declared_by = ", ".join(sorted(lane["name"] for lane, _ in entries))
            plan["warnings"].append(
                f"lane_agnostic packages are declared by {declared_by} but "
                f"compiler {compiler!r} derives no serial lane to build them; "
                f"no lane-agnostic exposure in this column"
            )
            continue
        if len(owners) > 1:
            owner_names = ", ".join(sorted(lane["name"] for lane, _ in owners))
            issues.append(
                Issue(
                    "error",
                    "lane-agnostic-ambiguous-owner",
                    f"lanes[{compiler}]",
                    f"lane_agnostic packages have more than one serial owner "
                    f"lane ({owner_names}) in compiler {compiler!r}; the shared "
                    f"module root needs exactly one",
                )
            )
            continue
        owner, packages = owners[0]
        plan["by_compiler"][compiler] = {
            "owner_lane": owner["name"],
            "packages": sorted(set(packages)),
            "shared_module_root": shared_module_root_for(owner),
        }

    plan["enabled"] = bool(plan["by_compiler"])
    return plan, issues


def shared_module_root_for(owner_lane: dict[str, Any]) -> str:
    """The per-compiler shared module root: a `shared` sibling of the lane
    package-module roots (modules/<release>/<system>/<stack>/<compiler>/shared)."""
    return posixpath.join(posixpath.dirname(owner_lane["package_module_root"]), "shared")


def lane_shared_module_set(
    lane: dict[str, Any], shared_exposure: dict[str, Any]
) -> dict[str, Any] | None:
    """The shared module set this lane's environment must emit, or None.

    Only the owning serial lane emits the set; consuming lanes reach it purely
    through MODULEPATH.
    """
    entry = shared_exposure["by_compiler"].get(lane["compiler"])
    if entry and entry["owner_lane"] == lane["name"]:
        return {"root": entry["shared_module_root"], "packages": entry["packages"]}
    return None


def shared_module_root_for_lane(
    lane: dict[str, Any], shared_exposure: dict[str, Any]
) -> str | None:
    """The shared module root a payload lane's selector module prepends, or None."""
    if lane.get("kind") not in PAYLOAD_KINDS:
        return None
    entry = shared_exposure["by_compiler"].get(lane["compiler"])
    return entry["shared_module_root"] if entry else None
