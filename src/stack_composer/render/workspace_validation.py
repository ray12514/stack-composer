from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from stack_composer.errors import Issue
from stack_composer.render.spack_specs import is_renderable_external_name_version


class UniqueKeyLoader(yaml.SafeLoader):
    pass


def construct_mapping(loader: UniqueKeyLoader, node: yaml.MappingNode, deep: bool = False) -> Any:
    mapping = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in mapping:
            raise yaml.YAMLError(f"duplicate key {key!r}")
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


UniqueKeyLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    construct_mapping,
)


def validate_rendered_workspace(workspace: Path) -> list[Issue]:
    issues: list[Issue] = []
    for path in sorted(workspace.rglob("*.yaml")):
        data = load_unique_yaml(path, issues)
        if data is None:
            continue
        if path.name == "packages.yaml":
            issues.extend(validate_packages_yaml(path, data))
    return issues


def load_unique_yaml(path: Path, issues: list[Issue]) -> Any:
    try:
        return yaml.load(path.read_text(encoding="utf-8"), Loader=UniqueKeyLoader)
    except (OSError, yaml.YAMLError) as exc:
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

