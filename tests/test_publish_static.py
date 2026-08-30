from __future__ import annotations

import grp
import os
import stat
import sys
from pathlib import Path

import yaml
from click.testing import CliRunner

from stack_composer.cli import cli
from stack_composer.render.release import ReleaseVars, SourceRepo
from stack_composer.render.static_catalog import render_static_catalog
from tests.conftest import fixture_path


def test_publish_static_promotes_reviewed_catalog_with_approval_record(
    tmp_path: Path,
) -> None:
    catalog = render_static_catalog(
        profile_path=fixture_path("profiles", "example-linux", "profile.yaml"),
        templates_root=fixture_path("template-sets"),
        template_set_name="v6",
        release_vars=ReleaseVars(
            release_tag="catalog-001",
            output_root=str(tmp_path / "restricted"),
            rendered_at="2026-08-29T12:00:00Z",
            source_repo=SourceRepo("stack-content", "abc123", False),
        ),
    )

    result = CliRunner().invoke(
        cli,
        [
            "publish-static",
            "--catalog",
            str(catalog),
            "--output-root",
            str(tmp_path / "published"),
            "--published-at",
            "2026-08-29T13:00:00Z",
            "--reviewed-by",
            "CSE Package Review",
            "--approved-by",
            "CSE Release Authority",
        ],
    )

    assert result.exit_code == 0, result.output
    published = tmp_path / "published" / "example-linux" / "static" / "catalog-001"
    assert result.output.strip() == str(published)
    assert (published / "manifest.yaml").read_bytes() == (catalog / "manifest.yaml").read_bytes()
    assert (published / "README.md").read_bytes() == (catalog / "README.md").read_bytes()

    record = load_yaml(published / "publication.yaml")
    assert record == {
        "schema_version": 1,
        "kind": "static-catalog-publication",
        "system": "example-linux",
        "release": "catalog-001",
        "published_at": "2026-08-29T13:00:00Z",
        "reviewed_by": "CSE Package Review",
        "approved_by": "CSE Release Authority",
        "checksum_inventory": "SHA256SUMS",
    }


def test_publish_static_records_source_checksums_and_consumer_modes(
    tmp_path: Path,
) -> None:
    catalog = render_static_catalog(
        profile_path=fixture_path("profiles", "example-linux", "profile.yaml"),
        templates_root=fixture_path("template-sets"),
        template_set_name="v6",
        release_vars=ReleaseVars(
            release_tag="catalog-001",
            output_root=str(tmp_path / "restricted"),
            rendered_at="2026-08-29T12:00:00Z",
            source_repo=SourceRepo("stack-content", "abc123", False),
        ),
    )
    note = catalog / "operator-note.txt"
    note.write_text("reviewed\n", encoding="utf-8")
    note.chmod(0o600)

    result = CliRunner().invoke(
        cli,
        [
            "publish-static",
            "--catalog",
            str(catalog),
            "--output-root",
            str(tmp_path / "published"),
            "--published-at",
            "2026-08-29T13:00:00Z",
            "--reviewed-by",
            "CSE Package Review",
            "--approved-by",
            "CSE Release Authority",
        ],
    )

    assert result.exit_code == 0, result.output
    published = tmp_path / "published" / "example-linux" / "static" / "catalog-001"
    inventory = (published / "SHA256SUMS").read_text(encoding="utf-8").splitlines()
    assert (
        "a9f2d25d1f71f8065e2119e538bde8846570fcdad320388236e99d9e225c290d  "
        "operator-note.txt"
    ) in inventory
    assert {line.split("  ", 1)[1] for line in inventory} == {
        path.relative_to(catalog).as_posix()
        for path in catalog.rglob("*")
        if path.is_file()
    }
    assert stat.S_IMODE(published.stat().st_mode) == 0o755
    assert stat.S_IMODE((published / "scopes").stat().st_mode) == 0o755
    assert stat.S_IMODE((published / "operator-note.txt").stat().st_mode) == 0o644
    assert stat.S_IMODE((published / "publication.yaml").stat().st_mode) == 0o644
    assert stat.S_IMODE((published / "SHA256SUMS").stat().st_mode) == 0o644


