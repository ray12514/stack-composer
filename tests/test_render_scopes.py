from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

from stack_composer.model.contract import load_contract
from stack_composer.model.profile import load_profile
from stack_composer.model.stack import load_stack, load_stack_defaults, merge_defaults
from stack_composer.render.engine import render_workspace
from stack_composer.render.plan import plan_lanes
from stack_composer.render.release import ReleaseVars, SourceRepo
from stack_composer.render.scopes import required_scopes, scopes_for_lane
from stack_composer.yaml_io import load_yaml, write_yaml
from tests.conftest import fixture_path


def test_scope_selection_is_lane_specific_for_cray_gpu_and_core() -> None:
    profile, stack, contract = fixture_context("example-cray")
    lanes, _skipped, _narrowing, issues = plan_lanes(profile, stack, contract)
    assert issues == []

    gpu_lane = lane_by_name(lanes, "gcc-gpu-craympich-gfx90a")
    assert scopes_for_lane(gpu_lane, stack, profile) == [
        "../../../configs/common",
        "../../../configs/os/rhel8",
        "../../../configs/target/zen3",
        "../../../configs/vendor/cray",
        "../../../configs/mpi/cray-mpich",
        "../../../configs/gpu/amd-rocm",
    ]

    core_lane = lane_by_name(lanes, "gcc-core")
    assert scopes_for_lane(core_lane, stack, profile) == [
        "../../../configs/common",
        "../../../configs/os/rhel8",
        "../../../configs/target/x86_64_v3",
        "../../../configs/vendor/cray",
    ]
    assert "gpu/amd-rocm" in required_scopes(profile, lanes)


def test_scope_selection_keeps_generic_linux_out_of_cray_scopes() -> None:
    profile, stack, contract = fixture_context("example-linux")
    lanes, _skipped, _narrowing, issues = plan_lanes(profile, stack, contract)
    assert issues == []

    mpi_lane = lane_by_name(lanes, "aocc-mpi-openmpi")
    assert scopes_for_lane(mpi_lane, stack, profile) == [
        "../../../configs/common",
        "../../../configs/os/rhel9",
        "../../../configs/target/zen3",
        "../../../configs/vendor/linux",
        "../../../configs/mpi/openmpi",
    ]
    scopes = required_scopes(profile, lanes)
    assert "vendor/linux" in scopes
    assert "mpi/openmpi" in scopes
    assert "vendor/cray" not in scopes
    assert not any(scope.startswith("gpu/") for scope in scopes)


def test_gpu_toolkit_scope_selection_is_independent_of_host_compiler() -> None:
    profile, stack, _contract = fixture_context("example-cray")
    lane = {
        "target": "zen3",
        "mpi_provider": "cray-mpich",
        "gpu_arch": "gfx90a",
    }

    for compiler in ("gcc", "cce", "aocc", "rocmcc", "nvhpc"):
        assert scopes_for_lane({**lane, "compiler": compiler}, stack, profile) == [
            "../../../configs/common",
            "../../../configs/os/rhel8",
            "../../../configs/target/zen3",
            "../../../configs/vendor/cray",
            "../../../configs/mpi/cray-mpich",
            "../../../configs/gpu/amd-rocm",
        ]

    nvidia_lane = {**lane, "compiler": "gcc", "gpu_arch": "sm_80"}
    assert scopes_for_lane(nvidia_lane, stack, profile)[-1] == "../../../configs/gpu/nvidia-cuda"


