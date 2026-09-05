"""Safety regressions promoted from the September assessment.

Run from the Stack Composer checkout with PYTHONPATH=src:. and pytest.
Only pytest-owned temporary directories and fake Spack commands are modified.
"""

from __future__ import annotations

import os
import shutil
import stat
import subprocess
from pathlib import Path

import pytest

from stack_composer.errors import ValidationFailed
from stack_composer.manifest.finalize import atomic_write_manifest
from stack_composer.publish.static_catalog import (
    publish_static_catalog,
    verify_static_catalog_publication,
)
from stack_composer.render.engine import render_workspace
from stack_composer.render.release import ReleaseVars, SourceRepo
from stack_composer.render.static_catalog import render_static_catalog
from stack_composer.workspace.initializer import initialize_workspace
from stack_composer.yaml_io import load_yaml, write_yaml
from tests.conftest import fixture_path
from tests.test_workspace_init import make_inputs


def render(root: Path, kind: str = "static", release: str = "audit", **overrides) -> Path:
    kwargs = dict(
        profile_path=fixture_path("profiles", "example-linux", "profile.yaml"),
        templates_root=fixture_path("template-sets"),
        release_vars=ReleaseVars(
            release_tag=release,
            output_root=str(root),
            rendered_at="2026-09-04T00:00:00Z",
            source_repo=SourceRepo("local://assessment", "a" * 40, False),
            overwrite=True,
        ),
    )
    if kind == "static":
        return render_static_catalog(**kwargs, template_set_name="v6")
    kwargs.update(
        deployment_path=fixture_path("deployments", "example-linux.yaml"),
        stack_path=fixture_path("stacks", "science-stack", "stack.yaml"),
        package_sets_dir=fixture_path("package-sets"),
        package_repos_dir=fixture_path("package-repos"),
    )
    kwargs.update(overrides)
    return render_workspace(**kwargs)


@pytest.mark.parametrize("kind", ["static", "full"])
def test_release_cannot_escape_output_root(tmp_path: Path, kind: str) -> None:
    outside = tmp_path / "outside-output-root"
    outside.mkdir()
    marker = outside / "existing-user-data"
    marker.write_text("preserve me")
    try:
        render(tmp_path / "declared-root", kind=kind, release=str(outside))
    except ValidationFailed:
        pass
    assert marker.is_file(), "absolute release escaped --output-root and removed existing data"


def test_static_render_preserves_another_runs_pending_tree(tmp_path: Path) -> None:
    pending = tmp_path / "example-linux/static/audit.rendering"
    pending.mkdir(parents=True)
    marker = pending / "other-run"
    marker.write_text("in progress")
    try:
        render(tmp_path)
    except ValidationFailed:
        pass
    assert marker.is_file(), "render-static deleted a pre-existing pending render"


def test_static_render_cleans_up_after_write_failure(tmp_path: Path, monkeypatch) -> None:
    from stack_composer.render import static_catalog

    def fail_write(*_args):
        raise OSError("injected disk-write failure")

    monkeypatch.setattr(static_catalog, "write_static_catalog", fail_write)
    with pytest.raises(OSError, match="injected"):
        render(tmp_path)
    assert not (tmp_path / "example-linux/static/audit.rendering").exists()


@pytest.mark.parametrize("kind", ["static", "full", "init"])
def test_overwrite_retains_old_workspace_if_promotion_fails(
    tmp_path: Path, monkeypatch, kind: str
) -> None:
    if kind == "init":
        blueprint, catalog, values = make_inputs(tmp_path / "inputs")
        destination = tmp_path / "workspace"
        destination.mkdir()

        def invoke():
            return initialize_workspace(
                blueprint_dir=blueprint,
                catalog_dir=catalog,
                values_path=values,
                output_dir=destination,
                overwrite=True,
            )
    else:
        destination = render(tmp_path / "out", kind=kind)

        def invoke():
            return render(tmp_path / "out", kind=kind)

    marker = destination / "original.lock"
    marker.write_text("previous successful workspace")
    real_replace, real_rename = Path.replace, Path.rename

    def fail_promotion(self, target):
        if Path(target) == destination:
            raise OSError("injected final rename failure")
        return real_replace(self, target)

    def fail_rename(self, target):
        if Path(target) == destination:
            raise OSError("injected final rename failure")
        return real_rename(self, target)

    monkeypatch.setattr(Path, "replace", fail_promotion)
    monkeypatch.setattr(Path, "rename", fail_rename)
    with pytest.raises((OSError, ValidationFailed)):
        invoke()
    assert marker.is_file(), "failed replacement permanently removed the prior workspace"


