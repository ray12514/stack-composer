#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
PYTHON=${PYTHON:-python3}
PYTHON=$("$PYTHON" -c 'import sys; print(sys.executable)')
export SOURCE_DATE_EPOCH=${SOURCE_DATE_EPOCH:-315532800} PYTHONHASHSEED=0 TZ=UTC LC_ALL=C

if [[ -n ${STACK_COMPOSER_WHEELHOUSE:-} || -n ${STACK_COMPOSER_WHEEL_LOCK:-} ]]; then
  [[ -d ${STACK_COMPOSER_WHEELHOUSE:-} && -f ${STACK_COMPOSER_WHEEL_LOCK:-} ]] || {
    echo 'Offline pyz builds require STACK_COMPOSER_WHEELHOUSE and STACK_COMPOSER_WHEEL_LOCK.' >&2
    exit 2
  }
fi

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

STAGE=$(mktemp -d "${TMPDIR:-/tmp}/stack-composer-release.XXXXXX")
trap 'rm -rf "$STAGE"' EXIT
mkdir -p "$ROOT_DIR/dist"
mkdir "$ROOT_DIR/dist/.build-pyz.running" 2>/dev/null || {
  echo 'build-pyz: another build owns dist/.build-pyz.running; it was not modified' >&2
  exit 1
}
trap 'rm -rf "$STAGE"; rmdir "$ROOT_DIR/dist/.build-pyz.running"' EXIT
"$PYTHON" "$ROOT_DIR/scripts/release_support.py" stage "$ROOT_DIR" "$STAGE/source"
# Build in a new source export. Persistent build/lib and egg-info can contain
# removed modules and must never feed the next wheel or executable.
cd "$STAGE/source"
mkdir -p dist/wheelhouse

"${PYTHON}" -m build --wheel --no-isolation
APP_WHEELS=(dist/stack_composer-*.whl)
[[ ${#APP_WHEELS[@]} -eq 1 && -f ${APP_WHEELS[0]} ]]
"$PYTHON" "$ROOT_DIR/scripts/release_support.py" verify "$STAGE/source" "${APP_WHEELS[0]}"
cp "${APP_WHEELS[0]}" dist/wheelhouse/
if [[ -n ${STACK_COMPOSER_WHEELHOUSE:-} ]]; then
  "${PYTHON}" -m pip download --no-cache-dir --no-index \
    --find-links "$STACK_COMPOSER_WHEELHOUSE" --require-hashes --only-binary=:all: \
    --dest dist/wheelhouse -r "$STACK_COMPOSER_WHEEL_LOCK"
else
"${PYTHON}" -m pip wheel --no-deps --only-binary=:all: --wheel-dir dist/wheelhouse \
  'click==8.1.8' \
  'fastjsonschema==2.21.2' \
  'Jinja2==3.1.6'
CC=/usr/bin/false "${PYTHON}" -m pip wheel \
  --no-cache-dir \
  --no-deps \
  --no-binary=MarkupSafe \
  --wheel-dir dist/wheelhouse \
  'MarkupSafe==2.1.5'
PYYAML_FORCE_LIBYAML=0 "${PYTHON}" -m pip wheel \
  --no-cache-dir \
  --no-deps \
  --no-binary=PyYAML \
  --wheel-dir dist/wheelhouse \
  'PyYAML==6.0.3'
fi
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
"$PYTHON" "$ROOT_DIR/scripts/release_support.py" verify "$STAGE/source" dist/stack-composer.pyz
SHIV_ROOT="$STAGE/smoke-cache" "$PYTHON" -S dist/stack-composer.pyz --help >/dev/null
SHIV_ROOT="$STAGE/smoke-cache" "$PYTHON" -S dist/stack-composer.pyz --licenses >/dev/null

RELEASE_DIR="dist/stack-composer-${VERSION}"
mkdir -p "${RELEASE_DIR}"
cp dist/stack-composer.pyz "${RELEASE_DIR}/stack-composer.pyz"
cp "$ROOT_DIR/scripts/spack-build" "${RELEASE_DIR}/spack-build"
cp README.md LICENSE THIRD_PARTY.toml "${RELEASE_DIR}/"
cp -R THIRD_PARTY_LICENSES "${RELEASE_DIR}/THIRD_PARTY_LICENSES"

cat > "${RELEASE_DIR}/README" <<'EOF'
Run with:
  ./stack-composer.pyz --help

No pip install is required on the target. Python 3.9+ is required.
EOF

"$PYTHON" "$ROOT_DIR/scripts/release_support.py" inventory "$STAGE/source" \
  > "$RELEASE_DIR/APPLICATION_FILES.json"
"$PYTHON" "$ROOT_DIR/scripts/release_support.py" checksums "$RELEASE_DIR"

"$PYTHON" "$ROOT_DIR/scripts/release_support.py" archive "$RELEASE_DIR" \
  "dist/stack-composer-${VERSION}.tar.gz" --epoch "$SOURCE_DATE_EPOCH"
# Replace only complete, smoke-tested files. Failed builds leave the old
# artifacts intact; unrelated distributions and staging trees are untouched.
for artifact in stack-composer.pyz "stack-composer-${VERSION}.tar.gz"; do
  cp "dist/$artifact" "$ROOT_DIR/dist/.$artifact.pending"
  mv -f "$ROOT_DIR/dist/.$artifact.pending" "$ROOT_DIR/dist/$artifact"
done
echo "dist/stack-composer-${VERSION}.tar.gz"
