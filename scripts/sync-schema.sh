#!/usr/bin/env bash
#
# Sync the bundled JSON schemas from the canonical source in stack-planning.
#
# stack-planning/schemas is the single source of truth; this repo bundles a copy
# so the pyz is self-contained at runtime. Run this whenever the canonical schemas
# change. tests/test_schema_drift.py fails if the bundled copies drift, so this
# script + that guard are the two halves of the contract.
#
# Canonical location override: STACK_PLANNING=<path> (default: sibling checkout).
set -euo pipefail

ROOT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
STACK_PLANNING=${STACK_PLANNING:-"${ROOT_DIR}/../stack-planning"}
SRC="${STACK_PLANNING}/schemas"
DST="${ROOT_DIR}/src/stack_composer/schemas"

if [ ! -d "${SRC}" ]; then
  echo "sync-schema: canonical schemas not found at ${SRC}" >&2
  echo "             clone stack-planning adjacent or set STACK_PLANNING=<path>" >&2
  exit 1
fi

count=0
for f in "${DST}"/*.json; do
  name=$(basename "${f}")
  if [ -f "${SRC}/${name}" ]; then
    cp "${SRC}/${name}" "${f}"
    count=$((count + 1))
  else
    echo "sync-schema: WARNING ${name} has no canonical counterpart in ${SRC}" >&2
  fi
done
echo "sync-schema: copied ${count} schema(s) from ${SRC}"
