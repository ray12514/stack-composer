from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tarfile
from pathlib import Path
from zipfile import ZipFile

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_release_archive_repeats_bytes_and_preserves_relative_links(tmp_path: Path) -> None:
    source = tmp_path / "tool"
    (source / "lib").mkdir(parents=True)
    (source / "lib/payload").write_bytes(b"reviewed library\n")
    (source / "run").write_bytes(b"#!/bin/sh\nexit 0\n")
    (source / "run").chmod(0o755)
    (source / "lib/current").symlink_to("payload")
    artifacts = [tmp_path / "first.tar.gz", tmp_path / "second.tar.gz"]
    for index, artifact in enumerate(artifacts):
        os.utime(source / "run", (1700000000 + index * 100, 1700000000 + index * 100))
        subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts/release_support.py"),
                "archive",
                str(source),
                str(artifact),
                "--epoch",
                "1700000000",
            ],
            check=True,
            capture_output=True,
            text=True,
        )
    assert artifacts[0].read_bytes() == artifacts[1].read_bytes()
    with tarfile.open(artifacts[0]) as archive:
        assert archive.getmember("tool/run").mode == 0o755
        link = archive.getmember("tool/lib/current")
        assert link.issym() and link.linkname == "payload"
        assert all(member.uid == 0 and member.gid == 0 for member in archive)


def test_delivery_verification_rejects_changed_and_unrecorded_inputs(tmp_path: Path) -> None:
    payload = tmp_path / "source.txt"
    payload.write_bytes(b"reviewed source\n")
    payload.chmod(0o644)
    (tmp_path / "RELEASE_INPUTS.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "files": {
                    "source.txt": {
                        "sha256": hashlib.sha256(payload.read_bytes()).hexdigest(),
                        "mode": 0o644,
                    }
                },
            }
        )
    )
    command = [sys.executable, str(ROOT / "scripts/offline_delivery.py"), "verify", str(tmp_path)]
    assert subprocess.run(command, capture_output=True).returncode == 0
    payload.write_bytes(b"changed source\n")
    assert subprocess.run(command, capture_output=True).returncode != 0
    payload.write_bytes(b"reviewed source\n")
    (tmp_path / "unexpected.whl").write_bytes(b"unapproved dependency")
    assert subprocess.run(command, capture_output=True).returncode != 0


@pytest.mark.parametrize("target", ["/etc/passwd", "../outside", "missing"])
def test_release_archive_rejects_unsafe_or_broken_links(tmp_path: Path, target: str) -> None:
    source = tmp_path / "tool"
    source.mkdir()
    (source / "link").symlink_to(target)
    artifact = tmp_path / "tool.tar.gz"
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/release_support.py"),
            "archive",
            str(source),
            str(artifact),
            "--epoch",
            "1700000000",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert not artifact.exists()


def test_wheel_lock_uses_distribution_metadata_not_vendored_metadata(tmp_path: Path) -> None:
    wheel = tmp_path / "example-1.0-py3-none-any.whl"
    with ZipFile(wheel, "w") as archive:
        archive.writestr("example-1.0.dist-info/METADATA", "Name: Example\nVersion: 1.0\n")
        archive.writestr(
            "example/vendor/other-2.0.dist-info/METADATA", "Name: Other\nVersion: 2.0\n"
        )
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/offline_delivery.py"),
            "wheel-lock",
            str(tmp_path),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    digest = hashlib.sha256(wheel.read_bytes()).hexdigest()
    assert result.stdout == f"example==1.0 --hash=sha256:{digest}\n"


