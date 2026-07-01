from __future__ import annotations

from pathlib import Path
from typing import Any

from stack_composer.schema_registry import validate_schema
from stack_composer.yaml_io import load_yaml

GPU_VARIANT_PLACEHOLDER = "+gpu"


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
    resolved = spec.replace(GPU_VARIANT_PLACEHOLDER, "+rocm")
    if "+rocm" in resolved and "amdgpu_target=" not in resolved:
        return f"{resolved} amdgpu_target={arch}"
    return resolved


def expand_nvidia_gpu_spec(spec: str, cuda_arch: str) -> str:
    resolved = spec.replace(GPU_VARIANT_PLACEHOLDER, "+cuda")
    if "+cuda" in resolved and "cuda_arch=" not in resolved:
        return f"{resolved} cuda_arch={cuda_arch}"
    return resolved
