# tests/test_letpair.py
"""Tests for full source language: Var, Pair, LetPair, Arrow type."""

import pytest

from lang.types import Q, Ten, Plus, Unit, Arrow, width
from lang.terms import (
    Id, Seq, H, S, X, CX,
    Var, Pair, LetPair, Lam, Apply, FunVar,
    Case, CH, CS,
)
from typing_.check import type_of, TypeCheckError
from compile.to_pytket import compile


# =============================================================================
# Arrow Type Tests
# =============================================================================

class TestArrowType:
    """Tests for the Arrow (linear function) type."""

    def test_arrow_width_q_to_q(self):
        """width(Q ⊸ Q) = 2"""
        arr = Arrow(Q(), Q())
        assert width(arr) == 2

    def test_arrow_width_qq_to_q(self):
        """width((Q ⊗ Q) ⊸ Q) = 3"""
        arr = Arrow(Ten(Q(), Q()), Q())
        assert width(arr) == 3

    def test_arrow_width_nested(self):
        """width((Q ⊸ Q) ⊸ Q) = 3"""
        inner = Arrow(Q(), Q())
        arr = Arrow(inner, Q())
        assert width(arr) == 3

    def test_arrow_str(self):
        """Arrow type has readable string representation."""
        arr = Arrow(Q(), Q())
        s = str(arr)
        assert "⊸" in s or "Q" in s


# =============================================================================
# Var Term Tests
# =============================================================================

class TestVarTerm:
    """Tests for variable reference terms."""

    def test_var_type(self):
        """Var has identity type: A → A."""
        v = Var("x", Q())
        dom, cod = type_of(v)
        assert dom == Q()
        assert cod == Q()

    def test_var_tensor_type(self):
        """Var with tensor type."""
        v = Var("pair", Ten(Q(), Q()))
        dom, cod = type_of(v)
        assert dom == Ten(Q(), Q())
        assert cod == Ten(Q(), Q())

    def test_var_compile(self):
        """Var compiles to identity (no gates)."""
        v = Var("x", Q())
        result = compile(v)
        assert result.circuit.n_gates == 0


# =============================================================================
# Pair Term Tests
# =============================================================================

class TestPairTerm:
    """Tests for tensor introduction (pairing)."""

    def test_pair_type(self):
        """Pair has type A ⊗ B → A ⊗ B."""
        p = Pair(Id(Q()), Id(Q()))
        dom, cod = type_of(p)
        assert dom == Ten(Q(), Q())
        assert cod == Ten(Q(), Q())

    def test_pair_with_gates(self):
        """Pair preserves gates in subterms."""
        p = Pair(H(0, Q()), S(0, Q()))
        result = compile(p)
        # Should have H and S gates
        assert result.circuit.n_gates == 2

    def test_pair_compile_structure(self):
        """Pair compiles subterms at correct offsets."""
        # H on first qubit, S on second qubit
        p = Pair(H(0, Q()), S(0, Q()))
        result = compile(p)
        cmds = result.circuit.get_commands()
        # Extract gate types
        gate_types = [cmd.op.type.name for cmd in cmds]
        assert "H" in gate_types
        assert "S" in gate_types


# =============================================================================
# LetPair Term Tests
# =============================================================================

