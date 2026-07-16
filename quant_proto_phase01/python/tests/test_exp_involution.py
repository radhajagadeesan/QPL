# tests/test_exp_involution.py
"""Tests for ExpSwap and ExpInvolution: exponentials of structural involutions.

These tests verify:
- ExpSwap compiles to XXPhase, YYPhase, ZZPhase gates
- ExpInvolution decomposes structural involutions into ExpSwap atoms
- Involution verification works correctly
"""

import pytest
import math
from pytket.circuit import OpType

from lang.types import Q, Ten, Plus, Arrow, width
from lang.terms import (
    TwistTen, TwistPlus, AssocTenL, AssocTenR, Seq, Id,
    ExpSwap, ExpInvolution, H, CX,
)
from typing_.check import type_of, assert_well_typed, TypeCheckError
from compile.to_pytket import compile
from core.perm import identity, WirePerm, is_involution, decompose_involution


class TestExpSwapBasics:
    """Basic tests for ExpSwap term."""

    def test_expswap_construction(self):
        """ExpSwap can be constructed with theta and wire indices."""
        exp = ExpSwap(theta=0.5, i=0, j=1)
        assert exp.theta == 0.5
        assert exp.i == 0
        assert exp.j == 1

    def test_expswap_default_type(self):
        """ExpSwap defaults to 2-qubit type."""
        exp = ExpSwap(theta=0.5)
        assert exp.ty_total == Ten(Q(), Q())

    def test_expswap_type_check_valid(self):
        """Valid ExpSwap passes type checking."""
        exp = ExpSwap(theta=0.5, i=0, j=1, ty_total=Ten(Q(), Q()))
        dom, cod = type_of(exp)
        assert dom == cod == Ten(Q(), Q())

    def test_expswap_type_check_same_index(self):
        """ExpSwap with same indices fails type check."""
        exp = ExpSwap(theta=0.5, i=0, j=0, ty_total=Ten(Q(), Q()))
        with pytest.raises(TypeCheckError):
            type_of(exp)

    def test_expswap_type_check_out_of_range(self):
        """ExpSwap with out of range index fails type check."""
        exp = ExpSwap(theta=0.5, i=0, j=5, ty_total=Ten(Q(), Q()))
        with pytest.raises(TypeCheckError):
            type_of(exp)


class TestExpSwapCompilation:
    """Tests for ExpSwap compilation."""

    def test_expswap_compiles_to_three_gates(self):
        """ExpSwap compiles to XXPhase, YYPhase, ZZPhase."""
        ty = Ten(Q(), Q())
        exp = ExpSwap(theta=0.5, i=0, j=1, ty_total=ty)

        result = compile(exp)
        cmds = list(result.circuit.get_commands())

        # Should have 3 gates: XXPhase, YYPhase, ZZPhase
        assert len(cmds) == 3
        op_names = [c.op.type.name for c in cmds]
        assert "XXPhase" in op_names
        assert "YYPhase" in op_names
        assert "ZZPhase" in op_names

    def test_expswap_parameter_conversion(self):
        """ExpSwap converts theta to pytket's alpha parameter."""
        ty = Ten(Q(), Q())
        theta = 0.5
        exp = ExpSwap(theta=theta, i=0, j=1, ty_total=ty)

        result = compile(exp)
        cmds = list(result.circuit.get_commands())

        # All gates should have the same parameter: alpha = -theta/pi
        # Note: pytket normalizes parameters to [0, 4) range, adding 4 to negatives
        expected_alpha = -theta / math.pi
        # Pytket normalizes to [0, 4) by adding 4 to negative values
        if expected_alpha < 0:
            expected_alpha += 4
        for cmd in cmds:
            actual_alpha = cmd.op.params[0]
            assert abs(actual_alpha - expected_alpha) < 1e-10

    def test_expswap_with_offset(self):
        """ExpSwap respects wire offsets in larger circuits."""
        ty = Ten(Ten(Q(), Q()), Ten(Q(), Q()))  # 4 qubits
        # ExpSwap on wires 2 and 3
        exp = ExpSwap(theta=0.5, i=2, j=3, ty_total=ty)

        result = compile(exp)
        cmds = list(result.circuit.get_commands())

        # All gates should be on wires 2 and 3
        for cmd in cmds:
            qubits = [q.index[0] for q in cmd.qubits]
            assert set(qubits) == {2, 3}


