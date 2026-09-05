from __future__ import annotations

from pathlib import Path
from typing import Any

from stack_composer.errors import Issue
from stack_composer.render.spack_specs import is_renderable_external_name_version
from stack_composer.yaml_io import load_yaml


def validate_rendered_workspace(workspace: Path) -> list[Issue]:
    issues: list[Issue] = []
    for path in sorted(workspace.rglob("*.yaml")):
        data = load_unique_yaml(path, issues)
        if data is None:
            continue
        if path.name == "packages.yaml":
            issues.extend(validate_packages_yaml(path, data))
        if path.name == "spack.yaml" and path.relative_to(workspace).parts[0] == "environments":
            spack = data.get("spack") if isinstance(data, dict) else None
            specs = spack.get("specs") if isinstance(spack, dict) else None
            if not isinstance(specs, list) or not specs:
                issues.append(Issue(
                    "error", "rendered-specs-empty", str(path),
                    "rendered environment must contain a nonempty spack.specs list",
                ))
    return issues


def load_unique_yaml(path: Path, issues: list[Issue]) -> Any:
    try:
        return load_yaml(path, unique_keys=True)
    except ValueError as exc:
        issues.append(
            Issue(
                "error",
                "rendered-yaml-invalid",
                str(path),
                f"rendered YAML is invalid: {exc}",
            )
        )
        return None


def validate_packages_yaml(path: Path, data: Any) -> list[Issue]:
    issues: list[Issue] = []
    packages = (data or {}).get("packages") if isinstance(data, dict) else None
    if not isinstance(packages, dict):
        return issues
    for package_name, package_data in packages.items():
        if not isinstance(package_data, dict):
            continue
        externals = package_data.get("externals") or []
        for index, external in enumerate(externals):
            if not isinstance(external, dict) or "spec" not in external:
                continue
            spec = external["spec"]
            if not is_safe_external_spec(spec):
                issues.append(
                    Issue(
                        "error",
                        "rendered-external-spec-invalid",
                        f"{path}:packages.{package_name}.externals[{index}].spec",
                        f"rendered external spec {spec!r} is not safe for Spack",
                    )
                )
    return issues


def is_safe_external_spec(spec: object) -> bool:
    if not isinstance(spec, str) or not spec:
        return False
    head = spec.split()[0]
    if "@" not in head:
        return True
    name, version = head.split("@", 1)
    return is_renderable_external_name_version(name, version)
