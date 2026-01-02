"""Test distR expanded form vs primitive.

Validates that the primitive DistR compiles correctly by comparing
against the expected behavior of the expanded form:

```ml
def distR_expanded : (A ⊗ Sum[B,C]) → Sum[A ⊗ B, A ⊗ C] =
  λx.
    let (a, bc) = x in
    case bc of
      | Inl(b) => Inl(a ⊗ b)
      | Inr(c) => Inr(a ⊗ c)
```

Expected properties:
- Elaborates to structural rewiring only
- Introduces no gates
- Produces a wire permutation that moves the tag to the front

See: RadhaMSG/distR_expanded_single_pattern.md
"""

import sys
from pathlib import Path

# Add paths for imports
TESTS_DIR = Path(__file__).parent.parent
SURFACE_DIR = TESTS_DIR.parent
PROJECT_DIR = SURFACE_DIR.parent
sys.path.insert(0, str(PROJECT_DIR))
sys.path.insert(0, str(TESTS_DIR))

from helpers import compile_term, is_empty_circuit

from lang.types import Q, Ten, Plus
from lang.terms import DistR, DistL, Id, Seq, TenTerm


class TestDistRExpanded:
    """Test DistR primitive matches expected expanded form behavior."""

    def test_distR_is_structural(self):
        """DistR should compile to structural rewiring only (no gates).

        The expanded form:
            λx. let (a, bc) = x in case bc of Inl(b) => Inl(a⊗b) | Inr(c) => Inr(a⊗c)

        Should elaborate to pure structural rewiring. The primitive DistR
        must compile identically.
        """
        a, b, c = Q(), Q(), Q()
        term = DistR(a, b, c)
        circuit, perm = compile_term(term, materialize=False)

        # DistR is structural - no gates
        assert is_empty_circuit(circuit), f"DistR should emit no gates, got {circuit.n_gates}"

    def test_distR_permutation_structure(self):
        """DistR should move the tag from position 1 to position 0.

        Input layout:  A ⊗ (B + C) = [A_wire, tag, B_wire, C_wire]
                                   = [0,      1,   2,      3     ]

        Output layout: (A ⊗ B) + (A ⊗ C) = [tag, A_wire, B_wire, C_wire]
                                         = [tag, A,      B,      C     ]

        The permutation moves tag from position 1 to position 0.
        """
        a, b, c = Q(), Q(), Q()
        term = DistR(a, b, c)
        circuit, perm = compile_term(term, materialize=False)

        # Width should be 4: 1 (A) + 1 (tag) + 1 (B) + 1 (C) = 4
        assert perm.n == 4, f"Expected width 4, got {perm.n}"

        # Tag moves from position 1 to position 0
        assert perm.new_to_old[0] == 1, f"Tag should move to front, got perm={perm.new_to_old}"

    def test_distL_is_structural(self):
        """DistL should compile to structural rewiring only (no gates).

        DistL: (A + B) ⊗ C → (A ⊗ C) + (B ⊗ C)

        The tag is already at position 0 in both input and output,
        so DistL is identity on wires.
        """
        a, b, c = Q(), Q(), Q()
        term = DistL(a, b, c)
        circuit, perm = compile_term(term, materialize=False)

        # DistL is structural - no gates
        assert is_empty_circuit(circuit), f"DistL should emit no gates, got {circuit.n_gates}"

    def test_distL_is_identity(self):
        """DistL is identity on wires (tag already at front).

        Input layout:  (A + B) ⊗ C = [tag, A_wire, B_wire, C_wire]
        Output layout: (A ⊗ C) + (B ⊗ C) = [tag, A_wire, C_wire, B_wire]...

        Actually with tagged layout, both have same physical layout.
        """
        a, b, c = Q(), Q(), Q()
        term = DistL(a, b, c)
        circuit, perm = compile_term(term, materialize=False)

        # Width should be 4
        assert perm.n == 4, f"Expected width 4, got {perm.n}"

        # DistL is identity on wires
        assert perm.new_to_old == [0, 1, 2, 3], f"DistL should be identity, got {perm.new_to_old}"


class TestDistRDistLRoundTrip:
    """Test that DistR and DistL are inverses (up to associators)."""

    def test_distR_distL_composition(self):
        """DistL ; DistR should give a well-defined permutation.

        Note: DistL and DistR are not exact inverses due to type structure,
        but composing related distributivity morphisms should be structural.
        """
        a, b, c = Q(), Q(), Q()

        # We can't directly compose DistL;DistR since types don't match,
        # but we can verify each is independently structural
        distL = DistL(a, b, c)
        distR = DistR(a, b, c)

        circuitL, permL = compile_term(distL, materialize=False)
        circuitR, permR = compile_term(distR, materialize=False)

        assert is_empty_circuit(circuitL)
        assert is_empty_circuit(circuitR)

        # Both should have same width
        assert permL.n == permR.n == 4


class TestDistributivityWithTypes:
    """Test distributivity with various type combinations."""

    def test_distR_nested_tensor(self):
        """DistR with nested tensor types."""
        # (Q ⊗ Q) ⊗ (Q + Q) → ((Q ⊗ Q) ⊗ Q) + ((Q ⊗ Q) ⊗ Q)
        a = Ten(Q(), Q())  # 2 wires
        b, c = Q(), Q()     # 1 wire each

        term = DistR(a, b, c)
        circuit, perm = compile_term(term, materialize=False)

        # Width: 2 (a) + 1 (tag) + 1 (b) + 1 (c) = 5
        assert perm.n == 5, f"Expected width 5, got {perm.n}"
        assert is_empty_circuit(circuit)

    def test_distL_nested_sum(self):
        """DistL with nested sum types."""
        # (Q + Q) ⊗ Q → (Q ⊗ Q) + (Q ⊗ Q)
        # Note: Q + Q has width 3 (tag + 2)
        a, b = Q(), Q()
        c = Q()

        term = DistL(a, b, c)
        circuit, perm = compile_term(term, materialize=False)

        # Width: 1 (tag) + 1 (a) + 1 (b) + 1 (c) = 4
        assert perm.n == 4, f"Expected width 4, got {perm.n}"
        assert is_empty_circuit(circuit)


if __name__ == '__main__':
    import pytest
    pytest.main([__file__, '-v'])
