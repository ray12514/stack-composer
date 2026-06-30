from __future__ import annotations

from pathlib import Path

from stack_composer.render.workspace_validation import validate_rendered_workspace


def test_rendered_workspace_validation_rejects_duplicate_yaml_keys(tmp_path: Path) -> None:
    packages = tmp_path / "configs" / "common" / "packages.yaml"
    packages.parent.mkdir(parents=True)
    packages.write_text(
        """packages:
  libfabric:
    buildable: false
  libfabric:
    buildable: false
""",
        encoding="utf-8",
    )

    issues = validate_rendered_workspace(tmp_path)

    assert [issue.code for issue in issues] == ["rendered-yaml-invalid"]
    assert "duplicate key 'libfabric'" in issues[0].message


def test_rendered_workspace_validation_rejects_bad_external_spec(tmp_path: Path) -> None:
    packages = tmp_path / "configs" / "vendor" / "cray" / "packages.yaml"
    packages.parent.mkdir(parents=True)
    packages.write_text(
        """packages:
  clang:
    buildable: false
    externals:
      - spec: "clang@clang/v2512- languages='c,c++'"
        prefix: /p/app/openfoam/aocc-compiler-4.1.0
        modules: []
""",
        encoding="utf-8",
    )

    issues = validate_rendered_workspace(tmp_path)

    assert [issue.code for issue in issues] == ["rendered-external-spec-invalid"]
    assert "clang@clang/v2512-" in issues[0].message

