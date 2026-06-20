from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

from stack_composer.manifest.provenance import inspect_lockfile
from stack_composer.model.manifest import load_release_manifest
from stack_composer.render.digest import sha256_file
from stack_composer.schema_registry import validate_schema
from stack_composer.yaml_io import load_yaml, write_yaml


def finalize_manifest(
    *,
    workspace: Path,
    build_host_name: str,
    lockfiles_dir: Path,
    platform_module_prereqs_path: Path,
    buildcache_destinations_path: Path,
    verify_results_path: Path,
    force: bool,
) -> dict[str, Any]:
    manifest_path = workspace / "release-manifest.yaml"
    manifest, issues = load_release_manifest(manifest_path)
    if issues:
        messages = "; ".join(i.message for i in issues)
        raise ValueError("draft manifest schema validation failed: " + messages)
    if manifest.get("phase") == "final" and not force:
        raise ValueError("manifest is already final; use --force to rewrite it")
    if manifest.get("phase") not in {"draft", "final"}:
        raise ValueError(f"expected manifest phase draft/final, got {manifest.get('phase')!r}")

    prereqs = load_lane_prereqs(platform_module_prereqs_path)
    buildcache = load_buildcache_destinations(buildcache_destinations_path)
    verify_report = load_verify_report(verify_results_path)

    manifest["phase"] = "final"
    manifest["spack"] = normalize_spack_block(verify_report)
    manifest["build_host"] = normalize_build_host_block(verify_report, build_host_name)
    manifest["verification"] = normalize_verification_block(verify_report)
    if "previous_release" in verify_report:
        manifest["previous_release"] = verify_report["previous_release"]

    manifest.setdefault("buildcache", {})["push_destinations"] = buildcache
    lane_overrides = verify_report.get("lanes") or {}
    for lane in manifest["lanes"]:
        lane_report = lane_overrides.get(lane["name"], {})
        lockfile, lockfile_rel = lockfile_for_lane(lockfiles_dir, lane)
        lock_data = load_yaml(lockfile)
        lock_info = inspect_lockfile(lock_data, lockfile.as_posix())
        lane["lockfile"] = lockfile_rel.as_posix()
        lane["lockfile_digest"] = sha256_file(lockfile)
        lane["install_root"] = lane_report.get("install_root") or lock_info.get("install_root")
        if not lane["install_root"]:
            raise ValueError(f"cannot determine install_root for lane {lane['name']!r}")
        lane["provenance_summary"] = lane_report.get("provenance_summary") or lock_info[
            "provenance_summary"
        ]
        lane["platform_module_prereqs"] = prereqs.get(lane["name"], [])

    manifest_issues = validate_schema("release-manifest", manifest, manifest_path.as_posix())
    if manifest_issues:
        messages = "; ".join(i.message for i in manifest_issues)
        raise ValueError("final manifest schema validation failed: " + messages)
    atomic_write_manifest(manifest_path, manifest)
    return manifest


def load_lane_prereqs(path: Path) -> dict[str, list[str]]:
    data = load_yaml(path) or {}
    raw = data.get("lanes") if isinstance(data, dict) and "lanes" in data else data
    if not isinstance(raw, dict):
        raise ValueError("platform-module-prereqs must be a mapping of lane name to module list")
    result = {}
    for lane, modules in raw.items():
        if modules is None:
            modules = []
        if not isinstance(modules, list):
            raise ValueError(f"platform-module-prereqs lane {lane!r} must be a list")
        result[str(lane)] = [str(module) for module in modules]
    return result


def load_buildcache_destinations(path: Path) -> list[dict[str, Any]]:
    data = load_yaml(path) or []
    destinations = data.get("push_destinations", data) if isinstance(data, dict) else data
    if not isinstance(destinations, list):
        raise ValueError("buildcache-destinations must be a list or push_destinations mapping")
    return destinations


def load_verify_report(path: Path) -> dict[str, Any]:
    data = load_yaml(path) or {}
    if not isinstance(data, dict):
        raise ValueError("verify-results must be a mapping")
    return data


def normalize_spack_block(report: dict[str, Any]) -> dict[str, Any]:
    spack = report.get("spack") or {}
    if not isinstance(spack, dict) or not spack.get("version"):
        raise ValueError("verify-results must include spack.version")
    return dict(spack)


def normalize_build_host_block(report: dict[str, Any], build_host_name: str) -> dict[str, Any]:
    build_host = dict(report.get("build_host") or {})
    build_host.setdefault("hostname", build_host_name)
    missing = [
        key
        for key in ("hostname", "os", "os_major", "glibc", "cpu")
        if key not in build_host
    ]
    if missing:
        raise ValueError("verify-results build_host missing required keys: " + ", ".join(missing))
    return build_host


def normalize_verification_block(report: dict[str, Any]) -> dict[str, Any]:
    verification = report.get("verification") or {}
    if not isinstance(verification, dict):
        raise ValueError("verify-results verification must be a mapping")
    missing = [
        key
        for key in ("spack_verify_libraries", "spack_verify_manifest", "site_smoke_tests")
        if key not in verification
    ]
    if missing:
        raise ValueError("verify-results verification missing required keys: " + ", ".join(missing))
    return verification


def lockfile_for_lane(lockfiles_dir: Path, lane: dict[str, Any]) -> tuple[Path, Path]:
    env_path = Path(lane["env_path"])
    if env_path.parts and env_path.parts[0] == "environments":
        relative_env = Path(*env_path.parts[1:])
    else:
        relative_env = env_path
    relative = relative_env / "spack.lock"
    lockfile = lockfiles_dir / relative
    if not lockfile.is_file():
        raise ValueError(f"lockfile for lane {lane['name']!r} is missing: {lockfile}")
    return lockfile, relative


def atomic_write_manifest(path: Path, manifest: dict[str, Any]) -> None:
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, delete=False
    ) as handle:
        tmp_path = Path(handle.name)
    try:
        write_yaml(tmp_path, manifest)
        tmp_path.replace(path)
    except Exception:
        if tmp_path.exists():
            tmp_path.unlink()
        raise
