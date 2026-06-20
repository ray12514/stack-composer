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

- `configs/vendor/cray/packages.yaml` — `cce`, `gcc`, `rocmcc`
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
- `configs/gpu/{cuda,nvhpc}/packages.yaml` — corresponding NVIDIA
  toolkit externals from `profile.gpu_toolkit_modules.cudatoolkit` /
  `nvhpc`.
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

- [ ] Rewrite `render/scopes.py::required_scopes` to take
  `(profile, rendered_lanes)` and select scopes by profile facts +
  lane axes (compiler family, MPI provider, GPU vendor, target arch,
  OS).
- [ ] Rewrite `render/scopes.py::scopes_for_lane` to take
  `(lane, stack, profile)` and emit lane-specific include ordering
  per v6 §Lane Render Order (common → os → target → vendor → mpi →
  gpu).
- [ ] Build `tests/fixtures/template-sets/v6/configs/vendor/cray/packages.yaml.j2`
  rendering `cce`, `gcc`, `rocmcc` externals from
  `profile.vendor_cray.<compiler>` (`prefix`, `modules`,
  `extra_attributes.compilers`).
- [ ] Build `tests/fixtures/template-sets/v6/configs/vendor/linux/packages.yaml.j2`
  rendering compiler externals from `profile.compilers_external`.
- [ ] Build `tests/fixtures/template-sets/v6/configs/mpi/cray-mpich/packages.yaml.j2`
  rendering per-compiler-flavor cray-mpich externals from
  `profile.vendor_cray.cray_mpich.flavors`.
- [ ] Build `tests/fixtures/template-sets/v6/configs/mpi/openmpi/packages.yaml.j2`
  rendering site openmpi external from `profile.mpi[]`.
- [ ] Build `tests/fixtures/template-sets/v6/configs/gpu/amd-rocm/packages.yaml.j2`
  rendering every `profile.gpu_toolkit_modules.rocm.spack_components[*]`
  as a `buildable: false` external with `prefix` and the toolkit
  `module`.
- [ ] Build `tests/fixtures/template-sets/v6/configs/gpu/cuda/packages.yaml.j2`
  and `configs/gpu/nvhpc/packages.yaml.j2` for NVIDIA toolchains.
- [ ] Build `tests/fixtures/template-sets/v6/configs/target/<arch>/packages.yaml.j2`
  per documented architecture (zen3, zen4, x86_64_v3, ...).
- [ ] Build `tests/fixtures/template-sets/v6/configs/os/<os>/packages.yaml.j2`
  for the documented OS families.
- [ ] Mirror the same scope buildout in the scaffold starters under
  `src/stack_composer/scaffold/starters/{library,application}/`.
- [ ] Add render tests asserting that:
  - A Cray + AMD-GPU lane renders `cray-mpich` and ROCm components
    with `buildable: false`.
  - A generic-Linux lane renders site openmpi as `buildable: false`
    and does not include `configs/vendor/cray/`.
  - A lane includes only the scopes it consumes (no leaked
    cross-vendor scope).

Acceptance per v6 design

- The rendered `configs/vendor/cray/packages.yaml` matches the design
  example at §2115-2141 byte-for-byte (modulo profile-specific
  versions/prefixes).
- The rendered `configs/mpi/cray-mpich/packages.yaml` matches the
  design example at §2148-2168.
- Re-running the smoke pipeline (local-only Docker runtime; see
  agent memory for the location) against a Cray-shaped profile
  produces a lane whose `spack concretize` resolves `cray-mpich`,
  `cce`, and ROCm components to externals rather than Spack-building
  them.
