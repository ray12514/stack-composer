from __future__ import annotations

from typing import Any


def emit_contract_stub(facts: dict[str, Any]) -> dict[str, Any]:
    gpu_selectors = {}
    for arch in facts.get("gpu_arches", []):
        key = arch.replace("_", "-")
        if arch.startswith("gfx"):
            gpu_selectors[key] = {
                "vendor": "amd",
                "arch_target": arch,
                "spack": {"amdgpu_target": arch},
            }
        elif arch.startswith("sm_"):
            gpu_selectors[key] = {
                "vendor": "nvidia",
                "arch_target": arch,
                "spack": {"cuda_arch": arch.removeprefix("sm_")},
            }
    return {
        "schema_version": 1,
        "build_classes": {
            "core": {
                "lane_kind": "core",
                "package_set_kind": "core",
                "default_target": "foundation",
                "requires": ["runtime_cpu"],
            },
            "serial": {
                "lane_kind": "serial",
                "package_set_kind": "serial",
                "default_target": "payload_default",
                "requires": ["runtime_cpu"],
            },
            "mpi": {
                "lane_kind": "mpi",
                "package_set_kind": "mpi",
                "default_target": "payload_default",
                "requires": ["runtime_cpu", "mpi"],
            },
            "gpu": {
                "lane_kind": "gpu",
                "package_set_kind": "gpu",
                "default_target": "payload_default",
                "requires": ["runtime_gpu", "mpi", "gpu_toolkit"],
            },
        },
        "toolchains": {
            "scaffold-core": {
                "compiler": "each_core_compiler",
                "mpi": "none",
                "gpu_toolkit": "none",
            },
            "scaffold-serial": {
                "compiler": "each_serial_compiler",
                "mpi": "none",
                "gpu_toolkit": "none",
            },
            "scaffold-mpi": {
                "compiler": "each_mpi_compiler",
                "mpi": "platform_then_stack_mpi",
                "gpu_toolkit": "none",
            },
            "scaffold-gpu": {
                "compiler": "gnu_host_default",
                "mpi": "platform_mpi_required",
                "gpu_toolkit": "prefer_platform",
            },
        },
        "node_selectors": {
            "cpu": {"match": "runtime_without_gpu"},
            "gpu": {"match": "runtime_with_gpu"},
        },
        "gpu_selectors": gpu_selectors,
        "vendor_scope_selectors": {
            "cray": {"profile_key": "vendor_cray", "scope": "vendor/cray"},
            "linux": {"default": True, "scope": "vendor/linux"},
        },
        "target_policies": {
            "foundation": {"resolve": "baseline_x86_64_v3", "hard_require": False},
            "payload_default": {"resolve": "runtime_preferred", "hard_require": False},
        },
    }
