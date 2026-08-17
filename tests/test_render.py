from __future__ import annotations

import shutil
from copy import deepcopy
from pathlib import Path

import pytest
import yaml
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

    packages = load_yaml(workspace / "configs" / "common" / "packages.yaml")
    assert packages["packages"]["all"]["permissions"] == {
        "group": "cse",
        "read": "group",
        "write": "group",
    }
    # Foundation pins render as require entries in the common scope, so every
    # lane's concretization resolves the pinned version, root or dependency.
    for name, version in (("zlib", "1.3.1"), ("xz", "5.4.6"), ("zstd", "1.5.6")):
        assert packages["packages"][name]["require"] == [f"@{version}"]
    config = load_yaml(workspace / "configs" / "common" / "config.yaml")
    assert config["config"]["install_tree"]["root"] == "/shared/stack/spack/opt"
    assert config["config"]["source_cache"] == "/shared/stack/spack/source-cache"
    assert (workspace / "configs" / "common" / "repos.yaml").exists()
    assert (workspace / "package-repos" / "science").is_dir()
    manifest = load_yaml(workspace / "release-manifest.yaml")
    assert validate_schema("release-manifest", manifest, "release-manifest.yaml") == []
    assert manifest["phase"] == "draft"
    assert manifest["templates"]["render_tool"]["name"] == "stack-composer render"
    assert {lane["kind"] for lane in manifest["lanes"]} == {
        "core", "common", "serial", "mpi", "gpu",
    }
    render_plan = load_yaml(workspace / "reports" / "render-plan.yaml")
    assert render_plan["system"]["name"] == "example-cray"
    assert render_plan["stack"]["name"] == "science-stack"
    assert {lane["kind"] for lane in render_plan["lanes"]} == {
        "core", "common", "serial", "mpi", "gpu",
    }
    assert render_plan["platform_plan"] == {
        "family": "cray-pe",
        "release_policy": {
            "selector": "latest",
            "scope": "platform_system_externals",
        },
        "selected_system_externals": [],
        "ignored_system_externals": [],
    }
    assert render_plan["network_plan"]["mpi_providers"] == [
        {
            "provider": "cray-mpich",
            "version": "8.1.29",
            "source": "platform",
            "toolchains": [
                {
                    "name": "cce1701_craympich8129",
                    "compiler": "cce",
                    "compiler_ref": "cce",
                },
                {
                    "name": "gcc1330_craympich8129",
                    "compiler": "gcc",
                    "compiler_ref": "gcc",
                },
            ],
        }
    ]
    assert render_plan["network_plan"]["fabric_userspace"] == {
        "observed": [
            {
                "name": "libfabric",
                "version": "1.20",
                "prefix": "/opt/cray/libfabric/1.20",
                "modules": [],
            },
            {"name": "ucx", "version": "1.15", "prefix": "/usr", "modules": []},
        ],
        "rendered_common_externals": [
            {
                "name": "libfabric",
                "version": "1.20",
                "prefix": "/opt/cray/libfabric/1.20",
                "provider_family": "system",
                "detection": {
                    "confidence": "probed",
                    "source": "fi_info version + development surface",
                },
            },
            {
                "name": "ucx",
                "version": "1.15",
                "prefix": "/usr",
                "provider_family": "system",
                "variants": "+thread_multiple",
                "detection": {
                    "confidence": "probed",
                    "source": "ucx_info version + development surface",
                },
            },
        ],
        "rendered_mpi_externals": [],
        "not_rendered": [],
    }
    assert render_plan["module_plan"]["exposure"] == "front_door"
    assert render_plan["module_plan"]["enabled"] is True


