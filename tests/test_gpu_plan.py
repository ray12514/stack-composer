from __future__ import annotations

from stack_composer.render.gpu import build_gpu_plan
from stack_composer.render.scopes import gpu_external_packages
from tests.test_render_scopes import fixture_context


def test_gpu_plan_resolves_rocm_toolkit_externals() -> None:
    # The plan layer resolves the GPU toolkit externals once so the gpu scope
    # templates only print. A Cray+ROCm profile exposes hip under the rocm key.
    profile, _stack = fixture_context("example-cray")

    plan = build_gpu_plan(profile)

    assert "rocm" in plan
    names = [package["name"] for package in plan["rocm"]]
    assert "hip" in names


def test_gpu_plan_matches_the_template_global_it_replaces() -> None:
    profile, _stack = fixture_context("example-cray")

    plan = build_gpu_plan(profile)

    assert plan.get("rocm", []) == gpu_external_packages(profile, "rocm")
    assert plan.get("cuda", []) == gpu_external_packages(profile, "cuda")
