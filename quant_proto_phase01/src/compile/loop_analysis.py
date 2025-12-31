# src/compile/loop_analysis.py
"""Phase 4A: Loop interaction analysis for enhanced extraction.

This module provides:
- Gate support analysis
- ExternalizeWitness construction
- Feedback eliminability analysis

Design invariants:
- Never inspect or rewrite inside gate atoms (firewall)
- Only reason about wire indices
- Deterministic analysis (same input → same witness)

With effective wire semantics:
- GateAtom.wires are effective indices (perm applied at emit time)
- Phase 4A checks if gates already avoid loop wires
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Set, Tuple, List

from core.perm import WirePerm, identity, compose, inverse
from compile.goi import GOIArtifact, GateAtom, LoopSpec, loop_wires


@dataclass(frozen=True)
class ExternalizeWitness:
    """Witness that feedback body can be restructured to be loop-free.

    Fields:
    - p_in: identity (with effective wires, no reindexing needed)
    - p_out: identity
    - externalized_support: the gate support (already external)
    - loop_wire_set: the loop wire set
    """
    p_in: WirePerm
    p_out: WirePerm
    externalized_support: Set[int]
    loop_wire_set: Set[int]


def gate_support(atom: GateAtom) -> Set[int]:
    """Return the set of wire indices this gate acts on."""
    return set(atom.wires)


def all_gates_support(atoms: Tuple[GateAtom, ...]) -> Set[int]:
    """Return union of all gate supports."""
    result: Set[int] = set()
    for atom in atoms:
        result.update(gate_support(atom))
    return result


def gates_avoid_loops(atoms: Tuple[GateAtom, ...], loop_wire_set: Set[int]) -> bool:
    """Check if all gates avoid loop wires.

    With effective wire indices, atoms already have their final positions.
    """
    for atom in atoms:
        if gate_support(atom) & loop_wire_set:
            return False
    return True


def analyze_feedback_eliminable(
    goi: GOIArtifact,
    loop: LoopSpec
) -> Optional[ExternalizeWitness]:
    """Analyze if a feedback loop can be eliminated.

    With effective wire semantics, atoms already have final positions.
    We simply check if gates avoid loop wires.

    Returns ExternalizeWitness if eliminable, None otherwise.
    """
    L = loop_wires(goi, loop)
    n = goi.n_out

    # Check if gates already avoid loop wires
    gate_sup = all_gates_support(goi.atoms)
    if not (gate_sup & L):
        # Gates don't touch loop wires - can eliminate
        return ExternalizeWitness(
            p_in=identity(n),
            p_out=identity(n),
            externalized_support=gate_sup,
            loop_wire_set=L
        )

    # Gates touch loop wires - cannot eliminate
    return None


def apply_witness(
    goi: GOIArtifact,
    witness: ExternalizeWitness
) -> GOIArtifact:
    """Apply an ExternalizeWitness to a GOIArtifact.

    With effective wire semantics, this is essentially a no-op
    since atoms already have their final positions.
    """
    # Compose permutations
    intermediate = compose(goi.perm, witness.p_in)
    new_perm = compose(witness.p_out, intermediate)

    return GOIArtifact(
        n_in=goi.n_in,
        n_out=goi.n_out,
        perm=new_perm,
        atoms=goi.atoms,
        loops=goi.loops
    )


# Legacy aliases for backward compatibility
def logical_support(atom: GateAtom) -> Set[int]:
    """Alias for gate_support."""
    return gate_support(atom)


def all_logical_support(atoms: Tuple[GateAtom, ...]) -> Set[int]:
    """Alias for all_gates_support."""
    return all_gates_support(atoms)


def physical_support_under_perm(support: Set[int], perm: WirePerm) -> Set[int]:
    """Compute wire positions after applying permutation."""
    return {perm.apply_new_to_old(w) for w in support}


def gates_avoid_loops_under_perm(
    atoms: Tuple[GateAtom, ...],
    loop_wire_set: Set[int],
    perm: WirePerm
) -> bool:
    """Check if gates avoid loops under a specific perm.

    With effective wires, atoms already have positions,
    but this applies an additional perm for testing.
    """
    for atom in atoms:
        phys = physical_support_under_perm(gate_support(atom), perm)
        if phys & loop_wire_set:
            return False
    return True
