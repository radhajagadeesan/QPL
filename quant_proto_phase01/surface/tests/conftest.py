"""Pytest configuration for surface language tests.

Skips OCaml-dependent tests when dune is not available in PATH.
"""

import shutil
import pytest


def dune_available():
    """Check if dune is available in PATH."""
    return shutil.which('dune') is not None


# Skip marker for tests requiring dune
requires_dune = pytest.mark.skipif(
    not dune_available(),
    reason="dune not available in PATH (run: eval $(opam env))"
)


def pytest_collection_modifyitems(config, items):
    """Auto-skip tests that call dune when it's not available."""
    if dune_available():
        return

    skip_dune = pytest.mark.skip(reason="dune not available in PATH (run: eval $(opam env))")

    for item in items:
        # Skip tests in surface/tests that likely need dune
        if 'surface/tests' in str(item.fspath):
            item.add_marker(skip_dune)
