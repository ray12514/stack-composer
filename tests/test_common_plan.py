from __future__ import annotations

from stack_composer.render.common import build_common_plan
from stack_composer.render.plan import plan_lanes
from stack_composer.render.scopes import common_external_packages
from tests.test_render_scopes import fixture_context


def test_common_plan_resolves_externals_default_provider_and_target() -> None:
    # The plan layer resolves the common scope's externals, default MPI
    # provider, and target preference once so the common template only prints.
    profile, stack = fixture_context("example-cray")
    lanes, _skipped, _narrowing, issues = plan_lanes(profile, stack)
    assert issues == []

    plan = build_common_plan(profile, stack, lanes)

    external_names = [package["name"] for package in plan["externals"]]
    assert "openssl" in external_names
    assert plan["default_mpi_provider"] == "cray-mpich"
    assert plan["target_prefer"] == lanes[0]["target"]


def test_common_plan_externals_match_the_template_global_it_replaces() -> None:
    profile, stack = fixture_context("example-cray")
    lanes, _skipped, _narrowing, _issues = plan_lanes(profile, stack)

    plan = build_common_plan(profile, stack, lanes)

    assert plan["externals"] == common_external_packages(profile, stack)


def test_common_plan_default_provider_is_none_without_mpi_lanes() -> None:
    profile, stack = fixture_context("example-cray")
    stack["builds"] = [{"name": "core", "kind": "core", "specs": ["zlib"], "compilers": ["gcc"]}]
    stack["per_system"] = {}
    lanes, _skipped, _narrowing, issues = plan_lanes(profile, stack)
    assert issues == []

    plan = build_common_plan(profile, stack, lanes)

    assert plan["default_mpi_provider"] is None
