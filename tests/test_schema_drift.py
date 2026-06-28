"""Drift guard for the shared JSON schemas.

The schemas are one cross-repo contract with multiple physical copies: canonical
in ``stack-planning/schemas`` (the source of truth), bundled here so the pyz is
self-contained, and embedded in cluster-inspector's binary. The bundled copies
must stay byte-identical to canonical — this test fails the moment they drift, so
a schema edit can't land in one copy and not the other.

Canonical is located via ``STACK_PLANNING`` (the same env var cluster-inspector's
Makefile uses), else a sibling checkout. The test skips when stack-planning is
not present rather than failing in a stack-composer-only checkout.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

_BUNDLED = Path(__file__).resolve().parents[1] / "src" / "stack_composer" / "schemas"


def _canonical_schemas() -> Path | None:
    override = os.environ.get("STACK_PLANNING")
    root = Path(override) if override else Path(__file__).resolve().parents[2] / "stack-planning"
    schemas = root / "schemas"
    return schemas if schemas.is_dir() else None


def test_bundled_schemas_match_canonical() -> None:
    canonical = _canonical_schemas()
    if canonical is None:
        pytest.skip(
            "stack-planning not found; set STACK_PLANNING or check it out as a "
            "sibling of stack-composer to enable the schema drift guard"
        )

    drifted: list[str] = []
    for bundled in sorted(_BUNDLED.glob("*.json")):
        twin = canonical / bundled.name
        if not twin.exists():
            drifted.append(f"{bundled.name} (absent from canonical)")
        elif bundled.read_bytes() != twin.read_bytes():
            drifted.append(bundled.name)

    assert not drifted, (
        "bundled schemas drifted from canonical stack-planning/schemas; "
        f"re-sync these: {drifted}"
    )