def test_render_workspace_writes_front_door_lane_modules(tmp_path: Path) -> None:
    workspace = render_fixture(tmp_path / "out-a")

    init_module = workspace / "modulefiles" / "cse" / "GCC"
    init_text = init_module.read_text(encoding="utf-8")

    assert init_text.startswith("#%Module1.0\n")
    assert 'module-whatis "cse compiler surface: GCC"' in init_text
    assert "prereq PrgEnv-gnu" in init_text
    assert "prereq gcc-native/13" in init_text
    assert (
        'prepend-path PATH "/shared/stack/views/2026.06/example-cray/'
        'science-stack/gcc/core/bin"'
    ) in init_text
    assert (
        'prepend-path MODULEPATH "/shared/stack/modules/2026.06/example-cray/'
        'science-stack/gcc/lanes"'
    ) in init_text
    assert "gpu-craympich-gfx90a" not in init_text

    selector = workspace / "modulefiles" / "gcc" / "lanes" / "GPU"
    text = selector.read_text(encoding="utf-8")

    assert text.startswith("#%Module1.0\n")
    assert 'module-whatis "cse lane: GCC GPU"' in text
    assert "conflict Serial" in text
    assert "conflict MPI" in text
    assert "prereq cray-mpich/8.1.29" in text
    assert "prereq rocm/6.0.0" in text
    assert 'setenv STACK_RELEASE "2026.06"' in text
    assert 'setenv STACK_COMPILER "gcc"' in text
    assert 'setenv STACK_LANE "GPU"' in text
    assert 'setenv STACK_LANE_ID "gpu-craympich-gfx90a"' in text
    assert (
        'prepend-path MODULEPATH "/shared/stack/modules/2026.06/example-cray/'
        'science-stack/gcc/gpu-craympich-gfx90a"'
    ) in text
    assert (
        'prepend-path MODULEPATH "/shared/stack/modules/2026.06/example-cray/'
        'science-stack/gcc/core"'
    ) not in text

    render_plan = load_yaml(workspace / "reports" / "render-plan.yaml")
    module_plan = render_plan["module_plan"]
    assert module_plan["module_root"] == "cse"
    gcc_init = next(
        entry for entry in module_plan["init_modules"] if entry["name"] == "cse/GCC"
    )
    assert gcc_init == {
        "name": "cse/GCC",
        "compiler": "gcc",
        "file": "modulefiles/cse/GCC",
        "prereqs": ["PrgEnv-gnu", "gcc-native/13"],
        "core_lane": "gcc-core",
        "core_view_root": "/shared/stack/views/2026.06/example-cray/science-stack/gcc/core",
        # Foundation reaches users through the view; Core and compiler-common
        # reach them as modules, both from the surface rather than a lane.
        "core_module_root": (
            "/shared/stack/modules/2026.06/example-cray/science-stack/gcc/core"
        ),
        "common_lane": "gcc-common",
        "common_module_root": (
            "/shared/stack/modules/2026.06/example-cray/science-stack/gcc/common"
        ),
        "lane_module_root": (
            "/shared/stack/modules/2026.06/example-cray/science-stack/gcc/lanes"
        ),
    }
    gpu_module = next(
        entry for entry in module_plan["lane_modules"] if entry["lane_id"] == "gpu-craympich-gfx90a"
    )
    assert gpu_module["public_name"] == "GPU"
    assert gpu_module["file"] == "modulefiles/gcc/lanes/GPU"
    assert gpu_module["prereqs"] == [
        "PrgEnv-gnu",
        "gcc-native/13",
        "cray-mpich/8.1.29",
        "rocm/6.0.0",
    ]
    assert "MPI" in gpu_module["conflicts"]
    assert "Serial" in gpu_module["conflicts"]
    assert gpu_module["package_module_root"] == (
        "/shared/stack/modules/2026.06/example-cray/science-stack/"
        "gcc/gpu-craympich-gfx90a"
    )


