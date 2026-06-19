from __future__ import annotations

from stack_composer.commands._stub import raise_not_implemented


def run(*, profile: str, seed: str | None, output: str, stack_kind: str) -> None:
    _ = (profile, seed, output, stack_kind)
    raise_not_implemented("scaffold-templates")
