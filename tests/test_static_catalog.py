from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import yaml
from click.testing import CliRunner

from stack_composer.cli import cli
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
    assert (workspace / "reports" / "static-plan.yaml").exists()

    assert_yaml_files_parse(workspace)
    manifest = load_yaml(workspace / "manifest.yaml")
    assert manifest["kind"] == "static-platform-catalog"
    assert manifest["scope_root"] == str(workspace / "scopes")
    assert manifest["recommendations"]["compiler"]["path"] == "scopes/compilers/gcc/13.3.0"
    assert manifest["recommendations"]["mpi"]["path"] == (
        "scopes/mpi/cray-mpich/8.1.29/gcc-13.3.0"
    )
    assert manifest["recommendations"]["gpu"] == [
        {"kind": "gpu", "name": "rocm", "path": "scopes/gpu/rocm/6.0.0", "version": "6.0.0"}
    ]
    readme = (workspace / "README.md").read_text(encoding="utf-8")
    assert f"  - {workspace}/scopes/common" in readme

    common = load_yaml(workspace / "scopes" / "common" / "packages.yaml")
    assert sorted(common["packages"]) == ["curl", "libfabric", "openssl", "ucx"]

    compiler = load_yaml(workspace / "scopes" / "compilers" / "gcc" / "13.3.0" / "packages.yaml")
    assert compiler["packages"]["gcc"]["externals"][0]["spec"] == "gcc@13.3.0"

    mpi_packages = load_yaml(
        workspace
        / "scopes"
        / "mpi"
        / "cray-mpich"
        / "8.1.29"
        / "gcc-13.3.0"
        / "packages.yaml"
    )
    assert mpi_packages["packages"]["mpi"]["require"] == ["cray-mpich"]
    assert mpi_packages["packages"]["cray-mpich"]["externals"][0]["spec"] == "cray-mpich@8.1.29"

    mpi_toolchains = load_yaml(
        workspace
        / "scopes"
        / "mpi"
        / "cray-mpich"
        / "8.1.29"
        / "gcc-13.3.0"
        / "toolchains.yaml"
    )
    assert "gcc1330_craympich8129" in mpi_toolchains["toolchains"]

    rocm = load_yaml(workspace / "scopes" / "gpu" / "rocm" / "6.0.0" / "packages.yaml")
    assert {"hip", "hsa-rocr-dev", "rocprim"} <= set(rocm["packages"])


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
    mpi_scope = workspace / "scopes" / "mpi" / "openmpi" / "4.1.6" / "aocc-4.2.0"
    assert mpi_scope.exists()
    packages = load_yaml(mpi_scope / "packages.yaml")
    assert packages["packages"]["openmpi"]["externals"][0]["spec"] == (
        "openmpi@4.1.6 %aocc@4.2.0"
    )
    toolchains = load_yaml(mpi_scope / "toolchains.yaml")
    assert "aocc420_openmpi416" in toolchains["toolchains"]


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
