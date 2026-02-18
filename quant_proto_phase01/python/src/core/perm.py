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

Option B: Flat Log-Tag Sum Layout
----------------------------------
For an n-ary sum A₁ ⊕ ... ⊕ Aₙ, the wire layout uses a flat log-sized
tag register + shared payload:

  ⟦Σ⟧ = Q^{⊗k} ⊗ W    where k = ceil(log2(n)), |W| = max_i(|Aᵢ|)

Layout: [tag₀ | ... | tag_{k-1} | payload₀ | ... | payload_{W-1}]

Structural operations on sums compile to symbolic tag permutations
(tracked in TaggedPerm.tag_perm) and are lowered to gates only at
emission time. This keeps the compilation pipeline clean and optimizable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, FrozenSet, Tuple

from lang.types import Ty, Ten, Plus, width, tag_width, payload_width, flatten_plus


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
    """Permutation with optional tag rewrites for sum types.

    In the Option B model, A ⊕ B has layout [tag_bits | shared_payload].
    Structural operations may need to relabel tag indices in addition to
    permuting payload wires.

    Attributes:
        perm: Wire permutation on the full wire space (tags + payload)
        tag_flips: Frozenset of wire indices that need X gates applied.
                   Fast-path for affine tag rewrites (XOR masks).
        tag_perm: Optional permutation of tag indices {0,...,n-1}.
                  Used for general structural relabelings (e.g., assoc).
                  None means identity on tag indices.

    The tag_flips are specified in terms of OUTPUT wire positions (after perm).
    """
    perm: WirePerm
    tag_flips: FrozenSet[int] = field(default_factory=frozenset)
    tag_perm: "Tuple[int, ...] | None" = None

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
    """TwistPlus: A ⊕ B → B ⊕ A with flat log-tag encoding.

    With Option B, Plus(a, b) is flattened to n summands with a shared payload.
    Layout: [tag_bits | shared_payload]

    TwistPlus swaps the summand groups: A-summands and B-summands exchange
    positions in the tag index space. The payload is shared and unchanged.

    For binary Plus(A, B) with 1 tag qubit:
      - Tag flip: 0↔1 (recorded as tag_flips={0})
      - Payload: identity (shared register, same size)

    For higher-arity cases, this is a tag_perm that swaps the A and B
    index blocks.
    """
    a_summands = flatten_plus(a) if isinstance(a, Plus) else [a]
    b_summands = flatten_plus(b) if isinstance(b, Plus) else [b]
    n_a = len(a_summands)
    n_b = len(b_summands)
    n = n_a + n_b

    total = width(Plus(a, b))

    # Wire permutation is identity (shared payload, tags are log-encoded)
    wire_perm = identity(total)

    # Build tag index permutation (forward): B indices come first, then A indices
    # A summand at old index i (i < n_a) → new index i + n_b
    # B summand at old index n_a + j (j < n_b) → new index j
    # So tp[i] = i + n_b for i < n_a, tp[n_a + j] = j for j < n_b
    tp = tuple(list(range(n_b, n)) + list(range(0, n_b)))

    # For binary case (n=2), the tag_perm (1,0) can also be expressed as
    # a tag flip on wire 0. Use tag_flips as fast path.
    if n == 2:
        return TaggedPerm(perm=wire_perm, tag_flips=frozenset({0}), tag_perm=tp)

    return TaggedPerm(perm=wire_perm, tag_flips=frozenset(), tag_perm=tp)


def twist_plus_perm_wire_only(a: Ty, b: Ty) -> WirePerm:
    """Wire permutation part of twist_plus (for compatibility).

    With Option B, this is identity since the payload is shared.
    """
    tp = twist_plus_perm(a, b)
    return tp.perm


def assoc_plus_L_perm(a: Ty, b: Ty, c: Ty) -> TaggedPerm:
    """AssocPlusL: (A ⊕ B) ⊕ C → A ⊕ (B ⊕ C) with flat log-tag encoding.

    With flattening, both types have the SAME summand list [A, B, C].
    The physical layout (tag register + shared payload) is identical.

    Therefore, AssocPlusL is IDENTITY on wires and tags.
    """
    total = width(Plus(Plus(a, b), c))
    return TaggedPerm(perm=identity(total), tag_flips=frozenset())


