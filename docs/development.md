# Development

`stack-composer` follows the current cross-repository model in
`stack-planning/docs/stack_generation_structure_v1.md`,
`stack-planning/docs/end_to_end_map_v1.md`, and
`stack-planning/docs/stack_build_handoff_note_v1.md`.

Current implementation decisions:

- Python package name: `stack_composer`.
- CLI entry point: `stack-composer`.
- Runtime validation: packaged JSON Schemas plus `fastjsonschema`.
- Typed model strategy: plain dictionaries at the schema boundary, with small
  model loader modules per durable input. Pydantic v2 is intentionally avoided
  so the shiv artifact stays platform-neutral.

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
.venv/bin/python -m pytest tests/ -q
.venv/bin/ruff check src tests
git diff --check
```

The runtime supports Python 3.9 or newer. Build and test from a dedicated
virtual environment; do not depend on user-site packages.

## Release Build

`scripts/build-pyz.sh` produces `dist/stack-composer-<version>.tar.gz` with a
shiv-built `stack-composer.pyz`, project license, third-party manifest, and
third-party license files.

The release build refreshes bundled schemas from an adjacent
`stack-planning` checkout when available. If it is not adjacent, the build uses
the bundled copies and the release operator must already have passed the schema
drift test in a four-repository checkout.

Runtime dependencies are exact release inputs. Their `pyproject.toml` pins,
the wheelhouse requirements in `scripts/build-pyz.sh`, and the versions in
`THIRD_PARTY.toml` must agree. The third-party script enforces that consistency,
refreshes license texts from installed runtime distributions, and syncs packaged
resources.

Smoke-check the built artifact with:

```bash
dist/stack-composer.pyz --help
dist/stack-composer.pyz --licenses
```
