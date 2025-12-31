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

Phase 0–1 note on distributivity
--------------------------------
Distributivity for (⊕,⊗) is *not* a plain permutation on flat wires because it
would require copying/shared wires. We'll typecheck dist maps now, but delay
compilation until we add a sum-aware layout model (Phase 2).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List

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


def block_swap(m: int, n: int) -> WirePerm:
    total = m + n
    new_to_old = list(range(m, total)) + list(range(0, m))
    return WirePerm(total, new_to_old)


def twist_tensor_perm(a: Ty, b: Ty) -> WirePerm:
    return block_swap(width(a), width(b))


def assoc_tensor_L_perm(a: Ty, b: Ty, c: Ty) -> WirePerm:
    # identity on flat wires
    n = width(Ten(Ten(a, b), c))
    return identity(n)


def assoc_tensor_R_perm(a: Ty, b: Ty, c: Ty) -> WirePerm:
    n = width(Ten(a, Ten(b, c)))
    return identity(n)


def twist_plus_perm(a: Ty, b: Ty) -> WirePerm:
    return block_swap(width(a), width(b))


def assoc_plus_L_perm(a: Ty, b: Ty, c: Ty) -> WirePerm:
    n = width(Plus(Plus(a, b), c))
    return identity(n)


def assoc_plus_R_perm(a: Ty, b: Ty, c: Ty) -> WirePerm:
    n = width(Plus(a, Plus(b, c)))
    return identity(n)
