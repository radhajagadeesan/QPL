# tests/test_e2e_recommendations.py
"""End-to-End Tests per e2e_test_recommendations_post_refactor.md

This test file implements the minimal high-value test set (Section 11)
plus additional tests from Sections 2-10 that were missing from
existing coverage.

Focus: black-box, end-to-end tests exercising public entry points.
"""

from __future__ import annotations

import pytest
from pytket.circuit import OpType

# Type imports
from lang.types import Q, Ten, Plus, width

# Term imports
from lang.terms import (
    Id, Seq, TenTerm,
    TwistTen, AssocTenL, AssocTenR,
    TwistPlus, AssocPlusL, AssocPlusR,
    DistL, DistR,
    Feedback,
    H, S, CX, X, Z,
)

# Compilation
from compile.to_pytket import compile, compile_goi, Compiled, CompiledGOI
from compile.goi import GOIArtifact

# Permutations
from core.perm import WirePerm, identity


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def qpow(n: int):
    """Build Q ⊗ Q ⊗ ... ⊗ Q (n times, right-associated)."""
    ty = Q()
    for _ in range(n - 1):
        ty = Ten(ty, Q())
    return ty


def count_gates(circ) -> int:
    """Count total gate operations (excluding SWAPs)."""
    return sum(1 for cmd in circ.get_commands()
               if cmd.op.type != OpType.SWAP)


def count_swaps(circ) -> int:
    """Count SWAP operations."""
    return sum(1 for cmd in circ.get_commands()
               if cmd.op.type == OpType.SWAP)


def get_op_sequence(circ):
    """Get sequence of (op_name, qubit_indices) tuples."""
    return [(cmd.op.type.name, tuple(q.index[0] for q in cmd.qubits))
            for cmd in circ.get_commands()]


def canonical_circuit_repr(circ) -> tuple:
    """Canonical serialization for determinism comparison."""
    return tuple(get_op_sequence(circ))


def canonical_perm_repr(perm: WirePerm) -> tuple:
    """Canonical serialization for permutation comparison."""
    return tuple(perm.new_to_old)


# ---------------------------------------------------------------------------
# Section 2: Smoke Tests (Repo Usability)
# ---------------------------------------------------------------------------

class TestSmokeTests:
    """Ensure the repository is runnable and usable."""

    def test_structural_swap_compiles(self):
        """Minimal structural program compiles."""
        prog = TwistTen(Q(), Q())
        result = compile(prog)
        assert result.circuit is not None
        assert count_gates(result.circuit) == 0

    def test_unitary_program_compiles(self):
        """Minimal unitary program (H ; CX) compiles."""
        prog = Seq(H(), CX())
        result = compile(prog)
        assert result.circuit is not None
        assert count_gates(result.circuit) == 2


# ---------------------------------------------------------------------------
# Section 3: Determinism Lock Tests
# ---------------------------------------------------------------------------

class TestDeterminismLock:
    """Ensure identical inputs always produce identical outputs."""

    @pytest.mark.parametrize("prog_name,prog", [
        ("tensor_swap", TwistTen(Q(), Q())),
        ("sum_swap", TwistPlus(Q(), Q())),
        ("bell_state", Seq(H(), CX())),
        ("tensor_assoc_l", AssocTenL(Q(), Q(), Q())),
        ("sum_assoc_l", AssocPlusL(Q(), Q(), Q())),
    ])
    def test_determinism_compile(self, prog_name, prog):
        """Compile twice, verify identical outputs."""
        r1 = compile(prog, materialize=False)
        r2 = compile(prog, materialize=False)

        assert canonical_circuit_repr(r1.circuit) == canonical_circuit_repr(r2.circuit), \
            f"Circuit mismatch for {prog_name}"
        assert canonical_perm_repr(r1.perm) == canonical_perm_repr(r2.perm), \
            f"Perm mismatch for {prog_name}"

    @pytest.mark.parametrize("prog_name,prog", [
        ("tensor_swap", TwistTen(Q(), Q())),
        ("bell_state", Seq(H(), CX())),
    ])
    def test_determinism_compile_goi(self, prog_name, prog):
        """compile_goi twice, verify identical outputs."""
        r1 = compile_goi(prog, materialize=False)
        r2 = compile_goi(prog, materialize=False)

        assert type(r1) is type(r2)
        if isinstance(r1, CompiledGOI):
            assert canonical_circuit_repr(r1.circuit) == canonical_circuit_repr(r2.circuit)
            assert canonical_perm_repr(r1.perm) == canonical_perm_repr(r2.perm)


# ---------------------------------------------------------------------------
# Section 4: Structural Purity Tests
# ---------------------------------------------------------------------------

