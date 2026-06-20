from __future__ import annotations

from typing import Any


def summarize_profile_facts(profile: dict[str, Any]) -> dict[str, Any]:
    vendor_cray = profile.get("vendor_cray") or {}
    compilers: list[str] = []
    for name in ("gcc", "cce", "aocc", "intel", "nvhpc", "rocmcc"):
        if vendor_cray.get(name) is not None:
            compilers.append(name)
    for entry in profile.get("compilers_external") or []:
        name = entry.get("name")
        if name and name not in compilers:
            compilers.append(name)

    mpi_providers: list[str] = []
    if vendor_cray.get("cray_mpich"):
        mpi_providers.append("cray-mpich")
    for entry in profile.get("mpi") or []:
        name = entry.get("name")
        if name and name not in mpi_providers:
            mpi_providers.append(name)

    cpu_targets: set[str] = set()
    runtime_node_types: list[str] = []
    gpu_arches: set[str] = set()
    for node_name, node in sorted((profile.get("node_types") or {}).items()):
        if node.get("role") in {"runtime", "both"}:
            runtime_node_types.append(node_name)
        cpu = node.get("cpu") or {}
        for key in ("preferred", "detected"):
            if cpu.get(key):
                cpu_targets.add(cpu[key])
        cpu_targets.update(cpu.get("alternates") or [])
        gpu = node.get("gpu") or {}
        if gpu.get("arch_target"):
            gpu_arches.add(gpu["arch_target"])

    os_block = profile.get("os") or {}
    fabric = profile.get("fabric") or {}
    module_system = profile.get("modules_system") or {}
    system = profile.get("system") or {}
    return {
        "system_name": system.get("name", "unknown"),
        "system_family": system.get("family", "unknown"),
        "os": os_summary(os_block),
        "fabric": fabric_summary(fabric),
        "vendor_cray": bool(vendor_cray),
        "module_system": module_system.get("tool", "unknown"),
        "compilers": compilers,
        "mpi_providers": mpi_providers,
        "gpu_arches": sorted(gpu_arches),
        "cpu_targets": sorted(cpu_targets),
        "runtime_node_types": runtime_node_types,
    }


def os_summary(os_block: dict[str, Any]) -> str:
    name = os_block.get("name", "unknown")
    major = os_block.get("major")
    minor = os_block.get("minor")
    glibc = os_block.get("glibc")
    version = ".".join(str(part) for part in (major, minor) if part is not None)
    suffix = f" {version}" if version else ""
    glibc_suffix = f" glibc-{glibc}" if glibc else ""
    return f"{name}{suffix}{glibc_suffix}"


def fabric_summary(fabric: dict[str, Any]) -> str:
    fabric_type = fabric.get("type", "unknown")
    generation = fabric.get("generation")
    return f"{fabric_type}/{generation}" if generation else fabric_type
