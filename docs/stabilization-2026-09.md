# Stack Composer stabilization results

Date: 2026-09-04

Scope: approved corrections to the
[assessment baseline](assessment-2026-09.md), an optional Linux executable,
and compatibility with the current CSE Initial Conversion Trials. This is a
local implementation checkpoint, not a push or promotion to a live system.
The matching repository revisions and artifact checksums are recorded in the
[CSE checkpoint receipt](../../stack-content/pilots/cse-pilot/checkpoints/2026-09-04-composer-stabilization.md).
Cluster Inspector is unchanged.

## Outcome

The 18 assessment findings have corresponding implementation corrections.
Regression tests cover the previously reproduced failures and additional
failure paths. The default Composer suite now has 248 passing tests on Python
3.9.25 and 3.14.7 on macOS, and Python 3.12.3 on Linux. Stack Content's CSE
support suite has 85 passing tests, including the native/default launcher tests.

The rebuilt `.pyz` contains exactly the current 77 application files. The
obsolete staging files found in the assessment are not in the new artifact.
The packaging scripts no longer use persistent `build/lib` as release input.

A Linux x86_64 native candidate is built and tested. It runs directly, without
a target Python installation or Shiv cache, with `_internal` retained beside
the executable. It is not yet the production or CSE trial default.

## Corrected behavior

| Assessment | Implemented correction |
|---|---|
| F01, F07 | Validate output identities and containment before writing; reject unsafe release/build names, duplicate build identities, escaping nested output paths, and output symlinks. |
| F02, F03, F05 | Share an owned staging transaction across full render, static render, and initialization. Do not remove another invocation's pending tree. Keep the previous output until replacement succeeds. Restore it on promotion failure, or retain and report its recovery path if restoration fails. |
| F04 | Preserve the existing manifest's Unix mode bits and group ID during replacement. Reject manifest symlinks. |
| F06, F08 | Merge partial MPI overrides with defaults. An explicit platform provider must resolve as requested or fail; it cannot silently become another provider. |
| F09 | Resolve exact compiler narrowing by compiler name and version. |
| F10 | Derive a supported baseline from profile CPU facts. Preserve the reviewed v3 cap where supported, use lower known generic targets where necessary, and reject unknown cases instead of guessing x86 support. `show` and render use the same resolution. |
| F11, F12 | Require package-set kind coverage and nonempty rendered root lists. Reject duplicate generated YAML keys through shared validation. |
| F13, F14, F16 | Fail promptly on missing companion option values. Treat failed hash inventory as failure, skip downstream steps after failed prerequisites, and report only actual successful cache pushes. |
| F15 | Record deployment and package-repository digests in full-render manifests. Record blueprint, templates, authored data, catalog, and values digests in initialized-workspace manifests. |
| F17 | Reserve publication metadata names only at the catalog root, not in every nested directory. |
| F18 | Build the wheel and zipapp from a clean private source export; verify exact application file names and hashes before publishing the artifacts. |

The companion `spack-build` also preserves an existing `spack.lock` by default.
`--reconcretize` explicitly requests a forced solve. A fresh environment still
needs concretization. Concurrent invocations cannot own the same report tree.
Full render now emits the planned platform-module prerequisites; the companion
preserves those facts rather than fabricating empty lists. An older workspace
without that evidence receives a review warning.

These companion changes do not replace or modify the CSE blueprint's
`cse-build`. The two scripts have different contracts.

Directory replacement is recoverable, not a portable atomic exchange or a
power-loss guarantee. Recovery tests include failure of both promotion and
rollback. Unix mode/group preservation is not a claim to preserve arbitrary
ACLs or the original file-owner UID across replacement by another manager.

## Current CSE compatibility

The trial blueprint, roster, templates, values generator, Spack pin, package
policies, eight-environment topology, and permission settings are unchanged.
No active workspace, lockfile, installed prefix, build cache, or published
catalog was regenerated or modified.

The actual checked-in CSE blueprint was rendered with both current lab value
fixtures before and after stabilization. After normalizing only the private
test-root paths, the results contain the same 63 Linux files and 69 Cray files.
Only `workspace-manifest.yaml` differs, through additional input digests. The
generated build scripts, environment YAML, configuration scopes, and catalog
snapshots match the prior fixture output.

This establishes compatibility for those fixtures, not every possible older
workspace or site overlay. The
[CSE update procedure](../../stack-content/pilots/cse-pilot/STACK-COMPOSER-UPDATE.md)
explains how to rebuild the tool, resume the existing trial, and compare copied
inputs in a new temporary workspace. A tool update alone is not a reason to
reconcretize or rerun initialization over a trial workspace.

The release-manifest schema additions are optional. Canonical Stack Planning
and bundled Composer schemas were updated together; older valid trial
manifests continue to validate.

## Native candidate evidence

The local candidate is:

```text
dist/native/stack-composer-0.1.0-linux-x86_64-glibc2.28-candidate.tar.gz
```

The archive extracts to `stack-composer/`. Run its `stack-composer` executable
directly and retain the adjacent `_internal` directory. This is a Linux
executable, not a macOS executable or a universal single-file binary.

