# tests/integration/test_e2e_residual_preservation.py
"""Integration Suite 7: Residual Preservation.

Purpose: Ensure extractor never mutates residuals unpredictably.

Key invariants:
- Residual artifacts are preserved exactly
- Multiple compilations produce identical residuals
- Debug flags don't alter residual data model
"""
from __future__ import annotations

import pytest

from compile.to_pytket import compile_goi
from compile.goi import GOIArtifact

from .helpers import (
    mk_phase3_residual_corpus,
    mk_phase4a_stays_residual_corpus,
    residual_fingerprint,
    atoms_equal,
    perm_equal,
    assert_residual,
)


# -----------------------------------------------------------------
# Fixtures
# -----------------------------------------------------------------

@pytest.fixture(scope="module")
def phase3_residual_terms():
    return mk_phase3_residual_corpus()


@pytest.fixture(scope="module")
def phase4a_residual_terms():
    return mk_phase4a_stays_residual_corpus()


# -----------------------------------------------------------------
# Phase 3 Residual Preservation
# -----------------------------------------------------------------

PHASE3_RES_NAMES = [
    "p3_feedback_residual_h_on_loop",
    "p3_feedback_residual_s_on_loop",
    "p3_feedback_residual_cx_spans",
    "p3_feedback_residual_cx_both_loop",
    "p3_feedback_residual_mixed",
]


@pytest.mark.integration
@pytest.mark.parametrize("name", PHASE3_RES_NAMES)
def test_phase3_residual_fingerprint_identical(phase3_residual_terms, name):
    """Phase 3 residual: fingerprint identical across compilations."""
    term = phase3_residual_terms[name]

    results = [compile_goi(term, materialize=False) for _ in range(5)]

    for r in results:
        assert_residual(r, name)

    fingerprints = [residual_fingerprint(r) for r in results]
    assert all(fp == fingerprints[0] for fp in fingerprints)


@pytest.mark.integration
@pytest.mark.parametrize("name", PHASE3_RES_NAMES)
def test_phase3_residual_atoms_preserved(phase3_residual_terms, name):
    """Phase 3 residual: atoms are exactly preserved."""
    term = phase3_residual_terms[name]

    r1 = compile_goi(term, materialize=False)
    r2 = compile_goi(term, materialize=False)

    res1 = assert_residual(r1, name)
    res2 = assert_residual(r2, name)

    assert atoms_equal(res1.atoms, res2.atoms)


@pytest.mark.integration
@pytest.mark.parametrize("name", PHASE3_RES_NAMES)
def test_phase3_residual_loops_preserved(phase3_residual_terms, name):
    """Phase 3 residual: loop structure is exactly preserved."""
    term = phase3_residual_terms[name]

    r1 = compile_goi(term, materialize=False)
    r2 = compile_goi(term, materialize=False)

    res1 = assert_residual(r1, name)
    res2 = assert_residual(r2, name)

    assert len(res1.loops) == len(res2.loops)
    for l1, l2 in zip(res1.loops, res2.loops):
        assert l1.k == l2.k


@pytest.mark.integration
@pytest.mark.parametrize("name", PHASE3_RES_NAMES)
def test_phase3_residual_perm_preserved(phase3_residual_terms, name):
    """Phase 3 residual: permutation is preserved."""
    term = phase3_residual_terms[name]

    r1 = compile_goi(term, materialize=False)
    r2 = compile_goi(term, materialize=False)

    res1 = assert_residual(r1, name)
    res2 = assert_residual(r2, name)

    assert perm_equal(res1.perm, res2.perm)


# -----------------------------------------------------------------
# Phase 4A Residual Preservation
# -----------------------------------------------------------------

PHASE4A_RES_NAMES = [
    "p4a_residual_h_on_loop",
    "p4a_residual_cx_spans_loop",
    "p4a_residual_mixed_touch",
    "p4a_residual_cx_both_loop",
]


@pytest.mark.integration
@pytest.mark.parametrize("name", PHASE4A_RES_NAMES)
def test_phase4a_residual_fingerprint_identical(phase4a_residual_terms, name):
    """Phase 4A residual: fingerprint identical across compilations."""
    term = phase4a_residual_terms[name]

    results = [compile_goi(term, materialize=False) for _ in range(5)]

    for r in results:
        assert_residual(r, name)

    fingerprints = [residual_fingerprint(r) for r in results]
    assert all(fp == fingerprints[0] for fp in fingerprints)


@pytest.mark.integration
@pytest.mark.parametrize("name", PHASE4A_RES_NAMES)
def test_phase4a_residual_atoms_preserved(phase4a_residual_terms, name):
    """Phase 4A residual: atoms are exactly preserved."""
    term = phase4a_residual_terms[name]

    r1 = compile_goi(term, materialize=False)
    r2 = compile_goi(term, materialize=False)

    res1 = assert_residual(r1, name)
    res2 = assert_residual(r2, name)

    assert atoms_equal(res1.atoms, res2.atoms)


# -----------------------------------------------------------------
# Materialize flag doesn't alter residuals
# -----------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.parametrize("name", PHASE3_RES_NAMES)
def test_materialize_flag_does_not_alter_residual(phase3_residual_terms, name):
    """Materialize flag should not alter residual artifact."""
    term = phase3_residual_terms[name]

    r_false = compile_goi(term, materialize=False)
    r_true = compile_goi(term, materialize=True)

    res_false = assert_residual(r_false, name)
    res_true = assert_residual(r_true, name)

    # Fingerprints should be identical
    assert residual_fingerprint(res_false) == residual_fingerprint(res_true)


# -----------------------------------------------------------------
# Explain flag doesn't alter residuals
# -----------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.parametrize("name", PHASE3_RES_NAMES[:2])
def test_explain_flag_does_not_alter_residual(phase3_residual_terms, name):
    """Explain flag should not alter residual artifact data model."""
    term = phase3_residual_terms[name]

    r_no_explain = compile_goi(term, materialize=False, explain=False)
    r_explain = compile_goi(term, materialize=False, explain=True)

    res_no = assert_residual(r_no_explain, name)
    res_yes = assert_residual(r_explain, name)

    # Fingerprints should be identical
    assert residual_fingerprint(res_no) == residual_fingerprint(res_yes)
