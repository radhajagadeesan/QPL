# src/compile/goi.py
"""Phase 3: Explicit GOI (Geometry-of-Interaction) feedback semantics.

This module provides:
- GOI data structures (GateAtom, LoopSpec, GOIArtifact)
- Normalization pass (normalize_goi)
- Yankability check (is_yankable)
- Feedback collapse (collapse_feedback)
- Extraction pass (try_extract)

Design invariants (from Phase 3 spec):
- Structural rewrites never enter gate atoms (firewall rule)
- No gate → no SWAPs unless materialize=True
- Extraction is sound but intentionally incomplete
- Failure to extract is not an error
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Set, Tuple, Union

from core.perm import WirePerm, identity, compose


@dataclass(frozen=True, slots=True)
class GateAtom:
    """Opaque gate atom with explicit wire indices.

    Gate atoms are opaque - normalization may only rewrite wire indices,
    never the gate_name or any internal parameters.
    """
    gate_name: str
    wires: Tuple[int, ...]  # physical wire indices

    def support(self) -> Set[int]:
        """Return the set of wires this gate touches."""
        return set(self.wires)


@dataclass(frozen=True, slots=True)
class LoopSpec:
    """Specification of a feedback loop.

    Canonical Phase 3 form: loop the last k output wires
    back to the last k input wires.
    """
    k: int  # number of loop wires


@dataclass(frozen=True)
class GOIArtifact:
    """GOI intermediate representation.

    Contains boundary info, routing permutation, gate atoms, and loop specs.
    """
    n_in: int
    n_out: int
    perm: WirePerm
    atoms: Tuple[GateAtom, ...]
    loops: Tuple[LoopSpec, ...] = field(default_factory=tuple)

    def __post_init__(self):
        # Ensure atoms and loops are tuples for immutability
        if isinstance(self.atoms, list):
            object.__setattr__(self, 'atoms', tuple(self.atoms))
        if isinstance(self.loops, list):
            object.__setattr__(self, 'loops', tuple(self.loops))


# Result types for extraction
@dataclass(frozen=True, slots=True)
class Extracted:
    """Successful extraction result: flat circuit + boundary permutation."""
    atoms: Tuple[GateAtom, ...]
    perm: WirePerm


# Type alias for extraction result
ExtractResult = Union[Extracted, GOIArtifact]


def loop_wires(goi: GOIArtifact, loop: LoopSpec) -> Set[int]:
    """Return the set of wire indices that belong to this loop.

    Canonical form: last k wires of the output.
    """
    start = goi.n_out - loop.k
    return set(range(start, goi.n_out))


def normalize_goi(goi: GOIArtifact) -> GOIArtifact:
    """Push all structural effects (permutation) into gate atom wire indices.

    After normalization:
    - perm is identity
    - atom wires are rewritten via the original perm
    - loop structure is preserved verbatim
    - gate types and order are unchanged (firewall rule)
    """
    perm = goi.perm
    new_atoms = []

    for atom in goi.atoms:
        # Rewrite wire indices through the permutation
        new_wires = tuple(perm.apply_new_to_old(w) for w in atom.wires)
        new_atoms.append(GateAtom(atom.gate_name, new_wires))

    return GOIArtifact(
        n_in=goi.n_in,
        n_out=goi.n_out,
        perm=identity(goi.n_out),
        atoms=tuple(new_atoms),
        loops=goi.loops
    )


def is_yankable(goi: GOIArtifact) -> bool:
    """Check if all loops in the GOI artifact are eliminable.

    A loop is yankable iff no gate atom touches any loop wire
    after normalization.

    This check is deliberately conservative:
    - False negatives are acceptable (sound but incomplete)
    - False positives are not allowed (must be sound)
    """
    for loop in goi.loops:
        L = loop_wires(goi, loop)
        for atom in goi.atoms:
            if any(w in L for w in atom.wires):
                return False
    return True


def collapse_feedback(goi: GOIArtifact) -> WirePerm:
    """Compute the induced boundary permutation when feedback is yankable.

    When a loop is yankable, the feedback wires can be "erased" and only
    the external boundary routing is retained.

    Precondition: goi should be normalized and yankable.
    """
    if not goi.loops:
        return goi.perm

    # For canonical Phase 3 form: single loop of size k
    loop = goi.loops[0]
    k = loop.k
    external_size = goi.n_out - k

    if external_size <= 0:
        raise ValueError("Cannot collapse feedback with no external wires")

    # The boundary permutation is the restriction of goi.perm to external wires
    # Since we're normalized, perm should be identity, but we still compute
    # the restriction properly.
    #
    # External wires are indices [0, external_size)
    # We build a new permutation on external_size wires.
    new_to_old = []
    for i in range(external_size):
        old = goi.perm.apply_new_to_old(i)
        if old >= external_size:
            # This wire maps to a loop wire - this shouldn't happen
            # if properly yankable and normalized
            raise ValueError(f"External wire {i} maps to loop wire {old}")
        new_to_old.append(old)

    return WirePerm(external_size, new_to_old)


def try_extract(goi: GOIArtifact) -> ExtractResult:
    """Attempt to extract a flat circuit from a GOI artifact.

    Returns:
    - Extracted(atoms, perm) if all loops are yankable
    - The original GOIArtifact (as ResidualGOI) if extraction fails

    Failure is not an error - it preserves all information for later refinement.
    """
    # If no loops, extraction is trivial
    if not goi.loops:
        return Extracted(atoms=goi.atoms, perm=goi.perm)

    # Normalize first
    goi_norm = normalize_goi(goi)

    # Check yankability
    if not is_yankable(goi_norm):
        # Return the original (not normalized) as residual
        # to preserve all structural information
        return goi

    # Collapse the feedback to a boundary permutation
    new_perm = collapse_feedback(goi_norm)

    # Filter atoms to only those on external wires
    # (loop-touching atoms would have failed yankability check)
    return Extracted(atoms=goi_norm.atoms, perm=new_perm)
