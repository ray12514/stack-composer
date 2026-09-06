# Offline release inputs and reproducibility research (2026-09)

This note closes the research portion of the native-release candidate. It is
about the current candidate (PyInstaller 6.22.2, hooks-contrib 2026.7,
CPython 3.12, AlmaLinux 8, onedir) and the existing Shiv artifact. It does not
change the Python 3.9 support floor or the existing runtime pins:
`click==8.1.8`, `fastjsonschema==2.21.2`, `Jinja2==3.1.6`,
`MarkupSafe==2.1.5`, and `PyYAML==6.0.3`.

## Findings and recommendations

### 1. Freeze the complete acquisition set before the offline build

Pip's secure-install mode requires every requirement and dependency to be
version-pinned and hashed; it is deliberately all-or-nothing. Pip also
documents `--no-index` plus a local `--find-links` directory for flat offline
installation, and `--only-binary :all:` prevents an unexpected source build
([secure installs](https://pip.pypa.io/en/stable/topics/secure-installs/);
[pip install options and offline example](https://pip.pypa.io/en/stable/cli/pip_install/)).

Practical release input contract:

* In a connected preparation job, resolve and download the *entire* native
  builder closure (direct requirements, transitive requirements, and the
  exact application/runtime packages) into a wheelhouse. Generate a
  requirements file containing `==` pins and one or more SHA-256 hashes for
  every wheel that may be selected. Include the pip/setuptools/build backend
  inputs used by the preparation process where those tools are installed into
  the builder.
* Record wheel filename, SHA-256, Python tag, ABI tag, platform tag, and the
  source index/URL in release evidence. Do not treat the current
  `native-build-requirements.txt` version pins as a hash lock: it has no hashes
  and its transitive closure is not spelled out.
* Build the isolated environment with an explicit command equivalent to
  `python -m pip install --no-index --find-links=<wheelhouse> --require-hashes
  --only-binary=:all: -r native-builder-lock.txt`. Fail if any wheel is missing,
  has a wrong hash, or would require a source distribution. The pyz's deliberate
  pure-Python MarkupSafe/PyYAML source-wheel steps are a separate, explicitly
  locked build input; they must not silently broaden the native builder's
  offline closure.
* Pin the base image by digest (the Dockerfile already does this), and capture
  the image digest plus the lockfile and wheelhouse inventory. A digest is the
  immutable image identity; Docker documents that tags are mutable conveniences
  and digest references select an exact image
  ([pull by digest](https://docs.docker.com/reference/cli/docker/image/pull/)).

### 2. Set reproducibility controls for every artifact-producing phase

PyInstaller's own reproducible-build guidance says normal builds can differ
because Python hash randomization affects bytecode and internal data
structures; set a fixed integer `PYTHONHASHSEED`. It also documents
`SOURCE_DATE_EPOCH` for the generated executable timestamp
([PyInstaller 6.22.2 reproducible builds](https://pyinstaller.org/en/v6.22.2/advanced-topics.html#creating-a-reproducible-build)).
Set both in the native and pyz build environment, along with `LC_ALL=C` and a
fixed timezone (UTC), and use fresh output/build/work directories for each run.

The current native path has reproducibility leaks that must be closed before
claiming success:

* `scripts/build-pyz.sh` uses Shiv's `--reproducible`, but does not export a
  shared `SOURCE_DATE_EPOCH` or `PYTHONHASHSEED` for wheel creation, source
  staging, or the native build.
* `scripts/native_inventory.py` uses `shutil.copy2` for notices and writes
  `NATIVE_COMPONENTS.json`; copied source mtimes and filesystem metadata can
  vary. License discovery should sort each distribution's file list (not only
  distributions), and the final staged tree should have normalized metadata
  before archiving.
* `packaging/stack-composer.spec` sorts package data, which is useful, but the
  complete PyInstaller output still needs the fixed hash seed and a two-build
  byte comparison. Record the exact Python executable, PyInstaller versions,
  base-image digest, and lockfile digest as evidence rather than embedding
  host-specific absolute paths in release metadata.
* `scripts/build-native.sh` builds from a random `mktemp` source path and copies
  the PyInstaller warning file into the payload. Check the executable, embedded
  traceback/source paths, warning text, and all manifests for path or
  timestamp differences; use a stable in-build prefix or strip/normalize such
  paths before the two-build comparison. `cp -R` also preserves source
  metadata, so it must be followed by the same normalization policy.

Shiv explicitly supports reproducible output through `--reproducible` or
`SOURCE_DATE_EPOCH`, and says unchanged inputs should produce idempotent output
([Shiv reproducibility](https://shiv.readthedocs.io/en/latest/#reproducibility)).
Keep the existing exact dependency set and Python 3.9+ runtime contract, but
apply the same epoch and deterministic environment to wheel creation, Shiv,
and all staging steps.

### 3. Make the release tarball deterministic independently of its contents

GNU tar identifies the relevant sources of variation: directory traversal
order, mtimes, ownership/user names, permissions, atime/ctime PAX fields, and
the compressor header. Its reproducible archive recipe uses
`--sort=name`, POSIX format, deleted atime/ctime, clamped `--mtime`, numeric
owner/group, and gzip `--no-name`; GNU gzip documents that `-n` omits the
original filename and timestamp ([GNU tar reproducibility](https://www.gnu.org/software/tar/manual/html_node/Reproducibility.html);
[GNU gzip `--no-name`](https://www.gnu.org/s/gzip/manual/gzip.html)).

The current `tar -C dist -czf ...` command does not set these controls. The
release assembly should therefore:

1. construct a fresh staging directory with a stable, explicitly chosen
   permission policy;
2. normalize regular-file and directory mtimes to the release epoch (and
   preserve only intentional executable bits and symlinks);
3. archive under `LC_ALL=C` with sorted names, numeric owner/group set to 0,
   fixed mtime, and deleted atime/ctime PAX fields; and
4. pipe the tar stream through `gzip -n` (with a fixed compression level), then
   compare SHA-256 hashes of the complete `.pyz`, native directory file
   inventory, uncompressed tar, and compressed tar from two clean builds.

Matching the executable alone is insufficient: notices, JSON evidence,
symlink entries, permissions, and archive headers are part of the delivered
  native tarball.

### 4. Define the two-build gate as an offline test

Run build A and build B in separate fresh workspaces from the same source
export, same lockfile/wheelhouse, same image digest, same epoch, locale, and
tool versions, with network disabled. Verify:

* the `.pyz` bytes match and both execute on the supported Python floor;
* every native file's relative path, type (including symlink), mode, size, and
  SHA-256 match before tar creation;
* the native tarballs' bytes and extracted inventories match; and
* no network access, ambient user site, checkout residue, current time, host
  path, or unpinned package is used.

This proves a reproducible artifact for the recorded inputs. It does **not**
prove that an arbitrary future builder can be recreated from upstream package
repositories.

### 5. Saved Docker images are transportable builder inputs, not a recipe

Docker documents that `docker image save` writes an image repository tar,
including parent layers and specified tags, while `docker image load` restores
the images and tags ([save](https://docs.docker.com/reference/cli/docker/image/save/);
[load](https://docs.docker.com/reference/cli/docker/image/load/)). Therefore a
connected preparation host may save the already-built, digest-pinned native
builder image, transfer it, load it on the offline host, verify the expected
image ID/digest, and run the build with `--network=none`.

That restoration supplies the image's filesystem, configuration, layers, and
tags. It does not recreate the Dockerfile build transaction, mutable package
repositories, registry credentials, external volumes, daemon configuration,
or a missing build context; nor does it make a new `docker build` from
upstream repositories possible without all required inputs being locally
available. This is an inference from the save/load contract, so the release
record must distinguish:

* **reproducible artifact:** two offline builds from the same recorded source,
  lockfile, wheelhouse, image digest, and deterministic settings produce
  identical bytes; versus
* **recreatable builder:** a separately archived image (or an independently
  reproducible image build with locked RPM repositories and all inputs) can be
  restored and identified, but an image tar alone is not evidence that the
  upstream builder can be rebuilt later.

The image archive itself should receive a SHA-256 and provenance record. Do
not include Docker save/load as a substitute for the artifact two-build gate.

## Primary-source references

* [pip secure installs](https://pip.pypa.io/en/stable/topics/secure-installs/)
* [pip install: `--no-index` and `--find-links`](https://pip.pypa.io/en/stable/cli/pip_install/)
* [PyInstaller 6.22.2 reproducible builds](https://pyinstaller.org/en/v6.22.2/advanced-topics.html#creating-a-reproducible-build)
* [Shiv reproducibility](https://shiv.readthedocs.io/en/latest/#reproducibility)
* [GNU tar reproducibility](https://www.gnu.org/software/tar/manual/html_node/Reproducibility.html)
* [GNU gzip manual](https://www.gnu.org/s/gzip/manual/gzip.html)
* [Docker image pull by digest](https://docs.docker.com/reference/cli/docker/image/pull/)
* [Docker image save](https://docs.docker.com/reference/cli/docker/image/save/)
* [Docker image load](https://docs.docker.com/reference/cli/docker/image/load/)
