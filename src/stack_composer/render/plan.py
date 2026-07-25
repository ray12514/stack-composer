from __future__ import annotations

from typing import Any

from stack_composer.errors import Issue
from stack_composer.render.gpu import build_gpu_plan
from stack_composer.render.mpi import (
    compiler_fragment_name_version,
    compiler_provider_ref,
    compiler_ref_axis,
    compiler_ref_name,
    compiler_ref_satisfies_flavor,
    compiler_version_matches,
    is_renderable_mpi_provider,
    mpi_toolchain_name_for_profile,
    select_compiler_provider,
    select_flavor_compiler,
    select_platform_mpi,
)
from stack_composer.render.spack_specs import is_renderable_external_name_version
from stack_composer.render.versioning import version_key
from stack_composer.resolve.build_kind import normalize_builds

# Conservative shared target for `target: baseline`.
_BASELINE_TARGET = "x86_64_v3"

# Reason codes that fail the whole plan even when the owning build is not
# required. These mark input-authoring defects (an ambiguous or nonexistent
# MPI version selection), not "this system lacks that lane" — silently
# skipping them would be as surprising as silently picking a version.
_HARD_REASON_CODES = {"mpi_ambiguous", "mpi_version_unresolved", "compiler_ambiguous"}


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
                f"per_system.{system_name} narrowing dropped every lane for build {build['name']!r}"
            )
        if build.get("required", False) or reason_code in _HARD_REASON_CODES:
            issues.append(
                Issue(
                    "error",
                    reason_code,
                    f"stack.builds.{build['name']}",
                    f"build {build['name']!r} cannot render: {reason}",
                )
            )
            continue
        skipped.append({"build": build["name"], "reason_code": reason_code, "reason": reason})

    skipped.sort(key=lambda entry: entry["build"])
    if not lanes:
        message = f"no stack builds can render for profile {system_name}"
        if skipped:
            details = "; ".join(
                f"{entry['build']}: {entry['reason_code']} — {entry['reason']}"
                for entry in skipped
            )
            message += f" (skipped: {details})"
        issues.append(Issue("error", "no-rendered-lanes", "stack.builds", message))
    issues.extend(gpu_toolkit_issues(profile, lanes))
    issues.extend(mpi_flavor_issues(profile, lanes))
    lanes.sort(key=lambda lane: (lane["compiler"], lane["lane"], lane["source_build"]))
    return lanes, skipped, applied_narrowing, issues


def mpi_flavor_issues(profile: dict[str, Any], lanes: list[dict[str, Any]]) -> list[Issue]:
    """Error when no MPI flavor on this system accepts the lane's compiler.

    A flavor-based provider (Cray PE cray-mpich) ships one build per compiler
    baseline. select_flavor_compiler drops a flavor the lane's compiler cannot
    satisfy, so a lane under every baseline would otherwise render with no MPI
    external at all, and Spack would then build the MPI from source rather than
    consume the platform's. HPE publishes a minimum supported compiler per
    release, so a compiler below every baseline is unsupported, not merely
    untested; that makes this an error and not a warning.
    """
    issues: list[Issue] = []
    seen: set[tuple[str, str, str]] = set()
    for lane in lanes:
        provider_name = lane.get("mpi_provider")
        if not provider_name or lane.get("mpi_source") != "platform":
            continue
        compiler_ref = str(lane.get("compiler_ref") or "")
        version = str(lane.get("mpi_version") or "")
        key = (compiler_ref, str(provider_name), version)
        if key in seen:
            continue
        seen.add(key)
        record = next(
            (
                provider
                for provider in profile.get("mpi_providers") or []
                if str(provider.get("name")) == str(provider_name)
                and str(provider.get("version") or "") == version
            ),
            None,
        )
        flavors = (record or {}).get("flavors") or {}
        if not flavors:
            continue
        # Mirror mpi_provider_externals exactly: a flavor survives only when
        # the lane's compiler ref satisfies its baseline AND the profile has a
        # compiler provider that satisfies it. Checking anything looser here
        # would report a lane healthy that renders without an MPI external.
        if any(
            compiler_ref_satisfies_flavor(compiler_ref, flavor, record)
            and select_flavor_compiler(profile, flavor, record) is not None
            for flavor in flavors
        ):
            continue
        baselines = ", ".join(sorted(flavors))
        # Name the compiler the profile actually reports, not just the lane's
        # ref: the ref is often a bare family name, and the operator needs the
        # version they have next to the baseline they need.
        family = compiler_ref_name(compiler_ref)
        present = ", ".join(
            sorted(
                f"{provider['name']}@{provider['version']}"
                for provider in profile.get("compiler_providers") or []
                if str(provider.get("name")) == family and provider.get("version")
            )
        )
        have = present or compiler_ref
        issues.append(
            Issue(
                "error",
                "mpi_flavor_compiler_unsupported",
                f"stack.builds.{lane['source_build']}",
                f"{provider_name} {version} on this system ships no flavor that accepts "
                f"compiler {compiler_ref} ({family} present: {have}); available flavor "
                f"baselines are {baselines}. Select a compiler that satisfies one of them, "
                f"or the lane would render with no {provider_name} external.",
            )
        )
    return issues


