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


# -- Feedback (Phase 3 GOI)

@dataclass(frozen=True, slots=True)
class Feedback:
    """Feedback_k(body) : explicit GOI feedback operator.

    If body : (A ⊗ X) → (B ⊗ X) with width(X) = k,
    then Feedback_k(body) : A → B.

    This is the ONLY construct that may introduce cycles.
    Feedback is explicit and fenced—no implicit GOI elsewhere.
    """
    k: int           # number of loop wires
    body: "Term"     # the body term


# -- Gate terms (Phase 0 minimal + Phase 4C extensions)

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


# -- Phase 4C: Additional fixed gates

@dataclass(frozen=True, slots=True)
class X:
    """Pauli-X gate on wire i."""
    i: int = 0
    ty_total: Ty = None  # type: ignore

    def __post_init__(self):
        if self.ty_total is None:
            object.__setattr__(self, 'ty_total', Ten(Q(), Q()))


@dataclass(frozen=True, slots=True)
class Y:
    """Pauli-Y gate on wire i."""
    i: int = 0
    ty_total: Ty = None  # type: ignore

    def __post_init__(self):
        if self.ty_total is None:
            object.__setattr__(self, 'ty_total', Ten(Q(), Q()))


@dataclass(frozen=True, slots=True)
class Z:
    """Pauli-Z gate on wire i."""
    i: int = 0
    ty_total: Ty = None  # type: ignore

    def __post_init__(self):
        if self.ty_total is None:
            object.__setattr__(self, 'ty_total', Ten(Q(), Q()))


@dataclass(frozen=True, slots=True)
class T:
    """T gate (π/4 phase) on wire i."""
    i: int = 0
    ty_total: Ty = None  # type: ignore

    def __post_init__(self):
        if self.ty_total is None:
            object.__setattr__(self, 'ty_total', Ten(Q(), Q()))


@dataclass(frozen=True, slots=True)
class Tdg:
    """T-dagger gate (inverse of T) on wire i."""
    i: int = 0
    ty_total: Ty = None  # type: ignore

    def __post_init__(self):
        if self.ty_total is None:
            object.__setattr__(self, 'ty_total', Ten(Q(), Q()))


@dataclass(frozen=True, slots=True)
class Sdg:
    """S-dagger gate (inverse of S) on wire i."""
    i: int = 0
    ty_total: Ty = None  # type: ignore

    def __post_init__(self):
        if self.ty_total is None:
            object.__setattr__(self, 'ty_total', Ten(Q(), Q()))


@dataclass(frozen=True, slots=True)
class CZ:
    """Controlled-Z gate with control i and target j."""
    i: int = 0
    j: int = 1
    ty_total: Ty = None  # type: ignore

    def __post_init__(self):
        if self.ty_total is None:
            object.__setattr__(self, 'ty_total', Ten(Q(), Q()))


@dataclass(frozen=True, slots=True)
class CH:
    """Controlled-Hadamard gate with control i and target j.

    Used for quantum control in case expressions on sum types.
    """
    i: int = 0
    j: int = 1
    ty_total: Ty = None  # type: ignore

    def __post_init__(self):
        if self.ty_total is None:
            object.__setattr__(self, 'ty_total', Ten(Q(), Q()))


@dataclass(frozen=True, slots=True)
class CS:
    """Controlled-S gate with control i and target j.

    Used for quantum control in case expressions on sum types.
    """
    i: int = 0
    j: int = 1
    ty_total: Ty = None  # type: ignore

    def __post_init__(self):
        if self.ty_total is None:
            object.__setattr__(self, 'ty_total', Ten(Q(), Q()))


@dataclass(frozen=True, slots=True)
class CSdg:
    """Controlled-S-dagger gate with control i and target j."""
    i: int = 0
    j: int = 1
    ty_total: Ty = None  # type: ignore

    def __post_init__(self):
        if self.ty_total is None:
            object.__setattr__(self, 'ty_total', Ten(Q(), Q()))


@dataclass(frozen=True, slots=True)
class CCX:
    """Toffoli (CCX) gate with controls i, j and target k."""
    i: int = 0
    j: int = 1
    k: int = 2
    ty_total: Ty = None  # type: ignore

    def __post_init__(self):
        if self.ty_total is None:
            object.__setattr__(self, 'ty_total', Ten(Ten(Q(), Q()), Q()))


# -- Phase 4C: Parameterized gates

@dataclass(frozen=True, slots=True)
class Rz:
    """Rz(θ) rotation around Z-axis on wire i.

    θ is in radians.
    """
    theta: float
    i: int = 0
    ty_total: Ty = None  # type: ignore

    def __post_init__(self):
        if self.ty_total is None:
            object.__setattr__(self, 'ty_total', Ten(Q(), Q()))


@dataclass(frozen=True, slots=True)
class Rx:
    """Rx(θ) rotation around X-axis on wire i.

    θ is in radians.
    """
    theta: float
    i: int = 0
    ty_total: Ty = None  # type: ignore

    def __post_init__(self):
        if self.ty_total is None:
            object.__setattr__(self, 'ty_total', Ten(Q(), Q()))


@dataclass(frozen=True, slots=True)
class Ry:
    """Ry(θ) rotation around Y-axis on wire i.

    θ is in radians.
    """
    theta: float
    i: int = 0
    ty_total: Ty = None  # type: ignore

    def __post_init__(self):
        if self.ty_total is None:
            object.__setattr__(self, 'ty_total', Ten(Q(), Q()))


@dataclass(frozen=True, slots=True)
class Phase:
    """Global phase gate e^{iφ} on wire i.

    φ is in radians. This applies a phase rotation.
    """
    phi: float
    i: int = 0
    ty_total: Ty = None  # type: ignore

    def __post_init__(self):
        if self.ty_total is None:
            object.__setattr__(self, 'ty_total', Ten(Q(), Q()))


@dataclass(frozen=True, slots=True)
class CRz:
    """Controlled-Rz(θ) with control i and target j.

    θ is in radians.
    """
    theta: float
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
    Feedback,
    # Phase 0 gates
    H, S, CX,
    # Phase 4C fixed gates
    X, Y, Z, T, Tdg, Sdg, CZ, CCX,
    # Phase 4C parameterized gates
    Rz, Rx, Ry, Phase, CRz,
    # Controlled single-qubit gates (for quantum case expressions)
    CH, CS, CSdg,
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
