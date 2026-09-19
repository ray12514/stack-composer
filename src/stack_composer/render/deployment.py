from __future__ import annotations

import posixpath
from copy import deepcopy
from typing import Any, cast

from stack_composer.errors import Issue, ValidationFailed
from stack_composer.render.records import Lane


def materialize_lane_paths(
    lanes: list[Lane],
    *,
    profile: dict[str, Any],
    stack: dict[str, Any],
    deployment: dict[str, Any],
    release_tag: str,
) -> list[Lane]:
    """Attach installer-owned view/module paths to logical lanes.

    The profile reports filesystem candidates; the deployment overlay records
    the chosen roots. Lane planning never guesses these paths.
    """
    system_name = profile["system"]["name"]
    stack_name = stack["name"]
    exposure = (stack.get("modules") or {}).get("exposure", "front_door")
    publish_root = (deployment.get("modules") or {}).get("publish_root")
    if exposure == "direct" and not publish_root:
        raise ValidationFailed(
            [
                Issue(
                    "error",
                    "direct-exposure-needs-publish-root",
                    "deployment.modules.publish_root",
                    "modules exposure is direct but the deployment declares no "
                    "publish_root to publish package modules into",
                )
            ]
        )
    rendered: list[Lane] = []
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
        if exposure == "direct":
            # No front door: package modules land directly in the
            # installer-chosen root already on the site MODULEPATH.
            # The direct-exposure preflight above requires this path.
            lane["package_module_root"] = cast(str, publish_root)
        else:
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
