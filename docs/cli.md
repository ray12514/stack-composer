# CLI

Implemented command surface:

- `stack-composer validate-template-set`
- `stack-composer show`
- `stack-composer render`
- `stack-composer validate`
- `stack-composer publish-manifest`

Top-level options:

- `stack-composer --help` prints the command list.
- `stack-composer --version` prints the package version.
- `stack-composer --licenses` prints the bundled runtime dependency license
  manifest.

Command status:

- `validate` checks schemas and render preflight invariants without writing a
  workspace.
- `render` writes a deterministic draft workspace and `release-manifest.yaml`.
- `show` prints the buildable menu from a profile plus optional defaults/stack:
  compilers, MPI providers, GPU arches, and lanes under the current defaults.
- `validate-template-set` renders a smoke stack for each supplied profile and
  writes per-profile reports. `--concretize` is intentionally deferred and exits
  with a clear not-implemented error.
- `publish-manifest` finalizes a rendered draft manifest after build/verify
  inputs are available.

The release tarball also ships `spack-build`, a Bash companion script for local
single-machine lane build/verify/publish input generation. It is not a Python
CLI subcommand.

`render` requires explicit release/source variables so deterministic manifest
fields do not come from ambient git state or the wall clock:

```bash
stack-composer render \
  --profile systems/example-cray/profile.yaml \
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
