# tests/integration/test_e2e_materialization_swap_policy.py
"""Integration Suite 4: Materialization & SWAP Policy.

Purpose: Prove SWAP invariant end-to-end.

Key invariants:
- materialize=False: NO SWAPs in output
- materialize=True: SWAPs permitted, perm becomes identity
- Residual programs never materialize (unchanged)
"""
from __future__ import annotations

import pytest

from compile.to_pytket import compile, compile_goi
from compile.goi import GOIArtifact
from core.perm import identity

from .helpers import (
    mk_phase0_2_corpus,
    mk_phase3_extractable_corpus,
    mk_phase3_residual_corpus,
    mk_phase4a_extracts_more_corpus,
    has_swaps,
    perm_is_identity,
    perm_equal,
    residual_fingerprint,
    assert_no_swaps,
    assert_extracted,
    assert_residual,
)


# -----------------------------------------------------------------
# Fixtures
# -----------------------------------------------------------------

@pytest.fixture(scope="module")
def phase0_2_terms():
    return mk_phase0_2_corpus()


@pytest.fixture(scope="module")
def phase3_extractable_terms():
    return mk_phase3_extractable_corpus()


@pytest.fixture(scope="module")
def phase3_residual_terms():
    return mk_phase3_residual_corpus()


@pytest.fixture(scope="module")
def phase4a_terms():
    return mk_phase4a_extracts_more_corpus()


# -----------------------------------------------------------------
# materialize=False: No SWAPs
# -----------------------------------------------------------------

PHASE0_2_NAMES = [
    "p0_struct_twist",
    "p1_gate_seq",
    "p1_mixed_h_twist_h",
    "p2_tenterm_basic",
]


@pytest.mark.integration
@pytest.mark.parametrize("name", PHASE0_2_NAMES)
def test_materialize_false_no_swaps_compile(phase0_2_terms, name):
    """compile(materialize=False) emits no SWAPs."""
    term = phase0_2_terms[name]
    result = compile(term, materialize=False)
    assert_no_swaps(result.circuit, f"compile materialize=False: {name}")


@pytest.mark.integration
@pytest.mark.parametrize("name", PHASE0_2_NAMES)
def test_materialize_false_no_swaps_compile_goi(phase0_2_terms, name):
    """compile_goi(materialize=False) emits no SWAPs."""
    term = phase0_2_terms[name]
    result = compile_goi(term, materialize=False)
    assert_extracted(result, name)
    assert_no_swaps(result.circuit, f"compile_goi materialize=False: {name}")


PHASE3_EXT_NAMES = [
    "p3_feedback_yankable_basic",
    "p3_feedback_yankable_cx",
]


@pytest.mark.integration
@pytest.mark.parametrize("name", PHASE3_EXT_NAMES)
def test_phase3_extractable_no_swaps(phase3_extractable_terms, name):
    """Phase 3 extractable: materialize=False emits no SWAPs."""
    term = phase3_extractable_terms[name]
    result = compile_goi(term, materialize=False)
    assert_extracted(result, name)
    assert_no_swaps(result.circuit, name)


# -----------------------------------------------------------------
# materialize=True: SWAPs permitted, perm identity
# -----------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.parametrize("name", PHASE0_2_NAMES)
def test_materialize_true_perm_identity_compile(phase0_2_terms, name):
    """compile(materialize=True) results in identity perm."""
    term = phase0_2_terms[name]
    result = compile(term, materialize=True)
    assert perm_is_identity(result.perm), f"Perm should be identity after materialize: {name}"


@pytest.mark.integration
@pytest.mark.parametrize("name", PHASE0_2_NAMES)
def test_materialize_true_perm_identity_compile_goi(phase0_2_terms, name):
    """compile_goi(materialize=True) results in identity perm."""
    term = phase0_2_terms[name]
    result = compile_goi(term, materialize=True)
    assert_extracted(result, name)
    assert perm_is_identity(result.perm), f"Perm should be identity after materialize: {name}"


@pytest.mark.integration
@pytest.mark.parametrize("name", PHASE3_EXT_NAMES)
def test_phase3_materialize_true_perm_identity(phase3_extractable_terms, name):
    """Phase 3 extractable with materialize=True has identity perm."""
    term = phase3_extractable_terms[name]
    result = compile_goi(term, materialize=True)
    assert_extracted(result, name)
    assert perm_is_identity(result.perm)


# -----------------------------------------------------------------
# Residual programs: materialize has no effect
# -----------------------------------------------------------------

PHASE3_RES_NAMES = [
    "p3_feedback_residual_h_on_loop",
    "p3_feedback_residual_cx_spans",
]


@pytest.mark.integration
@pytest.mark.parametrize("name", PHASE3_RES_NAMES)
def test_residual_materialize_unchanged(phase3_residual_terms, name):
    """Residual programs: materialize flag has no effect."""
    term = phase3_residual_terms[name]

    r_nom = compile_goi(term, materialize=False)
    r_mat = compile_goi(term, materialize=True)

    # Both should be residual
    res_nom = assert_residual(r_nom, f"{name} materialize=False")
    res_mat = assert_residual(r_mat, f"{name} materialize=True")

    # Should be identical
    assert residual_fingerprint(res_nom) == residual_fingerprint(res_mat), \
        f"Residual should be unchanged by materialize flag: {name}"


@pytest.mark.integration
@pytest.mark.parametrize("name", PHASE3_RES_NAMES)
def test_residual_never_has_circuit_swaps(phase3_residual_terms, name):
    """Residual GOI artifacts don't have circuits (no SWAPs to check)."""
    term = phase3_residual_terms[name]
    result = compile_goi(term, materialize=False)

    residual = assert_residual(result, name)

    # Residual is a GOIArtifact, not a compiled circuit
    # There's no circuit to have SWAPs in
    assert isinstance(residual, GOIArtifact)


# -----------------------------------------------------------------
# Phase 4A: Same SWAP policy
# -----------------------------------------------------------------

PHASE4A_NAMES = [
    "p4a_extracts_h_disjoint",
    "p4a_extracts_s_disjoint",
]


@pytest.mark.integration
@pytest.mark.parametrize("name", PHASE4A_NAMES)
def test_phase4a_extracted_no_swaps(phase4a_terms, name):
    """Phase 4A extracted: materialize=False emits no SWAPs."""
    term = phase4a_terms[name]
    result = compile_goi(term, materialize=False)
    assert_extracted(result, name)
    assert_no_swaps(result.circuit, name)


@pytest.mark.integration
@pytest.mark.parametrize("name", PHASE4A_NAMES)
def test_phase4a_extracted_materialize_identity_perm(phase4a_terms, name):
    """Phase 4A extracted with materialize=True has identity perm."""
    term = phase4a_terms[name]
    result = compile_goi(term, materialize=True)
    assert_extracted(result, name)
    assert perm_is_identity(result.perm)
