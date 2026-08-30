from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest
import yaml
from click.testing import CliRunner

from stack_composer.cli import cli
from stack_composer.errors import ValidationFailed
from stack_composer.render.release import ReleaseVars, SourceRepo
from stack_composer.render.static_catalog import render_static_catalog
from tests.conftest import fixture_path


def test_static_catalog_renders_cray_include_scopes(tmp_path: Path) -> None:
    workspace = render_static_catalog(
        profile_path=fixture_path("profiles", "example-cray", "profile.yaml"),
        templates_root=fixture_path("template-sets"),
        template_set_name="v6",
        release_vars=ReleaseVars(
            release_tag="alpha-001",
            output_root=str(tmp_path),
            rendered_at="2026-07-09T00:00:00Z",
            source_repo=SourceRepo("local-static-alpha", "abc123", False),
        ),
    )

    assert workspace == tmp_path / "example-cray" / "static" / "alpha-001"
    assert (workspace / "README.md").exists()
    assert (workspace / "manifest.yaml").exists()
    assert (workspace / "profile.yaml").read_bytes() == fixture_path(
        "profiles", "example-cray", "profile.yaml"
    ).read_bytes()
    assert (workspace / "reports" / "static-plan.yaml").exists()

    assert_yaml_files_parse(workspace)
    manifest = load_yaml(workspace / "manifest.yaml")
    assert manifest["kind"] == "static-platform-catalog"
    assert manifest["profile_snapshot"] == "profile.yaml"
    assert manifest["scope_root"] == "scopes"
    assert manifest["profile_facts"]["fabric"]
    assert manifest["profile_facts"]["system_externals"]
    assert manifest["profile_facts"]["filesystem"]
    assert manifest["profile_facts"]["node_types"]["cpu_compute"]["build_stage"]
    assert manifest["recommendations"]["compiler"]["path"] == "scopes/compilers/gcc/13.3.0"
    assert manifest["recommendations"]["mpi"]["path"] == (
        "scopes/mpi/cray-mpich/8.1.29/gcc-13.3"
    )
    assert manifest["recommendations"]["gpu"] == [
        {"kind": "gpu", "name": "rocm", "path": "scopes/gpu/rocm/6.0.0", "version": "6.0.0"}
    ]
    readme = (workspace / "README.md").read_text(encoding="utf-8")
    assert "  - scopes/common" in readme
    assert str(workspace) not in readme
    assert "retained as `profile.yaml`" in readme

    common = load_yaml(workspace / "scopes" / "common" / "packages.yaml")
    assert sorted(common["packages"]) == ["curl", "libfabric", "openssl", "ucx"]
    plan = load_yaml(workspace / "reports" / "static-plan.yaml")
    assert plan["missing_mpi_dependencies"] == [
        {"provider": "cray-mpich", "package": "cray-pmi"}
    ]

    compiler = load_yaml(workspace / "scopes" / "compilers" / "gcc" / "13.3.0" / "packages.yaml")
    assert compiler["packages"]["gcc"]["externals"][0]["spec"] == "gcc@13.3.0"
    assert not (
        workspace
        / "scopes"
        / "compilers"
        / "gcc"
        / "13.3.0"
        / "toolchains.yaml"
    ).exists()

    mpi_packages = load_yaml(
        workspace
        / "scopes"
        / "mpi"
        / "cray-mpich"
        / "8.1.29"
        / "gcc-13.3"
        / "packages.yaml"
    )
    assert mpi_packages["packages"]["mpi"]["require"] == ["cray-mpich"]
    assert mpi_packages["packages"]["cray-mpich"]["externals"][0]["spec"] == (
        "cray-mpich@8.1.29"
    )

    mpi_toolchains = load_yaml(
        workspace
        / "scopes"
        / "mpi"
        / "cray-mpich"
        / "8.1.29"
        / "gcc-13.3"
        / "toolchains.yaml"
    )
    assert set(mpi_toolchains["toolchains"]) == {"gcc133_craympich8129"}

    rocm = load_yaml(workspace / "scopes" / "gpu" / "rocm" / "6.0.0" / "packages.yaml")
    assert {"hip", "hsa-rocr-dev", "rocprim"} <= set(rocm["packages"])


