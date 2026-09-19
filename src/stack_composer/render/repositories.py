"""Workspace repository layout shared by registration and materialization."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from stack_composer.output import safe_segment
from stack_composer.yaml_io import load_yaml


def repository_output_parts(repo: dict[str, Any]) -> tuple[str, ...]:
    """Keep API v2's Python namespace path, and API v1's named repository path."""
    metadata = load_yaml(Path(repo["path"]) / "repo.yaml")["repo"]
    api = metadata.get("api", "v1.0")
    if isinstance(api, str) and api.startswith("v2."):
        parts = ("spack_repo", *repo["namespace"].split("."))
    else:
        parts = (repo["name"],)
    return tuple(safe_segment(part, "package repository output") for part in parts)