@pytest.mark.parametrize("mode", [0o660, 0o664])
def test_final_manifest_preserves_collaborative_file_mode(tmp_path: Path, mode: int) -> None:
    manifest = tmp_path / "release-manifest.yaml"
    write_yaml(manifest, {"phase": "draft"})
    manifest.chmod(mode)
    group = manifest.stat().st_gid
    atomic_write_manifest(manifest, {"phase": "final"})
    assert stat.S_IMODE(manifest.stat().st_mode) == mode
    assert manifest.stat().st_gid == group


def test_deployment_change_changes_manifest_provenance(tmp_path: Path) -> None:
    deployment = tmp_path / "deployment.yaml"
    shutil.copyfile(fixture_path("deployments", "example-linux.yaml"), deployment)
    first = render(tmp_path / "out", kind="full", deployment_path=deployment)
    old_manifest = (first / "release-manifest.yaml").read_bytes()
    old_config = (first / "configs/common/config.yaml").read_bytes()
    data = load_yaml(deployment)
    data["install_tree"]["root"] = "/different-reviewed-install-root"
    write_yaml(deployment, data)
    second = render(tmp_path / "out", kind="full", deployment_path=deployment)
    assert (second / "configs/common/config.yaml").read_bytes() != old_config
    assert (second / "release-manifest.yaml").read_bytes() != old_manifest


def test_initializer_rejects_duplicate_generated_yaml_keys(tmp_path: Path) -> None:
    blueprint, catalog, values = make_inputs(tmp_path / "inputs")
    (blueprint / "templates/spack.yaml.j2").write_text("spack:\n  specs: [hdf5]\n  specs: [zlib]\n")
    with pytest.raises(ValidationFailed):
        initialize_workspace(
            blueprint_dir=blueprint,
            catalog_dir=catalog,
            values_path=values,
            output_dir=tmp_path / "workspace",
        )


def test_published_catalog_with_nested_metadata_names_can_verify(tmp_path: Path) -> None:
    catalog = render(tmp_path / "restricted")
    write_yaml(catalog / "scopes/common/publication.yaml", {"note": "ordinary source file"})
    published = publish_static_catalog(
        catalog_dir=catalog,
        output_root=tmp_path / "published",
        published_at="2026-09-04T00:00:00Z",
        reviewed_by="test",
        approved_by="test",
    )
    verify_static_catalog_publication(
        catalog_dir=published,
        publication=load_yaml(published / "publication.yaml"),
    )


@pytest.mark.parametrize("flag", [
    "--workspace", "--jobs", "--spack-root", "--lanes", "--reports", "--concretize-jobs",
    "--buildcache",
])
def test_spack_build_missing_option_value_exits_promptly(flag: str) -> None:
    result = subprocess.run(
        ["scripts/spack-build", flag], capture_output=True, text=True, timeout=1
    )
    assert result.returncode != 0


