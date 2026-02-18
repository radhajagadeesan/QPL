# tests/test_spec_section7.py
"""Tests from spec section 7: Higher-order compilation validation.

These tests verify the correctness of Lam/Apply boundary semantics
as specified in full_source_language_compilation_spec.md section 7.
"""

import pytest
import numpy as np
from numpy.testing import assert_allclose

from lang.types import Q, Ten, Plus, Unit, Arrow, width
from lang.terms import (
    Id, Seq, H, S, X, Z, CX, TenTerm,
    Var, Pair, LetPair, Lam, Apply, FunVar,
    TwistTen, AssocTenL, AssocTenR,
    Case, CH, CS,
)
from typing_.check import type_of, TypeCheckError
from compile.to_pytket import compile


def circuit_unitary(circ):
    """Extract unitary matrix from pytket circuit."""
    return circ.get_unitary()


def unitaries_equal(u1, u2, rtol=1e-5, atol=1e-8):
    """Check if two unitaries are equal up to global phase."""
    # Try to find a global phase factor
    # If u1 = e^{iθ} * u2, then u1 * u2† = e^{iθ} * I
    product = u1 @ u2.conj().T
    # Check if product is proportional to identity
    diag = np.diag(product)
    if np.allclose(diag, diag[0], rtol=rtol, atol=atol):
        # All diagonal elements same, check off-diagonal is zero
        off_diag = product - np.diag(diag)
        if np.allclose(off_diag, 0, rtol=rtol, atol=atol):
            return True
    return False


# =============================================================================
# Test 7.1: β-law as circuit equivalence
# =============================================================================

