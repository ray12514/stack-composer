from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

from stack_composer.model.profile import load_profile
from stack_composer.model.stack import load_defaults, load_stack, merge_defaults
from stack_composer.render.engine import render_workspace
from stack_composer.render.plan import plan_lanes
from stack_composer.render.release import ReleaseVars, SourceRepo
from stack_composer.render.scopes import required_scopes, scopes_for_lane
from stack_composer.yaml_io import load_yaml, write_yaml
from tests.conftest import fixture_path


def test_scope_selection_is_lane_specific_for_cray_gpu_and_core() -> None:
    profile, stack = fixture_context("example-cray")
    lanes, _skipped, _narrowing, issues = plan_lanes(profile, stack)
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
    profile, stack = fixture_context("example-linux")
    lanes, _skipped, _narrowing, issues = plan_lanes(profile, stack)
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


def test_vendor_scope_is_automatic_from_profile() -> None:
    profile, stack = fixture_context("example-cray")
    lanes, _skipped, _narrowing, issues = plan_lanes(profile, stack)
    assert issues == []

    core_lane = lane_by_name(lanes, "gcc-core")
    assert core_lane["vendor_scope"] == "vendor/cray"
    assert scopes_for_lane(core_lane, stack, profile) == [
        "../../../configs/common",
        "../../../configs/os/rhel8",
        "../../../configs/target/x86_64_v3",
        "../../../configs/vendor/cray",
    ]


def test_vendor_scope_is_per_compiler_provider_family() -> None:
    profile, stack = fixture_context("example-cray")
    profile["compiler_providers"].append(
        {
            "name": "aocc",
            "version": "4.2.0",
            "prefix": "/opt/site/aocc/4.2.0",
            "provider_family": "site",
            "languages": ["c", "c++", "fortran"],
            "modules": ["aocc/4.2.0"],
        }
    )
    stack["builds"] = [{"name": "core", "kind": "cpu", "specs": ["zlib"], "compilers": "all"}]
    stack["per_system"] = {}

    lanes, _skipped, _narrowing, issues = plan_lanes(profile, stack)

    assert issues == []
    assert lane_by_name(lanes, "cce-core")["vendor_scope"] == "vendor/cray"
    assert lane_by_name(lanes, "aocc-core")["vendor_scope"] == "vendor/linux"


def test_rendered_compiler_scopes_filter_and_group_duplicate_provider_names(
    tmp_path: Path,
) -> None:
    profile, _stack = fixture_context("example-cray")
    profile = deepcopy(profile)
    profile["compiler_providers"].append(
        {
            "name": "aocc",
            "version": "4.2.0",
            "prefix": "/opt/site/aocc/4.2.0",
            "provider_family": "site",
            "languages": ["c", "c++", "fortran"],
            "modules": ["aocc/4.2.0"],
        }
    )
    profile["compiler_providers"].extend(
        [
            {
                "name": "aocc",
                "version": "5.1.0",
                "prefix": "/opt/platform/aocc/5.1.0",
                "provider_family": "platform",
                "platform_family": "cray-pe",
                "languages": ["c", "c++", "fortran"],
                "modules": ["PrgEnv-aocc", "aocc/5.1.0"],
            },
            {
                "name": "aocc",
                "version": "5.2.0",
                "prefix": "/opt/platform/aocc/5.2.0",
                "provider_family": "platform",
                "platform_family": "cray-pe",
                "languages": ["c", "c++", "fortran"],
                "modules": ["PrgEnv-aocc", "aocc/5.2.0"],
            },
        ]
    )
    stack = load_yaml(fixture_path("stacks", "science-stack", "stack.yaml"))
    stack["builds"] = [{"name": "core", "kind": "cpu", "specs": ["zlib"], "compilers": "all"}]
    stack["per_system"] = {}

    workspace = render_profile_with_stack(
        tmp_path / "out",
        profile_path=write_profile(tmp_path / "profile", profile),
        stack_path=write_stack(tmp_path / "stack", stack),
    )

    cray_text = (workspace / "configs" / "vendor" / "cray" / "packages.yaml").read_text(
        encoding="utf-8"
    )
    assert cray_text.count("\n  aocc:") == 1
    cray = load_yaml(workspace / "configs" / "vendor" / "cray" / "packages.yaml")
    assert [external["prefix"] for external in cray["packages"]["aocc"]["externals"]] == [
        "/opt/platform/aocc/5.1.0",
        "/opt/platform/aocc/5.2.0",
    ]

    linux = load_yaml(workspace / "configs" / "vendor" / "linux" / "packages.yaml")
    assert [external["prefix"] for external in linux["packages"]["aocc"]["externals"]] == [
        "/opt/site/aocc/4.2.0"
    ]


