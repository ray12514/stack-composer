# Workspace workflows and safe package sharing (2026-09)

| Field | Value |
|---|---|
| Date | 2026-09-04 |
| Status | Blueprint assembler retained; broader package-sharing policy remains a proposal |
| Scope | Preserve the Initial Conversion Trials while supporting `init-workspace` beside `render-static` and `render` |

## Recommendation

Keep `init-workspace` as a supported **blueprint assembler**, with its present
command line and authored-input shape. Do not turn it into a second stack
planner. Its small interface is useful: one authored blueprint, one exact static
catalog, one explicit values file, and one output workspace. The blueprint owns
the files it renders; Stack Composer owns safe assembly, validation, provenance,
and recoverable output promotion.

Keep `render` as the planned **managed-workspace compiler**. It resolves the
standard `profile.yaml` + `deployment.yaml` + `defaults.yaml` + `stack.yaml`
model and emits the complete managed Spack workspace. It should not consume a
blueprint or require package managers to learn another selection language.

This is a product-support decision, not a production-render redesign. The
current full-render gap in `PHASE_STATUS.md` remains, and the current trial
workspace must not be regenerated or reconcretized merely to adopt this
decision. The shared output transaction, duplicate-key checks, and input digests
are implemented; the cross-compiler package-sharing experiments below are not.

## Implemented boundary and remaining proposals

| Area | Stabilized behavior (2026-09-04) | Remaining direction |
|---|---|---|
| `render-static` | Produces path-independent, include-ready platform scopes and retains the reviewed `profile.yaml`; it has no package intent or deployment roots. | Unchanged. It remains the platform-catalog producer. |
| `init-workspace` | Supported blueprint assembler. It renders authored files from a blueprint plus selected catalog and values, validates generated YAML, and optionally snapshots the catalog and applies workspace modes. | Keep it deliberately non-planning. A blueprint is an authored output contract for a specialized workspace, not a new stack DSL. |
| `render` | Produces the older pre-v1 managed-workspace shape. It does not yet implement the complete Spack 1.2 producer/module contract. | Remains the normal production path once the coherent Spack 1.2 update is complete. It resolves lanes from the existing standard inputs. |
| Shared implementation | Full render, static render, and initialization share a recoverable output transaction; generated YAML uses duplicate-key validation; manifests record additional input digests. | Preserve these internal seams without merging the three user-facing product contracts. |
| Build execution | Downstream `cse-build`, bare Spack, `spack-build`, Ansible, or `spacktools` owns concretization and installation. | Unchanged. Neither renderer invokes Spack. |

The deletion test supports this seam: removing the assembler would force every
specialized workflow to reimplement catalog verification, strict rendering,
output containment, mode application, and provenance. Removing a hypothetical
second lane planner would merely remove duplicated policy. Therefore retain the
assembler and reject planner growth.

## Supported blueprint relationship to full render

```text
profile + policy -> render-static -> exact catalog
                                         |
                 blueprint + values -----+-> init-workspace -> workspace

profile + deployment + policy + stack/package intent -> render -> workspace

workspace -> downstream Spack build path
```

The two workspace-producing commands may converge on the same downstream tree
invariants without sharing a user-facing input language:

- every material input has a stable digest in the manifest;
- every include is explicit and workspace-contained (or a checksummed,
  deliberately supported remote input);
- generated YAML rejects duplicate keys and invalid or empty root groups;
- no host probing, ambient `$HOME` policy, Spack import, or Spack execution
  occurs during assembly;
- failed promotion restores the previous workspace, or retains and reports its
  recovery copy if restoration also fails; and
- the complete tree, not a lone `spack.yaml`, is the handoff.

Full render may materialize the same approved platform plan directly from its
standard inputs. `init-workspace` may snapshot the exact catalog bytes. Those
are delivery differences, not competing platform policies.

## Current trial compatibility contract

No trial file rename, required input-schema change, or command-line change is
needed. Manifest provenance additions are optional and accept older trial
manifests. Compatibility means continuing to accept:

- `stack-content/pilots/cse-pilot/blueprint.yaml`;
- `stack-content/pilots/cse-pilot/roster.yaml` and
  `openmpi-policy.yaml` as blueprint-owned data;
- `stack-content/pilots/cse-pilot/templates/**` as the authored output tree;
- the values shape documented by
  `stack-content/pilots/cse-pilot/site-values.example.yaml` and generated by
  `scripts/create-build-values.py`; and
