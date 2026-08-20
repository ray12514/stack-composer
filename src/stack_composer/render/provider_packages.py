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

# Runtime packages that must remain platform externals when the corresponding
# MPI provider is external. Both constraints are attached to the external MPI
# DAG. Libfabric is configured by the common scope; Cray PMI is configured in
# the provider scope because it is specific to Cray MPICH.
_MPI_RUNTIME_DEPENDENCIES = {
    "cray-mpich": ("libfabric", "cray-pmi"),
}

_MPI_SCOPE_DEPENDENCIES = {
    "cray-mpich": ("cray-pmi",),
}

# Provider-owned runtime search paths that must be present when Spack uses an
# external MPI from a clean build environment.  Keep this mapping at the
# provider adapter seam: the renderer selects the observed dependency version
# and prefix, while this table owns only the product-tree layout.
_MPI_RUNTIME_ENVIRONMENT_PATHS = {
    "cray-mpich": {
        "libfabric": ("LD_LIBRARY_PATH", "lib64"),
    },
}


def compiler_package_name(provider: dict[str, Any] | str) -> str:
    name = str(provider.get("name") if isinstance(provider, dict) else provider)
    return _COMPILER_PACKAGES.get(name, name)


def mpi_package_name(provider: dict[str, Any] | str) -> str:
    name = str(provider.get("name") if isinstance(provider, dict) else provider)
    return _MPI_PACKAGES.get(name, name)


def mpi_runtime_dependency_names(provider: dict[str, Any] | str) -> tuple[str, ...]:
    name = str(provider.get("name") if isinstance(provider, dict) else provider)
    return _MPI_RUNTIME_DEPENDENCIES.get(name, ())


def mpi_scope_dependency_names(provider: dict[str, Any] | str) -> tuple[str, ...]:
    name = str(provider.get("name") if isinstance(provider, dict) else provider)
    return _MPI_SCOPE_DEPENDENCIES.get(name, ())


def mpi_runtime_environment_paths(
    provider: dict[str, Any] | str,
) -> dict[str, tuple[str, str]]:
    """Return dependency-to-environment mappings for one external MPI."""
    name = str(provider.get("name") if isinstance(provider, dict) else provider)
    return dict(_MPI_RUNTIME_ENVIRONMENT_PATHS.get(name, {}))
