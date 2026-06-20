from __future__ import annotations

import shutil
from pathlib import Path

import click
import pytest

from stack_composer.commands import publish_manifest
from stack_composer.schema_registry import validate_schema
from stack_composer.yaml_io import load_yaml, write_yaml
from tests.conftest import fixture_path


def test_publish_manifest_finalizes_draft_with_multiple_lockfiles(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    shutil.copy2(
        fixture_path("manifests", "release-manifest-draft.yaml"),
        workspace / "release-manifest.yaml",
    )
    lockfiles = tmp_path / "locks"
    write_lockfile(lockfiles / "gcc" / "core" / "spack.lock", "/opt/spack/gcc-core")
    write_lockfile(
        lockfiles / "cce" / "mpi-craympich" / "spack.lock",
        "/opt/spack/cce-mpi-craympich",
        external_path="/opt/cray/pe/mpich/8.1.29",
    )
    prereqs = tmp_path / "platform-module-prereqs.yaml"
    write_yaml(
        prereqs,
        {
            "lanes": {
                "gcc-core": [],
                "cce-mpi-craympich": ["PrgEnv-cray", "cce/17.0.1", "cray-mpich/8.1.29"],
            }
        },
    )
    buildcache = tmp_path / "buildcache-destinations.yaml"
    write_yaml(
        buildcache,
        {
            "push_destinations": [
                {
                    "name": "payload",
                    "url": "file:///cache/payload",
                    "lanes_pushed": ["gcc-core", "cce-mpi-craympich"],
                }
            ]
        },
    )
    verify = tmp_path / "verify-results.yaml"
    write_yaml(verify, verify_report())

    publish_manifest.run(
        workspace=str(workspace),
        build_host="login01",
        lockfiles=str(lockfiles),
        platform_module_prereqs=str(prereqs),
        buildcache_destinations=str(buildcache),
        verify_results=str(verify),
        force=False,
    )

    manifest = load_yaml(workspace / "release-manifest.yaml")
    assert validate_schema("release-manifest", manifest, "release-manifest.yaml") == []
    assert manifest["phase"] == "final"
    assert manifest["spack"]["version"] == "1.1.1"
    assert manifest["build_host"]["hostname"] == "login01"
    assert [lane["lockfile"] for lane in manifest["lanes"]] == [
        "gcc/core/spack.lock",
        "cce/mpi-craympich/spack.lock",
    ]
    assert manifest["lanes"][0]["install_root"] == "/opt/spack/gcc-core"
    assert manifest["lanes"][1]["platform_module_prereqs"] == [
        "PrgEnv-cray",
        "cce/17.0.1",
        "cray-mpich/8.1.29",
    ]
    assert manifest["buildcache"]["push_destinations"][0]["lanes_pushed"] == [
        "gcc-core",
        "cce-mpi-craympich",
    ]


def test_publish_manifest_refuses_final_without_force(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    shutil.copy2(
        fixture_path("manifests", "release-manifest-final.yaml"),
        workspace / "release-manifest.yaml",
    )

    with pytest.raises(click.ClickException) as excinfo:
        publish_manifest.run(
            workspace=str(workspace),
            build_host="login01",
            lockfiles=str(tmp_path / "locks"),
            platform_module_prereqs=str(tmp_path / "prereqs.yaml"),
            buildcache_destinations=str(tmp_path / "buildcache.yaml"),
            verify_results=str(tmp_path / "verify.yaml"),
            force=False,
        )

    assert "already final" in str(excinfo.value)


def test_publish_manifest_rejects_unsupported_lockfile_shape(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    shutil.copy2(
        fixture_path("manifests", "release-manifest-draft.yaml"),
        workspace / "release-manifest.yaml",
    )
    lockfiles = tmp_path / "locks"
    write_lockfile(lockfiles / "gcc" / "core" / "spack.lock", "/opt/spack/gcc-core")
    write_yaml(
        lockfiles / "cce" / "mpi-craympich" / "spack.lock",
        {"_meta": {"lockfile-version": 99}, "roots": [], "concrete_specs": {}},
    )
    prereqs = tmp_path / "platform-module-prereqs.yaml"
    write_yaml(prereqs, {"lanes": {"gcc-core": [], "cce-mpi-craympich": []}})
    buildcache = tmp_path / "buildcache-destinations.yaml"
    write_yaml(buildcache, {"push_destinations": []})
    verify = tmp_path / "verify-results.yaml"
    write_yaml(verify, verify_report())

    with pytest.raises(click.ClickException) as excinfo:
        publish_manifest.run(
            workspace=str(workspace),
            build_host="login01",
            lockfiles=str(lockfiles),
            platform_module_prereqs=str(prereqs),
            buildcache_destinations=str(buildcache),
            verify_results=str(verify),
            force=False,
        )

    assert "unsupported spack.lock shape" in str(excinfo.value)


def write_lockfile(path: Path, install_root: str, external_path: str | None = None) -> None:
    specs = {
        "root": {
            "name": "zlib",
            "namespace": "builtin",
            "prefix": install_root,
        }
    }
    if external_path:
        specs["external"] = {
            "name": "cray-mpich",
            "namespace": "builtin",
            "external": {"path": external_path},
        }
    write_yaml(
        path,
        {
            "_meta": {"file-type": "spack-lockfile", "lockfile-version": 6},
            "roots": [{"hash": "root", "spec": "zlib"}],
            "concrete_specs": specs,
        },
    )


def verify_report() -> dict:
    return {
        "spack": {"version": "1.1.1", "commit": None},
        "build_host": {"os": "rhel", "os_major": 8, "glibc": "2.28", "cpu": "zen3"},
        "verification": {
            "spack_verify_libraries": "passed",
            "spack_verify_manifest": "passed",
            "site_smoke_tests": "passed",
            "notes": "fixture verification",
        },
        "previous_release": "2026.05",
    }
