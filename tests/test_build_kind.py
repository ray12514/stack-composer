from __future__ import annotations

from stack_composer.model.profile import load_profile
from stack_composer.model.stack import load_defaults, merge_defaults
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


def test_normalize_build_sets_kind() -> None:
    out = normalize_build({"name": "sci", "specs": ["hdf5@1.14.5+mpi+fortran"]})
    assert out["kind"] == "mpi"
    out = normalize_build({"name": "g", "kind": "gpu", "specs": ["cmake"]})
    assert out["kind"] == "gpu"
    out = normalize_build({"name": "c", "package_set": "x"})
    assert out["kind"] == "cpu"


def _v6_defaults() -> dict:
    defaults, issues = load_defaults(fixture_path("template-sets", "v6", "defaults.yaml"))
    assert issues == []
    return defaults


def test_spec_native_mpi_resolves_against_defaults_and_profile() -> None:
    profile, profile_issues = load_profile(fixture_path("profiles", "example-cray", "profile.yaml"))
    assert profile_issues == []
    stack = merge_defaults(
        _v6_defaults(),
        {
            "name": "science-stack",
            "builds": [{"name": "mpi", "kind": "mpi", "package_set": "science-full"}],
        },
    )
    lanes, _, _, issues = plan_lanes(profile, stack)
    assert issues == []
    # Cray auto-selects the platform MPI (cray-mpich) for an mpi build.
    assert lanes
    assert all(lane["mpi_provider"] == "cray-mpich" for lane in lanes)
    assert all(lane["mpi_source"] == "platform" for lane in lanes)
    # The science compilers the profile reports resolve into lanes.
    assert {"gcc", "cce"} <= {lane["compiler"] for lane in lanes}


def test_per_build_compiler_override_narrows_lanes() -> None:
    profile, _ = load_profile(fixture_path("profiles", "example-cray", "profile.yaml"))
    stack = merge_defaults(
        _v6_defaults(),
        {
            "name": "science-stack",
            "builds": [
                {"name": "mpi", "kind": "mpi", "package_set": "science-full", "compilers": ["gcc"]}
            ],
        },
    )
    lanes, _, _, issues = plan_lanes(profile, stack)
    assert issues == []
    assert {lane["compiler"] for lane in lanes} == {"gcc"}
