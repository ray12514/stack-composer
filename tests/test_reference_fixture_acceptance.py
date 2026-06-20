from __future__ import annotations

import io
from pathlib import Path

import yaml

from stack_composer.commands import validate_template_set
from stack_composer.schema_registry import validate_schema
from stack_composer.yaml_io import load_yaml
from tests.conftest import fixture_path

REFERENCE_STACKS = ("science-stack",)
REFERENCE_PROFILES = ("example-cray", "example-linux")

EXPECTED_LANES = {
    "example-cray": [
        "cce-core",
        "cce-mpi-craympich",
        "cce-serial",
        "gcc-core",
        "gcc-gpu-craympich-gfx90a",
        "gcc-mpi-craympich",
        "gcc-serial",
    ],
    "example-linux": [
        "aocc-core",
        "aocc-mpi-openmpi",
        "aocc-serial",
        "gcc-core",
        "gcc-mpi-openmpi",
        "gcc-serial",
    ],
}


def test_reference_fixture_catalog_matches_phase_4_matrix() -> None:
    assert fixture_dir_names("stacks") == REFERENCE_STACKS
    assert fixture_dir_names("profiles") == REFERENCE_PROFILES


def test_reference_fixture_acceptance_renders_every_stack_profile_pair(
    tmp_path: Path,
) -> None:
    for stack_name in REFERENCE_STACKS:
        output = tmp_path / stack_name
        err = io.StringIO()
        validate_template_set.run(
            templates=str(fixture_path("template-sets", "v6")),
            profiles=tuple(
                str(fixture_path("profiles", profile_name, "profile.yaml"))
                for profile_name in REFERENCE_PROFILES
            ),
            smoke_stack=str(fixture_path("stacks", stack_name, "stack.yaml")),
            package_sets_dir=str(fixture_path("package-sets")),
            package_repos_dir=str(fixture_path("package-repos")),
            output=str(output),
            concretize=False,
            stream=err,
        )

        summary = yaml.safe_load((output / "summary.yaml").read_text(encoding="utf-8"))
        assert err.getvalue() == "validate-template-set: 2/2 profiles ok\n"
        results = {entry["profile"]: entry for entry in summary["results"]}
        assert tuple(results) == REFERENCE_PROFILES

        for profile_name in REFERENCE_PROFILES:
            result = results[profile_name]
            assert result["render"] == "ok"
            workspace = Path(result["workspace"])
            assert workspace.exists()
            assert_reference_workspace(workspace, stack_name, profile_name)


def assert_reference_workspace(workspace: Path, stack_name: str, profile_name: str) -> None:
    manifest_path = workspace / "release-manifest.yaml"
    manifest = load_yaml(manifest_path)
    issues = validate_schema("release-manifest", manifest, manifest_path.as_posix())

    assert [(issue.code, issue.path, issue.message) for issue in issues] == []
    assert manifest["phase"] == "draft"
    assert manifest["stack"]["name"] == stack_name
    assert manifest["profile"]["system_name"] == profile_name
    assert sorted(lane["name"] for lane in manifest["lanes"]) == EXPECTED_LANES[profile_name]

    if profile_name == "example-linux":
        assert manifest["skipped_builds"] == [
            {
                "build": "gpu",
                "reason_code": "nodes_unmatched",
                "reason": "no profile node type matches selector 'gpu'",
            }
        ]
    else:
        assert manifest["skipped_builds"] == []

    for lane in manifest["lanes"]:
        assert (workspace / lane["env_path"] / "spack.yaml").is_file()


def fixture_dir_names(section: str) -> tuple[str, ...]:
    return tuple(path.name for path in sorted(fixture_path(section).iterdir()) if path.is_dir())
