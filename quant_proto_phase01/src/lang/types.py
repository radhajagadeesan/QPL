# src/lang/types.py
"""Shape-tree types for the prototype language.

Purpose
-------
We represent wire bundles using a *shape tree* built from two monoidals:
  - Tensor  (⊗): parallel composition of bundles
  - Plus    (⊕): tagged sum with shared payload

Option B: Flat Log-Tag Sum Layout
----------------------------------
For an n-ary sum A₁ ⊕ A₂ ⊕ ... ⊕ Aₙ (represented as nested binary Plus),
the wire layout uses a **flat log-sized tag register + shared payload**:

  ⟦A₁ ⊕ ... ⊕ Aₙ⟧ = Q^{⊗k} ⊗ W
  k = ceil(log2(n))
  |W| = max_i(width(Aᵢ))

Layout: [tag₀ | tag₁ | ... | tag_{k-1} | payload₀ | ... | payload_{W-1}]

The k-qubit tag register stores an index i ∈ {0,...,n-1} selecting a summand.
W is a shared payload register; unused payload wires are always |0⟩.
Tag values ≥ n are unreachable and must never be produced.

Structural operations on sums compile to symbolic tag permutations
(tracked in TaggedPerm) and are lowered to gates only at emission time.

Stability
---------
Other modules may assume:
  - width(Ty) returns the number of physical wires represented by the type
  - Ty objects are immutable and comparable by structural equality
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List, Union


@dataclass(frozen=True, slots=True)
class Unit:
    """Unit type I, with width 0 (no wires).

    Used to represent trivial payloads in sum types.
    Example: Bit = Unit + Unit has width 1 (just the tag qubit).
    """
    def __str__(self) -> str:
        return "I"


@dataclass(frozen=True, slots=True)
class Q:
    """Atomic wire type (a single qubit wire)."""
    def __str__(self) -> str:
        return "Q"


@dataclass(frozen=True, slots=True)
class Ten:
    """Tensor node: left ⊗ right."""
    left: "Ty"
    right: "Ty"

    def __str__(self) -> str:
        return f"({self.left} ⊗ {self.right})"


@dataclass(frozen=True, slots=True)
class Plus:
    """Sum node: left ⊕ right (structural only in Phases 0–1)."""
    left: "Ty"
    right: "Ty"

    def __str__(self) -> str:
        return f"({self.left} ⊕ {self.right})"


@dataclass(frozen=True, slots=True)
class Dual:
    """Dual type A* (the dual of A).

    In a compact-closed category, A* is the dual object.
    For our self-dual types, A* = A physically (same width),
    but we track Dual explicitly for documentation, debugging,
    and to distinguish input/output boundaries in function types.

    The key identity: A ⊸ B ≡ A* ⊗ B.
    """
    ty: "Ty"

    def __str__(self) -> str:
        return f"{self.ty}*"


Ty = Union[Unit, Q, Ten, Plus, Dual]

# Alias for documentation: I is the traditional name for the unit type
I = Unit


def width(ty: Ty) -> int:
    """Number of physical wires represented by ty.

    For Plus types with n leaf summands, uses flat log-tag encoding:
      ceil(log2(n)) tag qubits + max(width(Aᵢ)) shared payload.
    Layout: [tag_bits | shared_payload]
    Note: summands may themselves contain Plus, which get their own tags.
    Unit type has width 0.
    """
    if isinstance(ty, Unit):
        return 0
    if isinstance(ty, Q):
        return 1
    if isinstance(ty, Ten):
        return width(ty.left) + width(ty.right)
    if isinstance(ty, Plus):
        summands = flatten_plus(ty)
        return tag_width(ty) + payload_width(ty)
    if isinstance(ty, Dual):
        return width(ty.ty)
    raise TypeError(f"Unknown Ty node: {ty!r}")


def tag_width(ty: Ty) -> int:
    """Number of tag qubits for a Plus type.

    For n leaf summands: ceil(log2(n)).
    For n=1: 0 (degenerate, no tag needed).
    For non-Plus types: 0.
    """
    if isinstance(ty, Plus):
        n = len(flatten_plus(ty))
        if n <= 1:
            return 0
        return math.ceil(math.log2(n))
    if isinstance(ty, Dual):
        return tag_width(ty.ty)
    return 0


def payload_width(ty: Ty) -> int:
    """Width of the shared payload register for a Plus type.

    For n summands: max(width(Aᵢ)).
    For non-Plus types: same as width.
    """
    if isinstance(ty, Plus):
        summands = flatten_plus(ty)
        if not summands:
            return 0
        return max(width(s) for s in summands)
    if isinstance(ty, Dual):
        return payload_width(ty.ty)
    return width(ty)


def data_width(ty: Ty) -> int:
    """Number of data wires (excluding tag qubits) for ty.

    For Plus types, this is the shared payload width.
    Useful for computing data-only permutations.
    Unit type has data_width 0.
    """
    if isinstance(ty, Unit):
        return 0
    if isinstance(ty, Q):
        return 1
    if isinstance(ty, Ten):
        return data_width(ty.left) + data_width(ty.right)
    if isinstance(ty, Plus):
        return payload_width(ty)
    if isinstance(ty, Dual):
        return data_width(ty.ty)
    raise TypeError(f"Unknown Ty node: {ty!r}")


def tag_count(ty: Ty) -> int:
    """Number of tag qubits in ty.

    For Plus types: ceil(log2(n)) where n is number of leaf summands.
    For Tensor types: sum of tag counts of children.
    """
    if isinstance(ty, Unit):
        return 0
    if isinstance(ty, Q):
        return 0
    if isinstance(ty, Ten):
        return tag_count(ty.left) + tag_count(ty.right)
    if isinstance(ty, Plus):
        return tag_width(ty)
    if isinstance(ty, Dual):
        return tag_count(ty.ty)
    raise TypeError(f"Unknown Ty node: {ty!r}")


def dual(ty: Ty) -> Ty:
    """Construct the dual type A*.

    Involutive: dual(dual(A)) = A.
    """
    if isinstance(ty, Dual):
        return ty.ty
    return Dual(ty)


def pretty(ty: Ty) -> str:
    """Pretty string for errors and logs."""
    return str(ty)


def flatten_tensor(ty: Ty) -> List[Ty]:
    """Flatten a tensor tree into a left-to-right list of factors.

    Unit types are included in the list (they contribute width 0).
    """
    if isinstance(ty, Ten):
        return flatten_tensor(ty.left) + flatten_tensor(ty.right)
    return [ty]


def flatten_plus(ty: Ty) -> List[Ty]:
    """Flatten a plus tree into a left-to-right list of summands.

    Unit types are included in the list (they contribute width 0).
    """
    if isinstance(ty, Plus):
        return flatten_plus(ty.left) + flatten_plus(ty.right)
    return [ty]
