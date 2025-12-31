# tests/test_phase4a_integration.py
"""Phase 4A: Integration tests.

These tests verify:
- Phase 4A extracts a strict superset of Phase 3 cases
- Phase 0-3 behavior is unchanged
- No SWAPs emitted when materialize=False
- Determinism is preserved
"""

from __future__ import annotations

import pytest
from lang.types import Q, Ten
from lang.terms import Id, Seq, H, S, CX, Feedback, TwistTen
from compile.to_pytket import compile_goi, CompiledGOI
from compile.goi import GOIArtifact


def qpow(n: int):
    """Build Q^n type."""
    if n == 1:
        return Q()
    ty = Q()
    for _ in range(n - 1):
        ty = Ten(ty, Q())
    return ty


# -----------------------------------------------------------------------------
# Phase 0-3 Regression: All existing cases must work identically
# -----------------------------------------------------------------------------

@pytest.mark.phase4a
@pytest.mark.regression
def test_phase3_yankable_still_works():
    """Phase 3 yankable case: Feedback with no gate interaction."""
    q3 = qpow(3)
    # H on wire 0, Feedback loops wire 2
    term = Feedback(1, H(0, q3))

    result = compile_goi(term, materialize=False)
    assert isinstance(result, CompiledGOI)
    # Should have 2 external wires
    assert result.perm.n == 2

    # No SWAPs
    cmds = list(result.circuit.get_commands())
    for cmd in cmds:
        assert cmd.op.type.name.upper() != "SWAP"


@pytest.mark.phase4a
@pytest.mark.regression
def test_phase3_residual_still_residual():
    """Phase 3 non-yankable case: Gate touches loop wire."""
    q3 = qpow(3)
    # CX on wires 0 and 2, but wire 2 is in loop
    term = Feedback(1, CX(0, 2, q3))

    result = compile_goi(term, materialize=False)
    # Should be residual
    assert isinstance(result, GOIArtifact)


# -----------------------------------------------------------------------------
# Phase 4A New Capabilities
# -----------------------------------------------------------------------------

@pytest.mark.phase4a
def test_phase4a_extracts_more_basic():
    """Basic Phase 4A extraction: gates on external wires only."""
    q4 = qpow(4)
    # Gates on wires 0 and 1, loop is wires 2 and 3
    body = Seq(H(0, q4), CX(0, 1, q4))
    term = Feedback(2, body)

    result = compile_goi(term, materialize=False)
    assert isinstance(result, CompiledGOI)
    # External wires: 4 - 2 = 2
    assert result.perm.n == 2


@pytest.mark.phase4a
def test_phase4a_structure_plus_gates():
    """Structure (TwistTen) plus gates, all avoiding loop wires."""
    a = Q()
    b = Q()
    q2 = Ten(a, b)
    q4 = Ten(q2, q2)  # 4 wires

    # Structure + gate, then feedback
    body = Seq(H(0, q4), S(1, q4))
    term = Feedback(2, body)

    result = compile_goi(term, materialize=False)
    assert isinstance(result, CompiledGOI)


# -----------------------------------------------------------------------------
# No SWAP policy
# -----------------------------------------------------------------------------

@pytest.mark.phase4a
def test_no_swaps_in_extracted_circuit():
    """Extracted circuits must not contain SWAPs when materialize=False."""
    q4 = qpow(4)
    body = Seq(H(0, q4), S(1, q4))
    term = Feedback(2, body)

    result = compile_goi(term, materialize=False)
    assert isinstance(result, CompiledGOI)

    cmds = list(result.circuit.get_commands())
    swap_count = sum(1 for c in cmds if c.op.type.name.upper() == "SWAP")
    assert swap_count == 0, f"Found {swap_count} SWAPs"


@pytest.mark.phase4a
def test_materialize_true_adds_swaps_if_needed():
    """materialize=True may add SWAPs for non-identity permutation."""
    q2 = qpow(2)
    # Just a simple gate, no feedback
    term = H(0, q2)

    result = compile_goi(term, materialize=True)
    assert isinstance(result, CompiledGOI)
    # Perm should be identity after materialization
    assert result.perm.new_to_old == list(range(result.perm.n))


# -----------------------------------------------------------------------------
# Determinism
# -----------------------------------------------------------------------------

@pytest.mark.phase4a
def test_determinism_extracted():
    """Same term produces identical extracted result."""
    q4 = qpow(4)
    term = Feedback(2, Seq(H(0, q4), S(1, q4)))

    r1 = compile_goi(term, materialize=False)
    r2 = compile_goi(term, materialize=False)

    assert isinstance(r1, CompiledGOI)
    assert isinstance(r2, CompiledGOI)

    # Compare circuits
    cmds1 = [(c.op.type.name, [q.index[0] for q in c.qubits]) for c in r1.circuit.get_commands()]
    cmds2 = [(c.op.type.name, [q.index[0] for q in c.qubits]) for c in r2.circuit.get_commands()]
    assert cmds1 == cmds2

    # Compare perms
    assert r1.perm.new_to_old == r2.perm.new_to_old


@pytest.mark.phase4a
def test_determinism_residual():
    """Same term produces identical residual."""
    q3 = qpow(3)
    term = Feedback(1, CX(0, 2, q3))  # Gate touches loop

    r1 = compile_goi(term, materialize=False)
    r2 = compile_goi(term, materialize=False)

    assert isinstance(r1, GOIArtifact)
    assert isinstance(r2, GOIArtifact)

    assert r1.atoms == r2.atoms
    assert r1.loops == r2.loops
    assert r1.perm.new_to_old == r2.perm.new_to_old


# -----------------------------------------------------------------------------
# Edge cases
# -----------------------------------------------------------------------------

@pytest.mark.phase4a
def test_no_feedback_compiles_normally():
    """Terms without Feedback compile as in Phase 0-2."""
    q2 = qpow(2)
    term = Seq(H(0, q2), CX(0, 1, q2))

    result = compile_goi(term, materialize=False)
    assert isinstance(result, CompiledGOI)

    cmds = list(result.circuit.get_commands())
    assert len(cmds) == 2
    assert cmds[0].op.type.name == "H"
    assert cmds[1].op.type.name == "CX"


@pytest.mark.phase4a
def test_empty_body_feedback():
    """Feedback with identity body."""
    q2 = qpow(2)
    term = Feedback(1, Id(q2))

    result = compile_goi(term, materialize=False)
    assert isinstance(result, CompiledGOI)
    # No gates in circuit
    assert len(list(result.circuit.get_commands())) == 0
