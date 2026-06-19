from __future__ import annotations

from pathlib import Path

from stack_composer.errors import Issue
from stack_composer.yaml_io import write_yaml


def issue_to_dict(issue: Issue) -> dict[str, str]:
    return {
        "severity": issue.severity,
        "code": issue.code,
        "path": issue.path,
        "message": issue.message,
    }


def report_data(issues: list[Issue]) -> dict:
    return {
        "valid": not any(issue.severity == "error" for issue in issues),
        "issues": [issue_to_dict(issue) for issue in issues],
    }


def write_report(path: Path, issues: list[Issue]) -> None:
    write_yaml(path, report_data(issues))
