# Offline delivery and workspace portability

This procedure produces a candidate delivery from three exact Git commits:
Stack Composer, Stack Content, and Stack Planning. It includes both Composer
entry points, their matching `spack-build` helper, the authored workspace
blueprint and overlays, schemas, hash-locked Python wheels, source exports,
and a saved Linux builder image. Cluster Inspector is not part of this bundle.

The `.pyz` remains the trial default and needs Python 3.9 or newer. The native
candidate runs directly on Linux x86_64 with glibc 2.28 or newer; keep its
`_internal` directory beside the executable. This procedure does not promote
the native candidate or change an existing CSE workspace.

## Capture release inputs

Use committed, reviewed versions of all three repositories. `snapshot` exports
HEAD, not the working tree. Uncommitted changes are deliberately excluded.
Record the resulting commit IDs in the release review. Source export hashes
must still match at sealing time.

Run these commands from the Stack Composer checkout. Set absolute paths to
the selected sibling checkouts and a new delivery directory. The builder
below is the preserved assessment builder; its Dockerfile is an acquisition
recipe, not a promise that mutable RPM repositories recreate the image.

```bash
DELIVERY=/absolute/path/to/new-delivery
CONTENT=/absolute/path/to/stack-content
PLANNING=/absolute/path/to/stack-planning
BUILDER=sha256:51fda9ab888aa866ec15bb665815b628ea44fc78121b36b2947eeb910e90de96

python3 scripts/offline_delivery.py snapshot \
  --stack-composer "$PWD" --stack-content "$CONTENT" \
  --stack-planning "$PLANNING" --output "$DELIVERY/inputs"

docker run --rm --entrypoint /bin/bash \
  --mount "type=bind,source=$DELIVERY/inputs,target=/inputs" \
  "$BUILDER" /inputs/sources/stack-composer/scripts/acquire-offline-wheels.sh /inputs

docker image save --output "$DELIVERY/inputs/builder-image.tar" "$BUILDER"
python3 scripts/offline_delivery.py seal "$DELIVERY/inputs" --builder-image "$BUILDER"
python3 scripts/offline_delivery.py verify "$DELIVERY/inputs"
```

Acquisition is the connected phase. It downloads exact native/build wheels,
checks their complete dependency closure by installing with `--require-hashes`
into a fresh venv, and runs `pip check`. The portable runtime uses the same
versions but pure-Python MarkupSafe and PyYAML wheels. Their source archives
are retained. The sealed input inventory covers every file and permission,
including the saved builder image; changed, missing, or additional files fail
verification. A checksum inventory is not a signature or security approval.
Distribute its approved checksum through the release's trusted review channel.

## Rebuild without source checkouts or network

Transfer the complete `inputs` directory and verify its approved delivery
checksum before executing its scripts or loading the image. On the receiving
Linux Docker host:

```bash
python3 "$DELIVERY/inputs/offline_delivery.py" verify "$DELIVERY/inputs"
docker image load --input "$DELIVERY/inputs/builder-image.tar"
docker image inspect --format '{{.Id}}' "$BUILDER"

mkdir "$DELIVERY/build-a" "$DELIVERY/build-b"
for attempt in a b; do
  docker run --rm --network=none --entrypoint /bin/bash \
    --mount "type=bind,source=$DELIVERY/inputs,target=/inputs,readonly" \
    --mount "type=bind,source=$DELIVERY/build-$attempt,target=/result" \
    "$BUILDER" /inputs/rebuild-offline.sh
done

cmp "$DELIVERY/build-a/stack-composer.pyz" "$DELIVERY/build-b/stack-composer.pyz"
cmp "$DELIVERY/build-a/stack-composer-0.1.0.tar.gz" "$DELIVERY/build-b/stack-composer-0.1.0.tar.gz"
cmp "$DELIVERY/build-a/stack-composer-native-candidate.tar.gz" \
    "$DELIVERY/build-b/stack-composer-native-candidate.tar.gz"
cmp "$DELIVERY/inputs/RELEASE_INPUTS.json" "$DELIVERY/build-a/RELEASE_INPUTS.json"
cmp "$DELIVERY/build-a/SHA256SUMS" "$DELIVERY/build-b/SHA256SUMS"
```

Require the inspected image ID to equal `BUILDER`. Both containers start with
new venvs, no mounted developer checkouts, hash-required local dependencies,
fixed hash seed and source epoch, and no network interface. The tar writers
normalize entry order, times, ownership, and modes and retain safe relative
symlinks. The full archives must match, not just their executables.

