# Receive the trial maintenance tools

This delivery selects one exact Composer, Content and Planning source checkpoint.
It contains the portable Composer tool, its matching `spack-build` companion,
authored sources, operating procedures and hash-locked pure Python dependencies
for the preparation helpers. Cluster Inspector, Spack, builtin recipes and built
packages are supplied separately at their already recorded site locations.

The commands below install the tools in a new versioned directory. Existing
workspace inputs, locks, Spack databases, installed packages, views and modules
change only through a later, explicit maintenance operation. Production path
selection remains undecided.

## Verify and select the delivery

Transfer `@VERSION@.tar.gz` and `@VERSION@.tar.gz.sha256` through the approved
delivery channel. Compare the checksum file with the release receipt before
executing code from the archive. Run in the receiving directory with Bash and
Python 3.9 or newer; set `TOOLS_ROOT` to the site's tool-release directory:

```bash
set -euo pipefail
VERSION='@VERSION@'
TOOLS_ROOT=/absolute/site/path/tool-releases
sha256sum --check "$VERSION.tar.gz.sha256"
mkdir -p "$TOOLS_ROOT"
test ! -e "$TOOLS_ROOT/$VERSION"
tar -xzpf "$VERSION.tar.gz" -C "$TOOLS_ROOT"
DELIVERY_ROOT="$TOOLS_ROOT/$VERSION"
python3 "$DELIVERY_ROOT/verify-delivery.py" verify-bundle "$DELIVERY_ROOT"
(cd "$DELIVERY_ROOT" && sha256sum --check SHA256SUMS)
```

The delivery manifest records source commits, the sealed build-input digest,
and every included file's digest and mode. Verification also rejects additional
files. Keep writable runtime/cache directories outside this immutable tree.
The published SHA-256 identifies the reviewed bytes; it is not a signature.

Create a separate helper environment entirely from the delivered wheels. No pip
download or compiler is needed. The site Python must provide `venv`/`ensurepip`:

```bash
PREP_RUNTIME="$TOOLS_ROOT/$VERSION-runtime"
test ! -e "$PREP_RUNTIME"
python3 -m venv "$PREP_RUNTIME"
PREP_PYTHON="$PREP_RUNTIME/bin/python"
"$PREP_PYTHON" -m pip install --no-index --only-binary=:all: --require-hashes \
  --find-links "$DELIVERY_ROOT/wheels" \
  -r "$DELIVERY_ROOT/runtime-requirements.txt"
"$PREP_PYTHON" -m pip check

export SHIV_ROOT="$PREP_RUNTIME/shiv-cache"
export PYTHONDONTWRITEBYTECODE=1
STACK_COMPOSER="$DELIVERY_ROOT/tools/stack-composer.pyz"
CONTENT="$DELIVERY_ROOT/sources/stack-content"
PLANNING="$DELIVERY_ROOT/sources/stack-planning"
"$PREP_PYTHON" "$STACK_COMPOSER" --help
"$PREP_PYTHON" "$CONTENT/pilots/cse-pilot/scripts/refresh-workspace-controls.py" --help
```

Use these explicit paths for the trial maintenance window. Record `VERSION`,
the delivery checksum and the three source commits in the per-machine receipt.
There is no global tool symlink change in this procedure. The previous delivery
remains available by its own path.

## Update an existing completed or partial trial

First follow the delivered
[`CONTROL-REFRESH.md`](sources/stack-content/pilots/cse-pilot/CONTROL-REFRESH.md).
It specifies the current older-workspace rehearsal, prerequisite adoption,
preview, retained recovery record and module acceptance steps. Use the workspace's
recorded values, catalog and Spack identity. If old values lack current required
fields, make the render-only copy with the supplied
`prepare-existing-workspace-values.py` procedure; keep the original values.

Set `BUILD_WORKSPACE` and `REFRESH_VALUES` to the reviewed absolute paths. Start
by previewing only the workspace's module entrance and lane presentation:

```bash
BUILD_WORKSPACE=/absolute/site/path/to/existing-trial
REFRESH_VALUES=/absolute/site/path/to/reviewed-render-values.yaml
"$PREP_PYTHON" "$CONTENT/pilots/cse-pilot/scripts/refresh-workspace-controls.py" \
  --composer "$STACK_COMPOSER" --blueprint "$CONTENT/pilots/cse-pilot" \
  --values "$REFRESH_VALUES" --workspace "$BUILD_WORKSPACE" \
  --scope presentation --dry-run
```

Review the selected content and quiesce users of those controls before repeating
without `--dry-run`. Retain the printed recovery record. An accepted source/tool
delivery does not automatically accept a new overlay inventory in an old
workspace. Follow the prerequisite procedure before selecting `controls` or
`all`; a missing prerequisite stops that refresh.

Package modules use the existing lock and install database. Follow the generated
workspace's `BUILDER-HANDOFF.md` module-only command, and back up the external
module root before refreshing it. Test a clean module session and an installed
consumer before exposing the changed modules. This does not reconcretize,
fetch or rebuild packages.

For a changed recipe, package version, variant, compiler or MPI policy, prepare a
separate candidate and inspect its new lock and affected consumers. Resume the
two incomplete CCE builds from their retained workspaces; local fixture results
do not replace their compiler, Fortran/MPI and launch-path acceptance. Preserve
the recorded locks, database, prefixes and external runtime while updating tools.

## Restore the selected controls

Use the exact record printed by the refresh and preview the restore first:

```bash
REFRESH_RECORD=/absolute/path/from/refresh/output/record.json
"$PREP_PYTHON" "$CONTENT/pilots/cse-pilot/scripts/refresh-workspace-controls.py" \
  --workspace "$BUILD_WORKSPACE" --restore-from "$REFRESH_RECORD" --dry-run
```

After review, repeat without `--dry-run`. For an unfinished transaction use the
documented `--recover-from` procedure. Selecting the earlier tool directory alone
does not undo a workspace maintenance operation; the retained record owns that
restore. No render/init overwrite of the existing workspace is part of delivery.
