# src/compile/to_pytket.py
"""Compiler: Source Term ==> pytket Circuit, using permutations as metadata."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from pytket.circuit import Circuit

from lang.terms import (
    Term, Id, Seq, TenTerm,
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
    if isinstance(t, TenTerm):
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

    def emit_H(i: int, offset: int = 0) -> None:
        global_idx = i + offset
        phys = p.apply_new_to_old(global_idx)
        circ.H(phys)
        if explain:
            log.append(f"H local {i} + offset {offset} = global {global_idx} -> physical {phys}")

    def emit_S(i: int, offset: int = 0) -> None:
        global_idx = i + offset
        phys = p.apply_new_to_old(global_idx)
        circ.S(phys)
        if explain:
            log.append(f"S local {i} + offset {offset} = global {global_idx} -> physical {phys}")

    def emit_CX(i: int, j: int, offset: int = 0) -> None:
        global_i = i + offset
        global_j = j + offset
        phys_i = p.apply_new_to_old(global_i)
        phys_j = p.apply_new_to_old(global_j)
        circ.CX(phys_i, phys_j)
        if explain:
            log.append(f"CX local ({i},{j}) + offset {offset} = global ({global_i},{global_j}) -> physical ({phys_i},{phys_j})")

    def embed_local_perm(local_perm: WirePerm, offset: int) -> WirePerm:
        """Embed a local permutation into the global n-wire space.

        For a local permutation acting on wires [0..local_width-1],
        create a global permutation where:
        - Wires [0..offset-1] are identity
        - Wires [offset..offset+local_width-1] get the local perm (shifted)
        - Wires [offset+local_width..n-1] are identity
        """
        local_width = local_perm.n
        global_perm = list(range(n))  # Start with identity
        for i in range(local_width):
            # Map global wire (offset + i) to global wire (offset + local_perm[i])
            global_perm[offset + i] = offset + local_perm.new_to_old[i]
        return WirePerm(n, global_perm)

    def go(t: Term, offset: int = 0) -> None:
        nonlocal p
        if isinstance(t, Id):
            if explain:
                log.append(f"Id (offset={offset})")
            return
        if isinstance(t, Seq):
            go(t.f, offset)
            go(t.g, offset)
            return

        # TenTerm: parallel composition with offset semantics (Phase 2)
        if isinstance(t, TenTerm):
            # Get the type of the left branch to compute right branch offset
            left_dom, _ = type_of(t.f)
            left_width = width(left_dom)
            # Compile left branch first (spec: left-then-right order)
            go(t.f, offset)
            # Compile right branch with additional offset
            go(t.g, offset + left_width)
            if explain:
                log.append(f"TenTerm left_width={left_width}")
            return

        # Distributivity compilation deferred
        if isinstance(t, (DistL, DistR)):
            raise NotImplementedError("Distributivity compilation deferred (needs sum-aware layout).")

        if isinstance(t, TwistTen):
            local_step = twist_tensor_perm(t.a, t.b)
            step = embed_local_perm(local_step, offset)
            p = compose(step, p)
            if explain:
                log.append(f"TwistTen local={local_step.new_to_old} offset={offset} global={step.new_to_old}")
            return
        if isinstance(t, AssocTenL):
            local_step = assoc_tensor_L_perm(t.a, t.b, t.c)
            step = embed_local_perm(local_step, offset)
            p = compose(step, p)
            if explain:
                log.append(f"AssocTenL perm={step.new_to_old}")
            return
        if isinstance(t, AssocTenR):
            local_step = assoc_tensor_R_perm(t.a, t.b, t.c)
            step = embed_local_perm(local_step, offset)
            p = compose(step, p)
            if explain:
                log.append(f"AssocTenR perm={step.new_to_old}")
            return

        if isinstance(t, TwistPlus):
            local_step = twist_plus_perm(t.a, t.b)
            step = embed_local_perm(local_step, offset)
            p = compose(step, p)
            if explain:
                log.append(f"TwistPlus perm={step.new_to_old}")
            return
        if isinstance(t, AssocPlusL):
            local_step = assoc_plus_L_perm(t.a, t.b, t.c)
            step = embed_local_perm(local_step, offset)
            p = compose(step, p)
            if explain:
                log.append(f"AssocPlusL perm={step.new_to_old}")
            return
        if isinstance(t, AssocPlusR):
            local_step = assoc_plus_R_perm(t.a, t.b, t.c)
            step = embed_local_perm(local_step, offset)
            p = compose(step, p)
            if explain:
                log.append(f"AssocPlusR perm={step.new_to_old}")
            return

        if isinstance(t, H):
            emit_H(t.i, offset); return
        if isinstance(t, S):
            emit_S(t.i, offset); return
        if isinstance(t, CX):
            emit_CX(t.i, t.j, offset); return

        raise TypeError(f"Unknown term node: {t!r}")

    go(term)

    if materialize:
        swaps = swaps_for_perm(p)
        apply_swaps(circ, swaps)
        if explain:
            log.append(f"Materialize swaps={swaps}")
        p = identity(n)

    return Compiled(circuit=circ, perm=p, log=(log if explain else None))
