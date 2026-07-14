from __future__ import annotations

from pathlib import Path

from stack_composer.render.shared_exposure import build_shared_exposure_plan
from stack_composer.validate.checks import validate_lane_agnostic_names
from stack_composer.yaml_io import load_yaml
from tests.test_render import render_fixture

MODULE_ROOT = "/shared/stack/modules/2026.06/example-cray/science-stack"


def make_lane(name: str, kind: str, compiler: str = "gcc") -> dict:
    return {
        "name": name,
        "kind": kind,
        "compiler": compiler,
        "source_build": kind,
        "package_module_root": f"{MODULE_ROOT}/{compiler}/{name.removeprefix(compiler + '-')}",
    }


def sources_declaring(*builds: str, packages: list[str] | None = None) -> dict:
    packages = packages if packages is not None else ["openblas"]
    return {build: {"lane_agnostic": packages} for build in builds}


def test_no_declaration_disables_plan() -> None:
    lanes = [make_lane("gcc-serial", "serial"), make_lane("gcc-mpi", "mpi")]
    plan, issues = build_shared_exposure_plan(
        stack={}, lanes=lanes, spec_sources={"serial": {}, "mpi": {}}
    )
    assert plan["enabled"] is False
    assert plan["by_compiler"] == {}
    assert issues == []


def test_serial_lane_owns_the_shared_root() -> None:
    lanes = [make_lane("gcc-serial", "serial"), make_lane("gcc-mpi", "mpi")]
    plan, issues = build_shared_exposure_plan(
        stack={},
        lanes=lanes,
        spec_sources=sources_declaring("serial", "mpi", packages=["openblas", "netlib-lapack"]),
    )
    assert issues == []
    assert plan["enabled"] is True
    assert plan["by_compiler"]["gcc"] == {
        "owner_lane": "gcc-serial",
        "packages": ["netlib-lapack", "openblas"],
        "shared_module_root": f"{MODULE_ROOT}/gcc/shared",
    }


def test_direct_exposure_makes_declaration_vacuous() -> None:
    # Direct exposure publishes every package module into one root already.
    lanes = [make_lane("gcc-serial", "serial"), make_lane("gcc-mpi", "mpi")]
    plan, issues = build_shared_exposure_plan(
        stack={"modules": {"exposure": "direct"}},
        lanes=lanes,
        spec_sources=sources_declaring("serial", "mpi"),
    )
    assert plan["enabled"] is False
    assert issues == []


def test_column_without_serial_lane_warns_instead_of_failing() -> None:
    # A stack that skips the serial kind never builds the declared packages;
    # the declaration is vacuous there, like any other kind the stack skips.
    lanes = [make_lane("gcc-mpi", "mpi")]
    plan, issues = build_shared_exposure_plan(
        stack={}, lanes=lanes, spec_sources=sources_declaring("mpi")
    )
    assert issues == []
    assert plan["enabled"] is False
    assert len(plan["warnings"]) == 1
    assert "no serial lane" in plan["warnings"][0]


def test_two_serial_owners_in_one_column_is_an_error() -> None:
    lanes = [
        dict(make_lane("gcc-serial-a", "serial"), source_build="serial-a"),
        dict(make_lane("gcc-serial-b", "serial"), source_build="serial-b"),
    ]
    plan, issues = build_shared_exposure_plan(
        stack={}, lanes=lanes, spec_sources=sources_declaring("serial-a", "serial-b")
    )
    assert plan["enabled"] is False
    assert [issue.code for issue in issues] == ["lane-agnostic-ambiguous-owner"]


def test_lane_agnostic_names_must_be_serial_only() -> None:
    package_set = {
        "name": "example",
        "lane_agnostic": ["openblas", "gsl", "hdf5", "nonesuch"],
        "specs": {
            "any": ["gsl@2.8"],
            "serial": ["openblas@0.3.30", "hdf5@1.14.5~mpi"],
            "mpi": ["hdf5@1.14.5+mpi"],
        },
    }
    issues = validate_lane_agnostic_names(package_set, Path("example.yaml"))
    codes = sorted((issue.code, issue.message.split("'")[1]) for issue in issues)
    assert codes == [
        ("lane-agnostic-not-serial-only", "gsl"),
        ("lane-agnostic-not-serial-only", "hdf5"),
        ("lane-agnostic-unknown-package", "nonesuch"),
    ]