def test_static_catalog_keeps_cray_mpi_baseline_for_future_cse_compiler(
    tmp_path: Path,
) -> None:
    profile = load_yaml(fixture_path("profiles", "example-cray", "profile.yaml"))
    profile["system"]["name"] = "blueback-shaped"
    for node_type in profile["node_types"].values():
        if node_type.get("gpu") is None:
            node_type["cpu"]["alternates"] = [
                "x86_64_v3",
                "x86_64_v2",
                "x86_64",
            ]
    profile["compiler_providers"] = [
        {
            "name": "cce",
            "version": "21.0.0",
            "provider_family": "platform",
            "platform_family": "cray-pe",
            "prefix": "/opt/cray/pe/cce/21.0.0",
            "modules": ["PrgEnv-cray/8.7.0", "cce/21.0.0"],
            "languages": ["c", "c++", "fortran"],
        },
        {
            "name": "gcc",
            "version": "12.2.0",
            "provider_family": "platform",
            "platform_family": "cray-pe",
            "prefix": "/opt/cray/pe/gcc-native/12.2",
            "modules": ["PrgEnv-gnu/8.7.0", "gcc-native/12.2"],
            "languages": ["c", "c++", "fortran"],
        },
        {
            "name": "gcc",
            "version": "13.3.1",
            "provider_family": "platform",
            "platform_family": "cray-pe",
            "prefix": "/opt/cray/pe/gcc-native/13.3",
            "modules": ["PrgEnv-gnu/8.7.0", "gcc-native/13.3"],
            "languages": ["c", "c++", "fortran"],
        },
    ]
    profile["fabric"]["userspace"].append(
        {
            "name": "libfabric",
            "version": "2.3.1",
            "prefix": "/opt/cray/libfabric/2.3.1",
        }
    )
    profile["mpi_providers"] = [
        {
            "name": "cray-mpich",
            "version": "9.1.0",
            "provider_family": "platform",
            "platform_family": "cray-pe",
            "flavors": {
                "cce@20.0": {
                    "prefix": "/opt/cray/pe/mpich/9.1.0/ofi/cray/20.0",
                    "modules": ["cray-mpich/9.1.0"],
                },
                "gcc@12.3": {
                    "prefix": "/opt/cray/pe/mpich/9.1.0/ofi/gnu/12.3",
                    "modules": ["cray-mpich/9.1.0"],
                },
            },
        }
    ]
    profile_path = tmp_path / "profile.yaml"
    profile_path.write_text(yaml.safe_dump(profile, sort_keys=False), encoding="utf-8")

    workspace = render_static_catalog(
        profile_path=profile_path,
        templates_root=fixture_path("template-sets"),
        template_set_name="v6",
        release_vars=ReleaseVars(
            release_tag="catalog-001",
            output_root=str(tmp_path / "output"),
            rendered_at="2026-08-13T00:00:00Z",
            source_repo=SourceRepo("stack-content", "abc123", False),
        ),
    )

    gnu_scope = (
        workspace
        / "scopes"
        / "mpi"
        / "cray-mpich"
        / "9.1.0"
        / "gcc-12.3"
    )
    assert gnu_scope.is_dir()
    assert not (
        workspace
        / "scopes"
        / "mpi"
        / "cray-mpich"
        / "9.1.0"
        / "gcc-13.3.1"
    ).exists()
    packages = load_yaml(gnu_scope / "packages.yaml")["packages"]
    assert packages["cray-mpich"]["externals"][0]["prefix"] == (
        "/opt/cray/pe/mpich/9.1.0/ofi/gnu/12.3"
    )
    assert packages["cray-mpich"]["externals"][0]["spec"] == "cray-mpich@9.1.0"
    assert packages["cray-mpich"]["externals"][0]["extra_attributes"] == {
        "environment": {
            "prepend_path": {
                "LD_LIBRARY_PATH": "/opt/cray/libfabric/2.3.1/lib64",
            }
        }
    }
    assert packages["cray-mpich"]["variants"] == "+wrappers"
    manifest = load_yaml(workspace / "manifest.yaml")
    scope = next(
        item
        for item in manifest["scopes"]
        if item["path"].endswith("/gcc-12.3")
    )
    assert scope["compiler_ref"] == "gcc@12.3"
    assert scope["compiler_compatibility"] == "family_min_version"
    assert scope["compatible_compiler_refs"] == ["gcc@13.3.1"]

    gnu_toolchains = load_yaml(gnu_scope / "toolchains.yaml")["toolchains"]
    assert gnu_toolchains["gcc123_craympich910"] == [
        {"spec": "%c=gcc@12.3:", "when": "%c"},
        {"spec": "%cxx=gcc@12.3:", "when": "%cxx"},
        {"spec": "%fortran=gcc@12.3:", "when": "%fortran"},
        {"spec": "%mpi=cray-mpich@9.1.0+wrappers", "when": "%mpi"},
    ]

    cray_scope = (
        workspace
        / "scopes"
        / "mpi"
        / "cray-mpich"
        / "9.1.0"
        / "cce-20.0"
    )
    assert cray_scope.is_dir()
    assert not (
        workspace
        / "scopes"
        / "mpi"
        / "cray-mpich"
        / "9.1.0"
        / "cce-21.0.0"
    ).exists()
    cce_scope = next(
        item
        for item in manifest["scopes"]
        if item["path"].endswith("/cce-20.0")
    )
    assert cce_scope["compiler_ref"] == "cce@20.0"
    assert cce_scope["compatible_compiler_refs"] == ["cce@21.0.0"]


