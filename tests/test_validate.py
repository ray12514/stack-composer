from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import yaml

from stack_composer.validate.checks import validate_inputs
from stack_composer.yaml_io import load_yaml
from tests.conftest import fixture_path


def test_validate_inputs_accepts_reference_fixtures() -> None:
    for profile_name in ("example-cray", "example-linux"):
        issues, context = validate_inputs(
            profile_path=fixture_path("profiles", profile_name, "profile.yaml"),
            stack_path=fixture_path("stacks", "science-stack", "stack.yaml"),
            templates_root=fixture_path("template-sets"),
            package_sets_dir=fixture_path("package-sets"),
            package_repos_dir=fixture_path("package-repos"),
        )
        issue_data = [(issue.code, issue.path, issue.message) for issue in issues]
        assert issue_data == []
        assert context["profile"]["system"]["name"] == profile_name
        assert context["stack"]["name"] == "science-stack"


def test_validate_inputs_rejects_unknown_build_class(tmp_path) -> None:
    stack_path = fixture_path("stacks", "science-stack", "stack.yaml")
    data = stack_path.read_text(encoding="utf-8").replace("class: gpu", "class: bad-gpu")
    bad_stack = tmp_path / "bad-stack.yaml"
    bad_stack.write_text(data, encoding="utf-8")
    issues, _ = validate_inputs(
        profile_path=fixture_path("profiles", "example-cray", "profile.yaml"),
        stack_path=bad_stack,
        templates_root=fixture_path("template-sets"),
        package_sets_dir=fixture_path("package-sets"),
        package_repos_dir=fixture_path("package-repos"),
    )
    assert any(issue.code == "unknown-build-class" for issue in issues)


def test_validate_inputs_rejects_missing_package_repo_yaml(tmp_path: Path) -> None:
    repo_dir = tmp_path / "package-repos" / "science"
    repo_dir.mkdir(parents=True)

    issues, _ = validate_inputs(
        profile_path=fixture_path("profiles", "example-cray", "profile.yaml"),
        stack_path=fixture_path("stacks", "science-stack", "stack.yaml"),
        templates_root=fixture_path("template-sets"),
        package_sets_dir=fixture_path("package-sets"),
        package_repos_dir=tmp_path / "package-repos",
    )
    assert any(issue.code == "missing-file" and "repo.yaml" in issue.path for issue in issues)


def test_validate_inputs_rejects_package_repo_namespace_mismatch(tmp_path: Path) -> None:
    repo_dir = tmp_path / "package-repos" / "science"
    repo_dir.mkdir(parents=True)
    (repo_dir / "repo.yaml").write_text("repo:\n  namespace: other\n", encoding="utf-8")

    issues, _ = validate_inputs(
        profile_path=fixture_path("profiles", "example-cray", "profile.yaml"),
        stack_path=fixture_path("stacks", "science-stack", "stack.yaml"),
        templates_root=fixture_path("template-sets"),
        package_sets_dir=fixture_path("package-sets"),
        package_repos_dir=tmp_path / "package-repos",
    )
    assert any(issue.code == "package-repo-namespace-mismatch" for issue in issues)


def test_validate_inputs_rejects_duplicate_package_repo_namespace(tmp_path: Path) -> None:
    stack = deepcopy(load_yaml(fixture_path("stacks", "science-stack", "stack.yaml")))
    stack["package_repositories"] = [
        {
            "name": "science",
            "namespace": "science",
            "path": "package-repos/science",
            "priority": "before_builtin",
        },
        {
            "name": "science-duplicate",
            "namespace": "science",
            "path": "package-repos/science-duplicate",
            "priority": "before_builtin",
        },
    ]
    stack_path = tmp_path / "stack.yaml"
    stack_path.write_text(yaml.safe_dump(stack, sort_keys=False), encoding="utf-8")
    for name in ("science", "science-duplicate"):
        repo_dir = tmp_path / "package-repos" / name
        repo_dir.mkdir(parents=True)
        (repo_dir / "repo.yaml").write_text("repo:\n  namespace: science\n", encoding="utf-8")

    issues, _ = validate_inputs(
        profile_path=fixture_path("profiles", "example-cray", "profile.yaml"),
        stack_path=stack_path,
        templates_root=fixture_path("template-sets"),
        package_sets_dir=fixture_path("package-sets"),
        package_repos_dir=tmp_path / "package-repos",
    )
    assert any(issue.code == "duplicate-package-repo-namespace" for issue in issues)


