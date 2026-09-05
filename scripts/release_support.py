"""Clean source staging and byte-exact application inventories for releases."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
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
    args = parser.parse_args()
    if args.command == "stage":
        stage_project(args.root, args.destination)
    elif args.command == "verify":
        verify_archive(args.root, args.artifact)
    elif args.command == "inventory":
        print(json.dumps(package_inventory(args.root), indent=2, sort_keys=True))
    else:
        checksums(args.root)


if __name__ == "__main__":
    main()
