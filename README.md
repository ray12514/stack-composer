# stack-composer

`stack-composer` is the pure-Python renderer and validator described by the
current `stack-planning` notes, especially
`stack-planning/docs/stack_generation_structure_v1.md`.

It consumes explicit repository inputs and produces Spack-consumable output. It
does not probe hosts, import or run Spack while rendering, inspect ambient
machine state, or choose deployment paths.

## Product boundaries

There are two long-term render products and one temporary helper:

| Command | Output | Intended consumer |
|---|---|---|
| `render-static` | Reusable, include-ready platform scopes from one reviewed `profile.yaml` | Package managers authoring their own Spack environments |
| `render` | A complete managed workspace from profile, deployment, defaults, stack intent, package content, and templates | A downstream build path such as bare Spack, `spack-build`, `spacktools`, or Ansible |
| `init-workspace` | A workspace rendered from an authored blueprint plus one exact static catalog | Initial Conversion Trials only |

`init-workspace` is not a third production mode. It exists to exercise the
static/manual workflow during the trials and can be removed after the static
and full-render procedures are complete.

## Status

Current implementation status:

- Canonical schemas are packaged under `stack_composer/schemas/`.
- `validate` performs schema checks and render preflight checks.
- `render` writes deterministic draft workspaces with rendered config scopes,
  lane environments, package repositories, front-door modulefiles, reports,
  and `release-manifest.yaml`.
- `render-static` writes a reusable catalog of observed platform scopes for
  package managers who want to author their own Spack environments. The exact
  reviewed input is retained as `profile.yaml` beside the catalog. An MPI
  provider without a verified compiler pairing is rejected rather than emitted
  as an ambiguous scope.
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

The current full-render output is still pre-v1. It is usable for the exercised
platform-external path, but it is not yet the final Spack 1.2 managed-workspace
shape. Native environment-local `modules.yaml`, producer groups with `needs`,
explicit compiler binding for every lane, declarative GPU-as-MPI-superset
composition, and the remaining module/CPE policy must move together before the
full renderer is production-ready. See `PHASE_STATUS.md`.

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

Render a reusable static catalog with:

```bash
stack-composer render-static \
  --profile /path/to/profile.yaml \
  --templates /path/to/stack-content/templates \
  --template-set v6 \
  --output-root /path/to/catalogs \
  --release <catalog-release> \
  --rendered-at <utc-timestamp> \
  --source-repo <source-identifier> \
  --source-commit <full-commit>
```

The catalog is platform configuration, not a build workspace. It contains no
package roster, managed lane, view, operational module tree, or deployment
root.

## GitLab Note

The implementation does not hardcode GitHub-specific URLs or remote names.
Moving the repository to GitLab should only affect git remotes and hosting/CI
configuration.
