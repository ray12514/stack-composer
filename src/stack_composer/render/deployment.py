from __future__ import annotations

import posixpath
from copy import deepcopy
from typing import Any


def materialize_lane_paths(
    lanes: list[dict[str, Any]],
    *,
    profile: dict[str, Any],
    stack: dict[str, Any],
    deployment: dict[str, Any],
    release_tag: str,
) -> list[dict[str, Any]]:
    """Attach installer-owned view/module paths to logical lanes.

    The profile reports filesystem candidates; the deployment overlay records
    the chosen roots. Lane planning never guesses these paths.
    """
    system_name = profile["system"]["name"]
    stack_name = stack["name"]
    rendered: list[dict[str, Any]] = []
    for lane in lanes:
        lane = deepcopy(lane)
        lane["view_root"] = posixpath.join(
            deployment["roots"]["views"],
            release_tag,
            system_name,
            stack_name,
            lane["compiler"],
            lane["lane"],
        )
        lane["package_module_root"] = posixpath.join(
            deployment["roots"]["modules"],
            release_tag,
            system_name,
            stack_name,
            lane["compiler"],
            lane["lane"],
        )
        rendered.append(lane)
    return rendered
