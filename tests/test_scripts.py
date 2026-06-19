from __future__ import annotations

import subprocess
import sys


def test_generate_third_party_check_passes() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/generate-third-party.py", "--check"],
        check=False,
        text=True,
        capture_output=True,
    )
    assert result.returncode == 0, result.stderr
    assert "third-party manifest check passed" in result.stdout
