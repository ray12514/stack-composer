from __future__ import annotations

import grp
import hashlib
import os
import shutil
from pathlib import Path

from stack_composer.errors import Issue, ValidationFailed
from stack_composer.yaml_io import load_yaml, write_yaml


def publish_static_catalog(
    *,
    catalog_dir: Path,
    output_root: Path,
    published_at: str,
    reviewed_by: str,
    approved_by: str,
    publication_group: str | None = None,
    set_current: bool = False,
) -> Path:
    """Promote one reviewed static catalog into a versioned public release."""
    catalog_dir = catalog_dir.resolve()
    output_root = output_root.resolve()
    manifest = _load_manifest(catalog_dir)
    group = _resolve_publication_group(publication_group)
    _validate_static_plan(catalog_dir)
    _validate_no_symlinks(catalog_dir)
    _validate_reserved_metadata(catalog_dir)
    system = _safe_segment(manifest.get("system", {}).get("name"), "manifest.system.name")
    release = _safe_segment(manifest.get("release"), "manifest.release")
    destination = output_root / system / "static" / release
    pending = destination.with_name(f"{destination.name}.publishing")
    current = destination.parent / "current"

    if destination.exists():
        raise _failure(
            "static-publication-exists",
            destination,
            "published static catalog release already exists",
        )
    if pending.exists():
        raise _failure(
            "stale-publishing-path",
            pending,
            "stale static catalog publication path exists",
        )
    if set_current and os.path.lexists(current) and not current.is_symlink():
        raise _failure(
            "static-current-not-symlink",
            current,
            "current exists and is not a symbolic link",
        )

    try:
        _create_public_parents(
            output_root,
            pending.parent,
            group_id=group.gr_gid if group else None,
        )
        shutil.copytree(catalog_dir, pending)
        _write_checksum_inventory(pending)
        publication = {
            "schema_version": 1,
            "kind": "static-catalog-publication",
            "system": system,
            "release": release,
            "published_at": published_at,
            "reviewed_by": reviewed_by,
            "approved_by": approved_by,
            "checksum_inventory": "SHA256SUMS",
        }
        if group:
            publication["group"] = group.gr_name
        write_yaml(pending / "publication.yaml", publication)
        if group:
            _apply_publication_group(pending, group.gr_gid)
        _apply_publication_modes(pending, group_writable=group is not None)
        pending.replace(destination)
        if set_current:
            _set_current(destination, group_id=group.gr_gid if group else None)
    except OSError as exc:
        if pending.exists():
            shutil.rmtree(pending)
        raise _failure("static-publication", destination, str(exc)) from exc
    return destination


def verify_static_catalog_publication(
    *,
    catalog_dir: Path,
    publication: dict,
) -> None:
    """Verify a published catalog against its recorded source-file inventory."""
    _validate_no_symlinks(catalog_dir)
    inventory_name = str(publication.get("checksum_inventory") or "")
    if Path(inventory_name).name != inventory_name or inventory_name != "SHA256SUMS":
        raise _failure(
            "catalog-checksum-inventory",
            catalog_dir / inventory_name,
            "checksum inventory must be the catalog file SHA256SUMS",
        )
    inventory_path = catalog_dir / inventory_name
    try:
        lines = inventory_path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise _failure("catalog-checksum-inventory", inventory_path, str(exc)) from exc

    recorded: dict[str, str] = {}
    for line_number, line in enumerate(lines, start=1):
        digest, separator, relative = line.partition("  ")
        if (
            separator != "  "
            or len(digest) != 64
            or any(char not in "0123456789abcdef" for char in digest)
            or not relative
        ):
            raise _failure(
                "catalog-checksum-inventory",
                f"{inventory_path}:{line_number}",
                "expected '<sha256>  <relative-path>'",
            )
        candidate = (catalog_dir / relative).resolve()
        if candidate == catalog_dir or catalog_dir not in candidate.parents:
            raise _failure(
                "catalog-checksum-inventory",
                f"{inventory_path}:{line_number}",
                f"path escapes catalog root: {relative}",
            )
        if relative in recorded:
            raise _failure(
                "catalog-checksum-inventory",
                f"{inventory_path}:{line_number}",
                f"duplicate path: {relative}",
            )
        recorded[relative] = digest

    actual_files = {
        path.relative_to(catalog_dir).as_posix()
        for path in catalog_dir.rglob("*")
        if path.is_file()
        and path.relative_to(catalog_dir).as_posix() not in {"SHA256SUMS", "publication.yaml"}
    }
    if set(recorded) != actual_files:
        missing = sorted(actual_files - set(recorded))
        extra = sorted(set(recorded) - actual_files)
        raise _failure(
            "catalog-checksum-file-set",
            inventory_path,
            f"unlisted={missing!r} missing={extra!r}",
        )
    for relative, expected in recorded.items():
        actual = hashlib.sha256((catalog_dir / relative).read_bytes()).hexdigest()
        if actual != expected:
            raise _failure(
                "catalog-checksum-mismatch",
                catalog_dir / relative,
                f"expected {expected}; got {actual}",
            )


