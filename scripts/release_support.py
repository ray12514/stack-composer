"""Clean source staging and byte-exact application inventories for releases."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import shutil
import tarfile
from pathlib import Path
from zipfile import ZipFile


def package_files(root: Path) -> list[Path]:
    return sorted(
        path for path in (root / "src/stack_composer").rglob("*")
        if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc"
    )


def package_inventory(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root / "src").as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in package_files(root)
    }


def stage_project(root: Path, destination: Path) -> None:
    """Export only current build inputs, never persistent build/lib or egg-info."""
    destination.mkdir(parents=True, exist_ok=False)
    for name in ("pyproject.toml", "README.md", "LICENSE", "THIRD_PARTY.toml"):
        shutil.copy2(root / name, destination / name)
    shutil.copytree(root / "THIRD_PARTY_LICENSES", destination / "THIRD_PARTY_LICENSES")
    for path in package_files(root):
        target = destination / path.relative_to(root)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)


def verify_archive(root: Path, artifact: Path) -> None:
    expected = package_inventory(root)
    actual = {}
    with ZipFile(artifact) as archive:
        for entry in archive.infolist():
            name = entry.filename.removeprefix("site-packages/")
            if not name.startswith("stack_composer/") or entry.is_dir():
                continue
            if "__pycache__" in Path(name).parts or name.endswith(".pyc"):
                raise ValueError(f"compiled cache leaked into release: {name}")
            if name in actual:
                raise ValueError(f"duplicate application archive entry: {name}")
            actual[name] = hashlib.sha256(archive.read(entry)).hexdigest()
    missing = sorted(expected.keys() - actual.keys())
    extra = sorted(actual.keys() - expected.keys())
    changed = sorted(
        name for name in expected.keys() & actual.keys() if expected[name] != actual[name]
    )
    if missing or extra or changed:
        raise ValueError(
            f"application inventory mismatch: missing={missing}, extra={extra}, changed={changed}"
        )


def checksums(root: Path) -> None:
    entries = [
        f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.relative_to(root).as_posix()}\n"
        for path in sorted(root.rglob("*"))
        if path.is_file() and path != root / "SHA256SUMS"
    ]
    (root / "SHA256SUMS").write_text("".join(entries), encoding="utf-8")


def release_archive(root: Path, artifact: Path, epoch: int, preserve_modes: bool = False) -> None:
    """Archive a delivery tree without host ownership, times, or gzip filenames."""
    root = root.resolve()
    if epoch < 0 or not root.is_dir():
        raise ValueError("archive requires a directory and a nonnegative epoch")
    if artifact.resolve().is_relative_to(root):
        raise ValueError("archive output must be outside its input tree")
    paths = [root, *sorted(root.rglob("*"))]
    for path in paths:
        if path.is_symlink():
            if Path(os.readlink(path)).is_absolute() or not path.resolve().is_relative_to(root):
                raise ValueError(f"delivery symlink escapes its tree: {path.relative_to(root)}")
            if not path.exists():
                raise ValueError(f"broken delivery symlink: {path.relative_to(root)}")
        elif not path.is_file() and not path.is_dir():
            raise ValueError(f"unsupported delivery entry: {path}")
    # Exclusive creation keeps a failed/repeated build from replacing an existing release.
    with artifact.open("xb") as output:
        with gzip.GzipFile(filename="", mode="wb", fileobj=output, mtime=epoch) as compressed:
            with tarfile.open(fileobj=compressed, mode="w", format=tarfile.PAX_FORMAT) as archive:
                for path in paths:
                    info = archive.gettarinfo(str(path), path.relative_to(root.parent).as_posix())
                    info.uid = info.gid = 0
                    info.uname = info.gname = ""
                    info.mtime = epoch
                    info.pax_headers = {}
                    if not preserve_modes:
                        info.mode = 0o755 if info.isdir() or info.mode & 0o111 else 0o644
                    if info.isfile():
                        with path.open("rb") as content:
                            archive.addfile(info, content)
                    else:
                        archive.addfile(info)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    stage = commands.add_parser("stage")
    stage.add_argument("root", type=Path)
    stage.add_argument("destination", type=Path)
    verify = commands.add_parser("verify")
    verify.add_argument("root", type=Path)
    verify.add_argument("artifact", type=Path)
    inventory = commands.add_parser("inventory")
    inventory.add_argument("root", type=Path)
    checksum = commands.add_parser("checksums")
    checksum.add_argument("root", type=Path)
    archive = commands.add_parser("archive")
    archive.add_argument("root", type=Path)
    archive.add_argument("artifact", type=Path)
    archive.add_argument("--epoch", type=int, required=True)
    archive.add_argument(
        "--preserve-modes", action="store_true",
        help="Retain recorded permissions when wrapping an already sealed input capsule.",
    )
    args = parser.parse_args()
    if args.command == "stage":
        stage_project(args.root, args.destination)
    elif args.command == "verify":
        verify_archive(args.root, args.artifact)
    elif args.command == "inventory":
        print(json.dumps(package_inventory(args.root), indent=2, sort_keys=True))
    elif args.command == "archive":
        release_archive(args.root, args.artifact, args.epoch, args.preserve_modes)
    else:
        checksums(args.root)


if __name__ == "__main__":
    main()
