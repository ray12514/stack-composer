from __future__ import annotations

from typing import Any

from stack_composer.errors import Issue
from stack_composer.resolve.build_kind import normalize_builds

# Conservative shared target for `target: baseline`.
_BASELINE_TARGET = "x86_64_v3"


def plan_lanes(
    profile: dict[str, Any], stack: dict[str, Any]
) -> tuple[list[dict[str, Any]], list[dict[str, str]], dict[str, Any] | None, list[Issue]]:
    issues: list[Issue] = []
    lanes: list[dict[str, Any]] = []
    skipped: list[dict[str, str]] = []
    applied_narrowing = None
    stack = normalize_builds(stack)
    system_name = profile["system"]["name"]
    narrowing = ((stack.get("per_system") or {}).get(system_name) or {}).get("builds") or {}

    for build in stack.get("builds", []):
        candidates, reason_code, reason = lane_candidates_for_build(profile, stack, build)
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
    profile: dict[str, Any], stack: dict[str, Any], build: dict[str, Any]
) -> tuple[list[dict[str, Any]], str, str]:
    """Resolve one build into lanes = selected compilers × (mpi provider, for
    mpi/gpu) × (gpu arch, for gpu). Everything is read from the merged site
    defaults, overridable per build, resolved against the profile."""
    kind = build.get("kind") or "cpu"
    want_gpu = kind == "gpu"
    node_types = runtime_nodes(profile, want_gpu)
    if not node_types:
        which = "GPU" if want_gpu else "CPU"
        return [], "nodes_unmatched", f"profile has no runtime {which} node type"

    compilers, missing, explicit = resolve_compilers(profile, stack, build)
    if missing:
        return (
            [],
            "compiler_unavailable",
            f"requested compiler(s) not reported by profile: {', '.join(missing)}",
        )
    if not compilers:
        return [], "compiler_unavailable", "profile reports no compilers to build with"

    mpi_provider, mpi_source = (None, None)
    if kind in ("mpi", "gpu"):
        mpi_provider, mpi_source = resolve_mpi(profile, stack, build)
        if not mpi_provider:
            return (
                [],
                "mpi_unresolved",
                f"{kind} build needs an MPI provider; set defaults.mpi.provider",
            )
        # Auto-narrow a default (non-explicit) compiler set to those the chosen
        # platform MPI was actually built against. An explicit compiler list is
        # honored as-is (a missing platform flavor then errors, or use source:build).
        if mpi_source == "platform" and not explicit:
            compatible = mpi_compatible_compilers(profile, mpi_provider)
            if compatible:
                compilers = [c for c in compilers if c in compatible]
                if not compilers:
                    return (
                        [],
                        "compiler_unavailable",
                        f"no default compiler is compatible with platform MPI {mpi_provider!r}",
                    )

    target_policy = build.get("target") or stack.get("target") or "native"
    lanes: list[dict[str, Any]] = []
    if want_gpu:
        selected, missing_archs = resolve_gpu_archs(profile, stack, build, node_types)
        if missing_archs:
            return (
                [],
                "gpu_unavailable",
                f"requested GPU arch(es) not on this system: {', '.join(missing_archs)}",
            )
        if not selected:
            return [], "gpu_unavailable", "gpu build but the profile reports no GPU arch"
        selected_set = set(selected)
        # One lane per (compiler, gpu node); the lane's target follows its node.
        for compiler in compilers:
            for node_name, node in node_types:
                arch = (node.get("gpu") or {}).get("arch_target")
                if arch not in selected_set:
                    continue
                lanes.append(
                    make_lane(
                        profile, stack, build, kind, compiler,
                        mpi_provider, mpi_source, target_for(target_policy, node),
                        node_name, arch,
                    )
                )
    else:
        node_name, node = node_types[0]
        target = target_for(target_policy, node)
        for compiler in compilers:
            lanes.append(
                make_lane(
                    profile, stack, build, kind, compiler,
                    mpi_provider, mpi_source, target, node_name, None,
                )
            )
    return lanes, "no_candidates", "no lane candidates produced"