def test_invalid_compiler_provider_version_is_not_rendered_or_selected(
    tmp_path: Path,
) -> None:
    profile, _stack = fixture_context("example-cray")
    profile = deepcopy(profile)
    profile["compiler_providers"].insert(
        0,
        {
            "name": "clang",
            "version": "clang/v2512-",
            "prefix": "/p/app/openfoam/aocc-compiler-4.1.0",
            "provider_family": "platform",
            "platform_family": "cray-pe",
            "languages": ["c", "c++"],
            "modules": ["openfoam/Clang/v2512-"],
        },
    )
    stack = load_yaml(fixture_path("stacks", "science-stack", "stack.yaml"))
    stack["builds"] = [{"name": "core", "kind": "cpu", "specs": ["zlib"], "compilers": "all"}]
    stack["per_system"] = {}

    lanes, _skipped, _narrowing, issues = plan_lanes(profile, stack)
    assert issues == []
    assert "clang" not in {lane["compiler"] for lane in lanes}

    workspace = render_profile_with_stack(
        tmp_path / "out",
        profile_path=write_profile(tmp_path / "profile", profile),
        stack_path=write_stack(tmp_path / "stack", stack),
    )
    cray_text = (workspace / "configs" / "vendor" / "cray" / "packages.yaml").read_text(
        encoding="utf-8"
    )
    assert "clang@clang/v2512-" not in cray_text
    assert "openfoam/Clang/v2512-" not in cray_text


def test_mpi_auto_uses_profile_order_without_cray_special_case() -> None:
    profile, stack = fixture_context("example-cray")
    profile["mpi_providers"].insert(
        0,
        {
            "name": "openmpi",
            "version": "5.0.6",
            "provider_family": "site",
            "compatibility": {"compilers": ["gcc"]},
            "prefix": "/opt/site/openmpi/5.0.6-gcc",
            "modules": ["openmpi/5.0.6"],
        },
    )
    stack["builds"] = [{"name": "mpi", "kind": "mpi", "specs": ["hdf5+mpi"]}]

    lanes, _skipped, _narrowing, issues = plan_lanes(profile, stack)

    assert issues == []
    assert {lane["mpi_provider"] for lane in lanes} == {"openmpi"}
    assert {lane["mpi_source"] for lane in lanes} == {"platform"}


def test_invalid_mpi_provider_is_not_selected_or_rendered(tmp_path: Path) -> None:
    profile, stack = fixture_context("example-linux")
    profile = deepcopy(profile)
    raw_stack = load_yaml(fixture_path("stacks", "science-stack", "stack.yaml"))
    profile["mpi_providers"].insert(
        0,
        {
            "name": "openmpi",
            "version": "module/openmpi4",
            "provider_family": "site",
            "compatibility": {"compilers": ["aocc"]},
            "prefix": "/opt/site/openmpi/bad",
            "modules": ["openmpi/module/openmpi4"],
        },
    )
    stack["builds"] = [{"name": "mpi", "kind": "mpi", "specs": ["hdf5+mpi"]}]
    raw_stack["builds"] = stack["builds"]

    lanes, _skipped, _narrowing, issues = plan_lanes(profile, stack)
    assert issues == []
    assert {lane["mpi_provider"] for lane in lanes} == {"openmpi"}

    workspace = render_profile_with_stack(
        tmp_path / "out",
        profile_path=write_profile(tmp_path / "profile", profile),
        stack_path=write_stack(tmp_path / "stack", raw_stack),
    )
    openmpi_text = (workspace / "configs" / "mpi" / "openmpi" / "packages.yaml").read_text(
        encoding="utf-8"
    )
    assert "openmpi@module/openmpi4" not in openmpi_text
    assert "openmpi@4.1.6" in openmpi_text


