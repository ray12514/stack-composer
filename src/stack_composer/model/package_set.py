from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from stack_composer.schema_registry import validate_schema
from stack_composer.yaml_io import load_yaml

# Two GPU placeholders, because packages need the accelerator in two different
# ways. `+gpu` is for packages that compile device code (kokkos): they take the
# backend and the target architecture. `+gpu_runtime` is for packages that only
# use the GPU runtime, such as a profiler tracing kernels (tau): they take the
# backend and have no architecture variant to set. Rendering an arch flag onto
# a recipe that has no such variant is a concretization failure, so the package
# set author picks the placeholder that matches the recipe.
GPU_VARIANT_PLACEHOLDER = "+gpu"
GPU_RUNTIME_PLACEHOLDER = "+gpu_runtime"

_SPEC_NAME_SPLIT = re.compile(r"[@ +~%^]")


def spec_package_name(spec: str) -> str:
    return _SPEC_NAME_SPLIT.split(spec.strip(), maxsplit=1)[0]


def load_package_set(path: Path) -> tuple[dict[str, Any], list]:
    data = load_yaml(path)
    return data, validate_schema("package-set", data, str(path))


def expand_specs_for_lane(spec_source: dict[str, Any], lane: dict[str, Any]) -> list[str]:
    specs = spec_source.get("specs", {})
    if isinstance(specs, list):
        return [decorate_toolchain(expand_gpu_variant(spec, lane), lane) for spec in specs]
    expanded = []
    expanded.extend(specs.get("any", []))
    expanded.extend(specs.get(lane["kind"], []))
    return [decorate_toolchain(expand_gpu_variant(spec, lane), lane) for spec in expanded]


def decorate_toolchain(spec: str, lane: dict[str, Any]) -> str:
    toolchain = lane.get("toolchain")
    if not toolchain or "%" in spec:
        return spec
    return f"{spec} %{toolchain}"


def expand_gpu_variant(spec: str, lane: dict[str, Any]) -> str:
    arch = lane.get("gpu_arch")
    if not arch:
        return spec
    if arch.startswith("gfx"):
        return expand_amd_gpu_spec(spec, arch)
    if arch.startswith("sm_"):
        return expand_nvidia_gpu_spec(spec, arch[3:])
    return spec


def expand_amd_gpu_spec(spec: str, arch: str) -> str:
    # The runtime placeholder is checked first: replacing the `+gpu` substring
    # inside `+gpu_runtime` would corrupt it into `+rocm_runtime`.
    if GPU_RUNTIME_PLACEHOLDER in spec:
        return spec.replace(GPU_RUNTIME_PLACEHOLDER, "+rocm")
    resolved = spec.replace(GPU_VARIANT_PLACEHOLDER, "+rocm")
    if "+rocm" in resolved and "amdgpu_target=" not in resolved:
        return f"{resolved} amdgpu_target={arch}"
    return resolved


def expand_nvidia_gpu_spec(spec: str, cuda_arch: str) -> str:
    if GPU_RUNTIME_PLACEHOLDER in spec:
        return spec.replace(GPU_RUNTIME_PLACEHOLDER, "+cuda")
    resolved = spec.replace(GPU_VARIANT_PLACEHOLDER, "+cuda")
    if "+cuda" in resolved and "cuda_arch=" not in resolved:
        return f"{resolved} cuda_arch={cuda_arch}"
    return resolved
