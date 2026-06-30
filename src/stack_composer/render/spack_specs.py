from __future__ import annotations

import re

_PACKAGE_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
_VERSION_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.+:-]*$")


def is_spack_package_name(value: object) -> bool:
    return isinstance(value, str) and bool(_PACKAGE_RE.fullmatch(value))


def is_spack_version(value: object) -> bool:
    return isinstance(value, str) and bool(_VERSION_RE.fullmatch(value))


def is_renderable_external_name_version(name: object, version: object) -> bool:
    return is_spack_package_name(name) and is_spack_version(version)


def is_absolute_prefix(value: object) -> bool:
    return isinstance(value, str) and value.startswith("/")


def is_compiler_fragment(value: object) -> bool:
    if not isinstance(value, str) or not value:
        return False
    if "@" not in value:
        return is_spack_package_name(value)
    name, version = value.split("@", 1)
    return is_renderable_external_name_version(name, version)


def external_spec(name: str, version: str, suffix: str = "") -> str:
    spec = f"{name}@{version}"
    if suffix:
        spec += f" {suffix}"
    return spec