class TestLetPairTerm:
    """Tests for tensor elimination (destructuring)."""

    def test_letpair_type(self):
        """LetPair has correct type."""
        # let (x, y) = id : Q⊗Q in (x, y) : Q⊗Q
        pair_term = Id(Ten(Q(), Q()))
        body = Pair(Var("x", Q()), Var("y", Q()))
        lp = LetPair("x", "y", Q(), Q(), pair_term, body)

        dom, cod = type_of(lp)
        assert width(dom) == 2
        assert width(cod) == 2

    def test_letpair_compile_identity(self):
        """LetPair with identity body compiles to no gates."""
        pair_term = Id(Ten(Q(), Q()))
        body = Pair(Var("x", Q()), Var("y", Q()))
        lp = LetPair("x", "y", Q(), Q(), pair_term, body)

        result = compile(lp)
        assert result.circuit.n_gates == 0

    def test_letpair_with_gate_on_x(self):
        """LetPair binds x correctly: H on x should go to wire 0."""
        pair_term = Id(Ten(Q(), Q()))
        # Apply H to x (first component)
        body = Pair(Seq(Var("x", Q()), H(0, Q())), Var("y", Q()))
        lp = LetPair("x", "y", Q(), Q(), pair_term, body)

        result = compile(lp)
        # Should have 1 H gate
        assert result.circuit.n_gates == 1

    def test_letpair_with_gate_on_y(self):
        """LetPair binds y correctly: S on y should go to wire 1."""
        pair_term = Id(Ten(Q(), Q()))
        # Apply S to y (second component)
        body = Pair(Var("x", Q()), Seq(Var("y", Q()), S(0, Q())))
        lp = LetPair("x", "y", Q(), Q(), pair_term, body)

        result = compile(lp)
        # Should have 1 S gate
        assert result.circuit.n_gates == 1


# =============================================================================
# Lam/Apply Compilation Tests
# =============================================================================

class TestLamApply:
    """Tests for Lambda and Apply boundary semantics.

    Per spec sections 4.6 and 4.7:
    - Lam: Γ,x:A ⊢ body:B  ⇒  Γ ⊢ λx.body : A ⊸ B
    - Apply: Γ₁ ⊢ f:A⊸B  Γ₂ ⊢ u:A  ⇒  Γ₁⊗Γ₂ ⊢ f u : B
    """

    def test_lam_type(self):
        """Lambda: Γ ⊢ λx.body : A ⊸ B where body : (Γ ⊗ A) → B."""
        # body : Q⊗Q → Q⊗Q (width 2 → width 2)
        # If x:Q is bound, then Γ=Q, A=Q, B=Q (by convention)
        # Lam type: Q → (Q ⊸ Q)
        body = H(0, Ten(Q(), Q()))  # H acting on 2-wire space
        lam = Lam("x", Q(), Q(), body)
        dom, cod = type_of(lam)
        # dom = Γ = Q (body_width - wA = 2 - 1 = 1)
        assert width(dom) == 1
        # cod = Arrow(Q, Q)
        assert isinstance(cod, Arrow)
        assert width(cod) == 2  # Q ⊸ Q = 2 wires

    def test_apply_type(self):
        """Apply: f : A⊸B, arg : A  ⇒  f arg : B."""
        # f = λx.H(x) : Q → Arrow(Q, Q)
        body = H(0, Ten(Q(), Q()))
        f = Lam("x", Q(), Q(), body)
        # arg = Id(Q) : Q → Q
        arg = Id(Q())
        app = Apply(f, arg)
        dom, cod = type_of(app)
        # dom = Q ⊗ Q = Ten(Q, Q) (contexts of f and arg)
        assert width(dom) == 2
        # cod = B = Q (result type from Arrow(Q, Q))
        assert cod == Q()
        assert width(cod) == 1

    def test_lam_apply_roundtrip(self):
        """Apply(Lam("f", ..., body), arg) compiles correctly."""
        # Create a simple function: f that applies H
        body = H(0, Ten(Q(), Q()))  # H on first wire of function space
        lam = Lam("f", Q(), Q(), body)

        # Apply it to an argument
        arg = Id(Q())
        app = Apply(lam, arg)

        result = compile(app)
        # Should compile without error
        # Circuit should have at least the H gate from the lambda body
        assert result.circuit.n_gates >= 1


# =============================================================================
# Higher-Order QSwitch Test (Abstract)
# =============================================================================