These are reproducible application artifacts from preserved inputs. They are
not proof that CPython, every dependency wheel, or the RPM builder can be
rebuilt from upstream source with identical bytes. The saved image makes the
builder restorable; it does not recreate upstream RPM repositories.

## Model the moved workspace

Use new scratch directories. Do not run this against a trial workspace or a
shared HPC Lab service. The standalone lab image is only a test runtime; its
entrypoint is bypassed and no lab data volumes are mounted. The release
builder image and the test runtime image serve different purposes.

Supply clean, read-only Spack and recipe checkouts outside the workspace:

```bash
git clone --depth 1 --branch v1.2.2 https://github.com/spack/spack.git "$DELIVERY/spack-runtime"
git clone --depth 1 --branch v2026.06.0 \
  https://github.com/spack/spack-packages.git "$DELIVERY/spack-packages"
git -C "$DELIVERY/spack-runtime" rev-parse HEAD
git -C "$DELIVERY/spack-packages" rev-parse HEAD
```

Expected commits are `3e19345b6e12f5ff1b874f4059622fc6a1fd804a` and
`d4f7c711a6a42f1c4d551c8fd10fce9a11340a81`, respectively. This is connected test
preparation, not an action performed by the receiver. Production sites must
supply their approved equivalent runtime and recipe mirror.

```bash
mkdir -p "$DELIVERY/tools/native" "$DELIVERY/origin" "$DELIVERY/site"
tar -xzf "$DELIVERY/build-a/stack-composer-native-candidate.tar.gz" \
  --strip-components=1 -C "$DELIVERY/tools/native"
cp "$DELIVERY/build-a/stack-composer.pyz" "$DELIVERY/tools/"

docker run --rm --network=none --entrypoint python3.12 \
  --mount "type=bind,source=$DELIVERY/inputs,target=/inputs,readonly" \
  --mount "type=bind,source=$DELIVERY/tools,target=/tools,readonly" \
  --mount "type=bind,source=$DELIVERY/origin,target=/origin" \
  "$BUILDER" /inputs/sources/stack-composer/scripts/check-workspace-portability.py produce

mv "$DELIVERY/origin/workspaces" "$DELIVERY/received"
LAB_IMAGE=hpc-lab-node:ubuntu24.04
docker image inspect --format '{{.Id}}' "$LAB_IMAGE"
docker run --rm --network=none --entrypoint python3 \
  --mount "type=bind,source=$DELIVERY/received,target=/received" \
  --mount "type=bind,source=$DELIVERY/site,target=/site" \
  --mount "type=bind,source=$DELIVERY/tools,target=/tools,readonly" \
  --mount "type=bind,source=$DELIVERY/spack-runtime,target=/runtime/spack,readonly" \
  --mount "type=bind,source=$DELIVERY/spack-packages,target=/runtime/spack-packages,readonly" \
  --mount "type=bind,source=$DELIVERY/inputs/sources/stack-composer/scripts/check-workspace-portability.py,target=/probe.py,readonly" \
  "$LAB_IMAGE" /probe.py receive
```

Record the test image ID with `PORTABILITY-RESULT.json`. The receiver has no
`/origin`, `/inputs`, or developer repositories. Linux uses a published static
catalog; Cray uses a restricted catalog. Both are snapshotted into their
workspaces. Six inventories cover fresh, partial, and complete lockfile
states. Partial and complete locks are explicitly synthetic byte-preservation
fixtures, not valid package DAGs. Only fresh workspaces run the real Spack
login and compute status preflight, including all eight environment scopes.

The test preserves workspace files and lock bytes, validates workspace-only
inputs, and checks helper execution and relative configuration includes.
It does not build packages or validate Cray wrappers, MPI launch, GPU access,
installed libraries, modules, or buildcache contents.

## External paths stay external

Moving a workspace does not move or rewrite installed Spack prefixes, caches,
views, module roots, compiler paths, or runtime paths. Those explicit site
inputs must remain available at their recorded locations, or require a
separate reviewed deployment change. This test uses a local recipe mirror so
Spack cannot fall back to downloading recipes. The workspace snapshot carries
the CSE overlays; the full builtin recipe repository and Spack runtime remain
declared downstream prerequisites.

Do not regenerate a working trial environment to consume this packaging
change. Preserve existing `spack.lock` files, installation trees, and caches.
These checks qualify the delivery and handoff model, not a live HPC release.
