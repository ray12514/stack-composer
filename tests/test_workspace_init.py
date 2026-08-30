from __future__ import annotations

import os
import stat
import sys
from pathlib import Path

import yaml
from click.testing import CliRunner

from stack_composer.cli import cli
from stack_composer.publish.static_catalog import publish_static_catalog


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
            "scope_root": "scopes",
            "scopes": [],
        },
    )
    (catalog / "scopes").mkdir()
    write_yaml(
        catalog / "reports" / "static-plan.yaml",
        {"schema_version": 1, "missing_mpi_dependencies": []},
    )

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
    launcher = templates / "launch.sh.j2"
    launcher.write_text("#!/bin/sh\necho ready\n", encoding="utf-8")
    launcher.chmod(0o755)
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
    assert (output / "launch.sh").stat().st_mode & stat.S_IXUSR
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


def test_init_workspace_records_catalog_publication(tmp_path: Path) -> None:
    blueprint, catalog, values = make_inputs(tmp_path)
    published = publish_static_catalog(
        catalog_dir=catalog,
        output_root=tmp_path / "published",
        published_at="2026-08-29T13:00:00Z",
        reviewed_by="CSE Package Review",
        approved_by="CSE Release Authority",
    )
    output = tmp_path / "workspace"

    result = invoke_init(blueprint, published, values, output)

    assert result.exit_code == 0, result.output
    manifest = yaml.safe_load(
        (output / "workspace-manifest.yaml").read_text(encoding="utf-8")
    )
    assert manifest["catalog"]["publication"] == {
        "published_at": "2026-08-29T13:00:00Z",
        "reviewed_by": "CSE Package Review",
        "approved_by": "CSE Release Authority",
        "checksum_inventory": "SHA256SUMS",
    }


def test_init_workspace_rejects_modified_published_catalog(tmp_path: Path) -> None:
    blueprint, catalog, values = make_inputs(tmp_path)
    reviewed_file = catalog / "scopes" / "common" / "packages.yaml"
    write_yaml(reviewed_file, {"packages": {"zlib-ng": {"buildable": True}}})
    published = publish_static_catalog(
        catalog_dir=catalog,
        output_root=tmp_path / "published",
        published_at="2026-08-29T13:00:00Z",
        reviewed_by="CSE Package Review",
        approved_by="CSE Release Authority",
    )
    write_yaml(published / "scopes" / "common" / "packages.yaml", {})
    output = tmp_path / "workspace"

    result = invoke_init(blueprint, published, values, output)

    assert result.exit_code != 0
    assert "catalog-checksum-mismatch" in result.output
    assert "scopes/common/packages.yaml" in result.output
    assert not output.exists()


def test_init_workspace_rejects_symlinked_published_catalog_content(
    tmp_path: Path,
) -> None:
    blueprint, catalog, values = make_inputs(tmp_path)
    reviewed_file = catalog / "scopes" / "common" / "packages.yaml"
    write_yaml(reviewed_file, {"packages": {"zlib-ng": {"buildable": True}}})
    published = publish_static_catalog(
        catalog_dir=catalog,
        output_root=tmp_path / "published",
        published_at="2026-08-29T13:00:00Z",
        reviewed_by="CSE Package Review",
        approved_by="CSE Release Authority",
    )
    outside = tmp_path / "matching-reviewed-content.yaml"
    outside.write_bytes((published / "scopes" / "common" / "packages.yaml").read_bytes())
    (published / "scopes" / "common" / "packages.yaml").unlink()
    (published / "scopes" / "common" / "packages.yaml").symlink_to(outside)
    output = tmp_path / "workspace"

    result = invoke_init(blueprint, published, values, output)

    assert result.exit_code != 0
    assert "catalog-symlink" in result.output
    assert not output.exists()


