"""Tests for compact-closed structure: Dual type, Cup, Cap, and higher-order compilation.

The key identity: A ⊸ B ≡ A* ⊗ B. Since all types are self-dual (A* = A),
functions are tensor products of wires. Lambda = cup (expose wires),
application = cap (connect wires). Both are pure wiring — no gates.
"""
from __future__ import annotations

import pytest
from lang.types import Q, Unit, Ten, Plus, Dual, Arrow, width, tag_width, payload_width, dual
from lang.terms import (
    Cup, Cap, FunVar, Lam, Apply,
    Id, Seq, TenTerm, H, S, CX,
)
from typing_.check import type_of, TypeCheckError
from compile.to_pytket import compile


class TestDualType:
    """Dual type A* — self-dual, same width as A."""

    def test_dual_q_width(self):
        assert width(Dual(Q())) == 1

    def test_dual_ten_width(self):
        assert width(Dual(Ten(Q(), Q()))) == 2

    def test_dual_unit_width(self):
        assert width(Dual(Unit())) == 0

    def test_dual_plus_width(self):
        assert width(Dual(Plus(Q(), Q()))) == 2

    def test_dual_tag_width(self):
        assert tag_width(Dual(Plus(Q(), Q()))) == 1

    def test_dual_payload_width(self):
        assert payload_width(Dual(Plus(Q(), Q()))) == 1

    def test_dual_involutive(self):
        """dual(dual(A)) = A."""
        assert dual(dual(Q())) == Q()
        assert dual(dual(Ten(Q(), Q()))) == Ten(Q(), Q())

    def test_dual_constructor(self):
        """dual(A) wraps in Dual, dual(Dual(A)) unwraps."""
        assert dual(Q()) == Dual(Q())
        assert dual(Dual(Q())) == Q()

    def test_dual_str(self):
        assert str(Dual(Q())) == "Q*"


class TestCupCapTypes:
    """Type checking for Cup and Cap."""

    def test_cup_type(self):
        """Cup(A) : I → A ⊗ A*."""
        dom, cod = type_of(Cup(Q()))
        assert dom == Unit()
        assert cod == Ten(Q(), Dual(Q()))

    def test_cap_type(self):
        """Cap(A) : A* ⊗ A → I."""
        dom, cod = type_of(Cap(Q()))
        assert dom == Ten(Dual(Q()), Q())
        assert cod == Unit()

    def test_cup_tensor_type(self):
        ty = Ten(Q(), Q())
        dom, cod = type_of(Cup(ty))
        assert dom == Unit()
        assert cod == Ten(ty, Dual(ty))
        assert width(cod) == 4  # 2 + 2

    def test_cap_tensor_type(self):
        ty = Ten(Q(), Q())
        dom, cod = type_of(Cap(ty))
        assert dom == Ten(Dual(ty), ty)
        assert cod == Unit()
        assert width(dom) == 4


class TestFunVarLamApplyTypes:
    """Type checking for higher-order constructs."""

    def test_funvar_type(self):
        """FunVar is identity on A ⊗ B wires."""
        dom, cod = type_of(FunVar("f", Q(), Q()))
        assert dom == Ten(Q(), Q())
        assert cod == Ten(Q(), Q())

    def test_lam_type(self):
        """Lam: Γ,x:A ⊢ body:B  ⇒  Γ ⊢ λx.body : A ⊸ B.

        Per spec section 4.6:
        - body is compiled with x:A bound to extra input wires
        - Lambda's codomain is Arrow(A, B)
        - Lambda's domain is Γ (body's domain minus x:A)
        """
        # body : (Q ⊗ Q) → Q, so Γ = Q, A = Q, B = Q
        # Lam("x", Q, Q, body) : Q → (Q ⊸ Q)
        body = Id(Ten(Q(), Q()))  # width 2 → width 2, but we treat as (Γ⊗A) → B
        dom, cod = type_of(Lam("x", Q(), Q(), body))
        # dom = Γ = Q (body_width - A_width = 2 - 1 = 1)
        assert width(dom) == 1
        # cod = Arrow(A, B) = Q ⊸ Q
        assert isinstance(cod, Arrow)
        assert cod.dom == Q()  # A = domain of the function
        assert cod.cod == Q()  # B = codomain of the function

    def test_apply_type(self):
        """Apply: Γ₁ ⊢ f:A⊸B  Γ₂ ⊢ u:A  ⇒  Γ₁⊗Γ₂ ⊢ f u : B.

        Per spec section 4.7:
        - f has codomain Arrow(A, B)
        - arg has codomain A
        - Apply's codomain is B (the result type)
        """
        # Build f : Q → Arrow(Q, Q) (a term producing a function)
        # Use Lam to create a function-producing term
        body = H(0, Ten(Q(), Q()))  # body: Q⊗Q → Q⊗Q
        f = Lam("x", Q(), Q(), body)  # f : Q → (Q ⊸ Q)
        # f has type (Q, Arrow(Q, Q))

        # arg : A (must have codomain matching A from Arrow)
        arg = Id(Q())  # arg : Q → Q

        dom, cod = type_of(Apply(f, arg))
        # dom = Γ₁ ⊗ Γ₂ = Q ⊗ Q = Ten(Q, Q)
        assert width(dom) == 2
        # cod = B = Q (the result type from Arrow(Q, Q))
        assert cod == Q()


