from __future__ import annotations

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
    assert manifest["recommendations"]["compiler"]["path"] == "scopes/compilers/gcc/13.3.0"
    assert manifest["recommendations"]["mpi"]["path"] == (
        "scopes/mpi/cray-mpich/8.1.29/gcc-13.3.0"
    )
    assert manifest["recommendations"]["gpu"] == [
        {"kind": "gpu", "name": "rocm", "path": "scopes/gpu/rocm/6.0.0", "version": "6.0.0"}
    ]

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
