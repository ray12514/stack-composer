"""Drift guard for the shared v6 template set.

stack-composer vendors a copy of the v6 template set under
``tests/fixtures/template-sets/v6`` so its render/validate tests stay
self-contained. The authoritative copy lives in the ``stack-content`` repo at
``templates/v6``. Those are two adapters at one seam: the deliberate trade is a
local copy for test independence, paid for by this contract test that fails the
moment the two diverge.

When this test fails, re-sync the two trees (copy whichever side is correct) so
the fixture keeps exercising the templates render actually ships.

stack-content is located via ``STACK_CONTENT_DIR`` if set, else the default dev
layout (a sibling checkout of stack-composer). The test skips when neither is
present rather than failing in environments that only check out stack-composer.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

_FIXTURE_V6 = Path(__file__).parent / "fixtures" / "template-sets" / "v6"


def _stack_content_v6() -> Path | None:
    override = os.environ.get("STACK_CONTENT_DIR")
    if override:
        candidate = Path(override) / "templates" / "v6"
        return candidate if candidate.is_dir() else None
    sibling = Path(__file__).resolve().parents[2] / "stack-content" / "templates" / "v6"
    return sibling if sibling.is_dir() else None


def _relative_files(root: Path) -> set[str]:
    return {p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()}


def test_fixture_v6_matches_stack_content() -> None:
    content_v6 = _stack_content_v6()
    if content_v6 is None:
        pytest.skip(
            "stack-content not found; set STACK_CONTENT_DIR or check it out as a "
            "sibling of stack-composer to enable the template-set drift guard"
        )

    fixture_files = _relative_files(_FIXTURE_V6)
    content_files = _relative_files(content_v6)
    assert fixture_files == content_files, (
        "v6 template-set file lists differ between the stack-composer fixture and "
        f"stack-content.\n  only in fixture: {sorted(fixture_files - content_files)}\n"
        f"  only in stack-content: {sorted(content_files - fixture_files)}"
    )

    drifted = [
        rel
        for rel in sorted(fixture_files)
        if (_FIXTURE_V6 / rel).read_bytes() != (content_v6 / rel).read_bytes()
    ]
    assert not drifted, (
        "v6 template set drifted between the stack-composer fixture and "
        f"stack-content; re-sync these files: {drifted}"
    )
