# tests/test_30_compile_to_pytket_gates.py
"""Gate compilation tests (no structure)."""

from lang.types import Q, Ten
from lang.terms import H, S, CX, Seq
from compile.to_pytket import compile


def test_single_qubit_gates_compile():
    ty = Ten(Q(), Q())  # 2 wires
    out = compile(Seq(H(0, ty), S(1, ty)))
    cmds = out.circuit.get_commands()
    assert len(cmds) == 2
    q0 = cmds[0].qubits[0].index[0]
    q1 = cmds[1].qubits[0].index[0]
    assert q0 == 0
    assert q1 == 1


def test_cx_compiles():
    ty = Ten(Q(), Q())
    out = compile(CX(0, 1, ty))
    cmds = out.circuit.get_commands()
    assert len(cmds) == 1
    q0 = cmds[0].qubits[0].index[0]
    q1 = cmds[0].qubits[1].index[0]
    assert (q0, q1) == (0, 1)
