from __future__ import annotations

from click.testing import CliRunner

from stack_composer.cli import cli
from tests.conftest import fixture_path


def test_help_lists_commands() -> None:
    result = CliRunner().invoke(cli, ["--help"])
    assert result.exit_code == 0
    assert "render" in result.output
    assert "publish-manifest" in result.output


def test_licenses_flag_prints_manifest() -> None:
    result = CliRunner().invoke(cli, ["--licenses"])
    assert result.exit_code == 0
    assert "stack-composer" in result.output
    assert "PyYAML" in result.output


def test_show_command_prints_provider_families_and_module_chains() -> None:
    result = CliRunner().invoke(
        cli,
        [
            "show",
            "--profile",
            str(fixture_path("profiles", "example-cray", "profile.yaml")),
            "--templates",
            str(fixture_path("template-sets")),
            "--template-set",
            "v6",
            "--stack",
            str(fixture_path("stacks", "science-stack", "stack.yaml")),
        ],
    )

    assert result.exit_code == 0, result.output
    assert "provider families: platform" in result.output
    assert "platform families: cray-pe" in result.output
    assert "family=platform/cray-pe" in result.output
    assert "modules=PrgEnv-gnu, gcc-native/13" in result.output
    assert "gcc      modules=cray-mpich/8.1.29" in result.output
    assert "components=8: hip, hsa-rocr-dev, comgr" in result.output
    assert "system externals (2 candidates)" in result.output
    assert "openssl" in result.output
    assert "curl" in result.output
    assert "scope=vendor/cray" in result.output
    assert "modules=PrgEnv-gnu, gcc-native/13, cray-mpich/8.1.29, rocm/6.0.0" in result.output


def test_show_command_prints_generic_provider_families() -> None:
    result = CliRunner().invoke(
        cli,
        [
            "show",
            "--profile",
            str(fixture_path("profiles", "example-linux", "profile.yaml")),
            "--templates",
            str(fixture_path("template-sets")),
            "--template-set",
            "v6",
            "--stack",
            str(fixture_path("stacks", "science-stack", "stack.yaml")),
        ],
    )

    assert result.exit_code == 0, result.output
    assert "provider families: site, system" in result.output
    assert "family=site" in result.output
    assert "family=system" in result.output
    assert "scope=vendor/linux" in result.output


def test_show_command_prints_toolchain_names() -> None:
    result = CliRunner().invoke(
        cli,
        [
            "show",
            "--profile",
            str(fixture_path("profiles", "example-cray", "profile.yaml")),
            "--templates",
            str(fixture_path("template-sets")),
            "--template-set",
            "v6",
            "--stack",
            str(fixture_path("stacks", "science-stack", "stack.yaml")),
        ],
    )

    assert result.exit_code == 0, result.output
    # The provider line names the toolchains a manual user can decorate with.
    assert (
        "toolchains: cce1701_craympich8129, gcc1330_craympich8129, "
        "rocmcc600_craympich8129"
    ) in result.output
    # Each resolved lane shows the decoration it will apply.
    assert "toolchain=gcc1330_craympich8129" in result.output


def test_show_command_marks_ambiguous_mpi_versions(tmp_path) -> None:
    import yaml

    profile_path = fixture_path("profiles", "example-linux", "profile.yaml")
    profile = yaml.safe_load(profile_path.read_text(encoding="utf-8"))
    profile["mpi_providers"].append(
        {
            "name": "openmpi",
            "version": "5.0.3",
            "provider_family": "site",
            "prefix": "/opt/site/openmpi/5.0.3-aocc-4.2.0",
            "compiler": "aocc@4.2.0",
        }
    )
    ambiguous_path = tmp_path / "profile.yaml"
    ambiguous_path.write_text(yaml.safe_dump(profile), encoding="utf-8")

    result = CliRunner().invoke(cli, ["show", "--profile", str(ambiguous_path)])

    assert result.exit_code == 0, result.output
    # Each version gets its own line and its own version-qualified toolchain
    # identity, plus the pointer to the disambiguating stack.yaml field.
    assert "aocc420_openmpi416" in result.output
    assert "aocc420_openmpi503" in result.output
    assert "mpi.version" in result.output


def test_validate_command_passes_reference_fixture() -> None:
    result = CliRunner().invoke(
        cli,
        [
            "validate",
            "--profile",
            str(fixture_path("profiles", "example-cray", "profile.yaml")),
            "--deployment",
            str(fixture_path("deployments", "example-cray.yaml")),
            "--stack",
            str(fixture_path("stacks", "science-stack", "stack.yaml")),
            "--templates",
            str(fixture_path("template-sets")),
            "--package-sets",
            str(fixture_path("package-sets")),
            "--package-repos",
            str(fixture_path("package-repos")),
        ],
    )
    assert result.exit_code == 0, result.output
    assert "valid: true" in result.output


def test_render_command_writes_workspace(tmp_path) -> None:
    result = CliRunner().invoke(
        cli,
        [
            "render",
            "--profile",
            str(fixture_path("profiles", "example-cray", "profile.yaml")),
            "--deployment",
            str(fixture_path("deployments", "example-cray.yaml")),
            "--stack",
            str(fixture_path("stacks", "science-stack", "stack.yaml")),
            "--templates",
            str(fixture_path("template-sets")),
            "--package-sets",
            str(fixture_path("package-sets")),
            "--package-repos",
            str(fixture_path("package-repos")),
            "--output-root",
            str(tmp_path),
            "--release",
            "2026.06",
            "--rendered-at",
            "2026-06-19T00:00:00Z",
            "--source-repo",
            "git@example:stacks/science-stack",
            "--source-commit",
            "0375b16fdeadbeef0123456789abcdef01234567",
        ],
    )
    assert result.exit_code == 0, result.output
    workspace = tmp_path / "example-cray" / "science-stack" / "2026.06"
    assert workspace.as_posix() in result.output
    assert (workspace / "release-manifest.yaml").exists()


def test_publish_manifest_missing_workspace_returns_clear_error() -> None:
    result = CliRunner().invoke(
        cli,
        [
            "publish-manifest",
            "--workspace",
            "workspace",
            "--build-host",
            "host",
            "--lockfiles",
            "locks",
            "--platform-module-prereqs",
            "prereqs.yaml",
            "--buildcache-destinations",
            "buildcache.yaml",
            "--verify-results",
            "verify.yaml",
        ],
    )
    assert result.exit_code != 0
    assert "release-manifest.yaml" in result.output
