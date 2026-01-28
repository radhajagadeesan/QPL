# tests/test_21_structural_sum.py
"""Structural compilation tests (sum only): twist/assoc for ⊕.

Option B Flat Log-Tag Layout Model:
  For n-ary sum A₁ ⊕ ... ⊕ Aₙ, the layout is:
    [tag_bits | shared_payload]
  width(A ⊕ B) = ceil(log2(n)) + max(width(Aᵢ))

  Structural operations are tracked as symbolic tag permutations.
  TwistPlus emits X gates for binary tag flips.
  AssocPlusL/R: identity (same physical layout after flattening).
"""

from lang.types import Q, Ten
from lang.terms import TwistPlus, AssocPlusL, AssocPlusR, Seq
from compile.to_pytket import compile
from core.perm import identity


def test_twist_plus_is_tag_flip():
    """TwistPlus on A ⊕ B → B ⊕ A with flat log-tag encoding.

    For A = Q() (width 1), B = Q() ⊗ Q() (width 2):
    - A ⊕ B has width = 1 tag + max(1, 2) = 3
    - Layout: [tag | payload₀ | payload₁]
    - TwistPlus flips the tag bit (X gate) and leaves payload as identity.
    """
    a = Q()              # width 1
    b = Ten(Q(), Q())    # width 2
    out = compile(TwistPlus(a, b))

    # With Option B: 1 tag + max(1,2) = 3 wires
    assert out.circuit.n_qubits == 3

    # One X gate on the tag wire (tag flip)
    commands = out.circuit.get_commands()
    assert len(commands) == 1
    assert str(commands[0]).startswith("X")

    # Wire permutation is identity (shared payload unchanged)
    assert out.perm.new_to_old == [0, 1, 2]


def test_assoc_plus_is_identity():
    """AssocPlus with flat log-tag encoding is IDENTITY.

    For A = B = C = Q():
    - (A ⊕ B) ⊕ C flattens to [A, B, C]: ceil(log2(3))=2 tag bits + max(1)=1 = 3 wires
    - A ⊕ (B ⊕ C) flattens to [A, B, C]: same layout

    AssocPlusL and AssocPlusR are both IDENTITY!
    """
    a = b = c = Q()
    out = compile(AssocPlusL(a, b, c))

    # ceil(log2(3))=2 tag bits + max(1,1,1)=1 payload = 3 wires
    assert out.circuit.n_qubits == 3

    # No gates at all - identity
    assert len(out.circuit.get_commands()) == 0

    # Identity permutation
    expected_perm = [0, 1, 2]
    assert out.perm.new_to_old == expected_perm

    out2 = compile(AssocPlusR(a, b, c))
    assert out2.perm.new_to_old == expected_perm


def test_seq_of_twists_is_identity():
    """TwistPlus ; TwistPlus = identity (involution).

    Two consecutive TwistPlus operations cancel:
    - Each emits an X gate on the tag wire
    - X·X = I, so net effect is identity
    """
    a = Q()
    b = Ten(Q(), Q())
    t1 = TwistPlus(a, b)  # A ⊕ B → B ⊕ A
    t2 = TwistPlus(b, a)  # B ⊕ A → A ⊕ B
    out = compile(Seq(t1, t2))

    # 1 tag + max(1,2) = 3 wires
    assert out.circuit.n_qubits == 3

    # Two X gates (they cancel physically: X·X = I)
    commands = out.circuit.get_commands()
    assert len(commands) == 2

    # Wire permutation should be identity (tag flips cancel in perm layer)
    assert out.perm.new_to_old == identity(3).new_to_old
