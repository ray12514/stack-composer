from __future__ import annotations

from pathlib import Path

import click

from stack_composer.errors import ValidationFailed, format_issues
from stack_composer.workspace.initializer import initialize_workspace


def run(
    *,
    blueprint: str,
    catalog: str,
    values: str,
    output: str,
    overwrite: bool,
) -> None:
    try:
        workspace = initialize_workspace(
            blueprint_dir=Path(blueprint),
            catalog_dir=Path(catalog),
            values_path=Path(values),
            output_dir=Path(output),
            overwrite=overwrite,
        )
    except ValidationFailed as exc:
        raise click.ClickException(format_issues(exc.issues)) from exc
    click.echo(str(workspace))
