"""Spec-native build normalization.

A stack.yaml build may be authored minimally as just ``name`` + ``specs`` (or a
``package_set``), with an optional ``kind`` (cpu/mpi/gpu). This module infers the
kind from the specs when omitted, then fills ``class``/``toolchain``/``nodes``/
``expand`` from the contract's ``kind_defaults`` for that kind. Explicit build
fields always win, so the legacy fully-specified form is unchanged
(normalization is idempotent on it).
"""

from __future__ import annotations

from typing import Any

# GPU markers win over MPI: a `+mpi+rocm` spec is a GPU build.
_GPU_SPEC_MARKERS = ("+rocm", "+cuda", "+sycl", "cuda_arch", "amdgpu_target")
_MPI_SPEC_MARKERS = ("+mpi",)

# Fallback expand per kind when neither the build nor kind_defaults set it.
_DEFAULT_EXPAND = {"cpu": "one", "mpi": "one", "gpu": "per_gpu_arch"}

_FILLABLE_FIELDS = ("class", "toolchain", "nodes")


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


def normalize_build(build: dict[str, Any], contract: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of *build* with kind set and class/toolchain/nodes/expand
    filled from ``contract.kind_defaults[kind]`` where the build omits them.
    Explicit build fields are preserved."""
    normalized = dict(build)
    kind = infer_kind(build)
    normalized.setdefault("kind", kind)

    defaults = (contract.get("kind_defaults") or {}).get(kind, {})
    for field in _FILLABLE_FIELDS:
        if not normalized.get(field) and defaults.get(field):
            normalized[field] = defaults[field]
    if not normalized.get("expand"):
        normalized["expand"] = defaults.get("expand") or _DEFAULT_EXPAND.get(kind, "one")
    return normalized


def normalize_builds(stack: dict[str, Any], contract: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of *stack* with every build normalized. No-op when there are
    no builds."""
    builds = stack.get("builds")
    if not isinstance(builds, list):
        return stack
    normalized = dict(stack)
    normalized["builds"] = [normalize_build(build, contract) for build in builds]
    return normalized
