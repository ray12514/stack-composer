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
- [ ] Expand `validate` to cover every v6 render invariant.

Current render coverage:

- Writes through a `.rendering` side path and atomically renames on success.
- Deletes partial side-path output on render failure.
- Renders Jinja config scopes and lane environments with `StrictUndefined`.
- Writes a schema-valid draft `release-manifest.yaml`.
- Plans lanes for the current reference contract vocabulary
  (`runtime_without_gpu`, `runtime_with_gpu`, Cray MPICH, package-set specs,
  and `per_gpu_arch`).
- Validates selected package repositories have `repo.yaml`, matching namespaces,
  and no duplicate namespaces.
- Validates package-set tier/kind compatibility and inline spec kind
  compatibility with the selected build class.
- Builds `dist/stack-composer-<version>.tar.gz` with `stack-composer.pyz`,
  project license, third-party manifest, and third-party license files.
- Regenerates third-party manifest/license texts from installed runtime
  distributions and enforces manifest consistency against `pyproject.toml`.

## Phase 2 - Maintainer Commands

- [ ] Implement `assess-profiles`.
- [ ] Implement `explain`.
- [ ] Implement `validate-template-set` render-only mode.

## Phase 3 - Scaffold And Publish

- [ ] Implement `scaffold-templates`.
- [ ] Implement `publish-manifest`.
- [ ] Implement the `spack-build` companion script.

## Phase 4 - Reference Fixture Acceptance

- [ ] Render every documented stack against every documented reference profile.
- [ ] Wire rendered workspace fixtures into CI validation.