def test_rendered_cray_workspace_contains_external_scopes(tmp_path: Path) -> None:
    workspace = render_fixture(tmp_path / "out", "example-cray")

    vendor_cray = load_yaml(workspace / "configs" / "vendor" / "cray" / "packages.yaml")
    assert vendor_cray["packages"]["gcc"]["buildable"] is False
    assert vendor_cray["packages"]["gcc"]["externals"][0]["prefix"] == (
        "/opt/cray/pe/gcc-native/13"
    )
    assert vendor_cray["packages"]["gcc"]["externals"][0]["modules"] == [
        "PrgEnv-gnu",
        "gcc-native/13",
    ]
    assert vendor_cray["packages"]["cce"]["externals"][0]["extra_attributes"][
        "compilers"
    ] == {
        "c": "/opt/cray/pe/cce/17.0.1/bin/craycc",
        "cxx": "/opt/cray/pe/cce/17.0.1/bin/craycxx",
        "fortran": "/opt/cray/pe/cce/17.0.1/bin/crayftn",
    }
    assert vendor_cray["packages"]["rocmcc"]["buildable"] is False

    cray_mpich = load_yaml(workspace / "configs" / "mpi" / "cray-mpich" / "packages.yaml")
    assert cray_mpich["packages"]["mpi"] == {
        "buildable": False,
        "require": ["cray-mpich"],
    }
    assert cray_mpich["packages"]["cray-mpich"]["variants"] == "+wrappers"
    mpich_specs = [entry["spec"] for entry in cray_mpich["packages"]["cray-mpich"]["externals"]]
    assert "cray-mpich@8.1.29 %gcc" in mpich_specs
    assert "cray-mpich@8.1.29 %cce" in mpich_specs

    rocm = load_yaml(workspace / "configs" / "gpu" / "amd-rocm" / "packages.yaml")
    assert rocm["packages"]["hip"]["buildable"] is False
    assert rocm["packages"]["hip"]["externals"][0] == {
        "spec": "hip@6.0.0",
        "prefix": "/opt/rocm-6.0.0/hip",
        "modules": ["rocm/6.0.0"],
    }

    gpu_env = (
        workspace / "environments" / "gcc" / "gpu-craympich-gfx90a" / "spack.yaml"
    ).read_text(encoding="utf-8")
    assert "../../../configs/gpu/amd-rocm" in gpu_env
    assert "../../../configs/vendor/linux" not in gpu_env
    assert "kokkos+rocm amdgpu_target=gfx90a" in gpu_env
    assert "raja+rocm amdgpu_target=gfx90a" in gpu_env
    assert "amdgpu_target=gfx90a" in gpu_env
    assert "+gpu" not in gpu_env


def test_rendered_generic_linux_workspace_contains_site_mpi_without_cray(
    tmp_path: Path,
) -> None:
    workspace = render_fixture(tmp_path / "out", "example-linux")

    assert not (workspace / "configs" / "vendor" / "cray").exists()
    vendor_linux = load_yaml(workspace / "configs" / "vendor" / "linux" / "packages.yaml")
    assert vendor_linux["packages"]["aocc"]["externals"][0]["modules"] == ["aocc/4.2.0"]

    openmpi = load_yaml(workspace / "configs" / "mpi" / "openmpi" / "packages.yaml")
    assert openmpi["packages"]["openmpi"]["buildable"] is False
    assert openmpi["packages"]["openmpi"]["externals"] == [
        {
            "spec": "openmpi@4.1.6 %aocc@4.2.0",
            "prefix": "/opt/site/openmpi/4.1.6-aocc-4.2.0",
            "modules": [],
        }
    ]

    mpi_env = (workspace / "environments" / "aocc" / "mpi-openmpi" / "spack.yaml").read_text(
        encoding="utf-8"
    )
    assert "../../../configs/vendor/linux" in mpi_env
    assert "../../../configs/mpi/openmpi" in mpi_env
    assert "../../../configs/vendor/cray" not in mpi_env
    assert "../../../configs/gpu/" not in mpi_env


def test_rendered_cray_nvidia_workspace_uses_current_cpe_names(tmp_path: Path) -> None:
    profile, _stack, _contract = fixture_context("example-cray")
    profile = cray_nvidia_profile(profile)
    profile_path = write_profile(tmp_path / "profile", profile)

    workspace = render_profile(tmp_path / "out", profile_path)

    vendor_cray = load_yaml(workspace / "configs" / "vendor" / "cray" / "packages.yaml")
    assert vendor_cray["packages"]["nvhpc"]["externals"][0]["modules"] == [
        "PrgEnv-nvidia",
        "nvidia/25.3",
    ]

    cuda = load_yaml(workspace / "configs" / "gpu" / "nvidia-cuda" / "packages.yaml")
    assert cuda["packages"]["cuda"]["externals"][0] == {
        "spec": "cuda@12.4.1",
        "prefix": "/opt/nvidia/cuda/12.4.1",
        "modules": ["cuda/12.4.1"],
    }

    gpu_env = (
        workspace / "environments" / "gcc" / "gpu-craympich-sm_80" / "spack.yaml"
    ).read_text(encoding="utf-8")
    assert "../../../configs/gpu/nvidia-cuda" in gpu_env
    assert "kokkos+cuda cuda_arch=80" in gpu_env
    assert "raja+cuda cuda_arch=80" in gpu_env
    assert "cuda_arch=80" in gpu_env
    assert "amdgpu_target" not in gpu_env
    assert "+gpu" not in gpu_env
    assert "PrgEnv-nvhpc" not in gpu_env
    vendor_cray_text = (
        workspace / "configs" / "vendor" / "cray" / "packages.yaml"
    ).read_text(encoding="utf-8")
    assert "PrgEnv-nvhpc" not in vendor_cray_text


