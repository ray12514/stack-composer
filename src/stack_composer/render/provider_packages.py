"""Map observed provider identities to Spack package identities.

Profiles describe software as the system exposes it. Spack occasionally uses
a different package name for that provider. Keep those package-manager details
at this renderer seam instead of changing observed profile facts or spreading
vendor checks through templates.
"""

from __future__ import annotations

from typing import Any

_COMPILER_PACKAGES = {
    "intel": "intel-oneapi-compilers-classic",
    "oneapi": "intel-oneapi-compilers",
}

_MPI_PACKAGES = {
    "intel-mpi": "intel-oneapi-mpi",
}


def compiler_package_name(provider: dict[str, Any] | str) -> str:
    name = str(provider.get("name") if isinstance(provider, dict) else provider)
    return _COMPILER_PACKAGES.get(name, name)


def mpi_package_name(provider: dict[str, Any] | str) -> str:
    name = str(provider.get("name") if isinstance(provider, dict) else provider)
    return _MPI_PACKAGES.get(name, name)
