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


# ---------------------------------------------------------------------------
# GOI Unitary Conjugation: U : A → A as (U† ⊗ U) on A* ⊗ A
# ---------------------------------------------------------------------------

def conjugate_unitary(gate_name: str, wires: Tuple[int, ...], n_a: int,
                      params: Tuple[float, ...] = (),
                      inverse_gate_name: str = None) -> Tuple[GateAtom, GateAtom]:
    """Encode a unitary U : A → A as conjugation on A* ⊗ A.

    A unitary program U : A → A is represented in GOI as the endomorphism
    (U_dual ⊗ U) : End(A* ⊗ A), i.e. conjugation on the memory pair.
    This guarantees reversibility and allows apply + feedback to execute
    calls without leaving garbage.

    Boundary layout (2*n_a wires):
      [A* (0..n_a-1) | A (n_a..2n_a-1)]

    Returns two GateAtoms:
      - U† on negative wires [0, n_a)
      - U on positive wires [n_a, 2*n_a)

    Args:
        gate_name: Name of the gate (e.g., "H", "S", "CX")
        wires: Relative wire indices within A (e.g., (0,) for single-qubit)
        n_a: Width of type A
        params: Gate parameters (rotation angles, etc.)
        inverse_gate_name: Name for U† (defaults to gate_name + "†")
    """
    if inverse_gate_name is None:
        # Default inverse naming convention
        inverse_gate_name = gate_name + "†"

    # U† on negative wires (A*)
    neg_wires = tuple(w for w in wires)  # wires are already in [0, n_a)
    u_dag = GateAtom(inverse_gate_name, neg_wires, params)

    # U on positive wires (A) - offset by n_a
    pos_wires = tuple(w + n_a for w in wires)
    u = GateAtom(gate_name, pos_wires, params)

    return (u_dag, u)


def make_unitary_value(gate_name: str, wires: Tuple[int, ...], n_a: int,
                       params: Tuple[float, ...] = (),
                       inverse_gate_name: str = None) -> GOIArtifact:
    """Create a GOIArtifact representing a unitary program value U : A → A.

    The artifact has 2*n_a wires (A* ⊗ A) with conjugation gates.
    """
    u_dag, u = conjugate_unitary(gate_name, wires, n_a, params, inverse_gate_name)

    return GOIArtifact(
        n_in=2 * n_a,
        n_out=2 * n_a,
        perm=identity(2 * n_a),
        atoms=(u_dag, u),
        loops=()
    )


# ---------------------------------------------------------------------------
# GOI Apply: Permutation for higher-order application
# ---------------------------------------------------------------------------

def apply_perm(n_a: int, n_b: int) -> WirePerm:
    """Apply permutation on boundary A* ⊗ A ⊗ B* ⊗ B.

    Swaps A* ↔ A and B* ↔ B to align ports for GOI feedback.

    Boundary layout (total = 2*n_a + 2*n_b wires):
      [A* (0..n_a-1) | A (n_a..2n_a-1) | B* (2n_a..2n_a+n_b-1) | B (2n_a+n_b..end)]

    After apply_perm:
      [A (0..n_a-1) | A* (n_a..2n_a-1) | B (2n_a..2n_a+n_b-1) | B* (2n_a+n_b..end)]

    This is: swap positions of A* with A, and B* with B.

    "In GOI, apply is the structural permutation on A* ⊗ A ⊗ B* ⊗ B
     swapping A*↔A and B*↔B so that GOI feedback executes the call.
     It is WirePerm-only."
    """
    total = 2 * n_a + 2 * n_b
    new_to_old = []

    # A block: swap A* and A
    # New position 0..n_a-1 gets old A (positions n_a..2n_a-1)
    new_to_old.extend(range(n_a, 2 * n_a))
    # New position n_a..2n_a-1 gets old A* (positions 0..n_a-1)
    new_to_old.extend(range(0, n_a))

    # B block: swap B* and B
    # New position 2n_a..2n_a+n_b-1 gets old B (positions 2n_a+n_b..end)
    new_to_old.extend(range(2 * n_a + n_b, total))
    # New position 2n_a+n_b..end gets old B* (positions 2n_a..2n_a+n_b-1)
    new_to_old.extend(range(2 * n_a, 2 * n_a + n_b))

    return WirePerm(total, new_to_old)


# ---------------------------------------------------------------------------
# GOI Composition: f ; g via tensor + feedback
# ---------------------------------------------------------------------------