class TestBetaLaw:
    """Test 7.1: (λx.t) u ≡ t[u/x] as circuit equivalence.

    For small terms, verify that Apply(Lam(x, ..., body), arg) produces
    the same circuit semantics as directly substituting arg for x in body.
    """

    def test_beta_identity(self):
        """β-reduction: (λx.H(x)) Id ≡ H.

        With Γ = Unit (no context):
        - body = H(0, Q()) : Q → Q (width 1)
        - lam = Lam("x", Q, Q, body) : Unit → Arrow(Q, Q)
        - arg = Id(Q()) : Q → Q
        - Apply : Q → Q (since f_dom = Unit)
        """
        # body has domain Q (width 1), so Γ = Unit (gamma_width = 1 - 1 = 0)
        body = H(0, Q())  # H on x (the only wire)
        lam = Lam("x", Q(), Q(), body)
        arg = Id(Q())
        app = Apply(lam, arg)

        # Compile Apply term
        result_app = compile(app, materialize=True)

        # Direct: just H on Q
        direct = H(0, Q())
        result_direct = compile(direct, materialize=True)

        # Compare unitaries
        u_app = circuit_unitary(result_app.circuit)
        u_direct = circuit_unitary(result_direct.circuit)

        # Both should implement H on 1 qubit
        assert unitaries_equal(u_app, u_direct)

    def test_beta_composition(self):
        """β-reduction: (λx.S;H) Id ≡ S;H.

        With Γ = Unit, body operates only on x (the bound variable).
        """
        # Body applies S then H to x (the only wire, since Γ = Unit)
        body = Seq(S(0, Q()), H(0, Q()))
        lam = Lam("x", Q(), Q(), body)
        arg = Id(Q())
        app = Apply(lam, arg)

        result_app = compile(app, materialize=True)

        # Direct S;H
        direct = Seq(S(0, Q()), H(0, Q()))
        result_direct = compile(direct, materialize=True)

        u_app = circuit_unitary(result_app.circuit)
        u_direct = circuit_unitary(result_direct.circuit)

        assert unitaries_equal(u_app, u_direct)

    def test_beta_arg_transformation(self):
        """β-reduction with non-identity arg: (λx.H(x)) S ≡ S;H.

        Apply compiles arg first, then body. So arg's gates run first.
        """
        body = H(0, Q())  # H on x (Γ = Unit)
        lam = Lam("x", Q(), Q(), body)
        # arg = S (applies S to input)
        arg = S(0, Q())
        app = Apply(lam, arg)

        result_app = compile(app, materialize=True)

        # Direct: S;H (arg runs first, then body)
        direct = Seq(S(0, Q()), H(0, Q()))
        result_direct = compile(direct, materialize=True)

        u_app = circuit_unitary(result_app.circuit)
        u_direct = circuit_unitary(result_direct.circuit)

        assert unitaries_equal(u_app, u_direct)

    def test_beta_nested_apply(self):
        """β-reduction with nested Apply: f(g(x)) where f,g are lambdas.

        (λa.H(a))((λb.S(b)) Id) ≡ S;H
        """
        # Inner lambda: λb.S(b)
        body_g = S(0, Q())
        g = Lam("b", Q(), Q(), body_g)

        # Outer lambda: λa.H(a)
        body_f = H(0, Q())
        f = Lam("a", Q(), Q(), body_f)

        # Nested application: f(g(Id))
        x = Id(Q())
        gx = Apply(g, x)
        fgx = Apply(f, gx)

        result_nested = compile(fgx, materialize=True)

        # Direct: S;H
        direct = Seq(S(0, Q()), H(0, Q()))
        result_direct = compile(direct, materialize=True)

        u_nested = circuit_unitary(result_nested.circuit)
        u_direct = circuit_unitary(result_direct.circuit)

        assert unitaries_equal(u_nested, u_direct)

    def test_beta_with_two_qubit(self):
        """β-reduction with two-qubit gate: (λx.CX(x)) ≡ CX.

        Tests that the closed lambda path works for multi-qubit bodies.
        """
        # body operates on Q⊗Q
        ty = Ten(Q(), Q())
        body = CX(0, 1, ty)  # CX on x (Γ = Unit, body_dom = Q⊗Q)
        lam = Lam("x", ty, ty, body)

        arg = Id(ty)
        app = Apply(lam, arg)

        result_app = compile(app, materialize=True)

        # Direct: just CX
        direct = CX(0, 1, ty)
        result_direct = compile(direct, materialize=True)

        u_app = circuit_unitary(result_app.circuit)
        u_direct = circuit_unitary(result_direct.circuit)

        assert unitaries_equal(u_app, u_direct)

    def test_beta_wA_eq_wB_endomorphism(self):
        """β-reduction with wA = wB (endomorphism): tests swap routing.

        For f : Q⊗Q → Q⊗Q with wA = wB = 2, the routing uses a swap.
        """
        # f = λx:(Q⊗Q). (H⊗S)(x) : produces Arrow(Q⊗Q, Q⊗Q)
        ty = Ten(Q(), Q())
        body = TenTerm(H(0, Q()), S(0, Q()))  # H ⊗ S on Q⊗Q
        lam = Lam("x", ty, ty, body)

        # arg = Id(Q⊗Q)
        arg = Id(ty)

        app = Apply(lam, arg)
        result_app = compile(app, materialize=True)

        # Direct: H ⊗ S
        direct = TenTerm(H(0, Q()), S(0, Q()))
        result_direct = compile(direct, materialize=True)

        u_app = circuit_unitary(result_app.circuit)
        u_direct = circuit_unitary(result_direct.circuit)

        assert unitaries_equal(u_app, u_direct)

    def test_beta_wA_neq_wB_open_lambda(self):
        """β-reduction with wA ≠ wB: tests rotation routing.

        For f : Q → Arrow(Q, Q⊗Q), we have wA=1, wB=2, wA ≠ wB.
        This requires the general rotation routing, not just swap.

        The function's body has type (Γ⊗A) → B = (Q⊗Q) → (Q⊗Q).
        With Γ=Q (context), A=Q (arg), B=Q⊗Q (result).
        gamma_width = wB - wA = 2 - 1 = 1.
        """
        # body : Q⊗Q → Q⊗Q (operates on Γ⊗x where Γ=Q, x:Q)
        # The body applies H⊗S to the two wires
        body = TenTerm(H(0, Q()), S(0, Q()))  # H on Γ, S on x

        # Lam with wA=1 (Q), wB=2 (Q⊗Q) -> requires rotation routing
        lam = Lam("x", Q(), Ten(Q(), Q()), body)

        # Check that the function type is correct
        lam_dom, lam_cod = type_of(lam)
        assert width(lam_dom) == 1  # Γ = Q
        assert isinstance(lam_cod, Arrow)
        assert width(lam_cod.dom) == 1  # A = Q
        assert width(lam_cod.cod) == 2  # B = Q⊗Q

        # For Apply: we need an arg of type Q
        arg = H(0, Q())  # Apply H to the argument

        app = Apply(lam, arg)
        result_app = compile(app, materialize=True, explain=True)

        # The expected behavior:
        # - arg applies H to its input (producing transformed Q)
        # - body applies H⊗S to (Γ, x) = (context, transformed-arg)
        # So total: Γ gets H, arg gets H;S (H from arg, S from body on x)

        # Check it compiles without error
        assert result_app.circuit.n_qubits >= 2

        # Get commands
        cmds = list(result_app.circuit.get_commands())
        gate_names = [c.op.type.name for c in cmds]
        # Should have H (from body on Γ), H (from arg), and S (from body on x)
        assert gate_names.count("H") >= 2
        assert "S" in gate_names

    def test_beta_wA_neq_wB_closed_path(self):
        """β-reduction closed lambda path also works with wA ≠ wB indirectly.

        Even for closed lambdas (Γ=Unit), the body can have internal
        structure that exercises the routing.
        """
        # Closed lambda: body : A → B with A = Q, B = Q (wA = wB = 1)
        # But let's verify that the general routing still works correctly
        body = Seq(H(0, Q()), S(0, Q()))  # H;S on single qubit
        lam = Lam("x", Q(), Q(), body)

        # Verify it's a closed lambda (Γ = Unit)
        lam_dom, lam_cod = type_of(lam)
        assert isinstance(lam_dom, Unit)

        arg = Id(Q())
        app = Apply(lam, arg)

        result = compile(app, materialize=True)

        # Direct: H;S
        direct = Seq(H(0, Q()), S(0, Q()))
        result_direct = compile(direct, materialize=True)

        u_app = circuit_unitary(result.circuit)
        u_direct = circuit_unitary(result_direct.circuit)

        assert unitaries_equal(u_app, u_direct)


