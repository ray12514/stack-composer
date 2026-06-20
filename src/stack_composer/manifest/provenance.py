from __future__ import annotations

from typing import Any

SUPPORTED_LOCKFILE_VERSIONS = range(4, 7)


def inspect_lockfile(lockfile: dict[str, Any], source: str) -> dict[str, Any]:
    validate_lockfile_shape(lockfile, source)
    specs = lockfile["concrete_specs"]
    roots = lockfile["roots"]
    root_hashes = [root.get("hash") for root in roots if isinstance(root, dict)]
    install_root = first_root_prefix(specs, root_hashes)
    provenance = {
        "stack_built": 0,
        "platform_backed": 0,
        "site_external": 0,
        "spack_built": 0,
    }
    for spec in specs.values():
        if not isinstance(spec, dict):
            continue
        bucket = provenance_bucket(spec)
        provenance[bucket] += 1
    return {"install_root": install_root, "provenance_summary": provenance}


def validate_lockfile_shape(lockfile: dict[str, Any], source: str) -> None:
    meta = lockfile.get("_meta")
    if not isinstance(meta, dict):
        raise ValueError(f"unsupported spack.lock shape in {source}: missing _meta")
    version = meta.get("lockfile-version")
    if version not in SUPPORTED_LOCKFILE_VERSIONS:
        supported = f"{min(SUPPORTED_LOCKFILE_VERSIONS)}-{max(SUPPORTED_LOCKFILE_VERSIONS)}"
        raise ValueError(
            "unsupported spack.lock shape in "
            f"{source}: got lockfile-version={version!r}, supported={supported}"
        )
    if not isinstance(lockfile.get("roots"), list):
        raise ValueError(f"unsupported spack.lock shape in {source}: roots must be a list")
    if not isinstance(lockfile.get("concrete_specs"), dict):
        raise ValueError(
            f"unsupported spack.lock shape in {source}: concrete_specs must be a mapping"
        )


def first_root_prefix(specs: dict[str, Any], root_hashes: list[str | None]) -> str | None:
    for root_hash in root_hashes:
        if root_hash is None:
            continue
        spec = specs.get(root_hash)
        if isinstance(spec, dict) and isinstance(spec.get("prefix"), str):
            return spec["prefix"]
    for spec in specs.values():
        if isinstance(spec, dict) and isinstance(spec.get("prefix"), str):
            return spec["prefix"]
    return None


def provenance_bucket(spec: dict[str, Any]) -> str:
    if spec.get("external"):
        path = ""
        external = spec.get("external")
        if isinstance(external, dict):
            path = str(external.get("path") or external.get("prefix") or "")
        if path.startswith(("/opt/cray", "/opt/rocm", "/usr")):
            return "platform_backed"
        return "site_external"
    if spec.get("namespace") not in (None, "builtin", "spack_repo.builtin"):
        return "stack_built"
    return "spack_built"
