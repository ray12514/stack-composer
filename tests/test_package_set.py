from __future__ import annotations

from stack_composer.model.package_set import expand_gpu_variant, expand_specs_for_lane


def test_expands_gpu_placeholder_for_amd_lane() -> None:
    lane = {"kind": "gpu", "gpu_arch": "gfx90a"}

    assert expand_gpu_variant("kokkos+gpu", lane) == "kokkos+rocm amdgpu_target=gfx90a"


def test_expands_gpu_placeholder_for_nvidia_lane() -> None:
    lane = {"kind": "gpu", "gpu_arch": "sm_80"}

    assert expand_gpu_variant("kokkos+gpu", lane) == "kokkos+cuda cuda_arch=80"


def test_preserves_existing_gpu_arch_flags() -> None:
    lane = {"kind": "gpu", "gpu_arch": "gfx90a"}

    assert (
        expand_gpu_variant("kokkos+rocm amdgpu_target=gfx942", lane)
        == "kokkos+rocm amdgpu_target=gfx942"
    )


def test_expands_package_set_specs_for_lane_kind() -> None:
    spec_source = {
        "specs": {
            "any": ["gsl@2.8"],
            "gpu": ["kokkos+gpu"],
            "mpi": ["hdf5+mpi"],
        }
    }
    lane = {"kind": "gpu", "gpu_arch": "sm_80"}

    assert expand_specs_for_lane(spec_source, lane) == [
        "gsl@2.8",
        "kokkos+cuda cuda_arch=80",
    ]