- `stack-composer init-workspace --blueprint ... --catalog ... --values ...
  --output ...` (including recoverable replacement with `--overwrite`).

The current blueprint deliberately sets `snapshot_catalog: true` and
`apply_workspace_permissions: true`. It renders eight independently locked
environments: Core, Common, Serial, and MPI for a shared CSE GCC surface and a
platform-compiler surface. Restricted values use group read/write policy;
generated directories, ordinary files, and executable controls are expected to
be `2770`, `0660`, and `0770` respectively.

The checked-in reference values pin Spack `1.2.2`, tag `v1.2.2`, commit
`3e19345b6e12f5ff1b874f4059622fc6a1fd804a`, and `spack-packages`
`v2026.06.0`. They select one portable CPU target for all source-built roots,
keep platform externals at their inspected architectures, and reserve generic
`x86_64` for the named Miniforge binary exception. The lab compatibility
fixtures remain `hpc-lab/fixtures/workspace-init/linux-values.yaml` and
`cray-values.yaml`; they are test inputs, not new production defaults.

Existing accepted workspaces and lockfiles are immutable evidence. Safety fixes
to the initializer must be verified with copied inputs and new temporary output
paths. A package-policy or producer-binding change creates a candidate release;
it never silently refreshes an existing trial workspace.

## Foundation growth and sharing rule

“Build once” has two different meanings and they must not be conflated:

1. **Within one compiler surface:** repeat the exact Foundation producer specs
   in every independent environment. If complete inputs match, the concrete
   hashes must match; the shared store or build cache supplies one physical
   installation.
2. **Across compiler surfaces:** reuse only after the package's exported and
   runtime interfaces prove that the baseline-compiler artifact is acceptable
   to every consumer surface. A C implementation is a candidate, not automatic
   proof.

The active trials should continue to build `zlib@1.3.1`, `xz@5.4.6`, and
`zstd@1.5.6` per compiler surface. Grow the existing `specs.foundation` roster
first; do not reorganize the live trial topology. After trial evidence is
preserved, evaluate cross-surface sharing in this order:

| Package/interface class | Default reuse scope | Evidence required before broader reuse |
|---|---|---|
| Command-only generators (for example M4/Autoconf/Automake candidates) | One reviewed OS/CPU compatibility domain | Audit dynamic closure and CPU/glibc floor; compare generated output; run under every compiler front door. |
| C headers/libraries with a stable platform ABI | Compiler surface | Compile/link/run consumers with each supported compiler; compare exported symbols and data layout; audit `DT_NEEDED`, symbol-version floors, RPATH, and runtime resolution. |
| C++ libraries or tools exposing C++ plugins/headers | Compiler surface | Same C++ ABI, standard-library implementation, dialect, exception/RTTI settings, compiler runtime, and symbol versions; otherwise do not share. GCC explicitly warns that matching language standards alone is insufficient. |
| Fortran libraries or `.mod` producers | Compiler/provider surface | Compiler/version-direction tests for modules plus link/run tests for calling conventions and runtime libraries. Prefer standardized `ISO_C_BINDING` only where the public interface truly uses it. |
| OpenMP-linked libraries | OpenMP runtime/compiler surface | Confirm one runtime and ABI/interface path in the final process, thread behavior, nested parallelism, and offload behavior. Do not load competing OpenMP runtimes by accident. |
| MPI-linked packages | Exact MPI provider/toolchain lane | Compile and run C, C++, `mpif.h`, `use mpi`, and `use mpi_f08`; verify wrapper, launcher, fabric, PMI/PMIx, compiler flavor, and provider hash. MPICH-family ABI participation does not erase Fortran-module or platform integration constraints. |
| GPU/offload packages | Exact GPU runtime + driver/toolkit + MPI/GTL + architecture tuple | Vendor compatibility matrix, device architecture, driver floor, runtime libraries, MPI GPU transport, and multi-node execution. CUDA minor compatibility does not establish Cray GTL or cross-offload-runtime compatibility. |

The practical first cross-surface experiment should therefore use a small
command-only tool, not an ambient library. If a baseline-GCC-built package is
linked into a platform-compiler payload, its exact baseline compiler/runtime
closure becomes part of the approved external contract and must appear in the
lock and runtime audit. When that is undesirable, keep the package per surface.

## Spack 1.2 producer and reuse semantics

Use Spack-native groups, `needs`, toolchains, configuration scopes, and locks;
do not create a parallel dependency vocabulary.

