from __future__ import annotations

from stack_composer.render.gpu import build_gpu_plan, gpu_external_packages, select_gpu_toolkit
from tests.test_render_scopes import fixture_context


def test_select_gpu_toolkit_picks_latest_version() -> None:
    # Cluster Inspector reports every installed toolkit generation; the render
    # selects one. Default policy is latest (compatibility-matrix selection is a
    # documented follow-up).
    profile = {
        "gpu_toolkit_modules": {
            "rocm": [
                {"version": "6.0.0", "module": "rocm/6.0.0", "prefix": "/opt/rocm-6.0.0"},
                {"version": "7.0.0", "module": "rocm/7.0.0", "prefix": "/opt/rocm-7.0.0"},
            ]
        }
    }

    selected = select_gpu_toolkit(profile, "rocm")

    assert selected["version"] == "7.0.0"


def test_select_gpu_toolkit_empty_when_family_absent() -> None:
    assert select_gpu_toolkit({"gpu_toolkit_modules": {}}, "rocm") == {}


def test_gpu_plan_renders_latest_rocm_generation() -> None:
    # End-to-end: two ROCm generations installed; the plan renders the latest.
    profile = {
        "gpu_toolkit_modules": {
            "rocm": [
                {
                    "version": "6.0.0",
                    "module": "rocm/6.0.0",
                    "prefix": "/opt/rocm-6.0.0",
                    "spack_components": [{"package": "hip", "prefix": "/opt/rocm-6.0.0"}],
                },
                {
                    "version": "7.0.0",
                    "module": "rocm/7.0.0",
                    "prefix": "/opt/rocm-7.0.0",
                    "spack_components": [{"package": "hip", "prefix": "/opt/rocm-7.0.0"}],
                },
            ]
        }
    }

    plan = build_gpu_plan(profile)

    hip = next(p for p in plan["rocm"] if p["name"] == "hip")
    assert hip["externals"][0]["spec"] == "hip@7.0.0"
    assert hip["externals"][0]["modules"] == ["rocm/7.0.0"]


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