def test_snapshot_excludes_dirty_files_and_seal_rejects_changed_source(tmp_path: Path) -> None:
    repos = []
    for name in ("composer", "content", "planning"):
        repo = tmp_path / name
        repo.mkdir()
        (repo / "scripts").mkdir()
        for script in ("offline_delivery.py", "rebuild-offline.sh"):
            (repo / "scripts" / script).write_text("reviewed\n")
        (repo / "CLAUDE.md").symlink_to("scripts/offline_delivery.py")
        for command in (
            ["init", "-q"],
            ["add", "scripts", "CLAUDE.md"],
            [
                "-c",
                "user.name=Test",
                "-c",
                "user.email=test@example.invalid",
                "commit",
                "-qm",
                "fixture",
            ],
        ):
            subprocess.run(["git", "-C", str(repo), *command], check=True, capture_output=True)
        (repo / "scripts/rebuild-offline.sh").write_text("uncommitted\n")
        (repo / "untracked-secret").write_text("must not export\n")
        repos.append(repo)
    capsule = tmp_path / "capsule"
    base = [sys.executable, str(ROOT / "scripts/offline_delivery.py")]
    subprocess.run(
        [
            *base,
            "snapshot",
            "--stack-composer",
            str(repos[0]),
            "--stack-content",
            str(repos[1]),
            "--stack-planning",
            str(repos[2]),
            "--output",
            str(capsule),
        ],
        check=True,
        capture_output=True,
    )
    exported = capsule / "sources/stack-composer/scripts/rebuild-offline.sh"
    assert exported.read_text() == "reviewed\n"
    assert not list(capsule.rglob("untracked-secret"))
    exported.write_text("changed after snapshot\n")
    result = subprocess.run(
        [
            *base,
            "seal",
            str(capsule),
            "--builder-image",
            "sha256:" + "0" * 64,
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "source export changed after snapshot" in result.stderr
    assert not (capsule / "RELEASE_INPUTS.json").exists()


def test_outer_archive_preserves_sealed_input_modes(tmp_path: Path) -> None:
    capsule = tmp_path / "inputs"
    capsule.mkdir()
    payload = capsule / "builder-image.tar"
    payload.write_bytes(b"saved builder image\n")
    payload.chmod(0o600)
    (capsule / "RELEASE_INPUTS.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "files": {
                    "builder-image.tar": {
                        "sha256": hashlib.sha256(payload.read_bytes()).hexdigest(),
                        "mode": 0o600,
                    }
                },
            }
        )
    )
    artifact = tmp_path / "delivery.tar.gz"
    subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/release_support.py"),
            "archive",
            str(capsule),
            str(artifact),
            "--epoch",
            "1700000000",
            "--preserve-modes",
        ],
        check=True,
        capture_output=True,
    )
    received = tmp_path / "received"
    received.mkdir()
    with tarfile.open(artifact) as archive:
        archive.extractall(received)
    subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/offline_delivery.py"),
            "verify",
            str(received / "inputs"),
        ],
        check=True,
        capture_output=True,
    )


def _deployment_inputs(tmp_path: Path) -> tuple[Path, Path]:
    inputs = tmp_path / "inputs"
    composer = inputs / "sources/stack-composer"
    (composer / "src/stack_composer").mkdir(parents=True)
    (composer / "src/stack_composer/__init__.py").write_text("version = 'tested'\n")
    (composer / "scripts").mkdir()
    (composer / "scripts/offline_delivery.py").write_bytes(
        (ROOT / "scripts/offline_delivery.py").read_bytes()
    )
    (composer / "docs").mkdir()
    (composer / "docs/cluster-delivery.md").write_text("Receive @VERSION@ in a new directory.\n")
    (composer / "scripts/spack-build").write_text("#!/bin/sh\nexit 0\n")
    (composer / "scripts/spack-build").chmod(0o755)
    for name in ("stack-content", "stack-planning"):
        (inputs / "sources" / name).mkdir()
        (inputs / "sources" / name / "README.md").write_text(name + "\n")
    (inputs / "wheels/pyz").mkdir(parents=True)
    (inputs / "wheels/pyz/dependency-1.0-py3-none-any.whl").write_bytes(b"reviewed dependency")
    (inputs / "locks").mkdir()
    (inputs / "locks/pyz.txt").write_text("reviewed hash lock\n")
    sources = {
        name: {"commit": str(index) * 40, "tree": str(index + 1) * 40}
        for index, name in enumerate(("stack-composer", "stack-content", "stack-planning"), 1)
    }
    sources["source_date_epoch"] = 1700000000
    files = {
        path.relative_to(inputs).as_posix(): {
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "mode": path.stat().st_mode & 0o777,
        }
        for path in inputs.rglob("*") if path.is_file()
    }
    (inputs / "RELEASE_INPUTS.json").write_text(
        json.dumps({"schema_version": 1, "sources": sources, "files": files})
    )
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    (artifacts / "RELEASE_INPUTS.json").write_bytes((inputs / "RELEASE_INPUTS.json").read_bytes())
    with ZipFile(artifacts / "stack-composer.pyz", "w") as archive:
        archive.write(
            composer / "src/stack_composer/__init__.py",
            "site-packages/stack_composer/__init__.py",
        )
    return inputs, artifacts


