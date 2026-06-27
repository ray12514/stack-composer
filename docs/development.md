# Development

`stack-composer` follows the current stack-planning model in
`docs/stack_generation_structure_v1.md`, `docs/end_to_end_map_v1.md`, and
`docs/stack_build_handoff_note_v1.md`.

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

## Local Checks

```bash
.venv/bin/ruff check .
.venv/bin/pytest
git diff --check
```

## Release Build

`scripts/build-pyz.sh` produces `dist/stack-composer-<version>.tar.gz` with a
shiv-built `stack-composer.pyz`, project license, third-party manifest, and
third-party license files.

The third-party script refreshes exact dependency versions and license texts
from installed runtime distributions, enforces manifest consistency, and syncs
packaged resources.

Smoke-check the built artifact with:

```bash
dist/stack-composer.pyz --help
dist/stack-composer.pyz --licenses
```