def test_rendered_workspace_exposes_lane_agnostic_packages(tmp_path: Path) -> None:
    # The reference fixture declares lane_agnostic: [openblas, netlib-lapack]
    # in science-full. One serial build, module-visible from every payload lane.
    workspace = render_fixture(tmp_path / "out")
    root = workspace / "environments" / "gcc"

    serial_env = load_yaml(root / "serial" / "spack.yaml")
    modules = serial_env["spack"]["modules"]
    # The default set is a whitelist of the lane's own roots; the
    # lane-agnostic packages are simply not named (include outranks exclude),
    # so their only modulefiles are the shared set's.
    default_include = modules["default"]["tcl"]["include"]
    assert "openblas" not in default_include
    assert "netlib-lapack" not in default_include
    assert "hdf5" in default_include
    assert modules["default"]["tcl"]["exclude"] == ["@:"]
    shared = modules["cse_shared"]
    assert shared["use_view"] == "cse_modules"
    assert shared["roots"] == {"tcl": f"{MODULE_ROOT}/gcc/shared"}
    assert shared["tcl"]["include"] == ["netlib-lapack", "openblas"]
    assert shared["tcl"]["exclude"] == ["@:"]

    # Foundation pins never appear in any whitelist: they are reached through
    # the surface view and are never loadable modules.
    core_env = load_yaml(root / "core" / "spack.yaml")
    core_include = core_env["spack"]["modules"]["default"]["tcl"]["include"]
    assert "python" in core_include and "py-numpy" in core_include
    assert not {"zlib", "xz", "zstd"} & set(core_include)

    # Consuming lanes emit no shared set: they reach it purely via MODULEPATH.
    mpi_env = load_yaml(root / "mpi-craympich" / "spack.yaml")
    assert "cse_shared" not in mpi_env["spack"]["modules"]
    mpi_include = mpi_env["spack"]["modules"]["default"]["tcl"]["include"]
    assert "hdf5" in mpi_include and "tau" in mpi_include
    # Another lane's explicit installs never leak in: the whitelist is the
    # lane's own roster, nothing else.
    assert "openblas" not in mpi_include

    shared_prepend = f'prepend-path MODULEPATH "{MODULE_ROOT}/gcc/shared"'
    for selector in ("Serial", "MPI", "GPU"):
        text = (workspace / "modulefiles" / "gcc" / "lanes" / selector).read_text(
            encoding="utf-8"
        )
        assert shared_prepend in text
        # The lane's own root stays highest precedence (prepended last).
        assert text.index(shared_prepend) < text.index(
            f'prepend-path MODULEPATH "{MODULE_ROOT}/gcc/'
            + {"Serial": "serial", "MPI": "mpi-craympich", "GPU": "gpu-craympich-gfx90a"}[
                selector
            ]
        )
    init_text = (workspace / "modulefiles" / "cse" / "GCC").read_text(encoding="utf-8")
    assert "gcc/shared" not in init_text

    report = load_yaml(workspace / "reports" / "render-plan.yaml")
    assert report["shared_exposure"]["enabled"] is True
    assert report["shared_exposure"]["by_compiler"]["gcc"]["packages"] == [
        "netlib-lapack",
        "openblas",
    ]
    lane_entries = {
        entry["lane"]: entry for entry in report["module_plan"]["lane_modules"]
    }
    assert lane_entries["gcc-serial"]["shared_module_root"] == f"{MODULE_ROOT}/gcc/shared"
    assert lane_entries["gcc-mpi-craympich"]["shared_module_root"] == (
        f"{MODULE_ROOT}/gcc/shared"
    )
