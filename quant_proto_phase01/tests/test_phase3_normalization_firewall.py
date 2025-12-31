"""Phase 3 Test: Normalization Firewall.

Tests that structural rewrites (normalization) do not enter gate atoms:
- Atom identity preserved (types, order)
- Only wire indices changed
- Parameters and gate names untouched
"""
from __future__ import annotations

import pytest
from ._phase3_helpers import (
    make_goi_artifact, assert_atoms_equal,
    GateAtom, normalize_goi, identity,
)
from core.perm import WirePerm


@pytest.mark.phase3
class TestNormalizationFirewall:
    """A2: Normalization Firewall tests."""

    def test_atom_identity_preserved(self):
        """A2.1: Same atom types in same order after normalization."""
        # Create artifact with nontrivial perm (swap wires 0 and 1)
        goi = make_goi_artifact(
            n=3,
            atoms=[("H", (0,)), ("CX", (0, 2)), ("S", (1,))],
            perm=[1, 0, 2]  # swap first two wires
        )

        result = normalize_goi(goi)

        # Same number of atoms
        assert len(result.atoms) == len(goi.atoms)

        # Same gate types in same order
        for orig, norm in zip(goi.atoms, result.atoms):
            assert orig.gate_name == norm.gate_name

        # Resulting perm is identity
        assert result.perm.new_to_old == list(range(result.perm.n))

    def test_wire_indices_rewritten(self):
        """A2.1: Wire indices changed by perm.apply_new_to_old."""
        # perm = [1, 0, 2] swaps wires 0 and 1
        goi = make_goi_artifact(
            n=3,
            atoms=[("H", (0,)), ("S", (1,))],
            perm=[1, 0, 2]
        )

        result = normalize_goi(goi)

        # H was on wire 0, perm[0] = 1, so now on wire 1
        assert result.atoms[0].wires == (1,)
        # S was on wire 1, perm[1] = 0, so now on wire 0
        assert result.atoms[1].wires == (0,)

    def test_cx_both_wires_rewritten(self):
        """CX gate has both wires rewritten through perm."""
        goi = make_goi_artifact(
            n=3,
            atoms=[("CX", (0, 1))],
            perm=[2, 0, 1]  # 0->2, 1->0, 2->1
        )

        result = normalize_goi(goi)

        # CX was on (0, 1), after perm: (2, 0)
        assert result.atoms[0].wires == (2, 0)

    def test_opaque_atom_property(self):
        """A2.2: Gate name and structure unchanged, only wires change."""
        # Simulate a parametrized gate by using its name
        goi = make_goi_artifact(
            n=4,
            atoms=[
                ("Rz_0.5", (0,)),
                ("CX", (1, 2)),
                ("ExpH_pi", (3,))
            ],
            perm=[3, 2, 1, 0]  # full reversal
        )

        result = normalize_goi(goi)

        # Names preserved exactly
        assert [a.gate_name for a in result.atoms] == ["Rz_0.5", "CX", "ExpH_pi"]

        # Order preserved
        assert len(result.atoms) == 3

        # Wires rewritten (reversed)
        assert result.atoms[0].wires == (3,)  # 0 -> 3
        assert result.atoms[1].wires == (2, 1)  # (1,2) -> (2,1)
        assert result.atoms[2].wires == (0,)  # 3 -> 0

    def test_loops_preserved_verbatim(self):
        """Normalization does not alter loop specifications."""
        goi = make_goi_artifact(
            n=4,
            atoms=[("H", (0,))],
            loops=[2],
            perm=[1, 0, 2, 3]
        )

        result = normalize_goi(goi)

        # Loops unchanged
        assert len(result.loops) == len(goi.loops)
        assert result.loops[0].k == 2

    def test_multiple_normalizations_idempotent(self):
        """Normalizing twice gives same result as once."""
        goi = make_goi_artifact(
            n=3,
            atoms=[("H", (0,)), ("CX", (1, 2))],
            perm=[2, 1, 0]
        )

        r1 = normalize_goi(goi)
        r2 = normalize_goi(r1)

        # Should be identical (r1.perm is already identity)
        assert r1.perm.new_to_old == r2.perm.new_to_old
        for a1, a2 in zip(r1.atoms, r2.atoms):
            assert a1.gate_name == a2.gate_name
            assert a1.wires == a2.wires
