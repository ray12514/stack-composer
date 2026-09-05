#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
PYTHON=${PYTHON:-python3}
PYTHON=$("$PYTHON" -c 'import sys; print(sys.executable)')
OUTPUT=""
CANDIDATE=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --output)
      [[ $# -ge 2 && -n $2 && $2 != --* ]] || { echo '--output requires a path' >&2; exit 2; }
      OUTPUT=$2
      shift 2
      ;;
    --candidate) CANDIDATE=1; shift ;;
    --help|-h)
      echo 'Usage: build-native.sh --candidate --output NEW_DIRECTORY'
      echo 'Requires the pinned native builder. Does not replace the trial .pyz.'
      exit 0
      ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done
[[ $CANDIDATE -eq 1 && -n $OUTPUT ]] || {
  echo 'Native builds are opt-in candidates: pass --candidate and --output.' >&2
  exit 2
}
[[ ! -e $OUTPUT && ! -L $OUTPUT ]] || { echo 'Output must be a new directory.' >&2; exit 2; }
OUTPUT=$("$PYTHON" -c 'from pathlib import Path; import sys; print(Path(sys.argv[1]).resolve())' "$OUTPUT")
"$PYTHON" -c 'from importlib.metadata import version; assert version("pyinstaller") == "6.22.2"; assert version("pyinstaller-hooks-contrib") == "2026.7"'
"$PYTHON" "$ROOT_DIR/scripts/generate-third-party.py" --check
STAGE=$(mktemp -d "${TMPDIR:-/tmp}/stack-composer-native.XXXXXX")
trap 'rm -rf "$STAGE"' EXIT
"$PYTHON" "$ROOT_DIR/scripts/release_support.py" stage "$ROOT_DIR" "$STAGE/source"
export STACK_COMPOSER_NATIVE_SOURCE="$STAGE/source"
PYTHONPATH='' "$PYTHON" -m PyInstaller --clean --noconfirm \
  --workpath "$STAGE/work" --distpath "$STAGE/dist" "$ROOT_DIR/packaging/stack-composer.spec"
NATIVE="$STAGE/dist/stack-composer"
cp "$STAGE/work/stack-composer/warn-stack-composer.txt" "$NATIVE/BUILD_WARNINGS.txt"
PYTHONPATH='' PYTHONHOME='' "$NATIVE/stack-composer" --help >/dev/null
PYTHONPATH='' PYTHONHOME='' "$NATIVE/stack-composer" --licenses >/dev/null
"$PYTHON" "$ROOT_DIR/scripts/native_inventory.py" "$ROOT_DIR" "$STAGE/source" "$NATIVE"
"$PYTHON" "$ROOT_DIR/scripts/release_support.py" checksums "$NATIVE"
mkdir -p "$(dirname "$OUTPUT")"
# OUTPUT is a complete candidate directory, not the versioned trial tool path.
mkdir "$OUTPUT"
cp -R "$NATIVE" "$OUTPUT/stack-composer"
tar -C "$OUTPUT" -czf "$OUTPUT/stack-composer-native-candidate.tar.gz" stack-composer
echo "$OUTPUT/stack-composer/stack-composer"