def test_versioned_delivery_is_reproducible_and_verifiable_after_extraction(tmp_path: Path) -> None:
    inputs, artifacts = _deployment_inputs(tmp_path)
    outputs = [tmp_path / "first", tmp_path / "second"]
    command = [sys.executable, str(ROOT / "scripts/offline_delivery.py")]
    version = "stack-tools-2026.09.19-test"
    for output in outputs:
        result = subprocess.run(
            [*command, "bundle", "--inputs", str(inputs), "--artifacts", str(artifacts),
             "--version", version, "--output", str(output)],
            capture_output=True, text=True,
        )
        assert result.returncode == 0, result.stderr
    assert (outputs[0] / f"{version}.tar.gz").read_bytes() == (
        outputs[1] / f"{version}.tar.gz"
    ).read_bytes()
    received = tmp_path / "received"
    received.mkdir()
    with tarfile.open(outputs[0] / f"{version}.tar.gz") as archive:
        archive.extractall(received)
    delivery = received / version
    result = subprocess.run(
        [sys.executable, str(delivery / "verify-delivery.py"), "verify-bundle", str(delivery)],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    manifest = json.loads((delivery / "DELIVERY.json").read_text())
    assert manifest["version"] == version
    assert manifest["sources"]["stack-content"]["commit"] == "2" * 40
    assert (delivery / "tools/spack-build").stat().st_mode & 0o111
    assert (delivery / "wheels/dependency-1.0-py3-none-any.whl").is_file()
    assert not (delivery / "builder-image.tar").exists()
    assert not list(delivery.rglob("spack.lock"))


@pytest.mark.parametrize("change", ["modified", "missing", "unrecorded", "mode"])
def test_delivery_verifier_refuses_changed_receiver_payload(tmp_path: Path, change: str) -> None:
    inputs, artifacts = _deployment_inputs(tmp_path)
    output = tmp_path / "delivery"
    command = [sys.executable, str(ROOT / "scripts/offline_delivery.py")]
    subprocess.run(
        [*command, "bundle", "--inputs", str(inputs), "--artifacts", str(artifacts),
         "--version", "trial-update", "--output", str(output)],
        check=True, capture_output=True,
    )
    root = output / "trial-update"
    target = root / "tools/spack-build"
    if change == "modified":
        target.write_text("unexpected helper\n")
    elif change == "missing":
        target.unlink()
    elif change == "mode":
        target.chmod(0o644)
    else:
        (root / "unrecorded-script").write_text("unexpected\n")
    result = subprocess.run(
        [sys.executable, str(root / "verify-delivery.py"), "verify-bundle", str(root)],
        capture_output=True, text=True,
    )
    assert result.returncode != 0
    assert "delivery differs" in result.stderr


@pytest.mark.parametrize("change", ["application", "provenance"])
def test_bundle_refuses_artifacts_from_another_source_checkpoint(
    tmp_path: Path, change: str,
) -> None:
    inputs, artifacts = _deployment_inputs(tmp_path)
    if change == "provenance":
        (artifacts / "RELEASE_INPUTS.json").write_text("another capsule\n")
    else:
        with ZipFile(artifacts / "stack-composer.pyz", "w") as archive:
            archive.writestr("site-packages/stack_composer/__init__.py", "stale code\n")
    output = tmp_path / "delivery"
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts/offline_delivery.py"), "bundle",
         "--inputs", str(inputs), "--artifacts", str(artifacts),
         "--version", "trial-update", "--output", str(output)],
        capture_output=True, text=True,
    )
    assert result.returncode != 0
    assert not output.exists()


def test_bundle_refuses_to_replace_an_existing_delivery(tmp_path: Path) -> None:
    inputs, artifacts = _deployment_inputs(tmp_path)
    output = tmp_path / "delivery"
    output.mkdir()
    (output / "retained").write_text("earlier release\n")
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts/offline_delivery.py"), "bundle",
         "--inputs", str(inputs), "--artifacts", str(artifacts),
         "--version", "trial-update", "--output", str(output)],
        capture_output=True, text=True,
    )
    assert result.returncode != 0
    assert (output / "retained").read_text() == "earlier release\n"
    assert len(list(output.iterdir())) == 1


@pytest.mark.parametrize("parent", ["inputs", "artifacts"])
def test_bundle_keeps_sealed_inputs_and_build_outputs_unchanged(
    tmp_path: Path, parent: str,
) -> None:
    inputs, artifacts = _deployment_inputs(tmp_path)
    output = {"inputs": inputs, "artifacts": artifacts}[parent] / "receiver"
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts/offline_delivery.py"), "bundle",
         "--inputs", str(inputs), "--artifacts", str(artifacts),
         "--version", "trial-update", "--output", str(output)],
        capture_output=True, text=True,
    )
    assert result.returncode != 0
    assert not output.exists()


def test_bundle_runs_from_sealed_source_export_without_creating_bytecode(tmp_path: Path) -> None:
    inputs, artifacts = _deployment_inputs(tmp_path)
    source_script = inputs / "sources/stack-composer/scripts/offline_delivery.py"
    support = source_script.with_name("release_support.py")
    support.write_bytes((ROOT / "scripts/release_support.py").read_bytes())
    manifest = json.loads((inputs / "RELEASE_INPUTS.json").read_text())
    manifest["files"][support.relative_to(inputs).as_posix()] = {
        "sha256": hashlib.sha256(support.read_bytes()).hexdigest(),
        "mode": support.stat().st_mode & 0o777,
    }
    (inputs / "RELEASE_INPUTS.json").write_text(json.dumps(manifest))
    (artifacts / "RELEASE_INPUTS.json").write_bytes((inputs / "RELEASE_INPUTS.json").read_bytes())
    result = subprocess.run(
        [sys.executable, str(source_script), "bundle", "--inputs", str(inputs),
         "--artifacts", str(artifacts), "--version", "trial-update",
         "--output", str(tmp_path / "receiver")],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    assert not list(inputs.rglob("*.pyc"))
