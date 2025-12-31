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


@dataclass(frozen=True, slots=True)
class WirePerm:
    n: int
    new_to_old: List[int]

    def __post_init__(self) -> None:
        if len(self.new_to_old) != self.n:
            raise ValueError("WirePerm length mismatch")
        if sorted(self.new_to_old) != list(range(self.n)):
            raise ValueError(f"WirePerm is not a permutation: {self.new_to_old}")

    def apply_new_to_old(self, i_new: int) -> int:
        return self.new_to_old[i_new]


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
