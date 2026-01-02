# src/core/perm.py
"""Permutation (wire-renaming) infrastructure.

We compile structural isomorphisms (id/twist/assoc/...) to *permutations* of
wire indices, carried as metadata rather than emitted as SWAP gates.

Convention
----------
A WirePerm p of size n stores a mapping `p.new_to_old` such that:

  wire at NEW position i corresponds to OLD position p.new_to_old[i].

Composition:
  (q ∘ p).new_to_old[i] = p.new_to_old[ q.new_to_old[i] ].

Tagged Sum Layout
-----------------
For A ⊕ B, the wire layout is:
  [tag | A_wires | B_wires]

where:
  - tag is a single qubit indicating which branch is "active" (0=left, 1=right)
  - A_wires and B_wires are the data wires for each branch
  - width(A ⊕ B) = 1 + width(A) + width(B)

Some sum operations (like TwistPlus) require flipping the tag bit in addition
to permuting data wires. These are represented as TaggedPerm objects.

Distributivity
--------------
With the tagged layout:
  - DistL : (A⊕B)⊗C → (A⊗C)⊕(B⊗C) is identity on wires (same physical layout)
  - DistR : A⊗(B⊕C) → (A⊗B)⊕(A⊗C) moves the tag to the front
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, FrozenSet

from lang.types import Ty, Ten, Plus, width


class WirePerm:
    """Wire permutation representing wire reindexing.

    Can be constructed either as:
        WirePerm([1, 0, 2, 3])  # single list arg, n inferred
        WirePerm(4, [1, 0, 2, 3])  # explicit n and list
        WirePerm(n=4, new_to_old=[1, 0, 2, 3])  # keyword args
    """
    __slots__ = ('n', 'new_to_old')

    def __init__(self, n_or_list=None, new_to_old=None, *, n=None):
        # Handle keyword argument 'n'
        if n is not None:
            # Called with n=... keyword arg
            actual_n = n
            actual_list = list(new_to_old) if new_to_old is not None else list(n_or_list)
        elif new_to_old is not None:
            # Called with two positional args: WirePerm(4, [1,0,2,3])
            actual_n = n_or_list
            actual_list = list(new_to_old)
        else:
            # Called with single arg: WirePerm([1,0,2,3])
            actual_list = list(n_or_list)
            actual_n = len(actual_list)

        if len(actual_list) != actual_n:
            raise ValueError("WirePerm length mismatch")
        if sorted(actual_list) != list(range(actual_n)):
            raise ValueError(f"WirePerm is not a permutation: {actual_list}")

        object.__setattr__(self, 'n', actual_n)
        object.__setattr__(self, 'new_to_old', actual_list)

    def __setattr__(self, name, value):
        raise AttributeError("WirePerm is immutable")

    def __hash__(self):
        return hash((self.n, tuple(self.new_to_old)))

    def __eq__(self, other):
        if not isinstance(other, WirePerm):
            return NotImplemented
        return self.n == other.n and self.new_to_old == other.new_to_old

    def __repr__(self):
        return f"WirePerm(n={self.n}, new_to_old={self.new_to_old})"

    def apply_new_to_old(self, i_new: int) -> int:
        return self.new_to_old[i_new]

    def restrict(self, indices: "Set[int]") -> "WirePerm":
        """Restrict permutation to a subset of wire indices.

        Returns a new permutation on len(indices) wires that represents
        the behavior of this permutation restricted to the given indices.

        The indices are mapped to [0, len(indices)) in sorted order.
        """
        sorted_indices = sorted(indices)
        index_map = {old: new for new, old in enumerate(sorted_indices)}

        new_to_old = []
        for i in sorted_indices:
            old_target = self.new_to_old[i]
            if old_target not in index_map:
                raise ValueError(
                    f"Restriction invalid: wire {i} maps to {old_target} "
                    f"which is not in the restriction set {indices}"
                )
            new_to_old.append(index_map[old_target])

        return WirePerm(len(indices), new_to_old)


def identity(n: int) -> WirePerm:
    return WirePerm(n=n, new_to_old=list(range(n)))


def compose(q: WirePerm, p: WirePerm) -> WirePerm:
    if p.n != q.n:
        raise ValueError("Cannot compose WirePerm of different sizes")
    return WirePerm(n=p.n, new_to_old=[p.new_to_old[q.new_to_old[i]] for i in range(p.n)])


def inverse(p: WirePerm) -> WirePerm:
    inv = [0] * p.n
    for i_new, i_old in enumerate(p.new_to_old):
        inv[i_old] = i_new
    return WirePerm(n=p.n, new_to_old=inv)


def is_involution(p: WirePerm) -> bool:
    """Check if permutation is an involution (p ∘ p = identity).

    An involution is its own inverse: applying it twice returns to the start.
    Examples: swaps, identity, any product of disjoint transpositions.
    """
    composed = compose(p, p)
    return composed == identity(p.n)


def block_swap(m: int, n: int) -> WirePerm:
    total = m + n
    new_to_old = list(range(m, total)) + list(range(0, m))
    return WirePerm(total, new_to_old)


# ---------------------------------------------------------------------------
# TaggedPerm: Permutation with tag bit flips for sum types
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class TaggedPerm:
    """Permutation with optional tag bit flips for sum types.

    In the tagged sum model, A ⊕ B has layout [tag | A_wires | B_wires].
    Some operations (like TwistPlus) require flipping the tag bit in addition
    to permuting wires.

    Attributes:
        perm: Wire permutation (includes tag wire at position 0 for sums)
        tag_flips: Frozenset of wire indices that need X gates applied (tag flips)

    The tag_flips are specified in terms of OUTPUT wire positions (after perm).
    """
    perm: WirePerm
    tag_flips: FrozenSet[int] = field(default_factory=frozenset)

    def __post_init__(self):
        # Validate tag_flips are within bounds
        for pos in self.tag_flips:
            if pos < 0 or pos >= self.perm.n:
                raise ValueError(f"Tag flip position {pos} out of bounds for perm of size {self.perm.n}")


def tagged_identity(n: int) -> TaggedPerm:
    """Identity TaggedPerm with no flips."""
    return TaggedPerm(perm=identity(n), tag_flips=frozenset())


def tagged_compose(q: TaggedPerm, p: TaggedPerm) -> TaggedPerm:
    """Compose two TaggedPerms: (q ∘ p).

    When composing:
    1. Wire permutations compose normally
    2. Tag flips from p (at output positions) get mapped through q's perm
    3. Tag flips are XOR'd (flip twice = no flip)
    """
    if p.perm.n != q.perm.n:
        raise ValueError("Cannot compose TaggedPerm of different sizes")

    # Compose wire permutations
    new_perm = compose(q.perm, p.perm)

    # Map p's tag flips through q's permutation
    # p's flips are at p's output positions = q's input positions
    # We need to find where they end up at q's output
    p_flips_mapped = set()
    for pos in p.tag_flips:
        # Find which output position of q corresponds to input position pos
        # q.perm.new_to_old[out] = pos means output 'out' came from input 'pos'
        for out_pos, in_pos in enumerate(q.perm.new_to_old):
            if in_pos == pos:
                p_flips_mapped.add(out_pos)
                break

    # XOR the flip sets (positions that appear in both cancel out)
    combined = p_flips_mapped.symmetric_difference(q.tag_flips)

    return TaggedPerm(perm=new_perm, tag_flips=frozenset(combined))


def tagged_from_perm(p: WirePerm) -> TaggedPerm:
    """Convert a plain WirePerm to TaggedPerm with no flips."""
    return TaggedPerm(perm=p, tag_flips=frozenset())


# ---------------------------------------------------------------------------
# Type-directed permutations
# ---------------------------------------------------------------------------

def twist_tensor_perm(a: Ty, b: Ty) -> WirePerm:
    return block_swap(width(a), width(b))


def assoc_tensor_L_perm(a: Ty, b: Ty, c: Ty) -> WirePerm:
    # identity on flat wires
    n = width(Ten(Ten(a, b), c))
    return identity(n)


def assoc_tensor_R_perm(a: Ty, b: Ty, c: Ty) -> WirePerm:
    n = width(Ten(a, Ten(b, c)))
    return identity(n)


def twist_plus_perm(a: Ty, b: Ty) -> TaggedPerm:
    """TwistPlus: A ⊕ B → B ⊕ A in tagged layout.

    Layout transformation:
      Input:  [tag | A_wires | B_wires]
      Output: [tag | B_wires | A_wires]

    The tag is flipped (X gate) because:
      - tag=0 meant "left branch (A)" in input
      - tag=0 should mean "left branch (B)" in output
      - So if we had A active (tag=0), we need tag=1 for A in output
    """
    w_a = width(a)
    w_b = width(b)
    total = 1 + w_a + w_b  # 1 tag + data wires

    # Tag stays at position 0, data wires get swapped
    # [0 | 1..w_a | w_a+1..w_a+w_b] -> [0 | w_a+1..w_a+w_b | 1..w_a]
    new_to_old = [0]  # tag stays at position 0
    new_to_old.extend(range(1 + w_a, 1 + w_a + w_b))  # B_wires come first
    new_to_old.extend(range(1, 1 + w_a))  # A_wires come second

    perm = WirePerm(total, new_to_old)
    return TaggedPerm(perm=perm, tag_flips=frozenset([0]))  # Flip the tag


def twist_plus_perm_wire_only(a: Ty, b: Ty) -> WirePerm:
    """Legacy: just the wire permutation part of twist_plus (for compatibility)."""
    tp = twist_plus_perm(a, b)
    return tp.perm


def assoc_plus_L_perm(a: Ty, b: Ty, c: Ty) -> TaggedPerm:
    """AssocPlusL: (A ⊕ B) ⊕ C → A ⊕ (B ⊕ C) in tagged layout.

    Layout transformation:
      Input:  [t_outer | t_inner | A_wires | B_wires | C_wires]
              (t_outer: 0=AB, 1=C; t_inner: 0=A, 1=B when t_outer=0)
      Output: [t_outer' | A_wires | t_inner' | B_wires | C_wires]
              (t_outer': 0=A, 1=BC; t_inner': 0=B, 1=C when t_outer'=1)

    This permutation moves the inner tag from position 1 to position 1+w_a.
    Note: The tag recoding semantics require controlled operations in general,
    but for structural purposes we implement the wire permutation.
    """
    w_a = width(a)
    w_b = width(b)
    w_c = width(c)
    total = 2 + w_a + w_b + w_c  # 2 tags + data wires

    # Build permutation:
    # Input positions:  [0=t_out, 1=t_in, 2..2+w_a-1=A, 2+w_a..2+w_a+w_b-1=B, 2+w_a+w_b..end=C]
    # Output positions: [0=t_out', 1..1+w_a-1=A, 1+w_a=t_in', 1+w_a+1..end=B, then C]
    new_to_old = [0]  # outer tag stays at 0
    new_to_old.extend(range(2, 2 + w_a))  # A_wires at positions 1 to w_a
    new_to_old.append(1)  # inner tag moves to position 1 + w_a
    new_to_old.extend(range(2 + w_a, 2 + w_a + w_b))  # B_wires
    new_to_old.extend(range(2 + w_a + w_b, total))  # C_wires

    perm = WirePerm(total, new_to_old)
    # Note: Full semantic correctness requires tag recoding (controlled-X gates)
    # For now we return just the permutation; tag recoding is a TODO
    return TaggedPerm(perm=perm, tag_flips=frozenset())


def assoc_plus_R_perm(a: Ty, b: Ty, c: Ty) -> TaggedPerm:
    """AssocPlusR: A ⊕ (B ⊕ C) → (A ⊕ B) ⊕ C (inverse of AssocPlusL)."""
    w_a = width(a)
    w_b = width(b)
    w_c = width(c)
    total = 2 + w_a + w_b + w_c

    # Inverse of assoc_plus_L_perm
    # Input:  [t_out | A_wires | t_in | B_wires | C_wires]
    # Output: [t_out' | t_in' | A_wires | B_wires | C_wires]
    new_to_old = [0]  # outer tag stays at 0
    new_to_old.append(1 + w_a)  # inner tag from position 1+w_a to position 1
    new_to_old.extend(range(1, 1 + w_a))  # A_wires from 1..w_a to 2..2+w_a
    new_to_old.extend(range(2 + w_a, 2 + w_a + w_b))  # B_wires
    new_to_old.extend(range(2 + w_a + w_b, total))  # C_wires

    perm = WirePerm(total, new_to_old)
    return TaggedPerm(perm=perm, tag_flips=frozenset())


# ---------------------------------------------------------------------------
# Distributivity permutations
# ---------------------------------------------------------------------------

def dist_L_perm(a: Ty, b: Ty, c: Ty) -> TaggedPerm:
    """DistL: (A ⊕ B) ⊗ C → (A ⊗ C) ⊕ (B ⊗ C) in tagged layout.

    This is the key insight of the tagged layout model:
    DistL is IDENTITY on wires!

    Input layout for (A ⊕ B) ⊗ C:
      [(A ⊕ B) wires | C wires] = [tag | A_wires | B_wires | C_wires]
      Width: (1 + w_a + w_b) + w_c = 1 + w_a + w_b + w_c

    Output layout for (A ⊗ C) ⊕ (B ⊗ C):
      [tag | (A ⊗ C)_wires | (B ⊗ C)_wires]

      But (A ⊗ C) shares C with (B ⊗ C) in the linear/GOI interpretation!
      So the layout is: [tag | A_wires | C_wires : B_wires | C_wires]
      where C_wires is SHARED between branches.

      In practice, this means:
        [tag | A_wires | B_wires | C_wires]
        - If tag=0: active data is A_wires ++ C_wires
        - If tag=1: active data is B_wires ++ C_wires

    The physical wire layout is IDENTICAL - only the type interpretation changes.
    """
    w_a = width(a)
    w_b = width(b)
    w_c = width(c)
    n = 1 + w_a + w_b + w_c  # tagged layout width

    return TaggedPerm(perm=identity(n), tag_flips=frozenset())


def dist_R_perm(a: Ty, b: Ty, c: Ty) -> TaggedPerm:
    """DistR: A ⊗ (B ⊕ C) → (A ⊗ B) ⊕ (A ⊗ C) in tagged layout.

    Input layout for A ⊗ (B ⊕ C):
      [A_wires | (B ⊕ C)_wires] = [A_wires | tag | B_wires | C_wires]
      Width: w_a + (1 + w_b + w_c) = 1 + w_a + w_b + w_c

    Output layout for (A ⊗ B) ⊕ (A ⊗ C):
      [tag | (A ⊗ B)_wires | (A ⊗ C)_wires]
      With sharing: [tag | A_wires | B_wires | C_wires]

    The tag needs to move from position w_a to position 0.
    """
    w_a = width(a)
    w_b = width(b)
    w_c = width(c)
    n = 1 + w_a + w_b + w_c

    # Input positions:  [0..w_a-1=A | w_a=tag | w_a+1..w_a+w_b=B | rest=C]
    # Output positions: [0=tag | 1..w_a=A | w_a+1..w_a+w_b=B | rest=C]
    new_to_old = [w_a]  # tag moves from position w_a to position 0
    new_to_old.extend(range(0, w_a))  # A_wires move to positions 1..w_a
    new_to_old.extend(range(w_a + 1, n))  # B and C wires stay in order

    perm = WirePerm(n, new_to_old)
    return TaggedPerm(perm=perm, tag_flips=frozenset())


def undist_L_perm(a: Ty, b: Ty, c: Ty) -> TaggedPerm:
    """UndistL: (A ⊗ C) ⊕ (B ⊗ C) → (A ⊕ B) ⊗ C (inverse of DistL).

    Since DistL is identity, so is UndistL.
    """
    return dist_L_perm(a, b, c)  # Identity is self-inverse


def undist_R_perm(a: Ty, b: Ty, c: Ty) -> TaggedPerm:
    """UndistR: (A ⊗ B) ⊕ (A ⊗ C) → A ⊗ (B ⊕ C) (inverse of DistR).

    Inverse of dist_R_perm: move tag from position 0 back to position w_a.
    """
    w_a = width(a)
    w_b = width(b)
    w_c = width(c)
    n = 1 + w_a + w_b + w_c

    # Input positions:  [0=tag | 1..w_a=A | w_a+1..w_a+w_b=B | rest=C]
    # Output positions: [0..w_a-1=A | w_a=tag | w_a+1..end=B,C]
    new_to_old = list(range(1, w_a + 1))  # A_wires from 1..w_a to 0..w_a-1
    new_to_old.append(0)  # tag from position 0 to position w_a
    new_to_old.extend(range(w_a + 1, n))  # B and C wires stay in order

    perm = WirePerm(n, new_to_old)
    return TaggedPerm(perm=perm, tag_flips=frozenset())
