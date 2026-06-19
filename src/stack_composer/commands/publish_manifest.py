from __future__ import annotations

from stack_composer.commands._stub import raise_not_implemented


def run(
    *,
    workspace: str,
    build_host: str,
    lockfiles: str,
    platform_module_prereqs: str,
    buildcache_destinations: str,
    verify_results: str,
    force: bool,
) -> None:
    _ = (
        workspace,
        build_host,
        lockfiles,
        platform_module_prereqs,
        buildcache_destinations,
        verify_results,
        force,
    )
    raise_not_implemented("publish-manifest")
