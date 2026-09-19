"""Internal planning records, with the existing dictionary representation.

These are static types, not another input schema or runtime model framework.
Keep the keys and optional-field presence unchanged: templates, reports and
workspace manifests consume these same dictionaries. Authored input remains
validated by the packaged JSON Schemas before planning.
"""

from __future__ import annotations

from typing import TypedDict


class _LaneOptions(TypedDict, total=False):
    # Deployment adds these after logical planning. Do not supply defaults in
    # the planner: their presence distinguishes materialized workspace paths.
    view_root: str
    package_module_root: str
    publish: bool


class Lane(_LaneOptions):
    name: str
    source_build: str
    compiler: str
    compiler_ref: str
    compiler_axis: str
    compiler_version: str | None
    vendor_scope: str
    lane: str
    kind: str
    package_set: str | None
    target: str
    runtime_node_type: str
    gpu_selector: str | None
    gpu_arch: str | None
    compiler_source: str
    mpi_provider: str | None
    mpi_source: str | None
    mpi_version: str | None
    toolchain: str | None
    env_path: str
    spec_source: str


class SkippedBuild(TypedDict):
    build: str
    reason_code: str
    reason: str


class SelectionError(TypedDict):
    code: str
    message: str


class NarrowedAxis(TypedDict):
    kept: list[str]
    dropped: list[str]


class BuildNarrowing(TypedDict):
    dropped_lanes: list[str]
    narrowed_by: dict[str, NarrowedAxis]


class AppliedNarrowing(TypedDict):
    system: str
    builds: dict[str, BuildNarrowing]
