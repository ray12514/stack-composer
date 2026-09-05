from __future__ import annotations

import importlib.util
from pathlib import Path
from zipfile import ZipFile

import pytest


def support():
    path = Path(__file__).resolve().parents[1] / "scripts/release_support.py"
    spec = importlib.util.spec_from_file_location("release_support", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_release_stage_ignores_old_setuptools_output(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    stage = tmp_path / "source"
    support().stage_project(root, stage)
    assert not (stage / "build").exists()
    assert not (stage / "dist").exists()
    assert not list(stage.rglob("*.pyc"))
    assert support().package_inventory(root) == support().package_inventory(stage)


@pytest.mark.parametrize("prefix", ["", "site-packages/"])
def test_artifact_inventory_rejects_stale_or_missing_files(tmp_path: Path, prefix: str) -> None:
    root = tmp_path / "source"
    package = root / "src/stack_composer"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("version = 'test'\n")
    artifact = tmp_path / "artifact.zip"
    with ZipFile(artifact, "w") as archive:
        archive.writestr(prefix + "stack_composer/__init__.py", "version = 'test'\n")
    support().verify_archive(root, artifact)
    with ZipFile(artifact, "a") as archive:
        archive.writestr(prefix + "stack_composer/obsolete.py", "old code\n")
    with pytest.raises(ValueError, match="obsolete.py"):
        support().verify_archive(root, artifact)
    (package / "new.py").write_text("new code\n")
    with pytest.raises(ValueError, match="new.py"):
        support().verify_archive(root, artifact)