def test_static_catalog_renders_linux_mpi_pairing(tmp_path: Path) -> None:
    workspace = render_static_catalog(
        profile_path=fixture_path("profiles", "example-linux", "profile.yaml"),
        templates_root=fixture_path("template-sets"),
        template_set_name="v6",
        release_vars=ReleaseVars(
            release_tag="alpha-001",
            output_root=str(tmp_path),
            rendered_at="2026-07-09T00:00:00Z",
            source_repo=SourceRepo("local-static-alpha", "abc123", False),
        ),
    )

    assert_yaml_files_parse(workspace)
    manifest = load_yaml(workspace / "manifest.yaml")
    slurm = next(
        item
        for item in manifest["profile_facts"]["system_externals"]
        if item["name"] == "slurm"
    )
    assert slurm["capabilities"]["mpi_launch"] == {
        "command": "srun",
        "plugins": ["pmi2", "pmix", "pmix_v3"],
        "development_interfaces": ["pmi2"],
    }
    mpi_scope = workspace / "scopes" / "mpi" / "openmpi" / "4.1.6" / "aocc-4.2.0"
    assert mpi_scope.exists()
    packages = load_yaml(mpi_scope / "packages.yaml")
    assert packages["packages"]["openmpi"]["externals"][0]["spec"] == (
        "openmpi@4.1.6 %aocc@4.2.0"
    )
    toolchains = load_yaml(mpi_scope / "toolchains.yaml")
    assert "aocc420_openmpi416" in toolchains["toolchains"]


def test_static_catalog_does_not_render_unknown_cuda_version(tmp_path: Path) -> None:
    profile = load_yaml(fixture_path("profiles", "example-linux", "profile.yaml"))
    profile["system"]["name"] = "unknown-cuda"
    profile.setdefault("gpu_toolkit_modules", {})["cudatoolkit"] = [
        {
            "version": "unknown",
            "module": "cuda/default",
            "prefix": "/usr/local/cuda",
        }
    ]
    profile_path = tmp_path / "profile.yaml"
    profile_path.write_text(yaml.safe_dump(profile, sort_keys=False), encoding="utf-8")

    workspace = render_static_catalog(
        profile_path=profile_path,
        templates_root=fixture_path("template-sets"),
        template_set_name="v6",
        release_vars=ReleaseVars(
            release_tag="catalog-001",
            output_root=str(tmp_path / "output"),
            rendered_at="2026-08-17T00:00:00Z",
            source_repo=SourceRepo("stack-content", "abc123", False),
        ),
    )

    assert not (workspace / "scopes" / "gpu" / "cuda" / "unknown").exists()
    manifest = load_yaml(workspace / "manifest.yaml")
    assert not any(
        scope["kind"] == "gpu"
        and scope["name"] == "cuda"
        and scope["version"] == "unknown"
        for scope in manifest["scopes"]
    )


