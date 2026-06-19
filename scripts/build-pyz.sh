#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
PYTHON=${PYTHON:-python3}

cd "${ROOT_DIR}"

"${PYTHON}" scripts/generate-third-party.py --check --sync-resources

rm -rf \
  dist/build-pyz \
  dist/wheelhouse \
  dist/stack-composer.pyz \
  dist/stack-composer-* \
  dist/stack_composer-*.whl
mkdir -p dist/wheelhouse

"${PYTHON}" -m build --wheel --no-isolation
"${PYTHON}" -m pip wheel --wheel-dir dist/wheelhouse dist/stack_composer-*.whl

VERSION=$("${PYTHON}" - <<'PY'
from pathlib import Path

for line in Path("pyproject.toml").read_text(encoding="utf-8").splitlines():
    if line.startswith("version = "):
        print(line.split("=", 1)[1].strip().strip('"'))
        break
else:
    raise SystemExit("version not found in pyproject.toml")
PY
)

"${PYTHON}" -m shiv \
  --reproducible \
  -c stack-composer \
  -p '/usr/bin/env python3' \
  -o dist/stack-composer.pyz \
  --no-index \
  --find-links dist/wheelhouse \
  "stack-composer==${VERSION}"

RELEASE_DIR="dist/stack-composer-${VERSION}"
rm -rf "${RELEASE_DIR}"
mkdir -p "${RELEASE_DIR}"
cp dist/stack-composer.pyz "${RELEASE_DIR}/stack-composer.pyz"
cp README.md LICENSE THIRD_PARTY.toml "${RELEASE_DIR}/"
cp -R THIRD_PARTY_LICENSES "${RELEASE_DIR}/THIRD_PARTY_LICENSES"

cat > "${RELEASE_DIR}/README" <<'EOF'
Run with:
  ./stack-composer.pyz --help

No pip install is required on the target. Python 3.9+ is required.
EOF

tar -C dist -czf "dist/stack-composer-${VERSION}.tar.gz" "stack-composer-${VERSION}"
echo "dist/stack-composer-${VERSION}.tar.gz"
