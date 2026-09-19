from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest


def test_generate_third_party_check_passes() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/generate-third-party.py", "--check"],
        check=False,
        text=True,
        capture_output=True,
    )
    assert result.returncode == 0, result.stderr
    assert "third-party manifest check passed" in result.stdout


@pytest.mark.parametrize(
    ("group", "expected"),
    [
        ("pyz-binary", "click==8.1.8\nfastjsonschema==2.21.2\njinja2==3.1.6\n"),
        ("pyz-source", "markupsafe==2.1.5\npyyaml==6.0.3\n"),
        (
            "all",
            "click==8.1.8\nfastjsonschema==2.21.2\njinja2==3.1.6\n"
            "markupsafe==2.1.5\npyyaml==6.0.3\n",
        ),
    ],
)
def test_release_requirements_use_exact_runtime_pins(group: str, expected: str) -> None:
    result = subprocess.run(
        [sys.executable, "-S", "scripts/generate-third-party.py", "--requirements", group],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == expected


def test_acquisition_reads_changed_pins_without_installed_dependencies(tmp_path: Path) -> None:
    project = tmp_path / "pyproject.toml"
    project.write_text('[project]\ndependencies = [\n  "Example==2.4.0",\n]\n')
    command = [
        sys.executable, "-S", "scripts/generate-third-party.py", "--requirements", "all",
        "--pyproject", str(project),
    ]
    result = subprocess.run(command, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert result.stdout == "example==2.4.0\n"
    project.write_text('[project]\ndependencies = [\n  "Example>=2.4.0",\n]\n')
    result = subprocess.run(command, capture_output=True, text=True)
    assert result.returncode != 0
    assert "exact version pin" in result.stderr
    assert result.stdout == ""