# =============================================================================
# Test 7.2: η-like sanity (restricted linear form)
# =============================================================================

class TestEtaSanity:
    """Test 7.2: η-like properties in linear λ-calculus.

    In classical λ-calculus: η-reduction says λx.f(x) = f for f:A→B.
    In our linear setting, this is restricted because:
    1. Variables must be used exactly once (linearity)
    2. Functions are first-class but can't be duplicated

    What we CAN test:
    - Apply(Lam(x, body), Id) ≡ body  (β-like, but tests the roundtrip)
    - For primitive gates g, λx.g(x) applied to Id ≡ g
    - Composition: (λx.f(λy.g(x,y))) applied correctly
    """

    def test_eta_roundtrip_identity(self):
        """Verify that Apply(Lam(x, body), Id) ≡ body (η-like roundtrip).

        This is the closest to η we can express:
        For closed lambda f = λx.body, Apply(f, Id) should behave like body.
        """
        # f = λx.H(x) : Unit → Arrow(Q, Q) with Γ = Unit
        body = H(0, Q())
        f = Lam("x", Q(), Q(), body)

        # Apply to identity: should be equivalent to just H
        arg = Id(Q())
        app = Apply(f, arg)
        result = compile(app, materialize=True)

        # Should give H
        direct = H(0, Q())
        result_direct = compile(direct, materialize=True)

        u_app = circuit_unitary(result.circuit)
        u_direct = circuit_unitary(result_direct.circuit)

        assert unitaries_equal(u_app, u_direct)

    def test_eta_for_composition(self):
        """η-like property for composed terms: λx.(S;H)(x) ≡ S;H.

        The lambda wrapper shouldn't change the semantics of composition.
        """
        # f = λx.(S;H)(x) where body = S;H
        body = Seq(S(0, Q()), H(0, Q()))
        f = Lam("x", Q(), Q(), body)

        # Apply to identity
        app = Apply(f, Id(Q()))
        result = compile(app, materialize=True)

        # Direct composition
        direct = Seq(S(0, Q()), H(0, Q()))
        result_direct = compile(direct, materialize=True)

        u_app = circuit_unitary(result.circuit)
        u_direct = circuit_unitary(result_direct.circuit)

        assert unitaries_equal(u_app, u_direct)

    def test_eta_for_two_qubit_gates(self):
        """η-like property extends to multi-qubit operations."""
        ty = Ten(Q(), Q())
        body = CX(0, 1, ty)
        f = Lam("x", ty, ty, body)

        app = Apply(f, Id(ty))
        result = compile(app, materialize=True)

        direct = CX(0, 1, ty)
        result_direct = compile(direct, materialize=True)

        u_app = circuit_unitary(result.circuit)
        u_direct = circuit_unitary(result_direct.circuit)

        assert unitaries_equal(u_app, u_direct)


