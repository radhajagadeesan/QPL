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
    Feedback,
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
from compile.goi import (
    GateAtom, LoopSpec, GOIArtifact, Extracted,
    normalize_goi, is_yankable, collapse_feedback, try_extract,
    ExtractResult,
)


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
    if isinstance(t, Feedback):
        return _contains_dist(t.body)
    return False


def _contains_feedback(t: Term) -> bool:
    """Check if term contains Feedback anywhere."""
    if isinstance(t, Feedback):
        return True
    if isinstance(t, Seq):
        return _contains_feedback(t.f) or _contains_feedback(t.g)
    if isinstance(t, TenTerm):
        return _contains_feedback(t.f) or _contains_feedback(t.g)
    return False


def compile(term: Term, *, materialize: bool = False, explain: bool = False) -> Compiled:
    # Check for distributivity FIRST before any other checks
    if _contains_dist(term):
        raise NotImplementedError("Distributivity compilation deferred (needs sum-aware layout).")

    # Check for Feedback - must use compile_goi instead
    if _contains_feedback(term):
        raise NotImplementedError(
            "Feedback compilation requires compile_goi(). "
            "Use compile_goi(term) for Phase 3 GOI semantics."
        )

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


# -----------------------------------------------------------------------------
# Phase 3: GOI Compilation
# -----------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class CompiledGOI:
    """Result of compile_goi when extraction succeeds."""
    circuit: Circuit
    perm: WirePerm
    log: Optional[List[str]] = None


# Type alias for compile_goi result
GOIResult = CompiledGOI | GOIArtifact


def _compute_internal_width(term: Term) -> int:
    """Compute the internal width of a term (including loop wires for Feedback)."""
    if isinstance(term, Feedback):
        # For Feedback_k(body), internal width = body width
        body_dom, _ = type_of(term.body)
        return width(body_dom)
    else:
        # For non-Feedback terms, just use the term's width
        dom, _ = type_of(term)
        return width(dom)


def compile_goi(term: Term, *, materialize: bool = False, explain: bool = False) -> GOIResult:
    """Phase 3 compiler with explicit GOI feedback semantics.

    Returns:
    - CompiledGOI(circuit, perm) if extraction succeeds
    - GOIArtifact (residual) if extraction fails

    Invariants:
    - Phases 0-2 terms compile identically to compile()
    - Feedback terms are handled via GOI extraction
    - No SWAPs unless materialize=True and extraction succeeds
    - Failure to extract is not an error
    """
    # Check for distributivity
    if _contains_dist(term):
        raise NotImplementedError("Distributivity compilation deferred (needs sum-aware layout).")

    assert_well_typed(term)

    # For Feedback terms, we need to work with the body's width (internal),
    # not the external width of the Feedback term itself
    n_internal = _compute_internal_width(term)
    dom, cod = type_of(term)
    n_external = width(dom)

    # Compile to GOIArtifact
    atoms: List[GateAtom] = []
    loops: List[LoopSpec] = []
    p = identity(n_internal)
    log: List[str] = []

    def emit_atom(gate_name: str, wires: List[int], offset: int = 0) -> None:
        """Emit a gate atom with physical wire indices."""
        global_wires = [w + offset for w in wires]
        phys_wires = tuple(p.apply_new_to_old(g) for g in global_wires)
        atoms.append(GateAtom(gate_name, phys_wires))
        if explain:
            log.append(f"{gate_name} local {wires} + offset {offset} -> physical {phys_wires}")

    def embed_local_perm(local_perm: WirePerm, offset: int) -> WirePerm:
        """Embed a local permutation into the global n-wire space."""
        local_width = local_perm.n
        global_perm = list(range(n_internal))
        for i in range(local_width):
            global_perm[offset + i] = offset + local_perm.new_to_old[i]
        return WirePerm(n_internal, global_perm)

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

        if isinstance(t, TenTerm):
            left_dom, _ = type_of(t.f)
            left_width = width(left_dom)
            go(t.f, offset)
            go(t.g, offset + left_width)
            if explain:
                log.append(f"TenTerm left_width={left_width}")
            return

        if isinstance(t, Feedback):
            # For nested Feedback, we need to compile the body and add a loop
            body_dom, _ = type_of(t.body)
            body_width = width(body_dom)

            # Compile the body with current offset
            go(t.body, offset)

            # Add loop specification
            loops.append(LoopSpec(t.k))
            if explain:
                log.append(f"Feedback k={t.k} body_width={body_width}")
            return

        if isinstance(t, (DistL, DistR)):
            raise NotImplementedError("Distributivity compilation deferred (needs sum-aware layout).")

        if isinstance(t, TwistTen):
            local_step = twist_tensor_perm(t.a, t.b)
            step = embed_local_perm(local_step, offset)
            p = compose(step, p)
            if explain:
                log.append(f"TwistTen local={local_step.new_to_old} offset={offset}")
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
            emit_atom("H", [t.i], offset)
            return

        if isinstance(t, S):
            emit_atom("S", [t.i], offset)
            return

        if isinstance(t, CX):
            emit_atom("CX", [t.i, t.j], offset)
            return

        raise TypeError(f"Unknown term node: {t!r}")

    # If term is a top-level Feedback, we process it specially
    if isinstance(term, Feedback):
        # Compile the body
        go(term.body, 0)
        # Add the loop
        loops.append(LoopSpec(term.k))
        if explain:
            log.append(f"Top-level Feedback k={term.k}")
    else:
        go(term)

    # Build GOIArtifact
    goi = GOIArtifact(
        n_in=n_internal,
        n_out=n_internal,
        perm=p,
        atoms=tuple(atoms),
        loops=tuple(loops)
    )

    # Attempt extraction
    result = try_extract(goi)

    if isinstance(result, Extracted):
        # Use the extracted perm's size for circuit
        ext_n = result.perm.n
        circ = Circuit(ext_n)

        for atom in result.atoms:
            if atom.gate_name == "H":
                circ.H(atom.wires[0])
            elif atom.gate_name == "S":
                circ.S(atom.wires[0])
            elif atom.gate_name == "CX":
                circ.CX(atom.wires[0], atom.wires[1])
            else:
                raise ValueError(f"Unknown gate: {atom.gate_name}")

        final_perm = result.perm

        if materialize:
            swaps = swaps_for_perm(final_perm)
            apply_swaps(circ, swaps)
            if explain:
                log.append(f"Materialize swaps={swaps}")
            final_perm = identity(ext_n)

        return CompiledGOI(circuit=circ, perm=final_perm, log=(log if explain else None))
    else:
        # Return residual GOI artifact
        if explain:
            log.append("Extraction failed - returning residual GOI")
        return result
