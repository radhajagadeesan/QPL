from __future__ import annotations

import pytest
from ._phase2_helpers import (
    Q, Ten, width, qpow,
    Id, Seq, TenTerm, H, S, CX,
    compile_term, assert_no_swaps, op_name, qubit_idxs, full_signature
)

# ---------------------------
# Core offset semantics (H/S)
# ---------------------------

@pytest.mark.phase2
def test_offset_right_branch_h():
    """
    TenTerm(Id(A), H(0, B)) must place H at global wire width(A) when perm is identity.
    """
    A = qpow(2)  # width 2
    B = Q()      # width 1

    term = TenTerm(Id(A), H(0, B))
    res = compile_term(term, materialize=False)
    assert_no_swaps(res.circuit)

    hs = [c for c in res.circuit.get_commands() if op_name(c).upper() == "H"]
    assert len(hs) == 1
    assert qubit_idxs(hs[0]) == [width(A)]


@pytest.mark.phase2
def test_offset_left_branch_s():
    """
    TenTerm(S(0, A), Id(B)) must place S at global wire 0 when perm is identity.
    """
    A = Q()
    B = qpow(3)

    term = TenTerm(S(0, A), Id(B))
    res = compile_term(term, materialize=False)
    assert_no_swaps(res.circuit)

    ss = [c for c in res.circuit.get_commands() if op_name(c).upper() == "S"]
    assert len(ss) == 1
    assert qubit_idxs(ss[0]) == [0]


@pytest.mark.phase2
def test_branches_do_not_alias_same_local_index():
    """
    TenTerm(H(0,A), H(0,B)) must produce two H gates on distinct globals: 0 and width(A).
    """
    A = Q()
    B = Q()
    term = TenTerm(H(0, A), H(0, B))

    res = compile_term(term, materialize=False)
    assert_no_swaps(res.circuit)

    hs = [c for c in res.circuit.get_commands() if op_name(c).upper() == "H"]
    assert len(hs) == 2
    idxs = [qubit_idxs(h)[0] for h in hs]
    assert sorted(idxs) == [0, width(A)]

# ---------------------------
# Core offset semantics (CX)
# ---------------------------

@pytest.mark.phase2
def test_offset_right_branch_cx_shifts_both_operands():
    """
    TenTerm(Id(A), CX(0,1,B)) must land on [width(A), width(A)+1] (assuming identity perm).
    """
    A = qpow(3)      # width 3
    B = qpow(2)      # width 2

    term = TenTerm(Id(A), CX(0, 1, B))
    res = compile_term(term, materialize=False)
    assert_no_swaps(res.circuit)

    cxs = [c for c in res.circuit.get_commands() if op_name(c).upper() == "CX"]
    assert len(cxs) == 1
    assert qubit_idxs(cxs[0]) == [width(A), width(A)+1]

# ---------------------------
# Emission order and determinism
# ---------------------------

@pytest.mark.phase2
def test_emission_order_left_then_right():
    """
    Spec lock: left branch gates are emitted before right branch gates.
    """
    A = qpow(2)
    B = qpow(2)

    left = Seq(H(0, A), S(1, A))
    right = CX(0, 1, B)
    term = TenTerm(left, right)

    res = compile_term(term, materialize=False)
    assert_no_swaps(res.circuit)

    sig = full_signature(res.circuit)
    # Expect H then S then CX
    assert [s.op.upper() for s in sig[:3]] == ["H", "S", "CX"], sig

@pytest.mark.phase2
def test_determinism_same_ast_same_signature_and_perm():
    """
    Spec lock: determinism across compilations.
    """
    A = qpow(2)
    B = qpow(2)
    term = TenTerm(Seq(H(0, A), S(1, A)), CX(0, 1, B))

    r1 = compile_term(term, materialize=False)
    r2 = compile_term(term, materialize=False)

    assert full_signature(r1.circuit) == full_signature(r2.circuit)
    # Perm determinism too (best-effort: compare repr)
    assert repr(r1.perm) == repr(r2.perm)

# ---------------------------
# Loud error for out-of-block indices
# ---------------------------

@pytest.mark.phase2
def test_out_of_block_index_errors_loudly():
    """
    Branch-local indices must be within branch width.
    Right branch B has width 1, so H(1,B) must error (compile-time or type-check time).
    """
    A = qpow(2)
    B = Q()
    term = TenTerm(Id(A), H(1, B))
    with pytest.raises(Exception):
        compile_term(term, materialize=False)
