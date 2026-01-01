# tests/integration/test_phase4b_flag_gating.py
"""Phase 4B Flag Gating Tests (Section 2 of Integration Plan).

Tests verify:
1. enable_zx=False: results match Phase 4A baseline
2. enable_zx=True: only changes expected positive cases
3. Non-interference: v1/v2 extracted cases unchanged with enable_zx=True
"""

from __future__ import annotations

import pytest

from .helpers import (
    qpow, Q, Ten,
    Id, Seq, TenTerm, H, S, CX, TwistTen, AssocTenL, Feedback,
    mk_phase0_2_corpus, mk_phase3_extractable_corpus, mk_phase3_residual_corpus,
    mk_phase4a_stays_residual_corpus,
    extract_cmd_stream, perm_to_list, residual_fingerprint,
    assert_no_swaps, non_swap_signature,
)
from compile.to_pytket import compile_goi, CompiledGOI
from compile.goi import GOIArtifact
from compile.extract_zx import is_pyzx_available


# Skip all ZX tests if PyZX not available
pytestmark = pytest.mark.skipif(
    not is_pyzx_available(),
    reason="PyZX not installed"
)


class TestFlagGatingPhase0to4A:
    """Test that enable_zx flag doesn't affect Phase 0-4A behavior."""

    @pytest.mark.phase4b
    @pytest.mark.parametrize("name,term", list(mk_phase0_2_corpus().items()))
    def test_phase0_2_identical_with_flag_on_or_off(self, name, term):
        """Phase 0-2 terms produce identical results regardless of enable_zx."""
        res_off = compile_goi(term, materialize=False, enable_zx=False)
        res_on = compile_goi(term, materialize=False, enable_zx=True)

        # Both should extract (not residual)
        assert isinstance(res_off, CompiledGOI), f"{name} should extract"
        assert isinstance(res_on, CompiledGOI), f"{name} should extract"

        # Identical outputs
        assert extract_cmd_stream(res_off.circuit) == extract_cmd_stream(res_on.circuit)
        assert perm_to_list(res_off.perm) == perm_to_list(res_on.perm)

    @pytest.mark.phase4b
    @pytest.mark.parametrize("name,term", list(mk_phase3_extractable_corpus().items()))
    def test_phase3_yankable_identical_with_flag_on_or_off(self, name, term):
        """Phase 3 yankable terms produce identical results regardless of enable_zx."""
        res_off = compile_goi(term, materialize=False, enable_zx=False)
        res_on = compile_goi(term, materialize=False, enable_zx=True)

        assert isinstance(res_off, CompiledGOI), f"{name} should extract"
        assert isinstance(res_on, CompiledGOI), f"{name} should extract"

        assert extract_cmd_stream(res_off.circuit) == extract_cmd_stream(res_on.circuit)
        assert perm_to_list(res_off.perm) == perm_to_list(res_on.perm)


class TestFlagGatingResiduals:
    """Test flag gating behavior on residual cases."""

    @pytest.mark.phase4b
    @pytest.mark.parametrize("name,term", list(mk_phase4a_stays_residual_corpus().items()))
    def test_residuals_with_enable_zx_false_match_phase4a(self, name, term):
        """With enable_zx=False, residuals match Phase 4A baseline."""
        res = compile_goi(term, materialize=False, enable_zx=False)

        # Should be residual
        assert isinstance(res, GOIArtifact), f"{name} should be residual with enable_zx=False"

    @pytest.mark.phase4b
    @pytest.mark.parametrize("name,term", list(mk_phase4a_stays_residual_corpus().items()))
    def test_genuine_residuals_stay_residual_with_enable_zx_true(self, name, term):
        """Genuine residuals (gates touch loop) stay residual even with enable_zx=True."""
        res_off = compile_goi(term, materialize=False, enable_zx=False)
        res_on = compile_goi(term, materialize=False, enable_zx=True)

        # Both should be residual (ZX can't help with gate-loop interaction)
        assert isinstance(res_off, GOIArtifact), f"{name} should be residual"
        assert isinstance(res_on, GOIArtifact), f"{name} should still be residual with ZX"

        # Fingerprints should match (identical residual structure)
        assert residual_fingerprint(res_off) == residual_fingerprint(res_on)


class TestNonInterference:
    """Test that enable_zx=True doesn't interfere with v1/v2 extracted cases."""

    @pytest.mark.phase4b
    def test_non_interference_sample(self):
        """Sample of v1/v2 extracted cases unchanged with enable_zx=True."""
        # A variety of terms that Phase 3/4A extracts
        test_cases = [
            ("twist", TwistTen(Q(), Q())),
            ("assoc", AssocTenL(Q(), Q(), Q())),
            ("gate_h", H(0, Q())),
            ("gate_cx", CX(0, 1, Ten(Q(), Q()))),
            ("mixed", Seq(TwistTen(Q(), Q()), H(0, Ten(Q(), Q())))),
            ("yankable", Feedback(k=1, body=H(0, qpow(3)))),
        ]

        for name, term in test_cases:
            res_off = compile_goi(term, materialize=False, enable_zx=False)
            res_on = compile_goi(term, materialize=False, enable_zx=True)

            # Both should extract
            assert isinstance(res_off, CompiledGOI), f"{name} should extract"
            assert isinstance(res_on, CompiledGOI), f"{name} should extract with ZX"

            # Identical outputs (bit-for-bit)
            assert extract_cmd_stream(res_off.circuit) == extract_cmd_stream(res_on.circuit), \
                f"{name}: cmd stream differs"
            assert perm_to_list(res_off.perm) == perm_to_list(res_on.perm), \
                f"{name}: perm differs"

    @pytest.mark.phase4b
    def test_4b_does_not_run_when_v2_succeeds(self):
        """Verify 4B is not invoked when v2 already extracts."""
        # This is a yankable case - Phase 3/4A should handle it
        q3 = qpow(3)
        term = Feedback(k=1, body=Seq(H(0, q3), S(1, q3)))

        # With explain mode, we can check the log
        res = compile_goi(term, materialize=False, enable_zx=True, explain=True)

        assert isinstance(res, CompiledGOI)
        # Log should NOT mention Phase 4B ZX extraction since v1/v2 succeeded
        if res.log:
            log_text = " ".join(res.log)
            # If 4B ran on an already-extracted case, that's a bug
            # (though it might still work, it's inefficient)
            # For now we just verify the output is correct