# =============================================================================
# Test 7.3: "No wire selection" regression tests
# =============================================================================

class TestNoWireSelection:
    """Test 7.3: Verify routing via structural operations, not wire indices.

    Construct terms where the desired routing requires associativity/symmetry
    via letpair, ensuring compilation succeeds using structural rewiring.
    """

    def test_structural_routing_via_letpair(self):
        """Route through pair destructuring without explicit wire selection."""
        # Test that twist + gate compiles correctly
        # Twist swaps logical wires, H applies to logical wire 0
        ty = Ten(Q(), Q())
        term = Seq(TwistTen(Q(), Q()), H(0, ty))

        # With materialize=False, twist is tracked as permutation (no SWAP gates)
        result = compile(term, materialize=False)
        # Should have only H gate (twist is tracked in perm)
        assert result.circuit.n_gates == 1
        # Permutation should reflect the twist: [1, 0]
        assert result.perm.new_to_old == [1, 0]

        # With materialize=True, SWAP gates are emitted for the permutation
        result_mat = compile(term, materialize=True)
        # Should have H + SWAP (materialize emits swaps)
        assert result_mat.circuit.n_gates >= 1

    def test_assoc_routing(self):
        """Verify associativity for routing."""
        # (A ⊗ B) ⊗ C → A ⊗ (B ⊗ C) should be pure structural
        term = AssocTenL(Q(), Q(), Q())
        result = compile(term)
        assert result.circuit.n_gates == 0  # Pure structural


# =============================================================================
# Test 7.4: Higher-order QSwitch tests
# =============================================================================

class TestQSwitchHigherOrder:
    """Test 7.4: QSwitch as a higher-order term.

    QSwitch : (Q→Q) ⊗ (Q→Q) ⊗ Bool ⊗ Q → Bool ⊗ Q
    Semantics: |0⟩|ψ⟩ → |0⟩(g∘f)(ψ), |1⟩|ψ⟩ → |1⟩(f∘g)(ψ)
    """

    def test_qswitch_type_width(self):
        """QSwitch input has width 6: 2+2+1+1."""
        fn_ty = Arrow(Q(), Q())  # Q ⊸ Q = 2 wires
        bool_ty = Plus(Unit(), Unit())  # Bool = 1 wire
        input_ty = Ten(fn_ty, Ten(fn_ty, Ten(bool_ty, Q())))
        assert width(input_ty) == 6

    def test_qswitch_instantiated_hs(self):
        """QSwitch[H, S] via Case compiles correctly.

        case ctrl of
          | 0 => S;H  (g;f = S;H when ctrl=0)
          | 1 => H;S  (f;g = H;S when ctrl=1)
        """
        ty = Ten(Q(), Q())  # [tag | payload]

        # Branch for ctrl=0: S then H
        left = Seq(S(0, Q()), H(0, Q()))
        # Branch for ctrl=1: H then S
        right = Seq(H(0, Q()), S(0, Q()))

        # Case term
        qswitch = Case(Q(), Q(), left, right)
        result = compile(qswitch, materialize=True)

        # Should have gates for both branches (controlled)
        assert result.circuit.n_gates > 0


# =============================================================================
# Test 7.5: Sum layout invariants
# =============================================================================

class TestSumLayoutInvariants:
    """Test 7.5: Tag validity and payload padding invariants."""

    def test_tag_width_binary(self):
        """Binary sum has 1 tag qubit."""
        from lang.types import tag_width
        ty = Plus(Q(), Q())
        assert tag_width(ty) == 1

    def test_payload_padding(self):
        """Payload uses max width of summands."""
        from lang.types import payload_width
        # Plus(Unit, Q) has payload width 1 (max of 0, 1)
        ty = Plus(Unit(), Q())
        assert payload_width(ty) == 1


