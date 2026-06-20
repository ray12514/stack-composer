from __future__ import annotations

from click.testing import CliRunner

from stack_composer.cli import cli
from tests.conftest import fixture_path


def test_help_lists_commands() -> None:
    result = CliRunner().invoke(cli, ["--help"])
    assert result.exit_code == 0
    assert "render" in result.output
    assert "publish-manifest" in result.output


def test_licenses_flag_prints_manifest() -> None:
    result = CliRunner().invoke(cli, ["--licenses"])
    assert result.exit_code == 0
    assert "stack-composer" in result.output
    assert "PyYAML" in result.output


def test_validate_command_passes_reference_fixture() -> None:
    result = CliRunner().invoke(
        cli,
        [
            "validate",
            "--profile",
            str(fixture_path("profiles", "example-cray", "profile.yaml")),
            "--stack",
            str(fixture_path("stacks", "science-stack", "stack.yaml")),
            "--templates",
            str(fixture_path("template-sets")),
            "--package-sets",
            str(fixture_path("package-sets")),
            "--package-repos",
            str(fixture_path("package-repos")),
        ],
    )
    assert result.exit_code == 0, result.output
    assert "valid: true" in result.output


def test_render_command_writes_workspace(tmp_path) -> None:
    result = CliRunner().invoke(
        cli,
        [
            "render",
            "--profile",
            str(fixture_path("profiles", "example-cray", "profile.yaml")),
            "--stack",
            str(fixture_path("stacks", "science-stack", "stack.yaml")),
            "--templates",
            str(fixture_path("template-sets")),
            "--package-sets",
            str(fixture_path("package-sets")),
            "--package-repos",
            str(fixture_path("package-repos")),
            "--output-root",
            str(tmp_path),
            "--release",
            "2026.06",
            "--rendered-at",
            "2026-06-19T00:00:00Z",
            "--source-repo",
            "git@example:stacks/science-stack",
            "--source-commit",
            "0375b16fdeadbeef0123456789abcdef01234567",
        ],
    )
    assert result.exit_code == 0, result.output
    workspace = tmp_path / "example-cray" / "science-stack" / "2026.06"
    assert workspace.as_posix() in result.output
    assert (workspace / "release-manifest.yaml").exists()


def test_stub_command_returns_clear_error() -> None:
    result = CliRunner().invoke(
        cli,
        [
            "scaffold-templates",
            "--profile", "profile.yaml",
            "--output", "out",
        ],
    )
    assert result.exit_code != 0
    assert "not yet implemented" in result.output
