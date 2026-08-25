# Phase Status

Current branch: `codex/simplified-render-plan`.

This is the current pre-v1 implementation status. No released v1 behavior is
being preserved; when system evidence changes the design, update the active
model directly.

## Product model

- `render-static` produces reusable, include-ready Spack platform scopes from
  one reviewed Cluster Inspector profile. It contains no package intent,
  deployment roots, environment, lane, view, operational module tree, or build
  workspace.
- `render` produces the complete managed workspace from `profile.yaml`,
  `deployment.yaml`, `defaults.yaml`, `stack.yaml`, package content, and the
  active template set. It stops at the workspace handoff and never runs Spack.
- `init-workspace` is an Initial Conversion Trials convenience. It combines an
  authored blueprint with one exact static catalog. It is not a production
  renderer and can be removed after the static/manual and full-render workflows
  are complete and documented.

Cluster Inspector owns observed facts. Stack Content owns authored inputs and
templates. Stack Composer consumes only explicit inputs and never probes the
machine. A downstream build path owns concretization, fetch, install, module
refresh, verification, and buildcache publication.

## Implemented

- Packaged schemas for profile, defaults, deployment, stack, package sets, and
  release manifests, with cross-repository schema drift checks.
- Deterministic `validate`, `show`, `render`, `render-static`,
  `init-workspace`, `validate-template-set`, and `publish-manifest` command
  paths.
- Atomic full and static rendering with strict template variables and generated
  workspace validation.
- Generic compiler, MPI, GPU, OS, target, external-package, view, and
  front-door module planning from profile/defaults/stack/deployment inputs.
- Provider identity and package-layout translation at one adapter seam when
  Spack differs from observed facts: Classic Intel, LLVM-based oneAPI, Intel
  MPI, and oneAPI component-prefix normalization to the Spack suite root while
  preserving exact driver paths.
- Static catalogs that retain the exact reviewed profile, compiler scopes,
  compiler-specific MPI scopes and toolchains, platform/common/GPU scopes,
  recommendations, and a machine-readable plan.
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
.venv/bin/python -m pytest tests/ -q
.venv/bin/ruff check src tests
git diff --check
```

When render behavior changes, also inspect a reference workspace and run the
available Docker/Spack smoke path. Cross-repository schema and template drift
tests must run with sibling `stack-planning` and `stack-content` checkouts.
