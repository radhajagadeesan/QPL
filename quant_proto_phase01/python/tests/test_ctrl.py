"""Tests for the Ctrl (controlled combinator) term."""

import pytest
import numpy as np

from lang.terms import (
    Ctrl, H, S, X, Z, Sdg, Rz, CX, TenTerm, Seq, Id, TwistTen,
    PlusMap, Case,
)
from lang.types import Q, Ten, Plus, Unit
from typing_.check import type_of, TypeCheckError
from compile.to_pytket import compile


# Helper: Bool type for control
Bool = Plus(Unit(), Unit())


class TestCtrlTypeChecking:
    """Tests for Ctrl type rules."""

    def test_ctrl_h_type(self):
        """Ctrl(H) : Bool ⊗ Q → Bool ⊗ Q."""
        term = Ctrl(H(0, Q()))
        dom, cod = type_of(term)
        assert dom == Ten(Bool, Q())
        assert cod == Ten(Bool, Q())

    def test_ctrl_seq_type(self):
        """Ctrl(H;S) : Bool ⊗ Q → Bool ⊗ Q."""
        term = Ctrl(Seq(H(0, Q()), S(0, Q())))
        dom, cod = type_of(term)
        assert dom == Ten(Bool, Q())
        assert cod == Ten(Bool, Q())

    def test_ctrl_tenterm_type(self):
        """Ctrl(H ⊗ S) : Bool ⊗ (Q ⊗ Q) → Bool ⊗ (Q ⊗ Q)."""
        term = Ctrl(TenTerm(H(0, Q()), S(0, Q())))
        dom, cod = type_of(term)
        assert dom == Ten(Bool, Ten(Q(), Q()))
        assert cod == Ten(Bool, Ten(Q(), Q()))

    def test_ctrl_id_type(self):
        """Ctrl(Id) : Bool ⊗ A → Bool ⊗ A."""
        term = Ctrl(Id(Q()))
        dom, cod = type_of(term)
        assert dom == Ten(Bool, Q())
        assert cod == Ten(Bool, Q())

    def test_ctrl_nested_type(self):
        """Ctrl(Ctrl(H)) : Bool ⊗ (Bool ⊗ Q) → Bool ⊗ (Bool ⊗ Q)."""
        inner = Ctrl(H(0, Q()))
        outer = Ctrl(inner)
        dom, cod = type_of(outer)
        assert dom == Ten(Bool, Ten(Bool, Q()))
        assert cod == Ten(Bool, Ten(Bool, Q()))


