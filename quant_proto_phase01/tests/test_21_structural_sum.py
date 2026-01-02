# tests/test_21_structural_sum.py
"""Structural compilation tests (sum only): twist/assoc for ⊕.

Tagged Layout Model:
  A ⊕ B has layout [tag | A_wires | B_wires]
  width(A ⊕ B) = 1 + width(A) + width(B)

  TwistPlus: A ⊕ B → B ⊕ A
    - Swaps data wires
    - Emits X gate on tag (to flip the branch indicator)

  AssocPlusL/R: permute tag positions within the wire layout
"""

from lang.types import Q, Ten
from lang.terms import TwistPlus, AssocPlusL, AssocPlusR, Seq
from compile.to_pytket import compile
from core.perm import identity


def test_twist_plus_compiles_to_perm_and_tag_flip():
    """TwistPlus on A ⊕ B → B ⊕ A in tagged layout.

    For A = Q() (width 1), B = Q() ⊗ Q() (width 2):
    - A ⊕ B has width = 1 + 1 + 2 = 4 (tag + A + B)
    - Layout: [tag | A | B_0 | B_1]
    - After TwistPlus: [tag | B_0 | B_1 | A] with tag flipped

    The permutation swaps data wires (A ↔ B), tag stays at position 0.
    An X gate is emitted on the tag wire.
    """
    a = Q()              # width 1
    b = Ten(Q(), Q())    # width 2
    out = compile(TwistPlus(a, b))

    # With tagged layout: 1 tag + 1 (a) + 2 (b) = 4 wires
    assert out.circuit.n_qubits == 4

    # One X gate for the tag flip
    commands = out.circuit.get_commands()
    assert len(commands) == 1
    assert commands[0].op.type.name == 'X'

    # Permutation: tag stays, data wires swapped
    # [0=tag, 1=A, 2=B0, 3=B1] -> [0=tag, 1=B0, 2=B1, 3=A]
    # new_to_old: new position i came from old position new_to_old[i]
    expected_perm = [0, 2, 3, 1]  # tag:0←0, B0:1←2, B1:2←3, A:3←1
    assert out.perm.new_to_old == expected_perm


def test_assoc_plus_permutes_tags():
    """AssocPlus in tagged layout moves inner tag position.

    For A = B = C = Q():
    - (A ⊕ B) ⊕ C has width = 1 + width(A⊕B) + width(C)
                            = 1 + (1 + 1 + 1) + 1 = 5
    - Layout: [t_outer | t_inner | A | B | C]

    - A ⊕ (B ⊕ C) has width = 1 + width(A) + width(B⊕C)
                            = 1 + 1 + (1 + 1 + 1) = 5
    - Layout: [t_outer | A | t_inner | B | C]

    AssocPlusL moves the inner tag from position 1 to position 2.
    """
    a = b = c = Q()
    out = compile(AssocPlusL(a, b, c))

    # 2 tags + 3 data = 5 wires
    assert out.circuit.n_qubits == 5

    # No tag flips for assoc (just wire rearrangement)
    assert len(out.circuit.get_commands()) == 0

    # Permutation: [0=t_out, 1=t_in, 2=A, 3=B, 4=C] -> [0=t_out, 1=A, 2=t_in, 3=B, 4=C]
    expected_perm = [0, 2, 1, 3, 4]
    assert out.perm.new_to_old == expected_perm

    out2 = compile(AssocPlusR(a, b, c))
    # Inverse permutation
    expected_perm_inv = [0, 2, 1, 3, 4]  # Also [0, 2, 1, 3, 4] since it's an involution
    assert out2.perm.new_to_old == expected_perm_inv


def test_seq_of_twists_is_identity():
    """TwistPlus ∘ TwistPlus = identity (involution).

    Two consecutive TwistPlus operations should cancel out:
    - Wire permutation is involutive
    - Two X gates on the tag cancel (X ∘ X = I)
    """
    a = Q()
    b = Ten(Q(), Q())
    t1 = TwistPlus(a, b)  # A ⊕ B → B ⊕ A
    t2 = TwistPlus(b, a)  # B ⊕ A → A ⊕ B
    out = compile(Seq(t1, t2))

    # 4 wires total (1 tag + 1 + 2)
    assert out.circuit.n_qubits == 4

    # Two X gates (they would cancel physically, but we emit both)
    commands = out.circuit.get_commands()
    assert len(commands) == 2
    assert all(cmd.op.type.name == 'X' for cmd in commands)

    # Permutation should be identity
    assert out.perm.new_to_old == identity(4).new_to_old
