# Development

The [September 2026 assessment](assessment-2026-09.md) records the current
baseline test evidence, reproduced defects, and stabilization order. The
[packaging assessment](packaging-assessment-2026-09.md) evaluates a native
executable distribution. See [stabilization results](stabilization-2026-09.md)
for implemented corrections and the native candidate acceptance boundary.

`stack-composer` follows the current cross-repository model in
`stack-planning/docs/stack_generation_structure_v1.md`,
`stack-planning/docs/end_to_end_map_v1.md`, and
`stack-planning/docs/stack_build_handoff_note_v1.md`.

Current implementation decisions:

- Python package name: `stack_composer`.
- CLI entry point: `stack-composer`.
- Runtime validation: packaged JSON Schemas plus `fastjsonschema`.
- Typed model strategy: plain dictionaries at the schema boundary, with small
  model loader modules per durable input. Internal lane, selection-error,
  skipped-build, and narrowing records use standard-library `TypedDict` in
  `render/records.py`. They remain ordinary dictionaries at runtime, including
  optional-field presence and insertion order. No new runtime model library or
  input syntax is introduced.

The implementation does not depend on GitHub-specific URLs or remote names.
Repository hosting changes should be handled through remotes and CI files, not
through code paths.

## Cross-repository sources of truth

Two contracts are copied into this repository for runtime or test isolation:

- `stack-planning/schemas/*.json` is canonical. The installable package bundles
  byte-identical copies under `src/stack_composer/schemas/`.
- `stack-content/templates/v6/` is canonical for the active template set. The
  tests keep a byte-identical fixture under
  `tests/fixtures/template-sets/v6/`.

With the repositories checked out as siblings, the test suite enforces both
relationships. `STACK_PLANNING=<path>` and `STACK_CONTENT_DIR=<path>` override
the sibling locations. Run `scripts/sync-schema.sh` after a canonical schema
change. A template change must update the Stack Content source and this test
fixture in the same logical change.

## Local Checks

```bash
bash scripts/check.sh
```

The runtime supports Python 3.9 or newer. Build and test from a dedicated
virtual environment; do not depend on user-site packages.
Install the development tools with `.venv/bin/python -m pip install -e '.[dev]'`.
Set `PYTHON=/path/to/venv/bin/python` to run the same checks with another
interpreter. The check script does not install dependencies, refresh inputs,
build artifacts, or access a deployed workspace.

The gate runs the dependency/license consistency check, mypy, Ruff, shell syntax
checks, the complete pytest suite, and `git diff --check`. Mypy is a pinned
development dependency, not part of the released runtime. Its current scope is
the six planning, deployment, context, and release modules listed in
`pyproject.toml`. Imported interfaces are analyzed, but unlisted modules are not
claimed to be fully type-checked. Expand that list in small reviewed changes;
do not silence new errors with broad ignores or convert fields back to `Any`.

Schema-validated input dictionaries and template-specific data remain dynamic.
The limited casts in the planning code express existing schema or presence
checks; they do not perform conversions or change selection policy.

## Behavior-preserving maintenance

Keep command names and options, input schemas, dictionary keys, field presence,
selection order, diagnostic codes, generated paths, file modes, and module text
stable during internal refactoring. Changing a compiler default, lane policy,
template, runtime pin, or supported Python floor is a separate reviewed change.
Passing tests is evidence for the exercised cases, not a guarantee for every
site or older workspace.

For source versus previous packaged-tool comparison, use a new test directory:

```bash
PYTHONPATH=src .venv/bin/python docs/assessments/2026-09/artifact_smoke.py \
  --development /path/to/development \
  --output /path/to/new-test-directory \
  --pyz /path/to/previous-release/stack-composer.pyz
```

The harness uses the repository's Linux/Cray fixtures and the sibling
`stack-content/pilots/cse-pilot` blueprint. It does not require HPC Lab or access
an active trial. It compares static catalogs, full workspaces including module
files, and initialized CSE controls byte for byte, then checks public-catalog
consumption. Use `--executable /path/to/stack-composer` instead of `--pyz` when
checking a native artifact on a compatible Linux host. No Spack builds or module
activation are performed by this comparison.

For the already initialized CSE trial, the generated `cse-build` drives Spack's
install, view regeneration, and package-module refresh. Its `publish-modules`
action exposes the generated entry modules and lane selectors. Updating the
Composer executable does not update those retained workspace controls and is
not a reason to rerun `init-workspace --overwrite`, reconcretize, or replace
locks. If a later change actually modifies controls, follow the dedicated CSE
control-refresh runbook. Full managed `render` still generates its own module
presentation files, so the module-output regression checks remain required.

