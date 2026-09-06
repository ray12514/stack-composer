#!/usr/bin/env bash
# Run inside the recorded builder, --network=none, inputs mounted read-only at /inputs.
set -euo pipefail
[[ ! -e /build && -d /inputs && -d /result ]] || {
  echo 'Requires a fresh container with /inputs read-only and an empty /result mount.' >&2
  exit 2
}
[[ -z $(ls -A /result) ]] || { echo '/result must be empty.' >&2; exit 2; }
python3.12 /inputs/offline_delivery.py verify /inputs
mkdir /build
cp -R /inputs/sources/. /build/
python3.12 -m venv /build/venv
export PYTHON=/build/venv/bin/python
export PYTHONHASHSEED=0 PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1 TZ=UTC LC_ALL=C
export PIP_NO_INDEX=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
export SOURCE_DATE_EPOCH
SOURCE_DATE_EPOCH=$(python3.12 -c 'import json; print(json.load(open("/inputs/RELEASE_INPUTS.json"))["sources"]["source_date_epoch"])')
"$PYTHON" -m pip install --no-index --find-links /inputs/wheels/native --require-hashes \
  --only-binary=:all: -r /inputs/locks/native.txt
"$PYTHON" -m pip check
export STACK_COMPOSER_WHEELHOUSE=/inputs/wheels/pyz STACK_COMPOSER_WHEEL_LOCK=/inputs/locks/pyz.txt
bash /build/stack-composer/scripts/build-pyz.sh
bash /build/stack-composer/scripts/build-native.sh --candidate --output /build/native-output
cp /build/stack-composer/dist/stack-composer.pyz /build/stack-composer/dist/stack-composer-*.tar.gz /result/
cp /build/native-output/stack-composer-native-candidate.tar.gz /result/
cp /inputs/RELEASE_INPUTS.json /result/
"$PYTHON" /build/stack-composer/scripts/release_support.py checksums /result
