from __future__ import annotations

from stack_composer.commands._stub import raise_not_implemented


def run(*, profiles: tuple[str, ...], templates: str, output: str | None) -> None:
    _ = (profiles, templates, output)
    raise_not_implemented("assess-profiles")
