# src/compile/extract_v2.py
"""Phase 4A: Enhanced extraction (Extraction++).

This module provides:
- try_extract_v2(): strictly additive extraction over Phase 3

Design invariants:
- Succeeds on a STRICT SUPERSET of Phase 3 extractable cases
- Never extracts incorrectly (soundness preserved)
- Preserves residual GOI artifacts when extraction is not provably safe
- All Phase 0-3 golden outputs remain BIT-FOR-BIT IDENTICAL
- Calls Phase 3 (v1) first, only enhances residual cases

With logical wire semantics:
- GateAtom.wires are LOGICAL indices
- Physical positions = perm.apply(logical)
- Yankability checks use physical positions

Pipeline:
1. Phase 3 delegation (try_extract)
2. If residual: outer routing normalization
3. Feedback analysis with ExternalizeWitness
4. Global extraction check
"""

from __future__ import annotations

from typing import Union

from core.perm import WirePerm, identity, compose
from compile.goi import (
    GOIArtifact, GateAtom, LoopSpec,
    Extracted, ExtractResult,
    try_extract, normalize_goi, is_yankable, collapse_feedback, loop_wires,
)
from compile.routing_nf2 import normalize_routing_v2
from compile.loop_analysis import (
    ExternalizeWitness,
    analyze_feedback_eliminable,
    apply_witness,
    gate_support,
)


def try_extract_v2(goi: GOIArtifact) -> ExtractResult:
    """Phase 4A enhanced extraction.

    Attempts to extract a flat circuit from a GOI artifact using
    enhanced analysis that handles more cases than Phase 3.

    Returns:
    - Extracted(atoms, perm) if all loops are eliminable
    - The original GOIArtifact (as residual) if extraction fails

    Key guarantee: Phase 3 extractions are unchanged. We only
    attempt enhanced extraction on Phase 3 residuals.
    """
    # Step 1: Phase 3 delegation (MUST come first)
    # This preserves bit-for-bit identical Phase 3 behavior
    v1_result = try_extract(goi)

    if isinstance(v1_result, Extracted):
        # Phase 3 succeeded - return unchanged
        return v1_result

    # v1_result is residual GOIArtifact
    residual = v1_result

    # Step 2: Outer routing normalization (Phase 4A only)
    residual = normalize_routing_v2(residual)

    # Step 3: Feedback analysis
    # Walk feedback nodes in canonical order (by index for determinism)
    residual = _process_feedback_loops(residual)

    # Step 4: Final extraction attempt
    # If all feedback has been eliminated, we can extract
    if not residual.loops:
        # No loops remain - flatten to extracted
        return Extracted(atoms=residual.atoms, perm=residual.perm)

    # Check if now yankable (uses physical positions)
    if is_yankable(residual):
        # Can now yank all feedback
        new_perm = collapse_feedback(residual)
        # Filter atoms to external wires
        external_size = residual.n_out - residual.loops[0].k
        external_atoms = tuple(
            atom for atom in residual.atoms
            if all(w < external_size for w in atom.wires)
        )
        return Extracted(atoms=external_atoms, perm=new_perm)

    # Still has non-yankable feedback - return as residual
    return residual


def _process_feedback_loops(goi: GOIArtifact) -> GOIArtifact:
    """Process each feedback loop, attempting to eliminate or simplify.

    Returns a new GOIArtifact with potentially fewer/simpler loops.
    """
    if not goi.loops:
        return goi

    current = goi
    remaining_loops = []

    # Process loops in index order (deterministic)
    for i, loop in enumerate(goi.loops):
        # First check: is this loop already yankable?
        if _is_loop_yankable(current, loop):
            # Can eliminate this loop via Phase 3 yanking
            current = _yank_single_loop(current, loop)
            continue

        # Second check: can we find an ExternalizeWitness?
        witness = analyze_feedback_eliminable(current, loop)

        if witness is not None:
            # Apply the witness to restructure
            current = apply_witness(current, witness)

            # After witness application, check if now yankable
            if _is_loop_yankable(current, loop):
                current = _yank_single_loop(current, loop)
                continue

        # Could not eliminate - keep this loop
        remaining_loops.append(loop)

    # Return artifact with remaining loops
    return GOIArtifact(
        n_in=current.n_in,
        n_out=current.n_out,
        perm=current.perm,
        atoms=current.atoms,
        loops=tuple(remaining_loops)
    )


def _is_loop_yankable(goi: GOIArtifact, loop: LoopSpec) -> bool:
    """Check if a specific loop is yankable.

    A loop is yankable iff no gate touches loop wires.
    With effective wire semantics, atoms already have final positions.
    """
    L = loop_wires(goi, loop)
    for atom in goi.atoms:
        if gate_support(atom) & L:
            return False
    return True


def _yank_single_loop(goi: GOIArtifact, loop: LoopSpec) -> GOIArtifact:
    """Yank (eliminate) a single loop from the GOI artifact.

    Precondition: the loop must be yankable.
    """
    k = loop.k
    external_size = goi.n_out - k

    if external_size <= 0:
        raise ValueError("Cannot yank loop with no external wires")

    # Compute boundary permutation restricted to external wires
    new_to_old = []
    for i in range(external_size):
        old = goi.perm.apply_new_to_old(i)
        if old >= external_size:
            raise ValueError(f"External wire {i} maps to loop wire {old}")
        new_to_old.append(old)

    new_perm = WirePerm(external_size, new_to_old)

    # Filter atoms to only those on external wires (logical)
    # Since we're yankable, physical positions don't touch loop
    # But logical wires might still reference loop indices
    external_atoms = tuple(
        atom for atom in goi.atoms
        if all(w < external_size for w in atom.wires)
    )

    # Remove this loop from the loop list
    new_loops = tuple(l for l in goi.loops if l is not loop)

    return GOIArtifact(
        n_in=external_size,
        n_out=external_size,
        perm=new_perm,
        atoms=external_atoms,
        loops=new_loops
    )