class TestCtrlCompilation:
    """Tests for Ctrl compilation."""

    def test_ctrl_h_compiles(self):
        """Ctrl(H) compiles to CH gate."""
        term = Ctrl(H(0, Q()))
        result = compile(term, materialize=True)
        # Should have 1 gate: CH
        assert result.circuit.n_gates == 1
        cmds = list(result.circuit.get_commands())
        assert cmds[0].op.type.name == "CH"

    def test_ctrl_s_compiles(self):
        """Ctrl(S) compiles to CS gate."""
        term = Ctrl(S(0, Q()))
        result = compile(term, materialize=True)
        assert result.circuit.n_gates == 1
        cmds = list(result.circuit.get_commands())
        assert cmds[0].op.type.name == "CS"

    def test_ctrl_x_compiles(self):
        """Ctrl(X) compiles to CX gate."""
        term = Ctrl(X(0, Q()))
        result = compile(term, materialize=True)
        assert result.circuit.n_gates == 1
        cmds = list(result.circuit.get_commands())
        assert cmds[0].op.type.name == "CX"

    def test_ctrl_z_compiles(self):
        """Ctrl(Z) compiles to CZ gate."""
        term = Ctrl(Z(0, Q()))
        result = compile(term, materialize=True)
        assert result.circuit.n_gates == 1
        cmds = list(result.circuit.get_commands())
        assert cmds[0].op.type.name == "CZ"

    def test_ctrl_rz_compiles(self):
        """Ctrl(Rz) compiles to CRz gate."""
        import math
        term = Ctrl(Rz(math.pi / 4, 0, Q()))
        result = compile(term, materialize=True)
        assert result.circuit.n_gates == 1
        cmds = list(result.circuit.get_commands())
        assert cmds[0].op.type.name == "CRz"

    def test_ctrl_cx_compiles(self):
        """Ctrl(CX) compiles to CCX (Toffoli) gate."""
        term = Ctrl(CX(0, 1, Ten(Q(), Q())))
        result = compile(term, materialize=True)
        assert result.circuit.n_gates == 1
        cmds = list(result.circuit.get_commands())
        assert cmds[0].op.type.name == "CCX"

    def test_ctrl_seq_compiles(self):
        """Ctrl(H;S) compiles to CH;CS."""
        term = Ctrl(Seq(H(0, Q()), S(0, Q())))
        result = compile(term, materialize=True)
        assert result.circuit.n_gates == 2
        cmds = list(result.circuit.get_commands())
        assert cmds[0].op.type.name == "CH"
        assert cmds[1].op.type.name == "CS"

    def test_ctrl_tenterm_compiles(self):
        """Ctrl(H ⊗ S) compiles with shared control."""
        term = Ctrl(TenTerm(H(0, Q()), S(0, Q())))
        result = compile(term, materialize=True)
        # Should have CH on qubit 1, CS on qubit 2, both controlled by qubit 0
        assert result.circuit.n_gates == 2
        cmds = list(result.circuit.get_commands())
        # Both gates should have control on qubit 0
        ctrl_qubits = [cmd.qubits[0].index[0] for cmd in cmds]
        assert all(c == 0 for c in ctrl_qubits)

    def test_ctrl_id_compiles_to_zero_gates(self):
        """Ctrl(Id) compiles to zero gates."""
        term = Ctrl(Id(Q()))
        result = compile(term, materialize=True)
        assert result.circuit.n_gates == 0

    def test_ctrl_twist_compiles_to_cswap(self):
        """Ctrl(TwistTen(Q,Q)) compiles to CSWAP."""
        term = Ctrl(TwistTen(Q(), Q()))
        result = compile(term, materialize=True)
        assert result.circuit.n_gates == 1
        cmds = list(result.circuit.get_commands())
        assert cmds[0].op.type.name == "CSWAP"

    def test_ctrl_plusmap_compiles(self):
        """Ctrl(PlusMap(H, S)) compiles via decompose-and-control."""
        q = Q()
        pm = PlusMap(q, q, H(0, q), S(0, q))
        term = Ctrl(pm)
        result = compile(term, materialize=True)
        # Should produce gates (controlled versions of PlusMap's sub-circuit)
        assert result.circuit.n_gates > 0

    def test_ctrl_case_compiles(self):
        """Ctrl(Case(H, S)) compiles via decompose-and-control."""
        q = Q()
        case_term = Case(q, q, H(0, q), S(0, q))
        term = Ctrl(case_term)
        result = compile(term, materialize=True)
        assert result.circuit.n_gates > 0


