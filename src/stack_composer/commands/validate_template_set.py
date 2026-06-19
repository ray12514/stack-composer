from __future__ import annotations

from stack_composer.commands._stub import raise_not_implemented


def run(*, templates: str, profiles: tuple[str, ...], output: str, concretize: bool) -> None:
    _ = (templates, profiles, output, concretize)
    raise_not_implemented("validate-template-set")
