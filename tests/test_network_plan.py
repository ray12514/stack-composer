from __future__ import annotations

from copy import deepcopy

from stack_composer.render.network import build_mpi_plan
from stack_composer.render.plan import plan_lanes
from tests.test_render_scopes import fixture_context


def test_mpi_plan_resolves_selected_cray_mpich_externals_and_toolchains() -> None:
    # The plan layer resolves MPI selection once so templates only print. For a
    # Cray lane it must expose the lane-selected cray-mpich as a package with a
    # bound-compiler external and a matching toolchain — the same decisions the
    # template used to compute inline.
    profile, stack = fixture_context("example-cray")
    lanes, _skipped, _narrowing, issues = plan_lanes(profile, stack)
    assert issues == []

    plan = build_mpi_plan(profile, lanes)

    assert "cray-mpich" in plan
    packages = plan["cray-mpich"]["packages"]
    specs = [
        external["spec"]
        for package in packages
        for external in package["externals"]
    ]
    # The external pins the wrapper mode; the compiler binding lives in the
    # toolchain, not on the external.
    assert "cray-mpich@8.1.29 +wrappers" in specs

    toolchains = {
        toolchain["name"]: toolchain["entries"]
        for toolchain in plan["cray-mpich"]["toolchains"]
    }
    assert "gcc1330_craympich8129" in toolchains
    assert {"spec": "%c=gcc@13.3.0", "when": "%c"} in toolchains["gcc1330_craympich8129"]
    assert {"spec": "%mpi=cray-mpich@8.1.29+wrappers", "when": "%mpi"} in toolchains[
        "gcc1330_craympich8129"
    ]


def test_mpi_plan_only_covers_providers_used_by_lanes() -> None:
    profile, stack = fixture_context("example-cray")
    lanes, _skipped, _narrowing, issues = plan_lanes(profile, stack)
    assert issues == []

    plan = build_mpi_plan(profile, lanes)

    # example-cray lanes use cray-mpich only; openmpi has no lane, so it is not
    # in the plan (nothing to render for it).
    assert set(plan) == {"cray-mpich"}


def test_mpi_plan_matches_the_template_globals_it_replaces() -> None:
    # Guard: the resolved plan is exactly what the Jinja globals produced, so
    # moving the call out of the template changes no rendered output.
    from stack_composer.render.scopes import mpi_external_packages, mpi_toolchains

    profile, stack = fixture_context("example-cray")
    lanes, _skipped, _narrowing, _issues = plan_lanes(deepcopy(profile), deepcopy(stack))

    plan = build_mpi_plan(profile, lanes)

    assert plan["cray-mpich"]["packages"] == mpi_external_packages(profile, "cray-mpich", lanes)
    assert plan["cray-mpich"]["toolchains"] == mpi_toolchains(profile, lanes, "cray-mpich")