def fake_spack(tmp_path: Path, failure: str) -> tuple[dict, Path, Path]:
    workspace = tmp_path / "workspace"
    write_yaml(workspace / "environments/gcc/core/spack.yaml", {"spack": {"specs": ["zlib"]}})
    bindir = tmp_path / "bin"
    bindir.mkdir()
    fake = bindir / "spack"
    fake.write_text(
        "#!/bin/bash\n"
        'printf "%s\\n" "$*" >> "$ASSESSMENT_SPACK_LOG"\n'
        'if [[ "$1" == --version ]]; then echo 1.2.2; exit 0; fi\n'
        'if [[ "$*" == *"$ASSESSMENT_FAILURE"* ]]; then exit 9; fi\n'
        'if [[ "$*" == *"find --explicit"* ]]; then echo /opt/example/zlib; fi\n'
        "exit 0\n"
    )
    fake.chmod(0o755)
    env = dict(os.environ)
    log = tmp_path / "spack-calls.log"
    env.update(
        PATH=f"{bindir}{os.pathsep}{env['PATH']}",
        ASSESSMENT_SPACK_LOG=str(log),
        ASSESSMENT_FAILURE=failure,
    )
    return env, workspace, log


def test_failed_hash_inventory_cannot_report_verification_passed(tmp_path: Path) -> None:
    env, workspace, _ = fake_spack(tmp_path, "find -H")
    result = subprocess.run(
        ["scripts/spack-build", "--workspace", str(workspace), "--skip-push"],
        env=env,
        capture_output=True,
        text=True,
        timeout=10,
    )
    report = load_yaml(workspace / "reports/verify-results.yaml")
    assert result.returncode != 0, report
    assert report["verification"]["spack_verify_manifest"] == "failed"


