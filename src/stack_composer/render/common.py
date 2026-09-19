"""Resolved common-scope selection, computed once so templates only print.

The common Spack scope carries the workspace-wide externals (fabric userspace +
policy-allowed system externals), the default MPI provider preference, and the
target preference. Those decisions used to run inside the common template
(the `common_external_packages` global plus inline `rendered_lanes` filtering).
This module makes them once so the template becomes a dumb printer.
"""

from __future__ import annotations

import posixpath
from typing import Any

from stack_composer.render.repositories import repository_output_parts
from stack_composer.render.scopes import common_external_packages


def build_common_plan(
    profile: dict[str, Any],
    stack: dict[str, Any],
    rendered_lanes: list[dict[str, Any]],
    package_repos: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Resolve the common scope's externals, default MPI provider, target,
    and repos mapping.

    `default_mpi_provider` uses the first rendered lane's provider. Keeping
    that rule here makes it visible and testable.
    """
    lane_providers = [
        lane["mpi_provider"] for lane in rendered_lanes if lane.get("mpi_provider")
    ]
    return {
        "externals": common_external_packages(profile, stack),
        "default_mpi_provider": lane_providers[0] if lane_providers else None,
        "target_prefer": rendered_lanes[0]["target"] if rendered_lanes else None,
        "repos": repos_mapping(stack, package_repos or []),
        # Foundation single-version is enforced here, in the lock, not
        # assumed: every concretization in every lane resolves the pinned
        # version whether the package is a root or a dependency.
        "foundation_pins": [
            {"name": name, "version": str(version)}
            for name, version in sorted((stack.get("foundation_pins") or {}).items())
        ],
    }


def repos_mapping(
    stack: dict[str, Any], package_repos: list[dict[str, Any]]
) -> dict[str, Any]:
    """repos.yaml content, fully decided: the builtin recipe-generation pin
    from declared policy (spack.package_repo) plus local package repositories
    as named path entries in priority order, preserving authored order within
    each priority. Always a complete mapping — empty when nothing is declared
    — so the template prints it verbatim."""
    repos: dict[str, Any] = {
        str(repo["name"]): posixpath.join(
            "..", "..", "package-repos", *repository_output_parts(repo)
        )
        for repo in package_repos
        if repo["priority"] == "before_builtin"
    }
    spack_cfg = stack.get("spack")
    pin = spack_cfg.get("package_repo") if isinstance(spack_cfg, dict) else None
    if pin:
        repos["builtin"] = {
            key: pin[key] for key in ("git", "tag", "commit", "branch") if pin.get(key)
        }
    for repo in package_repos:
        if repo["priority"] == "after_builtin":
            repos[str(repo["name"])] = posixpath.join(
                "..", "..", "package-repos", *repository_output_parts(repo)
            )
    return repos
