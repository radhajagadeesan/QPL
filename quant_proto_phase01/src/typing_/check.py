# src/typing_/check.py
"""Lightweight runtime typechecking and (dom,cod) inference for terms."""

from __future__ import annotations

from typing import Tuple

from lang.types import Ty, Ten, Plus, width, pretty
from lang.terms import (
    Term,
    Id, Seq, TenTerm,
    TwistTen, AssocTenL, AssocTenR,
    TwistPlus, AssocPlusL, AssocPlusR,
    DistL, DistR,
    H, S, CX,
)


class TypeCheckError(TypeError):
    """Raised when a term is ill-typed."""

DomCod = Tuple[Ty, Ty]


def type_of(t: Term) -> DomCod:
    """Return (dom, cod) for term t; raise TypeCheckError if ill-typed."""
    if isinstance(t, Id):
        return (t.ty, t.ty)

    if isinstance(t, Seq):
        d1, c1 = type_of(t.f)
        d2, c2 = type_of(t.g)
        # Use width-based comparison to allow structural transforms to compose with gates
        if width(c1) != width(d2):
            raise TypeCheckError(
                "Seq type mismatch (width):\n"
                f"  cod(f) = {pretty(c1)} (width {width(c1)})\n"
                f"  dom(g) = {pretty(d2)} (width {width(d2)})"
            )
        return (d1, c2)

    if isinstance(t, TenTerm):
        d1, c1 = type_of(t.f)
        d2, c2 = type_of(t.g)
        return (Ten(d1, d2), Ten(c1, c2))

    if isinstance(t, TwistTen):
        return (Ten(t.a, t.b), Ten(t.b, t.a))

    if isinstance(t, AssocTenL):
        return (Ten(Ten(t.a, t.b), t.c), Ten(t.a, Ten(t.b, t.c)))

    if isinstance(t, AssocTenR):
        return (Ten(t.a, Ten(t.b, t.c)), Ten(Ten(t.a, t.b), t.c))

    if isinstance(t, TwistPlus):
        return (Plus(t.a, t.b), Plus(t.b, t.a))

    if isinstance(t, AssocPlusL):
        return (Plus(Plus(t.a, t.b), t.c), Plus(t.a, Plus(t.b, t.c)))

    if isinstance(t, AssocPlusR):
        return (Plus(t.a, Plus(t.b, t.c)), Plus(Plus(t.a, t.b), t.c))

    if isinstance(t, DistL):
        dom = Ten(Plus(t.a, t.b), t.c)
        cod = Plus(Ten(t.a, t.c), Ten(t.b, t.c))
        return (dom, cod)

    if isinstance(t, DistR):
        dom = Ten(t.a, Plus(t.b, t.c))
        cod = Plus(Ten(t.a, t.b), Ten(t.a, t.c))
        return (dom, cod)

    if isinstance(t, (H, S)):
        n = width(t.ty_total)
        if t.i < 0 or t.i >= n:
            raise TypeCheckError(f"Gate index out of range: i={t.i}, width={n}")
        return (t.ty_total, t.ty_total)

    if isinstance(t, CX):
        n = width(t.ty_total)
        if t.i < 0 or t.i >= n or t.j < 0 or t.j >= n:
            raise TypeCheckError(f"CX index out of range: (i,j)=({t.i},{t.j}), width={n}")
        if t.i == t.j:
            raise TypeCheckError("CX requires distinct control/target indices (i != j).")
        return (t.ty_total, t.ty_total)

    raise TypeCheckError(f"Unknown term node: {t!r}")


def assert_well_typed(t: Term) -> None:
    """Raise TypeCheckError if t is ill-typed."""
    _ = type_of(t)
