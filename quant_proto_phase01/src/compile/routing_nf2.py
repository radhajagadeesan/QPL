# src/compile/routing_nf2.py
"""Phase 4A: Outer-only routing normalization.

This module provides:
- normalize_routing_v2(): canonical routing normalization for residual GOI artifacts

Design invariants:
- Only rewrites routing structure (WirePerm, identity, inverse cancellation)
- Never rewrites inside gate atoms
- Never introduces SWAPs
- Deterministic and confluent on Phase 3-normal forms
- Applied ONLY after Phase 3 extraction fails
"""

from __future__ import annotations

from typing import Tuple

from core.perm import WirePerm, identity, compose, inverse
from compile.goi import GOIArtifact, GateAtom, LoopSpec


def is_identity(perm: WirePerm) -> bool:
    """Check if a permutation is the identity."""
    for i in range(perm.n):
        if perm.apply_new_to_old(i) != i:
            return False
    return True


def is_inverse_pair(p1: WirePerm, p2: WirePerm) -> bool:
    """Check if p2 is the inverse of p1."""
    if p1.n != p2.n:
        return False
    for i in range(p1.n):
        if p2.apply_new_to_old(p1.apply_new_to_old(i)) != i:
            return False
    return True


def normalize_perm(perm: WirePerm) -> WirePerm:
    """Normalize a permutation to canonical form.

    Currently just returns the perm as-is since WirePerm is already
    in a canonical representation. Future extensions could add
    cycle decomposition normalization.
    """
    return perm


def normalize_routing_v2(goi: GOIArtifact) -> GOIArtifact:
    """Apply outer-only routing normalization to a GOI artifact.

    This normalization:
    1. Eliminates identity permutations (no-op)
    2. Canonicalizes the permutation representation
    3. Does NOT modify gate atoms or their wire indices
    4. Preserves loop structure verbatim

    This is called ONLY on residual GOI artifacts (after Phase 3 fails).
    """
    # Step 1: Check if perm is identity (no routing work needed)
    if is_identity(goi.perm):
        # Already in simplest form
        return goi

    # Step 2: Normalize the permutation to canonical form
    normalized_perm = normalize_perm(goi.perm)

    # Return new artifact with normalized perm
    # Gate atoms and loops are preserved unchanged
    return GOIArtifact(
        n_in=goi.n_in,
        n_out=goi.n_out,
        perm=normalized_perm,
        atoms=goi.atoms,
        loops=goi.loops
    )


def try_simplify_perm_sequence(perms: Tuple[WirePerm, ...]) -> WirePerm:
    """Simplify a sequence of permutations by composing and canceling.

    Used when analyzing routing chains. Applies:
    - Identity elimination
    - Inverse cancellation (P ; P^-1 = Id)
    - Composition to single canonical perm
    """
    if not perms:
        raise ValueError("Cannot simplify empty permutation sequence")

    if len(perms) == 1:
        return perms[0]

    # Compose all permutations
    result = perms[0]
    for p in perms[1:]:
        if p.n != result.n:
            raise ValueError(f"Permutation size mismatch: {result.n} vs {p.n}")
        result = compose(result, p)

    # The composition may have resulted in identity
    return result


def decompose_for_feedback(perm: WirePerm, k: int) -> Tuple[WirePerm, WirePerm]:
    """Attempt to decompose perm for feedback elimination.

    For a feedback of k wires, try to find P_in, P_out such that:
    - perm = P_out ∘ P_in
    - After reindexing through P_in, gates avoid loop wires

    This is a heuristic helper for the loop analysis module.
    Returns (p_in, p_out) as a candidate decomposition.

    Default strategy: identity decomposition (perm = perm ∘ id).
    """
    n = perm.n
    # Default: trivial decomposition
    return (identity(n), perm)
