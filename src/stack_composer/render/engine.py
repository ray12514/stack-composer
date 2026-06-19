from __future__ import annotations

import shutil
from pathlib import Path

from stack_composer import __version__
from stack_composer.errors import Issue, ValidationFailed
from stack_composer.manifest.draft import draft_manifest
from stack_composer.render.context import build_render_context
from stack_composer.render.environments import render_lane_environment
from stack_composer.render.plan import plan_lanes
from stack_composer.render.release import ReleaseVars
from stack_composer.render.scopes import (
    make_jinja_environment,
    render_template_tree,
    required_scopes,
)
from stack_composer.schema_registry import validate_schema
from stack_composer.validate.checks import validate_inputs
from stack_composer.yaml_io import write_yaml


def render_workspace(
    *,
    profile_path: Path,
    stack_path: Path,
    templates_root: Path,
    release_vars: ReleaseVars,
    package_sets_dir: Path,
    package_repos_dir: Path,
) -> Path:
    issues, context = validate_inputs(
        profile_path=profile_path,
        stack_path=stack_path,
        templates_root=templates_root,
        package_sets_dir=package_sets_dir,
        package_repos_dir=package_repos_dir,
    )
    if issues:
        raise ValidationFailed(issues)
    profile = context["profile"]
    stack = context["stack"]
    stack["_release_tag"] = release_vars.release_tag
    template_set = Path(context["template_set"])
    rendered_lanes, skipped_builds, applied_narrowing, plan_issues = plan_lanes(
        profile, stack, context["contract"]
    )
    if plan_issues:
        raise ValidationFailed(plan_issues)
    render_context = build_render_context(
        base_context=context,
        rendered_lanes=rendered_lanes,
        skipped_builds=skipped_builds,
        applied_narrowing=applied_narrowing,
        release_vars=release_vars,
        renderer_identity={"name": "stack-composer render", "version": __version__},
    )
    workspace = (
        Path(release_vars.output_root)
        / profile["system"]["name"]
        / stack["name"]
        / release_vars.release_tag
    )
    pending = workspace.with_name(workspace.name + ".rendering")
    if workspace.exists() and not release_vars.overwrite:
        raise ValidationFailed(
            [Issue("error", "workspace-exists", str(workspace), "workspace already exists")]
        )
    if pending.exists():
        raise ValidationFailed(
            [Issue("error", "stale-render-path", str(pending), "stale render side path exists")]
        )
    try:
        pending.mkdir(parents=True)
        jinja_env = make_jinja_environment(template_set)
        context_dict = dict(render_context)
        rendered_scopes = required_scopes(template_set)
        for scope in rendered_scopes:
            render_template_tree(
                template_set / "configs" / scope,
                pending / "configs" / scope,
                jinja_env,
                context_dict,
            )
        materialize_package_repositories(context["package_repos"], pending / "package-repos")
        for lane in rendered_lanes:
            render_lane_environment(
                template_dir=template_set,
                pending=pending,
                env=jinja_env,
                ctx=context_dict,
                lane=lane,
                rendered_scopes=rendered_scopes,
            )
        manifest = draft_manifest(
            profile_path=profile_path,
            stack_path=stack_path,
            template_set=template_set,
            package_sets_dir=package_sets_dir,
            context=context_dict,
            release_vars=release_vars,
        )
        manifest_issues = validate_schema("release-manifest", manifest, "release-manifest.yaml")
        if manifest_issues:
            raise ValidationFailed(manifest_issues)
        write_yaml(pending / "release-manifest.yaml", manifest)
        if workspace.exists() and release_vars.overwrite:
            shutil.rmtree(workspace)
        pending.replace(workspace)
    except Exception:
        if pending.exists():
            shutil.rmtree(pending)
        raise
    return workspace


def materialize_package_repositories(repos: list[dict], destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    for repo in repos:
        source = Path(repo["path"])
        target = destination / repo["name"]
        if source.is_dir():
            shutil.copytree(source, target)