def test_mpi_auto_honors_explicit_platform_provider() -> None:
    profile, stack = fixture_context("example-cray")
    profile["mpi_providers"].insert(
        0,
        {
            "name": "openmpi",
            "version": "5.0.6",
            "provider_family": "site",
            "compatibility": {"compilers": ["gcc"]},
            "prefix": "/opt/site/openmpi/5.0.6-gcc",
            "modules": ["openmpi/5.0.6"],
        },
    )
    stack["builds"] = [
        {
            "name": "mpi",
            "kind": "mpi",
            "specs": ["hdf5+mpi"],
            "mpi": {"provider": "cray-mpich", "source": "auto"},
        }
    ]

    lanes, _skipped, _narrowing, issues = plan_lanes(profile, stack)

    assert issues == []
    assert {lane["mpi_provider"] for lane in lanes} == {"cray-mpich"}
    assert {lane["mpi_source"] for lane in lanes} == {"platform"}
    assert "mpi/cray-mpich" in required_scopes(profile, lanes)
    assert "mpi/openmpi" not in required_scopes(profile, lanes)


def test_invalid_single_prefix_mpi_compiler_is_not_rendered(tmp_path: Path) -> None:
    profile, stack = fixture_context("example-linux")
    profile = deepcopy(profile)
    raw_stack = load_yaml(fixture_path("stacks", "science-stack", "stack.yaml"))
    profile["mpi_providers"].insert(
        0,
        {
            "name": "openmpi",
            "version": "5.0.6",
            "provider_family": "site",
            "compatibility": {"compilers": ["clang"]},
            "compiler": "clang/v2512-",
            "prefix": "/opt/openfoam/openmpi/5.0.6",
            "modules": ["openfoam/openmpi/5.0.6"],
        },
    )
    stack["builds"] = [{"name": "mpi", "kind": "mpi", "specs": ["hdf5+mpi"]}]
    raw_stack["builds"] = stack["builds"]

    lanes, _skipped, _narrowing, issues = plan_lanes(profile, stack)
    assert issues == []
    assert {lane["mpi_provider"] for lane in lanes} == {"openmpi"}

    workspace = render_profile_with_stack(
        tmp_path / "out",
        profile_path=write_profile(tmp_path / "profile", profile),
        stack_path=write_stack(tmp_path / "stack", raw_stack),
    )
    openmpi_text = (workspace / "configs" / "mpi" / "openmpi" / "packages.yaml").read_text(
        encoding="utf-8"
    )
    assert "%clang/v2512-" not in openmpi_text
    assert "openmpi@4.1.6" in openmpi_text


