#!/usr/bin/env bash
# Connected preparation only, inside the recorded Linux native builder image.
set -euo pipefail
INPUTS=${1:?Usage: acquire-offline-wheels.sh CAPSULE_DIRECTORY}
SOURCE="$INPUTS/sources/stack-composer"
export SOURCE_DATE_EPOCH=315532800 PYTHONHASHSEED=0 TZ=UTC LC_ALL=C
export PIP_DISABLE_PIP_VERSION_CHECK=1 PIP_NO_CACHE_DIR=1
PYTHON=${PYTHON:-python3.12}
mkdir -p "$INPUTS/wheels/native" "$INPUTS/wheels/pyz" "$INPUTS/sdists" "$INPUTS/locks"
"$PYTHON" -m pip download --only-binary=:all: --no-deps \
  --dest "$INPUTS/wheels/native" -r "$SOURCE/packaging/offline-build-requirements.txt"
"$PYTHON" "$SOURCE/scripts/offline_delivery.py" wheel-lock "$INPUTS/wheels/native" > "$INPUTS/locks/native.txt"
python3.12 -m venv /tmp/offline-wheel-builder
PYTHON=/tmp/offline-wheel-builder/bin/python
"$PYTHON" -m pip install --no-index --find-links "$INPUTS/wheels/native" --require-hashes \
  --only-binary=:all: -r "$INPUTS/locks/native.txt"
"$PYTHON" -m pip check
"$PYTHON" -m pip download --no-deps --only-binary=:all: --dest "$INPUTS/wheels/pyz" \
  --no-index --find-links "$INPUTS/wheels/native" click==8.1.8 fastjsonschema==2.21.2 Jinja2==3.1.6
"$PYTHON" -m pip download --no-deps --no-build-isolation --no-binary=:all: \
  --dest "$INPUTS/sdists" MarkupSafe==2.1.5 PyYAML==6.0.3
CC=/usr/bin/false PYYAML_FORCE_LIBYAML=0 "$PYTHON" -m pip wheel \
  --no-index --no-deps --no-build-isolation --wheel-dir "$INPUTS/wheels/pyz" \
  "$INPUTS/sdists/MarkupSafe-2.1.5.tar.gz" "$INPUTS/sdists/pyyaml-6.0.3.tar.gz"
"$PYTHON" "$SOURCE/scripts/offline_delivery.py" wheel-lock "$INPUTS/wheels/pyz" > "$INPUTS/locks/pyz.txt"
