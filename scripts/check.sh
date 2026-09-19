#!/usr/bin/env bash
# Source checks with test-owned temporary workspaces. No deployment is performed.
set -euo pipefail
ROOT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
PYTHON=${PYTHON:-"$ROOT_DIR/.venv/bin/python"}
PYTHON=$("$PYTHON" -c 'import sys; print(sys.executable)')
cd "$ROOT_DIR"
export PYTHONPATH="$ROOT_DIR/src" PYTHONNOUSERSITE=1
"$PYTHON" scripts/generate-third-party.py --check
"$PYTHON" -m mypy
"$PYTHON" -m ruff check src tests scripts/generate-third-party.py
for script in scripts/check.sh scripts/build-pyz.sh scripts/acquire-offline-wheels.sh; do
  bash -n "$script"
done
"$PYTHON" -m pytest tests/ -q
git diff --check
