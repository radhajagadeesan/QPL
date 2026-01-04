"""End-to-end tests for Phase 0 compilation.

Verifies:
- Structural programs compile to WirePerm (pure permutation for all structural ops)
- materialize=False introduces no swaps
- Compilation is deterministic

Note: With the one-hot leaf-tag encoding:
- Sum types A + B have width = 2 + width(A) + width(B) (2 one-hot tags + payloads)
- Plus(Q, Q) = 2 tags + 2 data = 4 wires
- Nested sums flatten: Plus(Plus(Q,Q), Q) = 3 tags + 3 data = 6 wires
- TwistPlus is now a PURE PERMUTATION (no X gates) - swaps tags AND data
- DistL/DistR compile successfully as pure permutations
"""

import sys
from pathlib import Path

# Add paths for imports
TESTS_DIR = Path(__file__).parent.parent
SURFACE_DIR = TESTS_DIR.parent
PROJECT_DIR = SURFACE_DIR.parent
sys.path.insert(0, str(PROJECT_DIR))
sys.path.insert(0, str(TESTS_DIR))

from helpers import (
    compile_term, perm_serialize, circuit_to_commands,
    is_empty_circuit, compare_golden
)

from lang.types import Q, Ten, Plus
from lang.terms import (
    Id, Seq, TenTerm, TwistTen, TwistPlus,
    AssocTenL, AssocTenR, AssocPlusL, AssocPlusR,
    DistL, DistR
)

# Aliases for readability
TwistTensor = TwistTen
AssocTensorL = AssocTenL
AssocTensorR = AssocTenR


class TestStructuralCompilation:
    """Test that structural programs compile to WirePerm only."""

    def test_twist_plus_compiles_as_pure_perm(self):
        """TwistPlus should compile to pure permutation (no gates) with one-hot encoding."""
        term = TwistPlus(Q(), Q())
        circuit, perm = compile_term(term, materialize=False)

        # One-hot layout: Q + Q has width 4 (2 tags + 2 data)
        assert perm is not None
        assert perm.n == 4
        # With one-hot: swaps tags AND data: [1, 0, 3, 2]
        # Layout: [t1, t2, A, B] -> [t2, t1, B, A]
        assert perm.new_to_old == [1, 0, 3, 2], "TwistPlus should swap both tags and data"
        # No gates - pure permutation with one-hot encoding
        assert circuit.n_gates == 0, f"Expected 0 gates (pure perm), got: {circuit.n_gates}"

    def test_twist_tensor_compiles_to_perm_only(self):
        """TwistTensor should compile to permutation with no gates."""
        term = TwistTensor(Q(), Q())
        circuit, perm = compile_term(term, materialize=False)

        assert is_empty_circuit(circuit)
        assert perm is not None
        assert perm.n == 2
        assert perm.new_to_old == [1, 0]

    def test_assoc_plus_compiles_to_perm_only(self):
        """AssocPlusL/R should compile to permutation with no gates.

        With one-hot encoding:
        - Nested Plus flattens to 3 summands: 3 tags + 3 data = 6 wires
        - AssocPlus is pure permutation (reorders tags and data blocks)
        """
        a, b, c = Q(), Q(), Q()

        # AssocPlusL: (A + B) + C -> A + (B + C)
        # One-hot layout: 3 tags + 3 data = 6 wires
        term_l = AssocPlusL(a, b, c)
        circuit, perm = compile_term(term_l, materialize=False)
        assert is_empty_circuit(circuit)
        assert perm is not None
        assert perm.n == 6, f"Expected width 6, got {perm.n}"

        # AssocPlusR: A + (B + C) -> (A + B) + C
        term_r = AssocPlusR(a, b, c)
        circuit, perm = compile_term(term_r, materialize=False)
        assert is_empty_circuit(circuit)
        assert perm is not None
        assert perm.n == 6

    def test_assoc_tensor_compiles_to_perm_only(self):
        """AssocTensorL/R should compile to permutation with no gates."""
        a, b, c = Q(), Q(), Q()

        term_l = AssocTensorL(a, b, c)
        circuit, perm = compile_term(term_l, materialize=False)
        assert is_empty_circuit(circuit)
        assert perm is not None
        assert perm.n == 3

        term_r = AssocTensorR(a, b, c)
        circuit, perm = compile_term(term_r, materialize=False)
        assert is_empty_circuit(circuit)

    def test_dist_compiles_to_perm_only(self):
        """DistL/DistR should compile to permutation with no gates.

        With one-hot encoding:
        - (Q + Q) ⊗ Q has width 5 (2 tags + 2 data + 1 Q)
        - DistL is identity on wires
        - DistR moves tags to front
        """
        a, b, c = Q(), Q(), Q()

        # DistL: (A + B) ⊗ C -> (A ⊗ C) + (B ⊗ C)
        # Input: (Q + Q) ⊗ Q = 2 tags + 2 data + 1 Q = 5 wires
        term_l = DistL(a, b, c)
        circuit, perm = compile_term(term_l, materialize=False)
        assert is_empty_circuit(circuit), "DistL should emit no gates"
        assert perm is not None
        assert perm.n == 5, f"Expected width 5, got {perm.n}"
        assert perm.new_to_old == [0, 1, 2, 3, 4], "DistL is identity on wires"

        # DistR: A ⊗ (B + C) -> (A ⊗ B) + (A ⊗ C)
        # Input: Q ⊗ (Q + Q) = 1 Q + 2 tags + 2 data = 5 wires
        term_r = DistR(a, b, c)
        circuit, perm = compile_term(term_r, materialize=False)
        assert is_empty_circuit(circuit), "DistR should emit no gates"
        assert perm is not None
        assert perm.n == 5, f"Expected width 5, got {perm.n}"
        # Tags move from positions 1,2 to front: [A=0, t1=1, t2=2, B=3, C=4] -> [t1, t2, A, B, C]
        assert perm.new_to_old[0] == 1, "DistR moves first tag to position 0"
        assert perm.new_to_old[1] == 2, "DistR moves second tag to position 1"

    def test_identity_compiles_to_routing_identity(self):
        """Id should compile to identity ROUTING permutation.

        GOI Note: In the GOI theoretical model, id_A compiles to the
        through-wire involution J_A on the doubled boundary. In our
        implementation, we use routing permutations (not doubled boundaries),
        so Id produces an identity routing [0, 1, ...].

        The key GOI property (involution) is tested separately in
        test_e2e_certification.py::TestInvolutionAcceptance::test_identity_is_involutive.
        """
        term = Id(Ten(Q(), Q()))
        circuit, perm = compile_term(term, materialize=False)

        assert is_empty_circuit(circuit)
        assert perm is not None
        assert perm.n == 2
        # Routing permutation is identity (no wire rearrangement)
        assert perm.new_to_old == [0, 1]
        # GOI invariant: id is always involutive
        composed = [perm.new_to_old[perm.new_to_old[i]] for i in range(perm.n)]
        assert composed == list(range(perm.n)), "Id must be involutive (p∘p=id)"

    def test_sequential_structural_compiles_correctly(self):
        """Sequence of structural ops should compile correctly.

        With one-hot encoding:
        - Plus(Q,Q) = 2 tags + 2 data = 4 wires
        - TwistPlus ; TwistPlus = Id (pure permutation, no gates)
        """
        twist = TwistPlus(Q(), Q())
        term = Seq(twist, twist)
        circuit, perm = compile_term(term, materialize=False)

        assert perm is not None
        # Perm should be identity: [0, 1, 2, 3] for 4-wire sum type with one-hot
        assert perm.new_to_old == [0, 1, 2, 3], "twist;twist should be identity perm"
        # With one-hot encoding, no X gates needed (pure permutation)
        assert circuit.n_gates == 0, "TwistPlus;TwistPlus should emit no gates"

    def test_parallel_structural_compiles_correctly(self):
        """Tensor of structural ops should compile correctly.

        With one-hot encoding:
        - TwistPlus(Q,Q) has width 4 (2 tags + 2 data)
        - TwistTensor(Q,Q) has width 2
        - Both are pure permutations (no gates)
        """
        twist1 = TwistPlus(Q(), Q())
        twist2 = TwistTensor(Q(), Q())
        term = TenTerm(twist1, twist2)
        circuit, perm = compile_term(term, materialize=False)

        assert perm is not None
        # Total width: 4 + 2 = 6
        assert perm.n == 6, f"Expected width 6, got {perm.n}"
        # With one-hot encoding, no X gates (pure permutation)
        assert circuit.n_gates == 0, "Should emit 0 gates (pure permutation)"


