# Stack Composer assessment

Date: 2026-09-04

Reviewed commit: `2edb6f789ae70c0ca3acafe682ea62c9412c1292`

Branch: `codex/simplified-render-plan`

Historical baseline report. The approved correction work is recorded in
[stabilization results](stabilization-2026-09.md). Findings below describe the
reviewed commit, not the corrected working tree.

## Conclusion and scope

Keep Python and the existing separation of observed facts, deployment paths,
site policy, package intent, and templates. A language rewrite is not justified
by this assessment. Fix the safety and selection defects before undertaking the
larger full-render refactor.

The existing 202-test suite passes on three Python versions across macOS and
Linux. Additional probes reproduce 17 behavior defects through 21 failing test
cases on both macOS and Linux. The current local release archive also contains
54 obsolete package files. Passing the existing suite is therefore not
sufficient release evidence.

For binary distribution, evaluate PyInstaller's one-directory format first.
It can provide a normal `stack-composer` executable without requiring Python
on the target. It still has adjacent private runtime files, and needs separate
builds for the supported operating systems and CPU architectures. A true
single-file deliverable introduces temporary extraction and execution
requirements that are undesirable on some HPC sites. No frozen binary was
built or validated during this assessment. See the separate
[packaging assessment](packaging-assessment-2026-09.md) for primary sources and
the acceptance criteria.

At the assessment checkpoint, only documentation and
opt-in diagnostic harnesses were added. Application code, runtime pins,
generated workspaces, lockfiles, build caches, and published catalogs were not
changed. Cluster Inspector was not modified. This work neither diagnoses nor
claims to repair CCE package-build failures on Blueback.

## Evidence

| Check | Result |
|---|---|
| Existing suite, macOS, Python 3.9.25 | 202 passed |
| Existing suite, macOS, Python 3.14.7 | 202 passed |
| Existing suite, Linux lab login2, Python 3.12.3 | 202 passed |
| Ruff, application and existing tests | Passed |
| Shell syntax and ShellCheck, build scripts and companion | Passed |
| Exact runtime requirements and third-party manifest check | Passed |
| Installed dependency consistency | Passed |
| Baseline coverage with branch measurement | 91.8% statements; 79.2% branches; 88.3% combined |
| Source versus current zipapp, Linux and Cray fixtures | Byte-identical on Python 3.9, 3.12, and 3.14 |
| Added negative probes, macOS and Linux | 21 failed on each, exposing 17 behavior defects |
| Existing zipapp file inventory | 76 current package files match; 54 obsolete extras |

The artifact smoke test covers static rendering, full rendering, the actual
CSE trial blueprint, public-catalog promotion, and initialization from the
published catalog. For each source/zipapp comparison, it uses the same input
paths, timestamp, and destination. The zipapp runs with user-site packages and
ambient `PYTHONPATH` excluded and a private shiv cache.

For the Linux fixture it compares 9 static-catalog files, 25 full-workspace
files, and 63 initialized-workspace files. For the Cray fixture the counts are
15, 30, and 69. The generated CSE setup and build scripts pass shell syntax
checks. These are rendering checks, not executed Spack installations or
proof of compiler/MPI/GPU operation.

Coverage was measured against the existing suite only. The manifest and
initialization paths are less covered than the planner, but high planner
coverage also missed semantic selection defects. Add assertions about
correct outputs and failure behavior, not merely a higher percentage target.

## Findings requiring correction

P1 means address before trusting the affected operation with valuable
workspaces or release evidence. P2 means a correctness or release-engineering
defect that should be included in the stabilization work. P3 is a narrower
input edge case. None of these labels is a claim of an externally exploitable
security vulnerability.

Source locations below refer to the reviewed commit. The reproductions have
since become passing default-suite regressions in
[I/O and companion tests](../tests/test_io_regressions.py) and
[planning tests](../tests/test_planning_regressions.py).

### Output safety and shared management

