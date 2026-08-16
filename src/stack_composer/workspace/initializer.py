from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

import yaml
from jinja2 import Environment, FileSystemLoader, StrictUndefined, TemplateError

from stack_composer.errors import Issue, ValidationFailed
from stack_composer.yaml_io import load_yaml, write_yaml


def initialize_workspace(
    *,
    blueprint_dir: Path,
    catalog_dir: Path,
    values_path: Path,
    output_dir: Path,
    overwrite: bool = False,
) -> Path:
    """Render an authored blueprint against a static platform catalog."""
    blueprint_dir = blueprint_dir.resolve()
    catalog_dir = catalog_dir.resolve()
    values_path = values_path.resolve()
    output_dir = output_dir.resolve()
    pending = output_dir.with_name(f"{output_dir.name}.initializing")

    if output_dir.exists() and not overwrite:
        raise _failure("workspace-exists", output_dir, "workspace already exists")
    if pending.exists():
        raise _failure("stale-initializing-path", pending, "stale initialization path exists")

    blueprint = _load_mapping(blueprint_dir / "blueprint.yaml", "blueprint")
    catalog_manifest = _load_mapping(catalog_dir / "manifest.yaml", "catalog")
    values = _load_mapping(values_path, "values")
    issues = _validate_inputs(
        blueprint=blueprint,
        blueprint_dir=blueprint_dir,
        catalog_manifest=catalog_manifest,
        catalog_dir=catalog_dir,
        values=values,
    )
    if issues:
        raise ValidationFailed(issues)

    template_root = _child_path(
        blueprint_dir,
        str(blueprint["template_root"]),
        "blueprint.template_root",
    )
    data = _load_data_files(blueprint_dir, blueprint.get("data_files") or {})
    context = {
        "blueprint": blueprint,
        "catalog": {"root": str(catalog_dir), "manifest": catalog_manifest},
        "workspace": {"root": str(output_dir)},
        "values": values,
        "data": data,
    }

    try:
        pending.mkdir(parents=True)
        snapshot_catalog = bool(blueprint.get("snapshot_catalog", False))
        if snapshot_catalog:
            shutil.copytree(catalog_dir, pending / "catalog")
        _render_tree(template_root, pending, context)
        manifest = {
            "schema_version": 1,
            "kind": "initialized-workspace",
            "blueprint": blueprint["name"],
            "catalog": {
                "source_root": str(catalog_dir),
                "workspace_root": "catalog" if snapshot_catalog else None,
                "system": (catalog_manifest.get("system") or {}).get("name"),
                "release": catalog_manifest.get("release"),
            },
            "values": str(values_path),
        }
        write_yaml(pending / "workspace-manifest.yaml", manifest)
        _validate_generated_yaml(pending)
        if output_dir.exists():
            shutil.rmtree(output_dir)
        pending.replace(output_dir)
    except ValidationFailed:
        if pending.exists():
            shutil.rmtree(pending)
        raise
    except (OSError, TemplateError, ValueError, yaml.YAMLError) as exc:
        if pending.exists():
            shutil.rmtree(pending)
        raise _failure("template-render", blueprint_dir, str(exc)) from exc
    return output_dir


def _validate_inputs(
    *,
    blueprint: dict[str, Any],
    blueprint_dir: Path,
    catalog_manifest: dict[str, Any],
    catalog_dir: Path,
    values: dict[str, Any],
) -> list[Issue]:
    issues: list[Issue] = []
    for key in ("schema_version", "name", "template_root"):
        if not blueprint.get(key):
            issues.append(Issue("error", "blueprint-field", f"blueprint.{key}", "required"))
    if catalog_manifest.get("kind") != "static-platform-catalog":
        issues.append(
            Issue(
                "error",
                "catalog-kind",
                str(catalog_dir / "manifest.yaml"),
                "expected a static-platform-catalog manifest",
            )
        )
    if not (catalog_dir / "scopes").is_dir():
        issues.append(
            Issue("error", "catalog-scopes", str(catalog_dir / "scopes"), "directory missing")
        )
    snapshot_catalog = blueprint.get("snapshot_catalog", False)
    if not isinstance(snapshot_catalog, bool):
        issues.append(
            Issue(
                "error",
                "snapshot-catalog",
                "blueprint.snapshot_catalog",
                "must be true or false",
            )
        )
    template_root = blueprint.get("template_root")
    if template_root:
        try:
            path = _child_path(blueprint_dir, str(template_root), "blueprint.template_root")
            if not path.is_dir():
                issues.append(Issue("error", "template-root", str(path), "directory missing"))
        except ValidationFailed as exc:
            issues.extend(exc.issues)
    required_values = blueprint.get("required_values") or []
    if not isinstance(required_values, list):
        issues.append(
            Issue("error", "required-values", "blueprint.required_values", "must be a list")
        )
    else:
        for dotted_path in required_values:
            if not _has_value(values, str(dotted_path)):
                issues.append(
                    Issue("error", "missing-value", f"values.{dotted_path}", "required")
                )
    allowed_values = blueprint.get("allowed_values") or {}
    if not isinstance(allowed_values, dict):
        issues.append(
            Issue("error", "allowed-values", "blueprint.allowed_values", "must be a mapping")
        )
    else:
        for dotted_path, choices in allowed_values.items():
            if not isinstance(choices, list) or not choices:
                issues.append(
                    Issue(
                        "error",
                        "allowed-values",
                        f"blueprint.allowed_values.{dotted_path}",
                        "must be a non-empty list",
                    )
                )
                continue
            value = _get_value(values, str(dotted_path))
            if value is not None and value not in choices:
                issues.append(
                    Issue(
                        "error",
                        "value-not-allowed",
                        f"values.{dotted_path}",
                        f"expected one of {choices!r}; got {value!r}",
                    )
                )
    catalog_scope_values = blueprint.get("catalog_scope_values") or []
    if not isinstance(catalog_scope_values, list):
        issues.append(
            Issue(
                "error",
                "catalog-scope-values",
                "blueprint.catalog_scope_values",
                "must be a list",
            )
        )
    else:
        for dotted_path in catalog_scope_values:
            relative = _get_value(values, str(dotted_path))
            if relative is None:
                continue
            try:
                scope = _child_path(catalog_dir, str(relative), f"values.{dotted_path}")
                if not scope.is_dir():
                    issues.append(
                        Issue(
                            "error",
                            "catalog-scope",
                            f"values.{dotted_path}",
                            "directory missing",
                        )
                    )
            except ValidationFailed:
                issues.append(
                    Issue(
                        "error",
                        "catalog-scope",
                        f"values.{dotted_path}",
                        f"path escapes catalog root: {relative}",
                    )
                )
    return issues