_GPU_ARCH_TOOLKITS = (("gfx", "rocm"), ("sm_", "cuda"))


def gpu_toolkit_issues(profile: dict[str, Any], lanes: list[dict[str, Any]]) -> list[Issue]:
    """Warn when a GPU lane will not get toolkit externals from the profile.

    Such a lane concretizes, then surprises at fetch time with Spack building
    the toolkit itself (Raider: cuda_12.9_linux.run). Building the toolkit is
    legitimate, so these are warnings, never errors.
    """
    issues: list[Issue] = []
    plan: dict[str, Any] | None = None
    seen: set[tuple[str, str]] = set()
    for lane in lanes:
        arch = str(lane.get("gpu_arch") or "")
        if not arch or (lane["name"], arch) in seen:
            continue
        seen.add((lane["name"], arch))
        path = f"stack.builds.{lane['name']}"
        toolkit = next(
            (toolkit for prefix, toolkit in _GPU_ARCH_TOOLKITS if arch.startswith(prefix)), None
        )
        if toolkit is None:
            issues.append(
                Issue(
                    "warning",
                    "gpu_arch_unrecognized",
                    path,
                    f"gpu build {lane['name']!r}: arch_target {arch!r} is neither "
                    f"gfx* nor sm_*; no GPU toolkit scope will be included",
                )
            )
            continue
        if plan is None:
            plan = build_gpu_plan(profile)
        if not plan.get(toolkit):
            issues.append(
                Issue(
                    "warning",
                    "gpu_toolkit_unavailable",
                    path,
                    f"gpu build {lane['name']!r} ({arch}): profile reports no usable "
                    f"{toolkit} toolkit under gpu_toolkit_modules; Spack will build "
                    f"{toolkit} from source",
                )
            )
    return issues


