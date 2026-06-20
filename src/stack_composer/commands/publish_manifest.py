from __future__ import annotations

from pathlib import Path

import click

from stack_composer.manifest.finalize import finalize_manifest


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
    try:
        finalize_manifest(
            workspace=Path(workspace),
            build_host_name=build_host,
            lockfiles_dir=Path(lockfiles),
            platform_module_prereqs_path=Path(platform_module_prereqs),
            buildcache_destinations_path=Path(buildcache_destinations),
            verify_results_path=Path(verify_results),
            force=force,
        )
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(str(Path(workspace) / "release-manifest.yaml"))
