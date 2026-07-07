from __future__ import annotations

from copy import deepcopy
from typing import Any

from stack_composer.render.plan import plan_lanes
from tests.test_render_scopes import ambiguous_openmpi_profile, fixture_context


def selection_stack(mpi: dict[str, Any]) -> dict[str, Any]:
    """A stack as it looks after merge_defaults: mpi carries the site policy."""
    return {
        "schema_version": 1,
        "name": "selection",
        "profile_contract": {"schema_version": 1},
        "templates": {"set": "v6"},
        "mpi": mpi,
        "builds": [{"name": "mpi", "kind": "mpi", "specs": ["hdf5+mpi"]}],
    }


def mpi_lanes_of(lanes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [lane for lane in lanes if lane["kind"] == "mpi"]


def test_version_policy_newest_selects_latest_site_mpi() -> None:
    # Two site openmpi versions are a hard mpi_ambiguous error by default;
    # declared site policy (version_policy: newest) resolves it instead.
    profile = ambiguous_openmpi_profile()
    stack = selection_stack({"provider": "openmpi", "version_policy": "newest"})

    lanes, _skipped, _narrowing, issues = plan_lanes(profile, stack)

    assert not [issue for issue in issues if issue.code == "mpi_ambiguous"]
    selected = mpi_lanes_of(lanes)
    assert selected
    assert all(lane["mpi_version"] == "5.0.3" for lane in selected)


def test_without_version_policy_ambiguity_stays_a_hard_error() -> None:
    # Regression guard: the policy is opt-in; undeclared ambiguity remains an
    # authoring defect.
    profile = ambiguous_openmpi_profile()
    stack = selection_stack({"provider": "openmpi"})

    _lanes, _skipped, _narrowing, issues = plan_lanes(profile, stack)

    assert [issue for issue in issues if issue.code == "mpi_ambiguous"]


def test_preferred_provider_wins_over_profile_order() -> None:
    # defaults.mpi.provider is a preference: when the profile reports it, it
    # beats profile order.
    profile, _stack = fixture_context("example-linux")
    profile = deepcopy(profile)
    profile["mpi_providers"].insert(
        0,
        {
            "name": "mpich",
            "version": "4.2.0",
            "provider_family": "site",
            "prefix": "/opt/site/mpich/4.2.0",
            "compiler": "gcc@11.4.0",
        },
    )
    stack = selection_stack({"provider": "openmpi", "source": "auto"})

    lanes, _skipped, _narrowing, _issues = plan_lanes(profile, stack)

    selected = mpi_lanes_of(lanes)
    assert selected
    assert all(lane["mpi_provider"] == "openmpi" for lane in selected)


def test_preferred_provider_falls_back_to_reported_provider() -> None:
    # When the preferred provider is not on this system, use what the profile
    # reports (platform source) rather than failing or building from source.
    profile, _stack = fixture_context("example-linux")
    profile = deepcopy(profile)
    profile["mpi_providers"] = [
        {
            "name": "mpich",
            "version": "4.2.0",
            "provider_family": "site",
            "prefix": "/opt/site/mpich/4.2.0",
            "compiler": "gcc@11.4.0",
        }
    ]
    stack = selection_stack({"provider": "openmpi", "source": "auto"})

    lanes, _skipped, _narrowing, _issues = plan_lanes(profile, stack)

    selected = mpi_lanes_of(lanes)
    assert selected
    assert all(
        lane["mpi_provider"] == "mpich" and lane["mpi_source"] == "platform"
        for lane in selected
    )
