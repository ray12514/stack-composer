"""Planning regressions promoted from the September assessment."""

from __future__ import annotations

from copy import deepcopy

import yaml

from stack_composer.model.package_set import expand_specs_for_lane
from stack_composer.render.plan import plan_lanes, resolve_mpi
from stack_composer.schema_registry import validate_schema
from stack_composer.validate.checks import (
    load_spec_sources,
    validate_package_sets,
    validate_per_system_narrowing,
)
from tests.test_render_scopes import fixture_context


def test_partial_per_build_mpi_override_inherits_default_provider() -> None:
    """A source-only override must retain the default provider."""
    profile, _ = fixture_context("example-linux")
    stack = {"mpi": {"provider": "openmpi", "source": "auto"}}
    build = {"mpi": {"source": "build"}}

    assert resolve_mpi(profile, stack, build) == ("openmpi", "build")


def test_forced_platform_mpi_does_not_substitute_another_provider() -> None:
    """source=platform means the named provider or a clear error, never fallback."""
    profile, _ = fixture_context("example-linux")
    stack = {
        "name": "forced-platform",
        "mpi": {"provider": "openmpi", "source": "auto"},
        "builds": [
            {
                "name": "mpi",
                "kind": "mpi",
                "specs": ["hdf5+mpi"],
                # The fixture reports Open MPI but not MPICH.
                "mpi": {"provider": "mpich", "source": "platform"},
            }
        ],
    }

    lanes, _skipped, _narrowing, issues = plan_lanes(profile, stack)

    assert not lanes
    assert any(issue.severity == "error" for issue in issues)


def test_exact_narrowing_selects_one_version_of_a_duplicate_compiler() -> None:
    """Resolved compiler IDs in per_system narrowing include name@version."""
    profile, _ = fixture_context("example-linux")
    profile = deepcopy(profile)
    profile["compiler_providers"].append(
        {
            "name": "gcc",
            "version": "14.3.0",
            "prefix": "/opt/site/gcc/14.3.0",
            "provider_family": "site",
            "languages": ["c", "c++", "fortran"],
        }
    )
    assert validate_schema("profile", profile, "profile.yaml") == []

    stack = {
        "name": "exact-narrowing",
        "compilers": "all",
        "builds": [{"name": "serial", "kind": "serial", "specs": ["zlib"]}],
        "per_system": {
            profile["system"]["name"]: {"builds": {"serial": {"compilers": ["gcc@14.3.0"]}}}
        },
    }

    narrowing_issues = validate_per_system_narrowing(stack, profile)
    lanes, _skipped, _narrowing, plan_issues = plan_lanes(profile, stack)

    assert narrowing_issues == []
    assert plan_issues == []
    assert [lane["compiler_ref"] for lane in lanes] == ["gcc@14.3.0"]


def test_package_set_declared_kind_has_specs_for_that_kind_or_any(tmp_path) -> None:
    """A declared kind cannot validate and then expand to no root specs."""
    package_set = {
        "schema_version": 1,
        "name": "broken",
        "tier": "canonical",
        "description": "Declares GPU support but contains only serial roots.",
        "kinds": ["gpu"],
        "specs": {"serial": ["zlib"]},
    }
    assert validate_schema("package-set", package_set, "broken.yaml") == []

    package_set_path = tmp_path / "broken.yaml"
    package_set_path.write_text(yaml.safe_dump(package_set), encoding="utf-8")
    stack = {"builds": [{"name": "gpu", "kind": "gpu", "package_set": "broken"}]}

    issues = validate_package_sets(stack, tmp_path)
    expanded = expand_specs_for_lane(
        package_set,
        {"kind": "gpu", "gpu_arch": "gfx90a"},
    )

    assert not expanded  # Demonstrates why this input must be rejected.
    assert any(issue.severity == "error" for issue in issues)


def test_duplicate_build_names_are_rejected_before_spec_source_overwrite(tmp_path) -> None:
    """Build names are identity keys and therefore must be unique."""
    stack = {
        "schema_version": 1,
        "name": "duplicates",
        "profile_contract": {"schema_version": 1},
        "templates": {"set": "v6"},
        "builds": [
            {"name": "serial", "kind": "serial", "specs": ["zlib"]},
            {"name": "serial", "kind": "serial", "specs": ["xz"]},
        ],
    }
    assert validate_schema("stack", stack, "stack.yaml") == []

    _sources, issues = load_spec_sources(stack, tmp_path)

    # Reject the duplicate identity; collecting the last source is not success.
    assert any(issue.severity == "error" for issue in issues)


def test_baseline_target_never_exceeds_schema_valid_profile_support() -> None:
    """Baseline may downgrade or reject, but cannot emit an unsupported target.

    This deliberately does not assert that target=native covers every runtime
    node. The narrower contract under test is that the conservative shared
    baseline must be supported by the applicable runtime profile.
    """
    profile, _ = fixture_context("example-linux")
    profile = deepcopy(profile)
    runtime = profile["node_types"]["cpu_compute"]
    runtime["cpu"] = {
        "detected": "x86_64_v2",
        "preferred": "x86_64_v2",
        "alternates": ["x86_64"],
    }
    assert validate_schema("profile", profile, "profile.yaml") == []

    stack = {
        "name": "v2-only",
        "target": "baseline",
        "builds": [
            {
                "name": "serial",
                "kind": "serial",
                "specs": ["zlib"],
                "compilers": ["gcc"],
            }
        ],
    }
    supported = {"x86_64_v2", "x86_64"}

    lanes, _skipped, _narrowing, issues = plan_lanes(profile, stack)

    safely_downgraded = bool(lanes) and {lane["target"] for lane in lanes}.issubset(supported)
    clearly_rejected = not lanes and any(issue.severity == "error" for issue in issues)
    assert safely_downgraded or clearly_rejected
