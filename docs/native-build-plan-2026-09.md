# Stack Composer native Linux build plan (September 2026)

Status: the candidate builder and CSE opt-in launcher are implemented. Two
independent candidate freezes completed; their executable hashes match. Native
rendering passed with no host Python on `PATH`, no network, and a `noexec`
temporary filesystem. This document retains production acceptance requirements
that have not all passed. See [stabilization results](stabilization-2026-09.md)
for the exact evidence and remaining gates.

## Decision and boundary

Add a **candidate** PyInstaller one-directory build beside the current Shiv
artifact. Do not make it the CSE trial default, remove `stack-composer.pyz`,
change `requires-python = ">=3.9"`, refresh a catalog/workspace, or touch a
Spack lockfile or install tree in this packaging change.

The first candidate is Linux `x86_64`, built with CPython 3.12 on a RHEL 8
compatible userspace and labelled `glibc2.28`. It is a versioned tarball whose
top-level `stack-composer` file is the executable and whose `_internal/`
directory is inseparable private runtime content. PyInstaller does not bundle
glibc, so the build host sets the compatibility floor; its official guidance is
to build on the oldest GNU/Linux release to be supported
([PyInstaller Linux guidance](https://pyinstaller.org/en/v6.22.2/usage.html#making-gnu-linux-apps-forward-compatible)).
RHEL 8 introduced glibc 2.28
([RHEL 8 release notes](https://access.redhat.com/documentation/en-us/red_hat_enterprise_linux/8/pdf/8.0_release_notes/80-release-notes.pdf)).

This is an opt-in trial until the acceptance gates below pass on real target
systems. `onedir` is deliberate: PyInstaller documents it as a directory with
an executable plus support files, while `onefile` extracts code into a temporary
directory and is incompatible with a `noexec` temporary filesystem
([PyInstaller operating modes](https://pyinstaller.org/en/v6.22.2/operating-mode.html)).

## Pins and Python floor

- Pin `pyinstaller==6.22.2`. It is the current 2026-09-04 release and declares
  Python `>=3.8,<3.16`, including 3.9 and 3.12
  ([PyPI release metadata](https://pypi.org/pypi/pyinstaller/6.22.2/json)).
- Pin its independently released hook set as
  `pyinstaller-hooks-contrib==2026.7`; do not leave PyInstaller's declared
  `>=2026.6` lower bound floating. The 2026.7 release requires Python 3.8+
  ([hooks release metadata](https://pypi.org/project/pyinstaller-hooks-contrib/)).
- The candidate builder pins its build dependencies in
  `packaging/native-build-requirements.txt` and installs them in a private
  Python 3.12 virtual environment. The five application runtime pins remain
  those in `pyproject.toml` and `THIRD_PARTY.toml`. Before production, resolve
  and hash-lock the complete wheel closure, then install that wheelhouse with
  `--no-index --require-hashes`. Exact version pins and an offline freeze do
  not yet establish hash-locked dependency acquisition.
- Build the candidate with CPython 3.12, but keep source and `.pyz` support at
  Python 3.9+. A bundled 3.12 interpreter does not raise the source floor.
- Do not fold `click==8.3.3` into this change. Click 8.3.3 is the patched release
  discussed in the assessment, but its metadata requires Python 3.10+
  ([Click 8.3.3 metadata](https://pypi.org/pypi/click/8.3.3/json)) and Click 8.2
  explicitly dropped Python 3.9
  ([Click changes](https://click.palletsprojects.com/en/stable/changes/#version-8-2-0)).
  Making 8.3.3 the sole runtime pin would therefore contradict the preserved
  Python 3.9 contract. Conditional pins would leave the Python 3.9 path on the
  affected line and create two runtime behaviors. Production promotion remains
  blocked until the owner either raises the source floor to 3.10+, accepts a
  reviewed compatible patch/backport, or upstream provides a patched 3.9-capable
  release. A candidate using the current exact dependency set is packaging
  evidence, not a security-cleared production release.

## Minimal checked-in freezer definition

Use `packaging/stack-composer.spec`; do not freeze `build/lib` or another
persistent setuptools staging tree. Build from a clean temporary source export
of the exact candidate source and point the spec at that temporary source.
The candidate records source file hashes; production also requires a clean,
recorded commit and builder identity. PyInstaller spec files are executable build
definitions, and `datas` is the supported way to retain package data
([spec-file documentation](https://pyinstaller.org/en/v6.22.2/spec-files.html#adding-data-files)).

The following is the original design sketch. The checked-in spec is
authoritative: it takes `STACK_COMPOSER_NATIVE_SOURCE` from the build helper and
enumerates package resource files directly from that private source export.

```python
# -*- mode: python ; coding: utf-8 -*-

from PyInstaller.utils.hooks import collect_data_files

datas = collect_data_files(
    "stack_composer.schemas",
    includes=["*.json"],
)
datas += collect_data_files(
    "stack_composer.resources",
    includes=["*.toml", "THIRD_PARTY_LICENSES/*.txt"],
)

a = Analysis(
    ["src/stack_composer/__main__.py"],
    pathex=["src"],
    binaries=[],
    datas=datas,
    hiddenimports=[
        "stack_composer.schemas",
        "stack_composer.resources",
        "stack_composer.resources.THIRD_PARTY_LICENSES",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="stack-composer",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    contents_directory="_internal",
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="stack-composer",
)
```

The hidden imports are explicit because both resource packages are named by
string through `importlib.resources`. Do not use `collect_all`: the upstream
hook guidance recommends collecting only the required data and imports
([hook utilities](https://pyinstaller.org/en/v6.22.2/hooks.html#useful-items-in-pyinstaller-utils-hooks)).
No distribution metadata copy is currently needed: the application reads its
version from `stack_composer.__version__` and does not use
`importlib.metadata`. Add `copy_metadata("stack-composer")` only if that runtime
contract changes.

The exact data payload is:

```text
stack_composer/schemas/defaults-v1.json
stack_composer/schemas/deployment-v1.json
stack_composer/schemas/package-set-v1.json
stack_composer/schemas/profile-v1.json
stack_composer/schemas/release-manifest-v1.json
stack_composer/schemas/stack-v1.json
stack_composer/resources/renderer_identity.toml
stack_composer/resources/THIRD_PARTY.toml
stack_composer/resources/THIRD_PARTY_LICENSES/click.txt
stack_composer/resources/THIRD_PARTY_LICENSES/fastjsonschema.txt
stack_composer/resources/THIRD_PARTY_LICENSES/Jinja2.txt
stack_composer/resources/THIRD_PARTY_LICENSES/MarkupSafe.txt
stack_composer/resources/THIRD_PARTY_LICENSES/PyYAML.txt
```

Python package modules are analysis inputs, not `datas`. Templates, profiles,
deployments, stacks, package sets, and package repositories remain explicit
external inputs and must not be embedded.

Use the checked-in helper; it creates the private source export, invokes the
spec, verifies the frozen inventory, and assembles the candidate:

```bash
PYTHON=/opt/stack-composer-builder/bin/python \
  scripts/build-native.sh --candidate --output /out/new-candidate
```

This helper has been run successfully in the isolated builder. It refuses an
existing output directory and preserves the existing `.pyz`, its tarball, and
all CSE paths. Keep PyInstaller-created symlinks when copying or extracting the
one-directory tree.

## Release layout and licenses

Assemble the candidate tarball as:

```text
stack-composer/
  stack-composer
  _internal/
  spack-build
  README.md
  README.native.txt
  BUILD_WARNINGS.txt
  LICENSE
  THIRD_PARTY.toml
  THIRD_PARTY_LICENSES/
  NATIVE_COMPONENTS.json
  NATIVE_LICENSES/
  SHA256SUMS
```

Keep the existing project and five direct-runtime license files byte-identical
to their checked-in/package-resource copies. `stack-composer --licenses` must
continue to print its current bundled application manifest. The adjacent native
manifest completes the frozen closure without pretending PyInstaller build
tools are application dependencies.

`NATIVE_COMPONENTS.json` currently records the CPython build, builder
distributions and RPMs, source hashes, verified frozen application module set,
ELF paths and hashes, and required glibc symbol versions. Collected license
notices are adjacent. Every ELF is still marked for license review; this is
evidence collection, not a complete SBOM or license clearance.

Before production, map every collected runtime hook, Python extension module,
and shared library to its source/version and license, including the bootloader
exception. Retain the matching CPython
license/notices ([Python 3.12 license](https://docs.python.org/3.12/license.html))
and the pinned PyInstaller license/bootloader exception
([PyInstaller license](https://pyinstaller.org/en/v6.22.2/license.html)). Include
the hooks-contrib license when its code is present in the runtime payload. A
successful `--licenses` command does not replace this artifact-derived audit.

## Private Linux build environment

Read-only local Docker inventory on 2026-09-04 found unused official
`almalinux:8` and `almalinux:9` images and unused `rockylinux:8` and
`rockylinux:9` images, all `linux/amd64`. The best first baseline is the already
local AlmaLinux 8 image pinned by digest:

```text
almalinux@sha256:4a87d2615a770506e204c27d6248ac97f4df67f4e41e2e9c47c81f0ed0be98cb
```

AlmaLinux 8.10 documents a Python 3.12 application stream
([AlmaLinux 8.10 release notes](https://wiki.almalinux.org/release-notes/8.10.html)).
`packaging/Dockerfile.native` creates a separately named image from that digest
with CPython 3.12, `pip`, `binutils`, `file`, and archive tools. Candidate
dependency acquisition occurs during image preparation. The actual freeze was
run in a new `--rm`, `--network=none` container with source mounted read-only
and task-private output writable. The component report records the exact RPM
inventory; ELF inspection establishes the glibc symbol floor. The production
hash-locked wheelhouse requirement above remains open.

Do not use or `exec` into the running `hpc-lab` services. They are Ubuntu 24.04
and share project/lab volumes; their newer userspace is also the wrong glibc
floor. Do not run Compose, restart a lab container, mount the shared lab volume,
or write under `hpc-lab/artifacts`. The existing CSE smoke Dockerfile is useful
later as a target test with `ROCKY_TAG=8`, but it is not the release builder.

The private build invocation has this shape after the image and task-private
output parent exist:

```bash
docker run --rm --network=none --read-only \
  --tmpfs /tmp:rw,nosuid,nodev,exec \
  --mount type=bind,src="$CANDIDATE_SOURCE",dst=/src,readonly \
  --mount type=bind,src="$PRIVATE_OUTPUT",dst=/out \
  stack-composer-native-builder:<recorded-id> \
  /src/scripts/build-native.sh --candidate --output /out/new-candidate
```

The candidate helper accepts the reviewed working tree, records application
file hashes, and has no production-release mode. A future production mode
must refuse an unrecorded or dirty source identity and bind the exact builder
digest and acquired wheel hashes into release evidence.

## Activation and rollout

The current CSE operator session exports:

```text
STACK_COMPOSER=$COMPOSER/dist/stack-composer.pyz
CSE_PYTHON=$COMPOSER/.venv/bin/python
```

and invokes `"$CSE_PYTHON" "$STACK_COMPOSER"`. Leave that unchanged. Pointing
`STACK_COMPOSER` at an ELF executable would make the current Python-prefixed
invocation fail and could accidentally replace the reviewed trial tool path.

The current Stack Content operator helper supplies this opt-in command:

```bash
export CSE_STACK_COMPOSER_NATIVE="<absolute candidate directory>/stack-composer"
cse_stack_composer --help
cse_stack_composer --licenses
unset CSE_STACK_COMPOSER_NATIVE
```

When this variable is unset, `cse_stack_composer` retains the existing
`"$CSE_PYTHON" "$STACK_COMPOSER"` invocation. Existing commands that explicitly
invoke those two variables also remain unchanged. The helper does not switch
the recorded tool commit or active trial workspace. See the
[CSE update procedure](../../stack-content/pilots/cse-pilot/STACK-COMPOSER-UPDATE.md).

## Acceptance and blockers

Before any default switch, on Alma/Rocky/RHEL 8 and 9 representatives and the
actual CSE targets, with no Python on `PATH`, no checkout, and no network:

1. Pass `--version`, `--help`, and `--licenses`; load all six schemas.
2. Pass `show`, `validate`, `render-static`, `publish-static`, `render`, and
   `init-workspace` using copied inputs and task-private destinations.
3. Compare representative output byte-for-byte with the current `.pyz` path.
4. Run from the intended shared filesystem and with `/tmp` mounted `noexec`.
5. Inspect every ELF with `file`, `readelf`, `ldd`, and maximum referenced
   `GLIBC_*` symbol; prove `x86_64` and a floor no newer than 2.28.
6. Compare the PyInstaller archive/data inventory with the clean wheel/source
   inventory so F18 cannot recur; reject unexpected or missing package files.
7. Verify permissions and symlinks after tar extraction, produce checksums,
   scan the exact component inventory, and compare two independent builds.
8. Prove normal commands ignore ambient `PYTHONPATH`/user packages and make no
   network attempt.

Current blockers to production are the unresolved Click 8.3.3 versus Python
3.9 decision, complete artifact-derived license/security clearance, hash-locked
dependency acquisition and release identity, and actual CSE target-system
ABI/shared-filesystem evidence. Two independent freezes produced identical
executables, but complete archive reproducibility has not been established.
These gates do not block the opt-in candidate; they block replacing the `.pyz`
default or calling the tarball a production release.