def test_front_door_autoload_policy_loads_platform_modules(tmp_path: Path) -> None:
    stack = deepcopy(load_yaml(fixture_path("stacks", "science-stack", "stack.yaml")))
    stack["modules"] = {
        "format": "tcl",
        "exposure": "front_door",
        "module_root": "cse",
        "platform_module_policy": "autoload",
    }
    stack_path = tmp_path / "stack.yaml"
    stack_path.write_text(yaml.safe_dump(stack, sort_keys=False), encoding="utf-8")

    workspace = render_workspace(
        profile_path=fixture_path("profiles", "example-cray", "profile.yaml"),
        deployment_path=fixture_path("deployments", "example-cray.yaml"),
        stack_path=stack_path,
        templates_root=fixture_path("template-sets"),
        release_vars=ReleaseVars(
            release_tag="2026.06",
            output_root=(tmp_path / "out-a").as_posix(),
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

    init_text = (workspace / "modulefiles" / "cse" / "GCC").read_text(encoding="utf-8")
    lane_text = (
        workspace / "modulefiles" / "gcc" / "lanes" / "GPU"
    ).read_text(encoding="utf-8")
    assert "module load PrgEnv-gnu" in init_text
    assert "module load gcc-native/13" in init_text
    assert "prereq PrgEnv-gnu" not in init_text
    assert "module load cray-mpich/8.1.29" in lane_text
    assert "module load rocm/6.0.0" in lane_text
    assert "prereq cray-mpich/8.1.29" not in lane_text


def test_render_workspace_uses_build_names_when_lane_names_collide(tmp_path: Path) -> None:
    stack = deepcopy(load_yaml(fixture_path("stacks", "science-stack", "stack.yaml")))
    stack["builds"] = [
        build for build in stack["builds"] if build["name"] not in {"mpi", "gpu"}
    ]
    stack["builds"].extend(
        [
            {
                "name": "mpi-osu",
                "kind": "mpi",
                "package_set": "science-full",
                "compilers": ["gcc"],
            },
            {
                "name": "mpi-hdf5",
                "kind": "mpi",
                "package_set": "science-full",
                "compilers": ["gcc"],
            },
        ]
    )
    stack["per_system"]["example-cray"]["builds"] = {
        "core": {"compilers": ["gcc"]},
        "serial": {"compilers": ["gcc"]},
        "mpi-osu": {"compilers": ["gcc"]},
        "mpi-hdf5": {"compilers": ["gcc"]},
    }
    stack_path = tmp_path / "stack.yaml"
    stack_path.write_text(yaml.safe_dump(stack, sort_keys=False), encoding="utf-8")

    workspace = render_workspace(
        profile_path=fixture_path("profiles", "example-cray", "profile.yaml"),
        deployment_path=fixture_path("deployments", "example-cray.yaml"),
        stack_path=stack_path,
        templates_root=fixture_path("template-sets"),
        release_vars=ReleaseVars(
            release_tag="2026.06",
            output_root=(tmp_path / "out-a").as_posix(),
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

    lane_root = workspace / "modulefiles" / "gcc" / "lanes"
    assert (lane_root / "mpi-osu-craympich").exists()
    assert (lane_root / "mpi-hdf5-craympich").exists()
    assert not (lane_root / "mpi").exists()

    osu_text = (lane_root / "mpi-osu-craympich").read_text(encoding="utf-8")
    assert "conflict mpi-hdf5-craympich" in osu_text
    assert 'setenv STACK_LANE "mpi-osu-craympich"' in osu_text
    assert 'setenv STACK_LANE_ID "mpi-osu-craympich"' in osu_text


def test_render_workspace_skips_front_door_modules_for_direct_exposure(tmp_path: Path) -> None:
    stack = deepcopy(load_yaml(fixture_path("stacks", "science-stack", "stack.yaml")))
    stack["modules"] = {
        "format": "tcl",
        "exposure": "direct",
        "module_root": "ScienceStack",
    }
    stack_path = tmp_path / "stack.yaml"
    stack_path.write_text(yaml.safe_dump(stack, sort_keys=False), encoding="utf-8")
    deployment = deepcopy(load_yaml(fixture_path("deployments", "example-cray.yaml")))
    deployment["modules"]["publish_root"] = "/sw/site/modulefiles"
    deployment_path = tmp_path / "deployment.yaml"
    deployment_path.write_text(yaml.safe_dump(deployment, sort_keys=False), encoding="utf-8")

    workspace = render_workspace(
        profile_path=fixture_path("profiles", "example-cray", "profile.yaml"),
        deployment_path=deployment_path,
        stack_path=stack_path,
        templates_root=fixture_path("template-sets"),
        release_vars=ReleaseVars(
            release_tag="2026.06",
            output_root=(tmp_path / "out-a").as_posix(),
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

    assert not (workspace / "modulefiles").exists()
    render_plan = load_yaml(workspace / "reports" / "render-plan.yaml")
    assert render_plan["module_plan"]["exposure"] == "direct"
    assert render_plan["module_plan"]["enabled"] is False
    assert render_plan["module_plan"]["init_modules"] == []
    assert render_plan["module_plan"]["lane_modules"] == []


def test_render_workspace_handles_generic_linux_without_gpu(tmp_path: Path) -> None:
    workspace = render_fixture(tmp_path / "out-a", profile_name="example-linux")

    manifest = load_yaml(workspace / "release-manifest.yaml")
    assert validate_schema("release-manifest", manifest, "release-manifest.yaml") == []
    assert manifest["profile"]["system_name"] == "example-linux"
    assert {lane["kind"] for lane in manifest["lanes"]} == {"core", "common", "serial", "mpi"}
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
    broken_template = templates_root / "v6" / "environments" / "serial" / "spack.yaml.j2"
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
        deployment_path=fixture_path("deployments", profile_name + ".yaml"),
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


def test_repos_yaml_pins_builtin_recipe_generation(tmp_path: Path) -> None:
    # The recipe generation is a declared input, not whatever the Spack clone
    # defaults to: defaults.spack.package_repo pins builtin to an exact ref,
    # and local package repos ride alongside in the named mapping form.
    workspace = render_fixture(tmp_path / "out-a")

    repos = load_yaml(workspace / "configs" / "common" / "repos.yaml")
    builtin = repos["repos"]["builtin"]
    assert builtin["git"] == "https://github.com/spack/spack-packages.git"
    assert builtin["tag"] == "v2026.06.0"
    assert repos["repos"]["science"] == "../../package-repos/science"


def test_lane_environment_renders_projected_module_view(tmp_path: Path) -> None:
    # Spack 1.1+ use_view module generation: payload lanes carry a root-only,
    # version-projected default view plus a named projected view that package-
    # module generation reads. Public roots get clean {name}/{version}
    # projections; dependencies in the module view fall back to a hash-
    # qualified form and generate no modules (exclude_implicits).
    workspace = render_fixture(tmp_path / "out-a")

    env = load_yaml(workspace / "environments" / "gcc" / "serial" / "spack.yaml")
    views = env["spack"]["view"]
    default_view = views["default"]
    assert default_view["root"].endswith("/gcc/serial")
    assert default_view["link"] == "roots"
    assert default_view["projections"]["hdf5"] == "{name}/{version}"
    assert default_view["projections"]["all"] == "{name}/{version}-{hash:7}"
    modules_view = views["cse_modules"]
    assert modules_view["root"] == default_view["root"] + "-modules"
    assert modules_view["link"] == "roots"
    assert modules_view["projections"]["hdf5"] == "{name}/{version}"
    assert modules_view["projections"]["all"] == "{name}/{version}-{hash:7}"

    modules = env["spack"]["modules"]
    assert modules["default"]["use_view"] == "cse_modules"
    assert modules["default"]["roots"]["tcl"].endswith("/gcc/serial")
    assert modules["default"]["tcl"]["exclude_implicits"] is True
    assert modules["default"]["tcl"]["hash_length"] == 0
    assert modules["default"]["tcl"]["include"] == [
        "gsl@2.8",
        "hdf5@1.12.3~mpi+fortran",
        "hdf5@1.14.4~mpi+fortran",
        "hdf5@1.14.5~mpi+fortran",
        "netcdf-c@4.9.0~mpi",
        "netcdf-c@4.9.2~mpi",
    ]
    assert modules["default"]["tcl"]["projections"]["all"] == "{name}/{version}"


def test_core_default_view_contains_only_ambient_foundation(tmp_path: Path) -> None:
    workspace = render_fixture(tmp_path / "out-a")

    env = load_yaml(workspace / "environments" / "gcc" / "core" / "spack.yaml")
    default_view = env["spack"]["view"]["default"]
    assert default_view["link"] == "roots"
    assert default_view["select"] == ["xz", "zlib", "zstd"]
    assert "projections" not in default_view


def test_module_formats_come_from_declared_policy(tmp_path: Path) -> None:
    # modules.format/additional_formats are policy; the template prints the
    # computed list and never hardcodes a format.
    stack = deepcopy(load_yaml(fixture_path("stacks", "science-stack", "stack.yaml")))
    stack["modules"] = {"format": "tcl", "additional_formats": ["lmod"]}
    stack_path = tmp_path / "stack.yaml"
    stack_path.write_text(yaml.safe_dump(stack, sort_keys=False), encoding="utf-8")

    workspace = render_workspace(
        profile_path=fixture_path("profiles", "example-cray", "profile.yaml"),
        deployment_path=fixture_path("deployments", "example-cray.yaml"),
        stack_path=stack_path,
        templates_root=fixture_path("template-sets"),
        release_vars=ReleaseVars(
            release_tag="2026.06",
            output_root=(tmp_path / "out-a").as_posix(),
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

    env = load_yaml(workspace / "environments" / "gcc" / "serial" / "spack.yaml")
    modules = env["spack"]["modules"]["default"]
    assert modules["enable"] == ["tcl", "lmod"]
    assert modules["roots"]["tcl"].endswith("/gcc/serial")
    assert modules["roots"]["lmod"].endswith("/gcc/serial")
    assert modules["lmod"]["exclude_implicits"] is True


def direct_stack() -> dict:
    stack = deepcopy(load_yaml(fixture_path("stacks", "science-stack", "stack.yaml")))
    stack["modules"] = {"exposure": "direct"}
    stack["builds"] = [
        {"name": "serial", "kind": "serial", "compilers": ["gcc"], "specs": ["cmake"]}
    ]
    stack.pop("per_system", None)
    return stack


def test_direct_exposure_publishes_package_modules_to_publish_root(tmp_path: Path) -> None:
    # direct exposure: no front door; package modules root at the
    # installer-chosen publish_root already on the site MODULEPATH.
    deployment = deepcopy(load_yaml(fixture_path("deployments", "example-cray.yaml")))
    deployment["modules"]["publish_root"] = "/sw/site/modulefiles"
    deployment_path = tmp_path / "deployment.yaml"
    deployment_path.write_text(yaml.safe_dump(deployment, sort_keys=False), encoding="utf-8")
    stack_path = tmp_path / "stack.yaml"
    stack_path.write_text(yaml.safe_dump(direct_stack(), sort_keys=False), encoding="utf-8")

    workspace = render_workspace(
        profile_path=fixture_path("profiles", "example-cray", "profile.yaml"),
        deployment_path=deployment_path,
        stack_path=stack_path,
        templates_root=fixture_path("template-sets"),
        release_vars=ReleaseVars(
            release_tag="2026.06",
            output_root=(tmp_path / "out-a").as_posix(),
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

    assert not (workspace / "modulefiles").exists()
    env = load_yaml(workspace / "environments" / "gcc" / "serial" / "spack.yaml")
    assert env["spack"]["modules"]["default"]["roots"]["tcl"] == "/sw/site/modulefiles"


def test_direct_exposure_without_publish_root_is_an_error(tmp_path: Path) -> None:
    stack_path = tmp_path / "stack.yaml"
    stack_path.write_text(yaml.safe_dump(direct_stack(), sort_keys=False), encoding="utf-8")

    with pytest.raises(ValidationFailed) as excinfo:
        render_workspace(
            profile_path=fixture_path("profiles", "example-cray", "profile.yaml"),
            deployment_path=fixture_path("deployments", "example-cray.yaml"),
            stack_path=stack_path,
            templates_root=fixture_path("template-sets"),
            release_vars=ReleaseVars(
                release_tag="2026.06",
                output_root=(tmp_path / "out-a").as_posix(),
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
    assert any(issue.code == "direct-exposure-needs-publish-root" for issue in excinfo.value.issues)


def test_lane_environments_isolate_from_ambient_config(tmp_path: Path) -> None:
    """Rendered lanes must use `include::`, the two-colon override form.

    The handoff contract names the include list, not ambient ~/.spack, site, or
    system scopes, as the production isolation boundary. Spack only honours
    that when the key carries two colons: with one, a stray user-scope
    packages.yaml silently joins the concretization and the same tree stops
    producing the same build.
    """
    workspace = render_fixture(tmp_path / "out-isolation")

    text = (workspace / "environments" / "gcc" / "serial" / "spack.yaml").read_text(
        encoding="utf-8"
    )
    assert "\n  include::\n" in text, "lane spack.yaml must override ambient config scopes"

    # The parsed key keeps the override colon, which is how Spack detects it.
    env = load_yaml(workspace / "environments" / "gcc" / "serial" / "spack.yaml")
    assert "include:" in env["spack"]
    assert env["spack"]["include:"], "scope list must survive the override form"


def build_all_stack(tmp_path: Path) -> Path:
    """The science stack, but building its compiler instead of consuming one."""
    stack = deepcopy(load_yaml(fixture_path("stacks", "science-stack", "stack.yaml")))
    stack["externals"] = {
        "compilers": "build_all",
        "mpi": "prefer_platform",
        "openssl": "system",
        "curl": "system",
        "libfabric": "system",
        "ucx": "system",
        "cray-libsci": "system",
    }
    for build in stack["builds"]:
        build["compilers"] = ["gcc@14.3.0"]
    stack.pop("per_system", None)
    path = tmp_path / "build-all-stack.yaml"
    path.write_text(yaml.safe_dump(stack, sort_keys=False), encoding="utf-8")
    return path


def test_build_all_renders_without_platform_compiler_facts(tmp_path: Path) -> None:
    """A stack-built compiler has no platform module to require.

    Lane modules `prereq` the platform modules behind site-external providers.
    A compiler we build ourselves has none, so demanding profile facts for it
    makes the posture unrenderable on every system.
    """
    workspace = render_workspace(
        profile_path=fixture_path("profiles", "example-cray", "profile.yaml"),
        deployment_path=fixture_path("deployments", "example-cray.yaml"),
        stack_path=build_all_stack(tmp_path),
        templates_root=fixture_path("template-sets"),
        release_vars=ReleaseVars(
            release_tag="2026.06",
            output_root=(tmp_path / "out").as_posix(),
            rendered_at="2026-06-19T00:00:00Z",
            source_repo=SourceRepo(
                "git@example:x", "0375b16fdeadbeef0123456789abcdef01234567", False
            ),
        ),
        package_sets_dir=fixture_path("package-sets"),
        package_repos_dir=fixture_path("package-repos"),
    )

    envs = sorted(workspace.glob("environments/*/*/spack.yaml"))
    assert envs, "build_all must still render lanes"
