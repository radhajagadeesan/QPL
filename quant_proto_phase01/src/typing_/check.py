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
    Feedback,
    # Phase 0 gates
    H, S, CX,
    # Phase 4C fixed gates
    X, Y, Z, T, Tdg, Sdg, CZ, CCX,
    # Phase 4C parameterized gates
    Rz, Rx, Ry, Phase, CRz,
    # Controlled single-qubit gates
    CH, CS, CSdg,
    # Case/copairing
    Case,
    # Exponentials of structural involutions
    ExpSwap, ExpInvolution,
    # Qubit encoding isomorphism
    EncodeQubit, DecodeQubit,
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

    if isinstance(t, Feedback):
        # Feedback_k(body) : A → B
        # where body : (A ⊗ X) → (B ⊗ X) with width(X) = k
        body_dom, body_cod = type_of(t.body)
        k = t.k
        body_width = width(body_dom)
        if width(body_cod) != body_width:
            raise TypeCheckError(
                f"Feedback body must have equal input/output width, got "
                f"dom width {body_width}, cod width {width(body_cod)}"
            )
        if k < 0 or k > body_width:
            raise TypeCheckError(
                f"Feedback loop size k={k} out of range for body width {body_width}"
            )
        # The external type has width = body_width - k
        # We return a "synthetic" type based on width
        # For Phase 3, we use a width-based approach:
        # dom/cod of Feedback is (body_width - k) wires
        from lang.types import Q
        external_width = body_width - k
        if external_width == 0:
            raise TypeCheckError("Feedback cannot have zero external wires")
        # Build type as Q^external_width
        ext_ty = Q()
        for _ in range(external_width - 1):
            ext_ty = Ten(ext_ty, Q())
        return (ext_ty, ext_ty)

    # Phase 0 single-wire gates
    if isinstance(t, (H, S)):
        n = width(t.ty_total)
        if t.i < 0 or t.i >= n:
            raise TypeCheckError(f"Gate index out of range: i={t.i}, width={n}")
        return (t.ty_total, t.ty_total)

    # Phase 0 two-wire gate
    if isinstance(t, CX):
        n = width(t.ty_total)
        if t.i < 0 or t.i >= n or t.j < 0 or t.j >= n:
            raise TypeCheckError(f"CX index out of range: (i,j)=({t.i},{t.j}), width={n}")
        if t.i == t.j:
            raise TypeCheckError("CX requires distinct control/target indices (i != j).")
        return (t.ty_total, t.ty_total)

    # Phase 4C single-wire fixed gates
    if isinstance(t, (X, Y, Z, T, Tdg, Sdg)):
        n = width(t.ty_total)
        if t.i < 0 or t.i >= n:
            raise TypeCheckError(f"Gate index out of range: i={t.i}, width={n}")
        return (t.ty_total, t.ty_total)

    # Phase 4C two-wire fixed gate (CZ)
    if isinstance(t, CZ):
        n = width(t.ty_total)
        if t.i < 0 or t.i >= n or t.j < 0 or t.j >= n:
            raise TypeCheckError(f"CZ index out of range: (i,j)=({t.i},{t.j}), width={n}")
        if t.i == t.j:
            raise TypeCheckError("CZ requires distinct indices (i != j).")
        return (t.ty_total, t.ty_total)

    # Phase 4C three-wire fixed gate (CCX/Toffoli)
    if isinstance(t, CCX):
        n = width(t.ty_total)
        if t.i < 0 or t.i >= n or t.j < 0 or t.j >= n or t.k < 0 or t.k >= n:
            raise TypeCheckError(f"CCX index out of range: (i,j,k)=({t.i},{t.j},{t.k}), width={n}")
        if t.i == t.j or t.j == t.k or t.i == t.k:
            raise TypeCheckError("CCX requires three distinct indices.")
        return (t.ty_total, t.ty_total)

    # Phase 4C single-wire parameterized gates
    if isinstance(t, (Rz, Rx, Ry, Phase)):
        n = width(t.ty_total)
        if t.i < 0 or t.i >= n:
            raise TypeCheckError(f"Gate index out of range: i={t.i}, width={n}")
        return (t.ty_total, t.ty_total)

    # Phase 4C two-wire parameterized gate (CRz)
    if isinstance(t, CRz):
        n = width(t.ty_total)
        if t.i < 0 or t.i >= n or t.j < 0 or t.j >= n:
            raise TypeCheckError(f"CRz index out of range: (i,j)=({t.i},{t.j}), width={n}")
        if t.i == t.j:
            raise TypeCheckError("CRz requires distinct control/target indices (i != j).")
        return (t.ty_total, t.ty_total)

    # Controlled single-qubit gates (for quantum case expressions)
    if isinstance(t, (CH, CS, CSdg)):
        n = width(t.ty_total)
        if t.i < 0 or t.i >= n or t.j < 0 or t.j >= n:
            raise TypeCheckError(f"Controlled gate index out of range: (i,j)=({t.i},{t.j}), width={n}")
        if t.i == t.j:
            raise TypeCheckError("Controlled gate requires distinct control/target indices (i != j).")
        return (t.ty_total, t.ty_total)

    # ExpSwap: two-wire parameterized gate
    if isinstance(t, ExpSwap):
        n = width(t.ty_total)
        if t.i < 0 or t.i >= n or t.j < 0 or t.j >= n:
            raise TypeCheckError(f"ExpSwap index out of range: (i,j)=({t.i},{t.j}), width={n}")
        if t.i == t.j:
            raise TypeCheckError("ExpSwap requires distinct wire indices (i != j).")
        return (t.ty_total, t.ty_total)

    # ExpInvolution: parameterized structural involution
    if isinstance(t, ExpInvolution):
        # The body must be a structural term (checked at compile time)
        # Type is the same as the body's type
        body_dom, body_cod = type_of(t.body)
        if width(body_dom) != width(body_cod):
            raise TypeCheckError(
                f"ExpInvolution body must have equal domain and codomain width, "
                f"got {width(body_dom)} and {width(body_cod)}"
            )
        # ExpInvolution preserves the type (since exp(iθP) : A → A when P : A → A)
        return (body_dom, body_cod)

    # Qubit encoding isomorphism: Q ↔ I + I (with implicit ancilla)
    if isinstance(t, EncodeQubit):
        from lang.types import Q, Unit
        # encode : Q → I + I
        return (Q(), Plus(Unit(), Unit()))

    if isinstance(t, DecodeQubit):
        from lang.types import Q, Unit
        # decode : I + I → Q
        return (Plus(Unit(), Unit()), Q())

    # Case/copairing: [f, g] : (A + B) → C
    if isinstance(t, Case):
        # left  : A → C
        # right : B → C
        # Result: (A + B) → C
        left_dom, left_cod = type_of(t.left)
        right_dom, right_cod = type_of(t.right)

        # Check branches have matching codomains (by width)
        if width(left_cod) != width(right_cod):
            raise TypeCheckError(
                f"Case branches have different codomain widths:\n"
                f"  left  : {pretty(left_dom)} → {pretty(left_cod)} (cod width {width(left_cod)})\n"
                f"  right : {pretty(right_dom)} → {pretty(right_cod)} (cod width {width(right_cod)})"
            )

        # Check that branch domains match declared types (by width)
        if width(left_dom) != width(t.ty_left):
            raise TypeCheckError(
                f"Case left branch domain mismatch:\n"
                f"  declared ty_left = {pretty(t.ty_left)} (width {width(t.ty_left)})\n"
                f"  actual left dom  = {pretty(left_dom)} (width {width(left_dom)})"
            )
        if width(right_dom) != width(t.ty_right):
            raise TypeCheckError(
                f"Case right branch domain mismatch:\n"
                f"  declared ty_right = {pretty(t.ty_right)} (width {width(t.ty_right)})\n"
                f"  actual right dom  = {pretty(right_dom)} (width {width(right_dom)})"
            )

        # Result type: (A + B) → C
        dom = Plus(t.ty_left, t.ty_right)
        cod = left_cod  # Both branches have same codomain (checked above)
        return (dom, cod)

    raise TypeCheckError(f"Unknown term node: {t!r}")


def assert_well_typed(t: Term) -> None:
    """Raise TypeCheckError if t is ill-typed."""
    _ = type_of(t)