class TestExpInvolutionBasics:
    """Basic tests for ExpInvolution term."""

    def test_exp_involution_construction(self):
        """ExpInvolution can be constructed with theta and body."""
        body = TwistTen(Q(), Q())
        exp = ExpInvolution(theta=0.5, body=body)
        assert exp.theta == 0.5
        assert exp.body == body

    def test_exp_involution_type_check(self):
        """ExpInvolution type is same as body's type."""
        body = TwistTen(Q(), Q())
        exp = ExpInvolution(theta=0.5, body=body)

        dom, cod = type_of(exp)
        body_dom, body_cod = type_of(body)
        assert dom == body_dom
        assert cod == body_cod

    def test_exp_involution_rejects_arrow_body(self):
        """ExpInvolution body type must be first-order — no Arrow types."""
        body = TwistTen(Q(), Q())
        higher_ty = Arrow(Q(), Q())
        with pytest.raises(ValueError, match="first-order"):
            ExpInvolution(theta=0.5, body=body, ty_total=higher_ty)


class TestExpInvolutionCompilation:
    """Tests for ExpInvolution compilation."""

    def test_twistten_is_involution(self):
        """TwistTen(Q,Q) is an involution: SWAP² = I."""
        import numpy as np
        body = TwistTen(Q(), Q())
        result = compile(body, materialize=True)
        U = result.circuit.get_unitary()
        # SWAP² = I
        assert np.allclose(U @ U, np.eye(4), atol=1e-9)

    def test_exp_twistten_compiles(self):
        """exp(iθ · TwistTen) compiles via direct unitary synthesis."""
        import numpy as np
        body = TwistTen(Q(), Q())
        theta = 0.5
        exp = ExpInvolution(theta=theta, body=body)

        result = compile(exp, materialize=True)
        U = result.circuit.get_unitary()

        # TwistTen = SWAP, so exp(iθ·SWAP) = cos(θ)·I + i·sin(θ)·SWAP
        SWAP = np.array([[1,0,0,0],[0,0,1,0],[0,1,0,0],[0,0,0,1]], dtype=complex)
        expected = math.cos(theta) * np.eye(4) + 1j * math.sin(theta) * SWAP
        assert np.allclose(U, expected, atol=1e-9)

    def test_exp_twistplus_compiles(self):
        """exp(iθ · TwistPlus) compiles correctly via direct unitary synthesis.

        TwistPlus(Q,Q) = X⊗I on Plus(Q,Q) (2 qubits: 1 tag + 1 payload).
        ExpInvolution compiles the body to get U, verifies U²=I, and emits
        cos(θ)·I + i·sin(θ)·U.
        """
        import numpy as np
        body = TwistPlus(Q(), Q())
        theta = 0.5
        exp = ExpInvolution(theta=theta, body=body)

        result = compile(exp, materialize=True)
        U = result.circuit.get_unitary()

        # TwistPlus(Q,Q) = X⊗I on 2 qubits (tag flip on wire 0, identity on payload)
        X_mat = np.array([[0,1],[1,0]], dtype=complex)
        body_U = np.kron(X_mat, np.eye(2))
        expected = math.cos(theta) * np.eye(4) + 1j * math.sin(theta) * body_U
        assert np.allclose(U, expected, atol=1e-9)

    def test_exp_identity_produces_no_gates(self):
        """exp(iθ · Id) produces no gates (identity has no transpositions)."""
        body = Id(Ten(Q(), Q()))
        exp = ExpInvolution(theta=0.5, body=body)

        result = compile(exp)
        cmds = list(result.circuit.get_commands())

        # Identity permutation has no transpositions
        assert len(cmds) == 0

    def test_exp_twistten_twice_is_identity(self):
        """exp(iθ · TwistTen ; TwistTen) is exp(iθ · Id) = Id."""
        body = Seq(TwistTen(Q(), Q()), TwistTen(Q(), Q()))
        exp = ExpInvolution(theta=0.5, body=body)

        result = compile(exp)
        cmds = list(result.circuit.get_commands())

        # TwistTen twice = identity, which is involution with no transpositions
        assert len(cmds) == 0

    def test_exp_involution_with_non_involution_fails(self):
        """ExpInvolution with non-involutive body fails at compile time."""
        # TwistTen(Q, Ten(Q,Q)) is NOT an involution (it's a 3-cycle [1,2,0])
        body = TwistTen(Q(), Ten(Q(), Q()))
        exp = ExpInvolution(theta=0.5, body=body)

        # This should fail during compilation because the body is not involutive
        with pytest.raises(TypeCheckError) as exc:
            compile(exp)
        assert "involution" in str(exc.value).lower()

    def test_exp_involution_rejects_non_involution(self):
        """ExpInvolution rejects body where U² ≠ I."""
        # SWAP · (H⊗I) is not an involution
        ty = Ten(Q(), Q())
        body = Seq(TwistTen(Q(), Q()), H(0, ty))
        exp = ExpInvolution(theta=0.5, body=body, ty_total=ty)

        with pytest.raises(TypeCheckError) as exc:
            compile(exp)
        assert "involution" in str(exc.value).lower()


