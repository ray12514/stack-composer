from __future__ import annotations

from pathlib import Path

from stack_composer.render.engine import render_workspace
from stack_composer.render.release import ReleaseVars, SourceRepo
from stack_composer.schema_registry import validate_schema
from stack_composer.yaml_io import load_yaml
from tests.conftest import fixture_path


def test_render_workspace_writes_valid_draft_manifest(tmp_path: Path) -> None:
    workspace = render_fixture(tmp_path / "out-a")

    assert (workspace / "configs" / "common" / "packages.yaml").exists()
    assert (workspace / "configs" / "common" / "repos.yaml").exists()
    assert (workspace / "package-repos" / "science").is_dir()
    manifest = load_yaml(workspace / "release-manifest.yaml")
    assert validate_schema("release-manifest", manifest, "release-manifest.yaml") == []
    assert manifest["phase"] == "draft"
    assert manifest["templates"]["render_tool"]["name"] == "stack-composer render"
    assert {lane["kind"] for lane in manifest["lanes"]} == {"core", "serial", "mpi", "gpu"}


def test_render_workspace_is_byte_deterministic(tmp_path: Path) -> None:
    first = render_fixture(tmp_path / "out-a")
    second = render_fixture(tmp_path / "out-b")

    assert tree_bytes(first) == tree_bytes(second)


def render_fixture(output_root: Path) -> Path:
    return render_workspace(
        profile_path=fixture_path("profiles", "example-cray", "profile.yaml"),
        stack_path=fixture_path("stacks", "science-stack", "stack.yaml"),
        templates_root=fixture_path("template-sets"),
        release_vars=ReleaseVars(
            release_tag="2026.06",
            output_root=output_root.as_posix(),
            rendered_at="2026-06-19T00:00:00Z",
            source_repo=SourceRepo(
                url="git@example:stacks/science-stack",
                commit="0375b16fdeadbeef0123456789abcdef01234567",
                dirty=False,
            ),
        ),
        package_sets_dir=fixture_path("package-sets"),
        package_repos_dir=fixture_path("package-repos"),
    )


def tree_bytes(root: Path) -> list[tuple[str, bytes]]:
    return [
        (path.relative_to(root).as_posix(), path.read_bytes())
        for path in sorted(root.rglob("*"))
        if path.is_file()
    ]
