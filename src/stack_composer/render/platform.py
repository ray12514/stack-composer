from __future__ import annotations

from typing import Any

from stack_composer.render.versioning import version_key

PLATFORM_SYSTEM_EXTERNALS = frozenset({"cray-libsci"})
DEFAULT_PLATFORM_RELEASE_SELECTOR = "latest"


def selected_system_externals(
    profile: dict[str, Any], stack: dict[str, Any]
) -> list[dict[str, Any]]:
    """Return system externals after platform-release selection.

    Cluster Inspector deliberately reports broad system facts. Stack Composer
    owns render-time selection. For platform-owned runtime packages where many
    installed generations may be visible, the default render policy keeps only
    the latest coherent package generation and reports the rest through the
    render plan.
    """
    del stack  # Future explicit platform-release policy will be read here.

    selected, _ignored = classify_system_externals(profile)
    return selected


def platform_plan(profile: dict[str, Any], stack: dict[str, Any]) -> dict[str, Any]:
    """Summarize platform-owned runtime selection."""
    del stack  # Future explicit platform-release policy will be read here.

    selected, ignored = classify_system_externals(profile)
    platform_selected = [
        plan_entry(item)
        for item in selected
        if is_platform_selected_external(profile, item)
    ]
    return {
        "family": platform_family(profile),
        "release_policy": {
            "selector": DEFAULT_PLATFORM_RELEASE_SELECTOR,
            "scope": "platform_system_externals",
        },
        "selected_system_externals": sorted(
            platform_selected,
            key=lambda item: (item["name"], item["version"], item["prefix"]),
        ),
        "ignored_system_externals": sorted(
            ignored,
            key=lambda item: (item["name"], item["version"], item["prefix"]),
        ),
    }


def classify_system_externals(
    profile: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    by_name: dict[str, list[dict[str, Any]]] = {}
    selected: list[dict[str, Any]] = []

    for item in profile.get("system_externals") or []:
        if is_platform_selected_external(profile, item):
            by_name.setdefault(str(item["name"]), []).append(item)
        else:
            selected.append(item)

    ignored: list[dict[str, Any]] = []
    for _name, entries in sorted(by_name.items()):
        latest = latest_version(entries)
        for item in entries:
            if str(item.get("version")) == latest:
                selected.append(item)
            else:
                ignored.append(
                    {
                        **plan_entry(item),
                        "reason": "older_than_selected_platform_version",
                        "selected_version": latest,
                    }
                )

    return selected, ignored


def is_platform_selected_external(profile: dict[str, Any], item: dict[str, Any]) -> bool:
    name = item.get("name")
    if name not in PLATFORM_SYSTEM_EXTERNALS:
        return False
    if item.get("provider_family") == "platform":
        return True
    return platform_family(profile) == "cray-pe" and str(name).startswith("cray-")


def platform_family(profile: dict[str, Any]) -> str | None:
    for provider in profile.get("compiler_providers") or []:
        family = provider.get("platform_family")
        if family:
            return str(family)
    system_family = (profile.get("system") or {}).get("family")
    if system_family and "cray" in str(system_family).lower():
        return "cray-pe"
    return None


def latest_version(items: list[dict[str, Any]]) -> str:
    versions = {str(item.get("version")) for item in items if item.get("version") is not None}
    if not versions:
        return ""
    return max(versions, key=version_key)


def plan_entry(item: dict[str, Any]) -> dict[str, Any]:
    entry = {
        "name": str(item.get("name")),
        "version": str(item.get("version")),
        "prefix": str(item.get("prefix")),
    }
    modules = item.get("modules") or []
    if modules:
        entry["modules"] = modules
    return entry
