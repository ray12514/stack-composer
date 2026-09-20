"""Capture and verify exact, commit-based offline release inputs (not a signing service)."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
from email.parser import BytesParser
from pathlib import Path
from zipfile import ZipFile


def digest(path: Path) -> str:
    result = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(chunk)
    return result.hexdigest()


def inventory(root: Path, excluded: tuple = ("RELEASE_INPUTS.json",)) -> dict:
    root = root.resolve()
    result = {}
    for path in sorted(root.rglob("*")):
        if path.relative_to(root).as_posix() in excluded:
            continue
        if path.is_symlink():
            if (
                Path(os.readlink(path)).is_absolute()
                or not path.is_file()
                or not path.resolve().is_relative_to(root)
            ):
                raise ValueError(f"unsafe input symlink: {path}")
            result[path.relative_to(root).as_posix()] = {"symlink": os.readlink(path)}
        elif path.is_file():
            result[path.relative_to(root).as_posix()] = {
                "sha256": digest(path),
                "mode": path.stat().st_mode & 0o777,
            }
        elif not path.is_dir():
            raise ValueError(f"unsupported input: {path}")
    return result


def verify(root: Path) -> dict:
    manifest = json.loads((root / "RELEASE_INPUTS.json").read_text())
    if manifest.get("schema_version") != 1 or manifest.get("files") != inventory(root):
        raise ValueError("release inputs differ from the recorded inventory")
    return manifest


def git(root: Path, *args: str) -> bytes:
    return subprocess.check_output(["git", "-C", str(root), *args])


def snapshot(args) -> None:
    root = args.output.resolve()
    root.mkdir(parents=True, exist_ok=False)
    sources = {}
    for name in ("stack-composer", "stack-content", "stack-planning"):
        origin = getattr(args, name.replace("-", "_")).resolve()
        commit = git(origin, "rev-parse", "HEAD").decode().strip()
        destination = root / "sources" / name
        destination.mkdir(parents=True)
        # Always export commits, never ambient build/lib, dirty files or ignored secrets.
        with tarfile.open(fileobj=io.BytesIO(git(origin, "archive", commit))) as archive:
            regular_files = {member.name for member in archive.getmembers() if member.isfile()}
            for member in archive.getmembers():
                if member.name.startswith("/") or ".." in Path(member.name).parts:
                    raise ValueError(f"unsafe source archive path: {member.name}")
                if member.issym() and not Path(member.linkname).is_absolute():
                    target = (destination / member.name).parent / member.linkname
                    if (
                        target.resolve().is_relative_to(destination)
                        and target.resolve().relative_to(destination).as_posix() in regular_files
                    ):
                        continue
                if (
                    member.name.startswith("/")
                    or ".." in Path(member.name).parts
                    or not (member.isfile() or member.isdir())
                ):
                    raise ValueError(f"unsupported source archive entry: {member.name}")
            archive.extractall(destination)  # fresh tree; every member checked above
        sources[name] = {
            "commit": commit,
            "tree": git(origin, "rev-parse", "HEAD^{tree}").decode().strip(),
            "files": inventory(destination),
        }
    sources["source_date_epoch"] = int(
        git(args.stack_composer, "show", "-s", "--format=%ct", "HEAD")
    )
    (root / "SOURCE_REVISIONS.json").write_text(json.dumps(sources, indent=2) + "\n")
    scripts = root / "sources/stack-composer/scripts"
    for name in ("offline_delivery.py", "rebuild-offline.sh"):
        shutil.copy2(scripts / name, root / name)


def wheel_lock(root: Path) -> str:
    entries = {}
    for wheel in sorted(root.glob("*.whl")):
        with ZipFile(wheel) as archive:
            names = [
                name
                for name in archive.namelist()
                if name.count("/") == 1 and name.endswith(".dist-info/METADATA")
            ]
            if len(names) != 1:
                raise ValueError(f"ambiguous wheel metadata: {wheel}")
            metadata = BytesParser().parsebytes(archive.read(names[0]))
        name = re.sub(r"[-_.]+", "-", metadata["Name"]).lower()
        if name in entries:
            raise ValueError(f"more than one wheel for {name}")
        entries[name] = f"{name}=={metadata['Version']} --hash=sha256:{digest(wheel)}\n"
    if not entries:
        raise ValueError("empty wheelhouse")
    return "".join(entries[name] for name in sorted(entries))


def delivery_checksums(root: Path) -> str:
    return "".join(
        f"{digest(path)}  {path.relative_to(root).as_posix()}\n"
        for path in sorted(root.rglob("*"))
        if path.is_file() and path != root / "SHA256SUMS"
    )


def verify_bundle(root: Path) -> dict:
    """Check an extracted delivery before selecting any tool or authored source."""
    manifest = json.loads((root / "DELIVERY.json").read_text())
    if (
        manifest.get("schema_version") != 1
        or manifest.get("kind") != "cluster-tools"
        or manifest.get("files") != inventory(root, ("DELIVERY.json", "SHA256SUMS"))
        or (root / "SHA256SUMS").read_text() != delivery_checksums(root)
    ):
        raise ValueError("delivery differs from its recorded inventory or checksums")
    return manifest


def bundle(args) -> None:
    """Assemble a small receiver bundle from the existing offline build products."""
    # The documented entry point may be inside the sealed source export.
    # Loading its sibling helper must not add bytecode to those recorded inputs.
    sys.dont_write_bytecode = True
    from release_support import release_archive, verify_archive

    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", args.version):
        raise ValueError("version must be a simple directory name of at most 128 characters")
    inputs = args.inputs.resolve()
    artifacts = args.artifacts.resolve()
    manifest = verify(inputs)
    checksum_receipt = artifacts / "SHA256SUMS"
    if (
        not checksum_receipt.is_file()
        or checksum_receipt.read_text() != delivery_checksums(artifacts)
    ):
        raise ValueError("build artifact checksums are missing or do not match the build products")
    if (artifacts / "RELEASE_INPUTS.json").read_bytes() != (
        inputs / "RELEASE_INPUTS.json"
    ).read_bytes():
        raise ValueError("artifacts were built from a different release input capsule")
    composer = inputs / "sources/stack-composer"
    verify_archive(composer, artifacts / "stack-composer.pyz")
    output = args.output.resolve()
    if output.is_relative_to(inputs) or output.is_relative_to(artifacts):
        raise ValueError("delivery output must be outside the sealed inputs and build outputs")
    # A new directory makes an interrupted attempt visible and prevents overwrite.
    output.mkdir(parents=True, exist_ok=False)
    root = output / args.version
    root.mkdir()
    shutil.copytree(inputs / "sources", root / "sources", symlinks=True)
    (root / "tools").mkdir()
    shutil.copy2(artifacts / "stack-composer.pyz", root / "tools/stack-composer.pyz")
    (root / "tools/stack-composer.pyz").chmod(0o755)
    shutil.copy2(composer / "scripts/spack-build", root / "tools/spack-build")
    shutil.copytree(inputs / "wheels/pyz", root / "wheels")
    shutil.copy2(inputs / "locks/pyz.txt", root / "runtime-requirements.txt")
    shutil.copy2(composer / "scripts/offline_delivery.py", root / "verify-delivery.py")
    instructions = (composer / "docs/cluster-delivery.md").read_text()
    (root / "UPDATE.md").write_text(instructions.replace("@VERSION@", args.version))
    # Preserve links and executable bits, normalize other modes before recording.
    for path in [root, *root.rglob("*")]:
        if not path.is_symlink():
            path.chmod(0o755 if path.is_dir() or path.stat().st_mode & 0o111 else 0o644)
    delivery = {
        "schema_version": 1,
        "kind": "cluster-tools",
        "version": args.version,
        "sources": manifest["sources"],
        "release_inputs_sha256": digest(inputs / "RELEASE_INPUTS.json"),
        "runtime": {"python": ">=3.9", "entrypoint": "tools/stack-composer.pyz"},
        "files": inventory(root, ("DELIVERY.json", "SHA256SUMS")),
    }
    (root / "DELIVERY.json").write_text(json.dumps(delivery, indent=2, sort_keys=True) + "\n")
    (root / "DELIVERY.json").chmod(0o644)
    (root / "SHA256SUMS").write_text(delivery_checksums(root))
    (root / "SHA256SUMS").chmod(0o644)
    verify_bundle(root)
    artifact = output / f"{args.version}.tar.gz"
    release_archive(root, artifact, manifest["sources"]["source_date_epoch"])
    (output / f"{artifact.name}.sha256").write_text(f"{digest(artifact)}  {artifact.name}\n")
    print(artifact)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    capture = commands.add_parser("snapshot")
    for name in ("stack-composer", "stack-content", "stack-planning", "output"):
        capture.add_argument("--" + name, type=Path, required=True)
    package = commands.add_parser("bundle")
    for name in ("inputs", "artifacts", "output"):
        package.add_argument("--" + name, type=Path, required=True)
    package.add_argument("--version", required=True)
    for command in ("verify", "seal", "wheel-lock", "verify-bundle"):
        child = commands.add_parser(command)
        child.add_argument("root", type=Path)
        if command == "seal":
            child.add_argument("--builder-image", required=True)
    args = parser.parse_args()
    if args.command == "snapshot":
        snapshot(args)
    elif args.command == "bundle":
        bundle(args)
    elif args.command == "verify-bundle":
        manifest = verify_bundle(args.root)
        print(f"Delivery {manifest['version']} inventory and checksums verified.")
    elif args.command == "wheel-lock":
        print(wheel_lock(args.root), end="")
    elif args.command == "verify":
        verify(args.root)
        print("Release input inventory verified.")
    else:
        if not re.fullmatch(r"sha256:[0-9a-f]{64}", args.builder_image):
            raise ValueError("builder image must be an immutable sha256 image ID")
        sources = json.loads((args.root / "SOURCE_REVISIONS.json").read_text())
        for name in ("stack-composer", "stack-content", "stack-planning"):
            if inventory(args.root / "sources" / name) != sources[name]["files"]:
                raise ValueError(f"source export changed after snapshot: {name}")
        for name in ("offline_delivery.py", "rebuild-offline.sh"):
            if digest(args.root / name) != digest(
                args.root / "sources/stack-composer/scripts" / name
            ):
                raise ValueError(f"delivery entry point differs from source: {name}")
        for name in ("builder-image.tar", "locks/native.txt", "locks/pyz.txt"):
            if not (args.root / name).is_file():
                raise ValueError(f"missing required input: {name}")
        for name in ("native", "pyz"):
            expected = (args.root / "locks" / f"{name}.txt").read_text()
            if wheel_lock(args.root / "wheels" / name) != expected:
                raise ValueError(f"wheel lock mismatch: {name}")
        manifest = {
            "schema_version": 1,
            "builder_image": args.builder_image,
            "sources": sources,
            "files": inventory(args.root),
        }
        with (args.root / "RELEASE_INPUTS.json").open("x") as output:
            output.write(json.dumps(manifest, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
