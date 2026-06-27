from __future__ import annotations

import glob
import re
import sys
from pathlib import Path
from typing import IO, Any

import click
import yaml

from stack_composer.errors import ValidationFailed
from stack_composer.model.profile import load_profile
from stack_composer.render.engine import render_workspace
from stack_composer.render.release import ReleaseVars, SourceRepo


def expand_profile_globs(profile_args: tuple[str, ...]) -> list[Path]:
    paths: list[Path] = []
    seen: set[Path] = set()
    for arg in profile_args:
        if any(c in arg for c in "*?["):
            matches = sorted(Path(p) for p in glob.glob(arg))
        else:
            matches = [Path(arg)]
        for path in matches:
            resolved = path.resolve()
            if resolved not in seen:
                paths.append(path)
                seen.add(resolved)
    return paths

SMOKE_RELEASE_TAG = "validate"
SMOKE_RENDERED_AT = "1970-01-01T00:00:00Z"
SMOKE_SOURCE_REPO = SourceRepo(
    url="unknown",
    commit="0" * 40,
    dirty=False,
)


def run(
    *,
    templates: str,
    profiles: tuple[str, ...],
    smoke_stack: str,
    package_sets_dir: str,
    package_repos_dir: str,
    output: str,
    concretize: bool,
    stream: IO[str] | None = None,
) -> None:
    err = stream or sys.stderr
    if concretize:
        raise click.ClickException("--concretize is not implemented in this phase")

    template_set_dir = Path(templates)
    if not (template_set_dir / "defaults.yaml").is_file():
        raise click.ClickException(
            f"--templates must point at a single template set with defaults.yaml; "
            f"got {template_set_dir!r}"
        )

    profile_paths = expand_profile_globs(profiles)
    if not profile_paths:
        raise click.ClickException(f"no profiles matched globs {list(profiles)!r}")

    output_root = Path(output)
    output_root.mkdir(parents=True, exist_ok=True)

    summary: list[dict[str, Any]] = []
    for profile_path in profile_paths:
        profile_data, profile_issues = load_profile(profile_path)
        slug = profile_slug(profile_path, profile_data, profile_issues)
        report_dir = output_root / slug
        report_dir.mkdir(parents=True, exist_ok=True)

        result = render_one(
            profile_path=profile_path,
            profile_issues=profile_issues,
            smoke_stack=Path(smoke_stack),
            template_set_dir=template_set_dir,
            package_sets_dir=Path(package_sets_dir),
            package_repos_dir=Path(package_repos_dir),
            workspace_root=report_dir,
        )
        result["profile_path"] = str(profile_path)
        (report_dir / "result.yaml").write_text(
            yaml.safe_dump(result, sort_keys=False), encoding="utf-8"
        )
        summary.append({"profile": slug, **result})

    (output_root / "summary.yaml").write_text(
        yaml.safe_dump({"results": summary}, sort_keys=False), encoding="utf-8"
    )

    failed = [entry for entry in summary if entry["render"] != "ok"]
    err.write(
        f"validate-template-set: {len(summary) - len(failed)}/{len(summary)} profiles ok\n"
    )
    for entry in failed:
        err.write(f"  FAIL {entry['profile']}: {entry.get('reason', 'unknown')}\n")
    if failed:
        raise click.ClickException(
            f"{len(failed)} of {len(summary)} profiles failed to render"
        )


def render_one(
    *,
    profile_path: Path,
    profile_issues: list,
    smoke_stack: Path,
    template_set_dir: Path,
    package_sets_dir: Path,
    package_repos_dir: Path,
    workspace_root: Path,
) -> dict[str, Any]:
    if profile_issues:
        return {
            "render": "fail",
            "reason_code": "profile-schema",
            "reason": "; ".join(issue.message for issue in profile_issues),
        }
    workspace_dir = workspace_root / "workspace"
    workspace_dir.mkdir(parents=True, exist_ok=True)
    release_vars = ReleaseVars(
        release_tag=SMOKE_RELEASE_TAG,
        output_root=workspace_dir.as_posix(),
        rendered_at=SMOKE_RENDERED_AT,
        source_repo=SMOKE_SOURCE_REPO,
    )
    try:
        rendered = render_workspace(
            profile_path=profile_path,
            stack_path=smoke_stack,
            templates_root=template_set_dir.parent,
            release_vars=release_vars,
            package_sets_dir=package_sets_dir,
            package_repos_dir=package_repos_dir,
        )
    except ValidationFailed as exc:
        return {
            "render": "fail",
            "reason_code": exc.issues[0].code if exc.issues else "validation",
            "reason": "; ".join(issue.message for issue in exc.issues),
        }
    except Exception as exc:
        return {"render": "fail", "reason_code": "render-error", "reason": str(exc)}
    return {"render": "ok", "workspace": rendered.as_posix()}


_SLUG_BAD = re.compile(r"[^a-zA-Z0-9_-]+")


def profile_slug(profile_path: Path, profile: dict[str, Any], issues: list) -> str:
    if not issues:
        name = (profile.get("system") or {}).get("name")
        if isinstance(name, str) and name:
            return _SLUG_BAD.sub("-", name).strip("-") or profile_path.stem
    return _SLUG_BAD.sub("-", profile_path.stem).strip("-") or "profile"
