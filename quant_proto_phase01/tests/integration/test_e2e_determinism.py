# tests/integration/test_e2e_determinism.py
"""Integration Suite 5: Determinism & Stability.

Purpose: Enforce "same AST => identical output".

All compilation paths must be deterministic:
- Same term -> identical command stream
- Same term -> identical permutation
- Same term -> identical residual fingerprint
"""
from __future__ import annotations

import pytest

from compile.to_pytket import compile, compile_goi
from compile.goi import GOIArtifact

from .helpers import (
    mk_phase0_2_corpus,
    mk_phase3_extractable_corpus,
    mk_phase3_residual_corpus,
    mk_phase4a_extracts_more_corpus,
    mk_phase4a_stays_residual_corpus,
    extract_cmd_stream,
    perm_equal,
    residual_fingerprint,
    assert_extracted,
    assert_residual,
)


# -----------------------------------------------------------------
# Fixtures
# -----------------------------------------------------------------

@pytest.fixture(scope="module")
def all_terms():
    """Combined corpus for determinism testing."""
    terms = {}
    terms.update(mk_phase0_2_corpus())
    terms.update(mk_phase3_extractable_corpus())
    terms.update(mk_phase3_residual_corpus())
    terms.update(mk_phase4a_extracts_more_corpus())
    terms.update(mk_phase4a_stays_residual_corpus())
    return terms


# -----------------------------------------------------------------
# Phase 0-2: compile() determinism
# -----------------------------------------------------------------

PHASE0_2_NAMES = [
    "p0_struct_twist",
    "p0_struct_assoc_l",
    "p1_gate_seq",
    "p1_mixed_h_twist_h",
    "p2_tenterm_basic",
    "p2_tenterm_seq",
]


@pytest.mark.integration
@pytest.mark.parametrize("name", PHASE0_2_NAMES)
def test_compile_deterministic(all_terms, name):
    """compile() is deterministic: N runs produce identical results."""
    term = all_terms[name]

    results = [compile(term, materialize=False) for _ in range(5)]

    # All command streams must be identical
    cmd_streams = [extract_cmd_stream(r.circuit) for r in results]
    assert all(c == cmd_streams[0] for c in cmd_streams), f"Command stream not deterministic: {name}"

    # All perms must be identical
    assert all(perm_equal(r.perm, results[0].perm) for r in results), f"Perm not deterministic: {name}"


@pytest.mark.integration
@pytest.mark.parametrize("name", PHASE0_2_NAMES)
def test_compile_goi_deterministic_phase0_2(all_terms, name):
    """compile_goi() is deterministic for Phase 0-2 terms."""
    term = all_terms[name]

    results = [compile_goi(term, materialize=False) for _ in range(5)]

    # All should extract
    for r in results:
        assert_extracted(r, name)

    # All command streams must be identical
    cmd_streams = [extract_cmd_stream(r.circuit) for r in results]
    assert all(c == cmd_streams[0] for c in cmd_streams)

    # All perms must be identical
    assert all(perm_equal(r.perm, results[0].perm) for r in results)


# -----------------------------------------------------------------
# Phase 3: Extractable determinism
# -----------------------------------------------------------------

PHASE3_EXT_NAMES = [
    "p3_feedback_yankable_basic",
    "p3_feedback_yankable_cx",
    "p3_feedback_yankable_id",
]


@pytest.mark.integration
@pytest.mark.parametrize("name", PHASE3_EXT_NAMES)
def test_phase3_extractable_deterministic(all_terms, name):
    """Phase 3 extractable terms are deterministic."""
    term = all_terms[name]

    results = [compile_goi(term, materialize=False) for _ in range(5)]

    for r in results:
        assert_extracted(r, name)

    cmd_streams = [extract_cmd_stream(r.circuit) for r in results]
    assert all(c == cmd_streams[0] for c in cmd_streams)

    assert all(perm_equal(r.perm, results[0].perm) for r in results)


# -----------------------------------------------------------------
# Phase 3: Residual determinism
# -----------------------------------------------------------------

PHASE3_RES_NAMES = [
    "p3_feedback_residual_h_on_loop",
    "p3_feedback_residual_cx_spans",
    "p3_feedback_residual_mixed",
]


@pytest.mark.integration
@pytest.mark.parametrize("name", PHASE3_RES_NAMES)
def test_phase3_residual_deterministic(all_terms, name):
    """Phase 3 residual terms produce deterministic fingerprints."""
    term = all_terms[name]

    results = [compile_goi(term, materialize=False) for _ in range(5)]

    for r in results:
        assert_residual(r, name)

    fingerprints = [residual_fingerprint(r) for r in results]
    assert all(fp == fingerprints[0] for fp in fingerprints), f"Residual fingerprint not deterministic: {name}"


# -----------------------------------------------------------------
# Phase 4A: Determinism
# -----------------------------------------------------------------

PHASE4A_EXT_NAMES = [
    "p4a_extracts_h_disjoint",
    "p4a_extracts_s_disjoint",
]

PHASE4A_RES_NAMES = [
    "p4a_residual_h_on_loop",
    "p4a_residual_cx_spans_loop",
]


@pytest.mark.integration
@pytest.mark.parametrize("name", PHASE4A_EXT_NAMES)
def test_phase4a_extracted_deterministic(all_terms, name):
    """Phase 4A extracted terms are deterministic."""
    term = all_terms[name]

    results = [compile_goi(term, materialize=False) for _ in range(5)]

    for r in results:
        assert_extracted(r, name)

    cmd_streams = [extract_cmd_stream(r.circuit) for r in results]
    assert all(c == cmd_streams[0] for c in cmd_streams)

    assert all(perm_equal(r.perm, results[0].perm) for r in results)


@pytest.mark.integration
@pytest.mark.parametrize("name", PHASE4A_RES_NAMES)
def test_phase4a_residual_deterministic(all_terms, name):
    """Phase 4A residual terms produce deterministic fingerprints."""
    term = all_terms[name]

    results = [compile_goi(term, materialize=False) for _ in range(5)]

    for r in results:
        assert_residual(r, name)

    fingerprints = [residual_fingerprint(r) for r in results]
    assert all(fp == fingerprints[0] for fp in fingerprints)


# -----------------------------------------------------------------
# Cross-compilation determinism
# -----------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.parametrize("name", PHASE0_2_NAMES)
def test_compile_vs_compile_goi_deterministic(all_terms, name):
    """compile() and compile_goi() produce identical results for Phase 0-2."""
    term = all_terms[name]

    r_compile = compile(term, materialize=False)
    r_goi = compile_goi(term, materialize=False)

    assert_extracted(r_goi, name)

    assert extract_cmd_stream(r_compile.circuit) == extract_cmd_stream(r_goi.circuit)
    assert perm_equal(r_compile.perm, r_goi.perm)