def test_gpu_toolkit_scope_selection_is_independent_of_host_compiler() -> None:
    profile, stack = fixture_context("example-cray")
    lane = {
        "target": "zen3",
        "vendor_scope": "vendor/cray",
        "mpi_provider": "cray-mpich",
        "mpi_source": "platform",
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

    common = load_yaml(workspace / "configs" / "common" / "packages.yaml")
    assert common["packages"]["openssl"]["buildable"] is False
    assert common["packages"]["openssl"]["externals"][0] == {
        "spec": "openssl@3.0.7 +shared",
        "prefix": "/usr",
        "modules": [],
    }
    assert common["packages"]["curl"]["externals"][0] == {
        "spec": "curl@7.76.1",
        "prefix": "/usr",
        "modules": [],
    }
    assert common["packages"]["libfabric"]["externals"][0] == {
        "spec": "libfabric@1.20",
        "prefix": "/opt/cray/libfabric/1.20",
        "modules": [],
    }
    assert common["packages"]["ucx"]["externals"][0] == {
        "spec": "ucx@1.15",
        "prefix": "/usr",
        "modules": [],
    }

    platform_scope = load_yaml(workspace / "configs" / "vendor" / "cray" / "packages.yaml")
    assert platform_scope["packages"]["gcc"]["buildable"] is False
    assert platform_scope["packages"]["gcc"]["externals"][0]["prefix"] == (
        "/opt/cray/pe/gcc-native/13"
    )
    assert platform_scope["packages"]["gcc"]["externals"][0]["modules"] == [
        "PrgEnv-gnu",
        "gcc-native/13",
    ]
    assert platform_scope["packages"]["cce"]["externals"][0]["extra_attributes"][
        "compilers"
    ] == {
        "c": "/opt/cray/pe/cce/17.0.1/bin/craycc",
        "cxx": "/opt/cray/pe/cce/17.0.1/bin/craycxx",
        "fortran": "/opt/cray/pe/cce/17.0.1/bin/crayftn",
    }
    assert platform_scope["packages"]["rocmcc"]["buildable"] is False

    cray_mpich = load_yaml(workspace / "configs" / "mpi" / "cray-mpich" / "packages.yaml")
    assert cray_mpich["packages"]["mpi"] == {
        "buildable": False,
        "require": ["cray-mpich"],
    }
    assert cray_mpich["packages"]["cray-mpich"]["variants"] == "+wrappers"
    mpich_specs = [entry["spec"] for entry in cray_mpich["packages"]["cray-mpich"]["externals"]]
    assert "cray-mpich@8.1.29 %gcc" in mpich_specs
    assert "cray-mpich@8.1.29 %cce" in mpich_specs

    cray_mpich_toolchains = load_yaml(
        workspace / "configs" / "mpi" / "cray-mpich" / "toolchains.yaml"
    )
    assert cray_mpich_toolchains["toolchains"]["gcc_craympich"] == [
        {"spec": "%c=gcc@13.3.0", "when": "%c"},
        {"spec": "%cxx=gcc@13.3.0", "when": "%cxx"},
        {"spec": "%fortran=gcc@13.3.0", "when": "%fortran"},
        {"spec": "%mpi=cray-mpich@8.1.29", "when": "%mpi"},
    ]

    gpu_env = load_yaml(workspace / "environments" / "gcc" / "gpu-craympich-gfx90a" / "spack.yaml")
    assert "packages" not in gpu_env["spack"]
    assert gpu_env["spack"]["specs"]
    assert all(spec.endswith(" %gcc_craympich") for spec in gpu_env["spack"]["specs"])
    assert "kokkos+rocm amdgpu_target=gfx90a %gcc_craympich" in gpu_env["spack"]["specs"]

    rocm = load_yaml(workspace / "configs" / "gpu" / "amd-rocm" / "packages.yaml")
    assert rocm["packages"]["hip"]["buildable"] is False
    assert rocm["packages"]["hip"]["externals"][0] == {
        "spec": "hip@6.0.0",
        "prefix": "/opt/rocm-6.0.0/hip",
        "modules": ["rocm/6.0.0"],
    }


def test_invalid_gpu_toolkit_component_is_not_rendered(tmp_path: Path) -> None:
    profile, _stack = fixture_context("example-cray")
    profile = deepcopy(profile)
    profile["gpu_toolkit_modules"]["rocm"]["spack_components"].insert(
        0,
        {
            "package": "roc/solver",
            "prefix": "/opt/rocm-6.0.0/rocsolver",
        },
    )

    workspace = render_profile(tmp_path / "out", write_profile(tmp_path / "profile", profile))
    rocm_text = (workspace / "configs" / "gpu" / "amd-rocm" / "packages.yaml").read_text(
        encoding="utf-8"
    )
    assert "roc/solver" not in rocm_text
    assert "hip@6.0.0" in rocm_text


def test_rendered_common_scope_uses_arbitrary_system_external_policy(tmp_path: Path) -> None:
    profile, _stack = fixture_context("example-cray")
    profile = deepcopy(profile)
    profile["system_externals"].append(
        {
            "name": "cray-libsci",
            "version": "24.03.0",
            "prefix": "/opt/cray/pe/libsci/24.03.0",
            "provider_family": "platform",
            "modules": ["cray-libsci/24.03.0"],
            "detection": {"confidence": "probed", "source": "discovery policy"},
        }
    )
    workspace = render_profile(tmp_path / "out", write_profile(tmp_path, profile))

    common = load_yaml(workspace / "configs" / "common" / "packages.yaml")
    assert common["packages"]["cray-libsci"] == {
        "buildable": False,
        "externals": [
            {
                "spec": "cray-libsci@24.03.0",
                "prefix": "/opt/cray/pe/libsci/24.03.0",
                "modules": ["cray-libsci/24.03.0"],
            }
        ],
    }


def test_invalid_system_external_is_not_rendered(tmp_path: Path) -> None:
    profile, _stack = fixture_context("example-cray")
    profile = deepcopy(profile)
    profile["system_externals"].append(
        {
            "name": "bad/pkg",
            "version": "1.0",
            "prefix": "/opt/site/bad/pkg",
            "provider_family": "site",
            "detection": {"confidence": "probed", "source": "test"},
        }
    )
    stack = load_yaml(fixture_path("stacks", "science-stack", "stack.yaml"))
    stack["externals"] = {
        "compilers": "prefer_platform",
        "mpi": "prefer_platform",
        "openssl": "system",
        "curl": "system",
        "fabric_userspace": "prefer_platform",
        "bad/pkg": "system",
    }
    workspace = render_profile_with_stack(
        tmp_path / "out",
        profile_path=write_profile(tmp_path / "profile", profile),
        stack_path=write_stack(tmp_path / "stack", stack),
    )

    common_text = (workspace / "configs" / "common" / "packages.yaml").read_text(
        encoding="utf-8"
    )
    assert "bad/pkg" not in common_text
    assert "openssl@3.0.7" in common_text


def test_common_scope_prefers_platform_fabric_userspace_duplicates(tmp_path: Path) -> None:
    profile, _stack = fixture_context("example-cray")
    profile = deepcopy(profile)
    profile["fabric"]["userspace"].insert(
        0,
        {
            "name": "libfabric",
            "version": "1.22.0",
            "prefix": "/p/app/unsupported/libfabric/1.22.0",
        },
    )
    workspace = render_profile(tmp_path / "out", write_profile(tmp_path, profile))

    common_text = (workspace / "configs" / "common" / "packages.yaml").read_text(
        encoding="utf-8"
    )
    assert common_text.count("\n  libfabric:") == 1
    common = load_yaml(workspace / "configs" / "common" / "packages.yaml")
    assert common["packages"]["libfabric"]["externals"] == [
        {
            "spec": "libfabric@1.20",
            "prefix": "/opt/cray/libfabric/1.20",
            "modules": [],
        }
    ]


def test_common_scope_mixed_fabric_userspace_keeps_duplicates_under_one_key(
    tmp_path: Path,
) -> None:
    profile, _stack = fixture_context("example-cray")
    profile = deepcopy(profile)
    profile["fabric"]["userspace"].insert(
        0,
        {
            "name": "libfabric",
            "version": "1.22.0",
            "prefix": "/p/app/unsupported/libfabric/1.22.0",
        },
    )
    stack = load_yaml(fixture_path("stacks", "science-stack", "stack.yaml"))
    stack["externals"] = {
        "compilers": "prefer_platform",
        "mpi": "prefer_platform",
        "openssl": "system",
        "curl": "system",
        "fabric_userspace": "mixed",
    }

    workspace = render_profile_with_stack(
        tmp_path / "out",
        profile_path=write_profile(tmp_path / "profile", profile),
        stack_path=write_stack(tmp_path / "stack", stack),
    )

    common_text = (workspace / "configs" / "common" / "packages.yaml").read_text(
        encoding="utf-8"
    )
    assert common_text.count("\n  libfabric:") == 1
    common = load_yaml(workspace / "configs" / "common" / "packages.yaml")
    assert [external["prefix"] for external in common["packages"]["libfabric"]["externals"]] == [
        "/opt/cray/libfabric/1.20",
        "/p/app/unsupported/libfabric/1.22.0",
    ]


def test_stack_built_system_external_policy_does_not_render_external(tmp_path: Path) -> None:
    profile, _stack = fixture_context("example-cray")
    profile = deepcopy(profile)
    profile["system_externals"].append(
        {
            "name": "cray-libsci",
            "version": "24.03.0",
            "prefix": "/opt/cray/pe/libsci/24.03.0",
            "provider_family": "platform",
        }
    )
    stack = load_yaml(fixture_path("stacks", "science-stack", "stack.yaml"))
    stack["externals"] = {
        "compilers": "prefer_platform",
        "mpi": "prefer_platform",
        "openssl": "system",
        "curl": "system",
        "cray-libsci": "stack_built",
    }
    workspace = render_profile_with_stack(
        tmp_path / "out",
        profile_path=write_profile(tmp_path / "profile", profile),
        stack_path=write_stack(tmp_path / "stack", stack),
    )

    common = load_yaml(workspace / "configs" / "common" / "packages.yaml")
    assert "cray-libsci" not in common["packages"]

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
    profile, _stack = fixture_context("example-linux")
    profile["mpi_providers"].append(
        {
            "name": "openmpi",
            "version": "4.1.7",
            "provider_family": "site",
            "prefix": "/opt/site/openmpi/4.1.7",
            "modules": ["openmpi/4.1.7"],
        }
    )
    # Two openmpi versions on one system: the stack must pin one per build
    # (unpinned ambiguity is a hard render error, covered elsewhere). Both
    # externals still render — they are system facts; the pin picks the lane's.
    raw_stack = load_yaml(fixture_path("stacks", "science-stack", "stack.yaml"))
    for build in raw_stack["builds"]:
        if build["kind"] in ("mpi", "gpu"):
            build["mpi"] = {"provider": "openmpi", "source": "platform", "version": "4.1.6"}
    workspace = render_profile_with_stack(
        tmp_path / "out",
        profile_path=write_profile(tmp_path / "profile", profile),
        stack_path=write_stack(tmp_path / "stack", raw_stack),
    )

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
        },
        {
            "spec": "openmpi@4.1.7",
            "prefix": "/opt/site/openmpi/4.1.7",
            "modules": ["openmpi/4.1.7"],
        },
    ]

    mpi_env = (workspace / "environments" / "aocc" / "mpi-openmpi" / "spack.yaml").read_text(
        encoding="utf-8"
    )
    assert "../../../configs/vendor/linux" in mpi_env
    assert "../../../configs/mpi/openmpi" in mpi_env
    assert "../../../configs/vendor/cray" not in mpi_env
    assert "../../../configs/gpu/" not in mpi_env