| Check | Result |
|---|---|
| Builder baseline | AlmaLinux 8, CPython 3.12.14, x86_64 |
| Freezer | PyInstaller 6.22.2, hooks-contrib 2026.7 |
| Frozen application inventory | 63 package modules plus the entry script; all 13 resource files match source bytes |
| ELF inventory | 61 ELF files inspected; maximum referenced glibc symbol version is 2.28 |
| Direct startup | Passed on a bare AlmaLinux 8 image without the developer Python environment |
| Isolated rendering | Passed with network disabled, `PATH` and `PYTHONHOME` pointed at an absent Python location, and `/tmp` mounted `noexec` |
| Output comparison | Native output matches source bytes for static, full, and initialized Linux/Cray fixtures |
| Published-catalog consumption | Publication followed by initialization passed |
| Independent freezes | Two builds produced the same executable SHA-256 |

Executable SHA-256:

```text
7fede73a4196a2c4da743012b50434ebc4203bbc88c52d735a4967aa8d05d36a
```

The derived builder used for these checks is
`stack-composer-native-candidate:assessment-20260904`, with the image ID reported
by `docker image inspect`:
`sha256:51fda9ab888aa866ec15bb665815b628ea44fc78121b36b2947eeb910e90de96`.
It is separate from the running lab services. The image preparation downloads
version-pinned public dependencies; the subsequent source freeze has no
network access. Complete hash-locked acquisition is still a production gate.

The candidate includes `NATIVE_COMPONENTS.json`, build warnings, checksums,
the existing application licenses, collected builder-distribution notices,
and CPython notices. The component report lists source hashes, exact builder
packages, frozen modules, ELF hashes, and symbol versions. It explicitly marks
runtime license review as incomplete. Optional/platform-specific freezer
warnings remain attached for review; startup alone is not a complete closure
or license audit.

Matching executable hashes do not establish reproducibility of the complete
tarball. Build logs, timestamps, notices, and the complete frozen closure need
their own reproducible-release policy.

## Verification record

| Check | Result |
|---|---|
| Composer tests, macOS Python 3.9.25 | 248 passed |
| Composer tests, macOS Python 3.14.7 | 248 passed |
| Composer tests, Linux Python 3.12.3 | 248 passed |
| CSE support tests | 85 passed |
| Ruff | Passed for application, tests, new release helpers, and artifact harness |
| Shell syntax and ShellCheck | Passed for the updated packaging scripts and generic build companion |
| Canonical schema harness | Six schemas validated; eight positive and 45 negative cases passed |
| Schema/template drift tests | Passed against the sibling source-of-truth repositories |
| Rebuilt `.pyz`, Python 3.9 and Linux Python 3.12 | Source/artifact output equality and publication-to-workspace flow passed |
| Native candidate, Linux Python 3.12 builder baseline | Source/artifact output equality and publication-to-workspace flow passed |

Artifact comparison covers nine static, 26 full-render, and 63 initialized
files for the Linux fixture; 15, 31, and 69 respectively for Cray. The extra
full-render file relative to the baseline is the platform-module prerequisites
report. Generated `cse-build` and setup scripts also pass shell syntax checks.

The Linux regression suite reused pure-Python dependencies through explicit
read-only paths in the secondary login container, as in the baseline audit.
The native acceptance used a separate isolated Linux builder/runtime. Neither
test modifies scheduler configuration, module roots, group membership, shared
Spack stores, or the other task's lab workspace.

Regression sources:

1. [I/O and companion regressions](../tests/test_io_regressions.py)
2. [Planning regressions](../tests/test_planning_regressions.py)
3. [Release inventory checks](../tests/test_release_support.py)
4. [Source/artifact acceptance harness](assessments/2026-09/artifact_smoke.py)
5. [CSE launcher checks](../../stack-content/pilots/cse-pilot/tests/test_composer_launcher.py)

## Supported workflow and package growth

`init-workspace` is retained as a supported blueprint assembler. It takes an
authored blueprint, an exact static catalog, and explicit values. It is not a
second lane planner. `render-static` remains the platform-catalog producer;
full `render` remains the managed-workspace compiler using the standard
profile, deployment, defaults, and stack/package inputs.

The refactor places output ownership, generated-YAML validation, and digest
handling behind shared internal boundaries. It does not merge those three
user-facing input contracts. This keeps the trial assembler useful while the
full-render Spack 1.2 contract is completed separately.

Foundation growth should use the current roster and a new candidate release.
Cross-compiler reuse is an explicit compatibility claim, not an automatic
consequence of a package being written in C or built by a default compiler.
Keep current Foundation libraries per compiler surface during this trial.
Start any broader reuse experiment with a command-only tool, then require
compile, link, runtime, and dependency-closure evidence for each claimed
consumer domain. See the
[workflow and package-admission matrix](workspace-workflows-2026-09.md).

## Remaining gates

1. Resolve the Click security update versus the retained Python 3.9 support
   contract. This change does not claim that leaving the runtime pins unchanged
   resolves the advisory. A source-floor increase, reviewed compatible patch,
   or supported upstream fix needs an explicit decision.
2. Complete native dependency/license/security review, hash-locked acquisition,
   clean release identity, and full-archive reproducibility policy before
   production promotion.
3. Run the native candidate from the actual CSE shared filesystems on each
   supported OS/architecture. The glibc floor and local fixture checks do not
   establish every site's ABI compatibility.
4. Complete the full managed-render Spack 1.2 producer/module contract in a
   separate coherent update. Do not replace existing trial locks to adopt this
   stabilization work.
5. Retain real-system acceptance for CCE, Cray MPI, module activation,
   multi-manager filesystem permissions, offline builds, multi-node execution,
   and GPU behavior. Renderer tests do not establish package/compiler or
   hardware correctness, including the earlier Blueback package failures.