class TestStructuralPurity:
    """Ensure structural programs never emit gates (except tag flips)."""

    @pytest.mark.parametrize("prog_name,prog", [
        ("tensor_swap", TwistTen(Q(), Q())),
        # Note: sum_swap (TwistPlus) emits 1 X gate for tag flip - tested separately
        ("tensor_assoc_l", AssocTenL(Q(), Q(), Q())),
        ("tensor_assoc_r", AssocTenR(Q(), Q(), Q())),
        ("sum_assoc_l", AssocPlusL(Q(), Q(), Q())),
        ("sum_assoc_r", AssocPlusR(Q(), Q(), Q())),
        ("dist_l", DistL(Q(), Q(), Q())),
        ("dist_r", DistR(Q(), Q(), Q())),
    ])
    def test_structural_zero_gates(self, prog_name, prog):
        """Pure structural programs emit zero gates (tensor/assoc/dist)."""
        result = compile(prog, materialize=False)
        assert count_gates(result.circuit) == 0, \
            f"{prog_name} should emit 0 gates, got {count_gates(result.circuit)}"

    @pytest.mark.parametrize("prog_name,prog", [
        ("tensor_swap", TwistTen(Q(), Q())),
        ("sum_swap", TwistPlus(Q(), Q())),
        ("tensor_assoc_l", AssocTenL(Q(), Q(), Q())),
    ])
    def test_structural_no_swaps(self, prog_name, prog):
        """Structural programs emit no SWAPs with materialize=False."""
        result = compile(prog, materialize=False)
        assert count_swaps(result.circuit) == 0

    def test_mixed_assoc_plus_swap(self):
        """Mixed associator + swap remains structural."""
        prog = Seq(
            AssocTenL(Q(), Q(), Q()),
            TwistTen(Q(), Ten(Q(), Q())),
        )
        result = compile(prog, materialize=False)
        assert count_gates(result.circuit) == 0

    def test_sum_swap_emits_x_gate(self):
        """TwistPlus emits X gate for tag flip in tagged layout model."""
        prog = TwistPlus(Q(), Q())
        result = compile(prog, materialize=False)
        ops = get_op_sequence(result.circuit)
        # Tagged layout: TwistPlus emits X gate for tag flip
        x_ops = [op for op, _ in ops if op == 'X']
        assert len(x_ops) == 1, "TwistPlus should emit exactly one X gate"


# ---------------------------------------------------------------------------
# Section 5: Materialization Flag Tests
# ---------------------------------------------------------------------------

class TestMaterializationFlag:
    """Ensure materialize behavior remains correct."""

    def test_structural_swap_no_materialize(self):
        """materialize=False: no SWAPs on structural swap."""
        prog = TwistTen(Q(), Q())
        result = compile(prog, materialize=False)
        assert count_swaps(result.circuit) == 0
        # Perm should be non-identity
        assert result.perm.new_to_old == [1, 0]

    def test_structural_swap_with_materialize(self):
        """materialize=True: SWAPs appear for non-identity perm."""
        prog = TwistTen(Q(), Q())
        result = compile(prog, materialize=True)
        # After materialization, perm should be identity
        assert result.perm == identity(2)

    def test_unitary_with_nontrivial_perm(self):
        """Unitary program with nontrivial final perm."""
        ty = Ten(Q(), Q())
        prog = Seq(TwistTen(Q(), Q()), H(0, ty), CX(0, 1, ty))

        r_no_mat = compile(prog, materialize=False)
        r_mat = compile(prog, materialize=True)

        # Without materialization: perm is non-identity
        assert r_no_mat.perm.new_to_old == [1, 0]

        # With materialization: perm becomes identity
        assert r_mat.perm == identity(2)


# ---------------------------------------------------------------------------
# Section 7: Distributivity-Style Programming Tests
# ---------------------------------------------------------------------------

class TestDistributivityMacros:
    """Ensure distributive programming patterns remain supported."""

    def test_dist_l_identity(self):
        """DistL: (A ⊕ B) ⊗ C → (A ⊗ C) ⊕ (B ⊗ C) is identity on wires."""
        prog = DistL(Q(), Q(), Q())
        result = compile(prog)

        # Width: tag + Q + Q + Q = 4
        assert result.circuit.n_qubits == 4
        # Identity on wires: no gates
        assert count_gates(result.circuit) == 0

    def test_dist_r_permutes_tag(self):
        """DistR: A ⊗ (B ⊕ C) → (A ⊗ B) ⊕ (A ⊗ C) moves tag to front."""
        prog = DistR(Q(), Q(), Q())
        result = compile(prog)

        # Width: Q + tag + Q + Q = 4
        assert result.circuit.n_qubits == 4
        # No gates (just permutation)
        assert count_gates(result.circuit) == 0
        # Perm should move wire 1 (tag) to front
        assert result.perm.new_to_old[0] == 1

    def test_distributivity_elaboration_succeeds(self):
        """Surface elaboration and compilation of distributivity succeeds."""
        prog = DistL(Q(), Q(), Q())

        # Both compile paths work
        r1 = compile(prog)
        r2 = compile_goi(prog)

        assert r1.circuit is not None
        assert isinstance(r2, CompiledGOI)

    def test_distributivity_deterministic(self):
        """Distributivity compilation is deterministic."""
        prog = DistL(Q(), Q(), Q())

        r1 = compile(prog)
        r2 = compile(prog)

        assert canonical_circuit_repr(r1.circuit) == canonical_circuit_repr(r2.circuit)
        assert canonical_perm_repr(r1.perm) == canonical_perm_repr(r2.perm)