class TestDecomposeInvolution:
    """Tests for the decompose_involution helper."""

    def test_identity_decomposes_to_empty(self):
        """Identity permutation has no transpositions."""
        p = identity(4)
        swaps = decompose_involution(p)
        assert swaps == []

    def test_single_swap_decomposes(self):
        """Single swap (0,1) decomposes to [(0,1)]."""
        p = WirePerm([1, 0])
        swaps = decompose_involution(p)
        assert swaps == [(0, 1)]

    def test_two_swaps_decompose(self):
        """Two disjoint swaps decompose correctly."""
        # (0,1)(2,3) permutation: [1, 0, 3, 2]
        p = WirePerm([1, 0, 3, 2])
        swaps = decompose_involution(p)
        assert set(swaps) == {(0, 1), (2, 3)}

    def test_non_involution_raises(self):
        """Non-involutive permutation raises error."""
        # 3-cycle (0,1,2): not an involution
        p = WirePerm([1, 2, 0])
        with pytest.raises(ValueError):
            decompose_involution(p)


class TestExpInvolutionIntegration:
    """Integration tests for exp involutions in circuits."""

    def test_exp_involution_in_sequence(self):
        """ExpInvolution can be used in sequence with gates."""
        import numpy as np
        ty = Ten(Q(), Q())
        theta = 0.5
        prog = Seq(
            H(0, ty),
            ExpInvolution(theta=theta, body=TwistTen(Q(), Q()), ty_total=ty),
            CX(0, 1, ty),
        )

        result = compile(prog, materialize=True)

        # Verify the circuit produces a valid unitary
        U = result.circuit.get_unitary()
        assert U.shape == (4, 4)
        # Unitary check: U†U = I
        assert np.allclose(U @ U.conj().T, np.eye(4), atol=1e-9)


class TestExpInvolutionCompositionLaw:
    """Test exp_i(θ,P) ; exp_i(θ,P) = exp_i(2θ,P) via unitary extraction."""

    @staticmethod
    def matrices_equal_up_to_phase(A, B, tol=1e-9):
        """Check if A = e^{iφ} · B for some phase φ."""
        import numpy as np
        for i in range(B.shape[0]):
            for j in range(B.shape[1]):
                if abs(B[i, j]) > tol:
                    if abs(A[i, j]) < tol:
                        return False, 0
                    phase = A[i, j] / B[i, j]
                    diff = abs(A - phase * B).max()
                    return diff < tol, phase
        return False, 0

    def test_twist_compiles_to_swap(self):
        """TwistTen(Q,Q) compiles to SWAP (verified by unitary extraction)."""
        import numpy as np
        twist = TwistTen(Q(), Q())
        result = compile(twist, materialize=True)
        U = result.circuit.get_unitary()

        SWAP = np.array([[1,0,0,0],[0,0,1,0],[0,1,0,0],[0,0,0,1]], dtype=complex)
        match, _ = self.matrices_equal_up_to_phase(U, SWAP)
        assert match, "TwistTen should compile to SWAP"

    def test_composition_equals_swap_up_to_phase(self):
        """exp_i(π/4, twist) ; exp_i(π/4, twist) = SWAP up to global phase."""
        import numpy as np
        ty = Ten(Q(), Q())
        twist = TwistTen(Q(), Q())
        theta = math.pi / 4

        exp_twist = ExpInvolution(theta=theta, body=twist, ty_total=ty)
        composed = Seq(exp_twist, exp_twist)
        result = compile(composed)
        U = result.circuit.get_unitary()

        SWAP = np.array([[1,0,0,0],[0,0,1,0],[0,1,0,0],[0,0,0,1]], dtype=complex)
        match, phase = self.matrices_equal_up_to_phase(U, SWAP)
        assert match, "Composition should equal SWAP up to phase"
        assert abs(abs(phase) - 1.0) < 1e-9, "Phase should have magnitude 1"

    def test_composition_law_pi_4(self):
        """exp_i(π/4) ; exp_i(π/4) = exp_i(π/2) (verified by unitary)."""
        import numpy as np
        ty = Ten(Q(), Q())
        twist = TwistTen(Q(), Q())
        theta = math.pi / 4

        # Compile composition
        exp_twist = ExpInvolution(theta=theta, body=twist, ty_total=ty)
        composed = Seq(exp_twist, exp_twist)
        U_composed = compile(composed).circuit.get_unitary()

        # Compile direct exp_i(2θ)
        exp_double = ExpInvolution(theta=2*theta, body=twist, ty_total=ty)
        U_double = compile(exp_double).circuit.get_unitary()

        match, _ = self.matrices_equal_up_to_phase(U_composed, U_double)
        assert match, "exp(θ);exp(θ) should equal exp(2θ)"

    @pytest.mark.parametrize("theta", [math.pi/8, math.pi/6, math.pi/4, math.pi/3])
    def test_composition_law_various_angles(self, theta):
        """Test composition law for various angles (verified by unitary)."""
        import numpy as np
        ty = Ten(Q(), Q())
        twist = TwistTen(Q(), Q())

        exp_twist = ExpInvolution(theta=theta, body=twist, ty_total=ty)
        composed = Seq(exp_twist, exp_twist)
        U_composed = compile(composed).circuit.get_unitary()

        exp_double = ExpInvolution(theta=2*theta, body=twist, ty_total=ty)
        U_double = compile(exp_double).circuit.get_unitary()

        match, _ = self.matrices_equal_up_to_phase(U_composed, U_double)
        assert match, f"Composition law failed for θ={theta}"


