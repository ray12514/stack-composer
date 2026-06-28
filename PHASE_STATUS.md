# Phase Status

Current branch: `spec-native-builds`.

This file tracks the active pre-v1 implementation shape. Older contract /
toolchain / build-class phase text was removed because the current model is
spec-native and defaults-driven.

## Current model

- `stack.yaml` is the package-manager surface: builds are mostly `name` plus
  Spack `specs` or `package_set`; `kind`, `compilers`, `mpi`, `gpu`, and
  `target` are optional narrowing/override fields.
- `defaults.yaml` supplies site/template-set policy.
- `profile.yaml` supplies generic `compiler_providers` and `mpi_providers`.
- `deployment.yaml` supplies installer-chosen paths.
- `stack-composer render` writes the rendered workspace tree and stops.

Primary planning docs:

- `stack-planning/docs/stack_generation_structure_v1.md`
- `stack-planning/docs/end_to_end_map_v1.md`
- `stack-planning/docs/deployment_inputs_and_ownership_v1.md`
- `stack-planning/docs/stack_build_handoff_note_v1.md`

## Implemented

- Packaged schemas: `profile`, `defaults`, `deployment`, `stack`, `package-set`,
  `release-manifest`.
- `validate`: schema checks plus render preflight.
- `show`: profile/defaults/stack buildable-menu summary.
- `validate-template-set`: render-only smoke validation across profiles.
- `render`: deterministic workspace tree with config scopes, lane
  environments, package repos, and draft `release-manifest.yaml`.
- `publish-manifest`: finalizes a draft manifest from downstream build evidence.
- `spack-build`: local Spack-driving companion script.
- Front-door Tcl lane selector modulefiles are rendered under the workspace's
  `modulefiles/` tree. Spack still generates package modulefiles into each
  lane's `package_module_root`.
- Generic provider inventory consumption: `compiler_providers` +
  `mpi_providers`.
- Baseline compiler default: `gcc` if present, otherwise first reported
  compiler.
- MPI platform compatibility auto-narrowing for non-explicit compiler defaults.
- `deployment.yaml` as a first-class render input; render emits
  `configs/common/config.yaml` and lane view/module roots from deployment.
- System externals (`openssl`, `curl`) flow from `profile.yaml` into rendered
  `configs/common/packages.yaml` when stack/defaults policy allows them.
- Docker/Spack smoke path using `cse-stack/docker/smoke/run-smoke.sh` passes
  profile -> render -> Spack 1.1.1 concretize/fetch/install/verify for the
  Stack Content smoke lane.

## Deferred / open

- `validate-template-set --concretize` remains intentionally deferred.
- Front-door selector emission still needs real-system module-tool validation.
  Package module generation remains owned by Spack (`spack module tcl refresh`).
- Fabric userspace external inventory still needs first-system evidence and
  render coverage.
- Broader ordinary package external inventory remains focused/hints-driven;
  `openssl` and `curl` are covered by the current smoke path.

## Definition of ready for first full iteration

1. `pytest` passes.
2. `ruff` passes.
3. `stack-content` smoke render works with `systems/smoke/profile.yaml`,
   `systems/smoke/deployment.yaml`, `templates/v6`, and
   `stacks/mpi-smoke/stack.yaml`.
4. The Docker/Spack smoke path in `cse-stack/scripts` succeeds or has a clearly
   documented blocker. Current baseline passed with Spack 1.1.1 on Rocky 9.
