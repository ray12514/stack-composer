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
- Front-door Tcl modulefiles are rendered under the workspace's `modulefiles/`
  tree: compiler init modules such as `science_init_gcc`, plus short lane
  modules such as `science/mpi`. Spack still generates package modulefiles into
  each lane's `package_module_root`.
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
- Spack-native toolchains: every MPI lane's `%<toolchain_name>` spec
  decoration is defined by a `toolchains.yaml` in that lane's included
  `configs/mpi/<provider>` scope (platform lanes pin `%mpi=<provider>@<ver>`,
  build-sourced lanes pin `%mpi=<provider>` unversioned with `buildable: true`
  + an `mpi` requirement in the scope's packages.yaml). Same-name multi-version
  platform MPI is a hard render error unless the build sets `mpi.version`;
  toolchain names carry spec-token-safe compiler and MPI version slugs when
  known (`aocc420_openmpi503`, `gcc1330_craympich8129`) so dots/dashes never
  leak into `%toolchain` tokens. `stack-composer show` lists the identities.
- Manual/Tier-0 verification (2026-07-01): rendered the smoke workspace, then
  hand-authored a standalone `spack.yaml` that `include:`s the rendered
  `configs/{common,os/rhel9,target/x86_64_v4,vendor/linux,mpi/openmpi}` scopes
  and a spec like `hdf5+mpi %gcc1140_openmpi`; verified every `%name`
  referenced by the specs is a key in an included `toolchains.yaml` (structural
  check — no local Spack; re-run with `spack -e <env> concretize` on a system
  with Spack).

## Where we left off (2026-07-01)

Blueback run #1 is ready to resume. The spec-native toolchain rework landed and
is pushed: every MPI lane's `%<toolchain_name>` decoration is defined in an
included scope; same-name multi-version platform MPI hard-errors unless the
build pins `mpi.version`; toolchain names are spec-token-safe versioned slugs.
Next step on the box (per
`stack-content/systems/blueback/runbook-notes.md`): pull all three repos,
rebuild the pyz, `show` against the fresh profile, validate, render, oracle-diff
(including `configs/mpi/cray-mpich/toolchains.yaml`), build the mpi lane.
Note: the Blueback profile captured the system default CPE, which is now the
newest (ROCm 7-era) release — the known-good Kokkos baseline was built on the
previous CPE, so the oracle diff is structural (flavor paths, toolchain
binding), not version-exact.

## Deferred / open

- Compiler same-family multi-version disambiguation: two versions of one
  compiler family in a profile still resolve by first name match
  (`compiler_provider_for`); needs the same treatment MPI provider selection
  already has (candidates -> pin or hard error -> version-qualified identity).
  Prerequisite for the committed multi-CPE v1 goal.
- CPE-locked GPU/MPI pairing validation: profile facts (`cpe_version`,
  per-MPI GPU-runtime linkage) plus a render preflight that refuses
  cross-major toolkit/MPI pairings. Findings and sources:
  `stack-planning/docs/cpe_rocm_compatibility_note_v1.md`.
- GTL preload elimination: GPU-aware cray-mpich on Blueback currently needs an
  `LD_PRELOAD` of the GTL library; goal is to stop preloading (own package-repo
  GTL package, or site-style patches). Starting clue:
  https://github.com/llnl/benchpark/pull/1226. Not yet researched.
- `configs/common/packages.yaml.j2` sets the workspace `mpi` provider
  preference from the first rendered lane — same "first pick" shape the MPI
  version fix removed, one level up. Needs an explicit policy.
- Multi-CPE support is a v1 commitment (multiple CPE releases coexisting):
  needs version fan-out as a build axis and the deferred `cpe_version`
  pairing tag, on top of the two items above.
- `validate-template-set --concretize` remains intentionally deferred.
- Front-door compiler-init/lane module emission still needs real-system
  module-tool validation.
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
