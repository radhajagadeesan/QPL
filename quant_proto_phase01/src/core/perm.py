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

One-Hot Leaf-Tag Sum Layout
---------------------------
For an n-ary sum A₁ ⊕ ... ⊕ Aₙ (represented as nested binary Plus),
the wire layout uses one-hot encoding:

  [t₁ | t₂ | ... | tₙ | A₁_wires | A₂_wires | ... | Aₙ_wires]

Key invariant:
  ALL structural operations on sums compile to PURE WIRE PERMUTATIONS.
  No tag bit flips (X gates) are ever required.

This makes:
  - TwistPlus: pure permutation (swap tags and payloads)
  - AssocPlusL/R: identity (same physical layout after flattening)
  - DistL: identity on wires (with shared tensor semantics)
  - DistR: pure permutation (move tags to front)
  - Involutions easy to detect: π² = id iff P is involutive
  - exp(iθP) lowering clean: decompose into ExpSwap atoms
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, FrozenSet, Tuple

from lang.types import Ty, Ten, Plus, width, flatten_plus


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


def decompose_involution(p: WirePerm) -> List[Tuple[int, int]]:
    """Decompose an involutive permutation into disjoint transpositions.

    For an involution π with π² = id, every element is either:
    - Fixed (1-cycle): π(i) = i
    - Part of a swap (2-cycle): π(i) = j and π(j) = i where i ≠ j

    Returns a list of (a, b) pairs representing disjoint swaps.
    Fixed points are not included.

    Requires: is_involution(p) == True

    This decomposition is used for exp(iθP) lowering:
    - Each transposition (a, b) becomes an ExpSwap(θ, a, b) gate atom
    - Disjoint transpositions commute, so order doesn't matter
    """
    if not is_involution(p):
        raise ValueError("decompose_involution requires an involutive permutation")

    swaps = []
    seen = set()

    for i in range(p.n):
        if i in seen:
            continue
        j = p.apply_new_to_old(i)
        if i != j:
            # Found a swap (i, j) - use canonical ordering (smaller first)
            swaps.append((min(i, j), max(i, j)))
            seen.add(i)
            seen.add(j)
        # else: fixed point, skip

    return swaps


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
    """TwistPlus: A ⊕ B → B ⊕ A with one-hot leaf-tag encoding.

    The domain type Plus(a, b) is flattened to get leaf summands.
    The "a" block summands and "b" block summands are swapped.

    Layout transformation:
      Input:  [t_A₁ | ... | t_Aₘ | t_B₁ | ... | t_Bₖ | A₁_data | ... | Aₘ_data | B₁_data | ... | Bₖ_data]
      Output: [t_B₁ | ... | t_Bₖ | t_A₁ | ... | t_Aₘ | B₁_data | ... | Bₖ_data | A₁_data | ... | Aₘ_data]

    This is a PURE PERMUTATION - no X gates needed with one-hot encoding!
    """
    # Get leaf summand counts for each side
    a_summands = flatten_plus(a) if isinstance(a, Plus) else [a]
    b_summands = flatten_plus(b) if isinstance(b, Plus) else [b]
    n_a_tags = len(a_summands)
    n_b_tags = len(b_summands)
    n_tags = n_a_tags + n_b_tags

    # Data widths for each summand (NOT width(a) which would include nested tags!)
    # Each leaf summand contributes its own width to the data section
    w_a_data = sum(width(s) for s in a_summands)
    w_b_data = sum(width(s) for s in b_summands)
    total = n_tags + w_a_data + w_b_data

    # Build permutation: swap tag blocks and data blocks
    # Input layout:
    #   Tags: [0..n_a_tags-1 = A_tags | n_a_tags..n_tags-1 = B_tags]
    #   Data: [n_tags..n_tags+w_a_data-1 = A_data | n_tags+w_a_data..total-1 = B_data]
    # Output layout: [B_tags | A_tags | B_data | A_data]

    new_to_old = []
    # B tags come first
    new_to_old.extend(range(n_a_tags, n_tags))
    # A tags come second
    new_to_old.extend(range(0, n_a_tags))
    # B data
    new_to_old.extend(range(n_tags + w_a_data, total))
    # A data
    new_to_old.extend(range(n_tags, n_tags + w_a_data))

    perm = WirePerm(total, new_to_old)
    return TaggedPerm(perm=perm, tag_flips=frozenset())  # No flips needed!


def twist_plus_perm_wire_only(a: Ty, b: Ty) -> WirePerm:
    """Legacy: just the wire permutation part of twist_plus (for compatibility)."""
    tp = twist_plus_perm(a, b)
    return tp.perm


def assoc_plus_L_perm(a: Ty, b: Ty, c: Ty) -> TaggedPerm:
    """AssocPlusL: (A ⊕ B) ⊕ C → A ⊕ (B ⊕ C) with one-hot leaf-tag encoding.

    With one-hot encoding, both types flatten to the SAME layout!
      (A ⊕ B) ⊕ C flattens to [A, B, C]: [t_A | t_B | t_C | A | B | C]
      A ⊕ (B ⊕ C) flattens to [A, B, C]: [t_A | t_B | t_C | A | B | C]

    Therefore, AssocPlusL is IDENTITY - the physical layout is unchanged.
    """
    total = width(Plus(Plus(a, b), c))
    return TaggedPerm(perm=identity(total), tag_flips=frozenset())


