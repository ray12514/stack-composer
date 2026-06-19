#!/usr/bin/env python3
"""Generate and check bundled runtime dependency license metadata."""

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
    version: str
    license_spdx: str
    license_file: str
    project_url: str
    source_url: str
    purpose: str


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="Check manifest consistency.")
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="Rewrite THIRD_PARTY.toml and license texts from installed wheels.",
    )
    parser.add_argument(
        "--sync-resources",
        action="store_true",
        help="Copy root third-party manifest and license texts into package resources.",
    )
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    if args.refresh:
        refresh_manifest(root)
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
            distribution = metadata.distribution(dep.name)
        except metadata.PackageNotFoundError:
            errors.append(f"dependency {dep.name!r} is not installed in the build environment")
            continue
        if is_exact_version(dep.version) and dep.version != distribution.version:
            errors.append(
                f"dependency {dep.name!r} manifest version {dep.version!r} "
                f"does not match installed version {distribution.version!r}"
            )
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
        version=data["version"],
        license_spdx=data["license_spdx"],
        license_file=data["license_file"],
        project_url=data.get("project_url", ""),
        source_url=data.get("source_url", ""),
        purpose=data.get("purpose", ""),
    )
    entries[normalize_name(dep.name)] = dep


def normalize_name(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def is_exact_version(version: str) -> bool:
    return not version.startswith((">", "<", "=", "~", "!"))


def refresh_manifest(root: Path) -> None:
    pyproject = root / "pyproject.toml"
    manifest_path = root / "THIRD_PARTY.toml"
    existing = third_party_manifest(manifest_path)
    dependencies = []
    for name in runtime_dependencies(pyproject):
        key = normalize_name(name)
        if key not in existing:
            raise SystemExit(f"{name!r} is missing from THIRD_PARTY.toml; add purpose/URLs first")
        old = existing[key]
        distribution = metadata.distribution(old.name)
        license_file = f"THIRD_PARTY_LICENSES/{old.name}.txt"
        write_license_text(root / license_file, distribution)
        dependencies.append(
            Dependency(
                name=old.name,
                version=distribution.version,
                license_spdx=old.license_spdx,
                license_file=license_file,
                project_url=old.project_url,
                source_url=old.source_url,
                purpose=old.purpose,
            )
        )
    manifest_path.write_text(render_manifest(dependencies), encoding="utf-8")


def write_license_text(path: Path, distribution: metadata.Distribution) -> None:
    source = find_license_file(distribution)
    if source is None:
        raise SystemExit(f"could not find license text for {distribution.metadata['Name']}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source.read_text(encoding="utf-8", errors="replace"), encoding="utf-8")


def find_license_file(distribution: metadata.Distribution) -> Path | None:
    files = distribution.files or []
    candidates = []
    for file in files:
        name = file.name.lower()
        if name in {"license", "license.txt", "license.rst", "copying", "copying.txt"}:
            candidates.append(file)
    for candidate in sorted(candidates, key=lambda item: item.as_posix()):
        path = Path(distribution.locate_file(candidate))
        if path.is_file():
            return path
    return None


def render_manifest(dependencies: list[Dependency]) -> str:
    lines = [
        "[meta]",
        'generated_by = "scripts/generate-third-party.py"',
        'generated_at = "not-recorded"',
        'status = "generated from installed runtime distributions"',
        "",
    ]
    for dep in dependencies:
        lines.extend(
            [
                "[[dependency]]",
                f'name = "{dep.name}"',
                f'version = "{dep.version}"',
                f'license_spdx = "{dep.license_spdx}"',
                f'project_url = "{dep.project_url}"',
                f'source_url = "{dep.source_url}"',
                f'license_file = "{dep.license_file}"',
                f'purpose = "{dep.purpose}"',
                "",
            ]
        )
    return "\n".join(lines)


def sync_resources(root: Path) -> None:
    resources = root / "src" / "stack_composer" / "resources"
    licenses = resources / "THIRD_PARTY_LICENSES"
    licenses.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(root / "THIRD_PARTY.toml", resources / "THIRD_PARTY.toml")
    for source in sorted((root / "THIRD_PARTY_LICENSES").glob("*.txt")):
        shutil.copyfile(source, licenses / source.name)


if __name__ == "__main__":
    raise SystemExit(main())