def test_publish_static_assigns_group_manager_and_consumer_access(
    tmp_path: Path,
) -> None:
    catalog = render_static_catalog(
        profile_path=fixture_path("profiles", "example-linux", "profile.yaml"),
        templates_root=fixture_path("template-sets"),
        template_set_name="v6",
        release_vars=ReleaseVars(
            release_tag="catalog-001",
            output_root=str(tmp_path / "restricted"),
            rendered_at="2026-08-29T12:00:00Z",
            source_repo=SourceRepo("stack-content", "abc123", False),
        ),
    )
    executable = catalog / "verify-catalog"
    executable.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
    executable.chmod(0o700)
    publication_group = grp.getgrgid(os.getgid())

    result = CliRunner().invoke(
        cli,
        [
            "publish-static",
            "--catalog",
            str(catalog),
            "--output-root",
            str(tmp_path / "published"),
            "--published-at",
            "2026-08-29T13:00:00Z",
            "--reviewed-by",
            "CSE Package Review",
            "--approved-by",
            "CSE Release Authority",
            "--group",
            publication_group.gr_name,
        ],
    )

    assert result.exit_code == 0, result.output
    published = tmp_path / "published" / "example-linux" / "static" / "catalog-001"
    assert load_yaml(published / "publication.yaml")["group"] == publication_group.gr_name
    parent_mode = stat.S_IMODE(published.parent.stat().st_mode)
    assert parent_mode & 0o777 == 0o775
    if sys.platform.startswith("linux"):
        assert parent_mode & stat.S_ISGID
    for path in [published, *published.rglob("*")]:
        assert path.stat().st_gid == publication_group.gr_gid
        mode = stat.S_IMODE(path.stat().st_mode)
        if path.is_dir():
            assert mode & 0o777 == 0o775
            if sys.platform.startswith("linux"):
                assert mode & stat.S_ISGID
        elif path.is_file():
            assert mode == (0o775 if path.name == "verify-catalog" else 0o664)
        assert not mode & stat.S_IWOTH


def test_publish_static_can_set_relative_current_pointer(tmp_path: Path) -> None:
    catalog = render_static_catalog(
        profile_path=fixture_path("profiles", "example-linux", "profile.yaml"),
        templates_root=fixture_path("template-sets"),
        template_set_name="v6",
        release_vars=ReleaseVars(
            release_tag="catalog-001",
            output_root=str(tmp_path / "restricted"),
            rendered_at="2026-08-29T12:00:00Z",
            source_repo=SourceRepo("stack-content", "abc123", False),
        ),
    )

    result = CliRunner().invoke(
        cli,
        [
            "publish-static",
            "--catalog",
            str(catalog),
            "--output-root",
            str(tmp_path / "published"),
            "--published-at",
            "2026-08-29T13:00:00Z",
            "--reviewed-by",
            "CSE Package Review",
            "--approved-by",
            "CSE Release Authority",
            "--set-current",
        ],
    )

    assert result.exit_code == 0, result.output
    current = tmp_path / "published" / "example-linux" / "static" / "current"
    assert current.is_symlink()
    assert current.readlink() == Path("catalog-001")


def test_publish_static_rejects_catalog_with_missing_mpi_dependencies(
    tmp_path: Path,
) -> None:
    catalog = render_static_catalog(
        profile_path=fixture_path("profiles", "example-cray", "profile.yaml"),
        templates_root=fixture_path("template-sets"),
        template_set_name="v6",
        release_vars=ReleaseVars(
            release_tag="catalog-001",
            output_root=str(tmp_path / "restricted"),
            rendered_at="2026-08-29T12:00:00Z",
            source_repo=SourceRepo("stack-content", "abc123", False),
        ),
    )

    result = CliRunner().invoke(
        cli,
        [
            "publish-static",
            "--catalog",
            str(catalog),
            "--output-root",
            str(tmp_path / "published"),
            "--published-at",
            "2026-08-29T13:00:00Z",
            "--reviewed-by",
            "CSE Package Review",
            "--approved-by",
            "CSE Release Authority",
        ],
    )

    assert result.exit_code != 0
    assert "catalog-missing-mpi-dependencies" in result.output
    assert "cray-pmi" in result.output
    assert not (tmp_path / "published" / "example-cray").exists()


