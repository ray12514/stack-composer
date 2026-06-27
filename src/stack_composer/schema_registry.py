from __future__ import annotations

import json
from functools import cache
from importlib import resources
from typing import Any

import fastjsonschema
from fastjsonschema import JsonSchemaException

from stack_composer.errors import Issue

SCHEMA_FILES = {
    "profile": "profile-v1.json",
    "stack": "stack-v1.json",
    "defaults": "defaults-v1.json",
    "package-set": "package-set-v1.json",
    "release-manifest": "release-manifest-v1.json",
}


@cache
def load_schema(name: str) -> dict[str, Any]:
    try:
        filename = SCHEMA_FILES[name]
    except KeyError as exc:
        known = ", ".join(sorted(SCHEMA_FILES))
        raise ValueError(f"unknown schema {name!r}; known schemas: {known}") from exc
    text = resources.files("stack_composer.schemas").joinpath(filename).read_text(encoding="utf-8")
    return json.loads(text)


@cache
def schema_validator(name: str):
    return fastjsonschema.compile(load_schema(name))


def validate_schema(name: str, data: Any, source: str) -> list[Issue]:
    try:
        schema_validator(name)(data)
    except JsonSchemaException as exc:
        return [
            Issue(
                severity="error",
                code="schema",
                path=source,
                message=f"{name} schema validation failed: {exc.message}",
            )
        ]
    return []
