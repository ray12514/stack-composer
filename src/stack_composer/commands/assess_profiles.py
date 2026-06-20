from __future__ import annotations

import glob
import sys
from pathlib import Path
from typing import IO, Any

import yaml

from stack_composer.commands.explain import (
    resolvable_node_selectors,
    resolvable_toolchains,
    summarize_profile_facts,
)
from stack_composer.errors import ValidationFailed
from stack_composer.model.contract import load_contract
from stack_composer.model.profile import load_profile


def run(
    *,
    profiles: tuple[str, ...],
    templates: str,
    output: str | None,
    stream: IO[str] | None = None,
    stderr: IO[str] | None = None,
) -> None:
    out = stream or sys.stdout
    err = stderr or sys.stderr

    profile_paths = expand_profile_globs(profiles)
    if not profile_paths:
        raise ValueError(f"no profiles matched globs {list(profiles)!r}")

    profile_records = []
    for path in profile_paths:
        data, issues = load_profile(path)
        if issues:
            raise ValidationFailed(issues)
        profile_records.append((path, data))

    template_set_paths = enumerate_template_sets(Path(templates))
    if not template_set_paths:
        raise ValueError(f"no template sets found under {templates!r}")

    matrix: dict[str, dict[str, dict[str, Any]]] = {}
    for ts_path in template_set_paths:
        contract, contract_issues = load_contract(ts_path / "contract.yaml")
        if contract_issues:
            raise ValidationFailed(contract_issues)
        per_profile: dict[str, dict[str, Any]] = {}
        for _, profile in profile_records:
            per_profile[profile["system"]["name"]] = assess_pair(profile, contract)
        matrix[ts_path.name] = per_profile

    report = {"template_sets": matrix, "gaps": derive_gaps(matrix)}
    if output:
        Path(output).write_text(yaml.safe_dump(report, sort_keys=False), encoding="utf-8")
        write_summary(report, err)
    else:
        yaml.safe_dump(report, out, sort_keys=False, default_flow_style=False)


def expand_profile_globs(profile_args: tuple[str, ...]) -> list[Path]:
    paths: list[Path] = []
    seen: set[Path] = set()
    for arg in profile_args:
        if any(c in arg for c in "*?["):
            matches = sorted(Path(p) for p in glob.glob(arg))
        else:
            matches = [Path(arg)]
        for path in matches:
            resolved = path.resolve()
            if resolved not in seen:
                paths.append(path)
                seen.add(resolved)
    return paths


def enumerate_template_sets(root: Path) -> list[Path]:
    if not root.is_dir():
        return []
    return sorted(child for child in root.iterdir() if (child / "contract.yaml").is_file())


def assess_pair(profile: dict[str, Any], contract: dict[str, Any]) -> dict[str, Any]:
    facts = summarize_profile_facts(profile)
    build_classes = sorted((contract.get("build_classes") or {}).keys())
    toolchains_total = sorted((contract.get("toolchains") or {}).keys())
    node_selectors_total = sorted((contract.get("node_selectors") or {}).keys())
    gpu_selectors_total = sorted((contract.get("gpu_selectors") or {}).keys())

    toolchains_ok = resolvable_toolchains(profile, contract)
    node_selectors_ok = resolvable_node_selectors(profile, contract)
    profile_arches = set(facts["gpu_arches"])
    gpu_selectors_ok = [
        name
        for name in gpu_selectors_total
        if (contract.get("gpu_selectors") or {}).get(name, {}).get("arch_target") in profile_arches
    ]

    return {
        "covered": bool(toolchains_ok and node_selectors_ok),
        "build_classes": {"resolvable": build_classes, "total": len(build_classes)},
        "toolchains": {
            "resolvable": toolchains_ok,
            "blocked": [t for t in toolchains_total if t not in toolchains_ok],
        },
        "node_selectors": {
            "resolvable": node_selectors_ok,
            "blocked": [s for s in node_selectors_total if s not in node_selectors_ok],
        },
        "gpu_selectors": {
            "resolvable": gpu_selectors_ok,
            "blocked": [s for s in gpu_selectors_total if s not in gpu_selectors_ok],
        },
        "compilers": facts["compiler_names"],
        "mpi_providers": facts["mpi_provider_names"],
        "gpu_arches": facts["gpu_arches"],
    }


def derive_gaps(
    matrix: dict[str, dict[str, dict[str, Any]]],
) -> list[dict[str, Any]]:
    gaps: list[dict[str, Any]] = []
    for ts_name, profiles in matrix.items():
        for profile_name, result in profiles.items():
            blocked_toolchains = result["toolchains"]["blocked"]
            blocked_node_selectors = result["node_selectors"]["blocked"]
            blocked_gpu_selectors = result["gpu_selectors"]["blocked"]
            if not (blocked_toolchains or blocked_node_selectors or blocked_gpu_selectors):
                continue
            gaps.append(
                {
                    "template_set": ts_name,
                    "profile": profile_name,
                    "blocked_toolchains": list(blocked_toolchains),
                    "blocked_node_selectors": list(blocked_node_selectors),
                    "blocked_gpu_selectors": list(blocked_gpu_selectors),
                }
            )
    return gaps


def write_summary(report: dict[str, Any], err: IO[str]) -> None:
    err.write("assess-profiles summary:\n")
    for ts_name, profiles in report["template_sets"].items():
        for profile_name, result in profiles.items():
            covered = "covered" if result["covered"] else "uncovered"
            ok = len(result["toolchains"]["resolvable"])
            total = ok + len(result["toolchains"]["blocked"])
            err.write(f"  {ts_name} x {profile_name}: {covered} ({ok}/{total} toolchains)\n")
    err.write(f"gaps: {len(report['gaps'])}\n")
