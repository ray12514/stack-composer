from __future__ import annotations

from pathlib import Path

import click
import pytest

from stack_composer.commands import scaffold_templates
from stack_composer.schema_registry import validate_schema
from stack_composer.yaml_io import load_yaml
from tests.conftest import fixture_path


def test_scaffold_templates_copies_seed_and_writes_review(tmp_path: Path) -> None:
    output = tmp_path / "proposed"

    scaffold_templates.run(
        profile=str(fixture_path("profiles", "example-cray", "profile.yaml")),
        seed=str(fixture_path("template-sets", "v6")),
        output=str(output),
        stack_kind="library",
    )

    assert (output / "contract.yaml").exists()
    assert (output / "stack-defaults.yaml").exists()
    assert (output / "configs" / "common" / "packages.yaml.j2").exists()
    assert (output / "environments" / "gpu" / "spack.yaml.j2").exists()
    assert "example-cray" in (output / "REVIEW.md").read_text(encoding="utf-8")
    assert "gfx90a" in (output / "REVIEW.md").read_text(encoding="utf-8")
    assert_all_files_have_todo(output)
    assert validate_schema(
        "template-contract", load_yaml(output / "contract.yaml"), "contract"
    ) == []
    assert validate_schema(
        "stack-defaults", load_yaml(output / "stack-defaults.yaml"), "defaults"
    ) == []


@pytest.mark.parametrize("stack_kind", ["library", "application"])
def test_scaffold_templates_uses_bundled_starters(tmp_path: Path, stack_kind: str) -> None:
    output = tmp_path / stack_kind

    scaffold_templates.run(
        profile=str(fixture_path("profiles", "example-linux", "profile.yaml")),
        seed=None,
        output=str(output),
        stack_kind=stack_kind,
    )

    assert (output / "contract.yaml").exists()
    assert (output / "stack-defaults.yaml").exists()
    assert (output / "REVIEW.md").exists()
    assert (output / "configs" / "vendor" / "cray" / "packages.yaml.j2").exists()
    assert (output / "configs" / "vendor" / "linux" / "packages.yaml.j2").exists()
    assert (output / "configs" / "mpi" / "cray-mpich" / "packages.yaml.j2").exists()
    assert (output / "configs" / "mpi" / "openmpi" / "packages.yaml.j2").exists()
    assert (output / "configs" / "gpu" / "amd-rocm" / "packages.yaml.j2").exists()
    assert (output / "configs" / "gpu" / "nvidia-cuda" / "packages.yaml.j2").exists()
    assert (output / "configs" / "target" / "zen3" / "packages.yaml.j2").exists()
    assert (output / "configs" / "target" / "zen4" / "packages.yaml.j2").exists()
    assert (output / "configs" / "target" / "x86_64_v3" / "packages.yaml.j2").exists()
    assert (output / "configs" / "os" / "rhel8" / "packages.yaml.j2").exists()
    assert (output / "configs" / "os" / "rhel9" / "packages.yaml.j2").exists()
    assert_all_files_have_todo(output)
    assert validate_schema(
        "template-contract", load_yaml(output / "contract.yaml"), "contract"
    ) == []
    assert validate_schema(
        "stack-defaults", load_yaml(output / "stack-defaults.yaml"), "defaults"
    ) == []


def test_scaffold_templates_rejects_nonempty_output(tmp_path: Path) -> None:
    output = tmp_path / "proposed"
    output.mkdir()
    (output / "existing.txt").write_text("keep\n", encoding="utf-8")

    with pytest.raises(click.ClickException) as excinfo:
        scaffold_templates.run(
            profile=str(fixture_path("profiles", "example-cray", "profile.yaml")),
            seed=str(fixture_path("template-sets", "v6")),
            output=str(output),
            stack_kind="library",
        )

    assert "must not contain existing files" in str(excinfo.value)
    assert (output / "existing.txt").read_text(encoding="utf-8") == "keep\n"


def test_scaffold_templates_is_deterministic(tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    kwargs = {
        "profile": str(fixture_path("profiles", "example-linux", "profile.yaml")),
        "seed": None,
        "stack_kind": "library",
    }

    scaffold_templates.run(output=str(first), **kwargs)
    scaffold_templates.run(output=str(second), **kwargs)

    assert tree_text(first) == tree_text(second)


def assert_all_files_have_todo(output: Path) -> None:
    for path in sorted(p for p in output.rglob("*") if p.is_file()):
        assert "TODO" in path.read_text(encoding="utf-8"), path


def tree_text(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): path.read_text(encoding="utf-8")
        for path in sorted(p for p in root.rglob("*") if p.is_file())
    }
