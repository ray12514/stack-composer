from __future__ import annotations

from pathlib import Path

import click

from stack_composer.errors import ValidationFailed
from stack_composer.render.engine import render_workspace
from stack_composer.render.release import ReleaseVars, SourceRepo


def run(
    *,
    profile: str,
    deployment: str,
    stack: str,
    templates: str,
    output_root: str,
    release: str,
    rendered_at: str,
    source_repo: str,
    source_commit: str,
    source_dirty: bool,
    overwrite: bool,
    package_sets: str | None,
    package_repos: str | None,
) -> None:
    stack_path = Path(stack)
    stack_parent = stack_path.parent.parent if stack_path.parent.name else Path.cwd()
    package_sets_dir = Path(package_sets) if package_sets else stack_parent / "package-sets"
    package_repos_dir = Path(package_repos) if package_repos else stack_parent / "package-repos"
    try:
        workspace = render_workspace(
            profile_path=Path(profile),
            stack_path=stack_path,
            deployment_path=Path(deployment),
            templates_root=Path(templates),
            release_vars=ReleaseVars(
                release_tag=release,
                output_root=output_root,
                rendered_at=rendered_at,
                source_repo=SourceRepo(source_repo, source_commit, source_dirty),
                overwrite=overwrite,
            ),
            package_sets_dir=package_sets_dir,
            package_repos_dir=package_repos_dir,
        )
    except ValidationFailed as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(str(workspace))