def test_static_catalog_rejects_mpi_without_verified_compiler_pairing(
    tmp_path: Path,
) -> None:
    profile = load_yaml(fixture_path("profiles", "example-linux", "profile.yaml"))
    profile["system"]["name"] = "unpaired-mpi"
    profile["mpi_providers"] = [
        {
            "name": "openmpi",
            "version": "1.10.0",
            "provider_family": "system",
            "prefix": "/usr",
        }
    ]
    profile_path = tmp_path / "profile.yaml"
    profile_path.write_text(yaml.safe_dump(profile, sort_keys=False), encoding="utf-8")

    with pytest.raises(ValidationFailed) as exc_info:
        render_static_catalog(
            profile_path=profile_path,
            templates_root=fixture_path("template-sets"),
            template_set_name="v6",
            release_vars=ReleaseVars(
                release_tag="catalog-001",
                output_root=str(tmp_path / "output"),
                rendered_at="2026-08-17T00:00:00Z",
                source_repo=SourceRepo("stack-content", "abc123", False),
            ),
        )

    assert [issue.code for issue in exc_info.value.issues] == ["mpi-compiler-unresolved"]
    message = exc_info.value.issues[0].message
    assert "openmpi@1.10.0" in message
    assert "prefix=/usr" in message
    assert "modules=(none)" in message
    assert not (tmp_path / "output" / "unpaired-mpi").exists()


def test_static_catalog_maps_classic_intel_and_intel_mpi_packages(
    tmp_path: Path,
) -> None:
    profile = load_yaml(fixture_path("profiles", "example-linux", "profile.yaml"))
    profile["system"]["name"] = "classic-intel"
    profile["compiler_providers"] = [
        {
            "name": "intel",
            "version": "2021.10.0",
            "provider_family": "site",
            "prefix": "/opt/intel/oneapi/compiler/2023.2.4",
            "modules": ["intel/2023.2.4"],
            "languages": ["c", "c++", "fortran"],
        }
    ]
    profile["mpi_providers"] = [
        {
            "name": "intel-mpi",
            "version": "2021.10.0",
            "provider_family": "site",
            "prefix": "/opt/intel/oneapi/mpi/2021.10",
            "modules": ["intel-mpi/2021.10"],
            "compiler": "intel@2021.10.0",
        }
    ]
    profile_path = tmp_path / "profile.yaml"
    profile_path.write_text(yaml.safe_dump(profile, sort_keys=False), encoding="utf-8")

    workspace = render_static_catalog(
        profile_path=profile_path,
        templates_root=fixture_path("template-sets"),
        template_set_name="v6",
        release_vars=ReleaseVars(
            release_tag="trial-001",
            output_root=str(tmp_path / "output"),
            rendered_at="2026-08-12T00:00:00Z",
            source_repo=SourceRepo("local-static", "abc123", False),
        ),
    )

    manifest = load_yaml(workspace / "manifest.yaml")
    assert manifest["recommendations"]["compiler"]["package"] == (
        "intel-oneapi-compilers-classic"
    )
    assert manifest["recommendations"]["compiler"]["path"] == (
        "scopes/compilers/intel/2021.10.0"
    )
    assert manifest["recommendations"]["mpi"]["package"] == "intel-oneapi-mpi"

    compiler_scope = workspace / "scopes" / "compilers" / "intel" / "2021.10.0"
    compiler_packages = load_yaml(compiler_scope / "packages.yaml")["packages"]
    assert set(compiler_packages) == {"intel-oneapi-compilers-classic"}
    compiler_external = compiler_packages["intel-oneapi-compilers-classic"]["externals"][0]
    assert compiler_external["spec"] == "intel-oneapi-compilers-classic@2021.10.0"
    assert compiler_external["extra_attributes"]["compilers"] == {
        "c": "/opt/intel/oneapi/compiler/2023.2.4/bin/icc",
        "cxx": "/opt/intel/oneapi/compiler/2023.2.4/bin/icpc",
        "fortran": "/opt/intel/oneapi/compiler/2023.2.4/bin/ifort",
    }

    mpi_scope = (
        workspace
        / "scopes"
        / "mpi"
        / "intel-mpi"
        / "2021.10.0"
        / "intel-2021.10.0"
    )
    mpi_packages = load_yaml(mpi_scope / "packages.yaml")["packages"]
    assert mpi_packages["mpi"]["require"] == ["intel-oneapi-mpi"]
    assert mpi_packages["intel-oneapi-mpi"]["variants"] == "+classic-names"
    assert mpi_packages["intel-oneapi-mpi"]["externals"][0]["spec"] == (
        "intel-oneapi-mpi@2021.10.0 +classic-names "
        "%intel-oneapi-compilers-classic@2021.10.0"
    )
    toolchains = load_yaml(mpi_scope / "toolchains.yaml")["toolchains"]
    entries = toolchains["intel2021100_intelmpi2021100"]
    assert {entry["spec"] for entry in entries} == {
        "%c=intel-oneapi-compilers-classic@2021.10.0",
        "%cxx=intel-oneapi-compilers-classic@2021.10.0",
        "%fortran=intel-oneapi-compilers-classic@2021.10.0",
        "%mpi=intel-oneapi-mpi@2021.10.0+classic-names",
    }


