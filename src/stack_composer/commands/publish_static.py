from __future__ import annotations

from pathlib import Path

import click

from stack_composer.errors import ValidationFailed, format_issues
from stack_composer.publish.static_catalog import publish_static_catalog


def run(
    *,
    catalog: str,
    output_root: str,
    published_at: str,
    reviewed_by: str,
    approved_by: str,
    publication_group: str | None,
    set_current: bool,
) -> None:
    try:
        destination = publish_static_catalog(
            catalog_dir=Path(catalog),
            output_root=Path(output_root),
            published_at=published_at,
            reviewed_by=reviewed_by,
            approved_by=approved_by,
            publication_group=publication_group,
            set_current=set_current,
        )
    except ValidationFailed as exc:
        raise click.ClickException(format_issues(exc.issues)) from exc
    click.echo(str(destination))
