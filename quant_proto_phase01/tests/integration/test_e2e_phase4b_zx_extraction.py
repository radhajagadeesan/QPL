# tests/integration/test_e2e_phase4b_zx_extraction.py
"""Phase 4B integration tests: ZX-based residual extraction.

Tests verify:
1. Phase 4A behavior preserved when enable_zx=False
2. enable_zx=True doesn't change Phase 3/4A extractable cases
3. ZX extraction uses deterministic rewrites only
4. Residual preservation when ZX cannot extract
5. Basic ZX translation and extraction
"""

from __future__ import annotations

import pytest
from .helpers import (
    qpow, Q, Ten,
    Id, Seq, TenTerm, H, S, CX, TwistTen, Feedback,
    mk_phase0_acyclic_corpus, mk_phase1_structure_corpus,
    mk_phase2_tenterm_corpus, mk_phase3_extractable_corpus,
    mk_phase4a_residual_corpus,
    compile_goi_safe, assert_no_swaps, non_swap_signature,
    compile_term, is_goi_artifact,
)
from compile.goi import GOIArtifact
from compile.to_pytket import compile_goi, CompiledGOI
from compile.extract_zx import is_pyzx_available, try_extract_zx, to_pyzx_graph


# Skip all tests if PyZX not available
pytestmark = pytest.mark.skipif(
    not is_pyzx_available(),
    reason="PyZX not installed"
)


class TestPhase4BPreservation:
    """Tests that Phase 4B preserves all earlier phase behavior."""

    @pytest.mark.phase4b
    @pytest.mark.parametrize("name,term", list(mk_phase0_acyclic_corpus().items()))
    def test_phase0_unchanged_with_enable_zx(self, name, term):
        """Phase 0 acyclic terms produce identical output with or without enable_zx."""
        res_off = compile_goi(term, materialize=False, enable_zx=False)
        res_on = compile_goi(term, materialize=False, enable_zx=True)

        # Both must extract (not residual)
        assert isinstance(res_off, CompiledGOI), f"{name} should extract with enable_zx=False"
        assert isinstance(res_on, CompiledGOI), f"{name} should extract with enable_zx=True"

        # Same circuit output
        assert non_swap_signature(res_off.circuit) == non_swap_signature(res_on.circuit)
        assert list(res_off.perm.new_to_old) == list(res_on.perm.new_to_old)

    @pytest.mark.phase4b
    @pytest.mark.parametrize("name,term", list(mk_phase1_structure_corpus().items()))
    def test_phase1_unchanged_with_enable_zx(self, name, term):
        """Phase 1 structural terms produce identical output with or without enable_zx."""
        res_off = compile_goi(term, materialize=False, enable_zx=False)
        res_on = compile_goi(term, materialize=False, enable_zx=True)

        assert isinstance(res_off, CompiledGOI), f"{name} should extract with enable_zx=False"
        assert isinstance(res_on, CompiledGOI), f"{name} should extract with enable_zx=True"

        assert non_swap_signature(res_off.circuit) == non_swap_signature(res_on.circuit)
        assert list(res_off.perm.new_to_old) == list(res_on.perm.new_to_old)

    @pytest.mark.phase4b
    @pytest.mark.parametrize("name,term", list(mk_phase2_tenterm_corpus().items()))
    def test_phase2_unchanged_with_enable_zx(self, name, term):
        """Phase 2 TenTerm terms produce identical output with or without enable_zx."""
        res_off = compile_goi(term, materialize=False, enable_zx=False)
        res_on = compile_goi(term, materialize=False, enable_zx=True)

        assert isinstance(res_off, CompiledGOI), f"{name} should extract with enable_zx=False"
        assert isinstance(res_on, CompiledGOI), f"{name} should extract with enable_zx=True"

        assert non_swap_signature(res_off.circuit) == non_swap_signature(res_on.circuit)
        assert list(res_off.perm.new_to_old) == list(res_on.perm.new_to_old)

    @pytest.mark.phase4b
    @pytest.mark.parametrize("name,term", list(mk_phase3_extractable_corpus().items()))
    def test_phase3_yankable_unchanged_with_enable_zx(self, name, term):
        """Phase 3 yankable feedback terms produce identical output with or without enable_zx."""
        res_off = compile_goi(term, materialize=False, enable_zx=False)
        res_on = compile_goi(term, materialize=False, enable_zx=True)

        assert isinstance(res_off, CompiledGOI), f"{name} should extract with enable_zx=False"
        assert isinstance(res_on, CompiledGOI), f"{name} should extract with enable_zx=True"

        assert non_swap_signature(res_off.circuit) == non_swap_signature(res_on.circuit)
        assert list(res_off.perm.new_to_old) == list(res_on.perm.new_to_old)