def test_static_catalog_uses_oneapi_suite_root_for_wheat_component_prefix(
    tmp_path: Path,
) -> None:
    profile = load_yaml(fixture_path("profiles", "example-linux", "profile.yaml"))
    profile["system"]["name"] = "wheat"
    profile["compiler_providers"] = [
        {
            "name": "oneapi",
            "version": "2024.2.1",
            "provider_family": "site",
            "prefix": "/p/app/intel/2024.2.1/compiler/2024.2",
            "modules": [
                "intel/2024.2.1/compiler/latest",
                "intel/2024.2.1/compiler-rt/latest",
                "intel/2024.2.1/tbb/latest",
            ],
            "languages": ["c", "c++", "fortran"],
        }
    ]
    profile["mpi_providers"] = []
    profile_path = tmp_path / "profile.yaml"
    profile_path.write_text(yaml.safe_dump(profile, sort_keys=False), encoding="utf-8")

    workspace = render_static_catalog(
        profile_path=profile_path,
        templates_root=fixture_path("template-sets"),
        template_set_name="v6",
        release_vars=ReleaseVars(
            release_tag="wheat-001",
            output_root=str(tmp_path / "output"),
            rendered_at="2026-08-25T00:00:00Z",
            source_repo=SourceRepo("stack-content", "abc123", False),
        ),
    )

    packages_path = (
        workspace
        / "scopes"
        / "compilers"
        / "oneapi"
        / "2024.2.1"
        / "packages.yaml"
    )
    external = load_yaml(packages_path)["packages"]["intel-oneapi-compilers"][
        "externals"
    ][0]
    assert external["prefix"] == "/p/app/intel/2024.2.1"
    assert external["extra_attributes"]["compilers"] == {
        "c": "/p/app/intel/2024.2.1/compiler/2024.2/bin/icx",
        "cxx": "/p/app/intel/2024.2.1/compiler/2024.2/bin/icpx",
        "fortran": "/p/app/intel/2024.2.1/compiler/2024.2/bin/ifx",
    }
    assert "compiler/2024.2/compiler/2024.2" not in packages_path.read_text(
        encoding="utf-8"
    )


def test_static_catalog_uses_spack_cce_driver_names(tmp_path: Path) -> None:
    profile = load_yaml(fixture_path("profiles", "example-linux", "profile.yaml"))
    profile["system"]["name"] = "current-cce"
    profile["compiler_providers"] = [
        {
            "name": "cce",
            "version": "21.0.0",
            "provider_family": "platform",
            "prefix": "/opt/cray/pe/cce/21.0.0",
            "modules": ["PrgEnv-cray", "cce/21.0.0"],
            "languages": ["c", "c++", "fortran"],
        }
    ]
    profile["mpi_providers"] = []
    profile_path = tmp_path / "profile.yaml"
    profile_path.write_text(yaml.safe_dump(profile, sort_keys=False), encoding="utf-8")

    workspace = render_static_catalog(
        profile_path=profile_path,
        templates_root=fixture_path("template-sets"),
        template_set_name="v6",
        release_vars=ReleaseVars(
            release_tag="trial-001",
            output_root=str(tmp_path / "output"),
            rendered_at="2026-08-12T00:00:00Z",
            source_repo=SourceRepo("local-static", "abc123", False),
        ),
    )

    packages = load_yaml(
        workspace / "scopes" / "compilers" / "cce" / "21.0.0" / "packages.yaml"
    )["packages"]
    commands = packages["cce"]["externals"][0]["extra_attributes"]["compilers"]
    assert commands["c"] == "/opt/cray/pe/cce/21.0.0/bin/craycc"
    assert commands["cxx"] == "/opt/cray/pe/cce/21.0.0/bin/crayCC"
    assert commands["fortran"] == "/opt/cray/pe/cce/21.0.0/bin/crayftn"