## Release Build

`scripts/build-pyz.sh` produces `dist/stack-composer-<version>.tar.gz` with a
shiv-built `stack-composer.pyz`, project license, third-party manifest, and
third-party license files.

The release build refreshes bundled schemas from an adjacent
`stack-planning` checkout when available. If it is not adjacent, the build uses
the bundled copies and the release operator must already have passed the schema
drift test in a four-repository checkout.

Runtime dependencies are exact release inputs. `pyproject.toml` is the single
authored version list. Both wheel acquisition scripts obtain their requirements
from `generate-third-party.py --requirements`; the offline builder list contains
only build tools. The `.pyz` source-build policy for MarkupSafe and PyYAML remains
explicit so the wheelhouse stays platform-neutral. Native runtime wheels use
the same versions. Pure source wheels are built using the prepared build
environment (`--no-build-isolation`), matching offline acquisition rather than
allowing pip to select another build environment implicitly.

For a reviewed dependency update:

1. Change the exact runtime pin in `pyproject.toml` and review its Python floor,
   release notes, security notices, license, and transitive dependencies.
2. Install the reviewed version in the dedicated build environment. Run
   `.venv/bin/python scripts/generate-third-party.py --refresh --sync-resources`
   and review the resulting manifest and license diffs. This command records
   metadata; it does not grant security or license approval.
3. Update the explicit expected pins in `tests/test_scripts.py`, then run
   `bash scripts/check.sh` on the supported Python versions and perform the
   source/artifact comparison above.
4. Reacquire wheels and regenerate hash locks in a new offline input capsule.
   Rebuild and test both deliverables. Do not edit a sealed capsule or reuse
   checksums from the previous release. Retain its sources, tools, and evidence.

Inspect acquisition requirements without installing anything:

```bash
.venv/bin/python -S scripts/generate-third-party.py --requirements all
```

Runtime upgrades are not implicit in maintenance checks. In particular, the
previously recorded Click update versus Python 3.9 compatibility decision
remains separate; this refactor does not resolve that security-review gate.

Smoke-check the built artifact with:

```bash
dist/stack-composer.pyz --help
dist/stack-composer.pyz --licenses
```

Release staging is private and starts from current source files, not the
persistent `build/lib` tree. The build checks every application file in both
wheel and zipapp against that source export. Failed builds leave the previous
artifact intact. The tarball includes `APPLICATION_FILES.json` and `SHA256SUMS`.

For an optional Linux executable, use the isolated builder and
`scripts/build-native.sh --candidate --output <new-directory>` described in
[the native build plan](native-build-plan-2026-09.md). Run its `stack-composer`
directly and keep `_internal` beside it. This does not replace the `.pyz` default.

## Maintenance verification, 2026-09-07

The internal typing and dependency-acquisition changes were compared with
baseline commit `d3679b2` and the retained offline `.pyz` from source `997520a`.
The baseline had 256 passing tests; four acquisition-command cases were added.

| Check | Result |
|---|---|
| Full suite, macOS Python 3.9.25 | 260 passed |
| Full suite, macOS Python 3.14.7 | 260 passed |
| Scoped mypy, Python 3.9 target | Six modules passed |
| Negative typing probe | Wrong lane field name and integer compiler reference rejected |
| Ruff, ShellCheck, shell syntax, diff whitespace | Passed |
| Current source versus retained `.pyz` | Byte-identical Linux/Cray static, full, and initialized output |
| Rebuilt `.pyz` versus source | Same output comparison passed |
| Native executable versus source, Linux Python 3.12.14 builder | Same comparison passed with network disabled and `/tmp` mounted `noexec` |
| Public catalog consumed by initializer | Passed in the artifact comparisons |
| Revised acquisition using approved local wheels and source archives | Native and pure wheel hash locks identical to the retained offline inputs |
| Derived-pin packaging path using approved local inputs | Passed without network access |

The Linux fixture compares 9 catalog, 26 full-workspace, and 63 initialized
files; the Cray fixture compares 15, 31, and 69. These comparisons include
generated module files and trial build controls. The production runtime pins,
schemas, templates, and shipped `spack-build` script were not changed. No active
CSE workspace, lockfile, package store, build cache, or shared lab service was
modified. The packaged checks are local candidates, not a new published release
or new real-system compiler/MPI/GPU acceptance evidence.
