# Phase Status

Tracks progress against `stack-planning/docs/stack_composer_design_v1.md`.

## Phase 1 - Skeleton + Render Seam + Release Build

- [x] Create the `stack-composer/` repo with the planned Python layout.
- [x] Confirm Apache-2.0 as the project license.
- [x] Pick dataclasses/dicts + `fastjsonschema` instead of pydantic v2 to keep
  the eventual `.pyz` platform-neutral.
- [x] Package the six canonical schemas copied from `stack-planning/schemas/`.
- [x] Implement `cli.py` with all seven commands wired.
- [x] Implement top-level `--licenses` output from packaged metadata.
- [x] Implement schema loading and validation helpers.
- [x] Implement `validate` schema checks and initial render preflight checks.
- [x] Author complete third-party license generation/enforcement.
- [x] Author `scripts/build-pyz.sh` release packaging.
- [x] Implement deterministic render workspace writes for the initial fixture vocabulary.
- [x] Make `render` byte-identical for fixed fixture inputs.
- [x] Expand `validate` to cover every v6 render invariant.

Current render coverage:

- Writes through a `.rendering` side path and atomically renames on success.
- Deletes partial side-path output on render failure.
- Refuses existing workspaces unless overwrite is requested, and refuses stale
  `.rendering` side paths.
- Renders Jinja config scopes and lane environments with `StrictUndefined`.
- Writes a schema-valid draft `release-manifest.yaml`.
- Plans lanes for the current reference contract vocabulary
  (`runtime_without_gpu`, `runtime_with_gpu`, Cray MPICH, package-set specs,
  and `per_gpu_arch`).
- Renders both reference profiles in tests: Cray with GPU lanes and generic
  Linux with site MPI and a skipped non-required GPU build.
- Runs Phase 4 reference fixture acceptance through `validate-template-set`,
  covering every documented reference stack/profile pair and asserting the
  rendered lane matrices plus schema-valid draft manifests.
- Validates selected package repositories have `repo.yaml`, matching namespaces,
  and no duplicate namespaces.
- Validates package-set tier/kind compatibility and inline spec kind
  compatibility with the selected build class.
- Validates matching `per_system` narrowing axes against profile/contract
  resolved compiler, MPI, and GPU selector candidates.
