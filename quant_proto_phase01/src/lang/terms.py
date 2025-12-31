# src/lang/terms.py
"""AST for the prototype source language.

Design goal
-----------
Keep the AST *self-describing*: structural isomorphisms (twist/assoc/dist) carry
their intended type parameters so that typechecking is simple and errors are
readable.

Phases 0–1
----------
- Structural isos for both ⊗ and ⊕, plus distributivity maps.
- Gates are first-order and typed by a whole-program "ambient" type ty_total.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Union

from lang.types import Ty, Ten, Plus, Q


@dataclass(frozen=True, slots=True)
class Id:
    ty: Ty


class Seq:
    """Sequential composition of terms.

    Can be constructed with 2 or more terms:
        Seq(f, g)        # two terms
        Seq(f, g, h)     # three terms -> Seq(f, Seq(g, h))
        Seq(f, g, h, i)  # four terms  -> Seq(f, Seq(g, Seq(h, i)))
    """
    __slots__ = ('f', 'g')

    def __init__(self, f: "Term", g: "Term", *rest: "Term"):
        if rest:
            # Variadic: Seq(a, b, c, ...) -> Seq(a, Seq(b, c, ...))
            g = Seq(g, *rest)
        object.__setattr__(self, 'f', f)
        object.__setattr__(self, 'g', g)

    def __setattr__(self, name, value):
        raise AttributeError("Seq is immutable")

    def __hash__(self):
        return hash((self.f, self.g))

    def __eq__(self, other):
        if not isinstance(other, Seq):
            return NotImplemented
        return self.f == other.f and self.g == other.g

    def __repr__(self):
        return f"Seq({self.f!r}, {self.g!r})"


@dataclass(frozen=True, slots=True)
class TenTerm:
    """Parallel composition of terms: f ⊗ g."""
    f: "Term"
    g: "Term"


# -- Structural isos for tensor (⊗)

@dataclass(frozen=True, slots=True)
class TwistTen:
    """twist⊗_{a,b} : a⊗b -> b⊗a"""
    a: Ty
    b: Ty


@dataclass(frozen=True, slots=True)
class AssocTenL:
    """assoc⊗_L : (a⊗b)⊗c -> a⊗(b⊗c)"""
    a: Ty
    b: Ty
    c: Ty


@dataclass(frozen=True, slots=True)
class AssocTenR:
    """assoc⊗_R : a⊗(b⊗c) -> (a⊗b)⊗c"""
    a: Ty
    b: Ty
    c: Ty


# -- Structural isos for sum (⊕) (structural only in Phases 0–1)

@dataclass(frozen=True, slots=True)
class TwistPlus:
    """twist⊕_{a,b} : a⊕b -> b⊕a"""
    a: Ty
    b: Ty


@dataclass(frozen=True, slots=True)
class AssocPlusL:
    """assoc⊕_L : (a⊕b)⊕c -> a⊕(b⊕c)"""
    a: Ty
    b: Ty
    c: Ty


@dataclass(frozen=True, slots=True)
class AssocPlusR:
    """assoc⊕_R : a⊕(b⊕c) -> (a⊕b)⊕c"""
    a: Ty
    b: Ty
    c: Ty


# -- Distributivity (structural only in Phases 0–1)

@dataclass(frozen=True, slots=True)
class DistL:
    """dist_L : (a⊕b)⊗c -> (a⊗c) ⊕ (b⊗c)"""
    a: Ty
    b: Ty
    c: Ty


@dataclass(frozen=True, slots=True)
class DistR:
    """dist_R : a⊗(b⊕c) -> (a⊗b) ⊕ (a⊗c)"""
    a: Ty
    b: Ty
    c: Ty


# -- Gate terms (Phase 0 minimal)

@dataclass(frozen=True, slots=True)
class H:
    """Hadamard gate on wire i.

    Defaults: i=0, ty_total=Ten(Q(), Q()) for 2-qubit context.
    """
    i: int = 0
    ty_total: Ty = None  # type: ignore

    def __post_init__(self):
        if self.ty_total is None:
            object.__setattr__(self, 'ty_total', Ten(Q(), Q()))


@dataclass(frozen=True, slots=True)
class S:
    """S (phase) gate on wire i.

    Defaults: i=0, ty_total=Ten(Q(), Q()) for 2-qubit context.
    """
    i: int = 0
    ty_total: Ty = None  # type: ignore

    def __post_init__(self):
        if self.ty_total is None:
            object.__setattr__(self, 'ty_total', Ten(Q(), Q()))


@dataclass(frozen=True, slots=True)
class CX:
    """Controlled-X gate with control i and target j.

    Defaults: i=0, j=1, ty_total=Ten(Q(), Q()) for standard 2-qubit context.
    """
    i: int = 0
    j: int = 1
    ty_total: Ty = None  # type: ignore

    def __post_init__(self):
        if self.ty_total is None:
            object.__setattr__(self, 'ty_total', Ten(Q(), Q()))


Term = Union[
    Id, Seq, TenTerm,
    TwistTen, AssocTenL, AssocTenR,
    TwistPlus, AssocPlusL, AssocPlusR,
    DistL, DistR,
    H, S, CX,
]


def q() -> Ty:
    """Atomic Q wire."""
    return Q()


def ten(a: Ty, b: Ty) -> Ty:
    return Ten(a, b)


def plus(a: Ty, b: Ty) -> Ty:
    return Plus(a, b)


# Aliases for alternative naming conventions used in tests
TensorTwist = TwistTen
TensorAssocL = AssocTenL
TensorAssocR = AssocTenR
SumTwist = TwistPlus
SumAssocL = AssocPlusL
SumAssocR = AssocPlusR
