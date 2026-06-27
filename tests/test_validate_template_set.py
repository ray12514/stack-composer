from __future__ import annotations

import io
import shutil
from pathlib import Path

import click
import pytest
import yaml

from stack_composer.commands import validate_template_set
from tests.conftest import fixture_path


def _kwargs(output: Path, **overrides) -> dict:
    base = {
        "templates": str(fixture_path("template-sets", "v6")),
        "profiles": (
            str(fixture_path("profiles", "example-cray", "profile.yaml")),
            str(fixture_path("profiles", "example-linux", "profile.yaml")),
        ),
        "smoke_stack": str(fixture_path("stacks", "science-stack", "stack.yaml")),
        "package_sets_dir": str(fixture_path("package-sets")),
        "package_repos_dir": str(fixture_path("package-repos")),
        "output": str(output),
        "concretize": False,
    }
    base.update(overrides)
    return base


def test_validate_template_set_renders_every_profile_and_writes_reports(tmp_path: Path) -> None:
    err = io.StringIO()
    validate_template_set.run(stream=err, **_kwargs(tmp_path / "reports"))

    summary = yaml.safe_load((tmp_path / "reports" / "summary.yaml").read_text(encoding="utf-8"))
    assert [entry["profile"] for entry in summary["results"]] == ["example-cray", "example-linux"]
    for entry in summary["results"]:
        assert entry["render"] == "ok"
        report = yaml.safe_load(
            (tmp_path / "reports" / entry["profile"] / "result.yaml").read_text(encoding="utf-8")
        )
        assert report["render"] == "ok"
        assert Path(report["workspace"]).exists()

    assert "2/2 profiles ok" in err.getvalue()


def test_validate_template_set_records_render_failure_and_exits_nonzero(tmp_path: Path) -> None:
    bad_templates = tmp_path / "bad-templates" / "v6"
    bad_templates.mkdir(parents=True)
    src = Path(fixture_path("template-sets", "v6"))
    for child in src.iterdir():
        if child.is_dir():
            shutil.copytree(child, bad_templates / child.name)
        else:
            shutil.copy2(child, bad_templates / child.name)
    broken = bad_templates / "environments" / "cpu" / "spack.yaml.j2"
    broken.write_text("{{ missing_context_key }}\n", encoding="utf-8")

    err = io.StringIO()
    with pytest.raises(click.ClickException):
        validate_template_set.run(
            stream=err,
            **_kwargs(tmp_path / "reports", templates=str(bad_templates)),
        )
    summary = yaml.safe_load((tmp_path / "reports" / "summary.yaml").read_text(encoding="utf-8"))
    assert any(entry["render"] == "fail" for entry in summary["results"])
    assert "FAIL" in err.getvalue()


def test_validate_template_set_concretize_flag_is_not_implemented(tmp_path: Path) -> None:
    with pytest.raises(click.ClickException) as excinfo:
        validate_template_set.run(**_kwargs(tmp_path / "out", concretize=True))
    assert "concretize" in str(excinfo.value).lower()


def test_validate_template_set_rejects_templates_dir_without_defaults(tmp_path: Path) -> None:
    empty_templates = tmp_path / "empty"
    empty_templates.mkdir()
    with pytest.raises(click.ClickException) as excinfo:
        validate_template_set.run(**_kwargs(tmp_path / "out", templates=str(empty_templates)))
    assert "defaults.yaml" in str(excinfo.value)


def test_validate_template_set_is_deterministic(tmp_path: Path) -> None:
    output_a = tmp_path / "a"
    output_b = tmp_path / "b"
    validate_template_set.run(stream=io.StringIO(), **_kwargs(output_a))
    validate_template_set.run(stream=io.StringIO(), **_kwargs(output_b))
    summary_a = (output_a / "summary.yaml").read_text(encoding="utf-8")
    summary_b = (output_b / "summary.yaml").read_text(encoding="utf-8")
    # Workspace paths differ by output dir; strip them before comparison.
    cleaned_a = "\n".join(line for line in summary_a.splitlines() if "workspace" not in line)
    cleaned_b = "\n".join(line for line in summary_b.splitlines() if "workspace" not in line)
    assert cleaned_a == cleaned_b