- Surfaces required-build-cannot-resolve as `nodes_unmatched` /
  `requires_unsatisfied` (v6 invariants #10, #11) at validate time via
  `validate_lane_plan`.
- Emits `per_system_empty` when narrowing drops every lane of a required
  build (v6 invariant #14).
- Derives `platform_module_prereqs` per lane from profile facts and
  fails render/validate when a lane's compiler, MPI flavor, or GPU
  toolkit modules are not declared in the profile (v6 invariant #15).
- Requires `package_repositories[*].priority` to be set explicitly in
  stack source so shadow direction is recorded rather than defaulted
  (v6 invariant #7c).
- Builds `dist/stack-composer-<version>.tar.gz` with `stack-composer.pyz`,
  project license, third-party manifest, and third-party license files.
- Regenerates third-party manifest/license texts from installed runtime
  distributions and enforces manifest consistency against `pyproject.toml`.

## Phase 2 - Maintainer Commands

- [x] Implement `assess-profiles`.
- [x] Implement `explain`.
- [x] Implement `validate-template-set` render-only mode.

`validate-template-set --concretize` (Spack-driven concretize per lane)
remains deferred; the flag is wired but raises a clear "not implemented
in this phase" error.

Outstanding `assess-profiles` shape gap
(`stack_composer_design_v1.md` §`assess-profiles` algorithm sketch,
lines ~223-244):

- [ ] Per-cell output today carries `{covered, build_classes,
  toolchains, node_selectors, gpu_selectors, compilers,
  mpi_providers, gpu_arches}` — a broader per-axis breakdown. The
  design specifies `{covered: true, lane_count, lane_kinds}` for
  covered cells and `{covered: false, missing_facts,
  blocked_toolchains}` for uncovered cells. The current report is
  informational but is not the shape downstream maintainer tools
  agreed to. Need to add `lane_count` and `lane_kinds` (from a
  dry-resolve via `plan_lanes`), surface `missing_facts` (which
  profile keys would have to gain to flip an uncovered cell), and
  decide whether to keep the wider per-axis breakdown alongside or
  drop it.

`explain` was audited against the design's algorithm sketch and
matches: build_classes, toolchains (filter_resolvable), node_selectors,
gpu_arches, compilers, mpi_providers, and per_system_narrowing menu
when --stack is given.

## Phase 3 - Scaffold And Publish

- [x] Implement `scaffold-templates`.
- [x] Implement `publish-manifest`.
- [x] Implement the `spack-build` companion script.

Outstanding refinements in Phase 3:

- [ ] `publish-manifest` provenance bucket (`manifest/provenance.py::provenance_bucket`)
  is heuristic-driven: it classifies an external as `platform_backed`
  vs `site_external` by hardcoded path prefixes
  (`/opt/cray`, `/opt/rocm`, `/usr`). The design specifies the bucket
  is "derived from the lockfile **plus contract**"
  (`stack_composer_design_v1.md` line 654). Real-world site externals
  at non-canonical paths (e.g., `/shared/site/openmpi-5.0.9`,
  `/apps/cuda/12.4`) would misclassify today. Replace the path-prefix
  heuristic with a contract-driven lookup (e.g., walk
  `contract.toolchains[*]` / `profile.vendor_cray` /
  `profile.gpu_toolkit_modules` for known platform-backed prefixes).
- [ ] `spack-build` runs `spack verify manifest -a` which fails on
  system externals (they have no Spack manifest). The build itself
  succeeds; only the verify step trips. Filter externals from the
  verify-manifest invocation. Surfaced by the Phase 5 smoke pipeline.
- [ ] Scaffold-starter template-sets under
  `src/stack_composer/scaffold/starters/{library,application}/configs/`
  only ship `common/packages.yaml.j2` + `common/repos.yaml.j2`. Same
  scope-buildout gap as the v6 fixture. Tracked under Phase 5.

## Phase 4 - Reference Fixture Acceptance

- [x] Render every documented stack against every documented reference profile.
- [x] Wire rendered workspace fixtures into CI validation.

> Note: the Phase 4 acceptance covers that `validate-template-set` runs
> cleanly against the reference fixture. It does **not** prove the
> rendered configs are a v6-spec-conformant template set. Phase 5
> tracks that gap.

## Phase 5 - Render Seam Conformance With v6 Template-Set Spec

The shipped fixture template-set, the scaffold-templates starters, and
the scope-selection functions in `render/scopes.py` are all
stub-shaped relative to the v6 design specification. Phase 1's
"deterministic render workspace writes for the initial fixture
vocabulary" is met for the *fixture*, not for the *design*.

What the design requires
(`spack_stack_generation_design_v6.md` §2115-2233):

A v6-conformant template set must emit per-scope `packages.yaml` files
with `externals:` + `buildable: false` entries derived from the
profile:

- `configs/vendor/cray/packages.yaml` — `cce`, `gcc`, `rocmcc`, and
  optional `nvhpc` (Spack/compiler identity for current CPE
  `PrgEnv-nvidia` + `nvidia/<version>`)
  externals with `prefix`, `modules`, and (for compilers)
  `extra_attributes.compilers` from `profile.vendor_cray.<name>`.
- `configs/vendor/linux/packages.yaml` — `gcc`/`aocc`/`intel`/`nvhpc`
  externals from `profile.compilers_external`.
- `configs/mpi/cray-mpich/packages.yaml` — per-compiler-flavor
  `cray-mpich` externals from
  `profile.vendor_cray.cray_mpich.flavors`, plus the `mpi: provides`
  binding.
- `configs/mpi/<provider>/packages.yaml` — site MPI external from
  `profile.mpi[]`.
- `configs/gpu/amd-rocm/packages.yaml` — every component listed in
  `profile.gpu_toolkit_modules.rocm.spack_components` (`hip`,
  `hsa-rocr-dev`, `comgr`, `rocblas`, `hipblas`, `hipsparse`,
  `rocprim`, `llvm-amdgpu`, ...) as a `buildable: false` external.
- `configs/gpu/nvidia-cuda/packages.yaml` — CUDA toolkit externals
  from `profile.gpu_toolkit_modules.cudatoolkit`. Current Cray CPE
  uses `cuda/<version>` module naming; legacy `PrgEnv-nvhpc` is out of
  v1 scope unless a target site requires a future compatibility
  extension.
- `configs/target/<arch>/packages.yaml` — `packages.all.require:
  target=<arch>` per `lane.target`.
- `configs/os/<os>/packages.yaml` — `openssl`, `curl`, etc. system
  externals.

And selects only the scopes a given lane needs:

- `required_scopes(profile, rendered_lanes)` — design signature, line
  2621. Current code: `required_scopes(template_dir)`. Returns every
  subdir of `configs/` regardless of profile or lane.
- `scopes_for_lane(lane, stack, profile)` — design signature, line
  2637. Current code: `scopes_for_lane(rendered_scopes)`. Returns
  every scope for every lane.

Work items

- [x] Rewrite `render/scopes.py::required_scopes` to take
  `(profile, rendered_lanes)` and select scopes by profile facts +
  lane axes (compiler family, MPI provider, GPU vendor, target arch,
  OS).
- [x] Keep GPU toolkit scope selection independent from host compiler:
  general-purpose Cray PE hosts (`PrgEnv-gnu`, `PrgEnv-cray`,
  `PrgEnv-aocc`, or another site-verified general host) can compose
  with ROCm/CUDA toolkit scopes when the profile and template contract
  allow them.
  `PrgEnv-amd`/`PrgEnv-nvidia` remain explicit ROCmCC/NVHPC exception
  lanes, not defaults.
- [x] Rewrite `render/scopes.py::scopes_for_lane` to take
  `(lane, stack, profile)` and emit lane-specific include ordering
  per v6 §Lane Render Order (common → os → target → vendor → mpi →
  gpu).
- [x] Build `tests/fixtures/template-sets/v6/configs/vendor/cray/packages.yaml.j2`
  rendering `cce`, `gcc`, `rocmcc` externals from
  `profile.vendor_cray.<compiler>` (`prefix`, `modules`,
  `extra_attributes.compilers`).
- [x] Build `tests/fixtures/template-sets/v6/configs/vendor/linux/packages.yaml.j2`
  rendering compiler externals from `profile.compilers_external`.
- [x] Build `tests/fixtures/template-sets/v6/configs/mpi/cray-mpich/packages.yaml.j2`
  rendering per-compiler-flavor cray-mpich externals from
  `profile.vendor_cray.cray_mpich.flavors`.
- [x] Build `tests/fixtures/template-sets/v6/configs/mpi/openmpi/packages.yaml.j2`
  rendering site openmpi external from `profile.mpi[]`.
- [x] Build `tests/fixtures/template-sets/v6/configs/gpu/amd-rocm/packages.yaml.j2`
  rendering every `profile.gpu_toolkit_modules.rocm.spack_components[*]`
  as a `buildable: false` external with `prefix` and the toolkit
  `module`.
- [x] Build `tests/fixtures/template-sets/v6/configs/gpu/nvidia-cuda/packages.yaml.j2`
  for NVIDIA CUDA toolkit externals. Keep NVHPC as compiler identity
  in vendor scopes / exception lanes, not as a second default GPU
  toolkit scope.
- [x] Build `tests/fixtures/template-sets/v6/configs/target/<arch>/packages.yaml.j2`
  per documented architecture (zen3, zen4, x86_64_v3, ...).
- [x] Build `tests/fixtures/template-sets/v6/configs/os/<os>/packages.yaml.j2`
  for the documented OS families.
- [x] Mirror the same scope buildout in the scaffold starters under
  `src/stack_composer/scaffold/starters/{library,application}/`.
- [x] Add render tests asserting the existing fixture coverage: Cray + AMD GPU
  renders `cray-mpich` and ROCm component externals with `buildable: false`,
  generic Linux renders site OpenMPI with `buildable: false`, and lanes include
  only the scopes they consume.
- [x] Add remaining render tests asserting that:
  - A Cray + NVIDIA-GPU lane uses current CPE naming
    (`PrgEnv-nvidia`, `nvidia/<version>`, `cuda/<version>`) and not
    legacy `PrgEnv-nvhpc`.
  - Cray GPU lanes using GNU/CCE/AOCC or another site-verified general
    host compiler still select the same ROCm/CUDA toolkit scopes;
    GPU-aware ROCmCC/NVHPC lanes are explicit exceptions.
  - Generic Linux AMD/NVIDIA GPU lanes select GPU toolkit scopes
    independently from Cray platform scopes.

Acceptance per v6 design

- [x] The rendered `configs/vendor/cray/packages.yaml` matches the
  design example at §2115-2141 (modulo profile-specific
  versions/prefixes; small cosmetic differences: spec values quoted,
  modules emitted block-style).
- [x] The rendered `configs/mpi/cray-mpich/packages.yaml` matches the
  design example at §2148-2168.
- [x] Re-running the smoke pipeline against a Cray-shaped profile
  produces a workspace whose `spack concretize` loads and recognizes
  `cray-mpich`, `cce`, and the ROCm components by name from the
  rendered externals. Verified 2026-06-20: Spack's concretizer
  identifies all declared externals before tripping on cross-arch
  target compatibility (a smoke-environment quirk tracked under
  Phase 6).

## Phase 6 - Post-v6 polish and pre-CPE2 hardening

Phase 5 closed the render-seam conformance with the v6 spec. This
phase covers the follow-ups surfaced during Phase 5 (the smoke
concretize loop revealed two real gaps), the triage findings from
Phase 2 and Phase 3, and the pre-CPE2 hardening work from
`stack-planning/docs/cray_pe_coupling_inventory.md`.

These items are independent. An agent picking up this phase can take
any one bullet without touching the others.

### 6a - Package-set GPU-vendor neutrality

The `science-full.yaml` package set's `gpu` kind used to hardcode
`+rocm` specs (`kokkos+rocm`, `raja+rocm`). A real production package
set shared across AMD and NVIDIA GPU lanes should declare GPU-aware
specs once, and render should compose the right variant per the lane's
`gpu_arch`.

- [x] Decide the schema shape. Options sketched in
  `cray_pe_coupling_inventory.md` §"Recommended hardening work" but
  not yet decided. Chosen shape: package sets declare `+gpu` as a
  placeholder variant; render expands it to `+rocm` or `+cuda` plus
  the lane architecture flag based on `lane.gpu_arch`.
- [x] Implement the chosen shape in `model/package_set.py` and the
  fixture `science-full.yaml`.
- [x] Update `tests/test_render_scopes.py` to assert that the NVIDIA
  lane gets `cuda_arch=...` on GPU-aware specs (the assertion we
  dropped to land Phase 5 because the fixture has no `+cuda` specs).
- [x] Smoke verify: a Cray + NVIDIA profile + the updated science-full
  package set produces a GPU lane whose specs carry `+cuda
  cuda_arch=<arch>` exactly where expected. Verified 2026-06-20:
  rendered AMD lane in the smoke container shows
  `kokkos+rocm amdgpu_target=gfx90a` and
  `raja+rocm amdgpu_target=gfx90a` with non-GPU specs (gsl, hdf5,
  netcdf-c, parallel-netcdf, tau+mpi) emitted unchanged; the parallel
  NVIDIA case is exercised by
  `tests/test_render_scopes.py::test_rendered_cray_nvidia_workspace_uses_current_cpe_names`
  asserting `kokkos+cuda cuda_arch=80`. Spack concretize against the
  AMD lane recognizes all rendered externals by name (hip,
  hsa-rocr-dev, llvm-amdgpu, rocprim, cray-mpich, cce, gcc) before
  tripping on cross-arch target compatibility — the Phase 6b gap.

Acceptance:

- A single GPU-aware spec in the package set (`kokkos`) yields
  `kokkos+rocm amdgpu_target=gfx90a` on a `gfx90a` lane and
  `kokkos+cuda cuda_arch=80` on a `sm_80` lane, without duplicating
  the spec in the package set.

### 6b - Cross-architecture smoke concretize

The Phase 5 smoke pipeline runs in a rocky9 container with whatever
CPU the host happens to have. Rendering against a Cray `example-cray`
profile produces a workspace whose `configs/target/zen3/packages.yaml`
sets `target=zen3`. Spack's concretizer rejects that when the build
host's CPU isn't zen3 ("target=zen3 is not compatible with this
machine"). That is correct production behaviour - real Cray
deployments concretize on zen3 hosts - but it blocks the smoke loop
from going past concretize for cross-arch profiles.

- [ ] Add a `--cross-arch` (or equivalent) flag to the smoke runner
  that injects
  `config:concretizer:targets:host_compatible:false` into a
  `configs/common/concretizer.yaml.j2` (or equivalent overlay) when
  set, so smoke concretize succeeds against Cray-shaped profiles on a
  non-Cray host.
- [ ] Alternatively, expose this as a render-time stack option (e.g.,
  `stack.smoke.cross_arch: true`) so the renderer emits the override
  in the workspace. This keeps the runner thin but couples the stack
  source to a smoke concern. Decide one.
- [ ] Run a full smoke loop end-to-end (`render` + `concretize` + at
  least one lockfile inspection) against a Cray profile in the smoke
  container.

Acceptance:

- The smoke runner's `pipeline` action against a Cray-shaped profile
  exits 0 through concretize, and the resulting lockfile lists
  `cray-mpich`, `cce`, and the ROCm components with `external: true`.

### 6c - assess-profiles output shape conformance

Surfaced during the Phase 2 triage (see Phase 2 section above).

- [ ] Compute `lane_count` and `lane_kinds` per cell via a dry-resolve
  against `plan_lanes`.
- [ ] Compute `missing_facts` per uncovered cell: enumerate which
  profile fields would need values for the cell to flip to covered.
- [ ] Decide whether to keep the current wider per-axis breakdown
  alongside the design-specified `{covered, lane_count, lane_kinds,
  missing_facts, blocked_toolchains}` shape, or drop it.
- [ ] Update `tests/test_assess_profiles.py` for the new shape.

Acceptance:

- `assess-profiles --output report.yaml` produces a report whose
  per-cell structure matches `stack_composer_design_v1.md`
  §`assess-profiles` algorithm sketch (lines ~223-244) exactly for
  the covered and uncovered branches.

### 6d - publish-manifest provenance from the contract

Surfaced during the Phase 3 triage (see Phase 3 section above).

- [ ] Replace the path-prefix heuristic in
  `manifest/provenance.py::provenance_bucket` with a contract-driven
  lookup. The contract already knows which externals come from
  platform packages (`vendor_cray.*`, `gpu_toolkit_modules.*`) versus
  site externals (`compilers_external`, `mpi[]`). Walk the contract
  and the profile blocks the lockfile spec was resolved against,
  classify by that, not by `/opt/cray` / `/opt/rocm` / `/usr`.
- [ ] Add tests covering a site external at a non-canonical path
  (e.g., `/shared/site/openmpi-5.0.9`) and confirm it classifies as
  `site_external`, not `platform_backed`.

Acceptance:

- A lockfile whose `cray-mpich` external prefix is at an unusual path
  (e.g., `/scratch/test-cray-pe/mpich`) still classifies as
  `platform_backed` because the contract identifies `cray-mpich` as a
  platform provider, not because of the path string.

### 6e - spack-build verify-manifest external filter

Surfaced during the Phase 3 triage and seen again in the Phase 5
smoke loop.

- [ ] `scripts/spack-build` runs `spack verify manifest -a` which
  fails on system externals (gcc at `/usr` in the smoke container).
  Filter externals from the verify-manifest invocation. Likely
  approach: enumerate non-external installed specs via `spack -e
  <env> find --json`, parse out externals (specs with `external` key
  set), pass the remaining specs explicitly to `spack verify manifest
  <spec>...`.
- [ ] Smoke-verify: the Phase 5 smoke loop's verify-manifest step
  passes against the example-cray workspace.

Acceptance:

- `spack-build --workspace <rendered>` exits 0 on a workspace with
  externals; reports show `verify-manifest: passed` per lane.

### 6f - Pre-CPE2 hardening (vendor selection, MPI generalization, compiler enumeration)

From `stack-planning/docs/cray_pe_coupling_inventory.md`
§"Recommended hardening work" - three changes that significantly
reduce the eventual CPE2 migration sprint. Independent of each other
and of 6a-6e.

- [ ] **6f.1**: Lift vendor scope selection from
  `render/scopes.py::vendor_scope` into the contract. Today it is
  hardcoded: `if profile.vendor_cray: return "vendor/cray" else
  "vendor/linux"`. After this change, a third or fourth vendor scope
  (CPE2, IBM, Intel Aurora) is purely a template-set and contract
  addition; no Python change needed. See coupling inventory for the
  proposed contract schema field.
- [ ] **6f.2**: Generalize `render/platform_modules.py::_mpi_modules`
  out of its `if provider == "cray-mpich": ...` special case. Each
  MPI provider should describe its own `modules:` and optional
  `flavors:` block in `profile.mpi[]`. The renderer becomes
  provider-agnostic. May require a profile-v2 schema migration for
  the MPI block, depending on the chosen shape.
- [ ] **6f.3**: Replace the hardcoded compiler-name tuple
  `("gcc", "cce", "aocc", "intel", "nvhpc", "rocmcc")` in
  `render/plan.py:141-149`, `scaffold/facts.py:9-10`, and
  `commands/explain.py:87` with a schema-driven enumeration. Define
  the non-compiler exclusion list (e.g., `pe_version`, `cray_mpich`,
  `libsci`, `cce_extras`) in one place.

Acceptance:

- Adding a new vendor (call it `vendor_cpe2`) to the profile schema
  requires:
  - A new template-set scope `configs/vendor/cpe2/packages.yaml.j2`.
  - A contract entry naming `vendor_cpe2` as a discriminator for the
    `vendor/cpe2` scope.
  - Zero Python edits in stack-composer's `render/` tree.

### 6g - Coupling inventory upkeep

- [ ] Each time a change touches a spot listed in
  `stack-planning/docs/cray_pe_coupling_inventory.md`, the change
  also updates the inventory's file:line references. Enforce in PR
  review (a one-line CONTRIBUTING note or a pre-commit grep that
  flags PRs touching listed files without updating the inventory).
- [ ] Periodically (every release) audit the inventory for new spots
  that drifted in.

Acceptance:

- The inventory is current as of the latest release tag. A
  `git grep -l "cray" src/ tests/` cross-referenced against the
  inventory shows no missing entries.

## Phase 7 - Adoption-blocking scopes (config.yaml, compilers.yaml, foundation lane)

The 2026-06-20 design-vs-implementation coverage audit
(`stack-planning/docs/design_implementation_coverage.md` §6) found
five CRITICAL gaps that block the first real-system deployment.
Phase 7 closes the three that touch config scopes; Phase 8 closes the
foundation-pin work; Phase 9 closes front-door modules.

- [ ] Render `configs/common/config.yaml` from
  `profile.filesystem.install_tree_candidates`,
  `profile.node_types[*].build_stage`,
  `profile.filesystem.source_cache_candidate`, and
  `profile.filesystem.buildcache_candidate`. Without this, Spack
  installs to `/home/spack/spack/opt` (its default), not the
  profile's declared install tree. Every real deployment hits this on
  first install.
- [ ] Verify whether Spack v1.1's compiler discovery from
  `packages.yaml::extra_attributes.compilers` (Phase 5 work) is
  sufficient or whether a separate `configs/common/compilers.yaml`
  scope is still needed. If needed, render it from
  `profile.vendor_cray.<compiler>` and `profile.compilers_external`.
- [ ] Add `include_concrete:` references from each lane's
  `spack.yaml` to its compiler's Core lane (v6 §"GPU lane Core
  composition"). Today the GPU lane environment doesn't reference
  `gcc/core` even though the design requires it.

Acceptance:

- A smoke pipeline run installs Spack-built packages into
  `/shared/stack/spack/opt` (the example profile's install tree),
  not Spack's default.
- `spack -e <lane> compiler list` inside the rendered workspace
  enumerates the profile's compilers without an additional
  `spack compiler find` step.
- The GPU lane's `spack.yaml` shows `include_concrete:` referencing
  the matching `<compiler>/core` lane.

## Phase 8 - Foundation pins + foundation lane

- [ ] Render `configs/foundation/packages.yaml.j2` (or equivalent
  scope) emitting `require: "@<version>"` for each
  `stack.foundation_pins.*` entry (zlib, xz, zstd, plus any other
  declared pins). v6 §"Foundation lane" is explicit that these are
  load-bearing for cross-compiler binary compatibility; today they
  are emitted nowhere.
- [ ] Render the foundation lane environment (single lane, single
  compiler, single target) and wire it into the Core composition so
  every Core lane `include_concrete` references it.
- [ ] Implement `contract.target_policies` so the foundation lane's
  target is `foundation` / `baseline_target` (e.g., `x86_64_v3`) and
  payload lanes' target is `lane.cpu.preferred` (e.g., `zen3`). v6
  §"Target Policy" is explicit; renderer ignores the contract field
  today.

Acceptance:

- Foundation lane renders for every reference profile and pins
  declared foundation packages.
- A Core lane's resolved zlib hash equals the foundation lane's
  zlib hash (cross-compiler reproducibility).

## Phase 9 - Module emission (init, front-door, direct, package)

Covered in detail in agent memory `project_module_emission_gap.md`
and in `stack-planning/docs/design_implementation_coverage.md`
§4-5.

The v6 design (§1475-1485 and §4380-4480) names **exactly two
exposure scenarios**, both rendered by stack-composer:

**Scenario A - `front_door` (e.g., ScienceStack):**

- `modules.init_module` is the bootstrap surface (e.g.,
  `science-stack-init`). User runs `module load science-stack-init`
  once; it sets `MODULEPATH` to point at this release's modules
  directory. Required when the site doesn't already have the
  release's modules in its global MODULEPATH.
- `modules.module_root` is the lane namespace exposed after the
  bootstrap (e.g., `ScienceStack/GCC/mpi-craympich-gfx90a`). One
  front-door modulefile per rendered lane.
- User flow: `module load <init_module>` ->
  `module load <module_root>/<COMPILER>/<lane>` ->
  `module load <package>`.

**Scenario B - `direct` (e.g., fun3d):**

- `modules.init_module` is null. No bootstrap module is rendered.
- `modules.publish_root` is an existing site MODULEPATH root the
  site already has wired in (e.g., `/opt/site/modulefiles`).
- Per-package modules render directly into `publish_root` (e.g.,
  `fun3d/14.2-gpu-gfx90a`), carrying their lane's provenance,
  conflict, and prereq lines themselves (since there is no separate
  front-door gate).
- User flow: `module load fun3d/14.2-gpu-gfx90a`.

Both scenarios are entirely inside stack-composer. There is no
separate site-authored outer module to wire in - the documented
`init_module` IS the gateway for Scenario A, and the site's existing
`publish_root` IS the gateway for Scenario B.

Work items:

- [ ] Add `templates/<set>/configs/common/modules.yaml.j2` rendering
  hierarchy, projections, prefix inspections, and exclusion lists
  from `stack.modules.{hierarchy_style, expose_provenance,
  platform_module_policy}` so `spack module tcl refresh` projects
  package modules at the expected paths.
- [ ] Add `templates/<set>/modules/init/<format>.j2` for Scenario A:
  one per-release init modulefile that prepends the release's
  modules directory to MODULEPATH. Renders only when
  `modules.init_module` is non-null and `modules.exposure:
  front_door`.
- [ ] Add `templates/<set>/modules/front_door/<format>.j2` for
  Scenario A: per-lane front-door modulefile under
  `<module_root>/<COMPILER>/<lane>`. Emits MODULEPATH prepend for
  the lane's package module root, conflicts with sibling lanes,
  prereq lines for `lane.platform_module_prereqs` (driven by
  `modules.platform_module_policy`), identity setenv (release,
  lane, compiler, view path).
- [ ] Add `templates/<set>/modules/direct/<format>.j2` for Scenario
  B: per-public-package application modulefile under
  `publish_root/<package>/<version>`. Carries the same conflict,
  prereq, and provenance lines that the front-door would otherwise
  carry, since there's no separate gate.
- [ ] Walk `lane.platform_module_prereqs` into the rendered
  modulefiles (data is already in the render context; just needs a
  template consumer).
- [ ] Tests:
  - Rendered Scenario A front-door modulefile for a Cray + ROCm
    lane contains `prereq PrgEnv-gnu`, `prereq gcc-native/13`,
    `prereq rocm/<v>`, `prereq cray-mpich/<v>` and declares
    conflict with sibling GPU lanes.
  - Rendered Scenario A init modulefile sets MODULEPATH to the
    release's modules dir.
  - Rendered Scenario B direct modulefile for fun3d carries the
    same prereq and identity lines but no front-door gate.
- [ ] Smoke verify: in the smoke container,
  `module load <init_module>` followed by
  `module load <module_root>/GCC/gpu-craympich-gfx90a` succeeds and
  sets the expected MODULEPATH (Scenario A); separately, render the
  fun3d application example and assert the direct modulefile is in
  the expected location with the expected contents (Scenario B).

Acceptance:

- `modules.exposure: front_door` produces a working init module +
  per-lane front-door modulefiles (Scenario A).
- `modules.exposure: direct` produces working per-package direct
  modulefiles in `publish_root` with no init or front-door
  (Scenario B).
- A stack switching `modules.exposure` from `front_door` to
  `direct` re-renders cleanly with no carry-over.

## Phase 10 - Externals policy + buildcache mirrors

- [ ] `stack.externals.{compilers,mpi,openssl,curl,fabric_userspace,gpu_toolkit}`
  policy enforcement at render time. Today every Phase 5 scope
  renders externals unconditionally as `buildable: false`. The
  policy should gate which scopes get emitted (e.g.,
  `gpu_toolkit: build_all` should suppress `configs/gpu/amd-rocm/`
  so Spack builds ROCm).
- [ ] Render `configs/common/mirrors.yaml` from
  `stack.buildcache.{spack_generation, foundation_lane,
  payload_lane}` format strings with `{os_id}`, `{glibc}`,
  `{spack_version}`, `{package_repo_generation}`,
  `{baseline_target}`, `{system}` substitutions per v6
  §"Build-Cache Keying".
- [ ] Render `configs/common/concretizer.yaml` with `unify: false`
  for stack lanes per v6 §"Concretizer Posture".
- [ ] Add `vendor_cray.libsci` rendering as a scope.
- [ ] Render `profile.fabric.userspace` (libfabric, ucx) externals
  as a scope.

Acceptance:

- Setting `stack.externals.gpu_toolkit: build_all` in the smoke
  stack causes Spack to build ROCm from source.
- The rendered `mirrors.yaml` has fully-expanded buildcache URLs
  matching the design's keying scheme.

## Phase 11 - Cleanup and advisory clarifications

- [ ] Decide and document the behaviour of `stack.helpers.*`
  advisory flags - either implement them or remove them from the
  schema.
- [ ] Read `gpu_selectors[*].vendor` and `.spack` from the contract
  (currently inferred from arch prefix in Python).
- [ ] Render `gpu_toolkit_modules.nvhpc` as a separate scope for
  standalone NVHPC toolkit lanes.
- [ ] Add new `configs/mpi/<provider>/packages.yaml.j2` scopes for
  mpich, mvapich2, intel-mpi as profiles surface them.
- [ ] Implement `stack.release.retain_previous` cleanup (publish
  step deletes N-previous releases).
- [ ] Implement `stack.release.promotion: gated_manual` promotion
  gate in publish-manifest.

## Cross-cutting: ongoing audit discipline

After Phase 7-11 lands, run the audit again. The procedural lesson
from Phase 4/5 (claimed done, fixture didn't match design) and
Phase 5+ (entire stack.yaml blocks silently ignored) is the same:
**every PHASE_STATUS box needs a design-doc reference.** Going
forward, no box gets checked without citing the design section it
implements; the design vs implementation coverage doc is the
audit-trail artifact.
