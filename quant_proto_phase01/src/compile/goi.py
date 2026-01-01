# src/compile/goi.py
"""Phase 3: Explicit GOI (Geometry-of-Interaction) feedback semantics.

This module provides:
- GOI data structures (GateAtom, LoopSpec, GOIArtifact)
- Physicalization helper (physicalize_wires)
- Yankability check (is_yankable)
- Feedback collapse (collapse_feedback)
- Extraction pass (try_extract)

Design invariants (from Phase 3 spec):
- Structural rewrites never enter gate atoms (firewall rule)
- No gate → no SWAPs unless materialize=True
- Extraction is sound but intentionally incomplete
- Failure to extract is not an error

Phase 4A Design Decision:
- GateAtom.wires are LOGICAL (pre-routing) indices
- Physicalization is deferred to the backend
- Only the backend may compute physical wire positions
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Set, Tuple, Union

from core.perm import WirePerm, identity, compose


@dataclass(frozen=True, slots=True)
class GateAtom:
    """Opaque gate atom with effective wire indices and optional parameters.

    Gate atoms are opaque - extraction may reason about wire support
    but never inspects or modifies the gate_name or internal parameters.

    The wires field contains EFFECTIVE indices - the perm at emit time
    is already applied, capturing the routing state when the gate was emitted.

    Phase 4C: params field holds gate parameters (e.g., rotation angles).
    Parameters are opaque to extraction and normalization.
    """
    gate_name: str
    wires: Tuple[int, ...]  # effective wire indices (perm applied at emit)
    params: Tuple[float, ...] = ()  # optional parameters (angles, phases)

    def support(self) -> Set[int]:
        """Return the set of wires this gate touches."""
        return set(self.wires)


def physicalize_wires(atom: GateAtom, perm: WirePerm) -> Tuple[int, ...]:
    """Compute physical wire positions for a gate atom.

    This is the ONLY function that should convert logical to physical.
    Called only at backend lowering time.
    """
    return tuple(perm.apply_new_to_old(w) for w in atom.wires)


def physical_support(atom: GateAtom, perm: WirePerm) -> Set[int]:
    """Compute the physical wire support of a gate under a permutation."""
    return set(physicalize_wires(atom, perm))


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

    - atoms contain LOGICAL wire indices
    - perm defines the routing from logical to physical
    - Physical positions = perm.apply(logical)
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
    """Successful extraction result: flat circuit + boundary permutation.

    atoms contain LOGICAL wire indices.
    perm maps logical to physical for the external boundary.
    """
    atoms: Tuple[GateAtom, ...]
    perm: WirePerm


# Type alias for extraction result
ExtractResult = Union[Extracted, GOIArtifact]


def loop_wires(goi: GOIArtifact, loop: LoopSpec) -> Set[int]:
    """Return the set of wire indices that belong to this loop.

    Canonical form: last k wires of the output (physical positions).
    """
    start = goi.n_out - loop.k
    return set(range(start, goi.n_out))


def normalize_goi(goi: GOIArtifact) -> GOIArtifact:
    """Push permutation into gate atom wire indices.

    After normalization:
    - perm is identity
    - atom wires are rewritten via the original perm
    - loop structure is preserved verbatim
    - gate types and order are unchanged (firewall rule)

    Note: For GOIArtifacts created by compile_goi, atoms already have
    effective indices (perm applied at emit time). This function is
    mainly useful for manually constructed GOIArtifacts in tests.
    """
    perm = goi.perm
    new_atoms = []

    for atom in goi.atoms:
        # Rewrite wire indices through the permutation
        new_wires = tuple(perm.apply_new_to_old(w) for w in atom.wires)
        new_atoms.append(GateAtom(atom.gate_name, new_wires, atom.params))

    return GOIArtifact(
        n_in=goi.n_in,
        n_out=goi.n_out,
        perm=identity(goi.n_out),
        atoms=tuple(new_atoms),
        loops=goi.loops
    )


def is_yankable(goi: GOIArtifact) -> bool:
    """Check if all loops in the GOI artifact are eliminable.

    A loop is yankable iff no gate atom touches any loop wire.
    Atom wires are effective indices (perm already applied at emit time).

    This check is deliberately conservative:
    - False negatives are acceptable (sound but incomplete)
    - False positives are not allowed (must be sound)
    """
    for loop in goi.loops:
        L = loop_wires(goi, loop)
        for atom in goi.atoms:
            if atom.support() & L:
                return False
    return True


def is_yankable_under_perm(goi: GOIArtifact, perm: WirePerm) -> bool:
    """Check yankability under a specific permutation.

    Note: With effective wire indices, atoms already have the perm applied.
    This function is retained for API compatibility but uses atom.wires directly.
    """
    for loop in goi.loops:
        L = loop_wires(goi, loop)
        for atom in goi.atoms:
            if atom.support() & L:
                return False
    return True


def collapse_feedback(goi: GOIArtifact) -> WirePerm:
    """Compute the induced boundary permutation when feedback is yankable.

    When a loop is yankable, the feedback wires can be "erased" and only
    the external boundary routing is retained.

    Precondition: goi should be yankable.

    Returns a perm that maps external logical wires to external physical wires.
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
    # External wires are indices [0, external_size) in both logical and physical space
    # We build a new permutation on external_size wires.
    new_to_old = []
    for i in range(external_size):
        old = goi.perm.apply_new_to_old(i)
        if old >= external_size:
            # This wire maps to a loop wire - this shouldn't happen
            # if properly yankable
            raise ValueError(f"External wire {i} maps to loop wire {old}")
        new_to_old.append(old)

    return WirePerm(external_size, new_to_old)


def try_extract(goi: GOIArtifact) -> ExtractResult:
    """Attempt to extract a flat circuit from a GOI artifact.

    Returns:
    - Extracted(atoms, perm) if all loops are yankable
    - The original GOIArtifact (as residual) if extraction fails

    Failure is not an error - it preserves all information for later refinement.

    Note: Extracted.atoms contain LOGICAL wire indices.
    """
    # If no loops, extraction is trivial
    if not goi.loops:
        return Extracted(atoms=goi.atoms, perm=goi.perm)

    # Check yankability (uses physical positions internally)
    if not is_yankable(goi):
        # Return as residual to preserve all structural information
        return goi

    # Collapse the feedback to a boundary permutation
    new_perm = collapse_feedback(goi)

    # Filter atoms to only those on external wires
    # (loop-touching atoms would have failed yankability check)
    # Atoms stay in logical form
    external_size = goi.n_out - goi.loops[0].k
    external_atoms = tuple(
        atom for atom in goi.atoms
        if all(w < external_size for w in atom.wires)
    )

    return Extracted(atoms=external_atoms, perm=new_perm)