def test_validate_inputs_rejects_inline_spec_kind_mismatch(tmp_path: Path) -> None:
    stack = deepcopy(load_yaml(fixture_path("stacks", "science-stack", "stack.yaml")))
    for build in stack["builds"]:
        if build["name"] == "serial":
            build.pop("package_set")
            build["specs"] = {"gpu": ["hdf5@1.14.5"]}
            break
    stack_path = tmp_path / "stack.yaml"
    stack_path.write_text(yaml.safe_dump(stack, sort_keys=False), encoding="utf-8")

    issues, _ = validate_inputs(
        profile_path=fixture_path("profiles", "example-cray", "profile.yaml"),
        stack_path=stack_path,
        templates_root=fixture_path("template-sets"),
        package_sets_dir=fixture_path("package-sets"),
        package_repos_dir=fixture_path("package-repos"),
    )
    assert any(issue.code == "inline-spec-kind-mismatch" for issue in issues)


def test_validate_inputs_rejects_unresolved_narrowing_compiler(tmp_path: Path) -> None:
    stack = stack_with_narrowing("mpi", "compilers", ["not-a-compiler"])
    issues = validate_stack_copy(tmp_path, stack)
    assert any(issue.code == "unresolved-narrowing-compiler" for issue in issues)


def test_validate_inputs_rejects_unresolved_narrowing_mpi(tmp_path: Path) -> None:
    stack = stack_with_narrowing("mpi", "mpi", ["not-mpi"])
    issues = validate_stack_copy(tmp_path, stack)
    assert any(issue.code == "unresolved-narrowing-mpi" for issue in issues)


def test_validate_inputs_rejects_unresolved_narrowing_gpu_selector(tmp_path: Path) -> None:
    stack = stack_with_narrowing("gpu", "gpu_selectors", ["a100"])
    issues = validate_stack_copy(tmp_path, stack)
    assert any(issue.code == "unresolved-narrowing-gpu-selector" for issue in issues)


def test_validate_inputs_rejects_required_build_that_cannot_resolve(tmp_path: Path) -> None:
    stack = deepcopy(load_yaml(fixture_path("stacks", "science-stack", "stack.yaml")))
    for build in stack["builds"]:
        if build["name"] == "gpu":
            build["required"] = True
            break
    stack_path = tmp_path / "stack.yaml"
    stack_path.write_text(yaml.safe_dump(stack, sort_keys=False), encoding="utf-8")

    issues, _ = validate_inputs(
        profile_path=fixture_path("profiles", "example-linux", "profile.yaml"),
        stack_path=stack_path,
        templates_root=fixture_path("template-sets"),
        package_sets_dir=fixture_path("package-sets"),
        package_repos_dir=fixture_path("package-repos"),
    )
    assert any(
        issue.code == "nodes_unmatched" and issue.path == "stack.builds.gpu" for issue in issues
    )


def stack_with_narrowing(build_name: str, axis: str, values: list[str]) -> dict:
    stack = deepcopy(load_yaml(fixture_path("stacks", "science-stack", "stack.yaml")))
    stack["per_system"]["example-cray"]["builds"][build_name][axis] = values
    return stack


def validate_stack_copy(tmp_path: Path, stack: dict):
    stack_path = tmp_path / "stack.yaml"
    stack_path.write_text(yaml.safe_dump(stack, sort_keys=False), encoding="utf-8")
    issues, _ = validate_inputs(
        profile_path=fixture_path("profiles", "example-cray", "profile.yaml"),
        stack_path=stack_path,
        templates_root=fixture_path("template-sets"),
        package_sets_dir=fixture_path("package-sets"),
        package_repos_dir=fixture_path("package-repos"),
    )
    return issues
