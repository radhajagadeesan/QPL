# tests/test_22_distributivity.py
"""Distributivity tests with one-hot leaf-tag encoding.

One-Hot Distributivity:
  DistL: (A ⊕ B) ⊗ C → (A ⊗ C) ⊕ (B ⊗ C)
    - Physical layout: [t_A | t_B | A | B | C] (same for both types)
    - DistL is IDENTITY on wires

  DistR: A ⊗ (B ⊕ C) → (A ⊗ B) ⊕ (A ⊗ C)
    - Input layout:  [A | t_B | t_C | B | C]
    - Output layout: [t_B | t_C | A | B | C]
    - DistR moves all tags from after A to before A
"""

from lang.types import Q, Ten
from lang.terms import DistL, DistR
from compile.to_pytket import compile
from core.perm import identity


def test_distL_is_identity():
    """DistL: (A ⊕ B) ⊗ C → (A ⊗ C) ⊕ (B ⊗ C) is identity on wires.

    For A = Q(), B = Q() ⊗ Q(), C = Q():
    - Domain: (Q ⊕ (Q⊗Q)) ⊗ Q
    - (Q ⊕ (Q⊗Q)) has 2 summands: 2 tags + 1 + 2 = 5
    - Width = 5 + 1 = 6 [t_A | t_B | A | B0 | B1 | C]

    The physical layout is unchanged by distributivity - only the type changes.
    """
    a = Q()
    b = Ten(Q(), Q())
    c = Q()
    out = compile(DistL(a, b, c))

    # Width: 2 tags + 1 (a) + 2 (b) + 1 (c) = 6
    assert out.circuit.n_qubits == 6

    # No gates (pure permutation, which is identity)
    assert len(out.circuit.get_commands()) == 0

    # Permutation is identity
    assert out.perm.new_to_old == identity(6).new_to_old


def test_distR_moves_tags():
    """DistR: A ⊗ (B ⊕ C) → (A ⊗ B) ⊕ (A ⊗ C) moves tags to front.

    For A = Q(), B = Q(), C = Q() ⊗ Q():
    - Domain: Q ⊗ (Q ⊕ (Q⊗Q))
    - (Q ⊕ (Q⊗Q)) has 2 summands: 2 tags + 1 + 2 = 5
    - Width = 1 + 5 = 6 [A | t_B | t_C | B | C0 | C1]
    - Codomain layout: [t_B | t_C | A | B | C0 | C1]

    DistR permutes the 2 tags from positions 1,2 to positions 0,1.
    """
    a = Q()
    b = Q()
    c = Ten(Q(), Q())
    out = compile(DistR(a, b, c))

    # Width: 1 (a) + 2 tags + 1 (b) + 2 (c) = 6
    assert out.circuit.n_qubits == 6

    # No tag flips (just wire rearrangement)
    assert len(out.circuit.get_commands()) == 0

    # Permutation: [A, t_B, t_C, B, C0, C1] -> [t_B, t_C, A, B, C0, C1]
    # new_to_old: [1, 2, 0, 3, 4, 5]
    expected_perm = [1, 2, 0, 3, 4, 5]
    assert out.perm.new_to_old == expected_perm
