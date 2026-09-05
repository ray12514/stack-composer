# Stack Composer native packaging assessment (September 2026)

## Recommended decision

This is the pre-implementation assessment. The approved candidate implementation
and its remaining promotion gates are recorded in
[stabilization results](stabilization-2026-09.md).

If implementation is later authorized, adopt a **PyInstaller one-directory
(`onedir`) Linux release as the first native packaging target**, delivered as a
versioned tarball whose top-level command is `stack-composer`. This document is
an assessment, not authorization to migrate. Keep the present `.pyz` release
until the native artifact passes the acceptance matrix below.

A correctly collected onedir artifact would meet the operational meaning of
self-contained: the target needs neither Python, pip, a source checkout, nor
network access. This is feasible, not yet proved here. It is not a single
filesystem object after unpacking; the executable has a private directory of its
bundled interpreter and libraries. That trade is preferable for HPC systems because a
PyInstaller one-file executable expands into a temporary directory on every
launch and needs to execute code there. PyInstaller explicitly documents that a
`noexec` `/tmp` is incompatible with one-file mode ([PyInstaller operating
modes](https://pyinstaller.org/en/stable/operating-mode.html)). The project can
reconsider one-file only after testing the actual target sites and establishing
a safe, executable extraction directory.

Nuitka standalone mode is technically feasible, but its documented build
requirements include a C compiler ([Nuitka requirements](https://nuitka.net/user-documentation/user-manual.html#requirements)).
That adds a compilation/debugging layer without a demonstrated performance need
for this renderer. Nuitka also documents the oldest-Linux constraint and default
one-file temporary extraction ([Nuitka use cases](https://nuitka.net/user-documentation/use-cases.html)).
It is a useful fallback/bake-off candidate, not the initial recommendation.

## Locally verified repository and artifact facts

- `scripts/build-pyz.sh` creates a reproducible shiv zipapp and a release tarball.
  Its launcher is `#!/usr/bin/env python3`, and the release README correctly says
  that Python 3.9+ is required on the target. Python's own zipapp documentation
  likewise describes such an archive as runnable on machines with a suitable
  interpreter ([Python `zipapp`](https://docs.python.org/3/library/zipapp.html));
  therefore the current `.pyz` cannot satisfy a no-host-Python requirement.
- The script deliberately manufactures only `py3-none-any` wheels. MarkupSafe and
  PyYAML are forced to pure-Python builds so the zipapp remains platform-neutral.
  A frozen binary necessarily gives up that platform neutrality because it
  includes the active Python interpreter and a native bootloader
  ([PyInstaller platform specificity](https://pyinstaller.org/en/stable/operating-mode.html)).
- Runtime inputs that must survive freezing are package data, not just imports:
  six JSON schemas, `resources/renderer_identity.toml`,
  `resources/THIRD_PARTY.toml`, and the bundled license texts. The code accesses
  these through `importlib.resources`; the native build must explicitly collect
  them and smoke-test the paths. `setuptools.package-data` governs the wheel, but
  is not by itself a PyInstaller collection rule ([PyInstaller data-file
  collection](https://pyinstaller.org/en/stable/spec-files.html#adding-data-files)).
- The package already has a suitable entry script at
  `src/stack_composer/__main__.py`. No application redesign is indicated.
- The release also carries `scripts/spack-build`, the project `LICENSE`, the root
  `THIRD_PARTY.toml`, and `THIRD_PARTY_LICENSES/`. These should remain visible
  beside the native application directory in the release tarball rather than be
  hidden only inside a binary.
- The local development environment contains shiv 1.0.8, but neither PyInstaller
  nor Nuitka was installed when this assessment was made. The inspected machine
  is macOS x86_64, so it cannot produce or validate the required Linux artifact.
- Read-only comparison of Git-tracked package files with the existing 477 KiB
  `dist/stack-composer.pyz` produced this local evidence (the archive was not
  extracted or modified):

  ```json
  {
    "tracked_package_files": 76,
    "archive_package_files": 130,
    "byte_exact_matches": 76,
    "missing": 0,
    "changed": 0,
    "stale_extra": 54,
    "stale_extra_by_suffix": {".py": 15, ".json": 2, ".yaml": 4, ".j2": 33},
    "stale_examples": [
      "site-packages/stack_composer/commands/assess_profiles.py",
      "site-packages/stack_composer/model/contract.py",
      "site-packages/stack_composer/resolve/node_selector.py",
      "site-packages/stack_composer/schemas/stack-defaults-v1.json",
      "site-packages/stack_composer/schemas/template-contract-v1.json",
      "site-packages/stack_composer/scaffold/starters/application/contract.yaml"
    ]
  }
  ```

  The `.pyz` is content-current for retained files but **not a clean build of the
  current source tree** and should not be used as release proof.
- The stale files are also present in local `build/lib/stack_composer`, while
  `scripts/build-pyz.sh` cleans selected `dist/` paths but not the setuptools
  `build/` tree. The native packaging work must first make every release build
  use an empty staging/build directory (and verify its file inventory); otherwise
  a new freezer can faithfully package stale build output too.
- Independent baseline verification on this checkout reported 202 source tests
  passing under Python 3.14.7 and the pinned runtime/third-party manifest check
  passing. Those results support the application baseline only; they do not
  exercise any native package.

## Distribution choice

The behavior rows below summarize the vendor descriptions of [PyInstaller
onedir/onefile](https://pyinstaller.org/en/stable/operating-mode.html) and
[Nuitka standalone/onefile](https://nuitka.net/user-documentation/use-cases.html).
The “Fit here” row is this assessment's project-specific judgment.

| Property | PyInstaller onedir | PyInstaller onefile | Nuitka standalone / onefile |
|---|---|---|---|
| Host Python needed | No; the active interpreter is bundled | No | No in standalone or onefile mode |
| Runtime source checkout or network | No, if all code/data is collected | No, if all code/data is collected | No, if all code/data is included |
| Files delivered | Directory plus executable; tar for transport | One executable, with README/licenses still best shipped beside it | Directory / one executable |
| Startup and temporary execution | Loads from installed directory; no per-launch unpack | Unpacks to a unique temporary directory; `noexec` temp is incompatible | Onefile unpacks to a temporary directory by default; standalone is the lower-risk form |
| Linux portability | Build on oldest supported glibc and once per architecture | Same | Same oldest-OS constraint; compiler adds build complexity |
| Resource debugging | Collected files are inspectable | Diagnose onedir first, then onefile | Nuitka also recommends standalone first and provides a compilation report |
| Fit here | **Recommended first target** | Defer pending site evidence | Feasible fallback; no demonstrated advantage yet |

“Self-contained” must not be documented as “fully static” or “runs on every
Linux.” PyInstaller does not bundle glibc and does not cross-compile. Its output
is specific to the operating system, Python build, word size, and architecture;
third-party binaries may add further system-library requirements
([PyInstaller Linux and platform guidance](https://pyinstaller.org/en/stable/usage.html#platform-specific-notes)).

## Compatibility policy required before implementation

1. Publish an explicit target matrix. Repository fixtures currently demonstrate
   RHEL 8.9/glibc 2.28 and RHEL 9.4/glibc 2.34, while template fixtures also name
   SLES 15. That is not enough evidence to choose the minimum glibc or all CPU
   architectures. Each supported `(Linux family baseline, CPU architecture)`
   needs its own built and tested artifact.
2. Build on the oldest supported Linux userspace for that architecture. A binary
   built on RHEL 9 is not evidence that it will run on RHEL 8. PyInstaller's
   official guidance is to build on the oldest GNU/Linux version to be supported
   because glibc is forward-compatible but not backward-compatible
   ([PyInstaller GNU/Linux guidance](https://pyinstaller.org/en/stable/usage.html#making-gnu-linux-apps-forward-compatible)).
3. Do not use CPU-native compiler optimization for a generally distributed
   artifact. The executable's instruction-set floor should match the declared
   host baseline, independently of the Spack target data that Stack Composer
   reads and renders.
4. Name artifacts with the compatibility boundary, for example
   `stack-composer-<version>-linux-x86_64-glibc2.28.tar.gz`, and emit checksums.
   Do not silently replace one architecture with another under the same name.
5. Treat execution from shared storage as an acceptance case. Onedir avoids the
   onefile `/tmp` extraction problem, but the installed filesystem must still
   permit execution and preserve symlinks when the selected PyInstaller version
   uses them ([PyInstaller symlink guidance](https://pyinstaller.org/en/stable/common-issues-and-pitfalls.html#requirements-imposed-by-symbolic-links-in-frozen-application)).

## Proposed bounded implementation

- Add a pinned PyInstaller build dependency and a checked-in spec file. Build
  `src/stack_composer/__main__.py` in `onedir` mode and explicitly collect
  `stack_composer.schemas` and `stack_composer.resources`, preserving their
  package-relative layout. Distribution metadata does not appear necessary at
  runtime today because `__version__` is a source constant, but this must be
  revisited if code starts using `importlib.metadata`.
- Preserve the existing pre-build gates: schema refresh/drift policy,
  exact runtime pins, third-party manifest check, resource synchronization, and
  the companion `spack-build` script. Build the wheel and frozen application in
  fresh staging directories, and fail if their Stack Composer file inventory is
  not exactly the tracked source/package-data inventory. Remove the
  `py3-none-any` wheel assertion only in the native path; it expresses zipapp
  portability, not native-package correctness.
- Build in a clean, pinned Linux environment with network disabled after all
  inputs have been staged. Record the Python, PyInstaller, dependency, compiler,
  kernel/build-image, architecture, and glibc versions. Pinning inputs and using
  `PYTHONHASHSEED`/`SOURCE_DATE_EPOCH` are reasonable reproducibility controls,
  but byte-for-byte reproduction is an acceptance result, not assumed from
  configuration ([PyInstaller reproducible-build controls](https://pyinstaller.org/en/stable/advanced-topics.html#creating-a-reproducible-build)).
- Keep one artifact per target rather than attempting cross-compilation.
  PyInstaller's documentation says builds for different operating systems must
  be performed on those operating systems
  ([PyInstaller multi-platform builds](https://pyinstaller.org/en/stable/usage.html#supporting-multiple-operating-systems)).
- Run an optional Nuitka standalone bake-off only if PyInstaller cannot collect
  required resources cleanly, has unacceptable startup/size, or fails a target
  compatibility requirement. If tried, use its compilation report and explicit
  [package-data options](https://nuitka.net/user-documentation/user-manual.html#data-files)
  and [compilation report](https://nuitka.net/user-documentation/user-manual.html#compilation-report);
  do not start with Nuitka onefile.

## Resource, dependency, and license closure

The current third-party controls are a good direct-dependency baseline, but are
not yet a complete frozen-artifact inventory:

- Local comparison confirms that `pyproject.toml`, `scripts/build-pyz.sh`, and
  root `THIRD_PARTY.toml` agree on five exact direct runtime distributions:
  click 8.1.8, fastjsonschema 2.21.2, Jinja2 3.1.6, MarkupSafe 2.1.5, and PyYAML
  6.0.3. The root manifest and all five root license texts are byte-identical to
  their packaged copies under `src/stack_composer/resources/`. The generator
  check independently passed against the active build environment.
- The check does not hash or compare the license text against the installed
  distribution, prove the bundled resource copy matches the root copy before
  syncing, inventory the embedded CPython runtime/standard-library notices, or
  enumerate native libraries actually collected by a freezer.
- A native release therefore needs an artifact-derived component inventory and
  license set. At minimum include the exact CPython license/notices, every
  collected runtime distribution and native library requiring attribution, and
  the applicable PyInstaller bootloader/runtime-hook notices. PyInstaller's
  [bootloader exception](https://github.com/pyinstaller/pyinstaller/blob/develop/COPYING.txt)
  permits distribution of the combined executable, but it does not eliminate
  review of the [CPython license](https://docs.python.org/3/license.html) and
  notices for other collected components.
- Preserve the root human-readable license directory in the tarball and ensure
  `stack-composer --licenses` still works from the frozen executable. Decide
  whether that command should enumerate the newly bundled interpreter/tooling
  components or point to the complete adjacent notices; the current output
  covers only the five Python runtime dependencies.

### Direct-pin advisory snapshot (2026-09-04)

A local OSV `querybatch` for the five exact direct runtime pins returned one
match: Click 8.1.8 is affected by PYSEC-2026-2132 / CVE-2026-7246 /
GHSA-47fr-3ffg-hgmw. The original advisory describes shell-command injection
when an attacker-controlled filename reaches `click.edit()`; affected versions
are `<8.3.3` and 8.3.3 is patched ([original
advisory](https://github.com/tsigouris007/security-advisories/security/advisories/GHSA-47fr-3ffg-hgmw)).
Click's 8.3.3 release replaces shell command construction with split argument
lists and removes `shell=True` ([Click 8.3.3
release](https://github.com/pallets/click/releases/tag/8.3.3)).

A local source search found no Stack Composer call to `click.edit`,
`click.launch`, or Click's pager helpers. That does **not** make the old pin
secure, but no reachable application exploit was established by this review.
The other four direct pins returned no OSV match in that dated query; absence of
a match is not proof of security.

Upgrading to the patched Click line needs an explicit compatibility decision:
Click 8.2 dropped Python 3.7, 3.8, and 3.9, while Stack Composer currently
declares Python 3.9+ ([Click 8.2.0
changelog](https://click.palletsprojects.com/en/stable/changes/#version-8-2-0)).
Any Click change must coordinate the project's Python floor and pass the full
test/package matrix. No dependency change is authorized by this assessment.

This scan covered only the five direct Python pins. It did not inventory
transitive/build dependencies, the bundled CPython runtime, PyInstaller hooks or
bootloader, or native libraries in a future frozen artifact. A release should
scan the exact staged and artifact-derived inventories and retain the
machine-readable results. Separately, Jinja 3.1.6 is a documented [security
release](https://github.com/pallets/jinja/releases/tag/3.1.6), and the [PyYAML
project](https://github.com/yaml/pyyaml) advises `safe_load` for untrusted input;
Stack Composer uses `safe_load` at its input boundary.

## Acceptance evidence required before switching users

The recommendation above is **feasible based on code and vendor documentation,
not tested proof**. A replacement is ready only when all of the following pass on
each supported target, without Python on `PATH`, without a repository checkout,
and with network access denied:

- `stack-composer --version`, `--help`, and `--licenses`;
- schema validation using every packaged schema;
- `show`, `validate`, `render-static`, `publish-static`, `render`, and
  `init-workspace` smoke paths using copied fixtures/external inputs;
- byte comparison of representative output with the wheel/zipapp execution path;
- launch from the intended shared filesystem and with the site's temporary
  filesystem mounted `noexec` (the latter should be irrelevant to onedir);
- inspection of ELF interpreter, required shared libraries, minimum GLIBC symbol
  versions, architecture/instruction-set floor, permissions, and preserved
  symlinks;
- complete component/license inventory, dependency advisory scan, checksums, and
  two-build reproducibility comparison; and
- negative checks proving the binary neither imports from ambient user paths nor
  attempts network access during normal commands.

After that evidence exists, update `scripts/build-pyz.sh`/documentation in one
coherent release change or introduce a clearly named native build script and
retire the `.pyz` only after an overlap period.

## Primary sources

- [Python `zipapp`: interpreter requirement and caveats](https://docs.python.org/3/library/zipapp.html)
- [PyInstaller operating modes: bundled interpreter, onedir, onefile, and temporary extraction](https://pyinstaller.org/en/stable/operating-mode.html)
- [PyInstaller usage: onefile extraction location, Linux glibc compatibility, and per-platform builds](https://pyinstaller.org/en/stable/usage.html)
- [PyInstaller spec files: explicitly collecting data files](https://pyinstaller.org/en/stable/spec-files.html)
- [PyInstaller hook utilities: package data and distribution metadata](https://pyinstaller.org/en/stable/hooks.html)
- [PyInstaller runtime information: locating collected package data](https://pyinstaller.org/en/stable/runtime-information.html)
- [PyInstaller common issues: symlinks and bundled-library environment effects](https://pyinstaller.org/en/stable/common-issues-and-pitfalls.html)
- [PyInstaller license and bootloader exception](https://github.com/pyinstaller/pyinstaller/blob/develop/COPYING.txt)
- [CPython license](https://docs.python.org/3/license.html)
- [Nuitka use cases: standalone/onefile behavior and oldest-Linux guidance](https://nuitka.net/user-documentation/use-cases.html)
- [Nuitka user manual: compiler requirement, package data, and compilation reports](https://nuitka.net/user-documentation/user-manual.html)
- [Jinja 3.1.6 security release](https://github.com/pallets/jinja/releases/tag/3.1.6)
- [PyYAML project guidance for untrusted input](https://github.com/yaml/pyyaml)
- [Click command-injection advisory](https://github.com/tsigouris007/security-advisories/security/advisories/GHSA-47fr-3ffg-hgmw)
- [Click 8.3.3 fix release](https://github.com/pallets/click/releases/tag/8.3.3)
- [Click changelog: Python 3.9 support dropped in 8.2](https://click.palletsprojects.com/en/stable/changes/#version-8-2-0)