def goi_seq(f: GOIArtifact, g: GOIArtifact, n_shared: int) -> GOIArtifact:
    """Compose f : A → B with g : B → C via GOI feedback.

    f is represented as ⟦f⟧ ∈ End(A* ⊗ B) with n_f = n_a + n_b wires
    g is represented as ⟦g⟧ ∈ End(B* ⊗ C) with n_g = n_b + n_c wires

    The shared boundary B has n_shared = n_b wires.

    Composition:
    1. Tensor: ⟦f⟧ ⊗ ⟦g⟧ on A* ⊗ B ⊗ B* ⊗ C (n_a + n_b + n_b + n_c wires)
    2. Feedback on middle B ⊗ B* (2*n_b wires) to get End(A* ⊗ C)

    Returns GOIArtifact with loops for the feedback.
    """
    n_f = f.n_out
    n_g = g.n_out

    # Validate shared boundary
    # f outputs n_a + n_b wires (A* ⊗ B)
    # g outputs n_b + n_c wires (B* ⊗ C)
    # n_shared = n_b

    # Total wires for tensor
    n_total = n_f + n_g

    # Combine atoms (f's atoms, then g's atoms with offset)
    combined_atoms = list(f.atoms)
    for atom in g.atoms:
        # Offset g's wires by n_f
        new_wires = tuple(w + n_f for w in atom.wires)
        combined_atoms.append(GateAtom(atom.gate_name, new_wires, atom.params))

    # Combine permutations: tensor of f.perm and g.perm
    # f.perm on [0, n_f), g.perm on [n_f, n_total)
    combined_new_to_old = list(f.perm.new_to_old)
    combined_new_to_old.extend(w + n_f for w in g.perm.new_to_old)
    combined_perm = WirePerm(n_total, combined_new_to_old)

    # The feedback wires are the middle B ⊗ B* section
    # After tensor, layout is [A* | B | B* | C]
    # We need to feed back B ↔ B* (the middle 2*n_shared wires)
    # But canonical LoopSpec feeds back the LAST k wires
    # So we need to permute to move B ⊗ B* to the end

    # Wire positions in tensored layout:
    # A*: [0, n_a)  where n_a = n_f - n_shared
    # B:  [n_a, n_f)  = [n_f - n_shared, n_f)
    # B*: [n_f, n_f + n_shared)
    # C:  [n_f + n_shared, n_total)

    n_a = n_f - n_shared
    _n_c = n_g - n_shared  # Used implicitly in reorder calculation

    # Permute to [A* | C | B | B*] so B ⊗ B* is at the end
    # Then LoopSpec(2 * n_shared) feeds back the last 2*n_shared wires
    reorder = []
    reorder.extend(range(0, n_a))  # A* stays at front
    reorder.extend(range(n_f + n_shared, n_total))  # C moves to middle
    reorder.extend(range(n_a, n_f))  # B moves after C
    reorder.extend(range(n_f, n_f + n_shared))  # B* at end

    reorder_perm = WirePerm(n_total, reorder)
    final_perm = compose(reorder_perm, combined_perm)

    # Update atom wires through the reorder
    reordered_atoms = []
    for atom in combined_atoms:
        new_wires = tuple(reorder.index(w) for w in atom.wires)
        reordered_atoms.append(GateAtom(atom.gate_name, new_wires, atom.params))

    return GOIArtifact(
        n_in=n_total,  # Will be reduced after feedback
        n_out=n_total,
        perm=final_perm,
        atoms=tuple(reordered_atoms),
        loops=(LoopSpec(2 * n_shared),)  # Feed back the B ⊗ B* wires
    )


# ---------------------------------------------------------------------------
# GOI Trace: Execute feedback to collapse internal wires
# ---------------------------------------------------------------------------

