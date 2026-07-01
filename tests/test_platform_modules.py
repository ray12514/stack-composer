from __future__ import annotations

from stack_composer.render.platform_modules import platform_module_prereqs_for_lane


def test_returns_compiler_mpi_and_gpu_modules_for_cray_amd_lane() -> None:
    lane = {
        "name": "gcc-gpu",
        "compiler": "gcc",
        "mpi_provider": "cray-mpich",
        "mpi_source": "platform",
        "gpu_arch": "gfx90a",
    }
    profile = {
        "compiler_providers": [
            {"name": "gcc", "modules": ["PrgEnv-gnu", "gcc-native/13"]},
        ],
        "mpi_providers": [
            {"name": "cray-mpich", "flavors": {"gcc": {"modules": ["cray-mpich/8.1.29"]}}},
        ],
        "gpu_toolkit_modules": {"rocm": {"module": "rocm/6.0.0"}},
    }
    modules, issues = platform_module_prereqs_for_lane(lane, profile)
    assert issues == []
    assert modules == ["PrgEnv-gnu", "gcc-native/13", "cray-mpich/8.1.29", "rocm/6.0.0"]


def test_dedupes_modules_while_preserving_order() -> None:
    lane = {
        "name": "x",
        "compiler": "gcc",
        "mpi_provider": "cray-mpich",
        "mpi_source": "platform",
        "gpu_arch": None,
    }
    profile = {
        "compiler_providers": [{"name": "gcc", "modules": ["A", "B"]}],
        "mpi_providers": [{"name": "cray-mpich", "flavors": {"gcc": {"modules": ["B", "C"]}}}],
    }
    modules, issues = platform_module_prereqs_for_lane(lane, profile)
    assert issues == []
    assert modules == ["A", "B", "C"]


def test_empty_modules_lists_are_not_errors() -> None:
    lane = {"name": "site", "compiler": "aocc", "mpi_provider": "openmpi", "gpu_arch": None}
    profile = {
        "compiler_providers": [{"name": "aocc", "modules": []}],
        "mpi_providers": [{"name": "openmpi", "modules": []}],
    }
    modules, issues = platform_module_prereqs_for_lane(lane, profile)
    assert issues == []
    assert modules == []


def test_version_pinned_lane_gets_its_own_versions_modules() -> None:
    # Two same-name platform MPIs: the lane's pinned version selects which
    # entry's modules are prerequisites, not profile order.
    lane = {
        "name": "aocc-mpi",
        "compiler": "aocc",
        "mpi_provider": "openmpi",
        "mpi_source": "platform",
        "mpi_version": "5.0.3",
        "gpu_arch": None,
    }
    profile = {
        "compiler_providers": [{"name": "aocc", "modules": ["aocc/4.2.0"]}],
        "mpi_providers": [
            {"name": "openmpi", "version": "4.1.6", "modules": ["openmpi/4.1.6"]},
            {"name": "openmpi", "version": "5.0.3", "modules": ["openmpi/5.0.3"]},
        ],
    }
    modules, issues = platform_module_prereqs_for_lane(lane, profile)
    assert issues == []
    assert modules == ["aocc/4.2.0", "openmpi/5.0.3"]


def test_missing_cray_mpich_flavor_names_incompatible_compiler() -> None:
    lane = {
        "name": "rocmcc-mpi",
        "compiler": "rocmcc",
        "mpi_provider": "cray-mpich",
        "mpi_source": "platform",
        "gpu_arch": None,
    }
    profile = {
        "compiler_providers": [{"name": "rocmcc", "modules": ["PrgEnv-amd"]}],
        "mpi_providers": [
            {"name": "cray-mpich", "flavors": {"gcc": {"modules": ["cray-mpich/8.1.29"]}}}
        ],
    }
    modules, issues = platform_module_prereqs_for_lane(lane, profile)
    assert modules == ["PrgEnv-amd"]
    assert len(issues) == 1
    assert issues[0].code == "platform-mpi-compiler-incompatible"
    assert "platform MPI 'cray-mpich'" in issues[0].message
    assert "compiler 'rocmcc'" in issues[0].message


def test_unknown_compiler_raises_unresolved() -> None:
    lane = {"name": "ghost", "compiler": "ghost", "mpi_provider": None, "gpu_arch": None}
    profile = {"compiler_providers": [{"name": "gcc", "modules": ["gcc/12"]}]}
    modules, issues = platform_module_prereqs_for_lane(lane, profile)
    assert modules == []
    assert any(
        i.code == "unresolved-platform-module" and "'ghost'" in i.message for i in issues
    )


def test_amd_lane_without_rocm_toolkit_raises_unresolved() -> None:
    lane = {"name": "gpu", "compiler": "gcc", "mpi_provider": None, "gpu_arch": "gfx942"}
    profile = {
        "compiler_providers": [{"name": "gcc", "modules": []}],
        "gpu_toolkit_modules": {},
    }
    _, issues = platform_module_prereqs_for_lane(lane, profile)
    assert any(
        i.code == "unresolved-platform-module" and "rocm toolkit" in i.message for i in issues
    )


def test_nvidia_lane_uses_cuda_toolkit_for_nvhpc_compiler() -> None:
    lane = {"name": "nv", "compiler": "nvhpc", "mpi_provider": None, "gpu_arch": "sm_80"}
    profile = {
        "compiler_providers": [{"name": "nvhpc", "modules": ["PrgEnv-nvidia", "nvidia/25.3"]}],
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
        "compiler_providers": [{"name": "gcc", "modules": []}],
        "gpu_toolkit_modules": {"cudatoolkit": {"module": "cuda/12.4"}},
    }
    modules, issues = platform_module_prereqs_for_lane(lane, profile)
    assert issues == []
    assert modules == ["cuda/12.4"]
