from __future__ import annotations

import shutil
from copy import deepcopy
from pathlib import Path

import pytest
from jinja2 import UndefinedError

from stack_composer.errors import ValidationFailed
from stack_composer.model.profile import load_profile
from stack_composer.model.stack import load_defaults, load_stack, merge_defaults
from stack_composer.render.engine import render_workspace
from stack_composer.render.plan import plan_lanes
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
    assert {lane["kind"] for lane in manifest["lanes"]} == {"cpu", "mpi", "gpu"}


def test_render_workspace_handles_generic_linux_without_gpu(tmp_path: Path) -> None:
    workspace = render_fixture(tmp_path / "out-a", profile_name="example-linux")

    manifest = load_yaml(workspace / "release-manifest.yaml")
    assert validate_schema("release-manifest", manifest, "release-manifest.yaml") == []
    assert manifest["profile"]["system_name"] == "example-linux"
    assert {lane["kind"] for lane in manifest["lanes"]} == {"cpu", "mpi"}
    assert manifest["skipped_builds"] == [
        {
            "build": "gpu",
            "reason_code": "nodes_unmatched",
            "reason": "profile has no runtime GPU node type",
        }
    ]


def test_render_workspace_is_byte_deterministic(tmp_path: Path) -> None:
    first = render_fixture(tmp_path / "out-a")
    second = render_fixture(tmp_path / "out-b")

    assert tree_bytes(first) == tree_bytes(second)


def test_render_workspace_refuses_existing_workspace(tmp_path: Path) -> None:
    render_fixture(tmp_path / "out-a")

    with pytest.raises(ValidationFailed) as exc_info:
        render_fixture(tmp_path / "out-a")

    assert any(issue.code == "workspace-exists" for issue in exc_info.value.issues)


def test_render_workspace_refuses_stale_pending_path(tmp_path: Path) -> None:
    pending = tmp_path / "out-a" / "example-cray" / "science-stack" / "2026.06.rendering"
    pending.mkdir(parents=True)

    with pytest.raises(ValidationFailed) as exc_info:
        render_fixture(tmp_path / "out-a")

    assert pending.exists()
    assert any(issue.code == "stale-render-path" for issue in exc_info.value.issues)


def test_render_workspace_removes_pending_on_template_failure(tmp_path: Path) -> None:
    templates_root = tmp_path / "template-sets"
    shutil.copytree(fixture_path("template-sets"), templates_root)
    broken_template = templates_root / "v6" / "environments" / "cpu" / "spack.yaml.j2"
    broken_template.write_text("{{ missing_context_key }}\n", encoding="utf-8")

    output_root = tmp_path / "out-a"
    with pytest.raises(UndefinedError):
        render_fixture(output_root, templates_root=templates_root)

    workspace = output_root / "example-cray" / "science-stack" / "2026.06"
    assert not workspace.exists()
    assert not workspace.with_name(workspace.name + ".rendering").exists()


def test_plan_lanes_reports_per_system_empty_when_narrowing_drops_all_lanes() -> None:
    profile, _ = load_profile(fixture_path("profiles", "example-cray", "profile.yaml"))
    raw_stack, _ = load_stack(fixture_path("stacks", "science-stack", "stack.yaml"))
    template_set = fixture_path("template-sets", "v6")
    defaults, _ = load_defaults(template_set / "defaults.yaml")
    stack = merge_defaults(defaults, deepcopy(raw_stack))
    for build in stack["builds"]:
        if build["name"] == "mpi":
            build["required"] = True
            break
    stack["per_system"]["example-cray"]["builds"]["mpi"] = {"compilers": ["does-not-exist"]}

    lanes, _skipped, _narrowing, issues = plan_lanes(profile, stack)
    assert all(lane["source_build"] != "mpi" for lane in lanes)
    mpi_issues = [i for i in issues if i.path == "stack.builds.mpi"]
    assert len(mpi_issues) == 1
    assert mpi_issues[0].code == "per_system_empty"
    assert "narrowing dropped every lane" in mpi_issues[0].message


def render_fixture(
    output_root: Path, templates_root: Path | None = None, profile_name: str = "example-cray"
) -> Path:
    return render_workspace(
        profile_path=fixture_path("profiles", profile_name, "profile.yaml"),
        stack_path=fixture_path("stacks", "science-stack", "stack.yaml"),
        templates_root=templates_root or fixture_path("template-sets"),
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