- In Spack 1.2, `needs: [producer]` concretizes the producer group first and
  makes its concrete specs available for reuse **inside that environment**. It
  is an ordering/reuse relationship, not a compiler, MPI, or arbitrary
  dependency selector. Consumers still need an explicit conditional toolchain
  or dependency constraint.
- `needs` does not create edges between separate `spack.yaml` files. Independent
  environments repeat exact producer specs. Global lock verification proves
  expected hash convergence before installation.
- `concretizer: reuse: false` prevents an installed or cached concrete spec
  from steering a new solve; it does not prevent installation-time reuse of an
  already installed or build-cached artifact with the exact resulting hash.
- A manifest is intent; `spack.lock` is the concrete build record. A package
  name and version are not a reuse identity. Compare the full concrete hash and
  the approved compatibility domain.
- Shared-store parallelism is permitted only with `config:locks: true` and a
  cross-node test of the actual filesystem's lock semantics. Otherwise install
  with one Spack process.

Spack documents that environments can share one installation, that lockfiles
hold the fully concretized graph, and that `needs` makes producer groups
available for reuse. Its package configuration also states that declared
externals remain eligible with concretizer reuse disabled. See the
[Spack 1.2 environment documentation](https://spack.readthedocs.io/en/v1.2.0/environments.html),
[Spack 1.2 package settings](https://spack.readthedocs.io/en/v1.2.0/packages_yaml.html),
and [Spack 1.2 lock settings](https://spack.readthedocs.io/en/v1.2.0/config_yaml.html).

## Self-contained configuration and HPC externals

Every initialized or fully rendered environment should enumerate its complete
configuration through relative workspace includes. With
`snapshot_catalog: true`, the trial's catalog scopes remain under `catalog/`,
and the workspace continues to build after the original catalog path and tool
repositories disappear.

For each selected external, render a maximally specific `packages.yaml` entry:
exact package/version/variants, prefix and/or ordered modules, architecture when
material, and `buildable: false` when the platform provider is mandatory. Pair
that with explicit virtual-provider requirements and the selected toolchain.
The external allow-list and lock verifier must reject any unreviewed external
or a reviewed external with different identity evidence.

The initial explicit integration set should include, where selected:

- libc/dynamic-loader and the supported OS ABI floor;
- scheduler/launcher plus PMI or PMIx development and runtime interfaces;
- MPI and its compiler flavor;
- UCX or libfabric and vendor network runtime;
- Cray programming-environment runtimes such as LibSci/GTL when used; and
- GPU driver/toolkit/runtime and device architecture.

OpenSSL/curl or another OS package may also be external when following the
operating system's security lifecycle is deliberate policy. “Found in `/usr`”
or inherited through a module is not approval. Capture exact selection in the
manifest and treat a system update as an external-contract change.

Build shells should continue to disable unexpected local configuration and
verify active scopes. A clean solve must not depend on user, system, checkout
site, or preloaded provider state. Spack's own package-setting guide recommends
fully specifying externals because it otherwise guesses missing attributes;
HPE likewise documents separate Cray MPI/LibSci prefixes for different compiler
families. See [Spack package settings](https://spack.readthedocs.io/en/v1.2.0/packages_yaml.html)
and [HPE's CPE Spack configuration guide](https://cpe.ext.hpe.com/docs/latest/craype/spack.html).

## New-package onboarding gate

Adding a package to an expandable Foundation is a release/DAG change. Use this
gate without changing the input language:

1. Add the normal Spack spec to the appropriate existing roster list. Record
   placement, exposure, compiler binding, intended reuse scope, and source
   policy in the review; do not add a new YAML layer to encode the discussion.
2. Review the recipe at the pinned `spack-packages` tag: versions and source
   hashes, variants/defaults, dependency types and conditions, patches,
   conflicts, provider edges, tests, licenses, and transitive graph growth.
3. Render a candidate into a new temporary workspace from copied catalog and
   values inputs. Validate every generated YAML file, include path, spec group,
   module/view projection, and active Spack configuration scope.
4. Fresh-concretize the complete affected environment set with the pinned Spack
   identity. Run the workspace verifier before solving and the global lock/DAG
   verifier afterward. Check expected convergence and intentional separation.
5. Install with build-time tests where supported, then run Spack stand-alone
   tests plus C/C++/Fortran/OpenMP/MPI/GPU consumer probes appropriate to the
   claimed interface. A successful prefix alone is not acceptance.
6. Audit installed ELF/runtime metadata and test from clean compiler/lane front
   doors on every claimed system or compatibility domain. A compiler failure
   gets a reviewed package-level exception; it does not justify general
   cross-compiler mixing.
7. Preserve candidate locks, logs, manifests, test output, and before/after
   hashes. Promote only artifacts reachable from the approved locks.

Spack 1.2's own review guide asks for automated checks and a successful build
of every version on at least one platform, while its test guide distinguishes
install-time checks from later stand-alone smoke tests. The CSE gate is
deliberately stronger because a shared Foundation claim spans compilers,
providers, and systems. See the pinned
[Spack 1.2.2 package review guide](https://github.com/spack/spack/blob/v1.2.2/lib/spack/docs/package_review_guide.rst)
and [package testing guide](https://github.com/spack/spack/blob/v1.2.2/lib/spack/docs/packaging_guide_testing.rst).

## Zero-change trial rollout

1. The approved safety fixes and copied-input regression tests are implemented.
   Synchronize them through the normal reviewed tool update. Do not initialize,
   refresh, or reconcretize a live CSE workspace.
2. The assembler is now documented as supported. Output transaction,
   duplicate-key validation, input digest, and overwrite-preservation tests
   pass. Linux and Cray trial fixture comparisons retain the prior generated
   configuration, with additional provenance only in the workspace manifest.
   See [stabilization evidence](stabilization-2026-09.md).
3. Keep the present CSE blueprint, values generator, eight-environment topology,
   package roster, Spack pin, permission modes, and lock verifier unchanged for
   the remaining trials.
4. Finish the coherent full-render Spack 1.2 implementation separately. Compare
   one new full-render candidate with an initialized candidate for equivalent
   platform selections, producer hashes, externals, views/modules, and clean
   consumer behavior; do not require byte-identical trees or replace trial
   locks.
5. Trial broader Foundation reuse only after current platform-compiler evidence
   is preserved. Start with one command-only package and expand an allow-list
   from passing evidence, never from package category alone.

## ABI evidence behind the conservative defaults

- GCC states that most platforms have a defined C ABI, while C++
  interoperability also depends on the compiler ABI and the same compatible
  standard-library implementation. It also documents that newer libstdc++
  symbols are not backward-compatible with older runtimes:
  [GCC compatibility](https://gcc.gnu.org/onlinedocs/gcc-12.2.0/gcc/Compatibility.html)
  and [libstdc++ ABI policy](https://gcc.gnu.org/onlinedocs/gcc-8.1.0/libstdc%2B%2B/manual/manual/abi.html).
- GNU Fortran documents compiler-specific argument conventions and recommends
  `ISO_C_BINDING` to avoid them. GCC 15 also changed the `.mod` format relative
  to GCC 8-14, illustrating why Fortran modules remain version-direction
  sensitive: [GNU Fortran argument passing](https://gcc.gnu.org/onlinedocs/gfortran/Argument-passing-conventions.html)
  and [GCC 15 Fortran changes](https://gcc.gnu.org/gcc-15/changes.html).
- NVIDIA warns that mixed OpenMP runtimes can produce wrong behavior or poor
  performance, and separately states that cross-compiler GPU offload runtime
  interoperability is not supported: [NVPL OpenMP runtime guidance](https://docs.nvidia.com/nvpl/)
  and [NVIDIA HPC compiler interoperability](https://docs.nvidia.com/hpc-sdk/compilers/hpc-compilers-user-guide/#interoperability-with-other-openmp-compilers).
- The MPICH ABI initiative covers participating MPI library ABIs, not all
  compiler modules, wrappers, launchers, fabrics, or GPU transport contracts:
  [MPICH ABI Compatibility Initiative](https://www.mpich.org/abi/).
- HPE exposes distinct Cray MPI and LibSci compiler-family prefixes and couples
  GPU-aware MPI to its platform runtime set. NVIDIA CUDA minor compatibility
  also has driver, feature, PTX, and target-architecture caveats; AMD publishes
  ROCm compatibility as a versioned OS/kernel/GPU matrix. These are reasons to
  keep GPU lanes tied to explicit runtime tuples:
  [HPE CPE documentation](https://cpe.ext.hpe.com/docs/latest/),
  [CUDA minor-version compatibility](https://docs.nvidia.com/deploy/cuda-compatibility/minor-version-compatibility.html),
  and [ROCm compatibility matrix](https://rocm.docs.amd.com/en/docs-7.0.0/compatibility/compatibility-matrix.html).
