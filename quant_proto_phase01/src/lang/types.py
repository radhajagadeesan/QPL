# src/lang/types.py
"""Shape-tree types for the prototype language.

Purpose
-------
We represent wire bundles using a *shape tree* built from two monoidals:
  - Tensor  (⊗): parallel composition of bundles
  - Plus    (⊕): tagged sum with shared data wires

Tagged Sum Layout
-----------------
For A ⊕ B, the wire layout is:
  [tag | A_wires | B_wires]

where:
  - tag is a single qubit indicating which branch is "active"
  - A_wires and B_wires are the data wires for each branch
  - width(A ⊕ B) = 1 + width(A) + width(B)

This encoding enables distributivity as a pure permutation:
  DistL : (A⊕B)⊗C → (A⊗C)⊕(B⊗C) is identity on wires
  DistR : A⊗(B⊕C) → (A⊗B)⊕(A⊗C) rearranges to move tag to front

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


Ty = Union[Q, Ten, Plus]


def width(ty: Ty) -> int:
    """Number of physical wires represented by ty.

    For Plus types, includes 1 tag qubit plus data wires from both branches.
    Layout for A ⊕ B: [tag | A_wires | B_wires]
    """
    if isinstance(ty, Q):
        return 1
    if isinstance(ty, Ten):
        return width(ty.left) + width(ty.right)
    if isinstance(ty, Plus):
        # Tagged layout: 1 tag qubit + all data wires
        return 1 + width(ty.left) + width(ty.right)
    raise TypeError(f"Unknown Ty node: {ty!r}")


def data_width(ty: Ty) -> int:
    """Number of data wires (excluding tag qubits) for ty.

    For Plus types, this is width(left) + width(right) without the tag.
    Useful for computing data-only permutations.
    """
    if isinstance(ty, Q):
        return 1
    if isinstance(ty, Ten):
        return data_width(ty.left) + data_width(ty.right)
    if isinstance(ty, Plus):
        return data_width(ty.left) + data_width(ty.right)
    raise TypeError(f"Unknown Ty node: {ty!r}")


def tag_count(ty: Ty) -> int:
    """Number of tag qubits in ty (one per Plus node)."""
    if isinstance(ty, Q):
        return 0
    if isinstance(ty, Ten):
        return tag_count(ty.left) + tag_count(ty.right)
    if isinstance(ty, Plus):
        return 1 + tag_count(ty.left) + tag_count(ty.right)
    raise TypeError(f"Unknown Ty node: {ty!r}")


def pretty(ty: Ty) -> str:
    """Pretty string for errors and logs."""
    return str(ty)


def flatten_tensor(ty: Ty) -> List[Ty]:
    """Flatten a tensor tree into a left-to-right list of factors."""
    if isinstance(ty, Ten):
        return flatten_tensor(ty.left) + flatten_tensor(ty.right)
    return [ty]


def flatten_plus(ty: Ty) -> List[Ty]:
    """Flatten a plus tree into a left-to-right list of summands."""
    if isinstance(ty, Plus):
        return flatten_plus(ty.left) + flatten_plus(ty.right)
    return [ty]
