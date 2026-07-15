from __future__ import annotations

from stack_composer.model.package_set import (
    decorate_toolchain,
    expand_gpu_variant,
    expand_specs_for_lane,
)


def test_expands_gpu_placeholder_for_amd_lane() -> None:
    lane = {"kind": "gpu", "gpu_arch": "gfx90a"}

    assert expand_gpu_variant("kokkos+gpu", lane) == "kokkos+rocm amdgpu_target=gfx90a"


def test_expands_gpu_placeholder_for_nvidia_lane() -> None:
    lane = {"kind": "gpu", "gpu_arch": "sm_80"}

    assert expand_gpu_variant("kokkos+gpu", lane) == "kokkos+cuda cuda_arch=80"


def test_keeps_user_authored_gpu_arch_flags() -> None:
    lane = {"kind": "gpu", "gpu_arch": "gfx90a"}

    assert (
        expand_gpu_variant("kokkos+rocm amdgpu_target=gfx942", lane)
        == "kokkos+rocm amdgpu_target=gfx942"
    )


def test_gpu_runtime_placeholder_takes_the_backend_without_an_arch() -> None:
    # tau traces the GPU runtime rather than compiling device code, and its
    # recipe has no amdgpu_target/cuda_arch variant: rendering one would fail
    # concretization.
    amd = {"kind": "gpu", "gpu_arch": "gfx942"}
    nvidia = {"kind": "gpu", "gpu_arch": "sm_80"}

    assert expand_gpu_variant("tau+mpi+gpu_runtime", amd) == "tau+mpi+rocm"
    assert expand_gpu_variant("tau+mpi+gpu_runtime", nvidia) == "tau+mpi+cuda"


def test_gpu_runtime_placeholder_is_not_mangled_by_the_gpu_substring() -> None:
    # "+gpu" is a substring of "+gpu_runtime"; a naive replace would emit
    # "+rocm_runtime".
    lane = {"kind": "gpu", "gpu_arch": "gfx942"}

    resolved = expand_gpu_variant("tau+gpu_runtime", lane)
    assert resolved == "tau+rocm"
    assert "_runtime" not in resolved


def test_decorates_undecorated_spec_with_lane_toolchain() -> None:
    lane = {"toolchain": "gcc1140_openmpi416"}

    assert decorate_toolchain("hdf5+mpi", lane) == "hdf5+mpi %gcc1140_openmpi416"


def test_skips_spec_that_already_carries_a_compiler_or_toolchain() -> None:
    # A user-authored spec with its own %... qualification is never
    # double-decorated; their choice wins over the lane toolchain.
    lane = {"toolchain": "gcc1140_openmpi416"}

    assert decorate_toolchain("hdf5+mpi %aocc_site_mpi", lane) == "hdf5+mpi %aocc_site_mpi"
    assert decorate_toolchain("hdf5+mpi %gcc@11.4.0", lane) == "hdf5+mpi %gcc@11.4.0"


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
