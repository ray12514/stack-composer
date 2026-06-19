#!/usr/bin/env python3
"""Check bundled runtime dependency license metadata.

This bootstrap implementation enforces that every runtime dependency in
pyproject.toml is represented in THIRD_PARTY.toml, has an allowed SPDX license,
and has a declared license text file. Full wheel metadata regeneration remains a
Phase 1 follow-up, but build-pyz already refuses obvious manifest drift.
"""

from __future__ import annotations

import argparse
import re
import shutil
import sys
from dataclasses import dataclass
from importlib import metadata
from pathlib import Path

ALLOWED_LICENSES = {
    "Apache-2.0",
    "BSD-2-Clause",
    "BSD-3-Clause",
    "ISC",
    "MIT",
    "MPL-2.0",
    "Python-2.0",
}


@dataclass(frozen=True)
class Dependency:
    name: str
    license_spdx: str
    license_file: str


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="Check manifest consistency.")
    parser.add_argument(
        "--sync-resources",
        action="store_true",
        help="Copy root third-party manifest and license texts into package resources.",
    )
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    errors = check_manifest(root)
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    if args.sync_resources:
        sync_resources(root)
    print("third-party manifest check passed")
    return 0


def check_manifest(root: Path) -> list[str]:
    runtime_deps = runtime_dependencies(root / "pyproject.toml")
    manifest = third_party_manifest(root / "THIRD_PARTY.toml")
    errors: list[str] = []
    runtime_names = {normalize_name(name) for name in runtime_deps}
    manifest_names = set(manifest)
    for missing in sorted(runtime_names - manifest_names):
        errors.append(f"runtime dependency {missing!r} missing from THIRD_PARTY.toml")
    for extra in sorted(manifest_names - runtime_names):
        errors.append(f"THIRD_PARTY.toml contains non-runtime dependency {extra!r}")
    for name, dep in sorted(manifest.items()):
        if dep.license_spdx not in ALLOWED_LICENSES:
            errors.append(f"dependency {name!r} has unapproved license {dep.license_spdx!r}")
        license_path = root / dep.license_file
        if not license_path.exists():
            errors.append(f"dependency {name!r} missing license file {dep.license_file!r}")
        try:
            metadata.distribution(dep.name)
        except metadata.PackageNotFoundError:
            errors.append(f"dependency {dep.name!r} is not installed in the build environment")
    return errors


def runtime_dependencies(pyproject: Path) -> list[str]:
    deps = []
    in_dependencies = False
    for line in pyproject.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped == "dependencies = [":
            in_dependencies = True
            continue
        if in_dependencies and stripped == "]":
            return deps
        if not in_dependencies or not stripped or stripped.startswith("#"):
            continue
        match = re.match(r'"([A-Za-z0-9_.-]+)', stripped)
        if match:
            deps.append(match.group(1))
    return deps


def third_party_manifest(path: Path) -> dict[str, Dependency]:
    entries: dict[str, Dependency] = {}
    current: dict[str, str] | None = None
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped == "[[dependency]]":
            if current:
                add_dependency(entries, current)
            current = {}
            continue
        if current is None or "=" not in stripped:
            continue
        key, raw_value = stripped.split("=", 1)
        current[key.strip()] = raw_value.strip().strip('"')
    if current:
        add_dependency(entries, current)
    return entries


def add_dependency(entries: dict[str, Dependency], data: dict[str, str]) -> None:
    dep = Dependency(
        name=data["name"],
        license_spdx=data["license_spdx"],
        license_file=data["license_file"],
    )
    entries[normalize_name(dep.name)] = dep


def normalize_name(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def sync_resources(root: Path) -> None:
    resources = root / "src" / "stack_composer" / "resources"
    licenses = resources / "THIRD_PARTY_LICENSES"
    licenses.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(root / "THIRD_PARTY.toml", resources / "THIRD_PARTY.toml")
    for source in sorted((root / "THIRD_PARTY_LICENSES").glob("*.txt")):
        shutil.copyfile(source, licenses / source.name)


if __name__ == "__main__":
    raise SystemExit(main())
