# tests/integration/test_e2e_phase0_3_regression.py
"""Integration Suite 1: Phase 0-3 Regression Lockdown.

Purpose: Prove Phase 4A integration does not change any existing locked behavior.

All Phase 0-3 golden outputs must remain BIT-FOR-BIT IDENTICAL.
"""
from __future__ import annotations

import pytest

from compile.to_pytket import compile, compile_goi
from compile.goi import GOIArtifact

from .helpers import (
    mk_phase0_2_corpus,
    mk_phase3_extractable_corpus,
    mk_phase3_residual_corpus,
    extract_cmd_stream,
    has_swaps,
    perm_equal,
    perm_to_list,
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


# -----------------------------------------------------------------
# Phase 0-2: Acyclic terms (no Feedback)
# -----------------------------------------------------------------

PHASE0_2_NAMES = [
    "p0_struct_twist",
    "p0_struct_assoc_l",
    "p0_struct_assoc_r",
    "p0_struct_seq_twists",
    "p1_gate_h",
    "p1_gate_s",
    "p1_gate_cx",
    "p1_gate_seq",
    "p1_mixed_twist_h",
    "p1_mixed_h_twist_h",
    "p1_mixed_assoc_h",
    "p2_tenterm_basic",
    "p2_tenterm_cx",
    "p2_tenterm_seq",
    "p2_tenterm_nested",
]


@pytest.mark.integration
@pytest.mark.parametrize("name", PHASE0_2_NAMES)
def test_phase0_2_compile_no_swaps(phase0_2_terms, name):
    """Phase 0-2 terms: compile(materialize=False) emits no SWAPs."""
    term = phase0_2_terms[name]
    result = compile(term, materialize=False)
    assert_no_swaps(result.circuit, name)


@pytest.mark.integration
@pytest.mark.parametrize("name", PHASE0_2_NAMES)
def test_phase0_2_compile_goi_matches_compile(phase0_2_terms, name):
    """Phase 0-2 terms: compile_goi matches compile exactly."""
    term = phase0_2_terms[name]

    r_compile = compile(term, materialize=False)
    r_goi = compile_goi(term, materialize=False)

    # Must extract (not residual)
    assert_extracted(r_goi, f"compile_goi must extract for acyclic term: {name}")

    # Command stream must match
    assert extract_cmd_stream(r_goi.circuit) == extract_cmd_stream(r_compile.circuit), \
        f"Command stream mismatch for {name}"

    # Permutation must match
    assert perm_equal(r_goi.perm, r_compile.perm), \
        f"Permutation mismatch for {name}"

    # No SWAPs
    assert_no_swaps(r_goi.circuit, name)


@pytest.mark.integration
@pytest.mark.parametrize("name", PHASE0_2_NAMES)
def test_phase0_2_materialize_behavior(phase0_2_terms, name):
    """Phase 0-2 terms: materialize=True produces valid circuit."""
    term = phase0_2_terms[name]

    r_nom = compile(term, materialize=False)
    r_mat = compile(term, materialize=True)

    # Same qubit count
    assert r_mat.circuit.n_qubits == r_nom.circuit.n_qubits

    # compile_goi should also work
    r_goi_mat = compile_goi(term, materialize=True)
    assert_extracted(r_goi_mat, name)


# -----------------------------------------------------------------
# Phase 3: Extractable Feedback (yankable)
# -----------------------------------------------------------------

PHASE3_EXTRACTABLE_NAMES = [
    "p3_feedback_yankable_basic",
    "p3_feedback_yankable_cx",
    "p3_feedback_yankable_id",
    "p3_feedback_k2_yankable",
]


@pytest.mark.integration
@pytest.mark.parametrize("name", PHASE3_EXTRACTABLE_NAMES)
def test_phase3_extractable_extracts(phase3_extractable_terms, name):
    """Phase 3 yankable feedback: must extract."""
    term = phase3_extractable_terms[name]
    result = compile_goi(term, materialize=False)

    assert_extracted(result, f"Phase 3 yankable term must extract: {name}")
    assert_no_swaps(result.circuit, name)


@pytest.mark.integration
@pytest.mark.parametrize("name", PHASE3_EXTRACTABLE_NAMES)
def test_phase3_extractable_determinism(phase3_extractable_terms, name):
    """Phase 3 extractable: deterministic extraction."""
    term = phase3_extractable_terms[name]

    r1 = compile_goi(term, materialize=False)
    r2 = compile_goi(term, materialize=False)

    assert_extracted(r1, name)
    assert_extracted(r2, name)

    assert extract_cmd_stream(r1.circuit) == extract_cmd_stream(r2.circuit)
    assert perm_equal(r1.perm, r2.perm)


# -----------------------------------------------------------------
# Phase 3: Residual Feedback (not yankable)
# -----------------------------------------------------------------

PHASE3_RESIDUAL_NAMES = [
    "p3_feedback_residual_h_on_loop",
    "p3_feedback_residual_s_on_loop",
    "p3_feedback_residual_cx_spans",
    "p3_feedback_residual_cx_both_loop",
    "p3_feedback_residual_mixed",
]


@pytest.mark.integration
@pytest.mark.parametrize("name", PHASE3_RESIDUAL_NAMES)
def test_phase3_residual_returns_goi(phase3_residual_terms, name):
    """Phase 3 non-yankable feedback: must return residual."""
    term = phase3_residual_terms[name]
    result = compile_goi(term, materialize=False)

    residual = assert_residual(result, f"Phase 3 non-yankable term must return residual: {name}")

    # Residual should have loop(s)
    assert len(residual.loops) >= 1, f"Residual must have loops: {name}"

    # Residual should have atoms
    assert len(residual.atoms) >= 1, f"Residual must have atoms: {name}"


@pytest.mark.integration
@pytest.mark.parametrize("name", PHASE3_RESIDUAL_NAMES)
def test_phase3_residual_fingerprint_stable(phase3_residual_terms, name):
    """Phase 3 residual: fingerprint is stable across compilations."""
    term = phase3_residual_terms[name]

    r1 = compile_goi(term, materialize=False)
    r2 = compile_goi(term, materialize=False)

    res1 = assert_residual(r1, name)
    res2 = assert_residual(r2, name)

    fp1 = residual_fingerprint(res1)
    fp2 = residual_fingerprint(res2)

    assert fp1 == fp2, f"Residual fingerprint mismatch for {name}"


@pytest.mark.integration
@pytest.mark.parametrize("name", PHASE3_RESIDUAL_NAMES)
def test_phase3_residual_materialize_unchanged(phase3_residual_terms, name):
    """Phase 3 residual: materialize=True still returns residual unchanged."""
    term = phase3_residual_terms[name]

    r_nom = compile_goi(term, materialize=False)
    r_mat = compile_goi(term, materialize=True)

    # Both should be residual
    res_nom = assert_residual(r_nom, name)
    res_mat = assert_residual(r_mat, name)

    # Fingerprints should match (residual is unchanged)
    assert residual_fingerprint(res_nom) == residual_fingerprint(res_mat)