class TestCtrlSemantics:
    """Tests for Ctrl correctness via unitaries."""

    def test_ctrl_h_unitary(self):
        """Ctrl(H) produces correct 4x4 controlled-H unitary."""
        term = Ctrl(H(0, Q()))
        result = compile(term, materialize=True)

        # Get unitary directly from pytket
        U = result.circuit.get_unitary()

        # Expected: controlled-H (control=qubit 0, target=qubit 1)
        # In computational basis |00⟩, |01⟩, |10⟩, |11⟩
        # When control is 0: identity on target
        # When control is 1: H on target
        H_mat = np.array([[1, 1], [1, -1]]) / np.sqrt(2)
        I_mat = np.eye(2)

        # Expected CH matrix (in little-endian convention):
        # |00⟩ -> |00⟩, |01⟩ -> |01⟩ (control=0)
        # |10⟩, |11⟩ get H applied
        expected = np.block([
            [I_mat, np.zeros((2, 2))],
            [np.zeros((2, 2)), H_mat]
        ])

        assert np.allclose(U, expected), f"Got:\n{U}\nExpected:\n{expected}"

    def test_ctrl_z_unitary(self):
        """Ctrl(Z) = CZ produces correct unitary."""
        term = Ctrl(Z(0, Q()))
        result = compile(term, materialize=True)

        # Get unitary directly from pytket
        U = result.circuit.get_unitary()

        # CZ = diag(1, 1, 1, -1)
        expected = np.diag([1, 1, 1, -1])
        assert np.allclose(U, expected)

    def test_ctrl_x_unitary(self):
        """Ctrl(X) = CX (CNOT) produces correct unitary."""
        term = Ctrl(X(0, Q()))
        result = compile(term, materialize=True)

        U = result.circuit.get_unitary()

        # CNOT flips target when control is 1
        # |00⟩ -> |00⟩, |01⟩ -> |01⟩, |10⟩ -> |11⟩, |11⟩ -> |10⟩
        expected = np.array([
            [1, 0, 0, 0],
            [0, 1, 0, 0],
            [0, 0, 0, 1],
            [0, 0, 1, 0]
        ])
        assert np.allclose(U, expected)

    def test_ctrl_ctrl_x_unitary(self):
        """Ctrl(Ctrl(X)) = CCX (Toffoli) produces correct unitary."""
        inner = Ctrl(X(0, Q()))
        outer = Ctrl(inner)
        result = compile(outer, materialize=True)

        U = result.circuit.get_unitary()

        # Toffoli: flips target only when both controls are 1
        # 8x8 matrix, only |110⟩ <-> |111⟩ swap
        expected = np.eye(8)
        expected[6, 6] = 0
        expected[7, 7] = 0
        expected[6, 7] = 1
        expected[7, 6] = 1
        assert np.allclose(U, expected)


class TestCtrlNested:
    """Tests for nested Ctrl (doubly-controlled gates)."""

    def test_nested_ctrl_x_compiles_to_ccx(self):
        """Ctrl(Ctrl(X)) = CCX (Toffoli) compiles."""
        inner = Ctrl(X(0, Q()))
        outer = Ctrl(inner)
        result = compile(outer, materialize=True)
        # Should compile to CCX (Toffoli)
        assert result.circuit.n_gates == 1
        cmds = list(result.circuit.get_commands())
        assert cmds[0].op.type.name == "CCX"

    def test_nested_ctrl_seq_x_compiles(self):
        """Ctrl(Ctrl(X;X)) compiles to two CCX gates."""
        inner = Ctrl(Seq(X(0, Q()), X(0, Q())))
        outer = Ctrl(inner)
        result = compile(outer, materialize=True)
        # Should compile to 2 CCX gates
        assert result.circuit.n_gates == 2
        cmds = list(result.circuit.get_commands())
        assert all(cmd.op.type.name == "CCX" for cmd in cmds)

    def test_nested_ctrl_id_compiles(self):
        """Ctrl(Ctrl(Id)) compiles to zero gates."""
        inner = Ctrl(Id(Q()))
        outer = Ctrl(inner)
        result = compile(outer, materialize=True)
        assert result.circuit.n_gates == 0

    def test_ctrl_plusmap_unitary(self):
        """Ctrl(PlusMap(H, S)) produces correct controlled unitary.

        When control=0: identity on Q+Q payload
        When control=1: PlusMap(H,S) on Q+Q payload
        """
        q = Q()
        pm = PlusMap(q, q, H(0, q), S(0, q))

        # Get PlusMap unitary (4x4)
        pm_U = compile(pm, materialize=True).circuit.get_unitary()

        # Get Ctrl(PlusMap) unitary (8x8)
        term = Ctrl(pm)
        ctrl_U = compile(term, materialize=True).circuit.get_unitary()

        # Should be block diagonal: [I, 0; 0, pm_U]
        expected = np.block([
            [np.eye(4), np.zeros((4, 4))],
            [np.zeros((4, 4)), pm_U]
        ])
        assert np.allclose(ctrl_U, expected, atol=1e-10)

    def test_nested_ctrl_h_not_supported(self):
        """Ctrl(Ctrl(H)) raises NotImplementedError (no CCH primitive)."""
        inner = Ctrl(H(0, Q()))
        outer = Ctrl(inner)
        with pytest.raises(NotImplementedError, match="Multi-controlled.*not implemented"):
            compile(outer, materialize=True)
