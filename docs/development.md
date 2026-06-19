# Development

`stack-composer` follows `stack-planning/docs/stack_composer_design_v1.md`.

Current implementation decisions:

- Python package name: `stack_composer`.
- CLI entry point: `stack-composer`.
- Runtime validation: packaged JSON Schemas plus `fastjsonschema`.
- Typed model strategy: plain dictionaries at the schema boundary, with small
  model loader modules per durable input. Pydantic v2 is intentionally avoided
  so the eventual shiv artifact can stay platform-neutral.

The GitLab migration should be handled through remotes and future CI files, not
through hardcoded repository URLs in the implementation.

## Release Build

`scripts/build-pyz.sh` produces `dist/stack-composer-<version>.tar.gz` with a
shiv-built `stack-composer.pyz`, project license, third-party manifest, and
third-party license files.

The third-party script refreshes exact dependency versions and license texts
from installed runtime distributions, enforces manifest consistency, and syncs
packaged resources.