def test_static_catalog_keeps_cray_pmi_with_cray_mpich_scope(tmp_path: Path) -> None:
    profile = load_yaml(fixture_path("profiles", "example-cray", "profile.yaml"))
    profile["fabric"]["userspace"].append(
        {
            "name": "cray-pmi",
            "version": "6.1.15",
            "prefix": "/opt/cray/pe/pmi/6.1.15",
        }
    )
    profile_path = tmp_path / "profile.yaml"
    profile_path.write_text(yaml.safe_dump(profile, sort_keys=False), encoding="utf-8")

    workspace = render_static_catalog(
        profile_path=profile_path,
        templates_root=fixture_path("template-sets"),
        template_set_name="v6",
        release_vars=ReleaseVars(
            release_tag="trial-001",
            output_root=str(tmp_path / "output"),
            rendered_at="2026-08-12T00:00:00Z",
            source_repo=SourceRepo("local-static", "abc123", False),
        ),
    )

    packages = load_yaml(
        workspace
        / "scopes"
        / "mpi"
        / "cray-mpich"
        / "8.1.29"
        / "gcc-13.3"
        / "packages.yaml"
    )["packages"]
    assert packages["cray-pmi"] == {
        "buildable": False,
        "externals": [
            {
                "spec": "cray-pmi@6.1.15",
                "prefix": "/opt/cray/pe/pmi/6.1.15",
                "modules": [],
            }
        ],
    }
    assert packages["cray-mpich"]["externals"][0]["spec"] == (
        "cray-mpich@8.1.29"
    )
    plan = load_yaml(workspace / "reports" / "static-plan.yaml")
    assert {item["name"] for item in plan["mpi_dependency_externals"]} == {
        "cray-pmi"
    }
    assert "cray-pmi" not in {item["name"] for item in plan["not_rendered"]}
    assert plan["missing_mpi_dependencies"] == []


def test_static_catalog_recommends_platform_mpi_without_provider_name_bias(
    tmp_path: Path,
) -> None:
    profile = load_yaml(fixture_path("profiles", "example-cray", "profile.yaml"))
    cray_mpi = deepcopy(profile["mpi_providers"][0])
    platform_mpi = deepcopy(cray_mpi)
    platform_mpi["name"] = "vendor-mpi"
    platform_mpi["version"] = "2.0.0"
    profile["mpi_providers"] = [platform_mpi, cray_mpi]
    profile_path = tmp_path / "profile.yaml"
    profile_path.write_text(yaml.safe_dump(profile, sort_keys=False), encoding="utf-8")

    workspace = render_static_catalog(
        profile_path=profile_path,
        templates_root=fixture_path("template-sets"),
        template_set_name="v6",
        release_vars=ReleaseVars(
            release_tag="alpha-001",
            output_root=str(tmp_path / "output"),
            rendered_at="2026-07-09T00:00:00Z",
            source_repo=SourceRepo("local-static-alpha", "abc123", False),
        ),
    )

    manifest = load_yaml(workspace / "manifest.yaml")
    assert manifest["recommendations"]["mpi"]["name"] == "vendor-mpi"


def test_static_catalog_recommends_site_mpi_without_provider_name_bias(
    tmp_path: Path,
) -> None:
    profile = load_yaml(fixture_path("profiles", "example-linux", "profile.yaml"))
    profile["system"]["name"] = "generic-platform"
    profile["mpi_providers"] = [
        {
            "name": "vendor-mpi",
            "version": "5.0.0",
            "provider_family": "site",
            "prefix": "/opt/vendor-mpi/5.0.0",
            "compiler": "aocc@4.2.0",
        },
        {
            "name": "cray-mpich",
            "version": "8.1.29",
            "provider_family": "site",
            "prefix": "/opt/other-mpi/8.1.29",
            "compiler": "aocc@4.2.0",
        },
    ]
    profile_path = tmp_path / "profile.yaml"
    profile_path.write_text(yaml.safe_dump(profile, sort_keys=False), encoding="utf-8")

    workspace = render_static_catalog(
        profile_path=profile_path,
        templates_root=fixture_path("template-sets"),
        template_set_name="v6",
        release_vars=ReleaseVars(
            release_tag="alpha-001",
            output_root=str(tmp_path),
            rendered_at="2026-07-09T00:00:00Z",
            source_repo=SourceRepo("local-static-alpha", "abc123", False),
        ),
    )

    manifest = load_yaml(workspace / "manifest.yaml")
    assert manifest["recommendations"]["mpi"]["name"] == "vendor-mpi"
    assert manifest["recommendations"]["mpi"]["path"] == (
        "scopes/mpi/vendor-mpi/5.0.0/aocc-4.2.0"
    )


