from __future__ import annotations

import click

from stack_composer.errors import NotImplementedCommand


def raise_not_implemented(command: str) -> None:
    raise NotImplementedCommand(f"stack-composer {command} is not yet implemented")


def command_error_handler(func):
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except NotImplementedCommand as exc:
            raise click.ClickException(str(exc)) from exc

    return wrapper
