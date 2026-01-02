# tests/test_22_distributivity.py
"""Distributivity tests: now supported with tagged layout model.

Tagged Layout Distributivity:
  DistL: (A ⊕ B) ⊗ C → (A ⊗ C) ⊕ (B ⊗ C)
    - Physical layout: [tag | A | B | C] (same for both types)
    - DistL is IDENTITY on wires

  DistR: A ⊗ (B ⊕ C) → (A ⊗ B) ⊕ (A ⊗ C)
    - Input layout:  [A | tag | B | C]
    - Output layout: [tag | A | B | C]
    - DistR moves tag from position width(A) to position 0
"""

from lang.types import Q, Ten
from lang.terms import DistL, DistR
from compile.to_pytket import compile
from core.perm import identity


def test_distL_is_identity():
    """DistL: (A ⊕ B) ⊗ C → (A ⊗ C) ⊕ (B ⊗ C) is identity on wires.

    For A = Q(), B = Q() ⊗ Q(), C = Q():
    - Domain: (Q ⊕ (Q⊗Q)) ⊗ Q
    - Width = (1 + 1 + 2) + 1 = 5 [tag | A | B0 | B1 | C]

    The physical layout is unchanged by distributivity - only the type changes.
    """
    a = Q()
    b = Ten(Q(), Q())
    c = Q()
    out = compile(DistL(a, b, c))

    # Width: 1 tag + 1 (a) + 2 (b) + 1 (c) = 5
    assert out.circuit.n_qubits == 5

    # No gates (pure permutation, which is identity)
    assert len(out.circuit.get_commands()) == 0

    # Permutation is identity
    assert out.perm.new_to_old == identity(5).new_to_old


def test_distR_moves_tag():
    """DistR: A ⊗ (B ⊕ C) → (A ⊗ B) ⊕ (A ⊗ C) moves tag to front.

    For A = Q(), B = Q(), C = Q() ⊗ Q():
    - Domain: Q ⊗ (Q ⊕ (Q⊗Q))
    - Width = 1 + (1 + 1 + 2) = 5 [A | tag | B | C0 | C1]
    - Codomain layout: [tag | A | B | C0 | C1]

    DistR permutes the tag from position 1 to position 0.
    """
    a = Q()
    b = Q()
    c = Ten(Q(), Q())
    out = compile(DistR(a, b, c))

    # Width: 1 (a) + 1 tag + 1 (b) + 2 (c) = 5
    assert out.circuit.n_qubits == 5

    # No tag flips (just wire rearrangement)
    assert len(out.circuit.get_commands()) == 0

    # Permutation: [A, tag, B, C0, C1] -> [tag, A, B, C0, C1]
    # new_to_old: position 0 gets value from position 1 (tag)
    #             position 1 gets value from position 0 (A)
    #             positions 2-4 stay the same
    expected_perm = [1, 0, 2, 3, 4]
    assert out.perm.new_to_old == expected_perm