class TestPauliConjugation:
    """Test Pauli operations on qubit encoded as I+I.

    With Option B, Plus(Unit(), Unit()) = 1 wire (just the tag qubit).
    The logical qubit IS the physical tag qubit — no extraction needed.

    NOTE: ExpInvolution(TwistPlus) no longer captures the X gate (since
    wire perm is identity with Option B). These tests are adapted accordingly.
    """

    @staticmethod
    def matrices_equal_up_to_phase(A, B, tol=1e-9):
        import numpy as np
        for i in range(B.shape[0]):
            for j in range(B.shape[1]):
                if abs(B[i,j]) > tol:
                    if abs(A[i,j]) < tol:
                        return False, 0
                    phase = A[i,j] / B[i,j]
                    diff = abs(A - phase * B).max()
                    return diff < tol, phase
        return False, 0

    def test_twist_plus_is_pauli_x(self):
        """TwistPlus(I,I) = Pauli-X on logical qubit (the tag qubit).

        With Option B, Plus(Unit(), Unit()) = 1 wire. TwistPlus emits X gate.
        """
        import numpy as np
        from lang.types import Unit, Plus
        ty = Plus(Unit(), Unit())
        twist = TwistPlus(Unit(), Unit())
        U = compile(twist, materialize=True).circuit.get_unitary()
        expected = np.array([[0,1],[1,0]], dtype=complex)
        match, _ = self.matrices_equal_up_to_phase(U, expected)
        assert match, "TwistPlus(I,I) should be Pauli-X"

    def test_z_gate_on_wire0_is_pauli_z(self):
        """Z[0] on I+I = Pauli-Z on logical qubit (the tag qubit).

        With Option B, the tag qubit is wire 0 (the only wire).
        """
        import numpy as np
        from lang.types import Unit, Plus
        from lang.terms import Z
        ty = Plus(Unit(), Unit())
        Z_gate = Z(0, ty)
        U = compile(Z_gate).circuit.get_unitary()
        expected = np.array([[1,0],[0,-1]], dtype=complex)
        match, _ = self.matrices_equal_up_to_phase(U, expected)
        assert match, "Z[0] should be Pauli-Z"

    def test_conjugation_equals_y(self):
        """exp(iπ/4 · X) ; Z ; exp(-iπ/4 · X) = -Y (Pauli conjugation).

        With direct unitary synthesis, ExpInvolution(TwistPlus) correctly
        produces exp(iθ·X). Conjugating Z by exp(iπ/4·X) rotates Z → -Y.
        """
        import numpy as np
        from lang.types import Unit, Plus
        from lang.terms import Z
        ty = Plus(Unit(), Unit())
        twist = TwistPlus(Unit(), Unit())

        exp_X_pos = ExpInvolution(theta=math.pi/4, body=twist, ty_total=ty)
        exp_X_neg = ExpInvolution(theta=-math.pi/4, body=twist, ty_total=ty)
        Z_gate = Z(0, ty)

        conjugation = Seq(exp_X_pos, Z_gate, exp_X_neg)
        U = compile(conjugation, materialize=True).circuit.get_unitary()

        # exp(iπ/4·X) Z exp(-iπ/4·X) = -Y
        expected_neg_Y = np.array([[0, 1], [-1, 0]], dtype=complex)
        match, _ = self.matrices_equal_up_to_phase(U, expected_neg_Y)
        assert match, f"Conjugation should give -Y, got:\n{U}"
