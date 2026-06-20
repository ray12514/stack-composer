# Working in stack-composer

This file is the contract between an agent (human or LLM) picking up
work in `stack-composer` and the design that the code is meant to
implement.

## Read these first, in this order

1. `~/Development/stack-planning/docs/stack_composer_design_v1.md` —
   product boundary, repo shape, CLI command set, per-command spec,
   release packaging, and phase acceptance criteria.
2. `~/Development/stack-planning/docs/spack_stack_generation_design_v6.md`
   — the v6 render specification. **Authoritative for what a rendered
   workspace must contain.** Key landmarks:
   - §Render Step — Specification (`render()` pseudo-code, context
     keys, render-step invariants, failure modes).
   - §Template Render Context — the dict templates receive.
    - §Cray Toolchain / §Cray MPICH Externals — canonical
      `packages.yaml` examples (lines ~2115-2168).
    - §Host-Compiler Policy For GPU Lanes / §Cray PE + GPU lane
      assembly — default GPU lanes use a general host compiler plus
      standalone toolkit. `PrgEnv-gnu`, `PrgEnv-cray`, `PrgEnv-aocc`,
      and other site-verified, contract-approved general hosts are the
      default family; ROCmCC/NVHPC are narrow exception lanes. For Cray
      NVIDIA, v1 supports current CPE naming only:
      `PrgEnv-nvidia`, `nvidia/<version>`, and `cuda/<version>`.
    - §Generic Linux HPC — canonical site-MPI external example.
   - §Stack Defaults Merge Rules — how `stack.yaml` + `stack-defaults`
     compose.
3. `PHASE_STATUS.md` in this repo — what is *claimed* done, what is
   open, what is deferred. Note: do not trust a checked box as proof
   the design is met; check the box against the design first.

## Authority hierarchy

When in doubt, the order of authority is:

  design doc > schema > test fixtures > existing code > convenience

If the fixture template-set looks "minimal," ask: does the *design*
say the template-set should emit more? The fixtures under
`tests/fixtures/template-sets/v6/` are the smallest tree that keeps the
test suite passing. They are **not** a v6-conformant reference
template-set. Treat them as test scaffolding, not as the canonical
output shape.

## Render seam invariants (`render()`)

- Reads only its arguments and the named files in the workspace tree
  and the template-set. No `$HOME`, no environment probing, no
  `module list`, no `/etc/*` reads, no Spack imports.
- Deterministic: same inputs produce a byte-identical workspace.
- `StrictUndefined` Jinja: a reference to a missing context key fails
  render. Templates may not silently fall back.
- Templates may not mutate the context. The context is a frozen
  mapping at construction.
- On failure the `.rendering` side path is deleted and the workspace
  is not replaced.

If a template needs information not in the documented context, extend
the renderer to add the field — do not read it from the host at render
time.

## Don'ts that have actually bitten us

- **Don't claim a phase is complete because tests pass.** Tests can
  pass against an incomplete fixture. Map the design's acceptance
  criteria onto the test corpus first.
- **Don't say "the wiring is there" when only the data plumbing is
  there.** If the fixture template-set does not exercise the wiring,
  the wiring is not proven. Render a representative profile and
  inspect the output.
- **Don't trust function signatures from the codebase over the
  design.** If `required_scopes` in the code takes
  `(template_dir)` but the design specifies
  `(profile, rendered_lanes)`, the design wins and the code is a
  stub.
- **Don't simplify scaffold starters past what the design requires.**
  Scaffold output is what a maintainer reviews. Missing scope subdirs
  in the starter mean missing scope subdirs in production
  template-sets.

## Cross-repo boundaries

- This repo never imports or calls Spack at render time. Spack is
  only invoked by the bundled `spack-build` companion script (Phase
  3) or by the optional `validate-template-set --concretize` mode
  (Phase 2 deferred). Both treat Spack as a subprocess, not an
  import.
- `cluster-inspector` is the producer of `profile.yaml`. We treat the
  `profile-v1.json` schema in `schemas/` as the contract. Do not
  reach into the inspector for behavior; if a probe quirk needs
  changing, file it against `cluster-inspector` and pull the schema
  back from `stack-planning`.
- A reader of this repo should be able to understand it without
  reference to any host-integration repo. Do not put
  host-integration repo names in commits, docs, code, or comments.

## Verification rituals before claiming a change is done

1. Run `.venv/bin/python -m pytest tests/ -q` from the repo root.
   All tests must pass.
2. If you changed render output, render at least one of the
   reference profiles end-to-end (`example-cray`, `example-linux`)
   and visually inspect a diff against expected design output.
3. If you changed the render seam, the lane planner, the manifest
   shape, or anything `spack-build` consumes, also run the smoke
   pipeline against a real Spack install. The smoke runtime is at
   `~/Development/smoke-runtime/`; the orchestrator is on the same
   host (see `~/Development/smoke-runtime/README.md` for the
   actions and the orchestrator's location). The runtime is not
   tracked in any repo on purpose.
4. If you changed `PHASE_STATUS.md`, also update the design doc if
   the behavior changes the documented contract.
5. If you added or removed a runtime dependency, refresh
   `THIRD_PARTY.toml` with
   `python scripts/generate-third-party.py --refresh --sync-resources`.

## When you find a gap

If the design specifies behavior the code does not implement, the
right move is:

1. Note it in `PHASE_STATUS.md` under a Phase whose acceptance
   criterion covers the behavior. If no phase covers it, open a new
   phase block with a one-line statement of the gap and the design
   reference (file:line).
2. Do not silently re-frame the gap as "intentional minimal
   implementation."
3. If the gap is large enough that fixing it changes more than one
   file, write a short plan in `PHASE_STATUS.md` before touching
   code.

## Phase quick-status (mirror of PHASE_STATUS.md)

If `PHASE_STATUS.md` and this section drift, `PHASE_STATUS.md` wins.

- Phase 1 — Skeleton + Render Seam + Release Build: claimed done.
- Phase 2 — Maintainer Commands: claimed done; `--concretize`
  deferred.
- Phase 3 — Scaffold + Publish + spack-build: claimed done.
- Phase 4 — Reference Fixture Acceptance: claimed done **for the
  fixture**, not for the v6 spec. See Phase 5.
- Phase 5 — Render Seam Conformance With v6 Template-Set Spec: open.
  Tracks the externals-rendering + scope-selection gap that the
  earlier phases papered over.
