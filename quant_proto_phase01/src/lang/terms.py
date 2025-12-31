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


@dataclass(frozen=True, slots=True)
class Seq:
    f: "Term"
    g: "Term"


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
    i: int
    ty_total: Ty


@dataclass(frozen=True, slots=True)
class S:
    i: int
    ty_total: Ty


@dataclass(frozen=True, slots=True)
class CX:
    i: int
    j: int
    ty_total: Ty


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
