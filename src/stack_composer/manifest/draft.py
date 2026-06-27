from __future__ import annotations

from pathlib import Path
from typing import Any

from stack_composer import __version__
from stack_composer.render.digest import sha256_file, sha256_tree
from stack_composer.render.release import ReleaseVars


def draft_manifest(
    *,
    profile_path: Path,
    stack_path: Path,
    template_set: Path,
    package_sets_dir: Path,
    context: dict[str, Any],
    release_vars: ReleaseVars,
) -> dict[str, Any]:
    profile = context["profile"]
    stack = context["stack"]
    package_set_entries = []
    seen_package_sets = set()
    for name in sorted(context["spec_sources"]):
        source = context["spec_sources"][name]
        if source.get("kind") == "inline":
            continue
        if source["name"] in seen_package_sets:
            continue
        seen_package_sets.add(source["name"])
        path = package_sets_dir / f"{source['name']}.yaml"
        package_set_entries.append(
            {"name": source["name"], "path": path.as_posix(), "digest": sha256_file(path)}
        )
    return {
        "schema_version": 1,
        "phase": "draft",
        "release": {
            "name": release_vars.release_tag,
            "rendered_at": release_vars.rendered_at,
            "promoted_at": None,
            "promoted_by": None,
        },
        "stack": {
            "name": stack["name"],
            "source_repo": release_vars.source_repo.url,
            "source_commit": release_vars.source_repo.commit,
            "source_dirty": release_vars.source_repo.dirty,
        },
        "profile": {
            "path": profile_path.as_posix(),
            "digest": sha256_file(profile_path),
            "system_name": profile["system"]["name"],
        },
        "stack_file": {"path": stack_path.as_posix(), "digest": sha256_file(stack_path)},
        "package_sets": package_set_entries,
        "templates": {
            "set": stack["templates"]["set"],
            "digest": sha256_tree(template_set),
            "defaults_digest": sha256_file(template_set / "defaults.yaml"),
            "render_tool": {"name": "stack-composer render", "version": __version__},
            "applied_narrowing": context["applied_narrowing"],
        },
        "spack": None,
        "build_host": None,
        "lanes": [manifest_lane(lane) for lane in context["rendered_lanes"]],
        "skipped_builds": context["skipped_builds"],
        "buildcache": {
            "push_destinations": [],
            "signed": stack.get("buildcache", {}).get("signed", False),
        },
        "verification": None,
        "previous_release": None,
    }


def manifest_lane(lane: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": lane["name"],
        "source_build": lane["source_build"],
        "env_path": lane["env_path"],
        "kind": lane["kind"],
        "compiler": lane["compiler"],
        "target": lane["target"],
        "runtime_node_type": lane["runtime_node_type"],
        "spec_source": lane["spec_source"],
        "view_root": lane["view_root"],
        "package_module_root": lane["package_module_root"],
        "lockfile": None,
        "lockfile_digest": None,
        "install_root": None,
        "provenance_summary": None,
        "platform_module_prereqs": None,
    }
