from __future__ import annotations

from typing import Any

from stack_composer.errors import Issue


def plan_lanes(
    profile: dict[str, Any], stack: dict[str, Any], contract: dict[str, Any]
) -> tuple[list[dict[str, Any]], list[dict[str, str]], dict[str, Any] | None, list[Issue]]:
    issues: list[Issue] = []
    lanes: list[dict[str, Any]] = []
    skipped: list[dict[str, str]] = []
    applied_narrowing = None
    system_name = profile["system"]["name"]
    narrowing = ((stack.get("per_system") or {}).get(system_name) or {}).get("builds") or {}

    for build in stack.get("builds", []):
        candidates, reason_code, reason = lane_candidates_for_build(profile, stack, contract, build)
        had_candidates_before_narrowing = bool(candidates)
        candidates, narrowing_result = apply_narrowing(candidates, narrowing.get(build["name"], {}))
        if narrowing_result:
            applied_narrowing = applied_narrowing or {"system": system_name, "builds": {}}
            applied_narrowing["builds"][build["name"]] = narrowing_result
        if candidates:
            lanes.extend(candidates)
            continue
        if had_candidates_before_narrowing:
            reason_code = "per_system_empty"
            reason = (
                f"per_system.{system_name} narrowing dropped every lane "
                f"for build {build['name']!r}"
            )
        if build.get("required", False):
            issues.append(
                Issue(
                    "error",
                    reason_code,
                    f"stack.builds.{build['name']}",
                    f"required build {build['name']!r} cannot render: {reason}",
                )
            )
            continue
        skipped.append({"build": build["name"], "reason_code": reason_code, "reason": reason})

    if not lanes:
        issues.append(
            Issue(
                "error",
                "no-rendered-lanes",
                "stack.builds",
                f"no stack builds can render for profile {system_name}",
            )
        )
    lanes.sort(key=lambda lane: (lane["compiler"], lane["lane"], lane["source_build"]))
    skipped.sort(key=lambda entry: entry["build"])
    return lanes, skipped, applied_narrowing, issues


def lane_candidates_for_build(
    profile: dict[str, Any], stack: dict[str, Any], contract: dict[str, Any], build: dict[str, Any]
) -> tuple[list[dict[str, Any]], str, str]:
    build_class = contract["build_classes"][build["class"]]
    node_selector = contract["node_selectors"][build["nodes"]]["match"]
    node_types = matching_node_types(profile, node_selector)
    if not node_types:
        return [], "nodes_unmatched", f"no profile node type matches selector {build['nodes']!r}"

    toolchain = contract["toolchains"][build["toolchain"]]
    compilers = compiler_candidates(profile, toolchain)
    if not compilers:
        return [], "requires_unsatisfied", f"no compiler candidate for {build['toolchain']!r}"

    mpi_provider = mpi_provider_for(profile, toolchain, build_class)
    gpu_selectors = gpu_selectors_for(profile, contract, node_types, build)
    if (
        build_class.get("requires")
        and "runtime_gpu" in build_class["requires"]
        and not gpu_selectors
    ):
        return [], "requires_unsatisfied", "build requires GPU but no contract GPU selector matches"

    lanes: list[dict[str, Any]] = []
    for compiler in compilers:
        for node_name, node in node_types:
            if build.get("expand") == "per_gpu_arch":
                node_gpu_arch = (node.get("gpu") or {}).get("arch_target")
                for gpu_selector_name, gpu_selector in gpu_selectors:
                    if gpu_selector.get("arch_target") != node_gpu_arch:
                        continue
                    lanes.append(
                        make_lane(
                            profile,
                            stack,
                            build,
                            build_class,
                            compiler,
                            mpi_provider,
                            node_name,
                            node,
                            gpu_selector_name,
                            gpu_selector,
                        )
                    )
                continue
            lanes.append(
                make_lane(
                    profile,
                    stack,
                    build,
                    build_class,
                    compiler,
                    mpi_provider,
                    node_name,
                    node,
                    None,
                    None,
                )
            )
            break
    return lanes, "template_not_supported", "no lane candidates produced"


def matching_node_types(
    profile: dict[str, Any], selector_match: str
) -> list[tuple[str, dict[str, Any]]]:
    matches: list[tuple[str, dict[str, Any]]] = []
    for name, node in sorted(profile.get("node_types", {}).items()):
        if node.get("role") not in {"runtime", "both"}:
            continue
        has_gpu = node.get("gpu") is not None
        if selector_match == "runtime_without_gpu" and not has_gpu:
            matches.append((name, node))
        elif selector_match == "runtime_with_gpu" and has_gpu:
            matches.append((name, node))
    return matches


def compiler_candidates(profile: dict[str, Any], toolchain: dict[str, Any]) -> list[str]:
    candidates: list[str] = []
    vendor_cray = profile.get("vendor_cray") or {}
    for name in ("gcc", "cce", "aocc", "intel", "nvhpc", "rocmcc"):
        if vendor_cray.get(name) is not None:
            candidates.append(name)
    for compiler in profile.get("compilers_external") or []:
        name = compiler.get("name")
        if name and name not in candidates:
            candidates.append(name)
    allowed = toolchain.get("allowed_compilers")
    if allowed:
        candidates = [name for name in candidates if name in set(allowed)]
    if not candidates:
        return []
    policy = toolchain.get("compiler", "")
    if policy == "gnu_host_default" and "gcc" in candidates:
        return ["gcc"]
    if policy.startswith("each_science_"):
        return [name for name in candidates if name != "rocmcc"]
    return candidates


