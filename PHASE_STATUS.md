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

## Phase 3 - Scaffold And Publish

- [x] Implement `scaffold-templates`.
- [x] Implement `publish-manifest`.
- [x] Implement the `spack-build` companion script.

## Phase 4 - Reference Fixture Acceptance

- [x] Render every documented stack against every documented reference profile.
- [x] Wire rendered workspace fixtures into CI validation.
