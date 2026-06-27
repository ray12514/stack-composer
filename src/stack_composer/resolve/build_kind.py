"""Spec-native build kind inference.

A stack build is authored minimally as ``name`` + ``specs`` (or a
``package_set``) with an optional ``kind`` (cpu/mpi/gpu). When ``kind`` is
omitted it is inferred from the specs. That is the only normalization the build
needs — how it actually fans out into lanes (which compilers, which MPI, which
GPU arches, which target) is resolved by the planner from the merged site
defaults and any per-build overrides, against the profile. There is no contract,
toolchain, or build class.
"""

from __future__ import annotations

from typing import Any

# GPU markers win over MPI: a `+mpi+rocm` spec is a GPU build.
_GPU_SPEC_MARKERS = ("+rocm", "+cuda", "+sycl", "cuda_arch", "amdgpu_target")
_MPI_SPEC_MARKERS = ("+mpi",)


def _spec_strings(build: dict[str, Any]) -> list[str]:
    specs = build.get("specs")
    out: list[str] = []
    if isinstance(specs, list):
        out.extend(s for s in specs if isinstance(s, str))
    elif isinstance(specs, dict):
        for value in specs.values():
            if isinstance(value, list):
                out.extend(s for s in value if isinstance(s, str))
    return out


def infer_kind(build: dict[str, Any]) -> str:
    """Return the build's kind: explicit ``kind`` if set, else inferred from the
    specs (gpu > mpi > cpu). Package-set builds with no inline specs default to
    cpu and should set ``kind`` explicitly when they are MPI/GPU."""
    explicit = build.get("kind")
    if explicit:
        return str(explicit)

    specs = build.get("specs")
    if isinstance(specs, dict):
        keys = set(specs.keys())
        if "gpu" in keys:
            return "gpu"
        if "mpi" in keys:
            return "mpi"

    blob = " ".join(_spec_strings(build)).lower()
    if any(marker in blob for marker in _GPU_SPEC_MARKERS):
        return "gpu"
    if any(marker in blob for marker in _MPI_SPEC_MARKERS):
        return "mpi"
    return "cpu"


def normalize_build(build: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of *build* with ``kind`` set (inferred when omitted)."""
    normalized = dict(build)
    normalized.setdefault("kind", infer_kind(build))
    return normalized


def normalize_builds(stack: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of *stack* with every build's ``kind`` set."""
    builds = stack.get("builds")
    if not isinstance(builds, list):
        return stack
    normalized = dict(stack)
    normalized["builds"] = [normalize_build(build) for build in builds]
    return normalized