class TestCupCapCompilation:
    """Compilation of Cup, Cap, and higher-order terms."""

    def test_cup_then_cap_zero_gates(self):
        """Cup followed by Cap: I → A⊗A* → I. Roundtrip is identity on 0 wires.
        But standalone Cup/Cap can't be compiled (different dom/cod widths).
        They only make sense within larger terms — test via Seq or Lam/Apply."""
        # Cup and Cap are sub-terms; test them within a composition
        # Seq(Cup(Q), Cap(Q)) : I → I but internally needs 2 wires
        # This is the zig-zag identity: (η ⊗ id) ; (id ⊗ ε) = id
        # For now, just verify they type-check correctly
        dom, cod = type_of(Cup(Q()))
        assert width(dom) == 0
        assert width(cod) == 2
        dom2, cod2 = type_of(Cap(Q()))
        assert width(dom2) == 2
        assert width(cod2) == 0

    def test_funvar_zero_gates(self):
        """FunVar is identity — zero gates."""
        result = compile(FunVar("f", Q(), Q()))
        assert result.circuit.n_gates == 0

    def test_lam_with_gate_body(self):
        """Lambda with a gate in the body compiles the gate."""
        ty = Ten(Q(), Q())
        body = H(0, ty)
        term = Lam("f", Q(), Q(), body)
        result = compile(term)
        cmds = result.circuit.get_commands()
        assert len(cmds) == 1
        assert cmds[0].op.type.name == "H"

    def test_apply_compiles_both_sides(self):
        """Apply compiles f (producing function) and arg.

        Per spec section 4.7:
        - f must produce Arrow(A, B)
        - arg must produce A
        - Apply connects arg's A output to f's A_slot
        - Result is B

        Example: Apply(λx.H(x), S(q)) should produce S; H (first S on arg, then H on result)
        """
        # f = λx.H(x) : Q → (Q ⊸ Q)
        # This produces a function that applies H
        body = H(0, Ten(Q(), Q()))  # body operates on Q⊗Q wires
        f = Lam("x", Q(), Q(), body)  # f : Q → Arrow(Q, Q)

        # arg = S : Q → Q
        # arg produces Q which will be connected to f's A_slot
        arg = Seq(Id(Q()), S(0, Q()))  # Id;S : Q → Q

        term = Apply(f, arg)
        result = compile(term)
        cmds = result.circuit.get_commands()
        # Should have S (from arg) and H (from Lam body)
        gate_names = [c.op.type.name for c in cmds]
        assert "H" in gate_names
        assert "S" in gate_names

    def test_cup_qubit_count(self):
        """Cup(Q) produces circuit on width(I) = 0 qubits? No — the output has 2 wires."""
        # Cup : I → Q ⊗ Q* has codomain width 2
        # But compile() allocates based on domain width for the top-level term
        # The circuit width depends on the full term context
        dom, cod = type_of(Cup(Q()))
        assert width(dom) == 0
        assert width(cod) == 2


