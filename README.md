# stack-composer

`stack-composer` is the Python renderer/validator described by the current
stack-planning notes, especially
`stack-planning/docs/stack_generation_structure_v1.md`.

It consumes stack repository content and produces Spack-consumable rendered
workspaces. It does not probe hosts, run Spack during `render`, deploy files, or
make package intent decisions outside `stack.yaml`, `defaults.yaml`, and
templates.

## Status

Current implementation status:

- Canonical schemas are packaged under `stack_composer/schemas/`.
- `validate` performs schema checks and render preflight checks.
- `render` writes deterministic draft workspaces with rendered config scopes,
  lane environments, package repos, and `release-manifest.yaml`.
- `render-static` writes a reusable catalog of observed platform scopes for
  package managers who want to author their own Spack environments. The exact
  reviewed input is retained as `profile.yaml` beside the catalog.
- `init-workspace` is a CSE pilot convenience that assembles an authored
  starter blueprint against an exact static catalog selection. It is not a
  production render mode or a supported long-term consumption seam; it does
  not probe, build, or replace full `render`.
- `render` requires `deployment.yaml` and emits installer-owned install/cache
  paths into `configs/common/config.yaml`; profile filesystem entries are only
  candidates.
- Maintainer/operator commands are implemented: `show`, `validate-template-set`,
  and `publish-manifest`. `show` is the profile browser: it reports provider
  families, compiler/MPI/GPU module facts, and resolved lane module prerequisites
  from `profile.yaml` plus the selected defaults/stack.
- `scripts/spack-build` is shipped in the release tarball as the local build
  companion script.
- Reference fixture acceptance renders the smoke stack against Cray and generic
  Linux profiles in tests.
- Release packaging, platform-neutral `.pyz` enforcement, and third-party
  license enforcement are present.

`validate-template-set --concretize` remains intentionally deferred; the flag is
wired and exits with a clear not-implemented error.

## Development

```bash
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'
.venv/bin/pytest
.venv/bin/ruff check .
```

Build a local release artifact with:

```bash
PYTHON=.venv/bin/python scripts/build-pyz.sh
```

Initialize an authored pilot workspace from a static catalog with:

```bash
stack-composer init-workspace \
  --blueprint /path/to/stack-content/pilots/cse-pilot \
  --catalog /path/to/rendered-static/<system>/static/<catalog-release> \
  --values /path/to/<system>-cse-pilot-values.yaml \
  --output /path/to/workspaces/<system>/cse-pilot/<release>
```

The blueprint owns package intent and exposure policy. The values file selects
real catalog scopes and deployment roots. The command rejects missing or
escaping catalog paths, unsupported provider modes, incomplete values, and
invalid generated YAML before publishing the workspace atomically. A blueprint
may also request that the declared read/write policy be applied to the files and
directories in the newly initialized workspace.

## GitLab Note

The implementation does not hardcode GitHub-specific URLs or remote names.
Moving the repository to GitLab should only affect git remotes and hosting/CI
configuration.
