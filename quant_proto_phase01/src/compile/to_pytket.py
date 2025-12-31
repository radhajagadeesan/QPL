# src/compile/to_pytket.py
"""Compiler: Source Term ==> pytket Circuit, using permutations as metadata."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from pytket.circuit import Circuit

from lang.terms import (
    Term, Id, Seq,
    TwistTen, AssocTenL, AssocTenR,
    TwistPlus, AssocPlusL, AssocPlusR,
    DistL, DistR,
    H, S, CX,
)
from lang.types import width
from typing_.check import type_of, assert_well_typed, TypeCheckError
from core.perm import (
    WirePerm, identity, compose,
    twist_tensor_perm, assoc_tensor_L_perm, assoc_tensor_R_perm,
    twist_plus_perm, assoc_plus_L_perm, assoc_plus_R_perm,
)
from backends.materialize import swaps_for_perm, apply_swaps


@dataclass(frozen=True, slots=True)
class Compiled:
    circuit: Circuit
    perm: WirePerm
    log: Optional[List[str]] = None


def _contains_dist(t: Term) -> bool:
    """Check if term contains DistL or DistR anywhere."""
    if isinstance(t, (DistL, DistR)):
        return True
    if isinstance(t, Seq):
        return _contains_dist(t.f) or _contains_dist(t.g)
    return False


def compile(term: Term, *, materialize: bool = False, explain: bool = False) -> Compiled:
    # Check for distributivity FIRST before any other checks
    if _contains_dist(term):
        raise NotImplementedError("Distributivity compilation deferred (needs sum-aware layout).")

    assert_well_typed(term)
    dom, cod = type_of(term)
    n = width(dom)
    if width(cod) != n:
        raise TypeCheckError("Compilation currently requires width(dom)==width(cod).")

    circ = Circuit(n)
    p = identity(n)
    log: List[str] = []

    def emit_H(i: int) -> None:
        phys = p.apply_new_to_old(i)
        circ.H(phys)
        if explain:
            log.append(f"H logical {i} -> physical {phys}")

    def emit_S(i: int) -> None:
        phys = p.apply_new_to_old(i)
        circ.S(phys)
        if explain:
            log.append(f"S logical {i} -> physical {phys}")

    def emit_CX(i: int, j: int) -> None:
        phys_i = p.apply_new_to_old(i)
        phys_j = p.apply_new_to_old(j)
        circ.CX(phys_i, phys_j)
        if explain:
            log.append(f"CX logical ({i},{j}) -> physical ({phys_i},{phys_j})")

    def go(t: Term) -> None:
        nonlocal p
        if isinstance(t, Id):
            if explain:
                log.append("Id")
            return
        if isinstance(t, Seq):
            go(t.f)
            go(t.g)
            return

        # tensor and distributivity compilation are intentionally deferred (Phase 1+)
        if isinstance(t, (DistL, DistR)):
            raise NotImplementedError("Distributivity compilation deferred (needs sum-aware layout).")

        if isinstance(t, TwistTen):
            step = twist_tensor_perm(t.a, t.b)
            p = compose(step, p)
            if explain:
                log.append(f"TwistTen perm={step.new_to_old}")
            return
        if isinstance(t, AssocTenL):
            step = assoc_tensor_L_perm(t.a, t.b, t.c)
            p = compose(step, p)
            if explain:
                log.append(f"AssocTenL perm={step.new_to_old}")
            return
        if isinstance(t, AssocTenR):
            step = assoc_tensor_R_perm(t.a, t.b, t.c)
            p = compose(step, p)
            if explain:
                log.append(f"AssocTenR perm={step.new_to_old}")
            return

        if isinstance(t, TwistPlus):
            step = twist_plus_perm(t.a, t.b)
            p = compose(step, p)
            if explain:
                log.append(f"TwistPlus perm={step.new_to_old}")
            return
        if isinstance(t, AssocPlusL):
            step = assoc_plus_L_perm(t.a, t.b, t.c)
            p = compose(step, p)
            if explain:
                log.append(f"AssocPlusL perm={step.new_to_old}")
            return
        if isinstance(t, AssocPlusR):
            step = assoc_plus_R_perm(t.a, t.b, t.c)
            p = compose(step, p)
            if explain:
                log.append(f"AssocPlusR perm={step.new_to_old}")
            return

        if isinstance(t, H):
            emit_H(t.i); return
        if isinstance(t, S):
            emit_S(t.i); return
        if isinstance(t, CX):
            emit_CX(t.i, t.j); return

        raise TypeError(f"Unknown term node: {t!r}")

    go(term)

    if materialize:
        swaps = swaps_for_perm(p)
        apply_swaps(circ, swaps)
        if explain:
            log.append(f"Materialize swaps={swaps}")
        p = identity(n)

    return Compiled(circuit=circ, perm=p, log=(log if explain else None))
