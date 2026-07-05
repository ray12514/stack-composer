"""Resolved GPU toolkit selection, computed once so templates only print.

Which ROCm/CUDA externals a GPU scope exposes is read from the profile's GPU
toolkit facts. That resolution used to run inside the gpu scope templates (via
the `gpu_external_packages` global). This module makes it once, keyed by
toolkit, so the templates become dumb printers reading `gpu_plan[toolkit]`.
"""

from __future__ import annotations

from typing import Any

from stack_composer.render.scopes import gpu_external_packages

_TOOLKITS = ("rocm", "cuda")


def build_gpu_plan(profile: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    """Resolve GPU toolkit externals for every toolkit with facts on the system.

    Returns `{toolkit: [packages]}`. A toolkit with no resolved externals is
    omitted — there is nothing to render for it.
    """
    plan: dict[str, list[dict[str, Any]]] = {}
    for toolkit in _TOOLKITS:
        packages = gpu_external_packages(profile, toolkit)
        if packages:
            plan[toolkit] = packages
    return plan
