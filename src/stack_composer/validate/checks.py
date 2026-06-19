from __future__ import annotations

from pathlib import Path
from typing import Any

from stack_composer.errors import Issue
from stack_composer.model.contract import load_contract
from stack_composer.model.package_set import load_package_set
from stack_composer.model.profile import load_profile
from stack_composer.model.stack import load_stack, load_stack_defaults, merge_defaults


def validate_inputs(
    *,
    profile_path: Path,
    stack_path: Path,
    templates_root: Path,
    package_sets_dir: Path,
    package_repos_dir: Path,
) -> tuple[list[Issue], dict[str, Any]]:
    issues: list[Issue] = []
    profile, profile_issues = load_profile(profile_path)
    raw_stack, stack_issues = load_stack(stack_path)
    issues.extend(profile_issues)
    issues.extend(stack_issues)
    if issues:
        return issues, {}

    template_set_name = raw_stack["templates"]["set"]
    template_set = templates_root / template_set_name
    defaults_path = template_set / "stack-defaults.yaml"
    contract_path = template_set / "contract.yaml"
    if not defaults_path.exists():
        issues.append(missing_file_issue(defaults_path, "template stack-defaults.yaml is required"))
    if not contract_path.exists():
        issues.append(missing_file_issue(contract_path, "template contract.yaml is required"))
    if issues:
        return issues, {}

    defaults, defaults_issues = load_stack_defaults(defaults_path)
    contract, contract_issues = load_contract(contract_path)
    issues.extend(defaults_issues)
    issues.extend(contract_issues)
    if issues:
        return issues, {}

    stack = merge_defaults(defaults, raw_stack)
    issues.extend(cross_check_profile_contract(profile, stack))
    issues.extend(validate_builds_against_contract(stack, contract))
    issues.extend(validate_package_sets(stack, package_sets_dir, contract))
    issues.extend(validate_package_repositories(stack, package_repos_dir))
    issues.extend(validate_per_system_narrowing(stack, profile, contract))
    spec_sources, spec_source_issues = load_spec_sources(stack, package_sets_dir, contract)
    issues.extend(spec_source_issues)

    context = {
        "profile": profile,
        "stack": stack,
        "raw_stack": raw_stack,
        "defaults": defaults,
        "contract": contract,
        "template_set": str(template_set),
        "spec_sources": spec_sources,
        "package_repos": resolve_package_repositories(stack, package_repos_dir),
    }
    return issues, context


def missing_file_issue(path: Path, message: str) -> Issue:
    return Issue("error", "missing-file", str(path), message)


def cross_check_profile_contract(profile: dict[str, Any], stack: dict[str, Any]) -> list[Issue]:
    issues: list[Issue] = []
    expected = stack.get("profile_contract", {}).get("schema_version")
    actual = profile.get("schema_version")
    if expected is not None and actual != expected:
        issues.append(
            Issue(
                "error",
                "profile-contract",
                "profile.schema_version",
                "profile schema_version "
                f"{actual!r} does not match stack profile_contract {expected!r}",
            )
        )
    return issues


def validate_builds_against_contract(
    stack: dict[str, Any], contract: dict[str, Any]
) -> list[Issue]:
    issues: list[Issue] = []
    build_classes = contract.get("build_classes", {})
    toolchains = contract.get("toolchains", {})
    node_selectors = contract.get("node_selectors", {})
    for index, build in enumerate(stack.get("builds", [])):
        location = f"stack.builds[{index}]"
        if build.get("class") not in build_classes:
            issues.append(
                Issue("error", "unknown-build-class", f"{location}.class", build.get("class", ""))
            )
        if build.get("toolchain") not in toolchains:
            issues.append(
                Issue(
                    "error",
                    "unknown-toolchain",
                    f"{location}.toolchain",
                    build.get("toolchain", ""),
                )
            )
        if build.get("nodes") not in node_selectors:
            issues.append(
                Issue("error", "unknown-node-selector", f"{location}.nodes", build.get("nodes", ""))
            )
    return issues


