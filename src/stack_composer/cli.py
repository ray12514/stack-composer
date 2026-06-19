from __future__ import annotations

import click

from stack_composer import __version__
from stack_composer.commands import (
    assess_profiles as assess_profiles_command,
)
from stack_composer.commands import (
    explain as explain_command,
)
from stack_composer.commands import (
    publish_manifest as publish_manifest_command,
)
from stack_composer.commands import (
    render as render_command,
)
from stack_composer.commands import (
    scaffold_templates as scaffold_templates_command,
)
from stack_composer.commands import (
    validate as validate_command,
)
from stack_composer.commands import (
    validate_template_set as validate_template_set_command,
)
from stack_composer.commands._stub import command_error_handler
from stack_composer.commands.licenses import print_licenses
from stack_composer.errors import ValidationFailed


@click.group(context_settings={"help_option_names": ["-h", "--help"]}, invoke_without_command=True)
@click.version_option(__version__, prog_name="stack-composer")
@click.option("--licenses", "show_licenses", is_flag=True, help="Print bundled license metadata.")
@click.pass_context
def cli(ctx: click.Context, show_licenses: bool) -> None:
    """Render and validate declarative Spack stack workspaces."""
    if show_licenses:
        print_licenses()
        ctx.exit(0)


@cli.command("assess-profiles")
@click.option("--profiles", multiple=True, required=True, help="Profile glob; may be repeated.")
@click.option("--templates", required=True, help="Root directory containing template sets.")
@click.option("--output", help="Report YAML path; stdout when omitted.")
@command_error_handler
def assess_profiles(profiles: tuple[str, ...], templates: str, output: str | None) -> None:
    assess_profiles_command.run(profiles=profiles, templates=templates, output=output)


@cli.command("scaffold-templates")
@click.option("--profile", required=True, help="profile.yaml path.")
@click.option("--seed", help="Optional seed template-set directory.")
@click.option("--output", required=True, help="Empty output directory for proposed templates.")
@click.option("--stack-kind", type=click.Choice(["library", "application"]), default="library")
@command_error_handler
def scaffold_templates(profile: str, seed: str | None, output: str, stack_kind: str) -> None:
    scaffold_templates_command.run(profile=profile, seed=seed, output=output, stack_kind=stack_kind)


@cli.command("validate-template-set")
@click.option("--templates", required=True, help="Single template set directory under test.")
@click.option("--profiles", multiple=True, required=True, help="Profile glob; may be repeated.")
@click.option("--output", required=True, help="Report directory.")
@click.option("--concretize", is_flag=True, help="Optionally run spack concretize if available.")
@command_error_handler
def validate_template_set(
    templates: str, profiles: tuple[str, ...], output: str, concretize: bool
) -> None:
    validate_template_set_command.run(
        templates=templates, profiles=profiles, output=output, concretize=concretize
    )


@cli.command("explain")
@click.option("--profile", required=True, help="profile.yaml path.")
@click.option("--templates", required=True, help="Root directory containing template sets.")
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["human", "yaml", "json"]),
    default="human",
)
@command_error_handler
def explain(profile: str, templates: str, output_format: str) -> None:
    explain_command.run(profile=profile, templates=templates, output_format=output_format)


@cli.command("render")
@click.option("--profile", required=True, help="profile.yaml path.")
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


@cli.command("validate")
@click.option("--profile", required=True, help="profile.yaml path.")
@click.option("--stack", required=True, help="stack.yaml path.")
@click.option("--templates", required=True, help="Root directory containing template sets.")
@click.option("--package-sets", help="Package-set directory; defaults next to stack source.")
@click.option(
    "--package-repos", help="Package-repository directory; defaults next to stack source."
)
@click.option("--report", help="Optional YAML report path.")
def validate(
    profile: str,
    stack: str,
    templates: str,
    package_sets: str | None,
    package_repos: str | None,
    report: str | None,
) -> None:
    try:
        validate_command.run(
            profile=profile,
            stack=stack,
            templates=templates,
            package_sets=package_sets,
            package_repos=package_repos,
            report=report,
        )
    except ValidationFailed as exc:
        raise click.ClickException(str(exc)) from exc


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
