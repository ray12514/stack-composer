from __future__ import annotations

from pathlib import Path

from stack_composer.render.environments import module_root_projections, root_projections
from stack_composer.yaml_io import load_yaml
from tests.test_render import render_fixture

PY_QUALIFIED = "{name}/{version}-python{^python.version}"


def test_unique_roots_keep_clean_names() -> None:
    projections, issues = root_projections(["zlib@1.3.1", "hdf5@1.14.6~mpi", "hdf5@2.1.0~mpi"])
    assert issues == []
    assert all(entry["projection"] == "{name}/{version}" for entry in projections)


def test_python_line_collisions_get_qualified_names() -> None:
    specs = [
        "python@3.14.5",
        "python@3.13.13",
        "py-numpy@2.4.6 ^python@3.14.5",
        "py-numpy@2.4.6 ^python@3.13.13",
    ]
    projections, issues = root_projections(specs)
    assert issues == []
    by_name = {entry["name"]: entry["projection"] for entry in projections}
    # Qualified only where ambiguous: the two pythons differ by version.
    assert by_name["python"] == "{name}/{version}"
    assert by_name["py-numpy"] == PY_QUALIFIED


def test_collision_without_python_line_is_an_error() -> None:
    projections, issues = root_projections(["foo@1.0 +a", "foo@1.0 +b"])
    assert [issue.code for issue in issues] == [
        "ambiguous-root-modules",
        "ambiguous-root-modules",
    ]


def test_module_view_uses_hash_fallback_for_foundation_packages() -> None:
    projections, issues = root_projections(
        ["zlib@1.3.1", "xz@5.4.6", "zstd@1.5.6", "python@3.14.5"]
    )
    assert issues == []

    filtered = module_root_projections(
        projections,
        {"zlib": "1.3.1", "xz": "5.4.6", "zstd": "1.5.6"},
    )

    assert filtered == [{"name": "python", "projection": "{name}/{version}"}]


def test_rendered_core_env_carries_qualified_projections(tmp_path: Path) -> None:
    workspace = render_fixture(tmp_path / "out")
    core_env = load_yaml(workspace / "environments" / "gcc" / "core" / "spack.yaml")

    view = core_env["spack"]["view"]["cse_modules"]["projections"]
    assert view["py-numpy"] == PY_QUALIFIED
    assert view["python"] == "{name}/{version}"
    assert "zlib" not in view
    assert "xz" not in view
    assert "zstd" not in view

    tcl = core_env["spack"]["modules"]["default"]["tcl"]["projections"]
    assert tcl["py-numpy"] == PY_QUALIFIED
    assert tcl["all"] == "{name}/{version}"

    # Lanes without collisions render no per-package module projections.
    serial_env = load_yaml(workspace / "environments" / "gcc" / "serial" / "spack.yaml")
    assert serial_env["spack"]["modules"]["default"]["tcl"]["projections"] == {
        "all": "{name}/{version}"
    }
