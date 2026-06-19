from __future__ import annotations

from importlib import resources

import click

from stack_composer import __version__


def print_licenses() -> None:
    manifest = resources.files("stack_composer.resources").joinpath("THIRD_PARTY.toml")
    click.echo(f"stack-composer {__version__}")
    click.echo("Apache-2.0")
    click.echo()
    click.echo(manifest.read_text(encoding="utf-8").rstrip())