1. **F01, P1: a release value can escape the declared output root.**
   Full and static rendering join an unchecked release string onto the output
   path. An absolute release value discards the preceding components.
   With overwrite enabled, a temporary directory outside the declared output
   root was replaced and its sentinel file removed. This is an accidental-data
   loss risk as well as an input-validation defect; the reproduction touches
   only test-owned data.
   Locations: `render/engine.py:95`, `render/static_catalog.py:88`,
   `render/release.py:15`, under `src/stack_composer/`.
   Repro: `test_release_cannot_escape_output_root`, both variants.

2. **F02, P1: overwrite removes the successful workspace before replacement succeeds.**
   Full render, static render, and workspace initialization delete the
   destination, then rename the pending tree. An injected final-rename failure
   leaves the old workspace lost. In the full-render and initialization paths,
   error cleanup also removes the newly rendered pending tree. A staging
   directory does not make this replacement transaction atomic.
   Locations: `render/engine.py:165`, `render/static_catalog.py:116`,
   `workspace/initializer.py:94`.
   Repro: `test_overwrite_retains_old_workspace_if_promotion_fails`, three variants.

3. **F03, P1: static rendering deletes a pending tree it does not own.**
   A pre-existing `.rendering` directory is unconditionally removed, even
   without evidence that it is stale. A second invocation can destroy another
   invocation's work. The probe places a sentinel in the pending directory;
   it does not depend on thread timing.
   Location: `render/static_catalog.py:101`.
   Repro: `test_static_render_preserves_another_runs_pending_tree`.

4. **F04, P2: manifest finalization removes collaborative file access.**
   Replacing a manifest with `NamedTemporaryFile` changes a tested mode of
   `0664` to `0600`. This removes CSE group read/write access even when the
   previous manifest had the intended permissions. This finding concerns
   `publish-manifest`, not the package installation permissions or the separate
   public static-catalog mode policy.
   Location: `manifest/finalize.py:147`.
   Repro: `test_final_manifest_preserves_collaborative_file_mode`.

5. **F05, P2: failed static rendering leaves partial output behind.**
   An injected write failure leaves the pending catalog because this function
   has no failure-cleanup boundary. That contradicts the repository's render
   invariant and compounds F03.
   Location: `render/static_catalog.py:105`.
   Repro: `test_static_render_cleans_up_after_write_failure`.

The repair should validate containment before creating or removing anything,
give each invocation ownership of its own staging directory, and preserve the
previous successful output until promotion completes. Test destination
symlinks, concurrent writers, interrupted writes, and rename failures. Preserve
the declared management permissions without broadening access to unrelated
paths. Prefer new versioned output plus a separately updated pointer for
published releases.

### Selection and validation

6. **F06, P1: forced platform MPI can silently select a different provider.**
   A build explicitly requesting `mpich` with `source: platform` resolves to
   the fixture's `openmpi` instead. The selected compiler can change with it.
   An explicit provider must either resolve to that provider or produce an
   actionable failure; this is different from a permitted default preference
   under `source: auto`.
   Location: `render/plan.py:611`.
   Repro: `test_forced_platform_mpi_does_not_substitute_another_provider`.

7. **F07, P1: duplicate build names overwrite package intent.**
   Two schema-valid build entries named `serial`, with roots `zlib` and
   `xz`, share a dictionary key and output lane identity. The later source
   replaces the earlier one without a validation error. Reject duplicate
   names before loading spec sources or planning paths.
   Locations: `validate/checks.py:190`, `render/plan.py:672`.
   Repro: `test_duplicate_build_names_are_rejected_before_spec_source_overwrite`.

8. **F08, P2: a partial MPI override discards the remaining defaults.**
   With the default provider `openmpi`, a build override containing only
   `source: build` resolves to `(None, "build")`. The per-build mapping
   replaces rather than merges the default mapping. Apply a documented
   field-level override rule, including version and family-priority policy.
   Location: `render/plan.py:568`.
   Repro: `test_partial_per_build_mpi_override_inherits_default_provider`.

9. **F09, P2: exact compiler narrowing uses the wrong identity.**
   The planner has `compiler_ref` values such as `gcc@14.3.0`, but
   `per_system` validation and filtering compare the bare `compiler` field.
   An exact version is rejected and the direct planner drops the matching
   lane. A bare `gcc` cannot distinguish multiple GCC versions.
   Locations: `validate/checks.py:351`, `render/plan.py:733`.
   Repro: `test_exact_narrowing_selects_one_version_of_a_duplicate_compiler`.

