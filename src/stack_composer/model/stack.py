from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

from stack_composer.schema_registry import validate_schema
from stack_composer.yaml_io import load_yaml


def load_stack(path: Path) -> tuple[dict[str, Any], list]:
    data = load_yaml(path)
    return data, validate_schema("stack", data, str(path))


def load_defaults(path: Path) -> tuple[dict[str, Any], list]:
    data = load_yaml(path)
    return data, validate_schema("defaults", data, str(path))


def merge_defaults(defaults: dict[str, Any], stack: dict[str, Any]) -> dict[str, Any]:
    """Merge site defaults under the stack. Selection policy (compilers/mpi/gpu/
    target) and site conventions both land at stack top level; a stack key (or a
    per-build field) overrides the default."""
    merged = deepcopy(defaults)
    deep_update(merged, stack)
    return merged


def deep_update(base: dict[str, Any], overlay: dict[str, Any]) -> None:
    for key, value in overlay.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            deep_update(base[key], value)
            continue
        base[key] = deepcopy(value)