def assoc_plus_R_perm(a: Ty, b: Ty, c: Ty) -> TaggedPerm:
    """AssocPlusR: A ⊕ (B ⊕ C) → (A ⊕ B) ⊕ C with flat log-tag encoding.

    With flattening, both types have the SAME summand list [A, B, C].
    The physical layout (tag register + shared payload) is identical.

    Therefore, AssocPlusR is IDENTITY on wires and tags.
    """
    total = width(Plus(a, Plus(b, c)))
    return TaggedPerm(perm=identity(total), tag_flips=frozenset())


# ---------------------------------------------------------------------------
# Distributivity permutations
# ---------------------------------------------------------------------------

def dist_L_perm(a: Ty, b: Ty, c: Ty) -> TaggedPerm:
    """DistL: (A ⊕ B) ⊗ C → (A ⊗ C) ⊕ (B ⊗ C) with flat log-tag encoding.

    With Option B:
      Input (A ⊕ B) ⊗ C:  [tag_bits | payload_AB | C_wires]
        where payload_AB = max(|A|, |B|), tag_bits = ceil(log2(n))
      Output (A⊗C) ⊕ (B⊗C): [tag_bits | payload_AC_BC]
        where payload_AC_BC = max(|A|+|C|, |B|+|C|) = max(|A|,|B|) + |C|

    The tag register is preserved. The payload expands to include C.
    Physically: tag bits stay at front, AB payload stays, C wires appended.
    This is IDENTITY on wires — the layout is already correct.
    """
    total = width(Ten(Plus(a, b), c))
    return TaggedPerm(perm=identity(total), tag_flips=frozenset())


def dist_R_perm(a: Ty, b: Ty, c: Ty) -> TaggedPerm:
    """DistR: A ⊗ (B ⊕ C) → (A ⊗ B) ⊕ (A ⊗ C) with flat log-tag encoding.

    With Option B:
      Input A ⊗ (B ⊕ C):  [A_wires | tag_bits | payload_BC]
        where tag_bits = ceil(log2(n_bc)), payload_BC = max(|B|,|C|)
      Output (A⊗B) ⊕ (A⊗C): [tag_bits | payload_AB_AC]
        where payload_AB_AC = max(|A|+|B|, |A|+|C|) = |A| + max(|B|,|C|)

    The tag bits move from after A_wires to the front.
    """
    w_a = width(a)
    k = tag_width(Plus(b, c))

    total = width(Ten(a, Plus(b, c)))

    # Input positions:  [0..w_a-1=A | w_a..w_a+k-1=tag_bits | w_a+k..total-1=payload_BC]
    # Output positions: [0..k-1=tag_bits | k..k+w_a-1=A | k+w_a..total-1=payload_BC]
    new_to_old = []
    # Tag bits move to front
    new_to_old.extend(range(w_a, w_a + k))
    # A_wires move after tag bits
    new_to_old.extend(range(0, w_a))
    # Payload wires stay in order
    new_to_old.extend(range(w_a + k, total))

    perm = WirePerm(total, new_to_old)
    return TaggedPerm(perm=perm, tag_flips=frozenset())


def undist_L_perm(a: Ty, b: Ty, c: Ty) -> TaggedPerm:
    """UndistL: (A ⊗ C) ⊕ (B ⊗ C) → (A ⊕ B) ⊗ C (inverse of DistL).

    Since DistL is identity, so is UndistL.
    """
    return dist_L_perm(a, b, c)  # Identity is self-inverse


def undist_R_perm(a: Ty, b: Ty, c: Ty) -> TaggedPerm:
    """UndistR: (A ⊗ B) ⊕ (A ⊗ C) → A ⊗ (B ⊕ C) (inverse of DistR).

    Inverse of dist_R_perm: move tag bits from front back to after A_wires.
    """
    w_a = width(a)
    k = tag_width(Plus(b, c))

    total = width(Ten(a, Plus(b, c)))

    # Input positions:  [0..k-1=tag_bits | k..k+w_a-1=A | k+w_a..total-1=payload_BC]
    # Output positions: [0..w_a-1=A | w_a..w_a+k-1=tag_bits | w_a+k..total-1=payload_BC]
    new_to_old = []
    # A_wires move to front
    new_to_old.extend(range(k, k + w_a))
    # Tag bits move after A_wires
    new_to_old.extend(range(0, k))
    # Payload wires stay in order
    new_to_old.extend(range(k + w_a, total))

    perm = WirePerm(total, new_to_old)
    return TaggedPerm(perm=perm, tag_flips=frozenset())