def test_static_catalog_recommends_compiler_through_baseline_policy(
    tmp_path: Path,
) -> None:
    profile = load_yaml(fixture_path("profiles", "example-linux", "profile.yaml"))
    profile["system"]["name"] = "compiler-policy"
    profile["compiler_providers"] = [
        {
            "name": "gcc",
            "version": "13.3.1",
            "prefix": "/opt/site/gcc/13.3.1",
            "provider_family": "site",
            "languages": ["c", "c++", "fortran"],
        },
        {
            "name": "gcc",
            "version": "14.2.0",
            "prefix": "/usr",
            "provider_family": "system",
            "languages": ["c", "c++", "fortran"],
        },
    ]
    profile["mpi_providers"] = []
    profile_path = tmp_path / "profile.yaml"
    profile_path.write_text(yaml.safe_dump(profile, sort_keys=False), encoding="utf-8")

    workspace = render_static_catalog(
        profile_path=profile_path,
        templates_root=fixture_path("template-sets"),
        template_set_name="v6",
        release_vars=ReleaseVars(
            release_tag="alpha-001",
            output_root=str(tmp_path),
            rendered_at="2026-07-09T00:00:00Z",
            source_repo=SourceRepo("local-static-alpha", "abc123", False),
        ),
    )

    manifest = load_yaml(workspace / "manifest.yaml")
    assert manifest["recommendations"]["compiler"]["path"] == (
        "scopes/compilers/gcc/13.3.1"
    )


def test_render_static_cli_writes_catalog(tmp_path: Path) -> None:
    result = CliRunner().invoke(
        cli,
        [
            "render-static",
            "--profile",
            str(fixture_path("profiles", "example-linux", "profile.yaml")),
            "--templates",
            str(fixture_path("template-sets")),
            "--template-set",
            "v6",
            "--output-root",
            str(tmp_path),
            "--release",
            "alpha-001",
            "--rendered-at",
            "2026-07-09T00:00:00Z",
            "--source-repo",
            "local-static-alpha",
            "--source-commit",
            "abc123",
        ],
    )

    assert result.exit_code == 0, result.output
    workspace = tmp_path / "example-linux" / "static" / "alpha-001"
    assert str(workspace) in result.output
    assert (workspace / "manifest.yaml").exists()


def assert_yaml_files_parse(root: Path) -> None:
    for path in root.rglob("*.yaml"):
        load_yaml(path)


def load_yaml(path: Path) -> dict:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(data, dict), path
    return data


def test_recommendation_prefers_platform_family_mpi_regardless_of_name(tmp_path: Path) -> None:
    # The platform-provider preference is a provider-family fact, not a vendor
    # name: rename the Cray MPI and add a newer site MPI — the platform one
    # must still win the recommendation.
    profile = load_yaml(fixture_path("profiles", "example-cray", "profile.yaml"))
    profile = deepcopy(profile)
    for provider in profile["mpi_providers"]:
        if provider["name"] == "cray-mpich":
            provider["name"] = "vendor-mpich"
    profile["mpi_providers"].append(
        {
            "name": "mpich",
            "version": "99.0",
            "provider_family": "site",
            "prefix": "/opt/site/mpich/99.0",
            "compiler": "gcc@13.3.0",
        }
    )
    profile_path = tmp_path / "profile.yaml"
    profile_path.write_text(yaml.safe_dump(profile, sort_keys=False), encoding="utf-8")

    workspace = render_static_catalog(
        profile_path=profile_path,
        templates_root=fixture_path("template-sets"),
        template_set_name="v6",
        release_vars=ReleaseVars(
            release_tag="alpha-002",
            output_root=str(tmp_path),
            rendered_at="2026-07-09T00:00:00Z",
            source_repo=SourceRepo("local-static-alpha", "abc123", False),
        ),
    )

    manifest = load_yaml(workspace / "manifest.yaml")
    assert manifest["recommendations"]["mpi"]["name"] == "vendor-mpich"


