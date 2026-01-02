"""End-to-end tests for Phase 0 compilation.

Verifies:
- Structural programs compile to WirePerm only (no gates)
- materialize=False introduces no swaps
- Compilation is deterministic
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

    def test_twist_plus_compiles_to_perm_only(self):
        """TwistPlus should compile to permutation with no gates."""
        term = TwistPlus(Q(), Q())
        circuit, perm = compile_term(term, materialize=False)

        assert is_empty_circuit(circuit), f"Expected empty circuit, got: {circuit}"
        assert perm is not None
        assert perm.n == 2
        assert perm.new_to_old == [1, 0], "TwistPlus should swap wires"

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
        term_l = AssocPlusL(a, b, c)
        circuit, perm = compile_term(term_l, materialize=False)
        assert is_empty_circuit(circuit)
        assert perm is not None
        assert perm.n == 3

        # AssocPlusR: A + (B + C) -> (A + B) + C
        term_r = AssocPlusR(a, b, c)
        circuit, perm = compile_term(term_r, materialize=False)
        assert is_empty_circuit(circuit)
        assert perm is not None

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

        Note: Distributivity compilation is deferred (needs sum-aware layout).
        """
        import pytest
        a, b, c = Q(), Q(), Q()

        term_l = DistL(a, b, c)
        with pytest.raises(NotImplementedError, match="Distributivity"):
            compile_term(term_l, materialize=False)

        term_r = DistR(a, b, c)
        with pytest.raises(NotImplementedError, match="Distributivity"):
            compile_term(term_r, materialize=False)

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

    def test_sequential_structural_compiles_to_perm_only(self):
        """Sequence of structural ops should compile to perm only."""
        # TwistPlus ; TwistPlus = Id
        twist = TwistPlus(Q(), Q())
        term = Seq(twist, twist)
        circuit, perm = compile_term(term, materialize=False)

        assert is_empty_circuit(circuit)
        assert perm is not None
        assert perm.new_to_old == [0, 1], "twist;twist should be identity"

    def test_parallel_structural_compiles_to_perm_only(self):
        """Tensor of structural ops should compile to perm only."""
        twist1 = TwistPlus(Q(), Q())
        twist2 = TwistTensor(Q(), Q())
        term = TenTerm(twist1, twist2)
        circuit, perm = compile_term(term, materialize=False)

        assert is_empty_circuit(circuit)
        assert perm is not None
        assert perm.n == 4


class TestMaterializeFlag:
    """Test that materialize=False introduces no swaps."""

    def test_structural_no_materialize_no_swaps(self):
        """Structural programs with materialize=False should have no SWAP gates."""
        term = TwistPlus(Q(), Q())
        circuit, perm = compile_term(term, materialize=False)

        cmds = circuit_to_commands(circuit)
        assert 'SWAP' not in cmds.upper()

    def test_composed_structural_no_swaps(self):
        """Composed structural ops with materialize=False should have no SWAPs."""
        a, b, c = Q(), Q(), Q()
        term = Seq(
            AssocPlusL(a, b, c),
            TenTerm(TwistPlus(a, b), Id(c))
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
        term = Seq(
            AssocPlusL(a, b, c),
            Seq(TwistPlus(Plus(a, b), c), AssocPlusR(a, b, c))
        )

        _, perm1 = compile_term(term, materialize=False)
        _, perm2 = compile_term(term, materialize=False)

        assert perm_serialize(perm1) == perm_serialize(perm2)


if __name__ == '__main__':
    import pytest
    pytest.main([__file__, '-v'])
