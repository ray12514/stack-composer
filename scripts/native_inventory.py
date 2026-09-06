"""Collect artifact evidence for an unpromoted native candidate, not a license clearance."""

from __future__ import annotations

import hashlib
import json
import platform
import re
import shutil
import subprocess
import sys
import sysconfig
from importlib import metadata
from pathlib import Path

from release_support import package_inventory


def verify_frozen_application(source: Path, artifact: Path) -> list[str]:
    from PyInstaller.archive.readers import CArchiveReader

    expected_files = package_inventory(source)
    expected_modules = set()
    for name, digest in expected_files.items():
        if name.endswith(".py"):
            module = name.removesuffix(".py").replace("/", ".")
            expected_modules.add(module.removesuffix(".__init__"))
        else:
            payload = artifact / "_internal" / name
            if not payload.is_file() or hashlib.sha256(payload.read_bytes()).hexdigest() != digest:
                raise ValueError(f"missing or changed frozen resource: {name}")
    # The entry script is in the outer executable archive, not the module PYZ.
    expected_modules.remove("stack_composer.__main__")
    archive = CArchiveReader(str(artifact / "stack-composer"))
    if "__main__" not in archive.toc:
        raise ValueError("frozen entry script missing")
    pyz = archive.open_embedded_archive("PYZ.pyz")
    actual = {
        name for name in pyz.toc
        if name == "stack_composer" or name.startswith("stack_composer.")
    }
    if actual != expected_modules:
        raise ValueError(
            f"frozen module inventory mismatch: missing={sorted(expected_modules - actual)}, "
            f"extra={sorted(actual - expected_modules)}"
        )
    return sorted(actual)


def main() -> None:
    root, source, artifact = (Path(value) for value in sys.argv[1:])
    frozen_modules = verify_frozen_application(source, artifact)
    for name in ("README.md", "LICENSE", "THIRD_PARTY.toml"):
        shutil.copy2(root / name, artifact / name)
    shutil.copy2(root / "scripts/spack-build", artifact / "spack-build")
    shutil.copytree(root / "THIRD_PARTY_LICENSES", artifact / "THIRD_PARTY_LICENSES")
    notices = artifact / "NATIVE_LICENSES"
    notices.mkdir()
    distributions = []
    for distribution in sorted(metadata.distributions(), key=lambda item: item.metadata["Name"]):
        name = distribution.metadata["Name"]
        licenses = []
        for path in sorted(distribution.files or []):
            if any(
                part.lower().startswith(("license", "copying", "notice")) for part in path.parts
            ):
                origin = Path(distribution.locate_file(path))
                if origin.is_file():
                    target = notices / name / str(path).replace("../", "")
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(origin, target)
                    licenses.append(target.relative_to(artifact).as_posix())
        distributions.append({"name": name, "version": distribution.version, "notices": licenses})
    python_notices = []
    candidates = [Path(sysconfig.get_path("stdlib")) / "LICENSE.txt"]
    for base in (Path("/usr/share/licenses"), Path(sys.base_prefix)):
        if base == Path("/usr/share/licenses") and base.exists():
            candidates.extend(sorted(base.glob("python3.12*/LICENSE*")))
    for index, origin in enumerate(candidates):
        if origin.is_file():
            target = notices / f"CPython-{index}-{origin.name}"
            shutil.copy2(origin, target)
            python_notices.append(target.relative_to(artifact).as_posix())
    binaries = []
    glibc_versions = set()
    for path in sorted(artifact.rglob("*")):
        if not path.is_file():
            continue
        with path.open("rb") as handle:
            magic = handle.read(4)
        if magic != b"\x7fELF":
            continue
        versions = subprocess.run(
            ["readelf", "--version-info", str(path)], capture_output=True, text=True, check=True
        )
        required = sorted(set(re.findall(r"\bGLIBC_([0-9]+(?:\.[0-9]+)+)", versions.stdout)))
        glibc_versions.update(tuple(map(int, version.split("."))) for version in required)
        binaries.append({
            "path": path.relative_to(artifact).as_posix(),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "license_review": "required before promotion",
            "glibc_symbol_versions": required,
        })
    if not binaries or not glibc_versions or max(glibc_versions) > (2, 28):
        raise ValueError(
            "candidate must contain Linux ELF files requiring glibc no newer than 2.28"
        )
    rpm_inventory = None
    if shutil.which("rpm"):
        result = subprocess.run(["rpm", "-qa"], capture_output=True, text=True, check=True)
        rpm_inventory = sorted(result.stdout.splitlines())
    evidence = {
        "status": "candidate-only; not approved for production",
        "python": sys.version,
        "platform": sys.platform,
        "machine": platform.machine(),
        "libc": platform.libc_ver(),
        "application_files": package_inventory(source),
        "frozen_application_modules": frozen_modules,
        "maximum_glibc_symbol": ".".join(map(str, max(glibc_versions))),
        "builder_distributions": distributions,
        "builder_rpms": rpm_inventory,
        "python_notices": python_notices,
        "elf_files": binaries,
        "remaining_gates": [
            "Click/Python support decision", "complete frozen-runtime license and security review",
            "target-system ABI/shared-filesystem acceptance",
            "release-specific two-build reproducibility receipt",
        ],
    }
    (artifact / "NATIVE_COMPONENTS.json").write_text(json.dumps(evidence, indent=2) + "\n")
    (artifact / "README.native.txt").write_text(
        "Candidate only. Run ./stack-composer directly; do not prefix it with Python.\n"
        "Keep _internal beside the executable. No target Python or Shiv cache is needed.\n"
        "Do not replace the CSE trial default until the documented promotion gates pass.\n"
    )


if __name__ == "__main__":
    main()
