from __future__ import annotations

import re
from collections import Counter
from pathlib import Path
from typing import Any

from jinja2 import Environment

from stack_composer.errors import Issue, ValidationFailed
from stack_composer.model.package_set import expand_specs_for_lane, spec_package_name
from stack_composer.render.platform_modules import platform_module_prereqs_for_lane
from stack_composer.render.scopes import scopes_for_lane
from stack_composer.render.shared_exposure import lane_shared_module_set

_HEAD_VERSION = re.compile(r"@=?([A-Za-z0-9_.\-]+)")

CLEAN_PROJECTION = "{name}/{version}"
PYTHON_QUALIFIED_PROJECTION = "{name}/{version}-python{^python.version}"


def spec_name_version(spec: str) -> tuple[str, str | None]:
    head = spec.strip().split()[0]
    match = _HEAD_VERSION.search(head)
    return spec_package_name(head), match.group(1) if match else None


def root_projections(specs: list[str]) -> tuple[list[dict[str, str]], list[Issue]]:
    """Per-package view/module projections for a lane's root specs.

    Names stay clean until they collide: a package carrying two root specs
    with the same name and version (one per python line, e.g. py-numpy built
    against each supported python) gets a python-qualified projection so the
    module and view names stay unique. Same-name/version duplicates that no
    ^python dependency distinguishes are a render error, not a guess.
    """
    pairs = [spec_name_version(spec) for spec in specs]
    duplicated = {key for key, count in Counter(pairs).items() if count > 1}
    qualified: dict[str, str] = {}
    issues: list[Issue] = []
    for spec, key in zip(specs, pairs):
        if key not in duplicated:
            continue
        if "^python@" in spec:
            qualified[key[0]] = PYTHON_QUALIFIED_PROJECTION
        else:
            issues.append(
                Issue(
                    "error",
                    "ambiguous-root-modules",
                    spec,
                    f"root spec {spec!r} duplicates {key[0]}@{key[1]} with no "
                    f"^python line to qualify the module name; disambiguate "
                    f"the roots or drop one",
                )
            )
    projections = [
        {"name": name, "projection": qualified.get(name, CLEAN_PROJECTION)}
        for name in sorted({name for name, _ in pairs})
    ]
    return projections, issues


def module_root_projections(
    projections: list[dict[str, str]], foundation_pins: dict[str, str]
) -> list[dict[str, str]]:
    """Keep foundation libraries out of the root-only module view.

    Foundation packages are ambient roots in the user-facing core view and do
    not receive package modules. The module view contains roots only, and the
    module whitelist selects those roots with their complete spec constraints.
    """
    foundation = set(foundation_pins)
    return [entry for entry in projections if entry["name"] not in foundation]


def module_formats(stack: dict[str, Any]) -> list[str]:
    """Module formats are declared policy (modules.format + additional_formats),
    never a template constant."""
    modules = stack.get("modules") or {}
    formats = [str(modules.get("format") or "tcl")]
    for extra in modules.get("additional_formats") or []:
        if extra not in formats:
            formats.append(str(extra))
    return formats


def default_view_policy(
    lane: dict[str, Any], stack: dict[str, Any], projections: list[dict[str, str]]
) -> dict[str, Any]:
    """Describe the user-facing view without exposing dependency internals.

    The core view is prepended by the compiler-init module, so it contains only
    the deliberately ambient foundation roots. Payload views are not prepended;
    they retain every explicit root, projected by version so multiple supported
    root versions can coexist. The separate ``cse_modules`` view contains the
    explicit roots used by Spack module generation.
    """
    if lane["kind"] == "core":
        return {
            "link": "roots",
            "select": sorted((stack.get("foundation_pins") or {}).keys()),
            "projections": [],
        }
    return {
        "link": "roots",
        "select": [],
        "projections": projections,
    }


def lane_module_includes(
    lane: dict[str, Any], ctx: dict[str, Any], specs: list[str]
) -> list[str]:
    """Return exact root specs for the lane's default package-module set.

    Full constraints matter: a package-name-only include matches every
    concrete variant in Spack's shared install database. That lets roots from
    other lanes leak into this module tree and collide at ``name/version``.
    """
    shared = lane_shared_module_set(lane, ctx["shared_exposure_plan"])
    excluded = set(shared["packages"]) if shared else set()
    excluded |= set((ctx["stack"].get("foundation_pins") or {}).keys())
    return sorted(spec for spec in specs if spec_package_name(spec) not in excluded)


def lane_shared_module_includes(
    lane: dict[str, Any], ctx: dict[str, Any], specs: list[str]
) -> list[str]:
    """Return exact root specs owned by the lane's shared module set."""
    shared = lane_shared_module_set(lane, ctx["shared_exposure_plan"])
    if not shared:
        return []
    included = set(shared["packages"])
    return sorted(spec for spec in specs if spec_package_name(spec) in included)


def render_lane_environment(
    *,
    template_dir: Path,
    pending: Path,
    env: Environment,
    ctx: dict[str, Any],
    lane: dict[str, Any],
) -> None:
    prereqs, prereq_issues = platform_module_prereqs_for_lane(lane, ctx["profile"])
    if prereq_issues:
        raise ValidationFailed(prereq_issues)
    specs = expand_specs_for_lane(ctx["spec_sources"][lane["source_build"]], lane)
    projections, projection_issues = root_projections(specs)
    if projection_issues:
        raise ValidationFailed(projection_issues)
    lane_ctx = dict(ctx)
    default_view = default_view_policy(lane, ctx["stack"], projections)
    module_projections = module_root_projections(
        projections, ctx["stack"].get("foundation_pins") or {}
    )
    lane_ctx.update(
        {
            "lane": lane,
            "specs": specs,
            "scopes": scopes_for_lane(lane, ctx["stack"], ctx["profile"]),
            "view_root": lane["view_root"],
            "default_view": default_view,
            # Module generation reads this root-only projected view (use_view).
            # Explicit roots get clean {name}/{version} names, python-qualified
            # when two supported Python roots would otherwise collide.
            "module_view_root": lane["view_root"] + "-modules",
            "root_projections": module_projections,
            "qualified_projections": [
                entry
                for entry in module_projections
                if entry["projection"] != CLEAN_PROJECTION
            ],
            # Exact root constraints prevent another lane's variants from
            # matching this module set in the shared install database.
            "lane_module_includes": lane_module_includes(lane, ctx, specs),
            "module_formats": module_formats(ctx["stack"]),
            # Owning serial lane only: the shared module set for lane-agnostic
            # packages (single build, exposed in every payload lane).
            "lane_shared_module_set": lane_shared_module_set(
                lane, ctx["shared_exposure_plan"]
            ),
            "lane_shared_module_includes": lane_shared_module_includes(
                lane, ctx, specs
            ),
            "platform_module_prereqs": prereqs,
        }
    )
    src = template_dir / "environments" / lane["kind"] / "spack.yaml.j2"
    dst = pending / lane["env_path"] / "spack.yaml"
    dst.parent.mkdir(parents=True, exist_ok=True)
    template_name = src.relative_to(template_dir).as_posix()
    dst.write_text(env.get_template(template_name).render(lane_ctx), encoding="utf-8")
