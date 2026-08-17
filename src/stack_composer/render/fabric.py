from __future__ import annotations

from typing import Any

from stack_composer.render.platform import selected_system_externals
from stack_composer.render.versioning import version_key

DEFAULT_COMMON_SCOPE_FABRIC_EXTERNALS = frozenset({"libfabric", "ucx"})


def observed_fabric_userspace(profile: dict[str, Any]) -> list[dict[str, Any]]:
    """Return renderable fabric/runtime facts observed by Cluster Inspector."""
    observed: list[dict[str, Any]] = []
    for item in (profile.get("fabric") or {}).get("userspace") or []:
        name = item.get("name")
        version = item.get("version")
        prefix = item.get("prefix")
        if not (name and version and prefix):
            continue
        observed.append(
            {
                "name": name,
                "version": str(version),
                "prefix": prefix,
                "modules": item.get("modules") or [],
            }
        )
    return sorted(
        observed,
        key=lambda item: (
            str(item["name"]),
            str(item["version"]),
            str(item["prefix"]),
        ),
    )


def selected_build_fabric_externals(
    profile: dict[str, Any], stack: dict[str, Any]
) -> list[dict[str, Any]]:
    """Return development-verified fabric externals selected for builds.

    ``fabric.userspace`` is observational. Only ``system_externals`` carries
    the development-surface evidence required to place a package in
    ``packages.yaml`` for a source build.
    """
    policy = stack.get("externals") or {}
    return sorted(
        [
            item
            for item in selected_system_externals(profile, stack)
            if item.get("name") in DEFAULT_COMMON_SCOPE_FABRIC_EXTERNALS
            and policy.get(str(item.get("name"))) == "system"
        ],
        key=lambda item: (
            str(item.get("name") or ""),
            str(item.get("version") or ""),
            str(item.get("prefix") or ""),
        ),
    )


def selected_platform_runtime_userspace(
    profile: dict[str, Any],
    *,
    allowed_names: set[str] | frozenset[str],
) -> list[dict[str, Any]]:
    """Select observed runtimes needed by one external platform MPI.

    Cluster Inspector may report Cray runtime facts such as GTL, PMI, and PALS.
    This selection is intentionally separate from build externals: an external
    platform MPI may need an observed runtime from its own product tree, while
    a source build requires a development-verified ``system_externals`` fact.
    """
    by_name: dict[str, list[dict[str, Any]]] = {}
    for item in observed_fabric_userspace(profile):
        if item["name"] not in allowed_names:
            continue
        by_name.setdefault(item["name"], []).append(item)

    selected: list[dict[str, Any]] = []
    for _name, entries in sorted(by_name.items()):
        ranked = sorted(
            entries,
            key=lambda entry: version_key(str(entry.get("version") or "")),
            reverse=True,
        )
        ranked.sort(key=lambda entry: fabric_userspace_sort_key(profile, entry))
        selected.extend(ranked[:1])
    return selected


def unselected_fabric_userspace(
    profile: dict[str, Any],
    selected: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    selected_keys = {
        (item["name"], item["version"], item["prefix"])
        for item in selected
    }
    out: list[dict[str, Any]] = []
    for item in observed_fabric_userspace(profile):
        if (item["name"], item["version"], item["prefix"]) in selected_keys:
            continue
        reason = "observation_not_selected_as_platform_mpi_runtime"
        if item["name"] not in DEFAULT_COMMON_SCOPE_FABRIC_EXTERNALS:
            reason = "requires_explicit_package_repo_policy"
        out.append({**item, "reason": reason})
    return out


def fabric_userspace_sort_key(profile: dict[str, Any], entry: dict[str, Any]) -> tuple[int, str]:
    prefix = entry.get("prefix", "")
    is_cray_platform = (
        (profile.get("fabric") or {}).get("type") == "slingshot"
        and prefix.startswith("/opt/cray/")
    )
    return (0 if is_cray_platform else 1, entry.get("name", ""))
