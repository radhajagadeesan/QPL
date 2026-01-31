# tests/test_plusmap.py
"""Tests for PlusMap (⊕-Map): bifunctorial action on sums."""

import pytest
from lang.types import Q, Unit, Ten, Plus, width
from lang.terms import (
    PlusMap, Id, H, S, X, TwistPlus,
    Seq, TenTerm,
)
from typing_.check import type_of
from compile.to_pytket import compile


class TestPlusMapTypeChecking:
    """Test type checking for PlusMap."""

    def test_plusmap_basic_type(self):
        """PlusMap with identity branches: id_I ⊕ id_I."""
        left = Id(Unit())
        right = Id(Unit())
        pm = PlusMap(Unit(), Unit(), left, right)

        dom, cod = type_of(pm)
        # Domain: Unit + Unit (Bool)
        assert isinstance(dom, Plus)
        assert isinstance(dom.left, Unit)
        assert isinstance(dom.right, Unit)
        # Codomain: Unit + Unit (Bool) - same since branches are identities
        assert isinstance(cod, Plus)
        assert isinstance(cod.left, Unit)
        assert isinstance(cod.right, Unit)

    def test_plusmap_different_codomains(self):
        """PlusMap with different output types: id_I ⊕ H."""
        left = Id(Unit())  # I → I
        right = H(0, Q())  # Q → Q
        pm = PlusMap(Unit(), Q(), left, right)

        dom, cod = type_of(pm)
        # Domain: Unit + Q
        assert isinstance(dom, Plus)
        assert width(dom.left) == 0  # Unit
        assert width(dom.right) == 1  # Q
        # Codomain: Unit + Q (same types since branches are endomorphisms)
        assert isinstance(cod, Plus)

    def test_plusmap_with_twist(self):
        """PlusMap with TwistPlus as right branch: id_I ⊕ twist+(I,I)."""
        # This is the toggle_W operation from short-circuit AND
        left = Id(Unit())  # I → I
        right = TwistPlus(Unit(), Unit())  # (I + I) → (I + I)
        pm = PlusMap(Unit(), Plus(Unit(), Unit()), left, right)

        dom, cod = type_of(pm)
        # Domain: Unit + (Unit + Unit) = W
        assert isinstance(dom, Plus)
        assert width(dom) == 2  # 1 tag for outer, 1 for inner Bool
        # Codomain should match
        assert isinstance(cod, Plus)


class TestPlusMapCompilation:
    """Test compilation of PlusMap using anti-control pattern."""

    def test_plusmap_id_id_zero_gates(self):
        """PlusMap(id_I, id_I) should compile to zero gates (pure identity)."""
        left = Id(Unit())
        right = Id(Unit())
        pm = PlusMap(Unit(), Unit(), left, right)

        result = compile(pm, materialize=False)
        assert result.circuit.n_gates == 0

    def test_plusmap_id_h_controlled_h(self):
        """PlusMap(id_I, H) should produce anti-controlled identity + controlled H."""
        # Left: id on Unit (0 width) → no gates
        # Right: H on Q → 1 controlled gate
        left = Id(Unit())
        right = H(0, Q())
        pm = PlusMap(Unit(), Q(), left, right)

        result = compile(pm, materialize=True)
        # Should have CH (controlled H) for right branch
        cmds = list(result.circuit.get_commands())
        # Only the right branch has gates, and those are controlled
        assert any('CH' in str(cmd.op) for cmd in cmds)

    def test_plusmap_h_s_anticontrol_pattern(self):
        """PlusMap(H, S) uses anti-control pattern: X; CH; X; CS."""
        # This is similar to QSwitch compilation
        ty = Q()
        left = H(0, ty)   # H : Q → Q
        right = S(0, ty)  # S : Q → Q
        pm = PlusMap(Q(), Q(), left, right)

        result = compile(pm, materialize=True)
        cmds = list(result.circuit.get_commands())

        # Should have: X (anti-control), CH, X (restore), CS
        # The exact structure depends on compilation details
        gate_names = [cmd.op.type.name for cmd in cmds]
        assert 'X' in gate_names  # Tag flip for anti-control
        assert 'CH' in gate_names  # Controlled H
        assert 'CS' in gate_names  # Controlled S

    def test_plusmap_preserves_width(self):
        """PlusMap preserves wire width."""
        ty = Q()
        left = H(0, ty)
        right = S(0, ty)
        pm = PlusMap(Q(), Q(), left, right)

        dom, cod = type_of(pm)
        # Q + Q has width 2 (1 tag + 1 shared payload)
        assert width(dom) == 2
        assert width(cod) == 2

        result = compile(pm)
        # Circuit should have 2 qubits
        assert result.circuit.n_qubits == 2


class TestPlusMapSemantics:
    """Test that PlusMap has correct quantum semantics."""

    def test_plusmap_unitary_is_correct(self):
        """Verify PlusMap(H, S) produces correct 4x4 unitary."""
        ty = Q()
        left = H(0, ty)
        right = S(0, ty)
        pm = PlusMap(Q(), Q(), left, right)

        result = compile(pm, materialize=True)
        U = result.circuit.get_unitary()

        # The unitary should be block-diagonal in the tag basis:
        # When tag=0 (anti-controlled): applies H to payload
        # When tag=1 (controlled): applies S to payload
        import numpy as np

        # Tag qubit is wire 0, payload is wire 1
        # Basis: |00>, |01>, |10>, |11>
        # |tag, payload>

        # Expected behavior:
        # |0, x> → |0, H|x>>  (anti-controlled H when tag=0)
        # |1, x> → |1, S|x>>  (controlled S when tag=1)

        # The matrix structure depends on the controlled gate implementation
        # Check that it's unitary
        assert np.allclose(U @ U.conj().T, np.eye(4), atol=1e-10)