def test_init_workspace_applies_declared_group_collaboration_modes(
    tmp_path: Path,
) -> None:
    blueprint, catalog, values = make_inputs(tmp_path)
    output = tmp_path / "workspace"
    blueprint_data = yaml.safe_load(
        (blueprint / "blueprint.yaml").read_text(encoding="utf-8")
    )
    blueprint_data["apply_workspace_permissions"] = True
    blueprint_data["snapshot_catalog"] = True
    write_yaml(blueprint / "blueprint.yaml", blueprint_data)
    values_data = yaml.safe_load(values.read_text(encoding="utf-8"))
    values_data["permissions"] = {
        "group": "cse",
        "read": "group",
        "write": "group",
    }
    write_yaml(values, values_data)

    previous_umask = os.umask(0o077)
    try:
        result = invoke_init(blueprint, catalog, values, output)
    finally:
        os.umask(previous_umask)

    assert result.exit_code == 0, result.output
    assert stat.S_IMODE(output.stat().st_mode) & 0o777 == 0o770
    assert stat.S_IMODE((output / "catalog" / "scopes").stat().st_mode) & 0o777 == 0o770
    if sys.platform.startswith("linux"):
        assert output.stat().st_mode & stat.S_ISGID
        assert (output / "catalog" / "scopes").stat().st_mode & stat.S_ISGID
    assert stat.S_IMODE((output / "README.md").stat().st_mode) == 0o660
    assert stat.S_IMODE((output / "workspace-manifest.yaml").stat().st_mode) == 0o660
    assert stat.S_IMODE((output / "launch.sh").stat().st_mode) == 0o770


def test_init_workspace_applies_consumer_read_only_modes(tmp_path: Path) -> None:
    blueprint, catalog, values = make_inputs(tmp_path)
    output = tmp_path / "workspace"
    blueprint_data = yaml.safe_load(
        (blueprint / "blueprint.yaml").read_text(encoding="utf-8")
    )
    blueprint_data["apply_workspace_permissions"] = True
    write_yaml(blueprint / "blueprint.yaml", blueprint_data)
    values_data = yaml.safe_load(values.read_text(encoding="utf-8"))
    values_data["permissions"] = {
        "group": "cse",
        "read": "world",
        "write": "user",
    }
    write_yaml(values, values_data)

    result = invoke_init(blueprint, catalog, values, output)

    assert result.exit_code == 0, result.output
    assert stat.S_IMODE(output.stat().st_mode) & 0o777 == 0o755
    assert stat.S_IMODE((output / "README.md").stat().st_mode) == 0o644
    assert stat.S_IMODE((output / "launch.sh").stat().st_mode) == 0o755


def test_init_workspace_applies_published_group_collaboration_modes(
    tmp_path: Path,
) -> None:
    blueprint, catalog, values = make_inputs(tmp_path)
    output = tmp_path / "workspace"
    blueprint_data = yaml.safe_load(
        (blueprint / "blueprint.yaml").read_text(encoding="utf-8")
    )
    blueprint_data["apply_workspace_permissions"] = True
    write_yaml(blueprint / "blueprint.yaml", blueprint_data)
    values_data = yaml.safe_load(values.read_text(encoding="utf-8"))
    values_data["permissions"] = {
        "group": "cse",
        "read": "world",
        "write": "group",
    }
    write_yaml(values, values_data)

    previous_umask = os.umask(0o077)
    try:
        result = invoke_init(blueprint, catalog, values, output)
    finally:
        os.umask(previous_umask)

    assert result.exit_code == 0, result.output
    assert stat.S_IMODE(output.stat().st_mode) & 0o777 == 0o775
    if sys.platform.startswith("linux"):
        assert output.stat().st_mode & stat.S_ISGID
    assert stat.S_IMODE((output / "README.md").stat().st_mode) == 0o664
    assert stat.S_IMODE((output / "workspace-manifest.yaml").stat().st_mode) == 0o664
    assert stat.S_IMODE((output / "launch.sh").stat().st_mode) == 0o775


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
