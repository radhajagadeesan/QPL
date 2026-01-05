# tests/test_exp_involution.py
"""Tests for ExpSwap and ExpInvolution: exponentials of structural involutions.

These tests verify:
- ExpSwap compiles to XXPhase, YYPhase, ZZPhase gates
- ExpInvolution decomposes structural involutions into ExpSwap atoms
- Involution verification works correctly
- Both compile() and compile_goi() handle these terms
"""

import pytest
import math
from pytket.circuit import OpType

from lang.types import Q, Ten, Plus, width
from lang.terms import (
    TwistTen, TwistPlus, AssocTenL, AssocTenR, Seq, Id,
    ExpSwap, ExpInvolution, H, CX,
)
from typing_.check import type_of, assert_well_typed, TypeCheckError
from compile.to_pytket import compile, compile_goi, CompiledGOI, _compile_structural_to_perm
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

    def test_expswap_compile_goi(self):
        """ExpSwap compiles correctly via compile_goi."""
        ty = Ten(Q(), Q())
        exp = ExpSwap(theta=0.5, i=0, j=1, ty_total=ty)

        result = compile_goi(exp)
        assert isinstance(result, CompiledGOI)

        cmds = list(result.circuit.get_commands())
        assert len(cmds) == 3

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


class TestExpInvolutionCompilation:
    """Tests for ExpInvolution compilation."""

    def test_twistten_is_involution(self):
        """TwistTen(Q,Q) is an involution: (0,1) swap."""
        body = TwistTen(Q(), Q())
        perm = _compile_structural_to_perm(body)

        assert is_involution(perm)
        assert perm.new_to_old == [1, 0]

    def test_exp_twistten_compiles(self):
        """exp(iθ · TwistTen) compiles to ExpSwap(0,1)."""
        body = TwistTen(Q(), Q())
        exp = ExpInvolution(theta=0.5, body=body)

        result = compile(exp)
        cmds = list(result.circuit.get_commands())

        # TwistTen is one transposition (0,1), so 3 gates
        assert len(cmds) == 3

        # All on wires 0 and 1
        for cmd in cmds:
            qubits = [q.index[0] for q in cmd.qubits]
            assert set(qubits) == {0, 1}

    def test_exp_twistplus_compiles(self):
        """exp(iθ · TwistPlus) compiles correctly (one-hot encoding)."""
        body = TwistPlus(Q(), Q())
        exp = ExpInvolution(theta=0.5, body=body)

        result = compile(exp)
        cmds = list(result.circuit.get_commands())

        # TwistPlus(Q,Q) with one-hot swaps tags and data:
        # Layout: [t1, t2, A, B] -> [t2, t1, B, A]
        # That's transpositions (0,1) and (2,3), so 6 gates
        assert len(cmds) == 6

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

    def test_exp_involution_compile_goi(self):
        """ExpInvolution compiles correctly via compile_goi."""
        body = TwistTen(Q(), Q())
        exp = ExpInvolution(theta=0.5, body=body)

        result = compile_goi(exp)
        assert isinstance(result, CompiledGOI)

        cmds = list(result.circuit.get_commands())
        assert len(cmds) == 3

    def test_exp_involution_with_non_involution_fails(self):
        """ExpInvolution with non-involutive body fails at compile time."""
        # TwistTen(Q, Ten(Q,Q)) is NOT an involution (it's a 3-cycle [1,2,0])
        body = TwistTen(Q(), Ten(Q(), Q()))
        exp = ExpInvolution(theta=0.5, body=body)

        # This should fail during compilation because the body is not involutive
        with pytest.raises(TypeCheckError) as exc:
            compile(exp)
        assert "involutive" in str(exc.value).lower()

    def test_exp_involution_rejects_gates(self):
        """ExpInvolution body cannot contain gates."""
        # Body contains a gate (H)
        ty = Ten(Q(), Q())
        body = Seq(TwistTen(Q(), Q()), H(0, ty))
        exp = ExpInvolution(theta=0.5, body=body, ty_total=ty)

        with pytest.raises(TypeCheckError) as exc:
            compile(exp)
        assert "purely structural" in str(exc.value).lower()


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
        ty = Ten(Q(), Q())
        prog = Seq(
            H(0, ty),
            ExpInvolution(theta=0.5, body=TwistTen(Q(), Q()), ty_total=ty),
            CX(0, 1, ty),
        )

        result = compile(prog)
        cmds = list(result.circuit.get_commands())

        # 1 H + 3 ExpSwap gates + 1 CX = 5 gates
        assert len(cmds) == 5

        op_names = [c.op.type.name for c in cmds]
        assert op_names[0] == "H"
        assert op_names[-1] == "CX"


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
    """Test exp_i(π/4, X) ; Z ; exp_i(-π/4, X) = Y on qubit as I+I."""

    @staticmethod
    def extract_logical_submatrix(U):
        """Extract 2x2 logical qubit from 4x4 physical (one-hot encoding)."""
        import numpy as np
        # |0⟩_L = |10⟩_P (idx 2), |1⟩_L = |01⟩_P (idx 1)
        return np.array([[U[2,2], U[2,1]], [U[1,2], U[1,1]]])

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
        """TwistPlus(I,I) = Pauli-X on logical qubit."""
        import numpy as np
        from lang.types import Unit, Plus
        ty = Plus(Unit(), Unit())
        X = TwistPlus(Unit(), Unit())
        U_full = compile(X, materialize=True).circuit.get_unitary()
        U = self.extract_logical_submatrix(U_full)
        expected = np.array([[0,1],[1,0]], dtype=complex)
        match, _ = self.matrices_equal_up_to_phase(U, expected)
        assert match, "TwistPlus(I,I) should be Pauli-X"

    def test_z_gate_on_wire1_is_pauli_z(self):
        """Z[1] on I+I = Pauli-Z on logical qubit."""
        import numpy as np
        from lang.types import Unit, Plus
        from lang.terms import Z
        ty = Plus(Unit(), Unit())
        Z_gate = Z(1, ty)
        U_full = compile(Z_gate).circuit.get_unitary()
        U = self.extract_logical_submatrix(U_full)
        expected = np.array([[1,0],[0,-1]], dtype=complex)
        match, _ = self.matrices_equal_up_to_phase(U, expected)
        assert match, "Z[1] should be Pauli-Z"

    def test_conjugation_equals_y(self):
        """exp_i(π/4, X) ; Z ; exp_i(-π/4, X) = Y (verified by unitary)."""
        import numpy as np
        from lang.types import Unit, Plus
        from lang.terms import Z, S, Sdg
        ty = Plus(Unit(), Unit())
        X = TwistPlus(Unit(), Unit())

        exp_X_pos = ExpInvolution(theta=math.pi/4, body=X, ty_total=ty)
        exp_X_neg = ExpInvolution(theta=-math.pi/4, body=X, ty_total=ty)
        Z_gate = Z(1, ty)

        conjugation = Seq(exp_X_pos, Z_gate, exp_X_neg)
        U_conj_full = compile(conjugation, materialize=True).circuit.get_unitary()
        U_conj = self.extract_logical_submatrix(U_conj_full)

        # Expected Pauli-Y
        expected_Y = np.array([[0, -1j], [1j, 0]], dtype=complex)
        match, phase = self.matrices_equal_up_to_phase(U_conj, expected_Y)
        assert match, f"Conjugation should equal Y, phase={phase}"
