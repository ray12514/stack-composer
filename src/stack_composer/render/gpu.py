"""Resolved GPU toolkit selection, computed once so templates only print.

Which ROCm/CUDA externals a GPU scope exposes is read from the profile's GPU
toolkit facts. This module owns that selection and the Spack packages.yaml
shape for GPU toolkit externals so callers do not need to know where ROCm and
CUDA differ.
"""

from __future__ import annotations

from typing import Any

from stack_composer.render.spack_specs import (
    external_spec,
    is_absolute_prefix,
    is_renderable_external_name_version,
)
from stack_composer.render.versioning import version_key

_TOOLKITS = ("rocm", "cuda")


def build_gpu_plan(profile: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    """Resolve GPU toolkit externals for every toolkit.

    Returns `{toolkit: [packages]}` with every toolkit key always present
    (empty when the profile has no facts), so templates print without
    defaulting guards.
    """
    return {toolkit: gpu_external_packages(profile, toolkit) for toolkit in _TOOLKITS}


def select_gpu_toolkit(profile: dict[str, Any], family: str) -> dict[str, Any]:
    """Choose one GPU toolkit generation to render from the reported inventory.

    Cluster Inspector reports every installed toolkit generation as a list; the
    render selects one. Default policy is latest version. A compatibility
    matrix can replace this implementation later without changing callers.
    """
    toolkits = (profile.get("gpu_toolkit_modules") or {}).get(family) or []
    if not toolkits:
        return {}
    return max(toolkits, key=lambda toolkit: version_key(str(toolkit.get("version") or "0")))


def gpu_external_packages(profile: dict[str, Any], toolkit: str) -> list[dict[str, Any]]:
    if toolkit == "rocm":
        return rocm_external_packages(select_gpu_toolkit(profile, "rocm"))
    if toolkit == "cuda":
        return cuda_external_packages(select_gpu_toolkit(profile, "cudatoolkit"))
    return []


def rocm_external_packages(rocm: dict[str, Any]) -> list[dict[str, Any]]:
    packages: dict[str, dict[str, Any]] = {}
    version = rocm.get("version")
    module = rocm.get("module")
    for component in rocm.get("spack_components") or []:
        _add_external(
            packages,
            {
                "name": component.get("package"),
                "version": version,
                "prefix": component.get("prefix"),
                "modules": [module] if module else [],
            },
        )
    return list(packages.values())


def cuda_external_packages(cuda: dict[str, Any]) -> list[dict[str, Any]]:
    packages: dict[str, dict[str, Any]] = {}
    _add_external(
        packages,
        {
            "name": "cuda",
            "version": cuda.get("version"),
            "prefix": cuda.get("prefix"),
            "modules": [cuda["module"]] if cuda.get("module") else [],
        },
    )
    return list(packages.values())


def _add_external(packages: dict[str, dict[str, Any]], external: dict[str, Any]) -> None:
    name = external.get("name")
    version = external.get("version")
    prefix = external.get("prefix")
    if not (is_renderable_external_name_version(name, version) and is_absolute_prefix(prefix)):
        return
    package = packages.setdefault(name, {"name": name, "buildable": False, "externals": []})
    package["externals"].append(
        {
            "spec": external_spec(name, version),
            "prefix": external["prefix"],
            "modules": external.get("modules") or [],
        }
    )