def _load_manifest(catalog_dir: Path) -> dict:
    manifest_path = catalog_dir / "manifest.yaml"
    try:
        manifest = load_yaml(manifest_path)
    except ValueError as exc:
        raise _failure("catalog-manifest", manifest_path, str(exc)) from exc
    if not isinstance(manifest, dict):
        raise _failure("catalog-manifest", manifest_path, "expected a YAML mapping")
    if manifest.get("kind") != "static-platform-catalog":
        raise _failure(
            "catalog-kind",
            manifest_path,
            "expected a static-platform-catalog manifest",
        )
    if manifest.get("scope_root") != "scopes":
        raise _failure(
            "catalog-not-relocatable",
            manifest_path,
            "scope_root must be the catalog-relative path 'scopes'",
        )
    return manifest


def _validate_static_plan(catalog_dir: Path) -> None:
    plan_path = catalog_dir / "reports" / "static-plan.yaml"
    try:
        plan = load_yaml(plan_path)
    except ValueError as exc:
        raise _failure("catalog-static-plan", plan_path, str(exc)) from exc
    if not isinstance(plan, dict):
        raise _failure("catalog-static-plan", plan_path, "expected a YAML mapping")
    missing = plan.get("missing_mpi_dependencies") or []
    if missing:
        details = ", ".join(
            f"{item.get('provider', '(unknown)')}:{item.get('package', '(unknown)')}"
            for item in missing
            if isinstance(item, dict)
        )
        raise _failure(
            "catalog-missing-mpi-dependencies",
            plan_path,
            details or "static plan reports unresolved MPI dependencies",
        )


def _validate_no_symlinks(catalog_dir: Path) -> None:
    for path in catalog_dir.rglob("*"):
        if path.is_symlink():
            raise _failure(
                "catalog-symlink",
                path,
                "published catalog content must not contain symbolic links",
            )


def _validate_reserved_metadata(catalog_dir: Path) -> None:
    for name in ("publication.yaml", "SHA256SUMS"):
        path = catalog_dir / name
        if os.path.lexists(path):
            raise _failure(
                "catalog-publication-metadata",
                path,
                "reviewed catalog uses a filename reserved for publication metadata",
            )


def _write_checksum_inventory(root: Path) -> None:
    lines = []
    for path in sorted(path for path in root.rglob("*") if path.is_file()):
        relative = path.relative_to(root).as_posix()
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        lines.append(f"{digest}  {relative}")
    (root / "SHA256SUMS").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _apply_publication_modes(root: Path, *, group_writable: bool) -> None:
    for path in [root, *root.rglob("*")]:
        if path.is_dir():
            path.chmod(0o2775 if group_writable else 0o755)
        elif path.is_file():
            executable = bool(path.stat().st_mode & 0o111)
            if group_writable:
                path.chmod(0o775 if executable else 0o664)
            else:
                path.chmod(0o755 if executable else 0o644)


def _create_public_parents(
    output_root: Path,
    destination_parent: Path,
    *,
    group_id: int | None,
) -> None:
    missing = []
    current = destination_parent
    while not current.exists():
        missing.append(current)
        if current == output_root:
            break
        current = current.parent
    destination_parent.mkdir(parents=True, exist_ok=True)
    for path in reversed(missing):
        if group_id is not None:
            os.chown(path, -1, group_id)
        path.chmod(0o2775 if group_id is not None else 0o755)


def _apply_publication_group(root: Path, group_id: int) -> None:
    for path in [root, *root.rglob("*")]:
        os.chown(path, -1, group_id)


def _set_current(destination: Path, *, group_id: int | None) -> None:
    current = destination.parent / "current"
    pending = destination.parent / ".current.updating"
    if os.path.lexists(pending):
        pending.unlink()
    pending.symlink_to(destination.name, target_is_directory=True)
    if group_id is not None:
        os.chown(pending, -1, group_id, follow_symlinks=False)
    pending.replace(current)


def _resolve_publication_group(group_name: str | None) -> grp.struct_group | None:
    if group_name is None:
        return None
    try:
        return grp.getgrnam(group_name)
    except KeyError as exc:
        raise _failure(
            "publication-group",
            group_name,
            "Unix group does not exist on this system",
        ) from exc


def _safe_segment(value: object, issue_path: str) -> str:
    segment = str(value or "").strip()
    if not segment or segment in {".", ".."} or Path(segment).name != segment:
        raise _failure("catalog-identity", issue_path, "must be one safe path segment")
    return segment


def _failure(code: str, path: Path | str, message: str) -> ValidationFailed:
    return ValidationFailed([Issue("error", code, str(path), message)])
