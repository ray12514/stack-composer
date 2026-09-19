# stack-composer

`stack-composer` is the pure-Python renderer and validator described by the
current `stack-planning` notes, especially
`stack-planning/docs/stack_generation_structure_v1.md`.

It consumes explicit repository inputs and produces Spack-consumable output. It
does not probe hosts, import or run Spack while rendering, inspect ambient
machine state, or choose deployment paths.

## Product boundaries

There are two render products and a supported blueprint assembly path:

| Command | Output | Intended consumer |
|---|---|---|
| `render-static` | Reusable, include-ready platform scopes from one reviewed `profile.yaml` | Package managers authoring their own Spack environments |
| `publish-static` | An immutable public copy of one reviewed static catalog, with checksums and approval metadata | Package managers and `init-workspace` |
| `render` | A complete managed workspace from profile, deployment, defaults, stack intent, package content, and templates | A downstream build path such as bare Spack, `spack-build`, `spacktools`, or Ansible |
| `init-workspace` | A workspace rendered from an authored blueprint, explicit values, and one exact static catalog | CSE trials and maintained specialized blueprints |

`init-workspace` remains supported as a blueprint assembler, not a second lane
planner. It shares output safety and YAML validation with the other commands.
The blueprint owns its package and layout policy. Full `render` continues to
own the standard profile/deployment/defaults/stack planning interface. See
[workspace workflows](docs/workspace-workflows-2026-09.md) for the package-growth
proposal and the limits on cross-compiler reuse.

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
  as an ambiguous scope. Catalog manifests and README examples use relative
  scope paths so the reviewed tree can be promoted without rerendering.
- `publish-static` validates and copies one reviewed catalog into
  `<output-root>/<system>/static/<release>/`, records a SHA-256 inventory and
  approval metadata, applies CSE-group management and outside-consumer read
  modes, and can update a relative `current` symlink. It does not render or
  modify the restricted source tree.
- `init-workspace` assembles an authored
  starter blueprint against an exact restricted or published static catalog
  selection. Published input is verified against `SHA256SUMS`, and its approval
  metadata and input digests are retained in `workspace-manifest.yaml`. It does
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
bash scripts/check.sh
```

Build a local release artifact with:

```bash
PYTHON=.venv/bin/python scripts/build-pyz.sh
```

Initialize an authored pilot workspace from a static catalog with:

```bash
export STACK_CONTENT_ROOT="<site-selected Stack Content checkout>"
export CATALOG_ROOT="<site-selected catalog root>"
export WORKSPACE_ROOT="<site-selected workspace root>"
export SITE_VALUES_FILE="<reviewed site-values file>"

stack-composer init-workspace \
  --blueprint "$STACK_CONTENT_ROOT/pilots/cse-pilot" \
  --catalog "$CATALOG_ROOT/<system>/static/<catalog-release>" \
  --values "$SITE_VALUES_FILE" \
  --output "$WORKSPACE_ROOT/<system>/cse-pilot/<release>"
```

The blueprint owns package intent and exposure policy. The values file selects
real catalog scopes and deployment roots. The command rejects missing or
escaping catalog paths, unsupported provider modes, incomplete values, and
invalid generated YAML before promoting the workspace. Existing output is
retained until a validated replacement can be installed, with rollback on a
failed promotion. This is recoverable replacement, not a portable atomic
directory exchange or a power-loss guarantee. A blueprint
may also request that the declared read/write policy be applied to the files and
directories in the newly initialized workspace.

Render a reusable static catalog with:

```bash
export PROFILE_FILE="<reviewed system profile>"
export STACK_CONTENT_ROOT="<site-selected Stack Content checkout>"
export CATALOG_ROOT="<site-selected catalog root>"

stack-composer render-static \
  --profile "$PROFILE_FILE" \
  --templates "$STACK_CONTENT_ROOT/templates" \
  --template-set v6 \
  --output-root "$CATALOG_ROOT" \
  --release <catalog-release> \
  --rendered-at <utc-timestamp> \
  --source-repo <source-identifier> \
  --source-commit <full-commit>
```

The catalog is platform configuration, not a build workspace. It contains no
package roster, managed lane, view, operational module tree, or deployment
root.

Publish the reviewed catalog without running `render-static` again:

```bash
export REVIEWED_CATALOG="$CATALOG_ROOT/<system>/static/<catalog-release>"
export PUBLISHED_CATALOG_ROOT="<site-selected public catalog root>"
export CSE_GROUP="<site-cse-group>"

stack-composer publish-static \
  --catalog "$REVIEWED_CATALOG" \
  --output-root "$PUBLISHED_CATALOG_ROOT" \
  --published-at <utc-timestamp> \
  --reviewed-by "<reviewer-or-role>" \
  --approved-by "<release-authority-or-role>" \
  --group "$CSE_GROUP" \
  --set-current
```

The public path is
`<published-root>/<system>/static/<catalog-release>/`. Publication fails if the
reviewed catalog is not relocatable, has unresolved MPI dependencies, contains
symlinks, or already exists at the public release path. `--set-current` is
optional and is not used as a reproducible environment input.

`--group` assigns the CSE group to the published namespace and every released
catalog file. Directories are `2775`, executable files are `0775`, and ordinary
files are `0664`. Every CSE group member retains management access, while users
outside CSE receive read/traverse access without write access. An accepted
versioned release is immutable by process: `publish-static` will not overwrite
it, and a correction is rendered and published under a new release identifier.

Stack Composer does not infer whether an output root is restricted or public.
The CSE runbook passes the restricted root to `render-static`, retains that
catalog as the CSE workspace input, and later passes the public root to
`publish-static`. Keeping promotion as a separate command preserves the review
gate and prevents publication from rerendering or silently changing the CSE
catalog of record.

## GitLab Note

The implementation does not hardcode GitHub-specific URLs or remote names.
Moving the repository to GitLab should only affect git remotes and hosting/CI
configuration.
