from __future__ import annotations

import click

from stack_composer import __version__
from stack_composer.commands import (
    init_workspace as init_workspace_command,
)
from stack_composer.commands import (
    publish_manifest as publish_manifest_command,
)
from stack_composer.commands import (
    publish_static as publish_static_command,
)
from stack_composer.commands import (
    render as render_command,
)
from stack_composer.commands import (
    render_static as render_static_command,
)
from stack_composer.commands import (
    show as show_command,
)
from stack_composer.commands import (
    validate as validate_command,
)
from stack_composer.commands import (
    validate_template_set as validate_template_set_command,
)
from stack_composer.commands._stub import command_error_handler
from stack_composer.commands.licenses import print_licenses
from stack_composer.errors import ValidationFailed, format_issues


@click.group(context_settings={"help_option_names": ["-h", "--help"]}, invoke_without_command=True)
@click.version_option(__version__, prog_name="stack-composer")
@click.option("--licenses", "show_licenses", is_flag=True, help="Print bundled license metadata.")
@click.pass_context
def cli(ctx: click.Context, show_licenses: bool) -> None:
    """Render, publish, and validate declarative Spack stack artifacts."""
    if show_licenses:
        print_licenses()
        ctx.exit(0)


@cli.command("show")
@click.option("--profile", required=True, help="profile.yaml path.")
@click.option("--templates", help="Templates root; used with --template-set to load defaults.")
@click.option("--template-set", "template_set_name", help="Template-set name under --templates.")
@click.option("--defaults", "defaults_path", help="explicit defaults.yaml path.")
@click.option("--stack", "stack_path", help="Optional stack.yaml; recomputes the lanes for it.")
@command_error_handler
def show(
    profile: str,
    templates: str | None,
    template_set_name: str | None,
    defaults_path: str | None,
    stack_path: str | None,
) -> None:
    show_command.run(
        profile=profile,
        templates=templates,
        template_set_name=template_set_name,
        defaults_path=defaults_path,
        stack_path=stack_path,
    )


@cli.command("validate-template-set")
@click.option("--templates", required=True, help="Single template set directory under test.")
@click.option("--profiles", multiple=True, required=True, help="Profile glob; may be repeated.")
@click.option(
    "--smoke-stack",
    required=True,
    help="Smoke stack.yaml exercising the template set's lane kinds.",
)
@click.option("--package-sets-dir", required=True, help="Package sets root directory.")
@click.option("--package-repos-dir", required=True, help="Package repositories root directory.")
@click.option("--output", required=True, help="Report directory.")
@click.option("--concretize", is_flag=True, help="Optionally run spack concretize if available.")
@command_error_handler
def validate_template_set(
    templates: str,
    profiles: tuple[str, ...],
    smoke_stack: str,
    package_sets_dir: str,
    package_repos_dir: str,
    output: str,
    concretize: bool,
) -> None:
    validate_template_set_command.run(
        templates=templates,
        profiles=profiles,
        smoke_stack=smoke_stack,
        package_sets_dir=package_sets_dir,
        package_repos_dir=package_repos_dir,
        output=output,
        concretize=concretize,
    )


@cli.command("render")
@click.option("--profile", required=True, help="profile.yaml path.")
@click.option("--deployment", required=True, help="deployment.yaml path.")
@click.option("--stack", required=True, help="stack.yaml path.")
@click.option("--templates", required=True, help="Root directory containing template sets.")
@click.option("--output-root", required=True, help="Rendered workspace output root.")
@click.option("--release", required=True, help="Release tag, e.g. 2026.06.")
@click.option("--rendered-at", required=True, help="Explicit UTC render timestamp.")
@click.option("--source-repo", required=True, help="Stack source repository URL or identifier.")
@click.option("--source-commit", required=True, help="Stack source commit hex digest.")
@click.option("--source-dirty", is_flag=True, help="Record source tree as dirty.")
@click.option("--overwrite", is_flag=True, help="Replace an existing workspace path.")
@click.option("--package-sets", help="Package-set directory; defaults next to stack source.")
@click.option(
    "--package-repos", help="Package-repository directory; defaults next to stack source."
)
def render(
    profile: str,
    deployment: str,
    stack: str,
    templates: str,
    output_root: str,
    release: str,
    rendered_at: str,
    source_repo: str,
    source_commit: str,
    source_dirty: bool,
    overwrite: bool,
    package_sets: str | None,
    package_repos: str | None,
) -> None:
    render_command.run(
        profile=profile,
        deployment=deployment,
        stack=stack,
        templates=templates,
        output_root=output_root,
        release=release,
        rendered_at=rendered_at,
        source_repo=source_repo,
        source_commit=source_commit,
        source_dirty=source_dirty,
        overwrite=overwrite,
        package_sets=package_sets,
        package_repos=package_repos,
    )