def test_failed_build_is_not_reported_as_pushed(tmp_path: Path) -> None:
    env, workspace, log = fake_spack(tmp_path, " install ")
    result = subprocess.run(
        [
            "scripts/spack-build",
            "--workspace",
            str(workspace),
            "--buildcache",
            "test=file:///example",
        ],
        env=env,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode != 0
    assert "buildcache push" not in log.read_text()
    report = load_yaml(workspace / "reports/buildcache-destinations.yaml")
    assert report["push_destinations"][0]["lanes_pushed"] == []


@pytest.mark.parametrize("reconcretize", [False, True])
def test_existing_lock_requires_explicit_reconcretization(
    tmp_path: Path, reconcretize: bool
) -> None:
    env, workspace, log = fake_spack(tmp_path, "never-fail")
    lock = workspace / "environments/gcc/core/spack.lock"
    lock.write_bytes(b"previous reviewed lock\n")
    command = ["scripts/spack-build", "--workspace", str(workspace), "--skip-push"]
    if reconcretize:
        command.append("--reconcretize")
    result = subprocess.run(command, env=env, capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr
    assert ("concretize --force" in log.read_text()) == reconcretize
    if not reconcretize:
        assert "concretize" not in log.read_text()
    assert lock.read_bytes() == b"previous reviewed lock\n"


@pytest.mark.parametrize("failure", [" concretize ", " fetch ", " install "])
def test_failed_stage_prevents_downstream_execution(tmp_path: Path, failure: str) -> None:
    env, workspace, log = fake_spack(tmp_path, failure)
    result = subprocess.run(
        ["scripts/spack-build", "--workspace", str(workspace), "--skip-push"],
        env=env, capture_output=True, text=True, timeout=10,
    )
    assert result.returncode != 0
    calls = log.read_text()
    assert "verify libraries" not in calls
    assert "module tcl refresh" not in calls
    if failure != " install ":
        assert " install " not in calls
    report = load_yaml(workspace / "reports/verify-results.yaml")
    assert report["verification"]["spack_verify_manifest"] == "skipped"


@pytest.mark.parametrize("kind", ["static", "full"])
def test_output_symlink_cannot_replace_its_target(tmp_path: Path, kind: str) -> None:
    destination = render(tmp_path / "out", kind=kind)
    saved = destination.with_name("saved-output")
    destination.rename(saved)
    destination.symlink_to(saved, target_is_directory=True)
    with pytest.raises(ValidationFailed):
        render(tmp_path / "out", kind=kind)
    assert destination.is_symlink()
    assert saved.is_dir()


@pytest.mark.parametrize("changed", ["values", "template", "data", "catalog"])
def test_initialized_manifest_fingerprints_consumed_inputs(tmp_path: Path, changed: str) -> None:
    blueprint, catalog, values = make_inputs(tmp_path / "inputs")
    data_file = blueprint / "extra.yaml"
    write_yaml(data_file, {"value": "old"})
    blueprint_data = load_yaml(blueprint / "blueprint.yaml")
    blueprint_data["data_files"]["extra"] = "extra.yaml"
    write_yaml(blueprint / "blueprint.yaml", blueprint_data)

    def initialize():
        return initialize_workspace(
            blueprint_dir=blueprint, catalog_dir=catalog, values_path=values,
            output_dir=tmp_path / "workspace", overwrite=True,
        )

    first = initialize()
    original = load_yaml(first / "workspace-manifest.yaml")["input_digests"]
    targets = {
        "values": values,
        "template": blueprint / "templates/spack.yaml.j2",
        "data": data_file,
        "catalog": catalog / "manifest.yaml",
    }
    target = targets[changed]
    target.write_text(target.read_text() + "\n# reviewed input change\n")
    second = initialize()
    updated = load_yaml(second / "workspace-manifest.yaml")["input_digests"]
    assert updated != original


def test_empty_rendered_environment_is_not_promoted(tmp_path: Path) -> None:
    templates = tmp_path / "templates"
    shutil.copytree(fixture_path("template-sets"), templates)
    template = templates / "v6/environments/core/spack.yaml.j2"
    template.write_text("spack:\n  specs: []\n")
    with pytest.raises(ValidationFailed) as failure:
        render(tmp_path / "out", kind="full", templates_root=templates)
    assert any(issue.code == "rendered-specs-empty" for issue in failure.value.issues)
    assert not (tmp_path / "out/example-linux/science-stack/audit").exists()


def test_package_repository_change_changes_manifest_provenance(tmp_path: Path) -> None:
    repositories = tmp_path / "package-repos"
    shutil.copytree(fixture_path("package-repos"), repositories)
    first = render(tmp_path / "out", kind="full", package_repos_dir=repositories)
    original = load_yaml(first / "release-manifest.yaml")["package_repositories"]
    (repositories / "science/review-note.txt").write_text("approved recipe update\n")
    second = render(tmp_path / "out", kind="full", package_repos_dir=repositories)
    updated = load_yaml(second / "release-manifest.yaml")["package_repositories"]
    assert updated != original


@pytest.mark.parametrize("field", ["repository", "module_namespace"])
def test_nested_output_identity_cannot_escape_workspace(tmp_path: Path, field: str) -> None:
    stack = load_yaml(fixture_path("stacks", "science-stack", "stack.yaml"))
    outside = tmp_path / "must-not-be-written"
    if field == "repository":
        stack["package_repositories"][0]["name"] = str(outside)
    else:
        stack["modules"] = {"module_root": str(outside)}
    stack_path = tmp_path / "stack.yaml"
    write_yaml(stack_path, stack)
    with pytest.raises(ValidationFailed):
        render(tmp_path / "out", kind="full", stack_path=stack_path)
    assert not outside.exists()


def test_failed_rollback_retains_and_reports_recovery_copy(tmp_path: Path, monkeypatch) -> None:
    destination = render(tmp_path / "out")
    (destination / "reviewed.lock").write_text("keep this evidence\n")
    real_replace = Path.replace
    real_rename = os.rename

    def fail_promotion(path, target):
        if Path(target) == destination:
            raise OSError("promotion failed")
        return real_replace(path, target)

    def fail_recovery(source, target, *args, **kwargs):
        if Path(target) == destination:
            raise OSError("recovery failed")
        return real_rename(source, target, *args, **kwargs)

    monkeypatch.setattr(Path, "replace", fail_promotion)
    monkeypatch.setattr(os, "rename", fail_recovery)
    with pytest.raises(ValidationFailed) as error:
        render(tmp_path / "out")
    retained = list(destination.parent.glob(".audit.previous-*/workspace/reviewed.lock"))
    assert len(retained) == 1
    assert retained[0].read_text() == "keep this evidence\n"
    assert str(retained[0].parent) in error.value.issues[0].message
    assert error.value.issues[0].code == "output-recovery"
