# Phase Status

Current branch: `codex/simplified-render-plan`.

This is the current pre-v1 implementation status. No released v1 behavior is
being preserved as a final product contract. Existing CSE trial workspaces,
locks, and caches must nevertheless remain usable during stabilization.

## Product model

- `render-static` produces reusable, include-ready Spack platform scopes from
  one reviewed Cluster Inspector profile. It contains no package intent,
  deployment roots, environment, lane, view, operational module tree, or build
  workspace.
- `publish-static` promotes one exact reviewed static catalog into a versioned,
  consumer-readable release. It does not rerender platform facts or add package
  intent.
- `render` produces the complete managed workspace from `profile.yaml`,
  `deployment.yaml`, `defaults.yaml`, `stack.yaml`, package content, and the
  active template set. It stops at the workspace handoff and never runs Spack.
- `init-workspace` is a supported blueprint assembler. It combines an authored
  blueprint, explicit values, and one exact static catalog. It does not resolve
  a second lane-planning language or replace full `render`. Broader Foundation
  reuse remains a separate post-trial design change.

Cluster Inspector owns observed facts. Stack Content owns authored inputs and
templates. Stack Composer consumes only explicit inputs and never probes the
machine. A downstream build path owns concretization, fetch, install, module
refresh, verification, and buildcache publication.

## Implemented

- Packaged schemas for profile, defaults, deployment, stack, package sets, and
  release manifests, with cross-repository schema drift checks.
- Deterministic `validate`, `show`, `render`, `render-static`, `publish-static`,
  `init-workspace`, `validate-template-set`, and `publish-manifest` command
  paths.
- Owned staging and recoverable replacement for full/static rendering and
  initialization, with strict template variables and duplicate-key rejection.
  Failed replacement restores the previous output; an unsuccessful rollback
  retains a named recovery tree. No portable power-loss guarantee is claimed.
- Deployment/package-repository digests in new full-render manifests and
  blueprint/template/data/catalog/value digests in new initialization manifests.
  Existing trial manifests remain readable without regeneration.
- Generic compiler, MPI, GPU, OS, target, external-package, view, and
  front-door module planning from profile/defaults/stack/deployment inputs.
- Provider identity and package-layout translation at one adapter seam when
  Spack differs from observed facts: Classic Intel, LLVM-based oneAPI, Intel
  MPI, and oneAPI component-prefix normalization to the Spack suite root while
  preserving exact driver paths.
- Static catalogs that retain the exact reviewed profile, compiler scopes,
  compiler-specific MPI scopes and toolchains, platform/common/GPU scopes,
  recommendations, and a machine-readable plan.
- Relocatable static catalog manifests and README examples, plus immutable
  versioned public promotion with approval metadata, a SHA-256 inventory,
  CSE-group management access, outside-consumer read access, and an optional
  relative `current` pointer.
- Published-catalog checksum verification and approval provenance in
  `init-workspace`.
- Unresolved MPI/compiler observations are a static-render error. They are not
  emitted as `unpaired` scopes.
- Cray MPICH catalog scopes preserve the physical compiler-family baseline from
  the product tree and record compatible observed compilers separately. The
  consuming environment selects the exact compiler.
- Selected Cray MPICH is rendered as a non-buildable platform leaf. Its
  inspected Cray PMI record remains in the provider scope, and the selected
  platform libfabric record/runtime path is carried into the MPI build
  environment without converting either runtime into a source build.
- Initial Conversion Trials workspace initialization validates catalog scope
  selections, snapshots the catalog when the blueprint requests it, preserves
  executable templates, and can apply the declared modes to the new workspace
  without changing ownership or unrelated paths.
- Platform-neutral `.pyz` release packaging, exact runtime dependencies,
  third-party license checks, and the shipped `spack-build` companion.
- Clean release staging with byte-exact source/wheel/archive inventory checks.
- The companion preserves existing locks unless `--reconcretize` is explicit,
  stops dependent build steps after failure, checks inventory command results,
  and reports only successful cache pushes. It preserves rendered module
  prerequisite evidence instead of replacing it with empty lists.
- An opt-in native candidate build. The current Python 3.9+ `.pyz` path remains
  the trial default; production native promotion has separate acceptance gates.
- Behavior-preserving typed planning records and a scoped development-only
  type check. Release acquisition derives runtime pins from `pyproject.toml`;
  `scripts/check.sh` is the common maintenance gate. See
  `docs/development.md` for the update and compatibility procedure.

## Current Initial Conversion Trials evidence

The exercised path is:

1. Cluster Inspector produces and verifies `profile.yaml`.
2. `render-static` produces the reviewed platform catalog.
3. the CSE blueprint and system values initialize the restricted workspace;
4. the generated handoff runs the pinned Spack 1.2 runtime downstream.

The trial blueprint has exercised generic Linux and Cray platform shapes,
stack-built GCC, platform compilers, build-sourced Open MPI, platform Cray
MPICH, shared producer hashes, login/compute build contexts, source fetch,
lockfile verification, and resumed installation. Those are blueprint and build
handoff behaviors; they do not turn `init-workspace` into a generic production
mode.

## Full-render production gap

The current `render` implementation still emits the older pre-v1 managed
workspace shape. It is suitable for continued renderer testing, but it is not
the final Spack 1.2 production contract in
`stack-planning/docs/spack_1_2_rendered_environment_reference_v1.md`.

The next full-render change must be one coherent update:

1. emit a native environment-local `modules.yaml` rather than inline module
   policy in `spack.yaml`;
2. render exact compiler, Foundation, Core/build-tool, and build-sourced MPI
   producer groups with explicit `needs` relationships;
3. bind every payload lane, including Serial, to its selected compiler or
   compiler-plus-MPI surface without propagating source-build constraints into
   machine-owned externals;
4. define GPU as a declarative MPI superset instead of duplicating package
   lists;
5. render version-sensitive module conflicts/dependencies for public
   multi-version packages;
6. verify package-module visibility after install, view regeneration, and
   module refresh on generic Linux and Cray fixtures;
7. replace first-match MPI selection with explicit default policy; and
8. complete CPE/MPI/GPU compatibility and multi-CPE selection.

There is no legacy compatibility path for the current pre-v1 inline-module
shape. Templates, fixtures, golden output, runbooks, and module smoke tests move
together.

## Deferred

- `validate-template-set --concretize` remains intentionally unimplemented;
  the flag exits with a clear error.
- GPU/CPE compatibility, multi-CPE fan-out, and removal of any required GTL
  preload remain part of the coherent full-render work.
- Production package-module visibility and final module conflict behavior remain
  acceptance gates, not completed claims.

## Validation gate

Before a Stack Composer change is ready:

```bash
bash scripts/check.sh
```

When render behavior changes, also inspect a reference workspace and run the
available Docker/Spack smoke path. Cross-repository schema and template drift
tests must run with sibling `stack-planning` and `stack-content` checkouts.
