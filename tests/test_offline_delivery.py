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
