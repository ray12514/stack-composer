from __future__ import annotations

from stack_composer.commands._stub import raise_not_implemented


def run(*, profile: str, templates: str, output_format: str) -> None:
    _ = (profile, templates, output_format)
    raise_not_implemented("explain")
