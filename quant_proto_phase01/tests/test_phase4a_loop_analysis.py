# tests/test_phase4a_loop_analysis.py
"""Phase 4A: Unit tests for loop interaction analysis.

Tests:
- A1. Gate support
- A2. Loop-wire disjointness certification
- A3. Witness determinism

With effective wire semantics:
- GateAtom.wires are effective indices (perm applied at emit time)
- Phase 4A checks if gates already avoid loop wires
"""

from __future__ import annotations

import pytest
from core.perm import WirePerm, identity, compose, inverse
from compile.goi import GateAtom, LoopSpec, GOIArtifact, loop_wires
from compile.loop_analysis import (
    ExternalizeWitness,
    gate_support,
    all_gates_support,
    gates_avoid_loops,
    analyze_feedback_eliminable,
    apply_witness,
)


# -----------------------------------------------------------------------------
# A1. Gate support
# -----------------------------------------------------------------------------

@pytest.mark.phase4a
def test_gate_support_single_qubit():
    """Gate support returns correct wire set for single-qubit gate."""
    atom = GateAtom("H", (2,))
    assert gate_support(atom) == {2}


@pytest.mark.phase4a
def test_gate_support_two_qubit():
    """Gate support returns correct wire set for two-qubit gate."""
    atom = GateAtom("CX", (1, 3))
    assert gate_support(atom) == {1, 3}


@pytest.mark.phase4a
def test_all_gates_support_union():
    """all_gates_support returns union of all gate supports."""
    atoms = (
        GateAtom("H", (0,)),
        GateAtom("S", (2,)),
        GateAtom("CX", (1, 3)),
    )
    assert all_gates_support(atoms) == {0, 1, 2, 3}


# -----------------------------------------------------------------------------
# A2. Loop-wire disjointness certification
# -----------------------------------------------------------------------------

@pytest.mark.phase4a
def test_gates_avoid_loops_when_disjoint():
    """Disjointness certified when gates don't touch loop wires."""
    atoms = (GateAtom("H", (0,)), GateAtom("S", (1,)))
    loop_wire_set = {2, 3}
    assert gates_avoid_loops(atoms, loop_wire_set)


@pytest.mark.phase4a
def test_gates_touch_loops_when_overlapping():
    """Disjointness fails when gate touches loop wire."""
    atoms = (GateAtom("H", (2,)),)  # Touches loop wire 2
    loop_wire_set = {2, 3}
    assert not gates_avoid_loops(atoms, loop_wire_set)


@pytest.mark.phase4a
def test_gates_avoid_loops_cx_outside():
    """CX gate entirely outside loop region passes."""
    atoms = (GateAtom("CX", (0, 1)),)
    loop_wire_set = {2, 3}
    assert gates_avoid_loops(atoms, loop_wire_set)


@pytest.mark.phase4a
def test_gates_touch_loops_cx_spans():
    """CX gate spanning into loop region fails."""
    atoms = (GateAtom("CX", (1, 2)),)
    loop_wire_set = {2, 3}
    assert not gates_avoid_loops(atoms, loop_wire_set)


# -----------------------------------------------------------------------------
# A3. Witness determinism
# -----------------------------------------------------------------------------

@pytest.mark.phase4a
def test_witness_determinism_same_input():
    """Same GOIArtifact produces identical witness."""
    goi = GOIArtifact(
        n_in=4,
        n_out=4,
        perm=identity(4),
        atoms=(GateAtom("H", (0,)), GateAtom("S", (1,))),
        loops=(LoopSpec(2),)
    )
    loop = goi.loops[0]

    w1 = analyze_feedback_eliminable(goi, loop)
    w2 = analyze_feedback_eliminable(goi, loop)

    assert w1 is not None
    assert w2 is not None
    assert w1.p_in.new_to_old == w2.p_in.new_to_old
    assert w1.p_out.new_to_old == w2.p_out.new_to_old
    assert w1.externalized_support == w2.externalized_support
    assert w1.loop_wire_set == w2.loop_wire_set


@pytest.mark.phase4a
def test_witness_for_already_disjoint():
    """Witness with identity perms when already disjoint."""
    goi = GOIArtifact(
        n_in=4,
        n_out=4,
        perm=identity(4),
        atoms=(GateAtom("H", (0,)),),  # Only touches wire 0
        loops=(LoopSpec(2),)  # Loop is wires 2, 3
    )
    loop = goi.loops[0]

    witness = analyze_feedback_eliminable(goi, loop)
    assert witness is not None
    # Should be identity witness
    assert witness.p_in.new_to_old == list(range(4))
    assert witness.p_out.new_to_old == list(range(4))
    assert witness.loop_wire_set == {2, 3}


@pytest.mark.phase4a
def test_no_witness_when_gate_in_loop():
    """No witness when gate touches loop wire."""
    goi = GOIArtifact(
        n_in=4,
        n_out=4,
        perm=identity(4),
        atoms=(GateAtom("CX", (0, 2)),),  # Touches loop wire 2
        loops=(LoopSpec(2),)
    )
    loop = goi.loops[0]

    witness = analyze_feedback_eliminable(goi, loop)
    # Cannot externalize - gate touches loop wire
    assert witness is None


@pytest.mark.phase4a
def test_no_witness_single_qubit_in_loop():
    """No witness when single-qubit gate is in loop region."""
    goi = GOIArtifact(
        n_in=4,
        n_out=4,
        perm=identity(4),
        atoms=(GateAtom("H", (2,)),),  # In loop wire 2
        loops=(LoopSpec(2),)  # Loop is wires 2, 3
    )
    loop = goi.loops[0]

    witness = analyze_feedback_eliminable(goi, loop)
    assert witness is None


# -----------------------------------------------------------------------------
# Apply witness tests
# -----------------------------------------------------------------------------

@pytest.mark.phase4a
def test_apply_identity_witness():
    """Applying identity witness doesn't change GOI structure."""
    goi = GOIArtifact(
        n_in=4,
        n_out=4,
        perm=identity(4),
        atoms=(GateAtom("H", (0,)),),
        loops=(LoopSpec(2),)
    )

    witness = ExternalizeWitness(
        p_in=identity(4),
        p_out=identity(4),
        externalized_support={0},
        loop_wire_set={2, 3}
    )

    result = apply_witness(goi, witness)
    # Atoms stay unchanged
    assert result.atoms[0].wires == (0,)
    assert result.perm.new_to_old == list(range(4))


@pytest.mark.phase4a
def test_apply_witness_preserves_atoms():
    """Applying witness preserves atom wires (effective indices)."""
    goi = GOIArtifact(
        n_in=4,
        n_out=4,
        perm=identity(4),
        atoms=(GateAtom("H", (0,)), GateAtom("S", (1,))),
        loops=()
    )

    # Even with non-identity witness perms, atoms are preserved
    p_in = WirePerm(4, [1, 0, 2, 3])
    witness = ExternalizeWitness(
        p_in=p_in,
        p_out=inverse(p_in),
        externalized_support={0, 1},
        loop_wire_set=set()
    )

    result = apply_witness(goi, witness)
    # Atoms stay unchanged (effective wire indices)
    assert result.atoms[0].wires == (0,)
    assert result.atoms[1].wires == (1,)
