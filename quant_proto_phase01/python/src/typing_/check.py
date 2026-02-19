# src/typing_/check.py
"""Lightweight runtime typechecking and (dom,cod) inference for terms."""

from __future__ import annotations

from typing import Tuple

from lang.types import Ty, Q as Q_ty, Ten, Plus, Dual, Unit, Arrow, width, pretty, dual, build_plus_tree
from lang.terms import (
    Term,
    Id, Seq, TenTerm,
    TwistTen, AssocTenL, AssocTenR,
    TwistPlus, AssocPlusL, AssocPlusR,
    DistL, DistR, UndistL, UndistR,
    Feedback,
    # Phase 0 gates
    H, S, CX,
    # Phase 4C fixed gates
    X, Y, Z, T, Tdg, Sdg, CZ, CCX, CSWAP,
    # Phase 4C parameterized gates
    Rz, Rx, Ry, Phase, CRz,
    # Controlled single-qubit gates
    CH, CS, CSdg,
    # Compact-closed structure
    Cup, Cap,
    # Higher-order constructs
    FunVar, Lam, Apply,
    # Tensor intro/elim and variables (full source language)
    Pair, LetPair, Var,
    # Case/copairing and bifunctor
    Case,
    CaseExpr,
    PlusMap,
    NPlusMap,
    PhasedPlusMap,
    PhasedControl,
    # Exponentials of structural involutions
    ExpSwap, ExpInvolution,
    # Controlled combinator
    Ctrl,
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

    # UndistL: (a⊗c) ⊕ (b⊗c) → (a⊕b)⊗c (inverse of DistL)
    if isinstance(t, UndistL):
        dom = Plus(Ten(t.a, t.c), Ten(t.b, t.c))
        cod = Ten(Plus(t.a, t.b), t.c)
        return (dom, cod)

    # UndistR: (a⊗b) ⊕ (a⊗c) → a⊗(b⊕c) (inverse of DistR)
    if isinstance(t, UndistR):
        dom = Plus(Ten(t.a, t.b), Ten(t.a, t.c))
        cod = Ten(t.a, Plus(t.b, t.c))
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
        external_width = body_width - k
        if external_width == 0:
            raise TypeCheckError("Feedback cannot have zero external wires")
        # Build type as Q^external_width
        ext_ty = Q_ty()
        for _ in range(external_width - 1):
            ext_ty = Ten(ext_ty, Q_ty())
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

    # Phase 4C three-wire fixed gate (CSWAP/Fredkin)
    if isinstance(t, CSWAP):
        n = width(t.ty_total)
        if t.c < 0 or t.c >= n or t.i < 0 or t.i >= n or t.j < 0 or t.j >= n:
            raise TypeCheckError(f"CSWAP index out of range: (c,i,j)=({t.c},{t.i},{t.j}), width={n}")
        if t.c == t.i or t.c == t.j or t.i == t.j:
            raise TypeCheckError("CSWAP requires three distinct indices.")
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

    # Ctrl: controlled combinator
    # Ctrl(f) : Bool ⊗ A → Bool ⊗ A when f : A → A
    if isinstance(t, Ctrl):
        body_dom, body_cod = type_of(t.body)
        if width(body_dom) != width(body_cod):
            raise TypeCheckError(
                f"Ctrl body must have equal domain and codomain width, "
                f"got {width(body_dom)} and {width(body_cod)}"
            )
        # Bool = I + I (control qubit)
        Bool = Plus(Unit(), Unit())
        # Ctrl(f : A → A) : Bool ⊗ A → Bool ⊗ A
        return (Ten(Bool, body_dom), Ten(Bool, body_cod))

    # Qubit encoding isomorphism: Q ↔ I + I (with implicit ancilla)
    if isinstance(t, EncodeQubit):
        # encode : Q → I + I
        return (Q_ty(), Plus(Unit(), Unit()))

    if isinstance(t, DecodeQubit):
        # decode : I + I → Q
        return (Plus(Unit(), Unit()), Q_ty())

    # Case/copairing: [f, g] : (A + B) → C
    if isinstance(t, Case):
        # left  : A → C
        # right : B → D
        # Result: (A + B) → (C + D)
        # The tag is preserved — Case is a diagonal map on the sum.
        left_dom, left_cod = type_of(t.left)
        right_dom, right_cod = type_of(t.right)

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

        # Result type: (A + B) → (C + D), tag preserved
        dom = Plus(t.ty_left, t.ty_right)
        cod = Plus(left_cod, right_cod)
        return (dom, cod)

    # PlusMap (⊕-Map): f ⊕ g : (A + B) → (C + D)
    if isinstance(t, PlusMap):
        # left  : A → C
        # right : B → D
        # Result: (A + B) → (C + D), tag preserved
        left_dom, left_cod = type_of(t.left)
        right_dom, right_cod = type_of(t.right)

        # Check that branch domains match declared types (by width)
        if width(left_dom) != width(t.ty_left):
            raise TypeCheckError(
                f"PlusMap left branch domain mismatch:\n"
                f"  declared ty_left = {pretty(t.ty_left)} (width {width(t.ty_left)})\n"
                f"  actual left dom  = {pretty(left_dom)} (width {width(left_dom)})"
            )
        if width(right_dom) != width(t.ty_right):
            raise TypeCheckError(
                f"PlusMap right branch domain mismatch:\n"
                f"  declared ty_right = {pretty(t.ty_right)} (width {width(t.ty_right)})\n"
                f"  actual right dom  = {pretty(right_dom)} (width {width(right_dom)})"
            )

        # Result type: (A + B) → (C + D), tag preserved
        dom = Plus(t.ty_left, t.ty_right)
        cod = Plus(left_cod, right_cod)
        return (dom, cod)

    # NPlusMap: n-ary coherent sum eliminator
    if isinstance(t, NPlusMap):
        n = len(t.summand_types)
        if n < 2:
            raise TypeCheckError("NPlusMap needs at least 2 summands")
        if len(t.branches) != n:
            raise TypeCheckError(
                f"NPlusMap: {n} summand types but {len(t.branches)} branches"
            )
        dom_sum = build_plus_tree(list(t.summand_types))
        cod_types = []
        for i, (st, br) in enumerate(zip(t.summand_types, t.branches)):
            d, c = type_of(br)
            if width(d) != width(st):
                raise TypeCheckError(
                    f"NPlusMap branch {i}: domain width {width(d)} "
                    f"!= summand width {width(st)}"
                )
            cod_types.append(c)
        cod_sum = build_plus_tree(cod_types)
        return (dom_sum, cod_sum)

    # PhasedPlusMap: like PlusMap but with phase on left branch
    if isinstance(t, PhasedPlusMap):
        # Same typing as PlusMap, phase is runtime parameter
        left_dom, left_cod = type_of(t.left)
        right_dom, right_cod = type_of(t.right)

        # Check that branch domains match declared types (by width)
        if width(left_dom) != width(t.ty_left):
            raise TypeCheckError(
                f"PhasedPlusMap left branch domain mismatch:\n"
                f"  declared ty_left = {pretty(t.ty_left)} (width {width(t.ty_left)})\n"
                f"  actual left dom  = {pretty(left_dom)} (width {width(left_dom)})"
            )
        if width(right_dom) != width(t.ty_right):
            raise TypeCheckError(
                f"PhasedPlusMap right branch domain mismatch:\n"
                f"  declared ty_right = {pretty(t.ty_right)} (width {width(t.ty_right)})\n"
                f"  actual right dom  = {pretty(right_dom)} (width {width(right_dom)})"
            )

        # Result type: (A + B) → (C + D), tag preserved
        dom = Plus(t.ty_left, t.ty_right)
        cod = Plus(left_cod, right_cod)
        return (dom, cod)

    # PhasedControl: phase-weighted n-ary control
    if isinstance(t, PhasedControl):
        # Type: D ⊗ A → D ⊗ A where D = dt_rep
        # phases is just runtime data, doesn't affect typing
        dom = Ten(t.dt_rep, t.a_ty)
        cod = Ten(t.dt_rep, t.a_ty)
        return (dom, cod)

    # CaseExpr: pattern-matching case with variable binding
    if isinstance(t, CaseExpr):
        # case scrut of | inl x => left | inr y => right
        # scrut : Γ → A + B
        # left  : x:A in scope, produces C
        # right : y:B in scope, produces C (for true copairing)
        scrut_dom, scrut_cod = type_of(t.scrut)

        # Scrutinee must produce a sum type
        # Check width matches A + B = ty_x + ty_y
        expected_sum = Plus(t.ty_x, t.ty_y)
        if width(scrut_cod) != width(expected_sum):
            raise TypeCheckError(
                f"CaseExpr scrutinee codomain width mismatch:\n"
                f"  expected {pretty(expected_sum)} (width {width(expected_sum)})\n"
                f"  got {pretty(scrut_cod)} (width {width(scrut_cod)})"
            )

        # Type-check branches: they operate on the payload type
        # x:A in scope for left, y:B in scope for right
        left_dom, left_cod = type_of(t.left)
        right_dom, right_cod = type_of(t.right)

        # Branch domains should include the bound variable type
        # For now, check that widths are compatible
        if width(left_dom) < width(t.ty_x):
            raise TypeCheckError(
                f"CaseExpr left branch domain too small:\n"
                f"  expected at least width {width(t.ty_x)} for x:{pretty(t.ty_x)}\n"
                f"  got {pretty(left_dom)} (width {width(left_dom)})"
            )
        if width(right_dom) < width(t.ty_y):
            raise TypeCheckError(
                f"CaseExpr right branch domain too small:\n"
                f"  expected at least width {width(t.ty_y)} for y:{pretty(t.ty_y)}\n"
                f"  got {pretty(right_dom)} (width {width(right_dom)})"
            )

        # Result type: dom(scrut) → Plus(left_cod, right_cod)
        # This preserves the tag (bifunctorial semantics)
        return (scrut_dom, Plus(left_cod, right_cod))

    # Compact-closed: Cup and Cap
    if isinstance(t, Cup):
        # η_A : I → A ⊗ A*
        return (Unit(), Ten(t.ty, dual(t.ty)))

    if isinstance(t, Cap):
        # ε_A : A* ⊗ A → I
        return (Ten(dual(t.ty), t.ty), Unit())

    # Higher-order: FunVar, Lam, Apply
    if isinstance(t, FunVar):
        # A function variable x : A → B occupies A ⊗ B wires (since A ⊸ B ≡ A* ⊗ B ≡ A ⊗ B).
        # As a term, it's identity on those wires.
        fn_ty = Ten(t.dom, t.cod)
        return (fn_ty, fn_ty)

    if isinstance(t, Lam):
        # Typing rule: Γ, x:A ⊢ body:B  ⇒  Γ ⊢ λx.body : A ⊸ B
        #
        # The body is compiled with x bound to width(A) extra input wires.
        # Body type: (Γ ⊗ A) → B
        # Lambda type: Γ → (A ⊸ B) where A ⊸ B = Arrow(A, B)
        #
        # The domain is the body's domain MINUS the x-binding (width(A) wires).
        # The codomain is Arrow(dom, cod) exposing both A-slot and B-slot.
        body_dom, body_cod = type_of(t.body)

        # body_dom should be (Γ ⊗ A), we extract Γ by removing A wires
        # For now, we assume body_dom includes the x binding
        # Lambda's domain is body_dom minus width(dom) wires
        wA = width(t.dom)
        body_width = width(body_dom)

        if body_width < wA:
            raise TypeCheckError(
                f"Lam body domain too small: body_dom width {body_width}, "
                f"but x:A has width {wA}"
            )

        # The lambda's codomain is Arrow(A, B) = A ⊸ B
        lam_cod = Arrow(t.dom, t.cod)

        # The lambda's domain is the context Γ (body_dom minus the x:A part)
        # For simplicity, we compute based on widths
        gamma_width = body_width - wA
        if gamma_width == 0:
            lam_dom = Unit()
        else:
            # Build a tensor type of appropriate width
            # This is a simplification - ideally we'd track the actual type
            lam_dom = Q_ty()
            for _ in range(gamma_width - 1):
                lam_dom = Ten(lam_dom, Q_ty())

        return (lam_dom, lam_cod)

    if isinstance(t, Apply):
        # Typing rule: Γ₁ ⊢ f:A⊸B   Γ₂ ⊢ u:A  ⇒  Γ₁⊗Γ₂ ⊢ f u : B
        #
        # f produces Arrow(A, B) = [A_slot | B_slot] wires
        # arg produces A wires
        # Apply connects arg's output to f's A_slot (boundary splicing)
        # Result is B (the B_slot wires)
        f_dom, f_cod = type_of(t.f)
        arg_dom, arg_cod = type_of(t.arg)

        # f's codomain must be Arrow(A, B)
        if not isinstance(f_cod, Arrow):
            raise TypeCheckError(
                f"Apply expects function type, got {pretty(f_cod)}"
            )

        A = f_cod.dom  # argument type (domain of the function)
        B = f_cod.cod  # result type (codomain of the function)

        # arg's codomain must match A (by width)
        if width(arg_cod) != width(A):
            raise TypeCheckError(
                f"Apply argument type mismatch:\n"
                f"  expected {pretty(A)} (width {width(A)})\n"
                f"  got {pretty(arg_cod)} (width {width(arg_cod)})"
            )

        # Apply's domain is Γ₁ ⊗ Γ₂
        if isinstance(f_dom, Unit) and isinstance(arg_dom, Unit):
            apply_dom = Unit()
        elif isinstance(f_dom, Unit):
            apply_dom = arg_dom
        elif isinstance(arg_dom, Unit):
            apply_dom = f_dom
        else:
            apply_dom = Ten(f_dom, arg_dom)

        # Apply's codomain is B (the result type from the Arrow)
        return (apply_dom, B)

    # Full source language: Pair, LetPair, Var
    if isinstance(t, Var):
        # Variable reference: x : A (identity on A wires)
        return (t.ty, t.ty)

    if isinstance(t, Pair):
        # Tensor introduction: (t, u) : A ⊗ B
        # Given t : A (from Γ1) and u : B (from Γ2) with disjoint contexts,
        # produces (t, u) : A ⊗ B (from Γ1 ⊎ Γ2).
        fst_dom, fst_cod = type_of(t.fst)
        snd_dom, snd_cod = type_of(t.snd)
        return (Ten(fst_dom, snd_dom), Ten(fst_cod, snd_cod))

    if isinstance(t, LetPair):
        # Tensor elimination: let (x, y) = t in u
        # t : A ⊗ B (t.pair produces A⊗B)
        # x : A, y : B in u : C
        # Result: let (x,y) = t in u : C
        pair_dom, pair_cod = type_of(t.pair)

        # The pair's codomain should be A ⊗ B = ty_x ⊗ ty_y
        expected_pair_ty = Ten(t.ty_x, t.ty_y)
        if width(pair_cod) != width(expected_pair_ty):
            raise TypeCheckError(
                f"LetPair pair codomain width mismatch:\n"
                f"  pair codomain = {pretty(pair_cod)} (width {width(pair_cod)})\n"
                f"  expected = {pretty(expected_pair_ty)} (width {width(expected_pair_ty)})"
            )

        # Body type depends on the body term itself
        body_dom, body_cod = type_of(t.body)

        # The full term's domain is the context that t.pair needs plus body's extra context
        # For now we use width-based composition
        # domain: what the pair term needs (pair_dom)
        # codomain: what the body produces (body_cod)
        return (pair_dom, body_cod)

    raise TypeCheckError(f"Unknown term node: {t!r}")


def assert_well_typed(t: Term) -> None:
    """Raise TypeCheckError if t is ill-typed."""
    _ = type_of(t)
