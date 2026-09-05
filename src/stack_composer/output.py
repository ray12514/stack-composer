"""Owned staging and recoverable replacement of generated output trees."""

from __future__ import annotations

import os
import shutil
import stat
import tempfile
import warnings
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from stack_composer.errors import Issue, ValidationFailed


def safe_segment(value: object, field: str) -> str:
    """Accept an identity, never an absolute or multi-component path."""
    if (
        not isinstance(value, str)
        or not value.strip()
        or value != value.strip()
        or value in {".", ".."}
        or "/" in value
        or "\\" in value
        or any(ord(char) < 32 for char in value)
    ):
        raise _failure("output-identity", field, "must be one safe path segment")
    return value


def managed_output_path(root: Path, *segments: str) -> Path:
    """Resolve names below the declared root without following an escaping link."""
    target = root.joinpath(*(safe_segment(part, "output identity") for part in segments))
    resolved_root = root.resolve()
    resolved_target = target.resolve()
    if target.is_symlink() or resolved_root not in resolved_target.parents:
        raise _failure("output-path-escape", target, "output must remain inside its declared root")
    return target


@contextmanager
def output_transaction(
    destination: Path,
    *,
    overwrite: bool = False,
    suffix: str = ".rendering",
    exists_code: str = "workspace-exists",
    pending_code: str = "stale-render-path",
) -> Iterator[Path]:
    """Yield an exclusively owned staging tree and promote it after validation.

    Existing output is backed up until replacement succeeds. A failed rollback
    retains that backup and reports its path. Replacement of a nonempty directory
    is recoverable, not a portable atomic exchange or a power-loss guarantee.
    """
    _check_destination(destination, overwrite, exists_code)
    pending = destination.with_name(destination.name + suffix)
    # mkdir is the ownership claim. In particular, never clean up a directory
    # when mkdir failed because another invocation created it first.
    try:
        pending.mkdir(parents=True, exist_ok=False)
    except FileExistsError as exc:
        raise _failure(
            pending_code, pending, "pending output already exists; it was not modified"
        ) from exc
    try:
        yield pending
        _check_destination(destination, overwrite, exists_code)
        _promote(pending, destination)
    finally:
        _cleanup_owned(pending)


def _check_destination(destination: Path, overwrite: bool, exists_code: str) -> None:
    if destination.is_symlink():
        raise _failure("output-symlink", destination, "refusing to replace an output symlink")
    if destination.exists():
        if not destination.is_dir():
            raise _failure("output-not-directory", destination, "output is not a directory")
        if not overwrite:
            raise _failure(exists_code, destination, "workspace already exists; use --overwrite")


def _promote(pending: Path, destination: Path) -> None:
    if not destination.exists():
        pending.replace(destination)
        return

    backup_root = Path(
        tempfile.mkdtemp(prefix=f".{destination.name}.previous-", dir=destination.parent)
    )
    backup = backup_root / "workspace"
    try:
        previous = destination.stat()
        if backup_root.stat().st_gid != previous.st_gid:
            os.chown(backup_root, -1, previous.st_gid)
        backup_root.chmod(stat.S_IMODE(previous.st_mode))
        destination.rename(backup)
        try:
            pending.replace(destination)
        except BaseException as exc:
            try:
                # Use the OS rename directly so a failed promotion is a separate
                # operation from recovery of the previous successful tree.
                os.rename(backup, destination)
            except OSError as recovery_error:
                raise _failure(
                    "output-recovery",
                    destination,
                    f"replacement failed ({exc}); restore the retained workspace at {backup}; "
                    f"automatic recovery failed: {recovery_error}",
                ) from exc
            raise
    except BaseException:
        if not backup.exists():
            _cleanup_owned(backup_root)
        raise
    _cleanup_owned(backup_root)


def _cleanup_owned(path: Path) -> None:
    if not path.exists():
        return
    try:
        shutil.rmtree(path)
    except OSError as exc:
        # Never undo a completed promotion or hide its original failure merely
        # because deletion of our own old/staged files was denied.
        warnings.warn(
            f"retained generated-output recovery path {path}: {exc}", RuntimeWarning, stacklevel=2
        )


def _failure(code: str, path: Path | str, message: str) -> ValidationFailed:
    return ValidationFailed([Issue("error", code, str(path), message)])