def mpi_provider_for(
    profile: dict[str, Any], toolchain: dict[str, Any], build_class: dict[str, Any]
) -> str | None:
    if "mpi" not in build_class.get("requires", []):
        return None
    mpi_policy = toolchain.get("mpi", "")
    if (profile.get("vendor_cray") or {}).get("cray_mpich") and mpi_policy != "none":
        return "cray-mpich"
    providers = profile.get("mpi") or []
    return providers[0]["name"] if providers else None


def gpu_selectors_for(
    profile: dict[str, Any],
    contract: dict[str, Any],
    node_types: list[tuple[str, dict[str, Any]]],
    build: dict[str, Any],
) -> list[tuple[str, dict[str, Any]]]:
    if build.get("expand") != "per_gpu_arch":
        return []
    node_arches = {
        node.get("gpu", {}).get("arch_target")
        for _, node in node_types
        if node.get("gpu") is not None
    }
    selectors = []
    for name, selector in sorted((contract.get("gpu_selectors") or {}).items()):
        if selector.get("arch_target") in node_arches:
            selectors.append((name, selector))
    return selectors


def make_lane(
    profile: dict[str, Any],
    stack: dict[str, Any],
    build: dict[str, Any],
    build_class: dict[str, Any],
    compiler: str,
    mpi_provider: str | None,
    node_name: str,
    node: dict[str, Any],
    gpu_selector_name: str | None,
    gpu_selector: dict[str, Any] | None,
) -> dict[str, Any]:
    kind = build_class["lane_kind"]
    lane_suffix = kind
    if mpi_provider:
        lane_suffix += "-" + mpi_provider.replace("-", "")
    if gpu_selector:
        lane_suffix += "-" + gpu_selector["arch_target"]
    name = f"{compiler}-{lane_suffix}"
    target = (
        "x86_64_v3" if build_class["default_target"] == "foundation" else node["cpu"]["preferred"]
    )
    release_tag = stack.get("_release_tag", "validate")
    system_name = profile["system"]["name"]
    stack_name = stack["name"]
    release_root = f"/shared/stack/releases/{release_tag}/{system_name}/{stack_name}"
    return {
        "name": name,
        "source_build": build["name"],
        "compiler": compiler,
        "lane": lane_suffix,
        "kind": kind,
        "package_set": build.get("package_set"),
        "target": target,
        "runtime_node_type": node_name,
        "gpu_selector": gpu_selector_name,
        "gpu_arch": gpu_selector.get("arch_target") if gpu_selector else None,
        "mpi_provider": mpi_provider,
        "env_path": f"environments/{compiler}/{lane_suffix}",
        "spec_source": spec_source_id(build),
        "view_root": f"{release_root}/views/{compiler}/{lane_suffix}",
        "package_module_root": f"{release_root}/modules/{compiler}/{lane_suffix}",
    }


def spec_source_id(build: dict[str, Any]) -> str:
    if build.get("package_set"):
        return "package_set:" + build["package_set"]
    return "inline:" + build["name"]


def apply_narrowing(
    lanes: list[dict[str, Any]], narrowing: dict[str, Any]
) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    if not narrowing:
        return lanes, None
    narrowed = lanes
    narrowed_by: dict[str, dict[str, list[str]]] = {}
    for axis, lane_key in (("compilers", "compiler"), ("gpu_selectors", "gpu_selector")):
        allowed = narrowing.get(axis)
        if not allowed:
            continue
        allowed_set = set(allowed)
        before = {lane[lane_key] for lane in narrowed if lane.get(lane_key)}
        narrowed = [
            lane for lane in narrowed if not lane.get(lane_key) or lane[lane_key] in allowed_set
        ]
        after = {lane[lane_key] for lane in narrowed if lane.get(lane_key)}
        dropped = sorted(before - after)
        if dropped:
            narrowed_by[axis] = {"kept": sorted(after), "dropped": dropped}
    if narrowing.get("mpi"):
        allowed_mpi = set(narrowing["mpi"])
        before_providers = {lane["mpi_provider"] for lane in narrowed if lane.get("mpi_provider")}
        narrowed = [
            lane
            for lane in narrowed
            if not lane.get("mpi_provider") or lane["mpi_provider"] in allowed_mpi
        ]
        after_providers = {lane["mpi_provider"] for lane in narrowed if lane.get("mpi_provider")}
        dropped = sorted(before_providers - after_providers)
        if dropped:
            narrowed_by["mpi"] = {"kept": sorted(after_providers), "dropped": dropped}
    if not narrowed_by:
        return narrowed, None
    return narrowed, {
        "dropped_lanes": sorted(
            {lane["name"] for lane in lanes} - {lane["name"] for lane in narrowed}
        ),
        "narrowed_by": narrowed_by,
    }
