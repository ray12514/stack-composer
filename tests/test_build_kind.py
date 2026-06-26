from __future__ import annotations

from stack_composer.model.contract import load_contract
from stack_composer.model.profile import load_profile
from stack_composer.render.plan import plan_lanes
from stack_composer.resolve.build_kind import infer_kind, normalize_build
from tests.conftest import fixture_path


def test_infer_kind_from_specs() -> None:
    assert infer_kind({"specs": ["hdf5@1.14.5+mpi+fortran"]}) == "mpi"
    assert infer_kind({"specs": ["kokkos+rocm"]}) == "gpu"
    assert infer_kind({"specs": ["raja+cuda"]}) == "gpu"
    # GPU wins over MPI when both appear.
    assert infer_kind({"specs": ["hdf5+mpi", "kokkos+rocm"]}) == "gpu"
    assert infer_kind({"specs": ["cmake", "ninja"]}) == "cpu"
    # specs-map keyed by kind is a signal too.
    assert infer_kind({"specs": {"any": ["gsl"], "mpi": ["hdf5+mpi"]}}) == "mpi"
    # explicit kind always wins.
    assert infer_kind({"kind": "gpu", "specs": ["cmake"]}) == "gpu"
    # package-set build with no inline specs defaults to cpu.
    assert infer_kind({"package_set": "science-full"}) == "cpu"


def test_normalize_build_fills_from_kind_defaults() -> None:
    contract = {
        "kind_defaults": {
            "mpi": {
                "class": "mpi",
                "toolchain": "science-mpi-default",
                "nodes": "cpu",
                "expand": "one",
            }
        }
    }
    out = normalize_build({"name": "sci", "specs": ["hdf5@1.14.5+mpi+fortran"]}, contract)
    assert out["kind"] == "mpi"
    assert out["class"] == "mpi"
    assert out["toolchain"] == "science-mpi-default"
    assert out["nodes"] == "cpu"
    assert out["expand"] == "one"


def test_normalize_build_explicit_fields_win() -> None:
    contract = {
        "kind_defaults": {
            "mpi": {"class": "mpi", "toolchain": "science-mpi-default", "nodes": "cpu"}
        }
    }
    build = {
        "name": "sci",
        "kind": "mpi",
        "class": "custom",
        "toolchain": "custom-tc",
        "nodes": "gpu",
        "expand": "per_gpu_arch",
        "specs": ["hdf5+mpi"],
    }
    out = normalize_build(build, contract)
    assert (out["class"], out["toolchain"], out["nodes"], out["expand"]) == (
        "custom",
        "custom-tc",
        "gpu",
        "per_gpu_arch",
    )


def test_normalize_build_expand_falls_back_per_kind() -> None:
    # No kind_defaults at all: expand still gets a per-kind fallback.
    out = normalize_build({"name": "g", "kind": "gpu", "package_set": "x"}, {})
    assert out["expand"] == "per_gpu_arch"
    out = normalize_build({"name": "c", "kind": "cpu", "package_set": "x"}, {})
    assert out["expand"] == "one"


def test_spec_native_renders_same_lanes_as_explicit() -> None:
    profile, profile_issues = load_profile(fixture_path("profiles", "example-cray", "profile.yaml"))
    contract, contract_issues = load_contract(
        fixture_path("template-sets", "v6", "contract.yaml")
    )
    assert profile_issues == []
    assert contract_issues == []

    explicit_stack = {
        "name": "science-stack",
        "builds": [
            {
                "name": "mpi",
                "class": "mpi",
                "package_set": "science-full",
                "toolchain": "science-mpi-default",
                "nodes": "cpu",
                "expand": "one",
            }
        ],
    }
    spec_native_stack = {
        "name": "science-stack",
        "builds": [{"name": "mpi", "kind": "mpi", "package_set": "science-full"}],
    }

    explicit_lanes, _, _, explicit_issues = plan_lanes(profile, explicit_stack, contract)
    native_lanes, _, _, native_issues = plan_lanes(profile, spec_native_stack, contract)

    assert explicit_issues == []
    assert native_issues == []
    assert native_lanes == explicit_lanes
    # Sanity: the cray profile resolves both compilers for the MPI lane.
    assert {lane["compiler"] for lane in native_lanes} == {"gcc", "cce"}
