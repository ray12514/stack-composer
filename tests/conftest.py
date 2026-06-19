from __future__ import annotations

from pathlib import Path


def fixture_path(*parts: str) -> Path:
    return Path(__file__).parent / "fixtures" / Path(*parts)