def test_publish_static_rejects_catalog_with_absolute_scope_root(tmp_path: Path) -> None:
    catalog = render_static_catalog(
        profile_path=fixture_path("profiles", "example-linux", "profile.yaml"),
        templates_root=fixture_path("template-sets"),
        template_set_name="v6",
        release_vars=ReleaseVars(
            release_tag="catalog-001",
            output_root=str(tmp_path / "restricted"),
            rendered_at="2026-08-29T12:00:00Z",
            source_repo=SourceRepo("stack-content", "abc123", False),
        ),
    )
    manifest_path = catalog / "manifest.yaml"
    manifest = load_yaml(manifest_path)
    manifest["scope_root"] = str(catalog / "scopes")
    manifest_path.write_text(yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8")

    result = CliRunner().invoke(
        cli,
        [
            "publish-static",
            "--catalog",
            str(catalog),
            "--output-root",
            str(tmp_path / "published"),
            "--published-at",
            "2026-08-29T13:00:00Z",
            "--reviewed-by",
            "CSE Package Review",
            "--approved-by",
            "CSE Release Authority",
        ],
    )

    assert result.exit_code != 0
    assert "catalog-not-relocatable" in result.output
    assert not (tmp_path / "published" / "example-linux").exists()


def test_publish_static_makes_created_public_parents_traversable(tmp_path: Path) -> None:
    catalog = render_static_catalog(
        profile_path=fixture_path("profiles", "example-linux", "profile.yaml"),
        templates_root=fixture_path("template-sets"),
        template_set_name="v6",
        release_vars=ReleaseVars(
            release_tag="catalog-001",
            output_root=str(tmp_path / "restricted"),
            rendered_at="2026-08-29T12:00:00Z",
            source_repo=SourceRepo("stack-content", "abc123", False),
        ),
    )
    output_root = tmp_path / "published"

    previous_umask = os.umask(0o077)
    try:
        result = CliRunner().invoke(
            cli,
            [
                "publish-static",
                "--catalog",
                str(catalog),
                "--output-root",
                str(output_root),
                "--published-at",
                "2026-08-29T13:00:00Z",
                "--reviewed-by",
                "CSE Package Review",
                "--approved-by",
                "CSE Release Authority",
            ],
        )
    finally:
        os.umask(previous_umask)

    assert result.exit_code == 0, result.output
    assert stat.S_IMODE(output_root.stat().st_mode) == 0o755
    assert stat.S_IMODE((output_root / "example-linux").stat().st_mode) == 0o755
    assert stat.S_IMODE((output_root / "example-linux" / "static").stat().st_mode) == 0o755


def test_publish_static_rejects_symlinked_catalog_content(tmp_path: Path) -> None:
    catalog = render_static_catalog(
        profile_path=fixture_path("profiles", "example-linux", "profile.yaml"),
        templates_root=fixture_path("template-sets"),
        template_set_name="v6",
        release_vars=ReleaseVars(
            release_tag="catalog-001",
            output_root=str(tmp_path / "restricted"),
            rendered_at="2026-08-29T12:00:00Z",
            source_repo=SourceRepo("stack-content", "abc123", False),
        ),
    )
    outside = tmp_path / "outside.txt"
    outside.write_text("not catalog content\n", encoding="utf-8")
    (catalog / "linked.txt").symlink_to(outside)

    result = CliRunner().invoke(
        cli,
        [
            "publish-static",
            "--catalog",
            str(catalog),
            "--output-root",
            str(tmp_path / "published"),
            "--published-at",
            "2026-08-29T13:00:00Z",
            "--reviewed-by",
            "CSE Package Review",
            "--approved-by",
            "CSE Release Authority",
        ],
    )

    assert result.exit_code != 0
    assert "catalog-symlink" in result.output
    assert not (tmp_path / "published" / "example-linux").exists()


def test_publish_static_rejects_reserved_publication_metadata(
    tmp_path: Path,
) -> None:
    catalog = render_static_catalog(
        profile_path=fixture_path("profiles", "example-linux", "profile.yaml"),
        templates_root=fixture_path("template-sets"),
        template_set_name="v6",
        release_vars=ReleaseVars(
            release_tag="catalog-001",
            output_root=str(tmp_path / "restricted"),
            rendered_at="2026-08-29T12:00:00Z",
            source_repo=SourceRepo("stack-content", "abc123", False),
        ),
    )
    (catalog / "publication.yaml").write_text("reviewed: source\n", encoding="utf-8")

    result = CliRunner().invoke(
        cli,
        [
            "publish-static",
            "--catalog",
            str(catalog),
            "--output-root",
            str(tmp_path / "published"),
            "--published-at",
            "2026-08-29T13:00:00Z",
            "--reviewed-by",
            "CSE Package Review",
            "--approved-by",
            "CSE Release Authority",
        ],
    )

    assert result.exit_code != 0
    assert "catalog-publication-metadata" in result.output
    assert not (tmp_path / "published" / "example-linux").exists()


def load_yaml(path: Path) -> dict:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(data, dict), path
    return data