def test_rendered_cray_nvidia_workspace_uses_current_cpe_names(tmp_path: Path) -> None:
    profile, _stack = fixture_context("example-cray")
    profile = cray_nvidia_profile(profile)
    profile_path = write_profile(tmp_path / "profile", profile)

    workspace = render_profile(tmp_path / "out", profile_path)

    platform_scope = load_yaml(workspace / "configs" / "vendor" / "cray" / "packages.yaml")
    assert platform_scope["packages"]["nvhpc"]["externals"][0]["modules"] == [
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
    platform_scope_text = (
        workspace / "configs" / "vendor" / "cray" / "packages.yaml"
    ).read_text(encoding="utf-8")
    assert "PrgEnv-nvhpc" not in platform_scope_text


def test_rendered_generic_linux_gpu_workspace_uses_gpu_scopes_without_cray(
    tmp_path: Path,
) -> None:
    profile, _stack = fixture_context("example-linux")
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


def render_build_sourced_openmpi(tmp_path: Path) -> Path:
    """Render a lane that builds OpenMPI from source on a system without one."""
    profile, _stack = fixture_context("example-linux")
    profile = deepcopy(profile)
    profile["mpi_providers"] = []
    stack = {
        "schema_version": 1,
        "name": "build-mpi",
        "profile_contract": {"schema_version": 1},
        "templates": {"set": "v6"},
        "builds": [
            {
                "name": "mpi",
                "kind": "mpi",
                "compilers": ["gcc"],
                "mpi": {"provider": "openmpi", "source": "build"},
                "specs": ["osu-micro-benchmarks"],
            }
        ],
    }
    return render_profile_with_stack(
        tmp_path / "out",
        profile_path=write_profile(tmp_path / "profile", profile),
        stack_path=write_stack(tmp_path / "stack", stack),
    )


def test_build_sourced_mpi_lane_gets_a_defined_toolchain(tmp_path: Path) -> None:
    workspace = render_build_sourced_openmpi(tmp_path)

    env = load_yaml(workspace / "environments" / "gcc" / "mpi-openmpi" / "spack.yaml")
    assert env["spack"]["specs"] == ["osu-micro-benchmarks %gcc_openmpi"]
    assert "../../../configs/mpi/openmpi" in env["spack"]["include"]

    toolchains = load_yaml(workspace / "configs" / "mpi" / "openmpi" / "toolchains.yaml")
    assert toolchains["toolchains"]["gcc_openmpi"] == [
        {"spec": "%c=gcc@11.4.0", "when": "%c"},
        {"spec": "%cxx=gcc@11.4.0", "when": "%cxx"},
        {"spec": "%fortran=gcc@11.4.0", "when": "%fortran"},
        {"spec": "%mpi=openmpi", "when": "%mpi"},
    ]


def ambiguous_openmpi_profile() -> dict[str, Any]:
    """example-linux plus a second openmpi version: same provider name twice."""
    profile, _stack = fixture_context("example-linux")
    profile = deepcopy(profile)
    profile["mpi_providers"].append(
        {
            "name": "openmpi",
            "version": "5.0.3",
            "provider_family": "site",
            "prefix": "/opt/site/openmpi/5.0.3-aocc-4.2.0",
            "compiler": "aocc@4.2.0",
        }
    )
    return profile


def test_ambiguous_platform_mpi_without_version_is_a_hard_error() -> None:
    profile = ambiguous_openmpi_profile()
    _, stack = fixture_context("example-linux")
    stack["builds"] = [{"name": "mpi", "kind": "mpi", "specs": ["hdf5+mpi"]}]

    lanes, _skipped, _narrowing, issues = plan_lanes(profile, stack)

    # Ambiguity is an authoring defect in profile+stack input, not a missing
    # capability: it hard-errors even though the build is not marked required,
    # instead of silently picking one version or silently skipping the build.
    ambiguous = [issue for issue in issues if issue.code == "mpi_ambiguous"]
    assert len(ambiguous) == 1
    assert ambiguous[0].severity == "error"
    assert "4.1.6" in ambiguous[0].message and "5.0.3" in ambiguous[0].message
    assert not any(lane["kind"] == "mpi" for lane in lanes)


def test_mpi_version_pin_disambiguates_and_versions_toolchain_names(tmp_path: Path) -> None:
    profile = ambiguous_openmpi_profile()
    stack = {
        "schema_version": 1,
        "name": "pinned-mpi",
        "profile_contract": {"schema_version": 1},
        "templates": {"set": "v6"},
        "builds": [
            {
                "name": "mpi",
                "kind": "mpi",
                "compilers": ["aocc"],
                "mpi": {"provider": "openmpi", "source": "platform", "version": "5.0.3"},
                "specs": ["hdf5+mpi"],
            }
        ],
    }

    workspace = render_profile_with_stack(
        tmp_path / "out",
        profile_path=write_profile(tmp_path / "profile", profile),
        stack_path=write_stack(tmp_path / "stack", stack),
    )

    env = load_yaml(workspace / "environments" / "aocc" / "mpi-openmpi" / "spack.yaml")
    assert env["spack"]["specs"] == ["hdf5+mpi %aocc_openmpi_5.0.3"]

    # Both pairings render as a catalog, each under a version-qualified name;
    # the bare (collision-prone) name must not appear as a key.
    toolchains = load_yaml(workspace / "configs" / "mpi" / "openmpi" / "toolchains.yaml")
    assert set(toolchains["toolchains"]) == {"aocc_openmpi_4.1.6", "aocc_openmpi_5.0.3"}
    assert {"spec": "%mpi=openmpi@5.0.3", "when": "%mpi"} in toolchains["toolchains"][
        "aocc_openmpi_5.0.3"
    ]
    assert {"spec": "%mpi=openmpi@4.1.6", "when": "%mpi"} in toolchains["toolchains"][
        "aocc_openmpi_4.1.6"
    ]


def test_single_version_provider_keeps_unversioned_toolchain_name() -> None:
    # Regression guard: adding a second version of one provider must not
    # rename toolchains of a different, unambiguous provider elsewhere.
    profile, stack = fixture_context("example-linux")
    stack["builds"] = [
        {
            "name": "mpi",
            "kind": "mpi",
            "compilers": ["aocc"],
            "mpi": {"provider": "openmpi", "source": "platform"},
            "specs": ["hdf5+mpi"],
        }
    ]

    lanes, _skipped, _narrowing, issues = plan_lanes(profile, stack)

    assert issues == []
    lane = lane_by_name(lanes, "aocc-mpi-openmpi")
    assert lane["toolchain"] == "aocc_openmpi"
    assert lane["mpi_version"] == "4.1.6"


def test_platform_mpi_without_compiler_metadata_still_defines_lane_toolchain(
    tmp_path: Path,
) -> None:
    # An OS-packaged MPI may carry no compiler tag, flavors, or compatibility
    # list. The lane's decorated toolchain must still be defined in the scope.
    profile, _stack = fixture_context("example-linux")
    profile = deepcopy(profile)
    profile["mpi_providers"] = [
        {
            "name": "openmpi",
            "version": "4.1.7",
            "provider_family": "system",
            "prefix": "/usr",
        }
    ]
    stack = {
        "schema_version": 1,
        "name": "system-mpi",
        "profile_contract": {"schema_version": 1},
        "templates": {"set": "v6"},
        "builds": [
            {
                "name": "mpi",
                "kind": "mpi",
                "compilers": ["gcc"],
                "mpi": {"provider": "openmpi", "source": "platform"},
                "specs": ["hdf5+mpi"],
            }
        ],
    }

    workspace = render_profile_with_stack(
        tmp_path / "out",
        profile_path=write_profile(tmp_path / "profile", profile),
        stack_path=write_stack(tmp_path / "stack", stack),
    )

    env = load_yaml(workspace / "environments" / "gcc" / "mpi-openmpi" / "spack.yaml")
    assert env["spack"]["specs"] == ["hdf5+mpi %gcc_openmpi"]
    toolchains = load_yaml(workspace / "configs" / "mpi" / "openmpi" / "toolchains.yaml")
    assert toolchains["toolchains"]["gcc_openmpi"] == [
        {"spec": "%c=gcc@11.4.0", "when": "%c"},
        {"spec": "%cxx=gcc@11.4.0", "when": "%cxx"},
        {"spec": "%fortran=gcc@11.4.0", "when": "%fortran"},
        {"spec": "%mpi=openmpi@4.1.7", "when": "%mpi"},
    ]


def test_build_sourced_mpi_packages_yaml_is_buildable(tmp_path: Path) -> None:
    workspace = render_build_sourced_openmpi(tmp_path)

    packages = load_yaml(workspace / "configs" / "mpi" / "openmpi" / "packages.yaml")
    assert packages["packages"]["openmpi"] == {"buildable": True}
    assert packages["packages"]["mpi"] == {"require": ["openmpi"]}


def fixture_context(profile_name: str) -> tuple[dict[str, Any], dict[str, Any]]:
    profile, profile_issues = load_profile(fixture_path("profiles", profile_name, "profile.yaml"))
    assert profile_issues == []
    template_set = fixture_path("template-sets", "v6")
    defaults, default_issues = load_defaults(template_set / "defaults.yaml")
    assert default_issues == []
    raw_stack, stack_issues = load_stack(fixture_path("stacks", "science-stack", "stack.yaml"))
    assert stack_issues == []
    stack = merge_defaults(defaults, deepcopy(raw_stack))
    return profile, stack


def lane_by_name(lanes: list[dict[str, Any]], name: str) -> dict[str, Any]:
    return next(lane for lane in lanes if lane["name"] == name)


def render_fixture(output_root: Path, profile_name: str) -> Path:
    return render_profile(output_root, fixture_path("profiles", profile_name, "profile.yaml"))


def render_profile(output_root: Path, profile_path: Path) -> Path:
    return render_profile_with_stack(
        output_root,
        profile_path=profile_path,
        stack_path=fixture_path("stacks", "science-stack", "stack.yaml"),
    )


def render_profile_with_stack(output_root: Path, profile_path: Path, stack_path: Path) -> Path:
    deployment_path = output_root.parent / "deployment.yaml"
    profile = load_yaml(profile_path)
    write_test_deployment(deployment_path, profile["system"]["name"])
    return render_workspace(
        profile_path=profile_path,
        deployment_path=deployment_path,
        stack_path=stack_path,
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


def write_stack(directory: Path, stack: dict[str, Any]) -> Path:
    stack_path = directory / "stack.yaml"
    write_yaml(stack_path, stack)
    return stack_path


def write_test_deployment(path: Path, system: str) -> None:
    write_yaml(
        path,
        {
            "schema_version": 1,
            "system": system,
            "install_tree": {"root": "/shared/stack/spack/opt"},
            "build_stage": {"default": "/scratch/$user/spack-stage"},
            "caches": {
                "source": "/shared/stack/spack/source-cache",
                "misc": "/shared/stack/cache/misc",
            },
            "roots": {
                "views": "/shared/stack/views",
                "modules": "/shared/stack/modules",
            },
            "modules": {"publish_root": None},
            "buildcache": {
                "destinations": [
                    {"name": "payload", "url": "file:///shared/stack/buildcache/payload"}
                ]
            },
        },
    )


def cray_nvidia_profile(profile: dict[str, Any]) -> dict[str, Any]:
    profile = deepcopy(profile)
    profile["system"]["name"] = "example-cray-nvidia"
    profile["system"]["description"] = "Cray EX, NVIDIA A100"
    profile["compiler_providers"].append(
        {
            "name": "nvhpc",
            "version": "25.3",
            "prefix": "/opt/nvidia/hpc_sdk/Linux_x86_64/25.3/compilers",
            "provider_family": "platform",
            "platform_family": "cray-pe",
            "languages": ["c", "c++", "fortran"],
            "modules": ["PrgEnv-nvidia", "nvidia/25.3"],
        }
    )
    for mpi in profile["mpi_providers"]:
        if mpi["name"] == "cray-mpich":
            mpi["flavors"]["nvhpc"] = {
                "prefix": "/opt/cray/pe/mpich/8.1.29/ofi/nvidia/25.3",
                "modules": ["cray-mpich/8.1.29"],
            }
            mpi.setdefault("compatibility", {}).setdefault("compilers", []).append("nvhpc")
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
