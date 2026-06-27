from __future__ import annotations

from pathlib import Path
from typing import Any

from stack_composer.errors import Issue
from stack_composer.schema_registry import validate_schema
from stack_composer.yaml_io import load_yaml


def load_deployment(path: Path) -> tuple[dict[str, Any], list[Issue]]:
    try:
        data = load_yaml(path)
    except ValueError as exc:
        return {}, [Issue("error", "invalid-yaml", str(path), str(exc))]
    issues = validate_schema("deployment", data, str(path))
    return data or {}, issues


def validate_deployment_for_profile(
    deployment: dict[str, Any], profile: dict[str, Any], path: Path
) -> list[Issue]:
    expected = (profile.get("system") or {}).get("name")
    actual = deployment.get("system")
    if actual == expected:
        return []
    return [
        Issue(
            "error",
            "deployment-system-mismatch",
            str(path),
            f"deployment system {actual!r} does not match profile.system.name {expected!r}",
        )
    ]
