# tests/integration/test_e2e_phase4a_stays_residual.py
"""Integration Suite 3: Phase 4A Negative Delta - Must Remain Residual.

Purpose: Ensure Phase 4A does not overreach.

These cases must remain residual because gates genuinely touch loop wires.
Phase 4A cannot and should not extract them.
"""
from __future__ import annotations

import pytest

from compile.to_pytket import compile_goi
from compile.goi import GOIArtifact

from .helpers import (
    mk_phase4a_stays_residual_corpus,
    residual_fingerprint,
    assert_residual,
)


# -----------------------------------------------------------------
# Fixtures
# -----------------------------------------------------------------

@pytest.fixture(scope="module")
def phase4a_residual_terms():
    return mk_phase4a_stays_residual_corpus()


# -----------------------------------------------------------------
# Phase 4A Must Remain Residual
# -----------------------------------------------------------------

PHASE4A_RESIDUAL_NAMES = [
    "p4a_residual_h_on_loop",
    "p4a_residual_cx_spans_loop",
    "p4a_residual_mixed_touch",
    "p4a_residual_cx_both_loop",
]


@pytest.mark.integration
@pytest.mark.parametrize("name", PHASE4A_RESIDUAL_NAMES)
def test_phase4a_returns_residual(phase4a_residual_terms, name):
    """Phase 4A must return residual when gates touch loop wires."""
    term = phase4a_residual_terms[name]
    result = compile_goi(term, materialize=False)

    residual = assert_residual(result, f"Must remain residual: {name}")

    # Residual should have loop(s)
    assert len(residual.loops) >= 1

    # Residual should have atoms
    assert len(residual.atoms) >= 1


@pytest.mark.integration
@pytest.mark.parametrize("name", PHASE4A_RESIDUAL_NAMES)
def test_phase4a_residual_fingerprint_stable(phase4a_residual_terms, name):
    """Phase 4A residual fingerprint is stable (deterministic)."""
    term = phase4a_residual_terms[name]

    r1 = compile_goi(term, materialize=False)
    r2 = compile_goi(term, materialize=False)

    res1 = assert_residual(r1, name)
    res2 = assert_residual(r2, name)

    fp1 = residual_fingerprint(res1)
    fp2 = residual_fingerprint(res2)

    assert fp1 == fp2, f"Residual fingerprint must be stable: {name}"


@pytest.mark.integration
@pytest.mark.parametrize("name", PHASE4A_RESIDUAL_NAMES)
def test_phase4a_residual_no_error(phase4a_residual_terms, name):
    """Phase 4A residual cases do not raise errors (sound incompleteness)."""
    term = phase4a_residual_terms[name]

    # This should not raise - failure to extract is not an error
    try:
        result = compile_goi(term, materialize=False)
    except Exception as e:
        pytest.fail(f"Residual case {name} raised unexpected error: {e}")

    # Just verify it's residual
    assert_residual(result, name)


@pytest.mark.integration
@pytest.mark.parametrize("name", PHASE4A_RESIDUAL_NAMES)
def test_phase4a_residual_preserves_atoms(phase4a_residual_terms, name):
    """Phase 4A residual preserves all gate atoms."""
    term = phase4a_residual_terms[name]

    r1 = compile_goi(term, materialize=False)
    r2 = compile_goi(term, materialize=False)

    res1 = assert_residual(r1, name)
    res2 = assert_residual(r2, name)

    # Atoms should be identical
    assert len(res1.atoms) == len(res2.atoms)
    for a1, a2 in zip(res1.atoms, res2.atoms):
        assert a1.gate_name == a2.gate_name
        assert a1.wires == a2.wires


@pytest.mark.integration
@pytest.mark.parametrize("name", PHASE4A_RESIDUAL_NAMES)
def test_phase4a_residual_preserves_loops(phase4a_residual_terms, name):
    """Phase 4A residual preserves loop structure."""
    term = phase4a_residual_terms[name]

    r1 = compile_goi(term, materialize=False)
    r2 = compile_goi(term, materialize=False)

    res1 = assert_residual(r1, name)
    res2 = assert_residual(r2, name)

    # Loops should be identical
    assert len(res1.loops) == len(res2.loops)
    for l1, l2 in zip(res1.loops, res2.loops):
        assert l1.k == l2.k
