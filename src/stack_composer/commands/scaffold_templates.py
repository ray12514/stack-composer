from __future__ import annotations

from importlib import resources
from pathlib import Path

import click

from stack_composer.errors import ValidationFailed
from stack_composer.model.profile import load_profile
from stack_composer.scaffold.facts import summarize_profile_facts
from stack_composer.scaffold.scope_emitter import (
    copy_path_tree_with_todos,
    copy_resource_tree_with_todos,
    write_text_with_todo,
)


def run(*, profile: str, seed: str | None, output: str, stack_kind: str) -> None:
    profile_data, issues = load_profile(Path(profile))
    if issues:
        raise ValidationFailed(issues)

    output_dir = Path(output)
    require_empty_output(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if seed:
        seed_dir = Path(seed)
        if not seed_dir.is_dir():
            raise click.ClickException(f"seed template set does not exist: {seed_dir}")
        copy_path_tree_with_todos(seed_dir, output_dir)
        seed_label = "seed"
    else:
        starter = resources.files("stack_composer.scaffold").joinpath(
            "starters", stack_kind
        )
        if not starter.is_dir():
            raise click.ClickException(f"unknown bundled starter {stack_kind!r}")
        copy_resource_tree_with_todos(starter, output_dir)
        seed_label = f"bundled:{stack_kind}"

    facts = summarize_profile_facts(profile_data)
    write_text_with_todo(output_dir / "REVIEW.md", review_text(facts, stack_kind, seed_label))
    click.echo(str(output_dir))


def require_empty_output(output_dir: Path) -> None:
    if output_dir.exists() and any(output_dir.iterdir()):
        raise click.ClickException(
            f"scaffold output directory must not contain existing files: {output_dir}"
        )


def review_text(facts: dict, stack_kind: str, seed_label: str) -> str:
    lines = [
        "# Scaffold Review",
        "",
        "TODO(scaffold): Resolve every TODO marker before promoting this template set.",
        "",
        f"- profile: {facts['system_name']}",
        f"- stack_kind: {stack_kind}",
        f"- starter: {seed_label}",
        f"- system_family: {facts['system_family']}",
        f"- os: {facts['os']}",
        f"- fabric: {facts['fabric']}",
        f"- vendor_cray: {str(facts['vendor_cray']).lower()}",
        f"- module_system: {facts['module_system']}",
        "",
        "## Resolved Facts",
        "",
        "- compilers: " + comma_list(facts["compilers"]),
        "- mpi_providers: " + comma_list(facts["mpi_providers"]),
        "- gpu_arches: " + comma_list(facts["gpu_arches"]),
        "- cpu_targets: " + comma_list(facts["cpu_targets"]),
        "- runtime_node_types: " + comma_list(facts["runtime_node_types"]),
        "",
        "## Maintainer Checklist",
        "",
        "- TODO: Review contract toolchain names against local compiler/MPI policy.",
        "- TODO: Review stack-defaults.yaml module and buildcache policy.",
        "- TODO: Review configs/common/*.yaml.j2 for site package and repo defaults.",
        "- TODO: Review each environments/<lane-kind>/spack.yaml.j2 before rendering.",
        "- TODO: Run validate-template-set after replacing placeholder package roots.",
        "",
    ]
    return "\n".join(lines)


def comma_list(values: list[str]) -> str:
    return ", ".join(values) if values else "(none)"
