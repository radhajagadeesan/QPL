# src/lang/types.py
"""Shape-tree types for the prototype language.

Purpose
-------
We represent wire bundles using a *shape tree* built from two monoidals:
  - Tensor  (⊗): parallel composition of bundles
  - Plus    (⊕): sum-like bundling (structural only in Phases 0–1)

In Phases 0–1, both constructors are treated structurally: they determine
wire *layout* and therefore induced permutations (assoc/twist/dist), but we do
not assign ⊕ any operational meaning yet (no measurement/control).

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
    """Number of physical wires represented by ty."""
    if isinstance(ty, Q):
        return 1
    if isinstance(ty, Ten):
        return width(ty.left) + width(ty.right)
    if isinstance(ty, Plus):
        return width(ty.left) + width(ty.right)
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
