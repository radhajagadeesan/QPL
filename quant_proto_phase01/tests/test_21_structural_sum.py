# tests/test_21_structural_sum.py
"""Structural compilation tests (sum only): twist/assoc for ⊕.

One-Hot Leaf-Tag Layout Model:
  For n-ary sum A₁ ⊕ ... ⊕ Aₙ, the layout is:
    [t₁ | t₂ | ... | tₙ | A₁_wires | A₂_wires | ... | Aₙ_wires]
  width(A ⊕ B) = 2 + width(A) + width(B)  (2 one-hot tags for 2 summands)

  Key invariant: ALL structural operations on sums are PURE PERMUTATIONS.
  No X gates are ever needed!

  TwistPlus: A ⊕ B → B ⊕ A
    - Swaps tags and data blocks
    - NO X gates (one-hot encoding)

  AssocPlusL/R: identity (same physical layout after flattening)
"""

from lang.types import Q, Ten
from lang.terms import TwistPlus, AssocPlusL, AssocPlusR, Seq
from compile.to_pytket import compile
from core.perm import identity


def test_twist_plus_is_pure_permutation():
    """TwistPlus on A ⊕ B → B ⊕ A with one-hot leaf-tag encoding.

    For A = Q() (width 1), B = Q() ⊗ Q() (width 2):
    - A ⊕ B has width = 2 + 1 + 2 = 5 (2 one-hot tags + data)
    - Layout: [t_A | t_B | A | B_0 | B_1]
    - After TwistPlus: [t_B | t_A | B_0 | B_1 | A]

    With one-hot encoding, this is a PURE PERMUTATION - no X gates!
    """
    a = Q()              # width 1
    b = Ten(Q(), Q())    # width 2
    out = compile(TwistPlus(a, b))

    # With one-hot layout: 2 tags + 1 (a) + 2 (b) = 5 wires
    assert out.circuit.n_qubits == 5

    # NO X gates needed - pure permutation!
    commands = out.circuit.get_commands()
    assert len(commands) == 0

    # Permutation swaps tag block and data block
    # [0=t_A, 1=t_B, 2=A, 3=B0, 4=B1] -> [0=t_B, 1=t_A, 2=B0, 3=B1, 4=A]
    # new_to_old: [1, 0, 3, 4, 2]
    expected_perm = [1, 0, 3, 4, 2]
    assert out.perm.new_to_old == expected_perm


def test_assoc_plus_is_identity():
    """AssocPlus with one-hot leaf-tag encoding is IDENTITY.

    For A = B = C = Q():
    - (A ⊕ B) ⊕ C flattens to [A, B, C]: 3 one-hot tags + 3 data = 6 wires
    - A ⊕ (B ⊕ C) flattens to [A, B, C]: 3 one-hot tags + 3 data = 6 wires

    Both have the SAME physical layout: [t_A | t_B | t_C | A | B | C]

    AssocPlusL and AssocPlusR are both IDENTITY permutations!
    """
    a = b = c = Q()
    out = compile(AssocPlusL(a, b, c))

    # 3 tags + 3 data = 6 wires
    assert out.circuit.n_qubits == 6

    # No gates at all - pure identity permutation!
    assert len(out.circuit.get_commands()) == 0

    # Identity permutation
    expected_perm = [0, 1, 2, 3, 4, 5]
    assert out.perm.new_to_old == expected_perm

    out2 = compile(AssocPlusR(a, b, c))
    # Also identity
    assert out2.perm.new_to_old == expected_perm


def test_seq_of_twists_is_identity():
    """TwistPlus ∘ TwistPlus = identity (involution).

    Two consecutive TwistPlus operations should cancel out:
    - Wire permutation is involutive (with one-hot encoding)
    - NO X gates needed at all!
    """
    a = Q()
    b = Ten(Q(), Q())
    t1 = TwistPlus(a, b)  # A ⊕ B → B ⊕ A
    t2 = TwistPlus(b, a)  # B ⊕ A → A ⊕ B
    out = compile(Seq(t1, t2))

    # 5 wires total (2 tags + 1 + 2) with one-hot encoding
    assert out.circuit.n_qubits == 5

    # NO X gates with one-hot encoding!
    commands = out.circuit.get_commands()
    assert len(commands) == 0

    # Permutation should be identity (two swaps cancel)
    assert out.perm.new_to_old == identity(5).new_to_old
