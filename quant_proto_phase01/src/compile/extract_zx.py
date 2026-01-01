# src/compile/extract_zx.py
"""Phase 4B: ZX-based residual post-processing.

This module provides:
- try_extract_zx(): ZX-calculus based extraction for residual GOI artifacts
- to_pyzx_graph(): Direct translation from GOIArtifact to PyZX graph

Design invariants:
- Only processes RESIDUALS from Phase 4A (never extracts less)
- Uses deterministic structural rewrites only (id_simp, spider_simp)
- No heuristic passes (no full_reduce, no simulated annealing)
- Success = flat circuit + boundary perm (acyclic modulo boundary)
- Preserves all previous phase behavior when disabled

Translation strategy:
- GOIArtifact → PyZX Graph directly (NOT via circuit bridge)
- Gates as opaque box vertices (Z_BOX)
- Feedback loops as traced edges (cups/caps or self-loops)
- Boundary wires as BOUNDARY vertices

Key insight: We skip pytket↔pyzx bridges entirely for residuals because
those bridges don't preserve feedback/loop structure.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple, List, Dict

from core.perm import WirePerm, identity
from compile.goi import (
    GOIArtifact, GateAtom, LoopSpec,
    Extracted, ExtractResult,
    loop_wires,
)

# PyZX imports (optional - graceful fallback if not installed)
try:
    import pyzx
    from pyzx.graph import Graph
    from pyzx.utils import VertexType, EdgeType
    from pyzx import simplify
    PYZX_AVAILABLE = True
except ImportError:
    PYZX_AVAILABLE = False
    Graph = None


@dataclass(frozen=True, slots=True)
class ZXExtractionResult:
    """Result of ZX-based extraction attempt."""
    success: bool
    atoms: Optional[Tuple[GateAtom, ...]] = None
    perm: Optional[WirePerm] = None
    reason: Optional[str] = None


def is_pyzx_available() -> bool:
    """Check if PyZX is available."""
    return PYZX_AVAILABLE


def to_pyzx_graph(goi: GOIArtifact) -> "Graph":
    """Translate a GOIArtifact directly to a PyZX graph.

    Translation scheme:
    - Input boundaries: BOUNDARY vertices at row 0
    - Output boundaries: BOUNDARY vertices at final row
    - Gate atoms: Z_BOX vertices (opaque) at intermediate rows
    - Wire connections: SIMPLE edges
    - Feedback loops: Edges connecting output boundary back to input boundary

    This is a DIRECT translation - we don't go through pytket circuits
    because that would lose the feedback structure.
    """
    if not PYZX_AVAILABLE:
        raise RuntimeError("PyZX is not installed. Run: pip install pyzx")

    g = Graph()
    n = goi.n_out  # Total width including loop wires

    # Track vertices for wiring
    input_vertices: List[int] = []
    output_vertices: List[int] = []
    wire_state: Dict[int, int] = {}  # wire_idx -> current vertex

    # Row tracking for layout
    current_row = 0

    # Create input boundary vertices
    for i in range(n):
        v = g.add_vertex(VertexType.BOUNDARY, qubit=i, row=current_row)
        input_vertices.append(v)
        wire_state[i] = v

    current_row += 1

    # Add gate atoms as opaque boxes (Z_BOX)
    # Each gate gets a vertex and connects to its wire positions
    for atom in goi.atoms:
        # Create the gate vertex
        gate_v = g.add_vertex(VertexType.Z_BOX, qubit=atom.wires[0], row=current_row)

        # Store gate info in vertex data
        g.set_vdata(gate_v, 'gate_name', atom.gate_name)
        g.set_vdata(gate_v, 'wires', atom.wires)

        # For multi-wire gates, we need to track that this vertex
        # "owns" multiple wires. We create identity spiders to maintain
        # the wire structure for non-primary wires.
        primary_wire = atom.wires[0]

        # Connect gate to its input wires
        for wire in atom.wires:
            if wire in wire_state:
                # Connect from previous vertex on this wire
                prev_v = wire_state[wire]
                g.add_edge((prev_v, gate_v), EdgeType.SIMPLE)

        # Create output identity spiders for each wire the gate touches
        # so that subsequent gates can connect
        for wire in atom.wires:
            out_spider = g.add_vertex(VertexType.Z, qubit=wire, row=current_row + 0.5)
            g.add_edge((gate_v, out_spider), EdgeType.SIMPLE)
            wire_state[wire] = out_spider

        current_row += 1

    # Create output boundary vertices
    final_row = current_row + 1
    for i in range(n):
        v = g.add_vertex(VertexType.BOUNDARY, qubit=i, row=final_row)
        output_vertices.append(v)

        # Connect from current wire state
        if i in wire_state:
            g.add_edge((wire_state[i], v), EdgeType.SIMPLE)
        else:
            # Direct connection from input if no gates touched this wire
            g.add_edge((input_vertices[i], v), EdgeType.SIMPLE)

    # Handle feedback loops: connect output loop wires back to input loop wires
    for loop in goi.loops:
        L = loop_wires(goi, loop)
        for wire in L:
            # Apply perm to get the physical output wire
            phys = goi.perm.apply_new_to_old(wire)

            # In ZX, feedback is represented by connecting outputs to inputs
            # We add a cap structure (or direct edge in traced semantics)
            out_v = output_vertices[phys]
            in_v = input_vertices[wire]

            # Add a trace edge (connecting output back to corresponding input)
            # This creates the "loop" in the ZX diagram
            g.add_edge((out_v, in_v), EdgeType.SIMPLE)

    # Set inputs and outputs for the graph
    g.set_inputs(tuple(input_vertices))
    g.set_outputs(tuple(output_vertices))

    return g


def apply_deterministic_rewrites(g: "Graph") -> "Graph":
    """Apply only deterministic structural rewrites to a PyZX graph.

    We use ONLY:
    - id_simp: Remove identity spiders (degree-2 Z/X spiders with phase 0)
    - spider_simp: Fuse adjacent same-colored spiders

    We DO NOT use:
    - full_reduce (includes heuristic pivoting)
    - cliff_simp (introduces non-determinism)
    - to_graph_like + reduce (changes graph structure unpredictably)

    The goal is to simplify the graph while maintaining determinism
    and preserving the ability to extract a circuit.
    """
    if not PYZX_AVAILABLE:
        raise RuntimeError("PyZX is not installed")

    # Make a copy to avoid mutating the input
    g = g.copy()

    # Apply identity simplification
    # This removes degree-2 spiders with phase 0
    changed = True
    iterations = 0
    max_iterations = 100  # Safety limit

    while changed and iterations < max_iterations:
        changed = False
        iterations += 1

        # id_simp: removes identity (phase-0) spiders
        if simplify.id_simp(g):
            changed = True

        # spider_simp: fuses adjacent same-colored spiders
        if simplify.spider_simp(g):
            changed = True

    return g


def is_graph_extractable(g: "Graph") -> Tuple[bool, Optional[str]]:
    """Check if a ZX graph can be extracted to a flat circuit.

    A graph is extractable if:
    1. It has no loops (cycles that aren't boundary-to-boundary)
    2. All internal vertices are "gate-like" (can be interpreted as gates)
    3. The graph is "flow-consistent" (admits a valid causal order)

    For Phase 4B, we use a conservative check:
    - Graph is bipartite between inputs and outputs
    - No internal cycles
    - All Z_BOX vertices are preserved (opaque gates)
    """
    if not PYZX_AVAILABLE:
        return False, "PyZX not available"

    # Get boundary vertices
    inputs = g.inputs()
    outputs = g.outputs()

    if not inputs or not outputs:
        return False, "Missing boundary vertices"

    # Check for internal cycles using DFS
    # We want to verify the graph has a valid topological order from inputs to outputs
    visited = set()
    in_stack = set()

    def has_cycle(v: int, parent: Optional[int]) -> bool:
        """DFS cycle detection, ignoring back-edges to boundaries."""
        if v in in_stack:
            return True
        if v in visited:
            return False

        visited.add(v)
        in_stack.add(v)

        for neighbor in g.neighbors(v):
            # Skip parent to avoid false positive on undirected edges
            if neighbor == parent:
                continue
            # Boundaries are terminal - don't traverse past them
            if neighbor in outputs or neighbor in inputs:
                continue
            if has_cycle(neighbor, v):
                return True

        in_stack.remove(v)
        return False

    # Start DFS from each input
    for inp in inputs:
        for neighbor in g.neighbors(inp):
            if neighbor not in visited:
                if has_cycle(neighbor, inp):
                    return False, "Graph contains internal cycles"

    return True, None


def extract_circuit_from_graph(
    g: "Graph",
    original_goi: GOIArtifact
) -> Optional[Tuple[Tuple[GateAtom, ...], WirePerm]]:
    """Extract a flat circuit from a simplified ZX graph.

    This recovers the gate sequence and boundary permutation from
    the ZX graph after simplification.

    Returns None if extraction fails.
    """
    if not PYZX_AVAILABLE:
        return None

    # Compute the external boundary size
    external_size = original_goi.n_out
    for loop in original_goi.loops:
        external_size -= loop.k

    if external_size <= 0:
        return None

    # Find all Z_BOX vertices (our opaque gates)
    gate_vertices = []
    for v in g.vertices():
        if g.type(v) == VertexType.Z_BOX:
            gate_vertices.append(v)

    if not gate_vertices:
        # No gates - just return identity with the original perm
        # Build new permutation for external wires
        new_to_old = []
        for i in range(external_size):
            old = original_goi.perm.apply_new_to_old(i)
            if old < external_size:
                new_to_old.append(old)
            else:
                return None
        return ((), WirePerm(external_size, new_to_old))

    # Sort gates by row (preserves emission order)
    gate_vertices.sort(key=lambda v: g.row(v))

    # Reconstruct atoms from Z_BOX vertices
    # CRITICAL: Check if any gate wire is >= external_size (touches loop)
    atoms = []
    for v in gate_vertices:
        gate_name = g.vdata(v, 'gate_name')
        wires = g.vdata(v, 'wires')

        if gate_name is None or wires is None:
            # Lost gate data during simplification
            return None

        # Check if gate touches loop wires
        for w in wires:
            if w >= external_size:
                # Gate touches loop wire - cannot extract
                return None

        atoms.append(GateAtom(gate_name, tuple(wires)))

    # Build new permutation for external wires
    new_to_old = []
    for i in range(external_size):
        # Map through original perm, restricted to external wires
        old = original_goi.perm.apply_new_to_old(i)
        if old < external_size:
            new_to_old.append(old)
        else:
            # Wire maps outside external range - can't extract
            return None

    perm = WirePerm(external_size, new_to_old)

    return (tuple(atoms), perm)


def try_extract_zx(goi: GOIArtifact) -> ExtractResult:
    """Phase 4B ZX-based extraction.

    Attempts to extract a flat circuit from a residual GOI artifact
    using ZX-calculus simplification.

    This should only be called on RESIDUALS from Phase 4A.

    Returns:
    - Extracted(atoms, perm) if ZX simplification enables extraction
    - The original GOIArtifact (as residual) if ZX extraction fails

    Key guarantees:
    - Never extracts incorrectly (soundness)
    - Uses only deterministic rewrites (reproducibility)
    - Preserves residual when extraction is not provably safe
    """
    if not PYZX_AVAILABLE:
        # PyZX not available - return residual unchanged
        return goi

    # Step 1: Translate to PyZX graph
    try:
        g = to_pyzx_graph(goi)
    except Exception as e:
        # Translation failed - return residual
        return goi

    # Step 2: Apply deterministic structural rewrites
    try:
        g_simplified = apply_deterministic_rewrites(g)
    except Exception as e:
        # Simplification failed - return residual
        return goi

    # Step 3: Check if graph is now extractable
    extractable, reason = is_graph_extractable(g_simplified)

    if not extractable:
        # Still has cycles/structure that prevents extraction
        return goi

    # Step 4: Extract circuit from simplified graph
    result = extract_circuit_from_graph(g_simplified, goi)

    if result is None:
        # Extraction failed - return residual
        return goi

    atoms, perm = result
    return Extracted(atoms=atoms, perm=perm)