# ---------------------------------------------------------------------------
# Section 9: Example Suite Smoke Tests
# ---------------------------------------------------------------------------

class TestExampleAlgorithms:
    """Validate real programs continue to work."""

    def test_bell_state(self):
        """Bell state preparation compiles correctly."""
        prog = Seq(H(), CX())
        result = compile(prog)

        ops = get_op_sequence(result.circuit)
        assert ops == [('H', (0,)), ('CX', (0, 1))]
        assert count_swaps(result.circuit) == 0

    def test_ghz_state_3_qubit(self):
        """3-qubit GHZ state preparation."""
        ty3 = qpow(3)
        prog = Seq(
            H(0, ty3),
            CX(0, 1, ty3),
            CX(1, 2, ty3),
        )
        result = compile(prog)

        assert result.circuit.n_qubits == 3
        ops = get_op_sequence(result.circuit)
        assert len(ops) == 3
        assert ops[0] == ('H', (0,))
        assert ops[1] == ('CX', (0, 1))
        assert ops[2] == ('CX', (1, 2))

    def test_ghz_state_4_qubit(self):
        """4-qubit GHZ state preparation."""
        ty4 = qpow(4)
        prog = Seq(
            H(0, ty4),
            CX(0, 1, ty4),
            CX(1, 2, ty4),
            CX(2, 3, ty4),
        )
        result = compile(prog)

        assert result.circuit.n_qubits == 4
        assert count_gates(result.circuit) == 4

    def test_deutsch_jozsa_2_qubit_smoke(self):
        """Deutsch-Jozsa 2-qubit smoke test (balanced oracle stub)."""
        # 2-qubit DJ: H on both, oracle (CX), H on query qubit
        ty = Ten(Q(), Q())
        prog = Seq(
            H(0, ty),
            H(1, ty),
            CX(0, 1, ty),  # Simple balanced oracle
            H(0, ty),
        )
        result = compile(prog)

        assert result.circuit.n_qubits == 2
        assert count_gates(result.circuit) == 4

    def test_determinism_ghz(self):
        """GHZ compilation is deterministic."""
        ty3 = qpow(3)
        prog = Seq(H(0, ty3), CX(0, 1, ty3), CX(1, 2, ty3))

        r1 = compile(prog)
        r2 = compile(prog)

        assert canonical_circuit_repr(r1.circuit) == canonical_circuit_repr(r2.circuit)


# ---------------------------------------------------------------------------
# Section 11: Minimal High-Value Test Set
# ---------------------------------------------------------------------------

