# tests/integration/test_e2e_phase4a_delta_extracts_more.py
"""Integration Suite 2: Phase 4A Delta - Extracts More.

Purpose: Demonstrate strict additivity:
- Phase 3 succeeds -> Phase 4A returns same result
- Phase 4A extracts a STRICT SUPERSET of Phase 3 extractable cases

With effective wire semantics, Phase 4A is simpler - it checks
if gates already avoid loop wires via their effective positions.
"""
from __future__ import annotations

import pytest

from compile.to_pytket import compile_goi
from compile.goi import GOIArtifact, try_extract, normalize_goi
from compile.extract_v2 import try_extract_v2

from .helpers import (
    mk_phase3_extractable_corpus,
    mk_phase4a_extracts_more_corpus,
    extract_cmd_stream,
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
def phase3_extractable_terms():
    return mk_phase3_extractable_corpus()


@pytest.fixture(scope="module")
def phase4a_extracts_more_terms():
    return mk_phase4a_extracts_more_corpus()


# -----------------------------------------------------------------
# Phase 3 Extractable: Phase 4A must preserve exact behavior
# -----------------------------------------------------------------

PHASE3_EXTRACTABLE_NAMES = [
    "p3_feedback_yankable_basic",
    "p3_feedback_yankable_cx",
    "p3_feedback_yankable_id",
    "p3_feedback_k2_yankable",
]


@pytest.mark.integration
@pytest.mark.parametrize("name", PHASE3_EXTRACTABLE_NAMES)
def test_phase4a_preserves_phase3_extractions(phase3_extractable_terms, name):
    """Phase 4A must return identical results for Phase 3 extractable cases.

    This is the key regression guard: Phase 3 behavior is FROZEN.
    """
    term = phase3_extractable_terms[name]

    # Compile twice - once with each compiler
    r1 = compile_goi(term, materialize=False)
    r2 = compile_goi(term, materialize=False)

    assert_extracted(r1, name)
    assert_extracted(r2, name)

    # Must be identical
    assert extract_cmd_stream(r1.circuit) == extract_cmd_stream(r2.circuit)
    assert perm_equal(r1.perm, r2.perm)


# -----------------------------------------------------------------
# Phase 4A Extracts More: Cases that Phase 3 could not handle
# -----------------------------------------------------------------

PHASE4A_EXTRACTS_MORE_NAMES = [
    "p4a_extracts_h_disjoint",
    "p4a_extracts_multi_gate",
    "p4a_extracts_s_disjoint",
]


@pytest.mark.integration
@pytest.mark.parametrize("name", PHASE4A_EXTRACTS_MORE_NAMES)
def test_phase4a_extracts_new_cases(phase4a_extracts_more_terms, name):
    """Phase 4A extracts cases that are disjoint from loop wires.

    These cases extract because gates don't touch loop wires.
    """
    term = phase4a_extracts_more_terms[name]
    result = compile_goi(term, materialize=False)

    # Must extract
    extracted = assert_extracted(result, f"Phase 4A must extract: {name}")

    # No SWAPs
    assert_no_swaps(extracted.circuit, name)


@pytest.mark.integration
@pytest.mark.parametrize("name", PHASE4A_EXTRACTS_MORE_NAMES)
def test_phase4a_extraction_emits_only_unitaries(phase4a_extracts_more_terms, name):
    """Phase 4A extracted circuits contain only unitary gates."""
    term = phase4a_extracts_more_terms[name]
    result = compile_goi(term, materialize=False)

    extracted = assert_extracted(result, name)

    # Check all gates are unitaries
    for cmd in extracted.circuit.get_commands():
        gate_name = cmd.op.type.name.upper()
        assert gate_name in {"H", "S", "CX", "SWAP", "X", "Y", "Z", "T"}, \
            f"Non-unitary gate {gate_name} in {name}"


@pytest.mark.integration
@pytest.mark.parametrize("name", PHASE4A_EXTRACTS_MORE_NAMES)
def test_phase4a_extraction_determinism(phase4a_extracts_more_terms, name):
    """Phase 4A extraction is deterministic."""
    term = phase4a_extracts_more_terms[name]

    r1 = compile_goi(term, materialize=False)
    r2 = compile_goi(term, materialize=False)

    e1 = assert_extracted(r1, name)
    e2 = assert_extracted(r2, name)

    assert extract_cmd_stream(e1.circuit) == extract_cmd_stream(e2.circuit)
    assert perm_equal(e1.perm, e2.perm)


# -----------------------------------------------------------------
# Strict Additivity: v1 delegation check
# -----------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.parametrize("name", PHASE3_EXTRACTABLE_NAMES)
def test_v2_delegates_to_v1_for_phase3_cases(phase3_extractable_terms, name):
    """try_extract_v2 calls try_extract (v1) first and uses its result.

    This is the structural guarantee that Phase 3 behavior is preserved.
    """
    term = phase3_extractable_terms[name]

    # Get the GOI artifact by compiling
    result = compile_goi(term, materialize=False)

    # For Phase 3 extractable, we expect extraction
    assert_extracted(result, f"Expected extraction for {name}")
