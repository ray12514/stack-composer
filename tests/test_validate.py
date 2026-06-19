from __future__ import annotations

from stack_composer.validate.checks import validate_inputs
from tests.conftest import fixture_path


def test_validate_inputs_accepts_reference_fixtures() -> None:
    issues, context = validate_inputs(
        profile_path=fixture_path("profiles", "example-cray", "profile.yaml"),
        stack_path=fixture_path("stacks", "science-stack", "stack.yaml"),
        templates_root=fixture_path("template-sets"),
        package_sets_dir=fixture_path("package-sets"),
        package_repos_dir=fixture_path("package-repos"),
    )
    issue_data = [(issue.code, issue.path, issue.message) for issue in issues]
    assert issue_data == []
    assert context["profile"]["system"]["name"] == "example-cray"
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
