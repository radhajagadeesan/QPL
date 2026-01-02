"""End-to-end tests for Phase 0 compilation.

Verifies:
- Structural programs compile to WirePerm (with tag flips for sum types)
- materialize=False introduces no swaps
- Compilation is deterministic

Note: With the tagged layout model:
- Sum types A + B have width = 1 + width(A) + width(B) (includes tag qubit)
- TwistPlus emits an X gate for the tag flip
- DistL/DistR now compile successfully
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

    def test_twist_plus_compiles_with_tag_flip(self):
        """TwistPlus should compile to permutation + X gate for tag flip."""
        term = TwistPlus(Q(), Q())
        circuit, perm = compile_term(term, materialize=False)

        # Tagged layout: Q + Q has width 3 (1 tag + 1 + 1)
        assert perm is not None
        assert perm.n == 3
        # Tag stays at 0, data wires swap: [0, 2, 1]
        assert perm.new_to_old == [0, 2, 1], "TwistPlus should swap data wires"
        # Should emit exactly 1 X gate for tag flip
        assert circuit.n_gates == 1, f"Expected 1 gate (X for tag flip), got: {circuit.n_gates}"

    def test_twist_tensor_compiles_to_perm_only(self):
        """TwistTensor should compile to permutation with no gates."""
        term = TwistTensor(Q(), Q())
        circuit, perm = compile_term(term, materialize=False)

        assert is_empty_circuit(circuit)
        assert perm is not None
        assert perm.n == 2
        assert perm.new_to_old == [1, 0]

    def test_assoc_plus_compiles_to_perm_only(self):
        """AssocPlusL/R should compile to permutation with no gates."""
        a, b, c = Q(), Q(), Q()

        # AssocPlusL: (A + B) + C -> A + (B + C)
        # Tagged layout: (Q + Q) + Q has width 5 (2 tags + 3 data)
        term_l = AssocPlusL(a, b, c)
        circuit, perm = compile_term(term_l, materialize=False)
        assert is_empty_circuit(circuit)
        assert perm is not None
        assert perm.n == 5, f"Expected width 5, got {perm.n}"

        # AssocPlusR: A + (B + C) -> (A + B) + C
        term_r = AssocPlusR(a, b, c)
        circuit, perm = compile_term(term_r, materialize=False)
        assert is_empty_circuit(circuit)
        assert perm is not None
        assert perm.n == 5

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

        With tagged layout model:
        - DistL is identity on wires
        - DistR moves tag to front
        """
        a, b, c = Q(), Q(), Q()

        # DistL: (A + B) ⊗ C -> (A ⊗ C) + (B ⊗ C)
        # Width: 1 + 1 + 1 + 1 = 4 (tag + Q + Q + Q)
        term_l = DistL(a, b, c)
        circuit, perm = compile_term(term_l, materialize=False)
        assert is_empty_circuit(circuit), "DistL should emit no gates"
        assert perm is not None
        assert perm.n == 4
        assert perm.new_to_old == [0, 1, 2, 3], "DistL is identity on wires"

        # DistR: A ⊗ (B + C) -> (A ⊗ B) + (A ⊗ C)
        term_r = DistR(a, b, c)
        circuit, perm = compile_term(term_r, materialize=False)
        assert is_empty_circuit(circuit), "DistR should emit no gates"
        assert perm is not None
        assert perm.n == 4
        assert perm.new_to_old[0] == 1, "DistR moves tag from position 1 to front"

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
        """Sequence of structural ops should compile correctly."""
        # TwistPlus ; TwistPlus = Id (both perm and tag flips cancel)
        twist = TwistPlus(Q(), Q())
        term = Seq(twist, twist)
        circuit, perm = compile_term(term, materialize=False)

        assert perm is not None
        # Perm should be identity: [0, 1, 2] for 3-wire sum type
        assert perm.new_to_old == [0, 1, 2], "twist;twist should be identity perm"
        # Two X gates cancel (X;X = I), but may still be emitted
        # The key invariant is the perm is identity

    def test_parallel_structural_compiles_correctly(self):
        """Tensor of structural ops should compile correctly."""
        # TwistPlus has width 3 (tag + 2 data), TwistTensor has width 2
        twist1 = TwistPlus(Q(), Q())
        twist2 = TwistTensor(Q(), Q())
        term = TenTerm(twist1, twist2)
        circuit, perm = compile_term(term, materialize=False)

        assert perm is not None
        # Total width: 3 + 2 = 5
        assert perm.n == 5, f"Expected width 5, got {perm.n}"
        # TwistPlus emits 1 X gate for tag flip
        assert circuit.n_gates == 1, "Should emit 1 X gate from TwistPlus"


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