def runtime_nodes(profile: dict[str, Any], want_gpu: bool) -> list[tuple[str, dict[str, Any]]]:
    matches: list[tuple[str, dict[str, Any]]] = []
    for name, node in sorted(profile.get("node_types", {}).items()):
        if node.get("role") not in {"runtime", "both"}:
            continue
        has_gpu = node.get("gpu") is not None
        if want_gpu and has_gpu:
            matches.append((name, node))
        elif not want_gpu and not has_gpu:
            matches.append((name, node))
    return matches


def profile_compilers(profile: dict[str, Any]) -> list[str]:
    """Compiler names the profile reports, in profile order (deduped). Reads the
    generic compiler_providers inventory — any provider family, no hardcoded
    list, so a new CPE compiler is picked up automatically."""
    found: list[str] = []
    for provider in profile.get("compiler_providers") or []:
        name = provider.get("name")
        if name and name not in found:
            found.append(name)
    return found


def resolve_compilers(
    profile: dict[str, Any], stack: dict[str, Any], build: dict[str, Any]
) -> tuple[list[str], list[str], bool]:
    """Return (selected_compilers, missing, explicit). Selection = per-build
    override, else site default, else 'baseline'.

    - 'baseline' (lean default): gcc if the profile reports it, else the first
      reported compiler. Power users opt into more.
    - 'all': every reported compiler (fan-out).
    - a list: intersected with the profile; absent names reported as missing.

    explicit is True only for a list — it suppresses MPI auto-narrowing so an
    explicit compiler choice is honored verbatim."""
    available = profile_compilers(profile)
    selection = build.get("compilers") or stack.get("compilers") or "baseline"
    if selection == "baseline":
        if "gcc" in available:
            return ["gcc"], [], False
        return available[:1], [], False
    if selection == "all":
        return available, [], False
    selected_set = {name for name in selection if name in set(available)}
    missing = [name for name in selection if name not in set(available)]
    selected = [name for name in available if name in selected_set]
    return selected, missing, True


def mpi_compatible_compilers(profile: dict[str, Any], provider_name: str) -> set[str]:
    """Compilers a platform MPI provider was built against: its declared
    compatibility list plus any per-compiler flavor keys."""
    for provider in profile.get("mpi_providers") or []:
        if provider.get("name") == provider_name:
            compatible = set((provider.get("compatibility") or {}).get("compilers") or [])
            compatible |= set((provider.get("flavors") or {}).keys())
            return compatible
    return set()


def compiler_provider_metadata(profile: dict[str, Any], compiler_name: str) -> dict[str, Any]:
    for provider in profile.get("compiler_providers") or []:
        if provider.get("name") == compiler_name:
            return provider
    return {}


def vendor_scope_for(profile: dict[str, Any], stack: dict[str, Any], compiler_name: str) -> str:
    """Choose the compiler externals scope from provider metadata.

    The template defaults own provider-family-to-scope policy. This keeps
    provider-specific scopes as data-driven adapters instead of hardcoded vendor
    branches in the lane planner.
    """
    return vendor_scope_for_provider(stack, compiler_provider_metadata(profile, compiler_name))


def vendor_scope_for_provider(stack: dict[str, Any], provider: dict[str, Any]) -> str:
    scope_policy = (stack.get("provider_scopes") or {}).get("compiler") or {}
    default_scope = scope_policy.get("default", "vendor/linux")
    if not provider:
        return default_scope
    platform_family = provider.get("platform_family")
    if platform_family:
        platform_scope = (scope_policy.get("platform_families") or {}).get(platform_family)
        if platform_scope:
            return platform_scope
    family = provider.get("provider_family")
    if family:
        return (scope_policy.get("families") or {}).get(family, default_scope)
    return default_scope


