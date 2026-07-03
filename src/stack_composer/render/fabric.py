from __future__ import annotations

from typing import Any

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


def selected_common_scope_fabric_userspace(
    profile: dict[str, Any],
    mode: str,
    *,
    allowed_names: set[str] | frozenset[str] = DEFAULT_COMMON_SCOPE_FABRIC_EXTERNALS,
) -> list[dict[str, Any]]:
    """Select fabric userspace facts safe to emit in the common Spack scope.

    Cluster Inspector may report Cray runtime facts such as GTL, PMI, and PALS.
    Those are useful for the network plan, but they should not be rendered as
    Spack package externals unless the stack also ships the package repo policy
    that defines those packages. The default common scope remains conservative.
    """
    if mode not in {"prefer_platform", "mixed"}:
        return []

    by_name: dict[str, list[dict[str, Any]]] = {}
    for item in observed_fabric_userspace(profile):
        if item["name"] not in allowed_names:
            continue
        by_name.setdefault(item["name"], []).append(item)

    selected: list[dict[str, Any]] = []
    for _name, entries in sorted(by_name.items()):
        ranked = sorted(entries, key=lambda entry: fabric_userspace_sort_key(profile, entry))
        selected.extend(ranked if mode == "mixed" else ranked[:1])
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
        reason = "not_selected_by_policy"
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
