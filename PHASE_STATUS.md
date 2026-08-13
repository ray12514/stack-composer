# Phase Status

Current branch: `codex/simplified-render-plan`.

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
- `render-static`: reusable, include-ready Spack configuration catalogs from a
  Cluster Inspector profile, independent of managed stack lanes and deployment
  roots.
- `publish-manifest`: finalizes a draft manifest from downstream build evidence.
- `spack-build`: local Spack-driving companion script.
- Front-door Tcl modulefiles are rendered under the workspace's `modulefiles/`
  tree: compiler surface modules such as `cse/GCC`, plus short lane selectors
  such as `MPI` in the compiler-specific lane MODULEPATH. Spack still generates package modulefiles into
  each lane's `package_module_root`.
- Front-door platform prerequisites support explicit `prereq` and `autoload`
  policy. `autoload` emits `module load`; `prereq` requires the operator or
  user environment to have loaded the platform module already.
- Generic provider inventory consumption: `compiler_providers` +
  `mpi_providers`.
- Observed provider identities are translated at one renderer seam when Spack
  uses a different package name. Current mappings cover Classic Intel
  (`intel` -> `intel-oneapi-compilers-classic`), LLVM-based Intel
  (`oneapi` -> `intel-oneapi-compilers`), and Intel MPI
  (`intel-mpi` -> `intel-oneapi-mpi`). Static catalog paths retain the observed
  identity and their manifests record the Spack package identity.
- Cray MPICH scopes retain the inspected, non-buildable Cray PMI external that
  the pinned provider recipe requires. The common scope supplies the inspected
  platform libfabric external; neither runtime is replaced by a source build.
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

## Where we left off (2026-07-12)

Blueback and Raider have both exercised the profile -> validate/render ->
concretize/build path. The local Rocky/Spack smoke also has concrete core,
serial, and MPI lockfiles. Current local hardening adds clear ambiguity errors
for compiler version prefixes, merges repeated Cray MPICH flavor module
evidence, and validates the configured front-door autoload behavior.

The local Tcl/Lmod acceptance now passes compiler surface -> lane selection,
MODULEPATH wiring, and rejection of a mutually exclusive sibling lane. The
Docker smoke runner uses each rendered environment's module root rather than a
test-only global root. Lane selectors live directly in the compiler-specific
lane MODULEPATH (`Serial`, `MPI`, `GPU`); nesting them under the compiler init
name caused an Lmod reload storm and is prohibited. Actual package-module
visibility remains gated on completing the local concretization and module
refresh after a rerender.

## Full-render production-readiness audit (2026-08-05)

The current `render` implementation has the intended high-level ownership
boundaries: one environment per Core/Common/Serial/MPI/GPU build surface,
compiler and MPI selection through profile/defaults/stack inputs, projected
views, Spack-owned package-module generation, a compiler front door, and
mutually exclusive Serial/MPI/GPU selectors. `scripts/spack-build` already
regenerates each environment's view and runs `spack module tcl refresh` after
installation.

That output is suitable for the current platform-external pilot tests, but it
is not yet the final Spack 1.2 full-deployment shape described in
`stack-planning/docs/spack_1_2_rendered_environment_reference_v1.md`. The full
renderer must be updated as one coherent slice:

- emit one native `modules.yaml` scope per environment instead of embedding
  module policy in every `spack.yaml`;
- render Foundation/Core and stack-built MPI producers as Spack 1.2 groups
  with explicit `needs` relationships, and render a separate bootstrap
  environment plus fixed external view for a stack-built compiler;
- bind every payload lane, including Serial, to an explicit compiler-only or
  compiler-plus-MPI toolchain rather than relying on package preference;
- express GPU's MPI-superset roster as declarative package-set composition;
  the CSE pilot currently repeats the MPI roster in `science-full.yaml`, which
  works but can drift;
- encode and test version-sensitive module relationships for public
  multi-version packages so incompatible roots cannot be loaded together;
- complete end-to-end package-module visibility checks after install, view
  regeneration, and module refresh on both generic Linux and Cray fixtures;
- replace the first-rendered-lane MPI preference with explicit policy and add
  the remaining CPE/MPI/GPU compatibility and multi-CPE axes.

`init-workspace` is a CSE pilot convenience only. It is not a third production
render mode. The supported long-term seams remain `render-static` for reusable
platform scopes and `render` for complete managed deployments; the pilot
command can be removed after the static/manual and full-render procedures are
fully documented and exercised.

## Deferred / open

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
- Front-door compiler-init/lane selection passed the Docker/Lmod
  `module-smoke`; package-module visibility after a fresh concretization and
  real-system module-tool validation remain.
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

## Hand-maintained against the package sets (2026-07-14)

Three artifacts restate the roster and none of them are generated from it, so
a roster change means touching all of them in the same commit:

- `stack-content/package-sets/{core-foundation,science-full}.yaml` (the source
  of truth),
- `stack-planning/presentations/make_lanes_model_deck.py` (appendix tables),
- `stack-planning/docs/package_placement_map_v1.html` (per-package map).

Generating the last two from the package sets would remove the drift risk.
Not worth it while the roster is still moving; revisit if it outlives the
pilot. This note stays internal: the deck and the map are audience-facing and
carry no process bookkeeping.
