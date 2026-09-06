"""Capture and verify exact, commit-based offline release inputs (not a signing service)."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import shutil
import subprocess
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


def inventory(root: Path) -> dict:
    result = {}
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise ValueError(f"input capsule must not contain symlinks: {path}")
        if path.is_file() and path != root / "RELEASE_INPUTS.json":
            result[path.relative_to(root).as_posix()] = {
                "sha256": digest(path),
                "mode": path.stat().st_mode & 0o777,
            }
        elif not path.is_dir() and path != root / "RELEASE_INPUTS.json":
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
            for member in archive.getmembers():
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


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    capture = commands.add_parser("snapshot")
    for name in ("stack-composer", "stack-content", "stack-planning", "output"):
        capture.add_argument("--" + name, type=Path, required=True)
    for command in ("verify", "seal", "wheel-lock"):
        child = commands.add_parser(command)
        child.add_argument("root", type=Path)
        if command == "seal":
            child.add_argument("--builder-image", required=True)
    args = parser.parse_args()
    if args.command == "snapshot":
        snapshot(args)
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
