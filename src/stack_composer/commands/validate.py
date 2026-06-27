from __future__ import annotations

from pathlib import Path

import click

from stack_composer.errors import ValidationFailed
from stack_composer.validate.checks import validate_inputs
from stack_composer.validate.report import report_data, write_report
from stack_composer.yaml_io import dump_yaml


def run(
    *,
    profile: str,
    deployment: str | None,
    stack: str,
    templates: str,
    package_sets: str | None,
    package_repos: str | None,
    report: str | None,
) -> None:
    stack_path = Path(stack)
    stack_parent = stack_path.parent.parent if stack_path.parent.name else Path.cwd()
    package_sets_dir = Path(package_sets) if package_sets else stack_parent / "package-sets"
    package_repos_dir = Path(package_repos) if package_repos else stack_parent / "package-repos"
    issues, _ = validate_inputs(
        profile_path=Path(profile),
        stack_path=stack_path,
        deployment_path=Path(deployment) if deployment else None,
        templates_root=Path(templates),
        package_sets_dir=package_sets_dir,
        package_repos_dir=package_repos_dir,
    )
    if report:
        write_report(Path(report), issues)
    summary = report_data(issues)
    click.echo(dump_yaml(summary).rstrip())
    if any(issue.severity == "error" for issue in issues):
        raise ValidationFailed(issues)