def test_rendered_generic_linux_gpu_workspace_uses_gpu_scopes_without_cray(
    tmp_path: Path,
) -> None:
    profile, _stack, _contract = fixture_context("example-linux")
    profile = generic_linux_gpu_profile(profile)
    profile_path = write_profile(tmp_path / "profile", profile)

    workspace = render_profile(tmp_path / "out", profile_path)

    assert not (workspace / "configs" / "vendor" / "cray").exists()
    assert (workspace / "configs" / "vendor" / "linux" / "packages.yaml").exists()
    assert (workspace / "configs" / "gpu" / "amd-rocm" / "packages.yaml").exists()
    assert (workspace / "configs" / "gpu" / "nvidia-cuda" / "packages.yaml").exists()

    amd_env = (
        workspace / "environments" / "gcc" / "gpu-openmpi-gfx90a" / "spack.yaml"
    ).read_text(encoding="utf-8")
    assert "../../../configs/vendor/linux" in amd_env
    assert "../../../configs/vendor/cray" not in amd_env
    assert "../../../configs/gpu/amd-rocm" in amd_env
    assert "kokkos+rocm amdgpu_target=gfx90a" in amd_env
    assert "amdgpu_target=gfx90a" in amd_env
    assert "+gpu" not in amd_env

    nvidia_env = (
        workspace / "environments" / "gcc" / "gpu-openmpi-sm_80" / "spack.yaml"
    ).read_text(encoding="utf-8")
    assert "../../../configs/vendor/linux" in nvidia_env
    assert "../../../configs/vendor/cray" not in nvidia_env
    assert "../../../configs/gpu/nvidia-cuda" in nvidia_env
    assert "kokkos+cuda cuda_arch=80" in nvidia_env
    assert "cuda_arch=80" in nvidia_env
    assert "+gpu" not in nvidia_env


def fixture_context(profile_name: str) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    profile, profile_issues = load_profile(fixture_path("profiles", profile_name, "profile.yaml"))
    assert profile_issues == []
    template_set = fixture_path("template-sets", "v6")
    defaults, default_issues = load_stack_defaults(template_set / "stack-defaults.yaml")
    assert default_issues == []
    contract, contract_issues = load_contract(template_set / "contract.yaml")
    assert contract_issues == []
    raw_stack, stack_issues = load_stack(fixture_path("stacks", "science-stack", "stack.yaml"))
    assert stack_issues == []
    stack = merge_defaults(defaults, deepcopy(raw_stack))
    return profile, stack, contract


def lane_by_name(lanes: list[dict[str, Any]], name: str) -> dict[str, Any]:
    return next(lane for lane in lanes if lane["name"] == name)


def render_fixture(output_root: Path, profile_name: str) -> Path:
    return render_profile(output_root, fixture_path("profiles", profile_name, "profile.yaml"))


def render_profile(output_root: Path, profile_path: Path) -> Path:
    return render_workspace(
        profile_path=profile_path,
        stack_path=fixture_path("stacks", "science-stack", "stack.yaml"),
        templates_root=fixture_path("template-sets"),
        release_vars=ReleaseVars(
            release_tag="2026.06",
            output_root=output_root.as_posix(),
            rendered_at="2026-06-19T00:00:00Z",
            source_repo=SourceRepo(
                url="git@example:stacks/science-stack",
                commit="0375b16fdeadbeef0123456789abcdef01234567",
                dirty=False,
            ),
        ),
        package_sets_dir=fixture_path("package-sets"),
        package_repos_dir=fixture_path("package-repos"),
    )