def validate_package_sets(
    stack: dict[str, Any], package_sets_dir: Path, contract: dict[str, Any]
) -> list[Issue]:
    issues: list[Issue] = []
    class_kinds = {
        name: build_class["package_set_kind"]
        for name, build_class in contract.get("build_classes", {}).items()
    }
    loaded: dict[str, dict[str, Any]] = {}
    for index, build in enumerate(stack.get("builds", [])):
        package_set_name = build.get("package_set")
        if not package_set_name:
            continue
        path = package_sets_dir / f"{package_set_name}.yaml"
        if not path.exists():
            issues.append(missing_file_issue(path, f"package set {package_set_name!r} is required"))
            continue
        if package_set_name not in loaded:
            package_set, schema_issues = load_package_set(path)
            issues.extend(schema_issues)
            if schema_issues:
                continue
            if package_set.get("name") != package_set_name:
                issues.append(
                    Issue(
                        "error",
                        "package-set-name-mismatch",
                        str(path),
                        "name "
                        f"{package_set.get('name')!r} does not match file stem "
                        f"{package_set_name!r}",
                    )
                )
            loaded[package_set_name] = package_set
        package_set = loaded.get(package_set_name)
        if not package_set:
            continue
        required_kind = class_kinds.get(build.get("class"))
        if required_kind and required_kind not in package_set.get("kinds", []):
            issues.append(
                Issue(
                    "error",
                    "package-set-kind-mismatch",
                    f"stack.builds[{index}].package_set",
                    f"{package_set_name!r} does not provide kind {required_kind!r}",
                )
            )
    return issues


def load_spec_sources(
    stack: dict[str, Any], package_sets_dir: Path, contract: dict[str, Any]
) -> tuple[dict[str, dict[str, Any]], list[Issue]]:
    sources: dict[str, dict[str, Any]] = {}
    issues: list[Issue] = []
    class_kinds = {
        name: build_class["package_set_kind"]
        for name, build_class in contract.get("build_classes", {}).items()
    }
    for build in stack.get("builds", []):
        build_name = build["name"]
        required_kind = class_kinds.get(build.get("class"), build.get("class"))
        if build.get("package_set"):
            path = package_sets_dir / f"{build['package_set']}.yaml"
            if not path.exists():
                continue
            package_set, schema_issues = load_package_set(path)
            issues.extend(schema_issues)
            if not schema_issues:
                sources[build_name] = package_set
            continue
        specs = build.get("specs")
        if isinstance(specs, list):
            sources[build_name] = {
                "kind": "inline",
                "name": build_name,
                "kinds": [required_kind],
                "specs": {required_kind: specs},
            }
        elif isinstance(specs, dict):
            sources[build_name] = {
                "kind": "inline",
                "name": build_name,
                "kinds": sorted(k for k in specs if k != "any"),
                "specs": specs,
            }
    return sources, issues


def validate_package_repositories(stack: dict[str, Any], package_repos_dir: Path) -> list[Issue]:
    issues: list[Issue] = []
    for index, repo in enumerate(stack.get("package_repositories", []) or []):
        repo_path = Path(repo["path"])
        if not repo_path.is_absolute():
            repo_path = package_repos_dir.parent / repo_path
        if not repo_path.exists():
            issues.append(
                missing_file_issue(
                    repo_path,
                    f"package repository from stack.package_repositories[{index}] does not exist",
                )
            )
    return issues


def resolve_package_repositories(
    stack: dict[str, Any], package_repos_dir: Path
) -> list[dict[str, Any]]:
    repos = []
    for repo in stack.get("package_repositories", []) or []:
        repo_path = Path(repo["path"])
        if not repo_path.is_absolute():
            repo_path = package_repos_dir.parent / repo_path
        repos.append(
            {
                "name": repo["name"],
                "namespace": repo["namespace"],
                "path": repo_path.as_posix(),
                "priority": repo["priority"],
                "source_commit": "unknown",
            }
        )
    return repos


def validate_per_system_narrowing(
    stack: dict[str, Any], profile: dict[str, Any], contract: dict[str, Any]
) -> list[Issue]:
    issues: list[Issue] = []
    system_name = profile.get("system", {}).get("name")
    if not system_name:
        return issues
    system_block = (stack.get("per_system") or {}).get(system_name)
    if not system_block:
        return issues
    build_names = {build["name"] for build in stack.get("builds", [])}
    gpu_selectors = contract.get("gpu_selectors", {})
    for build_name, narrowing in (system_block.get("builds") or {}).items():
        if build_name not in build_names:
            issues.append(
                Issue(
                    "error",
                    "unknown-narrowed-build",
                    f"per_system.{system_name}.builds.{build_name}",
                    "narrowing references a build name not present in stack.builds",
                )
            )
        for gpu_selector in narrowing.get("gpu_selectors", []) or []:
            if gpu_selector not in gpu_selectors:
                issues.append(
                    Issue(
                        "error",
                        "unknown-gpu-selector",
                        f"per_system.{system_name}.builds.{build_name}.gpu_selectors",
                        f"gpu selector {gpu_selector!r} is not defined in template contract",
                    )
                )
    return issues
