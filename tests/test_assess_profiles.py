from __future__ import annotations

import io
from pathlib import Path

import yaml

from stack_composer.commands import assess_profiles
from tests.conftest import fixture_path


def _run(stdout: io.StringIO, stderr: io.StringIO, **kwargs) -> None:
    assess_profiles.run(
        profiles=kwargs.pop("profiles"),
        templates=str(kwargs.pop("templates")),
        output=kwargs.pop("output", None),
        stream=stdout,
        stderr=stderr,
    )


def _profile_paths() -> tuple[str, ...]:
    return (
        str(fixture_path("profiles", "example-cray", "profile.yaml")),
        str(fixture_path("profiles", "example-linux", "profile.yaml")),
    )


def test_assess_profiles_reports_both_profiles_under_v6() -> None:
    out, err = io.StringIO(), io.StringIO()
    _run(out, err, profiles=_profile_paths(), templates=fixture_path("template-sets"))

    report = yaml.safe_load(out.getvalue())
    assert set(report["template_sets"]["v6"].keys()) == {"example-cray", "example-linux"}
    cray = report["template_sets"]["v6"]["example-cray"]
    linux = report["template_sets"]["v6"]["example-linux"]

    assert cray["covered"]
    assert linux["covered"]
    assert "gpu" in cray["node_selectors"]["resolvable"]
    assert linux["node_selectors"]["resolvable"] == ["cpu"]
    assert linux["node_selectors"]["blocked"] == ["gpu"]


def test_assess_profiles_blocks_cuda_toolchain_on_rocm_only_cray() -> None:
    out, err = io.StringIO(), io.StringIO()
    _run(out, err, profiles=_profile_paths(), templates=fixture_path("template-sets"))
    report = yaml.safe_load(out.getvalue())
    cray = report["template_sets"]["v6"]["example-cray"]
    assert "science-craympich-cuda" in cray["toolchains"]["blocked"]


def test_assess_profiles_derives_gap_entries_for_uncovered_axes() -> None:
    out, err = io.StringIO(), io.StringIO()
    _run(out, err, profiles=_profile_paths(), templates=fixture_path("template-sets"))
    report = yaml.safe_load(out.getvalue())

    linux_gap = next(
        gap for gap in report["gaps"]
        if gap["profile"] == "example-linux" and gap["template_set"] == "v6"
    )
    assert linux_gap["blocked_node_selectors"] == ["gpu"]


def test_assess_profiles_writes_to_output_path_and_prints_summary_to_stderr(tmp_path: Path) -> None:
    out, err = io.StringIO(), io.StringIO()
    report_path = tmp_path / "coverage.yaml"
    _run(
        out, err,
        profiles=_profile_paths(),
        templates=fixture_path("template-sets"),
        output=str(report_path),
    )

    assert report_path.exists()
    report = yaml.safe_load(report_path.read_text(encoding="utf-8"))
    assert "template_sets" in report
    assert out.getvalue() == ""
    summary = err.getvalue()
    assert "assess-profiles summary" in summary
    assert "example-cray" in summary
    assert "example-linux" in summary


def test_assess_profiles_is_deterministic_across_runs() -> None:
    runs = []
    for _ in range(2):
        out = io.StringIO()
        _run(out, io.StringIO(), profiles=_profile_paths(), templates=fixture_path("template-sets"))
        runs.append(out.getvalue())
    assert runs[0] == runs[1]
