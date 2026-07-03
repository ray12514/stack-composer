from __future__ import annotations

import re


def version_key(version: object) -> tuple[tuple[int, str], ...]:
    """Natural-ish key for discovered package/provider versions.

    This is intentionally small. It is for choosing among already-discovered
    platform facts, not for implementing Spack's full version semantics.
    """
    parts: list[tuple[int, str]] = []
    for token in re.findall(r"\d+|[A-Za-z]+", str(version)):
        if token.isdigit():
            parts.append((1, f"{int(token):012d}"))
        else:
            parts.append((0, token.lower()))
    return tuple(parts)
