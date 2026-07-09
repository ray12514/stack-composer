from __future__ import annotations

from pathlib import Path

import click

from stack_composer.errors import ValidationFailed, format_issues
from stack_composer.render.release import ReleaseVars, SourceRepo
from stack_composer.render.static_catalog import render_static_catalog


def run(
    *,
    profile: str,
    templates: str,
    template_set_name: str,
    output_root: str,
    release: str,
    rendered_at: str,
    source_repo: str,
    source_commit: str,
    source_dirty: bool,
    overwrite: bool,
) -> None:
    try:
        workspace = render_static_catalog(
            profile_path=Path(profile),
            templates_root=Path(templates),
            template_set_name=template_set_name,
            release_vars=ReleaseVars(
                release_tag=release,
                output_root=output_root,
                rendered_at=rendered_at,
                source_repo=SourceRepo(source_repo, source_commit, source_dirty),
                overwrite=overwrite,
            ),
        )
    except ValidationFailed as exc:
        raise click.ClickException(format_issues(exc.issues)) from exc
    click.echo(str(workspace))
