from __future__ import annotations

from stack_composer.render.modulefiles import (
    compiler_display,
    compiler_init_module_name,
    lane_public_names,
)


def lane(name: str, kind: str, **extra: object) -> dict[str, object]:
    return {"name": name, "compiler": "gcc", "lane": name, "kind": kind, **extra}


def test_compiler_display_names() -> None:
    assert compiler_display("gcc") == "GCC"
    assert compiler_display("cce") == "CCE"
    assert compiler_display("aocc") == "AOCC"
    assert compiler_display("oneapi") == "oneAPI"
    assert compiler_display("somethinglong") == "Somethinglong"


def test_init_module_is_root_slash_compiler() -> None:
    assert compiler_init_module_name("cse", "gcc") == "cse/GCC"


def test_unambiguous_lanes_get_bare_capitalized_names() -> None:
    lanes = [
        lane("serial", "serial"),
        lane("mpi", "mpi", mpi_provider="cray-mpich"),
        lane("gpu", "gpu", mpi_provider="cray-mpich", gpu_arch="gfx942"),
    ]

    assert lane_public_names(lanes) == {
        "serial": "Serial",
        "mpi": "MPI",
        "gpu": "GPU",
    }


def test_two_mpi_providers_qualify_the_mpi_lanes() -> None:
    lanes = [
        lane("mpi-a", "mpi", mpi_provider="openmpi"),
        lane("mpi-b", "mpi", mpi_provider="mpich"),
    ]

    assert lane_public_names(lanes) == {
        "mpi-a": "MPI-openmpi",
        "mpi-b": "MPI-mpich",
    }


def test_two_gpu_archs_qualify_the_gpu_lanes() -> None:
    lanes = [
        lane("gpu-1", "gpu", mpi_provider="cray-mpich", gpu_arch="gfx90a"),
        lane("gpu-2", "gpu", mpi_provider="cray-mpich", gpu_arch="gfx942"),
    ]

    assert lane_public_names(lanes) == {
        "gpu-1": "GPU-gfx90a",
        "gpu-2": "GPU-gfx942",
    }


def test_gpu_lanes_same_arch_qualify_by_mpi() -> None:
    lanes = [
        lane("gpu-o", "gpu", mpi_provider="openmpi", gpu_arch="sm_80"),
        lane("gpu-m", "gpu", mpi_provider="mpich", gpu_arch="sm_80"),
    ]

    assert lane_public_names(lanes) == {
        "gpu-o": "GPU-openmpi",
        "gpu-m": "GPU-mpich",
    }