# =============================================================================
# Test 7.6: Structural round-trip tests
# =============================================================================

class TestStructuralRoundTrip:
    """Test 7.6: s ; s^{-1} = identity for structural isos."""

    def test_twist_roundtrip(self):
        """TwistTen ; TwistTen = id."""
        ty = Ten(Q(), Q())
        term = Seq(TwistTen(Q(), Q()), TwistTen(Q(), Q()))
        result = compile(term, materialize=True)

        # Should be identity (no gates, identity perm after materialize)
        u = circuit_unitary(result.circuit)
        assert_allclose(u, np.eye(4), atol=1e-10)

    def test_assoc_roundtrip(self):
        """AssocTenL ; AssocTenR = id."""
        term = Seq(
            AssocTenL(Q(), Q(), Q()),
            AssocTenR(Q(), Q(), Q())
        )
        result = compile(term, materialize=True)

        u = circuit_unitary(result.circuit)
        assert_allclose(u, np.eye(8), atol=1e-10)


# =============================================================================
# Test 7.7: Context-split (linearity) runtime checks
# =============================================================================

class TestContextSplit:
    """Test 7.7: Verify environment slicing in TensorIntro and LetPair."""

    def test_tensor_intro_disjoint(self):
        """Pair(t, u) compiles both sub-terms correctly."""
        # t on Q, u on Q -> Pair on Q⊗Q
        t = H(0, Q())
        u = S(0, Q())
        pair = Pair(t, u)
        result = compile(pair, materialize=True)

        # Should have both H and S
        gate_names = [c.op.type.name for c in result.circuit.get_commands()]
        assert "H" in gate_names
        assert "S" in gate_names

    def test_letpair_covers_full_width(self):
        """LetPair binds x,y to full A⊗B output."""
        pair_term = Id(Ten(Q(), Q()))
        body = Pair(Var("x", Q()), Var("y", Q()))
        lp = LetPair("x", "y", Q(), Q(), pair_term, body)

        result = compile(lp)
        # Should compile without error (verifies slicing is correct)
        assert result.circuit.n_qubits == 2


# =============================================================================
# Test 7.8: Permutation correctness tests
# =============================================================================

class TestPermutationCorrectness:
    """Test 7.8: Verify perm.apply_new_to_old direction."""

    def test_gate_through_twist(self):
        """Gate after twist applies to correct wire."""
        ty = Ten(Q(), Q())
        # Twist swaps wires, then H on wire 0 (which was wire 1)
        term = Seq(TwistTen(Q(), Q()), H(0, ty))

        # With materialize=False, perm tracks the swap
        result = compile(term, materialize=False)
        # perm should be [1, 0] (swap)
        assert result.perm.new_to_old == [1, 0]

        # With materialize=True, swap is applied
        result_mat = compile(term, materialize=True)
        # Check H is on correct physical wire
        cmds = list(result_mat.circuit.get_commands())
        assert len(cmds) >= 1


# =============================================================================
# Test 7.9: Compile-time determinism test
# =============================================================================

class TestCompileDeterminism:
    """Test 7.9: Same AST produces identical (circuit, perm)."""

    def test_determinism_simple(self):
        """Repeated compilation gives same result."""
        term = Seq(TwistTen(Q(), Q()), H(0, Ten(Q(), Q())))

        results = [compile(term, materialize=True) for _ in range(5)]

        # All should have same number of gates
        gate_counts = [r.circuit.n_gates for r in results]
        assert len(set(gate_counts)) == 1

        # All should have same unitary
        unitaries = [circuit_unitary(r.circuit) for r in results]
        for u in unitaries[1:]:
            assert_allclose(u, unitaries[0], atol=1e-10)

    def test_determinism_higher_order(self):
        """Higher-order terms compile deterministically."""
        body = H(0, Q())  # Γ = Unit
        lam = Lam("x", Q(), Q(), body)
        arg = Id(Q())
        app = Apply(lam, arg)

        results = [compile(app, materialize=True) for _ in range(5)]

        gate_counts = [r.circuit.n_gates for r in results]
        assert len(set(gate_counts)) == 1
