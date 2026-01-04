# src/lang/types.py
"""Shape-tree types for the prototype language.

Purpose
-------
We represent wire bundles using a *shape tree* built from two monoidals:
  - Tensor  (⊗): parallel composition of bundles
  - Plus    (⊕): tagged sum with shared data wires

One-Hot Leaf-Tag Sum Layout
---------------------------
For an n-ary sum A₁ ⊕ A₂ ⊕ ... ⊕ Aₙ (represented as nested binary Plus),
the wire layout uses **one-hot encoding**:

  [t₁ | t₂ | ... | tₙ | A₁_wires | A₂_wires | ... | Aₙ_wires]

where:
  - t₁...tₙ are one-hot tag wires (exactly one is 1)
  - Aᵢ_wires are the data wires for each summand
  - width(sum) = n + sum(width(Aᵢ))

Key invariant:
  ALL structural operations on sums compile to pure wire permutations.
  No tag bit flips (X gates) are ever required.

This encoding enables:
  - TwistPlus: pure permutation (swap tags and payloads)
  - AssocPlusL/R: identity (same physical layout after flattening)
  - DistL: identity on wires (with shared tensor semantics)
  - DistR: pure permutation (move tags to front)
  - Involutions: all structural involutions are WirePerms with π² = id

Stability
---------
Other modules may assume:
  - width(Ty) returns the number of physical wires represented by the type
  - Ty objects are immutable and comparable by structural equality
"""

from __future__ import annotations

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


Ty = Union[Unit, Q, Ten, Plus]


def width(ty: Ty) -> int:
    """Number of physical wires represented by ty.

    For Plus types with n leaf summands, uses one-hot encoding:
      n tag wires + sum of summand widths.
    Layout for A₁ ⊕ ... ⊕ Aₙ: [t₁ | ... | tₙ | A₁_wires | ... | Aₙ_wires]
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
        # One-hot leaf-tag encoding: n tags for n summands + their widths
        # Note: summands are non-Plus types (flattened), but may contain
        # nested Plus (e.g., Ten(A, Plus(B, C))) which get their own tags.
        summands = flatten_plus(ty)
        n_tags = len(summands)
        payload = sum(width(s) for s in summands)
        return n_tags + payload
    raise TypeError(f"Unknown Ty node: {ty!r}")


def data_width(ty: Ty) -> int:
    """Number of data wires (excluding tag qubits) for ty.

    For Plus types, this is width(left) + width(right) without the tag.
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
        return data_width(ty.left) + data_width(ty.right)
    raise TypeError(f"Unknown Ty node: {ty!r}")


def tag_count(ty: Ty) -> int:
    """Number of tag qubits in ty (one-hot: n tags for n leaf summands)."""
    if isinstance(ty, Unit):
        return 0
    if isinstance(ty, Q):
        return 0
    if isinstance(ty, Ten):
        return tag_count(ty.left) + tag_count(ty.right)
    if isinstance(ty, Plus):
        # One-hot encoding: n tags for n leaf summands
        return len(flatten_plus(ty))
    raise TypeError(f"Unknown Ty node: {ty!r}")


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