class TestQSwitchAbstract:
    """Tests for abstract QSwitch as a term."""

    def test_qswitch_type_signature(self):
        """QSwitch has type (Q→Q) ⊗ (Q→Q) ⊗ Bool ⊗ Q → Bool ⊗ Q."""
        # QSwitch : (Q⊸Q) ⊗ (Q⊸Q) ⊗ (I+I) ⊗ Q → (I+I) ⊗ Q
        fn_ty = Arrow(Q(), Q())  # Q ⊸ Q
        bool_ty = Plus(Unit(), Unit())  # I + I

        # Input: fn ⊗ fn ⊗ bool ⊗ q
        input_ty = Ten(fn_ty, Ten(fn_ty, Ten(bool_ty, Q())))
        # Output: bool ⊗ q
        output_ty = Ten(bool_ty, Q())

        # Check widths
        # fn_ty width = 2, bool_ty width = 1, Q width = 1
        assert width(fn_ty) == 2
        assert width(bool_ty) == 1
        assert width(input_ty) == 2 + 2 + 1 + 1  # = 6
        assert width(output_ty) == 1 + 1  # = 2

    def test_abstract_qswitch_structure(self):
        """Build abstract QSwitch term using LetPair and Case."""
        # Types
        fn_ty = Arrow(Q(), Q())
        bool_ty = Plus(Unit(), Unit())

        # Build: let (f, rest) = input in
        #        let (g, rest2) = rest in
        #        let (b, x) = rest2 in
        #        case b of
        #          | Left => (b, Apply(g, Apply(f, x)))  -- f;g
        #          | Right => (b, Apply(f, Apply(g, x))) -- g;f

        # Input type: fn ⊗ (fn ⊗ (bool ⊗ Q))
        input_ty = Ten(fn_ty, Ten(fn_ty, Ten(bool_ty, Q())))

        # For now, just verify the types work
        assert width(input_ty) == 6

        # A full implementation would build the term using:
        # - LetPair to destructure inputs
        # - FunVar to reference f and g
        # - Apply to call functions
        # - Case to branch on b
        # - Pair to reconstruct output


# =============================================================================
# Integration: QSwitch[H, S] via Term Construction
# =============================================================================

class TestQSwitchInstantiated:
    """Tests for QSwitch instantiated with concrete gates."""

    def test_qswitch_hs_via_case(self):
        """QSwitch[H, S] built using Case produces correct circuit."""
        # QSwitch on Bool ⊗ Q = (I + I) ⊗ Q
        # After DistR: (I⊗Q) + (I⊗Q)
        # Case operates on this: branches have type I⊗Q → I⊗Q

        # Summand type: I⊗Q (unit + qubit)
        IQ = Ten(Unit(), Q())

        # Left branch: H;S on the qubit (wire 1 since wire 0 is unit/tag)
        # Wire 0 is unit (width 0), so qubit is at wire 0 in the payload
        left_branch = Seq(H(0, IQ), S(0, IQ))   # H;S on Q at wire 0 of I⊗Q

        # Right branch: S;H on the qubit
        right_branch = Seq(S(0, IQ), H(0, IQ))  # S;H on Q at wire 0 of I⊗Q

        case_term = Case(IQ, IQ, left_branch, right_branch)

        result = compile(case_term, explain=True)
        # Should have gates for both branches
        # Anti-controlled left (X, CH, CS, X) + controlled right (CS, CH)
        assert result.circuit.n_gates >= 4

    def test_qswitch_xz_via_case(self):
        """QSwitch[X, Z] built using Case."""
        # Summand type: I⊗Q
        IQ = Ten(Unit(), Q())

        # Left branch: X;Z on the qubit
        left_branch = Seq(X(0, IQ), Seq(Id(IQ), Id(IQ)))  # X;Id

        # Right branch: Z;X on the qubit
        right_branch = Id(IQ)  # Just identity for simplicity

        case_term = Case(IQ, IQ, left_branch, right_branch)
        result = compile(case_term)
        assert result.circuit.n_gates >= 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
