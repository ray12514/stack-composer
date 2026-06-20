from __future__ import annotations

import io
import json

import pytest
import yaml

from stack_composer.commands import explain
from tests.conftest import fixture_path


def _run(stream: io.StringIO, **kwargs) -> str:
    explain.run(
        profile=str(kwargs.pop("profile")),
        templates=str(kwargs.pop("templates")),
        stack_path=kwargs.pop("stack_path", None),
        template_set_name=kwargs.pop("template_set_name", None),
        output_format=kwargs.pop("output_format", "yaml"),
        stream=stream,
    )
    return stream.getvalue()


def test_explain_cray_with_stack_lists_resolvable_vocabulary_and_narrowing_menu() -> None:
    buf = io.StringIO()
    text = _run(
        buf,
        profile=fixture_path("profiles", "example-cray", "profile.yaml"),
        templates=fixture_path("template-sets"),
        stack_path=fixture_path("stacks", "science-stack", "stack.yaml"),
    )
    parsed = yaml.safe_load(text)
    assert parsed["profile"] == "example-cray"
    assert parsed["template_set"] == "v6"
    assert {"core", "serial", "mpi", "gpu"} <= set(parsed["build_classes"])
    assert "science-gpu-default" in parsed["toolchains"]
    assert {"cpu", "gpu"} <= set(parsed["node_selectors"])
    assert "cray-mpich" in parsed["mpi_providers"]
    assert "gcc" in parsed["compilers"]
    assert {"gfx90a", "gfx942"} <= set(parsed["gpu_arches"])
    narrowing = parsed["per_system_narrowing"]
    assert narrowing["gpu"]["compilers"] == ["gcc"]
    assert narrowing["gpu"]["mpi"] == ["cray-mpich"]
    assert narrowing["gpu"]["gpu_selectors"] == ["mi250x"]
    assert narrowing["core"]["mpi"] == []


def test_explain_filters_out_toolchain_with_unavailable_gpu_toolkit() -> None:
    buf = io.StringIO()
    text = _run(
        buf,
        profile=fixture_path("profiles", "example-cray", "profile.yaml"),
        templates=fixture_path("template-sets"),
        template_set_name="v6",
    )
    parsed = yaml.safe_load(text)
    # cray profile has rocm but no cudatoolkit; the cuda toolchain must not appear
    assert "science-craympich-cuda" not in parsed["toolchains"]


def test_explain_linux_filters_out_unresolvable_node_selectors() -> None:
    buf = io.StringIO()
    text = _run(
        buf,
        profile=fixture_path("profiles", "example-linux", "profile.yaml"),
        templates=fixture_path("template-sets"),
        stack_path=fixture_path("stacks", "science-stack", "stack.yaml"),
    )
    parsed = yaml.safe_load(text)
    assert parsed["node_selectors"] == ["cpu"]
    assert parsed["gpu_arches"] == []
    assert parsed["per_system_narrowing"]["gpu"]["compilers"] == []


def test_explain_without_stack_requires_template_set_name() -> None:
    buf = io.StringIO()
    with pytest.raises(Exception) as excinfo:
        _run(
            buf,
            profile=fixture_path("profiles", "example-cray", "profile.yaml"),
            templates=fixture_path("template-sets"),
        )
    assert "template-set" in str(excinfo.value).lower()


def test_explain_with_template_set_only_omits_narrowing_menu() -> None:
    buf = io.StringIO()
    text = _run(
        buf,
        profile=fixture_path("profiles", "example-cray", "profile.yaml"),
        templates=fixture_path("template-sets"),
        template_set_name="v6",
        output_format="json",
    )
    parsed = json.loads(text)
    assert "per_system_narrowing" not in parsed
    assert parsed["template_set"] == "v6"


def test_explain_human_format_includes_each_section() -> None:
    buf = io.StringIO()
    text = _run(
        buf,
        profile=fixture_path("profiles", "example-cray", "profile.yaml"),
        templates=fixture_path("template-sets"),
        stack_path=fixture_path("stacks", "science-stack", "stack.yaml"),
        output_format="human",
    )
    for heading in (
        "profile:",
        "template_set:",
        "build_classes:",
        "toolchains:",
        "node_selectors:",
        "compilers:",
        "mpi_providers:",
        "gpu_arches:",
        "per_system_narrowing:",
    ):
        assert heading in text


def test_explain_is_deterministic_across_runs() -> None:
    runs = []
    for _ in range(2):
        buf = io.StringIO()
        runs.append(
            _run(
                buf,
                profile=fixture_path("profiles", "example-cray", "profile.yaml"),
                templates=fixture_path("template-sets"),
                stack_path=fixture_path("stacks", "science-stack", "stack.yaml"),
                output_format="yaml",
            )
        )
    assert runs[0] == runs[1]
