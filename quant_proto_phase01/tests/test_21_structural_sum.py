# tests/test_21_structural_sum.py
"""Structural compilation tests (sum only): twist/assoc for ⊕."""

from lang.types import Q, Ten
from lang.terms import TwistPlus, AssocPlusL, AssocPlusR, Seq
from compile.to_pytket import compile
from core.perm import identity, block_swap


def test_twist_plus_compiles_to_perm_only():
    a = Q()              # width 1
    b = Ten(Q(), Q())    # width 2
    out = compile(TwistPlus(a, b))
    assert out.circuit.n_qubits == 3
    assert len(out.circuit.get_commands()) == 0
    assert out.perm.new_to_old == block_swap(1, 2).new_to_old


def test_assoc_plus_is_identity_on_flat_wires():
    a = b = c = Q()
    out = compile(AssocPlusL(a, b, c))
    assert len(out.circuit.get_commands()) == 0
    assert out.perm.new_to_old == identity(3).new_to_old

    out2 = compile(AssocPlusR(a, b, c))
    assert out2.perm.new_to_old == identity(3).new_to_old


def test_seq_of_twists_is_identity():
    a = Q()
    b = Ten(Q(), Q())
    t1 = TwistPlus(a, b)
    t2 = TwistPlus(b, a)
    out = compile(Seq(t1, t2))
    assert out.perm.new_to_old == identity(3).new_to_old