class TestPhase4BZXTranslation:
    """Tests for ZX graph translation."""

    @pytest.mark.phase4b
    def test_to_pyzx_graph_basic(self):
        """Basic GOIArtifact translates to valid PyZX graph."""
        q3 = qpow(3)
        term = Feedback(k=1, body=H(2, q3))  # H on loop wire - non-yankable

        res = compile_goi(term, materialize=False, enable_zx=False)
        assert isinstance(res, GOIArtifact), "Should be residual without ZX"

        # Translate to ZX
        g = to_pyzx_graph(res)

        # Graph should have vertices
        assert len(list(g.vertices())) > 0
        # Should have inputs and outputs
        assert len(g.inputs()) > 0
        assert len(g.outputs()) > 0

    @pytest.mark.phase4b
    def test_to_pyzx_graph_preserves_gate_info(self):
        """Gate atoms preserve gate_name and wires in ZX graph."""
        q3 = qpow(3)
        term = Feedback(k=1, body=Seq(H(2, q3), S(2, q3)))  # Gates on loop wire

        res = compile_goi(term, materialize=False, enable_zx=False)
        assert isinstance(res, GOIArtifact)

        g = to_pyzx_graph(res)

        # Check Z_BOX vertices have gate data
        import pyzx
        from pyzx.utils import VertexType

        z_box_count = 0
        for v in g.vertices():
            if g.type(v) == VertexType.Z_BOX:
                z_box_count += 1
                gate_name = g.vdata(v, 'gate_name')
                wires = g.vdata(v, 'wires')
                assert gate_name in ("H", "S", "CX")
                assert wires is not None

        assert z_box_count >= 2, "Should have at least 2 gate boxes"


class TestPhase4BDeterminism:
    """Tests that Phase 4B is deterministic."""

    @pytest.mark.phase4b
    @pytest.mark.parametrize("name,term", list(mk_phase4a_residual_corpus().items()))
    def test_zx_extraction_is_deterministic(self, name, term):
        """ZX extraction produces identical results across multiple runs."""
        results = []
        for _ in range(3):
            res = compile_goi(term, materialize=False, enable_zx=True)
            if isinstance(res, CompiledGOI):
                sig = non_swap_signature(res.circuit)
                perm = list(res.perm.new_to_old)
                results.append((sig, perm))
            else:
                # Still residual - that's also deterministic
                results.append(("residual", list(res.perm.new_to_old), len(res.atoms)))

        # All results should be identical
        for r in results[1:]:
            assert r == results[0], f"Non-deterministic result for {name}"


class TestPhase4BResidualHandling:
    """Tests for residual handling in Phase 4B."""

    @pytest.mark.phase4b
    def test_residual_preserved_when_zx_cannot_extract(self):
        """Residuals remain residuals when ZX simplification cannot extract."""
        # Create a term that has genuine feedback structure
        q3 = qpow(3)
        # CX touching loop wire makes it non-yankable
        term = Feedback(k=1, body=CX(1, 2, q3))

        res = compile_goi(term, materialize=False, enable_zx=True)

        # Should still be residual (ZX can't always extract)
        # This is acceptable - Phase 4B is not guaranteed to extract everything
        if isinstance(res, GOIArtifact):
            # Residual should have loops
            assert len(res.loops) > 0
            # Atoms should be preserved
            assert len(res.atoms) > 0

    @pytest.mark.phase4b
    @pytest.mark.parametrize("name,term", list(mk_phase4a_residual_corpus().items()))
    def test_residual_structure_preserved(self, name, term):
        """Residual structure (atoms, loops, perm) is preserved when ZX cannot extract."""
        res_off = compile_goi(term, materialize=False, enable_zx=False)
        res_on = compile_goi(term, materialize=False, enable_zx=True)

        if isinstance(res_off, GOIArtifact) and isinstance(res_on, GOIArtifact):
            # If both residual, structure should be identical
            assert len(res_off.atoms) == len(res_on.atoms)
            assert len(res_off.loops) == len(res_on.loops)


class TestPhase4BNoSwapPolicy:
    """Tests that Phase 4B maintains the no-SWAP policy."""

    @pytest.mark.phase4b
    @pytest.mark.parametrize("name,term", list(mk_phase0_acyclic_corpus().items())[:5])
    def test_no_swaps_with_enable_zx(self, name, term):
        """No SWAPs emitted when materialize=False and enable_zx=True."""
        res = compile_goi(term, materialize=False, enable_zx=True)

        if isinstance(res, CompiledGOI):
            assert_no_swaps(res.circuit)

    @pytest.mark.phase4b
    @pytest.mark.parametrize("name,term", list(mk_phase3_extractable_corpus().items()))
    def test_no_swaps_on_yankable_with_enable_zx(self, name, term):
        """No SWAPs on yankable feedback with enable_zx=True."""
        res = compile_goi(term, materialize=False, enable_zx=True)

        if isinstance(res, CompiledGOI):
            assert_no_swaps(res.circuit)


class TestPhase4BExplainMode:
    """Tests for explain mode with Phase 4B."""

    @pytest.mark.phase4b
    def test_explain_logs_zx_attempts(self):
        """explain=True logs ZX extraction attempts."""
        q3 = qpow(3)
        term = Feedback(k=1, body=H(2, q3))  # Non-yankable

        res = compile_goi(term, materialize=False, enable_zx=True, explain=True)

        # With explain mode, we should get log info
        # The result may be CompiledGOI or GOIArtifact depending on ZX success
        if isinstance(res, CompiledGOI):
            assert res.log is not None
            # Should mention ZX extraction
            log_text = " ".join(res.log)
            assert "4B" in log_text or "ZX" in log_text or "extraction" in log_text.lower()
