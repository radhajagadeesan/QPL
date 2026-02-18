# tests/test_20_structural_tensor.py
from lang.types import Q, Ten
from lang.terms import TwistTen, AssocTenL, AssocTenR, Seq
from compile.to_pytket import compile
from core.perm import identity, block_swap


def test_twist_tensor_compiles_to_perm_only():
    a = Ten(Q(), Q())
    b = Q()
    out = compile(TwistTen(a, b))
    assert out.circuit.n_qubits == 3
    assert len(out.circuit.get_commands()) == 0
    assert out.perm.new_to_old == block_swap(2, 1).new_to_old


def test_assoc_tensor_is_identity_on_flat_wires():
    a = b = c = Q()
    out = compile(AssocTenL(a, b, c))
    assert len(out.circuit.get_commands()) == 0
    assert out.perm.new_to_old == identity(3).new_to_old

    out2 = compile(AssocTenR(a, b, c))
    assert out2.perm.new_to_old == identity(3).new_to_old


def test_seq_of_twists_is_identity():
    a = Ten(Q(), Q())
    b = Q()
    t1 = TwistTen(a, b)
    t2 = TwistTen(b, a)
    out = compile(Seq(t1, t2))
    assert out.perm.new_to_old == identity(3).new_to_old
