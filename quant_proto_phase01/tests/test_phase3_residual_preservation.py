"""Phase 3 Test: Residual Preservation.

Tests that extraction failure preserves all GOI information:
- Residual contains same atoms and loops
- No accidental materialization in residual path
- Failure is not an error
"""
from __future__ import annotations

import pytest
from ._phase3_helpers import (
    qpow, Q, Ten, Id, Seq, TenTerm, Feedback,
    H, S, CX,
    compile_goi,
    is_extracted, is_residual,
    GOIArtifact, CompiledGOI,
    make_goi_artifact, try_extract,
)


@pytest.mark.phase3
class TestResidualPreservation:
    """A5: Residual Preservation tests."""

    def test_extraction_failure_returns_residual(self):
        """A5.1: Extraction failure returns ResidualGOI, not error."""
        goi = make_goi_artifact(
            n=4,
            atoms=[("H", (3,))],  # touches loop wire
            loops=[2]  # loop wires = {2, 3}
        )

        result = try_extract(goi)

        assert is_residual(result)
        assert isinstance(result, GOIArtifact)

    def test_residual_contains_same_atoms(self):
        """A5.1: Residual contains the loop-touching gate."""
        goi = make_goi_artifact(
            n=4,
            atoms=[("H", (0,)), ("CX", (2, 3))],  # CX touches loop
            loops=[2]
        )

        result = try_extract(goi)

        assert is_residual(result)
        # Same atoms preserved
        assert len(result.atoms) == 2
        assert result.atoms[0].gate_name == "H"
        assert result.atoms[1].gate_name == "CX"

    def test_residual_contains_same_loops(self):
        """A5.1: Residual contains same loop spec."""
        goi = make_goi_artifact(
            n=4,
            atoms=[("H", (3,))],
            loops=[2]
        )

        result = try_extract(goi)

        assert is_residual(result)
        assert len(result.loops) == 1
        assert result.loops[0].k == 2

    def test_residual_preserves_routing_info(self):
        """A5.1: Residual preserves routing perm metadata."""
        goi = make_goi_artifact(
            n=4,
            atoms=[("H", (3,))],
            loops=[2],
            perm=[1, 0, 3, 2]  # nontrivial routing
        )

        result = try_extract(goi)

        assert is_residual(result)
        # Original perm preserved (not modified)
        assert result.perm.new_to_old == [1, 0, 3, 2]

    def test_no_materialization_in_residual_path(self):
        """A5.2: compile_goi with materialize=True still returns residual (no SWAPs)."""
        ty = qpow(2)
        body = H(1, ty)  # touches loop wire 1
        term = Feedback(k=1, body=body)

        result = compile_goi(term, materialize=True)

        # Should still be residual
        assert is_residual(result)
        assert isinstance(result, GOIArtifact)
        # No circuit was created, so no SWAPs

    def test_residual_stable_under_repeated_compilation(self):
        """Residual is stable across compilations."""
        ty = qpow(2)
        body = H(1, ty)
        term = Feedback(k=1, body=body)

        r1 = compile_goi(term)
        r2 = compile_goi(term)

        assert is_residual(r1) and is_residual(r2)

        # Same structure
        assert r1.n_in == r2.n_in
        assert r1.n_out == r2.n_out
        assert len(r1.atoms) == len(r2.atoms)
        assert len(r1.loops) == len(r2.loops)

        # Same atoms
        for a1, a2 in zip(r1.atoms, r2.atoms):
            assert a1.gate_name == a2.gate_name
            assert a1.wires == a2.wires

        # Same loops
        for l1, l2 in zip(r1.loops, r2.loops):
            assert l1.k == l2.k


@pytest.mark.phase3
class TestFailureIsNotError:
    """Extraction failure is a valid outcome, not an error."""

    def test_failure_does_not_raise(self):
        """try_extract does not raise on non-yankable input."""
        goi = make_goi_artifact(
            n=4,
            atoms=[("H", (3,))],
            loops=[2]
        )

        # Should not raise
        result = try_extract(goi)

        # Returns residual
        assert is_residual(result)

    def test_compile_goi_does_not_raise_on_residual(self):
        """compile_goi does not raise when extraction fails."""
        ty = qpow(2)
        body = H(1, ty)
        term = Feedback(k=1, body=body)

        # Should not raise
        result = compile_goi(term)

        assert is_residual(result)
