# Working in stack-composer

`stack-composer` is the pure Python renderer/validator for the current
spec-native stack-generation model.

## Read these first

1. `~/Development/stack-planning/docs/stack_generation_structure_v1.md`
2. `~/Development/stack-planning/docs/end_to_end_map_v1.md`
3. `~/Development/stack-planning/docs/deployment_inputs_and_ownership_v1.md`
4. `~/Development/stack-planning/docs/stack_build_handoff_note_v1.md`
5. `PHASE_STATUS.md`

## Current model

- `profile.yaml` contains observed system facts.
- `deployment.yaml` contains installer-chosen paths.
- `defaults.yaml` contains site/template-set policy.
- `stack.yaml` contains package intent and optional narrowing.
- templates contain render mechanics.

Do not add a separate contract/toolchain/build-class/node-selector layer; the
current model is spec-native plus defaults and provider facts.

## Render seam invariants

- `render` reads only explicit inputs and the named files in the stack-content
  tree.
- `render` requires `deployment.yaml`; never derive install tree, build stage,
  cache roots, view roots, or module roots from the profile.
- No host probing, no Spack imports, no ambient `$HOME` config.
- Same inputs produce a byte-identical workspace.
- Jinja uses `StrictUndefined`; missing context is a render failure.
- On failure the `.rendering` side path is deleted and the workspace is not
  replaced.

## Cross-repo boundaries

- `cluster-inspector` produces `profile.yaml`; this repo consumes the schema.
- `stack-content` owns authored inputs: templates, package sets, package repos,
  stacks, profiles, deployments.
- `stack-composer` renders a workspace tree; it does not build. Build happens
  downstream via `spacktools`, `spack-build`, Ansible, or bare Spack.
- Do not add project-owned personal-GitHub import paths or docs dependencies.

## Validation before claiming done

```bash
.venv/bin/python -m pytest tests/ -q
.venv/bin/ruff check src tests
```

If render behavior changes, also render a reference fixture and inspect the
workspace. If the rendered tree or `spack-build` seam changes, run the available
Docker/Spack smoke path from `~/Development/cse-stack/scripts` when feasible.

## Keep the model narrow

- `stack.yaml` stays spec-native; do not require extra package-manager syntax
  beyond specs/package sets and optional narrowing.
- Keep user-facing policy labels out of stack authoring.
- Keep render policy in `defaults.yaml`, provider facts, deployment, and
  templates.
- Avoid vendor-specific render branches where provider-family facts would work.
