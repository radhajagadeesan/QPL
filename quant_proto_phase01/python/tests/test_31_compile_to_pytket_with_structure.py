# tests/test_31_compile_to_pytket_with_structure.py
"""Gate compilation with structural permutations (metadata)."""

from lang.types import Q, Ten
from lang.terms import TwistTen, H, CX, Seq
from compile.to_pytket import compile
from core.perm import block_swap


def test_gate_reindexing_through_twist():
    a = Ten(Q(), Q())
    b = Q()
    ty_total = Ten(a, b)  # width 3

    term = Seq(TwistTen(a, b), H(0, ty_total))
    out = compile(term)
    cmds = out.circuit.get_commands()
    assert len(cmds) == 1
    phys = cmds[0].qubits[0].index[0]
    assert phys == 2
    assert out.perm.new_to_old == block_swap(2, 1).new_to_old


def test_cx_reindexing_through_twist():
    a = Ten(Q(), Q())
    b = Q()
    ty_total = Ten(a, b)  # width 3
    term = Seq(TwistTen(a, b), CX(0, 1, ty_total))
    out = compile(term)
    cmds = out.circuit.get_commands()
    assert len(cmds) == 1
    phys0 = cmds[0].qubits[0].index[0]
    phys1 = cmds[0].qubits[1].index[0]
    assert (phys0, phys1) == (2, 0)