def resolve_mpi(
    profile: dict[str, Any], stack: dict[str, Any], build: dict[str, Any]
) -> tuple[str | None, str]:
    """Resolve (provider, source). source policy:
      - auto (default): use the platform MPI the profile reports if any, else
        build the requested provider from source;
      - platform: use the platform MPI (falls back to requested);
      - build: build the requested provider regardless.
    The requested provider comes from the per-build override or defaults.mpi."""
    build_mpi = build.get("mpi")
    mpi = build_mpi or stack.get("mpi") or {}
    if not isinstance(mpi, dict):
        mpi = {}
    requested = mpi.get("provider")
    explicit_requested = requested if isinstance(build_mpi, dict) else None
    source = mpi.get("source", "auto")
    # Platform MPI = an mpi_provider the profile reports. Profile order is the
    # default priority; templates may supply a provider-family priority list.
    providers = profile.get("mpi_providers") or []
    platform_provider = None
    requested_provider = None
    if providers:
        priority = mpi.get("provider_family_priority") or []
        prioritized = [
            provider
            for family in priority
            for provider in providers
            if provider.get("provider_family") == family
        ]
        platform_provider = (prioritized[0] if prioritized else providers[0]).get("name")
        if explicit_requested:
            requested_provider = next(
                (
                    provider.get("name")
                    for provider in providers
                    if provider.get("name") == explicit_requested
                ),
                None,
            )
    if source == "build":
        return requested, "build"
    if source == "platform":
        return (
            requested_provider or platform_provider or explicit_requested or requested,
            "platform",
        )
    if explicit_requested:
        if requested_provider:
            return requested_provider, "platform"
        return explicit_requested, "build"
    if platform_provider:
        return platform_provider, "platform"
    return requested, "build"


def resolve_gpu_archs(
    profile: dict[str, Any],
    stack: dict[str, Any],
    build: dict[str, Any],
    node_types: list[tuple[str, dict[str, Any]]],
) -> tuple[list[str], list[str]]:
    available = sorted(
        {
            (node.get("gpu") or {}).get("arch_target")
            for _, node in node_types
            if (node.get("gpu") or {}).get("arch_target")
        }
    )
    gpu_block = build.get("gpu") or stack.get("gpu") or {}
    selection = gpu_block.get("archs", "all") if isinstance(gpu_block, dict) else "all"
    if selection == "all":
        return available, []
    selected = [a for a in available if a in set(selection)]
    missing = [a for a in selection if a not in set(available)]
    return selected, missing


def target_for(policy: str, node: dict[str, Any]) -> str:
    """Resolve a lane's CPU target: native = the node's preferred uarch;
    baseline = the conservative shared target; anything else = explicit."""
    if policy == "native":
        return node["cpu"]["preferred"]
    if policy == "baseline":
        return _BASELINE_TARGET
    return policy


def make_lane(
    profile: dict[str, Any],
    stack: dict[str, Any],
    build: dict[str, Any],
    kind: str,
    compiler: str,
    mpi_provider: str | None,
    mpi_source: str | None,
    target: str,
    node_name: str,
    gpu_arch: str | None,
) -> dict[str, Any]:
    # Key the lane on the build name so two builds of the same kind (e.g. two
    # cpu builds) never collide; the env template is still chosen by kind.
    lane_suffix = build["name"]
    if mpi_provider:
        lane_suffix += "-" + mpi_provider.replace("-", "")
    if gpu_arch:
        lane_suffix += "-" + gpu_arch
    name = f"{compiler}-{lane_suffix}"
    return {
        "name": name,
        "source_build": build["name"],
        "compiler": compiler,
        "vendor_scope": vendor_scope_for(profile, stack, compiler),
        "lane": lane_suffix,
        "kind": kind,
        "package_set": build.get("package_set"),
        "target": target,
        "runtime_node_type": node_name,
        "gpu_selector": gpu_arch,
        "gpu_arch": gpu_arch,
        "mpi_provider": mpi_provider,
        "mpi_source": mpi_source,
        "env_path": f"environments/{compiler}/{lane_suffix}",
        "spec_source": spec_source_id(build),
    }


def spec_source_id(build: dict[str, Any]) -> str:
    if build.get("package_set"):
        return "package_set:" + build["package_set"]
    return "inline:" + build["name"]


def apply_narrowing(
    lanes: list[dict[str, Any]], narrowing: dict[str, Any]
) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    """Subset-narrow resolved lanes by compiler / gpu arch / mpi provider."""
    if not narrowing:
        return lanes, None
    narrowed = lanes
    narrowed_by: dict[str, dict[str, list[str]]] = {}
    for axis, lane_key in (("compilers", "compiler"), ("gpu_archs", "gpu_arch")):
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
