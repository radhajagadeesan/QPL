from __future__ import annotations

import pytest
from ._phase2_helpers import (
    qpow, Q,
    TenTerm, Seq, H, S, CX,
    compile_term, assert_no_swaps,
    non_swap_signature, materialize_manual
)

@pytest.mark.phase2
def test_no_swaps_by_default_phase2():
    """
    TenTerm must not introduce SWAPs when materialize=False.
    """
    A = qpow(2)
    B = qpow(2)
    term = TenTerm(Seq(H(0, A), S(1, A)), CX(0, 1, B))

    res = compile_term(term, materialize=False)
    assert_no_swaps(res.circuit)

@pytest.mark.phase2
def test_materialize_true_equivalent_to_manual_apply_swaps():
    """
    `compile(materialize=True)` must match manual materialization of (circuit, perm).
    We compare the full command stream, including SWAPs.
    """
    A = qpow(2)
    B = qpow(2)
    term = TenTerm(Seq(H(0, A), S(1, A)), CX(0, 1, B))

    res_nom = compile_term(term, materialize=False)
    circ_manual = materialize_manual(res_nom)

    res_mat = compile_term(term, materialize=True)

    assert [c.op.type.name for c in circ_manual.get_commands()] == [c.op.type.name for c in res_mat.circuit.get_commands()]
    assert [[q.index[0] for q in c.qubits] for c in circ_manual.get_commands()] == [[q.index[0] for q in c.qubits] for c in res_mat.circuit.get_commands()]

@pytest.mark.phase2
def test_materialization_preserves_non_swap_gate_order():
    """
    Invariant: materialization may insert SWAPs but must preserve order of non-SWAP gates.
    """
    A = qpow(2)
    B = qpow(2)
    term = TenTerm(Seq(H(0, A), S(1, A)), CX(0, 1, B))

    res = compile_term(term, materialize=False)
    sig_before = non_swap_signature(res.circuit)

    circ_manual = materialize_manual(res)
    sig_after = non_swap_signature(circ_manual)

    assert sig_before == sig_after
