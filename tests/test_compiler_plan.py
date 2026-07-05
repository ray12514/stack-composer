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