class TestMaterializeFlag:
    """Test that materialize=False introduces no swaps."""

    def test_structural_no_materialize_no_swaps(self):
        """Structural programs with materialize=False should have no SWAP gates."""
        term = TwistPlus(Q(), Q())
        circuit, perm = compile_term(term, materialize=False)

        cmds = circuit_to_commands(circuit)
        assert 'SWAP' not in cmds.upper()

    def test_tensor_structural_no_swaps(self):
        """Tensor structural ops with materialize=False should have no SWAPs."""
        # Use only tensor operations to avoid type mismatches
        a, b, c = Q(), Q(), Q()
        term = Seq(
            AssocTenL(a, b, c),
            TwistTen(a, Ten(b, c))
        )
        circuit, perm = compile_term(term, materialize=False)

        cmds = circuit_to_commands(circuit)
        assert 'SWAP' not in cmds.upper()


class TestDeterminism:
    """Test compilation determinism."""

    def test_deterministic_perm_serialization(self):
        """Same term should produce same perm serialization."""
        term = TwistPlus(Q(), Q())

        _, perm1 = compile_term(term, materialize=False)
        _, perm2 = compile_term(term, materialize=False)

        ser1 = perm_serialize(perm1)
        ser2 = perm_serialize(perm2)
        assert ser1 == ser2, "Permutation serialization should be deterministic"

    def test_deterministic_circuit(self):
        """Same term should produce same circuit."""
        term = TwistPlus(Q(), Q())

        circuit1, _ = compile_term(term, materialize=False)
        circuit2, _ = compile_term(term, materialize=False)

        cmds1 = circuit_to_commands(circuit1)
        cmds2 = circuit_to_commands(circuit2)
        assert cmds1 == cmds2, "Circuit should be deterministic"

    def test_deterministic_composed_term(self):
        """Composed terms should compile deterministically."""
        a, b, c = Q(), Q(), Q()
        # Use tensor operations for simpler type matching
        term = Seq(
            AssocTenL(a, b, c),
            Seq(TwistTen(Ten(a, b), c), AssocTenR(a, b, c))
        )

        _, perm1 = compile_term(term, materialize=False)
        _, perm2 = compile_term(term, materialize=False)

        assert perm_serialize(perm1) == perm_serialize(perm2)


if __name__ == '__main__':
    import pytest
    pytest.main([__file__, '-v'])
