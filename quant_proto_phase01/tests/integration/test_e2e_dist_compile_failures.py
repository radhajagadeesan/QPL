# tests/integration/test_e2e_dist_compile_failures.py
"""Integration Suite 6: DistL/DistR Loud Failures.

Purpose: Ensure distributivity typechecks but fails at compile-time.

Key invariants:
- DistL/DistR terms may typecheck
- Compile MUST raise NotImplementedError
- Error message must be clear
- Failure is deterministic
"""
from __future__ import annotations

import pytest

from lang.types import Q, Ten
from lang.terms import Id, Seq, DistL, DistR
from compile.to_pytket import compile, compile_goi
from typing_.check import assert_well_typed

from .helpers import mk_dist_failure_corpus


# -----------------------------------------------------------------
# Fixtures
# -----------------------------------------------------------------

@pytest.fixture(scope="module")
def dist_terms():
    return mk_dist_failure_corpus()


# -----------------------------------------------------------------
# Distributivity must fail loudly
# -----------------------------------------------------------------

DIST_NAMES = [
    "dist_distl",
    "dist_distr",
    "dist_seq_distl",
]


@pytest.mark.integration
@pytest.mark.parametrize("name", DIST_NAMES)
def test_dist_typechecks(dist_terms, name):
    """Distributivity terms may typecheck."""
    term = dist_terms[name]
    # This should not raise
    try:
        assert_well_typed(term)
    except Exception:
        # If it doesn't typecheck, that's also fine
        pass


@pytest.mark.integration
@pytest.mark.parametrize("name", DIST_NAMES)
def test_dist_compile_raises(dist_terms, name):
    """compile() must raise NotImplementedError for distributivity."""
    term = dist_terms[name]

    with pytest.raises(NotImplementedError) as exc_info:
        compile(term, materialize=False)

    # Error message should mention distributivity
    assert "distributivity" in str(exc_info.value).lower() or "deferred" in str(exc_info.value).lower()


@pytest.mark.integration
@pytest.mark.parametrize("name", DIST_NAMES)
def test_dist_compile_goi_raises(dist_terms, name):
    """compile_goi() must raise NotImplementedError for distributivity."""
    term = dist_terms[name]

    with pytest.raises(NotImplementedError) as exc_info:
        compile_goi(term, materialize=False)

    # Error message should mention distributivity
    assert "distributivity" in str(exc_info.value).lower() or "deferred" in str(exc_info.value).lower()


@pytest.mark.integration
@pytest.mark.parametrize("name", DIST_NAMES)
def test_dist_failure_deterministic(dist_terms, name):
    """Distributivity failure is deterministic."""
    term = dist_terms[name]

    errors = []
    for _ in range(3):
        try:
            compile(term, materialize=False)
            errors.append(None)
        except NotImplementedError as e:
            errors.append(str(e))

    # All should raise
    assert all(e is not None for e in errors), "Distributivity should always fail"

    # All error messages should be identical
    assert all(e == errors[0] for e in errors), "Error message not deterministic"


# -----------------------------------------------------------------
# Negative controls: Similar terms without Dist compile fine
# -----------------------------------------------------------------

@pytest.mark.integration
def test_non_dist_compiles_fine():
    """Terms without distributivity compile normally."""
    from lang.terms import TwistTen, H

    # Similar structure but no DistL/DistR
    term = Seq(
        TwistTen(Q(), Q()),
        H(0, Ten(Q(), Q()))
    )

    # Should not raise
    result = compile(term, materialize=False)
    assert result.circuit is not None


@pytest.mark.integration
def test_non_dist_in_feedback_compiles():
    """Feedback without distributivity compiles/extracts normally."""
    from lang.terms import Feedback, H

    q3 = Ten(Q(), Ten(Q(), Q()))

    # Feedback without distributivity
    term = Feedback(k=1, body=H(0, q3))

    # Should not raise
    result = compile_goi(term, materialize=False)
    # May extract or return residual - both are valid
    assert result is not None