def write_profile(directory: Path, profile: dict[str, Any]) -> Path:
    profile_path = directory / "profile.yaml"
    write_yaml(profile_path, profile)
    return profile_path


def cray_nvidia_profile(profile: dict[str, Any]) -> dict[str, Any]:
    profile = deepcopy(profile)
    profile["system"]["name"] = "example-cray-nvidia"
    profile["system"]["description"] = "Cray EX, NVIDIA A100"
    profile["vendor_cray"]["nvhpc"] = {
        "version": "25.3",
        "prefix": "/opt/nvidia/hpc_sdk/Linux_x86_64/25.3/compilers",
        "modules": ["PrgEnv-nvidia", "nvidia/25.3"],
    }
    profile["vendor_cray"]["cray_mpich"]["flavors"]["nvhpc"] = {
        "prefix": "/opt/cray/pe/mpich/8.1.29/ofi/nvidia/25.3",
        "modules": ["cray-mpich/8.1.29"],
    }
    profile["gpu_toolkit_modules"] = {
        "cudatoolkit": {
            "version": "12.4.1",
            "module": "cuda/12.4.1",
            "prefix": "/opt/nvidia/cuda/12.4.1",
        }
    }
    profile["node_types"] = {
        "login": profile["node_types"]["login"],
        "cpu_compute": profile["node_types"]["cpu_compute"],
        "gpu_compute_a100": {
            "role": "runtime",
            "description": "GPU compute, NVIDIA A100 (sm_80), Zen3 host",
            "cpu": {"detected": "zen3", "preferred": "zen3"},
            "gpu": {
                "vendor": "nvidia",
                "driver_version": "550.54",
                "toolkit_ceiling": "12.4.1",
                "arch_target": "sm_80",
                "cuda_compat_available": True,
            },
            "build_stage": [
                {
                    "path": "/local_scratch/$user/spack-stage",
                    "visibility": "compute-only",
                    "writable": True,
                    "throughput_class": "fast",
                }
            ],
        },
    }
    return profile


def generic_linux_gpu_profile(profile: dict[str, Any]) -> dict[str, Any]:
    profile = deepcopy(profile)
    profile["system"]["name"] = "example-linux-gpu"
    profile["system"]["description"] = "Generic Linux HPC with AMD and NVIDIA GPUs"
    profile["gpu_toolkit_modules"] = {
        "rocm": {
            "version": "6.0.0",
            "module": "rocm/6.0.0",
            "prefix": "/opt/rocm-6.0.0",
            "spack_components": [
                {"package": "hip", "prefix": "/opt/rocm-6.0.0/hip"},
            ],
        },
        "cudatoolkit": {
            "version": "12.4.1",
            "module": "cuda/12.4.1",
            "prefix": "/opt/nvidia/cuda/12.4.1",
        },
    }
    profile["node_types"]["gpu_compute_mi250x"] = {
        "role": "runtime",
        "description": "GPU compute, MI250X (gfx90a), Zen3 host",
        "cpu": {"detected": "zen3", "preferred": "zen3"},
        "gpu": {
            "vendor": "amd",
            "driver_version": "6.0",
            "toolkit_ceiling": "6.0.0",
            "arch_target": "gfx90a",
        },
        "build_stage": [
            {
                "path": "/local_scratch/$user/spack-stage",
                "visibility": "compute-only",
                "writable": True,
                "throughput_class": "fast",
            }
        ],
    }
    profile["node_types"]["gpu_compute_a100"] = {
        "role": "runtime",
        "description": "GPU compute, NVIDIA A100 (sm_80), Zen3 host",
        "cpu": {"detected": "zen3", "preferred": "zen3"},
        "gpu": {
            "vendor": "nvidia",
            "driver_version": "550.54",
            "toolkit_ceiling": "12.4.1",
            "arch_target": "sm_80",
            "cuda_compat_available": True,
        },
        "build_stage": [
            {
                "path": "/local_scratch/$user/spack-stage",
                "visibility": "compute-only",
                "writable": True,
                "throughput_class": "fast",
            }
        ],
    }
    return profile
