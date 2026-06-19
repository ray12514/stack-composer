# CLI

Implemented command surface:

- `stack-composer assess-profiles`
- `stack-composer scaffold-templates`
- `stack-composer validate-template-set`
- `stack-composer explain`
- `stack-composer render`
- `stack-composer validate`
- `stack-composer publish-manifest`

Only `validate`, top-level `--licenses`, and render preflight are active in the
bootstrap implementation. `render` now writes a deterministic draft workspace
for the reference fixture vocabulary. Other commands return a clear
not-yet-implemented error until their planned phases land.

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
