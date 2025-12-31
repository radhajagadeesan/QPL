"""Phase 3 Test: Feedback Elimination (Yankability).

Tests the yankability check and feedback collapse:
- Yankable when loop wires are untouched
- Not yankable when any atom touches a loop wire
- Collapse produces correct boundary permutation
"""
from __future__ import annotations

import pytest
from ._phase3_helpers import (
    make_goi_artifact, is_extracted, is_residual,
    GateAtom, LoopSpec, GOIArtifact, Extracted,
    normalize_goi, is_yankable, collapse_feedback, try_extract,
    identity,
)
from core.perm import WirePerm


@pytest.mark.phase3
class TestYankability:
    """A3: Yankability (Eliminability) Check tests."""

    def test_yankable_when_loop_wires_untouched(self):
        """A3.1: Yankable when no gate touches loop wires."""
        # n_out = 6, loop k = 2, loop wires = {4, 5}
        # atoms only touch {0, 1, 2, 3}
        goi = make_goi_artifact(
            n=6,
            atoms=[
                ("H", (0,)),
                ("CX", (1, 2)),
                ("S", (3,))
            ],
            loops=[2]
        )

        assert is_yankable(goi) is True

    def test_not_yankable_single_qubit_gate_on_loop(self):
        """A3.2: Not yankable when a single-qubit gate touches loop wire."""
        # n = 6, k = 2, loop wires = {4, 5}
        # H on wire 5 (in loop)
        goi = make_goi_artifact(
            n=6,
            atoms=[
                ("H", (0,)),
                ("H", (5,))  # touches loop wire
            ],
            loops=[2]
        )

        assert is_yankable(goi) is False

    def test_not_yankable_cx_intersects_loop(self):
        """A3.3: Not yankable when multi-wire gate intersects loop."""
        # CX on (3, 4) where 4 is in loop
        goi = make_goi_artifact(
            n=6,
            atoms=[("CX", (3, 4))],
            loops=[2]  # loop wires = {4, 5}
        )

        assert is_yankable(goi) is False

    def test_yankable_with_no_loops(self):
        """No loops means always yankable (trivially)."""
        goi = make_goi_artifact(
            n=4,
            atoms=[("H", (0,)), ("CX", (1, 2))]
        )

        assert is_yankable(goi) is True

    def test_yankable_empty_atoms(self):
        """Empty atom list with loop is yankable."""
        goi = make_goi_artifact(
            n=4,
            atoms=[],
            loops=[2]
        )

        assert is_yankable(goi) is True


@pytest.mark.phase3
class TestFeedbackCollapse:
    """A4: Feedback Collapse tests."""

    def test_collapse_preserves_atoms(self):
        """A4.1: Collapse returns unchanged atom list."""
        goi = make_goi_artifact(
            n=4,
            atoms=[("H", (0,)), ("S", (1,))],
            loops=[2]  # loop wires = {2, 3}
        )

        # Normalize first (required for proper collapse)
        goi_norm = normalize_goi(goi)

        result = try_extract(goi_norm)

        assert is_extracted(result)
        assert isinstance(result, Extracted)
        # Same atoms (but possibly different wires after normalization)
        assert len(result.atoms) == len(goi.atoms)

    def test_collapse_removes_loop(self):
        """A4.1: Successful extraction removes loop."""
        goi = make_goi_artifact(
            n=4,
            atoms=[("H", (0,))],
            loops=[2]
        )

        result = try_extract(goi)

        assert is_extracted(result)
        # Extracted result has no loops (it's atoms + perm)

    def test_collapse_returns_boundary_perm(self):
        """A4.1: Collapse returns boundary permutation on external wires."""
        # 4 wires, loop of 2 -> external = 2 wires
        goi = make_goi_artifact(
            n=4,
            atoms=[("H", (0,))],
            loops=[2]
        )

        result = try_extract(goi)

        assert is_extracted(result)
        assert isinstance(result, Extracted)
        # Perm should be on external_size = 4 - 2 = 2 wires
        assert result.perm.n == 2

    def test_collapse_with_nontrivial_routing(self):
        """A4.2: Collapse depends only on routing when yankable."""
        # Two identical GOIs except atom list
        goi1 = make_goi_artifact(
            n=4,
            atoms=[("H", (0,))],
            loops=[2]
        )
        goi2 = make_goi_artifact(
            n=4,
            atoms=[("H", (0,)), ("S", (1,))],
            loops=[2]
        )

        r1 = try_extract(goi1)
        r2 = try_extract(goi2)

        assert is_extracted(r1) and is_extracted(r2)
        # Same boundary perm since routing (identity) is the same
        assert r1.perm.new_to_old == r2.perm.new_to_old


@pytest.mark.phase3
class TestTryExtract:
    """Full try_extract integration tests."""

    def test_extract_success_yankable(self):
        """Extraction succeeds for yankable GOI."""
        goi = make_goi_artifact(
            n=4,
            atoms=[("H", (0,)), ("CX", (0, 1))],
            loops=[2]  # loop wires = {2, 3}, atoms don't touch
        )

        result = try_extract(goi)

        assert is_extracted(result)
        assert isinstance(result, Extracted)

    def test_extract_fails_not_yankable(self):
        """Extraction fails for non-yankable GOI, returns residual."""
        goi = make_goi_artifact(
            n=4,
            atoms=[("H", (3,))],  # touches loop wire
            loops=[2]
        )

        result = try_extract(goi)

        assert is_residual(result)
        assert isinstance(result, GOIArtifact)
        # Original GOI preserved
        assert result.loops == goi.loops

    def test_extract_trivial_no_loops(self):
        """Extraction of GOI with no loops succeeds immediately."""
        goi = make_goi_artifact(
            n=3,
            atoms=[("H", (0,)), ("S", (1,))]
        )

        result = try_extract(goi)

        assert is_extracted(result)
        # Same atoms and perm
        assert len(result.atoms) == 2
        assert result.perm.n == 3

    def test_extract_determinism(self):
        """A6.2: try_extract is deterministic."""
        goi = make_goi_artifact(
            n=4,
            atoms=[("H", (0,)), ("CX", (0, 1))],
            loops=[2]
        )

        r1 = try_extract(goi)
        r2 = try_extract(goi)

        # Both should be identical
        if is_extracted(r1):
            assert is_extracted(r2)
            assert r1.atoms == r2.atoms
            assert r1.perm.new_to_old == r2.perm.new_to_old
        else:
            assert is_residual(r2)
