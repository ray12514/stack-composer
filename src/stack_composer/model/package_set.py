from __future__ import annotations

from pathlib import Path
from typing import Any

from stack_composer.schema_registry import validate_schema
from stack_composer.yaml_io import load_yaml


def load_package_set(path: Path) -> tuple[dict[str, Any], list]:
    data = load_yaml(path)
    return data, validate_schema("package-set", data, str(path))
