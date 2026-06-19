# stack-composer

`stack-composer` is the Python implementation described by
`stack-planning/docs/stack_composer_design_v1.md`.

It consumes stack repository content and produces Spack-consumable rendered
workspaces. It does not probe hosts, run Spack during `render`, deploy files, or
make package intent decisions outside `stack.yaml` and template contracts.

## Status

Phase 1 foundation is in progress:

- Python package scaffold and CLI are present.
- Canonical schemas are packaged under `stack_composer/schemas/`.
- `validate` performs schema and initial render preflight checks.
- `render` writes a deterministic draft workspace for the reference fixture
  vocabulary, including rendered config scopes, lane environments, package repos,
  and `release-manifest.yaml`.
- Full v6 resolver coverage, release packaging, and third-party license
  enforcement are still in progress.

## Development

```bash
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'
.venv/bin/pytest
.venv/bin/ruff check .
```

## GitLab Note

The implementation does not hardcode GitHub-specific URLs or remote names.
Moving the repository to GitLab should only affect git remotes and future CI
configuration.
