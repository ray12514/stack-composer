#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
PYTHON=${PYTHON:-python3}

cd "${ROOT_DIR}"

# Refresh bundled schemas from canonical stack-planning when it's adjacent
# (best-effort; tests/test_schema_drift.py is the hard gate). Release builds
# without the sibling fall back to the already-bundled copies.
if [ -d "${STACK_PLANNING:-${ROOT_DIR}/../stack-planning}/schemas" ]; then
  scripts/sync-schema.sh
else
  echo "build-pyz: stack-planning not adjacent; using bundled schemas as-is" >&2
  echo "           (run scripts/sync-schema.sh to refresh from canonical)" >&2
fi

"${PYTHON}" scripts/generate-third-party.py --check --sync-resources

rm -rf \
  dist/build-pyz \
  dist/wheelhouse \
  dist/stack-composer.pyz \
  dist/stack-composer-* \
  dist/stack_composer-*.whl
mkdir -p dist/wheelhouse

"${PYTHON}" -m build --wheel --no-isolation
"${PYTHON}" -m pip wheel --no-deps --wheel-dir dist/wheelhouse dist/stack_composer-*.whl
"${PYTHON}" -m pip wheel --no-deps --only-binary=:all: --wheel-dir dist/wheelhouse \
  'click>=8.1,<8.2' \
  'fastjsonschema>=2.20,<3' \
  'Jinja2>=3.1,<4'
CC=/usr/bin/false "${PYTHON}" -m pip wheel \
  --no-cache-dir \
  --no-deps \
  --no-binary=MarkupSafe \
  --wheel-dir dist/wheelhouse \
  'MarkupSafe>=2.1,<3'
PYYAML_FORCE_LIBYAML=0 "${PYTHON}" -m pip wheel \
  --no-cache-dir \
  --no-deps \
  --no-binary=PyYAML \
  --wheel-dir dist/wheelhouse \
  'PyYAML>=6.0,<7'
"${PYTHON}" - <<'PY'
from pathlib import Path

bad = []
for wheel in sorted(Path("dist/wheelhouse").glob("*.whl")):
    parts = wheel.name.removesuffix(".whl").split("-")
    python_tag, abi_tag, platform_tag = parts[-3:]
    if "py3" not in python_tag or abi_tag != "none" or platform_tag != "any":
        bad.append(wheel.name)
if bad:
    raise SystemExit("platform-specific wheels are not allowed in pyz wheelhouse: " + ", ".join(bad))
PY

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
cp scripts/spack-build "${RELEASE_DIR}/spack-build"
cp README.md LICENSE THIRD_PARTY.toml "${RELEASE_DIR}/"
cp -R THIRD_PARTY_LICENSES "${RELEASE_DIR}/THIRD_PARTY_LICENSES"

cat > "${RELEASE_DIR}/README" <<'EOF'
Run with:
  ./stack-composer.pyz --help

No pip install is required on the target. Python 3.9+ is required.
EOF

tar -C dist -czf "dist/stack-composer-${VERSION}.tar.gz" "stack-composer-${VERSION}"
echo "dist/stack-composer-${VERSION}.tar.gz"