def _load_mapping(path: Path, label: str) -> dict[str, Any]:
    try:
        data = load_yaml(path)
    except ValueError as exc:
        raise _failure(f"{label}-read", path, str(exc)) from exc
    if not isinstance(data, dict):
        raise _failure(f"{label}-shape", path, "expected a YAML mapping")
    return data


def _load_data_files(blueprint_dir: Path, entries: Any) -> dict[str, Any]:
    if not isinstance(entries, dict):
        raise _failure("data-files", blueprint_dir / "blueprint.yaml", "must be a mapping")
    loaded: dict[str, Any] = {}
    for name, relative_path in entries.items():
        path = _child_path(blueprint_dir, str(relative_path), f"blueprint.data_files.{name}")
        loaded[str(name)] = _load_mapping(path, f"data-{name}")
    return loaded


def _render_tree(template_root: Path, destination: Path, context: dict[str, Any]) -> None:
    environment = Environment(
        loader=FileSystemLoader(str(template_root)),
        undefined=StrictUndefined,
        autoescape=False,
        keep_trailing_newline=True,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    environment.filters["yaml_flow"] = _yaml_flow
    environment.filters["yaml_scalar"] = _yaml_scalar
    for source in sorted(template_root.rglob("*")):
        if source.is_dir():
            continue
        relative = source.relative_to(template_root)
        if any(part.startswith("_") for part in relative.parts):
            continue
        rendered_relative = _render_relative_path(environment, relative, context)
        target = destination / rendered_relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if source.suffix == ".j2":
            template = environment.get_template(relative.as_posix())
            target.write_text(template.render(**context), encoding="utf-8")
        else:
            shutil.copyfile(source, target)
        shutil.copymode(source, target)


def _render_relative_path(
    environment: Environment,
    relative: Path,
    context: dict[str, Any],
) -> Path:
    rendered = environment.from_string(relative.as_posix()).render(**context)
    if rendered.endswith(".j2"):
        rendered = rendered[:-3]
    path = Path(rendered)
    if path.is_absolute() or ".." in path.parts or not rendered:
        raise ValueError(f"rendered template path is invalid: {rendered!r}")
    return path


def _validate_generated_yaml(root: Path) -> None:
    issues: list[Issue] = []
    for path in sorted((*root.rglob("*.yaml"), *root.rglob("*.yml"))):
        try:
            load_yaml(path)
        except ValueError as exc:
            issues.append(Issue("error", "generated-yaml", str(path), str(exc)))
    if issues:
        raise ValidationFailed(issues)


def _child_path(root: Path, relative: str, issue_path: str) -> Path:
    candidate = (root / relative).resolve()
    if candidate != root and root not in candidate.parents:
        raise _failure("path-escape", issue_path, f"path escapes blueprint root: {relative}")
    return candidate


def _has_value(values: dict[str, Any], dotted_path: str) -> bool:
    return _get_value(values, dotted_path) is not None


def _get_value(values: dict[str, Any], dotted_path: str) -> Any:
    current: Any = values
    for part in dotted_path.split("."):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def _yaml_flow(value: Any) -> str:
    return _strip_document_end(
        yaml.safe_dump(value, default_flow_style=True, sort_keys=False, width=4096).strip()
    )


def _yaml_scalar(value: Any) -> str:
    return _strip_document_end(
        yaml.safe_dump(value, default_flow_style=True, sort_keys=False, width=4096).strip()
    )


def _strip_document_end(rendered: str) -> str:
    lines = rendered.splitlines()
    if lines and lines[-1] == "...":
        lines.pop()
    return "\n".join(lines)


def _failure(code: str, path: Path | str, message: str) -> ValidationFailed:
    return ValidationFailed([Issue("error", code, str(path), message)])
