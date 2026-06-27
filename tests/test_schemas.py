from __future__ import annotations

from stack_composer.schema_registry import SCHEMA_FILES, load_schema, validate_schema
from stack_composer.yaml_io import load_yaml
from tests.conftest import fixture_path


def test_packaged_schemas_load() -> None:
    for name in SCHEMA_FILES:
        schema = load_schema(name)
        assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"


def test_positive_fixtures_validate_against_schemas() -> None:
    cases = [
        ("profile", fixture_path("profiles", "example-cray", "profile.yaml")),
        ("profile", fixture_path("profiles", "example-linux", "profile.yaml")),
        ("stack", fixture_path("stacks", "science-stack", "stack.yaml")),
        ("defaults", fixture_path("template-sets", "v6", "defaults.yaml")),
        ("package-set", fixture_path("package-sets", "science-full.yaml")),
        ("package-set", fixture_path("package-sets", "core-foundation.yaml")),
        ("release-manifest", fixture_path("manifests", "release-manifest-draft.yaml")),
        ("release-manifest", fixture_path("manifests", "release-manifest-final.yaml")),
    ]
    for schema_name, path in cases:
        assert validate_schema(schema_name, load_yaml(path), str(path)) == []