def lane_candidates_for_build(
    profile: dict[str, Any], stack: dict[str, Any], build: dict[str, Any]
) -> tuple[list[dict[str, Any]], str, str]:
    """Resolve one build into lanes = selected compilers × (mpi provider, for
    mpi/gpu) × (gpu arch, for gpu). Everything is read from the merged site
    defaults, overridable per build, resolved against the profile."""
    kind = build.get("kind") or "serial"
    want_gpu = kind == "gpu"
    node_types = runtime_nodes(profile, want_gpu)
    if not node_types:
        which = "GPU" if want_gpu else "CPU"
        return [], "nodes_unmatched", f"profile has no runtime {which} node type"

    compilers, missing, explicit, compiler_error = resolve_compilers(profile, stack, build)
    if compiler_error:
        return [], compiler_error["code"], compiler_error["message"]
    if missing:
        return (
            [],
            "compiler_unavailable",
            f"requested compiler(s) not reported by profile: {', '.join(missing)}",
        )
    if not compilers:
        return [], "compiler_unavailable", "profile reports no compilers to build with"

    mpi_provider, mpi_source, mpi_record = (None, None, None)
    if kind in ("mpi", "gpu"):
        mpi_provider, mpi_source = resolve_mpi(profile, stack, build)
        if not mpi_provider:
            return (
                [],
                "mpi_unresolved",
                f"{kind} build needs an MPI provider; set defaults.mpi.provider",
            )
        if mpi_source == "platform":
            mpi_config = build.get("mpi") or stack.get("mpi") or {}
            requested_version = mpi_config.get("version") if isinstance(mpi_config, dict) else None
            # version_policy is site policy: it comes from the merged defaults,
            # never from a per-build override (those pin exact versions).
            stack_mpi = stack.get("mpi")
            version_policy = (
                stack_mpi.get("version_policy") if isinstance(stack_mpi, dict) else None
            )
            mpi_record, error_code, error = select_platform_mpi(
                profile, mpi_provider, requested_version, version_policy
            )
            if error_code:
                return [], error_code, error
        # Auto-narrow a default (non-explicit) compiler set to those the chosen
        # platform MPI was actually built against. An explicit compiler list is
        # honored as-is (a missing platform flavor then errors, or use source:build).
        if mpi_source == "platform" and not explicit:
            compatible = mpi_compatible_compilers(mpi_record)
            if compatible:
                narrowed = [
                    c
                    for c in compilers
                    if any(compiler_ref_matches(c, compat, mpi_record) for compat in compatible)
                ]
                if not narrowed:
                    narrowed, _missing, error = resolve_compiler_refs(profile, sorted(compatible))
                    if error:
                        return [], error["code"], error["message"]
                compilers = narrowed
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
                        profile,
                        stack,
                        build,
                        kind,
                        compiler,
                        mpi_provider,
                        mpi_source,
                        mpi_record,
                        target_for(target_policy, node),
                        node_name,
                        arch,
                    )
                )
    else:
        node_name, node = node_types[0]
        target = target_for(target_policy, node)
        for compiler in compilers:
            lanes.append(
                make_lane(
                    profile,
                    stack,
                    build,
                    kind,
                    compiler,
                    mpi_provider,
                    mpi_source,
                    mpi_record,
                    target,
                    node_name,
                    None,
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
        if not is_renderable_external_name_version(name, provider.get("version")):
            continue
        if name and name not in found:
            found.append(name)
    return found


def renderable_compiler_providers(profile: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        provider
        for provider in profile.get("compiler_providers") or []
        if is_renderable_external_name_version(provider.get("name"), provider.get("version"))
    ]


def resolve_compilers(
    profile: dict[str, Any], stack: dict[str, Any], build: dict[str, Any]
) -> tuple[list[str], list[str], bool, dict[str, str] | None]:
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
            candidates = compiler_provider_candidates(profile, "gcc")
            if len(candidates) > 1:
                return (
                    [compiler_provider_ref(preferred_baseline_compiler_provider(candidates))],
                    [],
                    False,
                    None,
                )
            refs, missing, error = resolve_compiler_refs(profile, ["gcc"])
            return refs, missing, False, error
        if not available:
            return [], [], False, None
        refs, missing, error = resolve_compiler_refs(profile, [available[0]])
        return refs, missing, False, error
    if selection == "all":
        duplicate_names = compiler_duplicate_names(profile)
        return (
            [
                compiler_provider_ref(provider)
                if provider["name"] in duplicate_names
                else str(provider["name"])
                for provider in renderable_compiler_providers(profile)
            ],
            [],
            False,
            None,
        )
    selected, missing, error = resolve_compiler_refs(profile, selection)
    return selected, missing, True, error


def resolve_compiler_refs(
    profile: dict[str, Any], selection: list[str]
) -> tuple[list[str], list[str], dict[str, str] | None]:
    selected: list[str] = []
    missing: list[str] = []
    for requested in selection:
        candidates = compiler_provider_candidates(profile, requested)
        if not candidates:
            missing.append(requested)
            continue
        requested_name, requested_version = compiler_fragment_name_version(requested)
        if len(candidates) > 1:
            available = ", ".join(
                sorted(compiler_provider_ref(provider) for provider in candidates)
            )
            return (
                [],
                [],
                {
                    "code": "compiler_ambiguous",
                    "message": (
                        f"compiler {requested!r} is ambiguous: the profile reports "
                        f"{available}; set compilers to an exact version such as "
                        f"{compiler_provider_ref(candidates[0])}"
                    ),
                },
            )
        selected.append(
            compiler_provider_ref(candidates[0]) if requested_version else requested_name
        )
    return selected, missing, None


def compiler_duplicate_names(profile: dict[str, Any]) -> set[str]:
    counts: dict[str, int] = {}
    for provider in renderable_compiler_providers(profile):
        counts[str(provider["name"])] = counts.get(str(provider["name"]), 0) + 1
    return {name for name, count in counts.items() if count > 1}


def compiler_provider_candidates(profile: dict[str, Any], requested: str) -> list[dict[str, Any]]:
    requested_name, requested_version = compiler_fragment_name_version(requested)
    candidates = [
        provider
        for provider in renderable_compiler_providers(profile)
        if provider.get("name") == requested_name
    ]
    if requested_version:
        return [
            provider
            for provider in candidates
            if compiler_version_matches(str(provider.get("version")), requested_version)
        ]
    return candidates


def preferred_baseline_compiler_provider(candidates: list[dict[str, Any]]) -> dict[str, Any]:
    """Pick a deterministic lean default from duplicate same-name compilers.

    `baseline` is policy, not an explicit user request. Prefer the platform
    provider when the profile has one, otherwise site, otherwise system; within
    each bucket choose the newest version.
    """
    family_rank = {"platform": 3, "site": 2, "system": 1}
    return max(
        candidates,
        key=lambda provider: (
            family_rank.get(str(provider.get("provider_family")), 0),
            version_key(str(provider.get("version", ""))),
        ),
    )


def compiler_ref_matches(
    compiler: str, compatible: str, provider: dict[str, Any] | None = None
) -> bool:
    return compiler_ref_satisfies_flavor(compiler, compatible, provider)


def mpi_compatible_compilers(provider: dict[str, Any] | None) -> set[str]:
    """Compilers the selected platform MPI was built against: its declared
    compatibility list plus any per-compiler flavor keys. Works on the one
    record select_platform_mpi already resolved — never re-searches by name,
    so an unrelated same-name entry can't contribute its compatibility."""
    if not provider:
        return set()
    if provider.get("flavors"):
        return set(provider.get("flavors") or {})
    compatible = set((provider.get("compatibility") or {}).get("compilers") or [])
    if provider.get("compiler"):
        compatible.add(str(provider["compiler"]))
    return compatible


def compiler_provider_metadata(profile: dict[str, Any], compiler_name: str) -> dict[str, Any]:
    return select_compiler_provider(profile, compiler_name) or {}


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
    providers = [
        provider
        for provider in profile.get("mpi_providers") or []
        if is_renderable_mpi_provider(provider)
    ]
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
        # The policy-named provider (defaults.mpi.provider) is a preference:
        # when the profile reports it, it beats profile order; when it does
        # not, auto falls back to whatever MPI the system has.
        requested_reported = None
        if requested:
            requested_reported = next(
                (
                    provider.get("name")
                    for provider in providers
                    if provider.get("name") == requested
                ),
                None,
            )
        platform_provider = requested_reported or (
            prioritized[0] if prioritized else providers[0]
        ).get("name")
        if explicit_requested:
            requested_provider = requested_reported
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
    mpi_record: dict[str, Any] | None,
    target: str,
    node_name: str,
    gpu_arch: str | None,
) -> dict[str, Any]:
    # Key the lane on the build name so two builds of the same kind (e.g. two
    # cpu builds) never collide; the env template is still chosen by kind.
    lane_suffix = build["name"]
    compiler_name = compiler_ref_name(compiler)
    compiler_axis = compiler_ref_axis(compiler)
    if mpi_provider:
        lane_suffix += "-" + mpi_provider.replace("-", "")
    if gpu_arch:
        lane_suffix += "-" + gpu_arch
    name = f"{compiler_axis}-{lane_suffix}"
    return {
        "name": name,
        "source_build": build["name"],
        "compiler": compiler_name,
        "compiler_ref": compiler,
        "compiler_axis": compiler_axis,
        "compiler_version": compiler_fragment_name_version(compiler)[1],
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
        "mpi_version": mpi_record.get("version") if mpi_record else None,
        "toolchain": toolchain_for(profile, compiler, mpi_provider, mpi_record),
        "env_path": f"environments/{compiler_axis}/{lane_suffix}",
        "spec_source": spec_source_id(build),
    }


def toolchain_for(
    profile: dict[str, Any],
    compiler: str,
    mpi_provider: str | None,
    mpi_record: dict[str, Any] | None,
) -> str | None:
    if not mpi_provider:
        return None
    mpi_version = str(mpi_record["version"]) if mpi_record and mpi_record.get("version") else None
    return mpi_toolchain_name_for_profile(profile, compiler, mpi_provider, mpi_version)


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
