from __future__ import annotations

from pathlib import Path

import yaml
from click.testing import CliRunner

from stack_composer.cli import cli


def write_yaml(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")


def make_inputs(tmp_path: Path) -> tuple[Path, Path, Path]:
    catalog = tmp_path / "catalog"
    write_yaml(
        catalog / "manifest.yaml",
        {
            "schema_version": 1,
            "kind": "static-platform-catalog",
            "system": {"name": "example-linux"},
            "release": "alpha-001",
            "scopes": [],
        },
    )
    (catalog / "scopes").mkdir()

    blueprint = tmp_path / "blueprint"
    write_yaml(
        blueprint / "blueprint.yaml",
        {
            "schema_version": 1,
            "name": "example-pilot",
            "template_root": "templates",
            "required_values": ["system.name", "paths.install_tree"],
            "allowed_values": {"mode": ["external", "build"]},
            "catalog_scope_values": ["catalog_scopes.common"],
            "data_files": {"roster": "roster.yaml"},
        },
    )
    write_yaml(blueprint / "roster.yaml", {"specs": ["cmake@4.3.3"]})
    templates = blueprint / "templates"
    templates.mkdir()
    (templates / "README.md.j2").write_text(
        "# {{ blueprint.name }} for {{ values.system.name }}\n",
        encoding="utf-8",
    )
    (templates / "spack.yaml.j2").write_text(
        "spack:\n"
        "  include::\n"
        "  - {{ catalog.root }}/scopes/common\n"
        "  - {{ workspace.root }}/configs/common\n"
        "  specs:\n"
        "{% for spec in data.roster.specs %}"
        "  - {{ spec }}\n"
        "{% endfor %}",
        encoding="utf-8",
    )
    (templates / "notes.txt").write_text("plain file\n", encoding="utf-8")
    partials = templates / "_partials"
    partials.mkdir()
    (partials / "header.txt.j2").write_text("private partial\n", encoding="utf-8")
    system_templates = templates / "systems" / "{{ values.system.name }}"
    system_templates.mkdir(parents=True)
    (system_templates / "{{ values.system.name }}.yaml.j2").write_text(
        "system: {{ values.system.name | yaml_scalar }}\n",
        encoding="utf-8",
    )

    values = tmp_path / "values.yaml"
    write_yaml(
        values,
        {
            "schema_version": 1,
            "system": {"name": "example-linux"},
            "paths": {"install_tree": "/shared/cse/spack/opt"},
            "mode": "external",
            "catalog_scopes": {"common": "scopes/common"},
        },
    )
    (catalog / "scopes" / "common").mkdir()
    return blueprint, catalog, values


def invoke_init(
    blueprint: Path,
    catalog: Path,
    values: Path,
    output: Path,
    *extra: str,
):
    return CliRunner().invoke(
        cli,
        [
            "init-workspace",
            "--blueprint",
            str(blueprint),
            "--catalog",
            str(catalog),
            "--values",
            str(values),
            "--output",
            str(output),
            *extra,
        ],
    )


def test_init_workspace_renders_blueprint_and_valid_yaml(tmp_path: Path) -> None:
    blueprint, catalog, values = make_inputs(tmp_path)
    output = tmp_path / "workspace"

    result = invoke_init(blueprint, catalog, values, output)

    assert result.exit_code == 0, result.output
    assert output.exists()
    assert not output.with_name("workspace.initializing").exists()
    assert (output / "README.md").read_text(encoding="utf-8") == (
        "# example-pilot for example-linux\n"
    )
    assert (output / "notes.txt").read_text(encoding="utf-8") == "plain file\n"
    assert not (output / "_partials").exists()
    assert yaml.safe_load(
        (output / "systems" / "example-linux" / "example-linux.yaml").read_text(
            encoding="utf-8"
        )
    ) == {"system": "example-linux"}
    rendered = yaml.safe_load((output / "spack.yaml").read_text(encoding="utf-8"))
    assert rendered["spack"]["include:"] == [
        str(catalog / "scopes" / "common"),
        str(output / "configs" / "common"),
    ]
    assert rendered["spack"]["specs"] == ["cmake@4.3.3"]
    manifest = yaml.safe_load(
        (output / "workspace-manifest.yaml").read_text(encoding="utf-8")
    )
    assert manifest["blueprint"] == "example-pilot"
    assert manifest["catalog"]["system"] == "example-linux"
    assert manifest["catalog"]["release"] == "alpha-001"
    assert manifest["catalog"]["source_root"] == str(catalog)
    assert manifest["catalog"]["workspace_root"] is None


def test_init_workspace_can_snapshot_catalog_into_handoff(tmp_path: Path) -> None:
    blueprint, catalog, values = make_inputs(tmp_path)
    output = tmp_path / "workspace"
    blueprint_data = yaml.safe_load(
        (blueprint / "blueprint.yaml").read_text(encoding="utf-8")
    )
    blueprint_data["snapshot_catalog"] = True
    write_yaml(blueprint / "blueprint.yaml", blueprint_data)

    result = invoke_init(blueprint, catalog, values, output)

    assert result.exit_code == 0, result.output
    assert (output / "catalog" / "manifest.yaml").is_file()
    assert (output / "catalog" / "scopes" / "common").is_dir()
    manifest = yaml.safe_load(
        (output / "workspace-manifest.yaml").read_text(encoding="utf-8")
    )
    assert manifest["catalog"]["source_root"] == str(catalog)
    assert manifest["catalog"]["workspace_root"] == "catalog"


def test_init_workspace_rejects_existing_output_without_overwrite(tmp_path: Path) -> None:
    blueprint, catalog, values = make_inputs(tmp_path)
    output = tmp_path / "workspace"
    output.mkdir()

    result = invoke_init(blueprint, catalog, values, output)

    assert result.exit_code != 0
    assert "workspace-exists" in result.output


def test_init_workspace_cleans_pending_output_after_template_failure(tmp_path: Path) -> None:
    blueprint, catalog, values = make_inputs(tmp_path)
    output = tmp_path / "workspace"
    (blueprint / "templates" / "broken.txt.j2").write_text(
        "{{ values.missing.value }}\n", encoding="utf-8"
    )

    result = invoke_init(blueprint, catalog, values, output)

    assert result.exit_code != 0
    assert "template-render" in result.output
    assert not output.exists()
    assert not output.with_name("workspace.initializing").exists()


def test_init_workspace_rejects_unsupported_value(tmp_path: Path) -> None:
    blueprint, catalog, values = make_inputs(tmp_path)
    output = tmp_path / "workspace"
    write_yaml(
        values,
        {
            "schema_version": 1,
            "system": {"name": "example-linux"},
            "paths": {"install_tree": "/shared/cse/spack/opt"},
            "mode": "automatic",
            "catalog_scopes": {"common": "scopes/common"},
        },
    )

    result = invoke_init(blueprint, catalog, values, output)

    assert result.exit_code != 0
    assert "value-not-allowed" in result.output


def test_init_workspace_rejects_missing_or_escaping_catalog_scope(tmp_path: Path) -> None:
    blueprint, catalog, values = make_inputs(tmp_path)
    output = tmp_path / "workspace"
    write_yaml(
        values,
        {
            "schema_version": 1,
            "system": {"name": "example-linux"},
            "paths": {"install_tree": "/shared/cse/spack/opt"},
            "mode": "external",
            "catalog_scopes": {"common": "../other/scopes"},
        },
    )

    result = invoke_init(blueprint, catalog, values, output)

    assert result.exit_code != 0
    assert "catalog-scope" in result.output
