# src/compile/to_pytket.py
"""Compiler: Source Term ==> pytket Circuit, using permutations as metadata."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Tuple

from pytket.circuit import Circuit

from lang.terms import (
    Term, Id, Seq, TenTerm,
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
    ExtractResult, physicalize_wires,
)
from compile.extract_v2 import try_extract_v2
from compile.extract_zx import try_extract_zx, is_pyzx_available


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

    # Phase 4C: Additional fixed gate emitters
    def emit_X(i: int, offset: int = 0) -> None:
        phys = p.apply_new_to_old(i + offset)
        circ.X(phys)

    def emit_Y(i: int, offset: int = 0) -> None:
        phys = p.apply_new_to_old(i + offset)
        circ.Y(phys)

    def emit_Z(i: int, offset: int = 0) -> None:
        phys = p.apply_new_to_old(i + offset)
        circ.Z(phys)

    def emit_T(i: int, offset: int = 0) -> None:
        phys = p.apply_new_to_old(i + offset)
        circ.T(phys)

    def emit_Tdg(i: int, offset: int = 0) -> None:
        phys = p.apply_new_to_old(i + offset)
        circ.Tdg(phys)

    def emit_Sdg(i: int, offset: int = 0) -> None:
        phys = p.apply_new_to_old(i + offset)
        circ.Sdg(phys)

    def emit_CZ(i: int, j: int, offset: int = 0) -> None:
        phys_i = p.apply_new_to_old(i + offset)
        phys_j = p.apply_new_to_old(j + offset)
        circ.CZ(phys_i, phys_j)

    def emit_CCX(i: int, j: int, k: int, offset: int = 0) -> None:
        phys_i = p.apply_new_to_old(i + offset)
        phys_j = p.apply_new_to_old(j + offset)
        phys_k = p.apply_new_to_old(k + offset)
        circ.CCX(phys_i, phys_j, phys_k)

    # Phase 4C: Parameterized gate emitters
    def emit_Rz(theta: float, i: int, offset: int = 0) -> None:
        phys = p.apply_new_to_old(i + offset)
        circ.Rz(theta, phys)

    def emit_Rx(theta: float, i: int, offset: int = 0) -> None:
        phys = p.apply_new_to_old(i + offset)
        circ.Rx(theta, phys)

    def emit_Ry(theta: float, i: int, offset: int = 0) -> None:
        phys = p.apply_new_to_old(i + offset)
        circ.Ry(theta, phys)

    def emit_Phase(phi: float, i: int, offset: int = 0) -> None:
        phys = p.apply_new_to_old(i + offset)
        # pytket uses U1 for phase gate: U1(phi) = diag(1, e^{i*phi})
        circ.U1(phi, phys)

    def emit_CRz(theta: float, i: int, j: int, offset: int = 0) -> None:
        phys_i = p.apply_new_to_old(i + offset)
        phys_j = p.apply_new_to_old(j + offset)
        circ.CRz(theta, phys_i, phys_j)

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

        # Phase 4C: Additional fixed gates
        if isinstance(t, X):
            emit_X(t.i, offset); return
        if isinstance(t, Y):
            emit_Y(t.i, offset); return
        if isinstance(t, Z):
            emit_Z(t.i, offset); return
        if isinstance(t, T):
            emit_T(t.i, offset); return
        if isinstance(t, Tdg):
            emit_Tdg(t.i, offset); return
        if isinstance(t, Sdg):
            emit_Sdg(t.i, offset); return
        if isinstance(t, CZ):
            emit_CZ(t.i, t.j, offset); return
        if isinstance(t, CCX):
            emit_CCX(t.i, t.j, t.k, offset); return

        # Phase 4C: Parameterized gates
        if isinstance(t, Rz):
            emit_Rz(t.theta, t.i, offset); return
        if isinstance(t, Rx):
            emit_Rx(t.theta, t.i, offset); return
        if isinstance(t, Ry):
            emit_Ry(t.theta, t.i, offset); return
        if isinstance(t, Phase):
            emit_Phase(t.phi, t.i, offset); return
        if isinstance(t, CRz):
            emit_CRz(t.theta, t.i, t.j, offset); return

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


def compile_goi(
    term: Term,
    *,
    materialize: bool = False,
    explain: bool = False,
    enable_zx: bool = False
) -> GOIResult:
    """Phase 3+ compiler with explicit GOI feedback semantics.

    Returns:
    - CompiledGOI(circuit, perm) if extraction succeeds
    - GOIArtifact (residual) if extraction fails

    Parameters:
    - materialize: If True, append SWAPs to realize the boundary permutation
    - explain: If True, include a compilation log
    - enable_zx: If True, use Phase 4B ZX-based extraction on residuals

    Invariants:
    - Phases 0-2 terms compile identically to compile()
    - Feedback terms are handled via GOI extraction
    - No SWAPs unless materialize=True and extraction succeeds
    - Failure to extract is not an error
    - Phase 4B (enable_zx) only processes residuals from Phase 4A
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

    def emit_atom(gate_name: str, wires: List[int], offset: int = 0, params: Tuple[float, ...] = ()) -> None:
        """Emit a gate atom with effective wire indices.

        The perm is applied at emit time to capture the routing state.
        This ensures gates appear at the correct physical positions
        when structure and gates are interleaved.

        Phase 4C: params holds gate parameters (angles, phases) for parameterized gates.
        """
        global_wires = [w + offset for w in wires]
        effective_wires = tuple(p.apply_new_to_old(g) for g in global_wires)
        atoms.append(GateAtom(gate_name, effective_wires, params))
        if explain:
            log.append(f"{gate_name} local {wires} + offset {offset} -> effective {effective_wires} params={params}")

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

        # Phase 4C: Additional fixed gates
        if isinstance(t, X):
            emit_atom("X", [t.i], offset)
            return

        if isinstance(t, Y):
            emit_atom("Y", [t.i], offset)
            return

        if isinstance(t, Z):
            emit_atom("Z", [t.i], offset)
            return

        if isinstance(t, T):
            emit_atom("T", [t.i], offset)
            return

        if isinstance(t, Tdg):
            emit_atom("Tdg", [t.i], offset)
            return

        if isinstance(t, Sdg):
            emit_atom("Sdg", [t.i], offset)
            return

        if isinstance(t, CZ):
            emit_atom("CZ", [t.i, t.j], offset)
            return

        if isinstance(t, CCX):
            emit_atom("CCX", [t.i, t.j, t.k], offset)
            return

        # Phase 4C: Parameterized gates
        if isinstance(t, Rz):
            emit_atom("Rz", [t.i], offset, params=(t.theta,))
            return

        if isinstance(t, Rx):
            emit_atom("Rx", [t.i], offset, params=(t.theta,))
            return

        if isinstance(t, Ry):
            emit_atom("Ry", [t.i], offset, params=(t.theta,))
            return

        if isinstance(t, Phase):
            emit_atom("U1", [t.i], offset, params=(t.phi,))
            return

        if isinstance(t, CRz):
            emit_atom("CRz", [t.i, t.j], offset, params=(t.theta,))
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

    # Attempt extraction (Phase 4A: use v2 which delegates to v1 first)
    result = try_extract_v2(goi)

    # Phase 4B: If Phase 4A returned a residual and enable_zx is True,
    # attempt ZX-based extraction
    if enable_zx and isinstance(result, GOIArtifact):
        if explain:
            log.append("Phase 4A returned residual - attempting Phase 4B ZX extraction")
        result = try_extract_zx(result)
        if explain:
            if isinstance(result, Extracted):
                log.append("Phase 4B ZX extraction succeeded")
            else:
                log.append("Phase 4B ZX extraction returned residual")

    if isinstance(result, Extracted):
        # Use the extracted perm's size for circuit
        ext_n = result.perm.n
        circ = Circuit(ext_n)

        # Emit atoms directly - they already have effective wire indices
        for atom in result.atoms:
            name = atom.gate_name
            wires = atom.wires
            params = atom.params

            # Phase 0 gates
            if name == "H":
                circ.H(wires[0])
            elif name == "S":
                circ.S(wires[0])
            elif name == "CX":
                circ.CX(wires[0], wires[1])
            # Phase 4C fixed gates
            elif name == "X":
                circ.X(wires[0])
            elif name == "Y":
                circ.Y(wires[0])
            elif name == "Z":
                circ.Z(wires[0])
            elif name == "T":
                circ.T(wires[0])
            elif name == "Tdg":
                circ.Tdg(wires[0])
            elif name == "Sdg":
                circ.Sdg(wires[0])
            elif name == "CZ":
                circ.CZ(wires[0], wires[1])
            elif name == "CCX":
                circ.CCX(wires[0], wires[1], wires[2])
            # Phase 4C parameterized gates
            elif name == "Rz":
                circ.Rz(params[0], wires[0])
            elif name == "Rx":
                circ.Rx(params[0], wires[0])
            elif name == "Ry":
                circ.Ry(params[0], wires[0])
            elif name == "U1":
                circ.U1(params[0], wires[0])
            elif name == "CRz":
                circ.CRz(params[0], wires[0], wires[1])
            else:
                raise ValueError(f"Unknown gate: {name}")
            if explain:
                log.append(f"Emit {name} on wires {wires} params={params}")

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