10. **F10, P2: the baseline CPU target is not checked against the profile.**
    `baseline` always produces `x86_64_v3`. A schema-valid runtime node
    reporting only `x86_64_v2` support still receives that higher target with
    no diagnostic. Resolve a supported baseline from policy and facts, or
    clearly reject an unsupported baseline. This finding does not assume that
    `native` must cover every heterogeneous runtime node; that broader
    contract needs a separate explicit decision.
    Locations: `render/plan.py:24`, `render/plan.py:647`.
    Repro: `test_baseline_target_never_exceeds_schema_valid_profile_support`.

11. **F11, P2: package-set kind declarations can validate but expand to no roots.**
    A package set declaring `kinds: [gpu]` but containing only
    `specs.serial` passes schema and semantic checks. GPU expansion returns
    no roots. The renderer's generated-YAML checks do not enforce nonempty
    `spack.specs`. Validate kind-to-spec coverage, including `any`, before
    rendering and check the resulting environment shape.
    Locations: `validate/checks.py:173`, `model/package_set.py:32`,
    `render/workspace_validation.py:32`.
    Repro: `test_package_set_declared_kind_has_specs_for_that_kind_or_any`.

12. **F12, P2: workspace initialization accepts duplicate generated YAML keys.**
    A blueprint emitting two `spack.specs` keys succeeds and the second value
    silently replaces the first when loaded. Full render already has a
    duplicate-key-rejecting loader, but initialization uses ordinary
    `safe_load`. Share one explicit YAML policy across these output boundaries.
    Location: `workspace/initializer.py:404`.
    Repro: `test_initializer_rejects_duplicate_generated_yaml_keys`.

### Provenance and companion build evidence

13. **F13, P1: the companion can report verification passed after inventory failure.**
    When the fake Spack hash-inventory command exits with status 9,
    `verify_non_external_manifests` ignores the failed pipeline, sees an empty
    list, and returns success. The companion exits zero and records manifest
    verification as passed. `pipefail` alone does not help when command status
    is not checked. Inventory failure must be distinct from a successfully
    inventoried environment with no local installs.
    Location: `scripts/spack-build:209`.
    Repro: `test_failed_hash_inventory_cannot_report_verification_passed`.

14. **F14, P2: buildcache reports list lanes that were never pushed.**
    A fake failed installation correctly prevents the push and produces a
    nonzero overall exit, but the destination report still lists that lane
    under `lanes_pushed`. Record actual per-destination successful push
    operations, not every selected lane.
    Location: `scripts/spack-build:300`.
    Repro: `test_failed_build_is_not_reported_as_pushed`.

15. **F15, P2: the release manifest omits a material render input.**
    Changing only `deployment.install_tree.root` changes rendered
    `configs/common/config.yaml` while leaving the draft release manifest
    byte-identical. Deployment content is missing from the input digests.
    The input inventory should also explicitly cover package-repository content
    and any other materialized inputs. Separately, the initialization manifest
    records a values pathname and blueprint name, not their content digests.
    The deployment omission is reproduced; the other omissions are
    source-inspection observations.
    Locations: `manifest/draft.py:11`, `workspace/initializer.py:82`.
    Repro: `test_deployment_change_changes_manifest_provenance`.

16. **F16, P2: missing companion option values hang instead of failing.**
    `spack-build --workspace` and `spack-build --jobs` repeatedly attempt
    `shift 2` when only one argument remains. They were terminated by a
    bounded subprocess timeout. Validate argument count and value before each
    shift, then add missing-value checks for every valued option.
    Location: `scripts/spack-build:38`.
    Repro: `test_spack_build_missing_option_value_exits_promptly`, two variants.

These companion findings apply to the script shipped in this repository.
They do not establish that the separate CSE blueprint's generated
`cse-build` has the same defects.

An additional inspected operational concern is that the shipped companion
always starts with `concretize --force` and proceeds to later lane steps
after an earlier step fails unless fail-fast was requested. It is not a
lock-preserving resume command. It also emits empty platform-module
prerequisite lists. Do not treat those outputs as complete release evidence
without defining and testing the downstream workflow.

