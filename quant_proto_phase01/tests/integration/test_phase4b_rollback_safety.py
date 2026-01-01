# tests/integration/test_phase4b_rollback_safety.py
"""Phase 4B Rollback Safety Tests (Section 2.2 of Integration Plan).

Tests verify that when ZX extraction fails, the original residual is
returned unchanged (byte-identical serialization).

This guards against:
1. Partial normalization leaking into residuals
2. Structural modification without successful extraction
3. Lost information during failed translation/rewrite
"""

from __future__ import annotations

import pytest

from .helpers import (
    qpow, Q, Ten,
    Id, Seq, TenTerm, H, S, CX, TwistTen, AssocTenL, Feedback,
    residual_fingerprint, perm_to_list,
)
from compile.to_pytket import compile_goi, CompiledGOI
from compile.goi import GOIArtifact
from compile.extract_zx import is_pyzx_available, try_extract_zx


pytestmark = pytest.mark.skipif(
    not is_pyzx_available(),
    reason="PyZX not installed"
)


def mk_rollback_test_corpus():
    """Cases that trigger various failure paths in ZX extraction.

    IMPORTANT: We avoid structure that remaps external wires to loop wires,
    as that causes issues with collapse_feedback.
    """
    q3 = qpow(3)
    q4 = qpow(4)
    q5 = qpow(5)

    return {
        # Simple cases that fail due to gate-loop interaction
        "rb_simple_gate_on_loop": Feedback(k=1, body=H(2, q3)),
        "rb_cx_spans_loop": Feedback(k=1, body=CX(1, 2, q3)),

        # Multiple gates on loop wire
        "rb_multi_gate_on_loop": Feedback(
            k=1,
            body=Seq(H(2, q3), S(2, q3))
        ),

        # Large feedback with gate on loop
        "rb_large_k": Feedback(k=3, body=H(2, q5)),

        # Mixed gates, last one touches loop
        "rb_mixed_last_loop": Feedback(
            k=1,
            body=Seq(H(0, q3), S(1, q3), H(2, q3))
        ),

        # CX with both on loop (k=2)
        "rb_cx_both_loop": Feedback(k=2, body=CX(2, 3, q4)),
    }


class TestRollbackSafety:
    """Test that failed ZX extraction returns original residual unchanged."""

    @pytest.mark.phase4b
    @pytest.mark.parametrize("name,term", list(mk_rollback_test_corpus().items()))
    def test_rollback_preserves_residual_exactly(self, name, term):
        """When ZX fails, residual is byte-identical to input."""
        # Get the Phase 4A residual
        res_baseline = compile_goi(term, materialize=False, enable_zx=False)
        assert isinstance(res_baseline, GOIArtifact), f"{name} must be residual"

        # Get the Phase 4B result
        res_zx = compile_goi(term, materialize=False, enable_zx=True)
        assert isinstance(res_zx, GOIArtifact), f"{name} must still be residual after ZX"

        # Verify byte-identical (via fingerprint)
        assert residual_fingerprint(res_baseline) == residual_fingerprint(res_zx), \
            f"{name}: rollback did not preserve residual exactly"

    @pytest.mark.phase4b
    @pytest.mark.parametrize("name,term", list(mk_rollback_test_corpus().items()))
    def test_rollback_preserves_atoms(self, name, term):
        """Atoms are unchanged after failed ZX extraction."""
        res_baseline = compile_goi(term, materialize=False, enable_zx=False)
        res_zx = compile_goi(term, materialize=False, enable_zx=True)

        assert isinstance(res_baseline, GOIArtifact)
        assert isinstance(res_zx, GOIArtifact)

        # Same number of atoms
        assert len(res_baseline.atoms) == len(res_zx.atoms)

        # Same atom content
        for a1, a2 in zip(res_baseline.atoms, res_zx.atoms):
            assert a1.gate_name == a2.gate_name
            assert a1.wires == a2.wires

    @pytest.mark.phase4b
    @pytest.mark.parametrize("name,term", list(mk_rollback_test_corpus().items()))
    def test_rollback_preserves_loops(self, name, term):
        """Loop structure is unchanged after failed ZX extraction."""
        res_baseline = compile_goi(term, materialize=False, enable_zx=False)
        res_zx = compile_goi(term, materialize=False, enable_zx=True)

        assert isinstance(res_baseline, GOIArtifact)
        assert isinstance(res_zx, GOIArtifact)

        # Same number of loops
        assert len(res_baseline.loops) == len(res_zx.loops)

        # Same loop sizes
        for l1, l2 in zip(res_baseline.loops, res_zx.loops):
            assert l1.k == l2.k

    @pytest.mark.phase4b
    @pytest.mark.parametrize("name,term", list(mk_rollback_test_corpus().items()))
    def test_rollback_preserves_perm(self, name, term):
        """Permutation is unchanged after failed ZX extraction."""
        res_baseline = compile_goi(term, materialize=False, enable_zx=False)
        res_zx = compile_goi(term, materialize=False, enable_zx=True)

        assert isinstance(res_baseline, GOIArtifact)
        assert isinstance(res_zx, GOIArtifact)

        # Same perm
        assert perm_to_list(res_baseline.perm) == perm_to_list(res_zx.perm)

    @pytest.mark.phase4b
    @pytest.mark.parametrize("name,term", list(mk_rollback_test_corpus().items()))
    def test_rollback_preserves_boundary_sizes(self, name, term):
        """Boundary sizes (n_in, n_out) unchanged after failed ZX extraction."""
        res_baseline = compile_goi(term, materialize=False, enable_zx=False)
        res_zx = compile_goi(term, materialize=False, enable_zx=True)

        assert isinstance(res_baseline, GOIArtifact)
        assert isinstance(res_zx, GOIArtifact)

        assert res_baseline.n_in == res_zx.n_in
        assert res_baseline.n_out == res_zx.n_out


class TestDirectTryExtractZXRollback:
    """Test try_extract_zx directly for rollback behavior."""

    @pytest.mark.phase4b
    def test_try_extract_zx_returns_same_object_on_failure(self):
        """try_extract_zx returns the input GOIArtifact on failure."""
        q3 = qpow(3)
        term = Feedback(k=1, body=H(2, q3))

        # Get residual
        res = compile_goi(term, materialize=False, enable_zx=False)
        assert isinstance(res, GOIArtifact)

        # Call try_extract_zx directly
        result = try_extract_zx(res)

        # Should return GOIArtifact (not Extracted)
        assert isinstance(result, GOIArtifact)

        # Should be the same structure
        assert residual_fingerprint(res) == residual_fingerprint(result)