@cli.command("render-static")
@click.option("--profile", required=True, help="profile.yaml path.")
@click.option("--templates", required=True, help="Root directory containing template sets.")
@click.option("--template-set", "template_set_name", default="v6", show_default=True)
@click.option("--output-root", required=True, help="Static catalog output root.")
@click.option("--release", required=True, help="Static catalog release tag.")
@click.option("--rendered-at", required=True, help="Explicit UTC render timestamp.")
@click.option("--source-repo", required=True, help="Source repository URL or identifier.")
@click.option("--source-commit", required=True, help="Source commit hex digest.")
@click.option("--source-dirty", is_flag=True, help="Record source tree as dirty.")
@click.option("--overwrite", is_flag=True, help="Replace an existing static catalog path.")
def render_static(
    profile: str,
    templates: str,
    template_set_name: str,
    output_root: str,
    release: str,
    rendered_at: str,
    source_repo: str,
    source_commit: str,
    source_dirty: bool,
    overwrite: bool,
) -> None:
    render_static_command.run(
        profile=profile,
        templates=templates,
        template_set_name=template_set_name,
        output_root=output_root,
        release=release,
        rendered_at=rendered_at,
        source_repo=source_repo,
        source_commit=source_commit,
        source_dirty=source_dirty,
        overwrite=overwrite,
    )


@cli.command("publish-static")
@click.option("--catalog", required=True, help="Reviewed static catalog directory.")
@click.option("--output-root", required=True, help="Published static catalog output root.")
@click.option("--published-at", required=True, help="Explicit UTC publication timestamp.")
@click.option("--reviewed-by", required=True, help="Recorded catalog reviewer or role.")
@click.option("--approved-by", required=True, help="Recorded publication authority or role.")
@click.option(
    "--group",
    "publication_group",
    help="Unix group assigned to the published namespace and release tree.",
)
@click.option("--set-current", is_flag=True, help="Point current at the published release.")
def publish_static(
    catalog: str,
    output_root: str,
    published_at: str,
    reviewed_by: str,
    approved_by: str,
    publication_group: str | None,
    set_current: bool,
) -> None:
    """Promote one reviewed static catalog into an immutable public release."""
    publish_static_command.run(
        catalog=catalog,
        output_root=output_root,
        published_at=published_at,
        reviewed_by=reviewed_by,
        approved_by=approved_by,
        publication_group=publication_group,
        set_current=set_current,
    )


@cli.command("init-workspace")
@click.option("--blueprint", required=True, help="Authored workspace blueprint directory.")
@click.option("--catalog", required=True, help="Rendered static platform catalog directory.")
@click.option("--values", required=True, help="Site-specific blueprint values YAML.")
@click.option("--output", required=True, help="Initialized workspace destination.")
@click.option("--overwrite", is_flag=True, help="Replace an existing initialized workspace.")
def init_workspace(
    blueprint: str,
    catalog: str,
    values: str,
    output: str,
    overwrite: bool,
) -> None:
    """Initialize a CSE pilot workspace from a static catalog and blueprint."""
    init_workspace_command.run(
        blueprint=blueprint,
        catalog=catalog,
        values=values,
        output=output,
        overwrite=overwrite,
    )


@cli.command("validate")
@click.option("--profile", required=True, help="profile.yaml path.")
@click.option("--deployment", required=True, help="deployment.yaml path (render requires it too).")
@click.option("--stack", required=True, help="stack.yaml path.")
@click.option("--templates", required=True, help="Root directory containing template sets.")
@click.option("--package-sets", help="Package-set directory; defaults next to stack source.")
@click.option(
    "--package-repos", help="Package-repository directory; defaults next to stack source."
)
@click.option("--report", help="Optional YAML report path.")
def validate(
    profile: str,
    deployment: str,
    stack: str,
    templates: str,
    package_sets: str | None,
    package_repos: str | None,
    report: str | None,
) -> None:
    try:
        validate_command.run(
            profile=profile,
            deployment=deployment,
            stack=stack,
            templates=templates,
            package_sets=package_sets,
            package_repos=package_repos,
            report=report,
        )
    except ValidationFailed as exc:
        raise click.ClickException(format_issues(exc.issues)) from exc


@cli.command("publish-manifest")
@click.option("--workspace", required=True, help="Rendered workspace directory.")
@click.option("--build-host", required=True, help="Build host name.")
@click.option("--lockfiles", required=True, help="Directory containing lane spack.lock files.")
@click.option("--platform-module-prereqs", required=True, help="Platform prereq YAML.")
@click.option("--buildcache-destinations", required=True, help="Buildcache destination YAML.")
@click.option("--verify-results", required=True, help="Verification results YAML.")
@click.option("--force", is_flag=True, help="Allow rewriting a final manifest.")
@command_error_handler
def publish_manifest(
    workspace: str,
    build_host: str,
    lockfiles: str,
    platform_module_prereqs: str,
    buildcache_destinations: str,
    verify_results: str,
    force: bool,
) -> None:
    publish_manifest_command.run(
        workspace=workspace,
        build_host=build_host,
        lockfiles=lockfiles,
        platform_module_prereqs=platform_module_prereqs,
        buildcache_destinations=buildcache_destinations,
        verify_results=verify_results,
        force=force,
    )


def main() -> None:
    cli(prog_name="stack-composer")


if __name__ == "__main__":
    main()
