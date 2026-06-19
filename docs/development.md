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
