from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SourceRepo:
    url: str
    commit: str
    dirty: bool


@dataclass(frozen=True)
class ReleaseVars:
    release_tag: str
    output_root: str
    rendered_at: str
    source_repo: SourceRepo
    overwrite: bool = False


def release_vars_dict(vars: ReleaseVars, system_name: str) -> dict:
    return {
        "release_tag": vars.release_tag,
        "system_name": system_name,
        "output_root": vars.output_root,
        "rendered_at": vars.rendered_at,
        "source_repo": {
            "url": vars.source_repo.url,
            "commit": vars.source_repo.commit,
            "dirty": vars.source_repo.dirty,
        },
        "mirror_urls": {},
        "overrides": {},
    }