def assoc_plus_R_perm(a: Ty, b: Ty, c: Ty) -> TaggedPerm:
    """AssocPlusR: A ⊕ (B ⊕ C) → (A ⊕ B) ⊕ C with one-hot leaf-tag encoding.

    With one-hot encoding, both types flatten to the SAME layout!
      A ⊕ (B ⊕ C) flattens to [A, B, C]: [t_A | t_B | t_C | A | B | C]
      (A ⊕ B) ⊕ C flattens to [A, B, C]: [t_A | t_B | t_C | A | B | C]

    Therefore, AssocPlusR is IDENTITY - the physical layout is unchanged.
    """
    total = width(Plus(a, Plus(b, c)))
    return TaggedPerm(perm=identity(total), tag_flips=frozenset())


# ---------------------------------------------------------------------------
# Distributivity permutations
# ---------------------------------------------------------------------------

def dist_L_perm(a: Ty, b: Ty, c: Ty) -> TaggedPerm:
    """DistL: (A ⊕ B) ⊗ C → (A ⊗ C) ⊕ (B ⊗ C) with one-hot leaf-tag encoding.

    This is the key insight of the tagged layout model:
    DistL is IDENTITY on wires!

    With one-hot encoding:
      Input (A ⊕ B) ⊗ C:  [t_A | t_B | A_wires | B_wires | C_wires]
      Output (A⊗C)⊕(B⊗C): [t_{A⊗C} | t_{B⊗C} | A_wires | B_wires | C_wires]
                          = [t_A | t_B | A_wires | B_wires | C_wires]

    With shared tensor semantics:
      - If t_A=1: active data is A_wires ++ C_wires
      - If t_B=1: active data is B_wires ++ C_wires

    The physical wire layout is IDENTICAL - only the type interpretation changes.
    """
    total = width(Ten(Plus(a, b), c))
    return TaggedPerm(perm=identity(total), tag_flips=frozenset())


def dist_R_perm(a: Ty, b: Ty, c: Ty) -> TaggedPerm:
    """DistR: A ⊗ (B ⊕ C) → (A ⊗ B) ⊕ (A ⊗ C) with one-hot leaf-tag encoding.

    With one-hot encoding:
      Input A ⊗ (B ⊕ C):  [A_wires | t_B | t_C | B_wires | C_wires]
      Output (A⊗B)⊕(A⊗C): [t_B | t_C | A_wires | B_wires | C_wires]

    The tags move from after A_wires to before A_wires.
    """
    w_a = width(a)
    # Get number of tags for B ⊕ C
    bc_summands = flatten_plus(Plus(b, c))
    n_tags = len(bc_summands)

    total = width(Ten(a, Plus(b, c)))

    # Input positions:  [0..w_a-1=A | w_a..w_a+n_tags-1=tags | rest=B,C_wires]
    # Output positions: [0..n_tags-1=tags | n_tags..n_tags+w_a-1=A | rest=B,C_wires]
    new_to_old = []
    # Tags move to front
    new_to_old.extend(range(w_a, w_a + n_tags))
    # A_wires move after tags
    new_to_old.extend(range(0, w_a))
    # B and C wires stay in order
    new_to_old.extend(range(w_a + n_tags, total))

    perm = WirePerm(total, new_to_old)
    return TaggedPerm(perm=perm, tag_flips=frozenset())


def undist_L_perm(a: Ty, b: Ty, c: Ty) -> TaggedPerm:
    """UndistL: (A ⊗ C) ⊕ (B ⊗ C) → (A ⊕ B) ⊗ C (inverse of DistL).

    Since DistL is identity, so is UndistL.
    """
    return dist_L_perm(a, b, c)  # Identity is self-inverse


def undist_R_perm(a: Ty, b: Ty, c: Ty) -> TaggedPerm:
    """UndistR: (A ⊗ B) ⊕ (A ⊗ C) → A ⊗ (B ⊕ C) (inverse of DistR).

    Inverse of dist_R_perm: move tags from front back to after A_wires.
    """
    w_a = width(a)
    # Get number of tags for B ⊕ C
    bc_summands = flatten_plus(Plus(b, c))
    n_tags = len(bc_summands)

    total = width(Ten(a, Plus(b, c)))

    # Input positions:  [0..n_tags-1=tags | n_tags..n_tags+w_a-1=A | rest=B,C_wires]
    # Output positions: [0..w_a-1=A | w_a..w_a+n_tags-1=tags | rest=B,C_wires]
    new_to_old = []
    # A_wires move to front
    new_to_old.extend(range(n_tags, n_tags + w_a))
    # Tags move after A_wires
    new_to_old.extend(range(0, n_tags))
    # B and C wires stay in order
    new_to_old.extend(range(n_tags + w_a, total))

    perm = WirePerm(total, new_to_old)
    return TaggedPerm(perm=perm, tag_flips=frozenset())