### Publication and release artifacts

17. **F17, P3: nested reserved metadata names break publication verification.**
    A source file named `scopes/common/publication.yaml` is accepted and
    included in the checksum inventory, but verification excludes every file
    whose basename is `publication.yaml` or `SHA256SUMS`. The new catalog
    then fails its own verification. Reserve only the intended root-relative
    paths, consistently at write and verification time.
    Locations: `publish/static_catalog.py:137`,
    `publish/static_catalog.py:228`.
    Repro: `test_published_catalog_with_nested_metadata_names_can_verify`.

18. **F18, P2: the existing zipapp contains obsolete application files.**
    All 76 tracked package files match the archive exactly, but the archive has
    54 extras: 15 Python files, 2 schemas, 4 YAML files, and 33 templates.
    Obsolete files are also present in `build/lib/stack_composer`; the build
    script clears selected `dist` paths but not this staging tree. A clean
    source inventory must be checked against the wheel and executable payload.
    The observed archive was not rebuilt or removed during the assessment.
    Location: `scripts/build-pyz.sh:21`.
    Evidence and representative file names are in the packaging assessment.

## Design recommendations

### Retain the useful boundaries

The renderer already separates CLI handling, schema-backed input loading,
lane planning, template rendering, catalog publication, and manifest handling.
Strict template variables, explicit-input rendering, exact dependency pins,
packaged license resources, and cross-repository schema/template drift tests
are useful controls. The source and artifact smoke results show that the
current pure-Python implementation is portable across the exercised hosts.

Do not introduce a second contract/toolchain/node-selector configuration
language or move Spack execution into the renderer. Provider-specific behavior
should remain data-driven where the profile and defaults already carry it.
The subsequent support decision retains the initializer as a blueprint
assembler, not a second production planner. See the workspace workflow note.

### Refactor around demonstrated shared responsibilities

| Boundary | Responsibility to put behind it | Existing consumers |
|---|---|---|
| Output transaction | Containment, staging ownership, failure cleanup, promotion, declared modes | Full render, static render, initialization; publication where its immutable policy fits |
| Selection plan | Exact compiler/MPI identities, partial overrides, required/optional selection, target support, collision detection | Validation, render, plan reports; shared selection helpers for show |
| YAML validation | Duplicate keys, syntax, required output shapes, nonempty root specs | Full-render output and initializer output |
| Input provenance | Content inventory and stable digests for every material input | Draft manifests, initialization manifests, publication evidence |
| Build-step reporting | Explicit pass/fail/skipped states derived from checked command results | The shipped downstream companion |

Each suggested boundary has multiple existing callers or a reproduced failure
to justify it. Avoid creating a general filesystem abstraction or dependency
injection framework just to split large files. Small typed records for
`CompilerRef`, `MpiSelection`, `Lane`, and `RenderPlan` would make identity
and absence explicit without replacing the schema dictionaries at every input.

These are interface recommendations, not a requirement to preserve the current
internal function names used by the probes. When implementing a fix, retain
the behavior assertion and move it to the final public boundary as necessary.

## Dependency review

The five exact direct runtime pins agree across packaging and the license
manifest. A dated OSV query nevertheless matches Click 8.1.8 to
PYSEC-2026-2132 / CVE-2026-7246. The affected editor API is not called by the
reviewed Stack Composer source, so this assessment does not establish a
reachable exploit. The four other pins returned no matching advisory, which
is not a security guarantee.

