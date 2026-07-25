from __future__ import annotations

from stack_composer.render.compilers import build_compiler_plan
from stack_composer.render.plan import plan_lanes
from stack_composer.render.scopes import compiler_external_packages
from tests.test_render_scopes import fixture_context


def test_compiler_plan_resolves_externals_per_vendor_scope() -> None:
    # The plan layer resolves the compiler externals for each vendor scope a
    # lane uses, so the vendor macro only prints.
    profile, stack = fixture_context("example-cray")
    lanes, _skipped, _narrowing, issues = plan_lanes(profile, stack)
    assert issues == []

    plan = build_compiler_plan(profile, stack, lanes)

    assert "vendor/cray" in plan
    names = [package["name"] for package in plan["vendor/cray"]]
    assert "gcc" in names


def test_compiler_plan_matches_the_template_global_it_replaces() -> None:
    profile, stack = fixture_context("example-cray")
    lanes, _skipped, _narrowing, _issues = plan_lanes(profile, stack)

    plan = build_compiler_plan(profile, stack, lanes)

    assert plan["vendor/cray"] == compiler_external_packages(profile, stack, "vendor/cray")


def stack_building_its_own_compiler(stack: dict, version: str) -> dict:
    """A stack that names a compiler to build rather than consume."""
    from copy import deepcopy

    stack = deepcopy(stack)
    stack["compilers"] = [f"gcc@{version}"]
    stack["externals"] = {**(stack.get("externals") or {}), "compilers": "build_all"}
    # Builds in this fixture carry their own `compilers: all`, which outranks
    # the stack-level selection; pin them too so the posture is what is tested.
    for build in stack.get("builds", []):
        build["compilers"] = [f"gcc@{version}"]
    stack.pop("per_system", None)
    return stack


def test_build_all_accepts_a_compiler_the_profile_does_not_report() -> None:
    # Under build_all the stack names the version to build, so requiring the
    # profile to already report it would make the posture unusable: a compiler
    # we intend to build is by definition not installed yet.
    profile, stack = fixture_context("example-cray")
    stack = stack_building_its_own_compiler(stack, "14.3.0")

    lanes, _skipped, _narrowing, issues = plan_lanes(profile, stack)

    assert not [issue for issue in issues if issue.code == "compilers_missing"], (
        f"build_all must not require profile presence; got {[i.code for i in issues]}"
    )
    assert lanes, "a stack-built compiler must still produce lanes"
    assert {lane["compiler_ref"] for lane in lanes} == {"gcc@14.3.0"}


def test_build_all_emits_no_compiler_externals() -> None:
    # A compiler scope's whole effect is `buildable: false` plus an external
    # prefix. Emitting one under build_all would pin the platform compiler and
    # silently defeat the posture.
    profile, stack = fixture_context("example-cray")
    stack = stack_building_its_own_compiler(stack, "14.3.0")
    lanes, _skipped, _narrowing, _issues = plan_lanes(profile, stack)

    plan = build_compiler_plan(profile, stack, lanes)

    pinned = [
        package
        for packages in plan.values()
        for package in packages
        if package.get("buildable") is False
    ]
    assert not pinned, f"build_all must not pin a compiler as an external: {pinned}"