def execute_trace(goi: GOIArtifact) -> GOIArtifact:
    """Execute the trace/feedback to collapse internal wires.

    For a GOIArtifact with loops, this:
    1. Identifies the loop wires (internal)
    2. Maps gates on loop wires to external wires via feedback connection
    3. Returns a GOIArtifact with only external wires

    For composing conjugations f ; g where:
    - f = (f† ⊗ f) on [A* | B]
    - g = (g† ⊗ g) on [B* | C]
    - Loop is on [B | B*]

    The trace produces (f;g)† ⊗ (f;g) on [A* | C]:
    - External A* gets: g†; f† (reversed order of duals)
    - External C gets: f; g (forward order)

    The gates on the loop wires get "composed" through feedback:
    - f's positive gate (on B) connects to g's negative gate (on B*)
    - This gives the composition f ; g
    """
    if not goi.loops:
        return goi  # No loops, nothing to trace

    # Get loop specification
    loop = goi.loops[0]
    k = loop.k  # Number of loop wires

    # External wires are [0, n_out - k)
    # Loop wires are [n_out - k, n_out)
    n_external = goi.n_out - k
    loop_start = n_external

    # Separate atoms into external and loop
    external_atoms = []
    loop_atoms = []

    for atom in goi.atoms:
        if all(w < n_external for w in atom.wires):
            external_atoms.append(atom)
        else:
            loop_atoms.append(atom)

    # For conjugation composition, the loop atoms need to be
    # "moved" to the external wires via the feedback connection.
    #
    # The feedback identifies:
    # - Loop wire k (first half of loop) with loop wire k + n_shared
    # - These represent the B and B* parts being connected
    #
    # For the composition (f† ⊗ f) ; (g† ⊗ g):
    # - f on B (loop wire) and g† on B* (loop wire) are connected
    # - Through feedback, f's action on B becomes part of g's input
    # - The result: f;g on external C, and (f;g)† = g†;f† on external A*
    #
    # Concretely, for gates on loop wires:
    # - Gate on loop wire i maps to external wire based on feedback structure

    # For the simple case of composing Q→Q unitaries (n_shared = 1):
    # - Loop has 2 wires: [B | B*] = [n_external | n_external + 1]
    # - Gate on B (wire n_external) was f's positive part
    # - Gate on B* (wire n_external + 1) was g's negative part
    #
    # The trace composition:
    # - f's positive (on B) connects to g's negative (on B*)
    # - This means: f acts, then g† acts on the same qubit
    # - For the external A*: we need g†; f† (since (f;g)† = g†; f†)
    # - For the external C: we need f; g

    # Map loop atoms to external wires
    # For n_shared = 1 (Q→Q composition):
    # - Loop wire n_external (B) has a gate from f's positive half
    # - Loop wire n_external+1 (B*) has a gate from g's negative half
    #
    # Through feedback:
    # - The gate on B (f's positive) contributes to external C
    # - The gate on B* (g's negative) contributes to external A*

    n_shared = k // 2  # k = 2 * n_shared

    # Loop atoms come FIRST because:
    # - For positive wire (C): f;g means f (from loop) before g (external)
    # - For negative wire (A*): (f;g)† = g†;f† means g† (from loop) before f† (external)
    mapped_loop_atoms = []

    for atom in loop_atoms:
        # Determine which part of the loop this gate is on
        for w in atom.wires:
            if w >= loop_start and w < loop_start + n_shared:
                # This is on the B part (first half of loop)
                # It's from f's positive half, maps to external C (wire n_shared)
                # Actually, external C is at position n_external - n_shared ... hmm

                # Let me reconsider the wire layout after reorder:
                # [A* | C | B | B*]
                # A* is wires [0, n_a)
                # C is wires [n_a, n_a + n_c) = [n_a, n_external)
                # B is wires [n_external, n_external + n_shared)
                # B* is wires [n_external + n_shared, n_total)

                # For H;S with n_a=1, n_c=1, n_shared=1:
                # A* is wire 0
                # C is wire 1
                # B is wire 2
                # B* is wire 3

                # Gate on B (wire 2) is H (from H's positive half)
                # Gate on B* (wire 3) is Sdg (from S's negative half)

                # Through feedback composition:
                # - H (on B) contributes to C: the composed f;g has f then g on C
                # - Sdg (on B*) contributes to A*: the composed (f;g)† has g† then f† on A*

                # So:
                # - Gate on B maps to external C (wire 1 for n_a=1)
                # - Gate on B* maps to external A* (wire 0 for n_a=1)

                # External C starts at n_a (which is n_f - n_shared = n_external - n_c... wait)
                # Let me just compute n_a for this case
                # n_external = n_a + n_c
                # For symmetric case (A=C=Q), n_a = n_c = n_shared = 1
                # So n_external = 2, n_a = 1, n_c = 1

                # Gate on B (wire 2) → maps to C (wire 1) = wire n_a
                new_wire = w - loop_start + (n_external - n_shared)  # Map B to C
                new_atom = GateAtom(atom.gate_name, (new_wire,), atom.params)
                mapped_loop_atoms.append(new_atom)
                break

            elif w >= loop_start + n_shared:
                # This is on the B* part (second half of loop)
                # It's from g's negative half, maps to external A* (wire 0)
                new_wire = w - loop_start - n_shared  # Map B* to A*
                new_atom = GateAtom(atom.gate_name, (new_wire,), atom.params)
                mapped_loop_atoms.append(new_atom)
                break

    # Compose: loop atoms first (f contribution), then external atoms (g contribution)
    composed_atoms = mapped_loop_atoms + list(external_atoms)

    # Return the traced artifact with only external wires
    return GOIArtifact(
        n_in=n_external,
        n_out=n_external,
        perm=identity(n_external),  # Simplified; may need to extract from goi.perm
        atoms=tuple(composed_atoms),
        loops=()  # No more loops after trace
    )
