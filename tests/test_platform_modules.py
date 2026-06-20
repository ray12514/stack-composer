from __future__ import annotations

from stack_composer.render.platform_modules import platform_module_prereqs_for_lane


def test_returns_compiler_mpi_and_gpu_modules_for_cray_amd_lane() -> None:
    lane = {
        "name": "gcc-gpu",
        "compiler": "gcc",
        "mpi_provider": "cray-mpich",
        "gpu_arch": "gfx90a",
    }
    profile = {
        "vendor_cray": {
            "gcc": {"modules": ["PrgEnv-gnu", "gcc-native/13"]},
            "cray_mpich": {
                "flavors": {"gcc": {"modules": ["cray-mpich/8.1.29"]}},
            },
        },
        "gpu_toolkit_modules": {"rocm": {"module": "rocm/6.0.0"}},
    }
    modules, issues = platform_module_prereqs_for_lane(lane, profile)
    assert issues == []
    assert modules == ["PrgEnv-gnu", "gcc-native/13", "cray-mpich/8.1.29", "rocm/6.0.0"]


def test_dedupes_modules_while_preserving_order() -> None:
    lane = {"name": "x", "compiler": "gcc", "mpi_provider": "cray-mpich", "gpu_arch": None}
    profile = {
        "vendor_cray": {
            "gcc": {"modules": ["A", "B"]},
            "cray_mpich": {"flavors": {"gcc": {"modules": ["B", "C"]}}},
        },
    }
    modules, issues = platform_module_prereqs_for_lane(lane, profile)
    assert issues == []
    assert modules == ["A", "B", "C"]


def test_empty_modules_lists_are_not_errors() -> None:
    lane = {"name": "site", "compiler": "aocc", "mpi_provider": "openmpi", "gpu_arch": None}
    profile = {
        "compilers_external": [{"name": "aocc", "modules": []}],
        "mpi": [{"name": "openmpi", "modules": []}],
    }
    modules, issues = platform_module_prereqs_for_lane(lane, profile)
    assert issues == []
    assert modules == []


def test_missing_cray_mpich_flavor_raises_unresolved() -> None:
    lane = {
        "name": "rocmcc-mpi",
        "compiler": "rocmcc",
        "mpi_provider": "cray-mpich",
        "gpu_arch": None,
    }
    profile = {
        "vendor_cray": {
            "rocmcc": {"modules": ["PrgEnv-amd"]},
            "cray_mpich": {"flavors": {"gcc": {"modules": ["cray-mpich/8.1.29"]}}},
        },
    }
    modules, issues = platform_module_prereqs_for_lane(lane, profile)
    assert modules == ["PrgEnv-amd"]
    assert len(issues) == 1
    assert issues[0].code == "unresolved-platform-module"
    assert "cray-mpich flavor for compiler 'rocmcc'" in issues[0].message


def test_unknown_compiler_raises_unresolved() -> None:
    lane = {"name": "ghost", "compiler": "ghost", "mpi_provider": None, "gpu_arch": None}
    profile = {"compilers_external": [{"name": "gcc", "modules": ["gcc/12"]}]}
    modules, issues = platform_module_prereqs_for_lane(lane, profile)
    assert modules == []
    assert any(
        i.code == "unresolved-platform-module" and "'ghost'" in i.message for i in issues
    )


def test_amd_lane_without_rocm_toolkit_raises_unresolved() -> None:
    lane = {"name": "gpu", "compiler": "gcc", "mpi_provider": None, "gpu_arch": "gfx942"}
    profile = {
        "compilers_external": [{"name": "gcc", "modules": []}],
        "gpu_toolkit_modules": {},
    }
    _, issues = platform_module_prereqs_for_lane(lane, profile)
    assert any(
        i.code == "unresolved-platform-module" and "rocm toolkit" in i.message for i in issues
    )


def test_nvidia_lane_uses_cuda_toolkit_for_nvhpc_compiler() -> None:
    lane = {"name": "nv", "compiler": "nvhpc", "mpi_provider": None, "gpu_arch": "sm_80"}
    profile = {
        "vendor_cray": {"nvhpc": {"modules": ["PrgEnv-nvidia", "nvidia/25.3"]}},
        "gpu_toolkit_modules": {
            "cudatoolkit": {"module": "cuda/12.4"},
            "nvhpc": {"module": "nvhpc/24.3"},
        },
    }
    modules, issues = platform_module_prereqs_for_lane(lane, profile)
    assert issues == []
    assert modules == ["PrgEnv-nvidia", "nvidia/25.3", "cuda/12.4"]


def test_nvidia_lane_picks_cuda_toolkit_for_non_nvhpc_compiler() -> None:
    lane = {"name": "gcc-gpu", "compiler": "gcc", "mpi_provider": None, "gpu_arch": "sm_90"}
    profile = {
        "compilers_external": [{"name": "gcc", "modules": []}],
        "gpu_toolkit_modules": {"cudatoolkit": {"module": "cuda/12.4"}},
    }
    modules, issues = platform_module_prereqs_for_lane(lane, profile)
    assert issues == []
    assert modules == ["cuda/12.4"]