def test_static_catalog_keeps_one_scope_per_mpi_compiler_build(tmp_path: Path) -> None:
    """One MPI version built once per compiler must not collapse into one scope.

    Generic Linux profiles report a physical install per compiler, so a site
    that ships openmpi 5.0.5 for both gcc and aocc has two prefixes under one
    name and version. Each build needs its own scope: the prefixes differ, and
    a user picking the aocc scope must not be handed the gcc prefix.
    """
    profile = load_yaml(fixture_path("profiles", "example-linux", "profile.yaml"))
    profile["mpi_providers"] = [
        {
            "name": "openmpi",
            "version": "5.0.5",
            "provider_family": "site",
            "prefix": "/opt/site/openmpi/5.0.5-gcc-11.4.0",
            "compiler": "gcc@11.4.0",
        },
        {
            "name": "openmpi",
            "version": "5.0.5",
            "provider_family": "site",
            "prefix": "/opt/site/openmpi/5.0.5-aocc-4.2.0",
            "compiler": "aocc@4.2.0",
        },
    ]
    profile_path = tmp_path / "profile.yaml"
    profile_path.write_text(yaml.safe_dump(profile, sort_keys=False), encoding="utf-8")

    workspace = render_static_catalog(
        profile_path=profile_path,
        templates_root=fixture_path("template-sets"),
        template_set_name="v6",
        release_vars=ReleaseVars(
            release_tag="alpha-001",
            output_root=str(tmp_path / "output"),
            rendered_at="2026-07-09T00:00:00Z",
            source_repo=SourceRepo("local-static-alpha", "abc123", False),
        ),
    )

    gcc_scope = workspace / "scopes" / "mpi" / "openmpi" / "5.0.5" / "gcc-11.4.0"
    aocc_scope = workspace / "scopes" / "mpi" / "openmpi" / "5.0.5" / "aocc-4.2.0"
    assert gcc_scope.exists(), "gcc build of openmpi 5.0.5 lost its scope"
    assert aocc_scope.exists(), "aocc build of openmpi 5.0.5 lost its scope"

    gcc_external = load_yaml(gcc_scope / "packages.yaml")["packages"]["openmpi"]["externals"][0]
    aocc_external = load_yaml(aocc_scope / "packages.yaml")["packages"]["openmpi"]["externals"][0]
    assert gcc_external["prefix"] == "/opt/site/openmpi/5.0.5-gcc-11.4.0"
    assert aocc_external["prefix"] == "/opt/site/openmpi/5.0.5-aocc-4.2.0"


def test_static_catalog_readme_states_the_mpi_compiler_pairing(tmp_path: Path) -> None:
    """The static tree informs rather than enforces, so it must say the rule.

    A user assembling their own environment picks scopes by hand. The pairing
    between an MPI build and the compiler it was built with is only implicit in
    the scope path, so the README states it plainly and names the compiler the
    recommended MPI scope expects.
    """
    workspace = render_static_catalog(
        profile_path=fixture_path("profiles", "example-cray", "profile.yaml"),
        templates_root=fixture_path("template-sets"),
        template_set_name="v6",
        release_vars=ReleaseVars(
            release_tag="alpha-001",
            output_root=str(tmp_path),
            rendered_at="2026-07-09T00:00:00Z",
            source_repo=SourceRepo("local-static-alpha", "abc123", False),
        ),
    )

    readme = (workspace / "README.md").read_text(encoding="utf-8")
    assert "minimum compiler baseline gcc@13.3" in readme
    assert "gcc@13.3.0" in readme, "README must list observed compatible compilers"


def test_static_catalog_readme_documents_isolation_and_own_compiler(tmp_path: Path) -> None:
    """The README is the whole interface for a hand-assembled environment.

    Two moves are not discoverable from the scope tree alone: overriding
    ambient config scopes, and building your own compiler rather than taking
    the platform's. Both belong in the generated README or they stay tribal.
    """
    workspace = render_static_catalog(
        profile_path=fixture_path("profiles", "example-cray", "profile.yaml"),
        templates_root=fixture_path("template-sets"),
        template_set_name="v6",
        release_vars=ReleaseVars(
            release_tag="alpha-001",
            output_root=str(tmp_path),
            rendered_at="2026-07-09T00:00:00Z",
            source_repo=SourceRepo("local-static-alpha", "abc123", False),
        ),
    )

    readme = (workspace / "README.md").read_text(encoding="utf-8")
    assert "include::" in readme, "README must show the ambient-scope override"
    assert "~/.spack" in readme
    assert "scopes/compilers" in readme, "README must explain the compiler scope choice"
