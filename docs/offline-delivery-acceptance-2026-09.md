# Offline delivery acceptance

Date: 2026-09-06

Status: local candidate complete for offline tool rebuilding and the modeled
workspace handoff. No remote push, production promotion, package installation,
trial workspace update, or shared HPC Lab service change was performed.

The outer delivery archive preserves the sealed input permission bits. The
final transport check caught Docker's `0600` image archive being normalized to
`0644`; the packaging utility now supports `--preserve-modes`, with an
unpack-and-verify regression test. This outer transport correction does not
change the sealed inputs or any of the two-build artifact hashes below.

## Recorded inputs

| Repository | Source commit |
|---|---|
| Stack Composer | `997520a190acb7b80be61d73a8ec9cc2ba1ec18e` |
| Stack Content | `a1f3d1d2252066561b5fe1f4030c4e7762066708` |
| Stack Planning | `013382915ad58fa332347ba4402e580487e45713` |

These are clean commit exports. Uncommitted changes in the development
checkouts were not captured. This acceptance note and the Content runbook
receipt are subsequent documentation-only changes, not part of the frozen
application inputs. Cluster Inspector is outside this delivery.

The builder image ID is
`sha256:51fda9ab888aa866ec15bb665815b628ea44fc78121b36b2947eeb910e90de96`.
Its saved archive SHA-256 is
`4609bd6e7f66cd9c844ee834ac158d3c56c384e013142810aa0a537fb8074f11`.
Loading that archive restored the expected image ID.

The sealed capsule includes all three source exports, complete per-file
inventories and modes, 15 native/build wheels, five portable-runtime wheels,
two source archives for the intentionally pure-Python dependency wheels,
SHA-256 requirement locks, and the builder image archive. Source exports and
top-level build entry points are checked against their captured inventories
before sealing. Missing, altered, additional, and unsafe linked inputs fail
verification. Pip installation and `pip check` verify the builder dependency
closure. Both formats retain the same five application dependency versions.

The full capsule manifest SHA-256 is
`bbcf38cb888578491070b578940b1089541d6e29ab733eabf03ace0a3858ff5a`.
Checksums identify reviewed bytes; they are not signatures or security approval.

## Reproducible artifacts

Two fresh containers built from the capsule with `--network=none`, a new venv
each time, no developer source mounts, hash-required local wheels, fixed hash
seed, and source epoch `1788726925`. The complete output directories matched
byte for byte, including the copied provenance manifest and checksum file.

| Artifact | SHA-256 |
|---|---|
| `stack-composer.pyz` | `ad29827c9dd339f8ed130a49cc3a8217311413b83197ad6724d03ccc95f116ec` |
| `stack-composer-0.1.0.tar.gz` | `e0865dabc14a3e5add3c476baf68f871f77808e7c824e984782b9b3fdb2eb975` |
| `stack-composer-native-candidate.tar.gz` | `1fdf66ecdc05040b6211e3e808c6165076684726975cf6c36220de44708cbfb2` |

The `.pyz` application inventory and native component inventory match the
captured Composer source files exactly. The `spack-build` helper in both
archives matches that same source checkpoint. All 61 ELF entries in the
native directory require no GLIBC symbol newer than 2.28.

The native entry point and bundled license command ran successfully on the
bare AlmaLinux 8 base image, without a `python3` command, with read-only
delivery files, no network, and a non-executable `/tmp`. The portable artifact
ran on macOS Python 3.9.25 with `-S` and a fresh writable `SHIV_ROOT`.

This proves reproducible application outputs from preserved inputs. It does
not prove source reproducibility of upstream wheels, CPython, or RPMs.

## Workspace relocation

The producer used only the delivered tools and source exports. It generated
Linux and Cray-shaped catalogs and initialized six complete workspace trees.
Linux consumed a published catalog; Cray consumed a restricted catalog. Both
catalogs were snapshotted into the workspaces.

The whole workspace directory was moved from `/origin/workspaces` to
`/received`. A separate receiving container had no `/origin`, no `/inputs`,
and no developer repositories mounted. Its only source-derived files were
the moved workspaces, delivered tools, and the single verification script.
Spack and the builtin recipe mirror were supplied separately, read-only.

| Model | Byte preservation and workspace validation | Real Spack preflight |
|---|---|---|
| Linux fresh | Pass | Login and compute, all eight environment scopes |
| Linux partial | Pass | Not a valid package-DAG test |
| Linux complete | Pass | Not a valid package-DAG test |
| Cray fresh | Pass | Login and compute, all eight environment scopes |
| Cray partial | Pass | Not a valid package-DAG test |
| Cray complete | Pass | Not a valid package-DAG test |

Partial and complete locks are explicitly synthetic preservation fixtures.
They demonstrate retained bytes, not successful concretization or compilation.
Original input paths remain only in `workspace-manifest.yaml` as provenance,
not in executable controls or operational configuration.

The test runtime image was
`sha256:b0539cdfe11d80162ffc499a2134b2a5085102ed219447b506ad50c50041aafc`.
The real Spack checkout was 1.2.2 at
`3e19345b6e12f5ff1b874f4059622fc6a1fd804a`. The builtin recipe mirror was
`v2026.06.0` at `d4f7c711a6a42f1c4d551c8fd10fce9a11340a81`.

A further network-disabled check used a fresh recipe cache. Real Spack listed
the relocated `cse_trials` repository, fetched builtin recipes from the local
`file:///runtime/spack-packages` mirror, and loaded the `zlib` and `cce` recipe
metadata. No upstream source directory or package index was used. The model
workspace was writable: even `spack -e ... info` needs an environment
transaction lock. A read-only workspace rejected that lock as expected.

## Regression checks and limits

The frozen Composer payload passed 255 tests on macOS Python 3.14.7 and Python 3.9.25. CSE
support: 85 tests passed. Ruff, ShellCheck, source/schema drift tests, capsule
verification, artifact checksum checks, and application inventory checks
passed. The new regression cases cover deterministic archives, unsafe links,
vendored wheel metadata, dirty source exclusion, and modified input rejection.
The outer-archive transport regression is additional to that frozen test set.
The final repository, including that regression, passed 256 tests on each
Python version. The transport fix changes only the outer archive wrapper;
the frozen tool payload and its reproducibility results remain unchanged.

Spack, the builtin recipe mirror, installed prefixes, caches, views, modules,
compiler and MPI paths, and site permissions remain explicit downstream
prerequisites. No installed package tree was relocated. No CCE, MPI, GPU,
multi-node, or package-runtime acceptance is claimed. The native candidate
still requires the dependency/Python-support decision, complete runtime
license/security review, and target-system acceptance before promotion.

The local delivery is under
`dist/offline/stack-composer-0.1.0-997520a/`, with `artifacts`, `inputs`, and
`evidence` directories. See [the offline procedure](offline-delivery.md) for
repeatable acquisition, offline rebuild, and receiving-workspace commands.
