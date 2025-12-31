# tests/integration/test_e2e_backend_pytket_sanity.py
"""Integration Suite 8: Backend Sanity (pytket).

Purpose: Prove that extracted circuits are valid pytket objects.

Key invariants:
- Circuits build successfully
- Gate set is within allowed unitary operations
- No SWAPs when materialize=False
- Circuit properties are valid
"""
from __future__ import annotations

import pytest

from pytket import Circuit

from compile.to_pytket import compile, compile_goi
from compile.goi import GOIArtifact

from .helpers import (
    mk_phase0_2_corpus,
    mk_phase3_extractable_corpus,
    mk_phase4a_extracts_more_corpus,
    has_swaps,
    get_gate_names,
    is_unitary_only,
    assert_extracted,
    assert_no_swaps,
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
def phase4a_terms():
    return mk_phase4a_extracts_more_corpus()


# -----------------------------------------------------------------
# Pytket Circuit Validity
# -----------------------------------------------------------------

PHASE0_2_NAMES = [
    "p0_struct_twist",
    "p1_gate_seq",
    "p1_mixed_h_twist_h",
    "p2_tenterm_basic",
]


@pytest.mark.integration
@pytest.mark.parametrize("name", PHASE0_2_NAMES)
def test_pytket_circuit_is_valid(phase0_2_terms, name):
    """Compiled circuits are valid pytket Circuit objects."""
    term = phase0_2_terms[name]
    result = compile(term, materialize=False)

    # Should be a Circuit
    assert isinstance(result.circuit, Circuit)

    # Should have valid qubit count
    assert result.circuit.n_qubits >= 0

    # Should have valid commands
    cmds = result.circuit.get_commands()
    assert isinstance(cmds, list)


@pytest.mark.integration
@pytest.mark.parametrize("name", PHASE0_2_NAMES)
def test_pytket_circuit_unitary_only(phase0_2_terms, name):
    """Compiled circuits contain only unitary operations."""
    term = phase0_2_terms[name]
    result = compile(term, materialize=False)

    assert is_unitary_only(result.circuit), f"Non-unitary gate found in {name}"


@pytest.mark.integration
@pytest.mark.parametrize("name", PHASE0_2_NAMES)
def test_pytket_circuit_allowed_gates(phase0_2_terms, name):
    """Compiled circuits use only allowed gate set."""
    term = phase0_2_terms[name]
    result = compile(term, materialize=False)

    allowed_gates = {"H", "S", "CX", "SWAP", "X", "Y", "Z", "T", "Tdg", "Sdg"}

    for cmd in result.circuit.get_commands():
        gate_name = cmd.op.type.name.upper()
        assert gate_name in {g.upper() for g in allowed_gates}, \
            f"Disallowed gate {gate_name} in {name}"


# -----------------------------------------------------------------
# Phase 3 Extractable: Pytket Sanity
# -----------------------------------------------------------------

PHASE3_EXT_NAMES = [
    "p3_feedback_yankable_basic",
    "p3_feedback_yankable_cx",
]


@pytest.mark.integration
@pytest.mark.parametrize("name", PHASE3_EXT_NAMES)
def test_phase3_pytket_circuit_valid(phase3_extractable_terms, name):
    """Phase 3 extracted circuits are valid pytket objects."""
    term = phase3_extractable_terms[name]
    result = compile_goi(term, materialize=False)

    extracted = assert_extracted(result, name)
    assert isinstance(extracted.circuit, Circuit)
    assert extracted.circuit.n_qubits >= 0


@pytest.mark.integration
@pytest.mark.parametrize("name", PHASE3_EXT_NAMES)
def test_phase3_pytket_unitary_only(phase3_extractable_terms, name):
    """Phase 3 extracted circuits are unitary only."""
    term = phase3_extractable_terms[name]
    result = compile_goi(term, materialize=False)

    extracted = assert_extracted(result, name)
    assert is_unitary_only(extracted.circuit)


# -----------------------------------------------------------------
# Phase 4A: Pytket Sanity
# -----------------------------------------------------------------

PHASE4A_NAMES = [
    "p4a_extracts_h_disjoint",
    "p4a_extracts_s_disjoint",
]


@pytest.mark.integration
@pytest.mark.parametrize("name", PHASE4A_NAMES)
def test_phase4a_pytket_circuit_valid(phase4a_terms, name):
    """Phase 4A extracted circuits are valid pytket objects."""
    term = phase4a_terms[name]
    result = compile_goi(term, materialize=False)

    extracted = assert_extracted(result, name)
    assert isinstance(extracted.circuit, Circuit)
    assert extracted.circuit.n_qubits >= 0


@pytest.mark.integration
@pytest.mark.parametrize("name", PHASE4A_NAMES)
def test_phase4a_pytket_no_swaps(phase4a_terms, name):
    """Phase 4A extracted circuits have no SWAPs when materialize=False."""
    term = phase4a_terms[name]
    result = compile_goi(term, materialize=False)

    extracted = assert_extracted(result, name)
    assert_no_swaps(extracted.circuit, name)


@pytest.mark.integration
@pytest.mark.parametrize("name", PHASE4A_NAMES)
def test_phase4a_pytket_unitary_only(phase4a_terms, name):
    """Phase 4A extracted circuits are unitary only."""
    term = phase4a_terms[name]
    result = compile_goi(term, materialize=False)

    extracted = assert_extracted(result, name)
    assert is_unitary_only(extracted.circuit)


# -----------------------------------------------------------------
# Qubit Index Validity
# -----------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.parametrize("name", PHASE0_2_NAMES)
def test_qubit_indices_in_range(phase0_2_terms, name):
    """All qubit indices are within circuit bounds."""
    term = phase0_2_terms[name]
    result = compile(term, materialize=False)

    n_qubits = result.circuit.n_qubits

    for cmd in result.circuit.get_commands():
        for qubit in cmd.qubits:
            idx = qubit.index[0]
            assert 0 <= idx < n_qubits, \
                f"Qubit index {idx} out of range [0, {n_qubits}) in {name}"


# -----------------------------------------------------------------
# Materialize Produces Valid Circuits
# -----------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.parametrize("name", PHASE0_2_NAMES)
def test_materialize_produces_valid_circuit(phase0_2_terms, name):
    """materialize=True produces valid pytket circuits."""
    term = phase0_2_terms[name]
    result = compile(term, materialize=True)

    assert isinstance(result.circuit, Circuit)
    assert result.circuit.n_qubits >= 0
    assert is_unitary_only(result.circuit)
