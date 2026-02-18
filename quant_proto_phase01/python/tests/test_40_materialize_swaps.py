# tests/test_40_materialize_swaps.py
from lang.types import Q, Ten
from lang.terms import TwistTen
from compile.to_pytket import compile
from core.perm import identity


def test_materialize_resets_perm_to_identity():
    a = Ten(Q(), Q())
    b = Q()
    out = compile(TwistTen(a, b), materialize=True)
    assert out.perm.new_to_old == identity(3).new_to_old
    assert len(out.circuit.get_commands()) > 0