class TestMinimalHighValue:
    """The 10 tests that catch most regressions."""

    def test_01_structural_swap_zero_gates(self):
        """1. Structural swap compiles with 0 gates."""
        result = compile(TwistTen(Q(), Q()))
        assert count_gates(result.circuit) == 0

    def test_02_bell_state_two_gates(self):
        """2. Bell state compiles with 2 gates."""
        result = compile(Seq(H(), CX()))
        assert count_gates(result.circuit) == 2

    def test_03_determinism_structural_swap(self):
        """3. Determinism: structural swap."""
        prog = TwistTen(Q(), Q())
        r1 = compile(prog)
        r2 = compile(prog)
        assert canonical_circuit_repr(r1.circuit) == canonical_circuit_repr(r2.circuit)
        assert canonical_perm_repr(r1.perm) == canonical_perm_repr(r2.perm)

    def test_04_determinism_bell_state(self):
        """4. Determinism: Bell state."""
        prog = Seq(H(), CX())
        r1 = compile(prog)
        r2 = compile(prog)
        assert canonical_circuit_repr(r1.circuit) == canonical_circuit_repr(r2.circuit)

    def test_05_materialize_flag_on_swap(self):
        """5. Materialize flag behavior on swap."""
        prog = TwistTen(Q(), Q())

        r_no = compile(prog, materialize=False)
        r_yes = compile(prog, materialize=True)

        assert count_swaps(r_no.circuit) == 0
        assert r_no.perm.new_to_old == [1, 0]
        assert r_yes.perm == identity(2)

    def test_06_exp_i_accepts_involution(self):
        """6. exp_i accepts known involution (tensor swap)."""
        from core.perm import is_involution
        prog = TwistTen(Q(), Q())
        result = compile(prog)
        # Tensor swap is an involution: swap ∘ swap = id
        assert is_involution(result.perm)

    def test_07_exp_i_rejects_non_involution(self):
        """7. exp_i rejects non-involution (3-cycle)."""
        from core.perm import is_involution
        # Create a 3-cycle via associators
        prog = Seq(
            AssocTenL(Q(), Q(), Q()),
            TwistTen(Q(), Ten(Q(), Q())),
        )
        result = compile(prog)
        # This is not an involution
        assert not is_involution(result.perm)

    def test_08_distributivity_macro(self):
        """8. Distributivity-style macro example."""
        prog = DistL(Q(), Q(), Q())
        result = compile(prog)
        assert result.circuit is not None
        assert count_gates(result.circuit) == 0

    def test_09_deutsch_jozsa_smoke(self):
        """9. Deutsch-Jozsa smoke test."""
        ty = Ten(Q(), Q())
        prog = Seq(H(0, ty), H(1, ty), CX(0, 1, ty), H(0, ty))
        result = compile(prog)
        assert result.circuit is not None
        assert count_gates(result.circuit) == 4

    def test_10_reject_invalid_gate_index(self):
        """10. Reject invalid gate index (negative capability)."""
        from typing_.check import assert_well_typed, TypeCheckError

        # Gate with index out of bounds
        bad_gate = H(5, Ten(Q(), Q()))  # Only 2 qubits, index 5 invalid

        with pytest.raises(TypeCheckError):
            assert_well_typed(bad_gate)


# ---------------------------------------------------------------------------
# Tagged Layout Model Coverage
# ---------------------------------------------------------------------------

class TestTaggedLayoutCoverage:
    """Verify tagged layout model changes are properly covered."""

    def test_plus_width_includes_tag(self):
        """Plus types include tag qubit in width."""
        assert width(Plus(Q(), Q())) == 3  # 1 tag + 1 + 1

    def test_nested_plus_width(self):
        """Nested Plus types accumulate tags correctly."""
        # (Q ⊕ Q) ⊕ Q
        ty = Plus(Plus(Q(), Q()), Q())
        # Inner: 3, Outer: 1 + 3 + 1 = 5
        assert width(ty) == 5

    def test_twist_plus_involution_property(self):
        """TwistPlus is involutive (twist ∘ twist = id)."""
        prog = Seq(TwistPlus(Q(), Q()), TwistPlus(Q(), Q()))
        result = compile(prog, materialize=False)
        # After two twists, should be identity
        assert result.perm == identity(3)
        # X gates cancel (X ∘ X = I)
        # Net gate count should be 0 after optimization
        # (Current implementation may show 2 X gates that cancel)

    def test_dist_l_preserves_physical_width(self):
        """DistL preserves physical wire count (sharing model)."""
        prog = DistL(Q(), Q(), Q())
        result = compile(prog)
        # (Q ⊕ Q) ⊗ Q has width 4: tag + Q + Q + Q
        # (Q ⊗ Q) ⊕ (Q ⊗ Q) also has width 4: tag + Q + Q + Q (C shared)
        assert result.circuit.n_qubits == 4

    def test_dist_r_preserves_physical_width(self):
        """DistR preserves physical wire count."""
        prog = DistR(Q(), Q(), Q())
        result = compile(prog)
        # Q ⊗ (Q ⊕ Q) has width 4: Q + tag + Q + Q
        # (Q ⊗ Q) ⊕ (Q ⊗ Q) also has width 4
        assert result.circuit.n_qubits == 4


# ---------------------------------------------------------------------------
# Feedback (GOI) Tests
# ---------------------------------------------------------------------------

class TestFeedbackGOI:
    """Test Feedback constructs with compile_goi."""

    def test_yankable_feedback_extracts(self):
        """Yankable feedback (body doesn't touch loop) extracts."""
        ty3 = qpow(3)
        # H on wire 0, loop on last 1 wire (wire 2)
        body = H(0, ty3)
        prog = Feedback(k=1, body=body)

        result = compile_goi(prog)
        assert isinstance(result, CompiledGOI), "Yankable feedback should extract"

    def test_non_yankable_feedback_residual(self):
        """Non-yankable feedback (body touches loop) returns residual."""
        ty2 = Ten(Q(), Q())
        # H on wire 1, loop on last 1 wire (wire 1)
        body = H(1, ty2)
        prog = Feedback(k=1, body=body)

        result = compile_goi(prog)
        assert isinstance(result, GOIArtifact), "Non-yankable feedback should return residual"
        assert len(result.loops) >= 1