The patched Click line changes the supported Python floor. Handle dependency
updates, interpreter support, license inventory, and native packaging as one
tested release decision. The
[packaging assessment](packaging-assessment-2026-09.md#direct-pin-advisory-snapshot-2026-09-04)
contains the primary-source links and compatibility details; the
[query snapshot](assessments/2026-09/dependency-advisories.json) records the
five inputs and raw batch response. This was not a comprehensive security
assessment of every build dependency, interpreter, or system library.

## Known full-render work, distinct from new defects

`PHASE_STATUS.md` already states that full render still emits an older pre-v1
shape, not the final Spack 1.2 production contract. Its listed work remains:

1. Environment-local native `modules.yaml`.
2. Exact compiler, Foundation, Core/build-tool, and built-MPI producer groups
   with explicit dependencies.
3. Compiler binding for every payload lane, including Serial.
4. Declarative GPU inheritance from the MPI lane.
5. Version-sensitive module conflicts and dependencies.
6. Installed package visibility after view regeneration and module refresh.
7. Explicit default MPI policy and complete CPE/MPI/GPU compatibility.

Do not count fixture rendering or the success of trial initialization as
completion of that production contract. The phase-status claim of atomic
rendering also needs qualification in the correction work, given F02.

## Proposed order of work

1. Correct F01 through F05 and F13 through small reviewed changes. Preserve
   successful workspaces and truthful verification before other refactoring.
2. Correct selection, identity, and validation defects F06 through F12. Add
   public-command regression coverage for silent substitutions, omitted roots,
   exact-version narrowing, and unsupported targets.
3. Complete provenance and companion reporting, including F14 through F17.
   Preserve shared management access and require checked evidence at each
   release transition.
4. Correct release staging F18, resolve the Click/Python support decision, and
   trial a native Linux onedir build against the packaging acceptance matrix.
5. Implement the coherent full-render Spack 1.2 contract with coordinated
   Stack Content templates and Stack Planning schemas. Verify the actual
   installed module surface before moving the trial onto it.

A safety repair should not require regenerating a live build's lockfile.
Treat changes to rendered intent, producer bindings, or dependency policy as
reviewed candidate renders; compare them before replacing trial inputs.
Nothing in this assessment authorizes a live workspace refresh or a force
reconcretization.

## Reproducing this assessment

The original opt-in probes asserted the desired safe behavior and failed on the
reviewed commit. During correction they were moved into `tests/` and expanded;
they now form part of the normal passing gate. They use temporary directories
and fake Spack commands, not the live installation.

From the Stack Composer checkout:

~~~bash
PYTHONPATH=src:. .venv/bin/python -m pytest tests/ -q
.venv/bin/ruff check src tests docs/assessments/2026-09

PYTHONPATH=src:. .venv/bin/python -m pytest \
  tests/test_io_regressions.py \
  tests/test_planning_regressions.py \
  -q --tb=short -p no:cacheprovider
~~~

The original probe set had 21 failing cases at the reviewed commit.
Individual groups can be selected with pytest's `-k` option. Do not use
existing installation directories as test output.

The artifact harness requires sibling `stack-content` and `hpc-lab`
checkouts for the actual trial blueprint and lab values. It renders files
only, checks shell syntax, and creates no Spack installation:

~~~bash
assessment_tmp=$(mktemp -d /tmp/stack-composer-smoke.XXXXXX)
PYTHONPATH=src:. PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1 \
  .venv/bin/python docs/assessments/2026-09/artifact_smoke.py \
  --development .. \
  --output "$assessment_tmp/output" \
  --pyz dist/stack-composer.pyz
~~~

Use a newly built artifact for release acceptance. The current archive was
used here only to measure existing behavior and expose its stale inventory.

## Lab concurrency and remaining validation limits

This run used the second login container, read-only repository mounts, and
unique temporary paths. It did not restart containers, modify scheduler
configuration, change shared module roots or group memberships, or execute
the lab's global stack suite. The Linux Python 3.12 suite loaded the installed
pure-Python test/runtime modules through explicit read-only paths; it was not
a new release installation.

Separate renderer processes can use the lab concurrently when their output
paths are distinct. The current global stack harness is not a concurrent
sandbox: it changes shared workspace and module locations and has lifecycle
operations. Respect its exclusive lock and isolate those resources before
running it alongside another task.

Still required for a production release: real Spack 1.2 concretization and
installation against the final full-render contract, existing-lock resume,
non-member public-catalog consumption, two-manager permission tests, actual
module load/unload/conflict tests, offline native-artifact acceptance,
multinode MPI execution, and real CCE/Cray MPI/GPU validation. The virtual
cluster cannot establish vendor ABI or hardware behavior.
