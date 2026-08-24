# CLI

Implemented command surface:

- `stack-composer show`
- `stack-composer validate`
- `stack-composer render-static`
- `stack-composer render`
- `stack-composer init-workspace`
- `stack-composer validate-template-set`
- `stack-composer publish-manifest`

Top-level options:

- `stack-composer --help` prints the command list.
- `stack-composer --version` prints the package version.
- `stack-composer --licenses` prints the bundled runtime dependency license
  manifest.

Command status:

- `show` summarizes the buildable menu from a profile plus optional
  defaults/stack: provider families, compiler modules, MPI compiler/flavor
  relationships, GPU toolkit modules, system external candidates, and resolved
  lane prerequisites. It reports facts and policy resolution; it does not probe.
- `validate` checks schemas and full-render preflight invariants without
  writing a workspace. `--deployment` is required because it validates the same
  input contract as `render`.
- `render-static` writes a deterministic platform catalog from `profile.yaml`
  and path-independent template-set policy. It accepts no stack or deployment
  input and emits no environment, lane, view, operational module tree, or build
  workspace. It rejects an MPI provider whose compiler pairing is unresolved.
- `render` writes a deterministic draft workspace and `release-manifest.yaml`.
  It requires `--deployment`; install tree, build stage, caches, view roots, and
  module roots are installer-owned deployment inputs, not profile guesses.
- `init-workspace` initializes an authored Initial Conversion Trials blueprint
  against one exact static catalog selection. It is a temporary pilot helper,
  not a production render mode. It does not probe, concretize, fetch, install,
  or replace `render`.
- `validate-template-set` renders a smoke stack for each supplied profile and
  writes per-profile reports. `--concretize` is intentionally deferred and exits
  with a clear not-implemented error.
- `publish-manifest` finalizes a rendered draft manifest after build/verify
  inputs are available.

The release tarball also ships `spack-build`, a Bash companion script for local
single-machine lane build/verify/publish input generation. It is not a Python
CLI subcommand.

## Static catalog

```bash
stack-composer render-static \
  --profile systems/example-cray/profile.yaml \
  --templates templates \
  --template-set v6 \
  --output-root /shared/catalogs \
  --release example-cray-catalog-001 \
  --rendered-at 2026-08-24T00:00:00Z \
  --source-repo stack-content \
  --source-commit 0375b16fdeadbeef0123456789abcdef01234567
```

The output path is
`<output-root>/<system>/static/<release>/`. It contains `scopes/`,
`manifest.yaml`, `reports/static-plan.yaml`, the exact reviewed `profile.yaml`,
and a generated usage README. Pass `--overwrite` only when intentionally
replacing that exact output path. Rendering uses a side path and publishes the
completed tree atomically.

`render` requires explicit release/source variables so deterministic manifest
fields do not come from ambient git state or the wall clock:

```bash
stack-composer render \
  --profile systems/example-cray/profile.yaml \
  --deployment systems/example-cray/deployment.yaml \
  --stack stacks/science-stack/stack.yaml \
  --templates templates \
  --package-sets package-sets \
  --package-repos package-repos \
  --output-root /tmp/rendered \
  --release 2026.06 \
  --rendered-at 2026-06-19T00:00:00Z \
  --source-repo git@example:stacks/science-stack \
  --source-commit 0375b16fdeadbeef0123456789abcdef01234567
```

`--source-dirty` records that the source content was not clean. It does not
inspect Git; all provenance fields remain explicit inputs.

## Initial Conversion Trials workspace

```bash
stack-composer init-workspace \
  --blueprint /path/to/stack-content/pilots/cse-pilot \
  --catalog /shared/catalogs/example-cray/static/example-cray-catalog-001 \
  --values /path/to/example-cray-values.yaml \
  --output /shared/workspaces/example-cray/example-cray-trial-001
```

The blueprint owns the generated file set and required values. The initializer
validates catalog-relative scope selections, renders with `StrictUndefined`,
validates every generated YAML file, and publishes only a complete workspace.
If the blueprint requests workspace permissions, those modes apply only to the
new tree; group ownership still comes from the prepared setgid parent.

Render-only template-set validation example:

```bash
stack-composer validate-template-set \
  --templates templates/v6 \
  --profiles 'systems/*/profile.yaml' \
  --smoke-stack stacks/science-stack/stack.yaml \
  --package-sets-dir package-sets \
  --package-repos-dir package-repos \
  --output /tmp/template-set-report
```
