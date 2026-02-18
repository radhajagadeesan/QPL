# tests/test_22_distributivity.py
"""Distributivity tests with flat log-tag encoding.

Option B Distributivity:
  DistL: (A ⊕ B) ⊗ C → (A ⊗ C) ⊕ (B ⊗ C)
    - Physical layout: [tag_bits | payload | C_wires] (same for both types)
    - DistL is IDENTITY on wires

  DistR: A ⊗ (B ⊕ C) → (A ⊗ B) ⊕ (A ⊗ C)
    - Input layout:  [A_wires | tag_bits | payload_BC]
    - Output layout: [tag_bits | A_wires | payload_BC]
    - DistR moves tag bits from after A to before A
"""

from lang.types import Q, Ten
from lang.terms import DistL, DistR
from compile.to_pytket import compile
from core.perm import identity


def test_distL_is_identity():
    """DistL: (A ⊕ B) ⊗ C → (A ⊗ C) ⊕ (B ⊗ C) is identity on wires.

    For A = Q(), B = Q() ⊗ Q(), C = Q():
    - (Q ⊕ (Q⊗Q)) has 1 tag + max(1, 2) = 3 wires
    - Width = 3 + 1 = 4: [tag | payload₀ | payload₁ | C]
    """
    a = Q()
    b = Ten(Q(), Q())
    c = Q()
    out = compile(DistL(a, b, c))

    # Width: 1 tag + max(1,2)=2 payload + 1 C = 4
    assert out.circuit.n_qubits == 4

    # No gates (pure identity)
    assert len(out.circuit.get_commands()) == 0

    # Permutation is identity
    assert out.perm.new_to_old == identity(4).new_to_old


def test_distR_moves_tags():
    """DistR: A ⊗ (B ⊕ C) → (A ⊗ B) ⊕ (A ⊗ C) moves tags to front.

    For A = Q(), B = Q(), C = Q() ⊗ Q():
    - (Q ⊕ (Q⊗Q)) has 1 tag + max(1, 2) = 3 wires
    - Domain: Q ⊗ (Q ⊕ (Q⊗Q)) = 1 + 3 = 4 wires: [A | tag | p₀ | p₁]
    - Codomain: [tag | A | p₀ | p₁]
    """
    a = Q()
    b = Q()
    c = Ten(Q(), Q())
    out = compile(DistR(a, b, c))

    # Width: 1 A + 1 tag + max(1,2)=2 payload = 4
    assert out.circuit.n_qubits == 4

    # No tag flips (just wire rearrangement)
    assert len(out.circuit.get_commands()) == 0

    # Permutation: [A, tag, p0, p1] -> [tag, A, p0, p1]
    # new_to_old: [1, 0, 2, 3]
    expected_perm = [1, 0, 2, 3]
    assert out.perm.new_to_old == expected_perm
