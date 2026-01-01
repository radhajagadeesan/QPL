# tests/integration/test_phase4b_negative_residuals.py
"""Phase 4B Negative Corpus Tests (Section 4 of Integration Plan).

Tests for cases that MUST remain residual to ensure soundness:
1. Genuine gate-feedback interaction
2. Nested feedback with gate involvement
3. Opaque gate barriers blocking routing-only simplification

These tests guard against over-extraction.
"""

from __future__ import annotations

import pytest

from .helpers import (
    qpow, Q, Ten,
    Id, Seq, TenTerm, H, S, CX, TwistTen, AssocTenL, Feedback,
    extract_cmd_stream, perm_to_list, residual_fingerprint,
)
from compile.to_pytket import compile_goi, CompiledGOI
from compile.goi import GOIArtifact
from compile.extract_zx import is_pyzx_available


pytestmark = pytest.mark.skipif(
    not is_pyzx_available(),
    reason="PyZX not installed"
)


def mk_phase4b_negative_corpus():
    """Cases that MUST remain residual for soundness.

    These have genuine gate-loop interaction that cannot be eliminated
    by routing-only rewrites.

    IMPORTANT: We avoid structure that remaps external wires to loop wires,
    as that causes collapse_feedback to fail. The goal is to test cases
    where gates genuinely touch loop wires.
    """
    q3 = qpow(3)
    q4 = qpow(4)
    q5 = qpow(5)

    return {
        # === Genuine gate-feedback interaction ===
        # Gate directly on loop wire
        "neg_h_on_loop": Feedback(k=1, body=H(2, q3)),
        "neg_s_on_loop": Feedback(k=1, body=S(2, q3)),

        # CX spanning into loop
        "neg_cx_spans_loop": Feedback(k=1, body=CX(1, 2, q3)),

        # CX with both qubits on loop
        "neg_cx_both_loop": Feedback(k=2, body=CX(2, 3, q4)),

        # Mixed: some gates ok, but one touches loop
        "neg_mixed_touch": Feedback(
            k=1,
            body=Seq(H(0, q3), H(2, q3))  # H(0) ok, H(2) touches loop
        ),

        # Gate at start touches loop
        "neg_seq_first_touches": Feedback(
            k=1,
            body=Seq(H(2, q3), H(0, q3), S(0, q3))
        ),

        # Multiple gates on loop
        "neg_multiple_on_loop": Feedback(
            k=1,
            body=Seq(H(2, q3), S(2, q3))
        ),

        # k=2 with gate on first loop wire
        "neg_k2_first_loop": Feedback(k=2, body=H(2, q4)),

        # k=2 with gate on second loop wire
        "neg_k2_second_loop": Feedback(k=2, body=H(3, q4)),

        # k=2 with CX spanning both loop wires
        "neg_k2_cx_both_loops": Feedback(k=2, body=CX(2, 3, q4)),

        # Gate on loop then simple gate on external
        "neg_loop_gate_then_ext": Feedback(
            k=1,
            body=Seq(H(2, q3), H(0, q3))
        ),

        # === Large feedback (k=3) ===
        "neg_k3_gate_on_loop": Feedback(k=3, body=H(2, q5)),
        "neg_k3_gate_on_last_loop": Feedback(k=3, body=H(4, q5)),
    }


class TestPhase4BNegativeCorpusMustRemainResidual:
    """Test that negative corpus cases remain residual with enable_zx=True."""

    @pytest.mark.phase4b
    @pytest.mark.parametrize("name,term", list(mk_phase4b_negative_corpus().items()))
    def test_negative_case_is_residual_with_enable_zx_false(self, name, term):
        """Negative cases are residual with enable_zx=False (Phase 4A baseline)."""
        res = compile_goi(term, materialize=False, enable_zx=False)
        assert isinstance(res, GOIArtifact), f"{name} must be residual in Phase 4A"

    @pytest.mark.phase4b
    @pytest.mark.parametrize("name,term", list(mk_phase4b_negative_corpus().items()))
    def test_negative_case_stays_residual_with_enable_zx_true(self, name, term):
        """Negative cases MUST remain residual with enable_zx=True."""
        res = compile_goi(term, materialize=False, enable_zx=True)
        assert isinstance(res, GOIArtifact), \
            f"{name} MUST remain residual - extraction would be unsound"

    @pytest.mark.phase4b
    @pytest.mark.parametrize("name,term", list(mk_phase4b_negative_corpus().items()))
    def test_negative_residual_identical_with_or_without_zx(self, name, term):
        """Negative residuals are byte-identical with or without enable_zx."""
        res_off = compile_goi(term, materialize=False, enable_zx=False)
        res_on = compile_goi(term, materialize=False, enable_zx=True)

        # Both residual
        assert isinstance(res_off, GOIArtifact)
        assert isinstance(res_on, GOIArtifact)

        # Fingerprints identical
        assert residual_fingerprint(res_off) == residual_fingerprint(res_on), \
            f"{name}: residual structure differs (no partial normalization leakage)"


class TestPhase4BNegativeCorpusProperties:
    """Test invariant properties of negative corpus."""

    @pytest.mark.phase4b
    def test_all_negative_have_loops(self):
        """All negative cases must have feedback loops."""
        for name, term in mk_phase4b_negative_corpus().items():
            res = compile_goi(term, materialize=False, enable_zx=True)
            assert isinstance(res, GOIArtifact), f"{name} should be residual"
            assert len(res.loops) > 0, f"{name} residual must have loops"

    @pytest.mark.phase4b
    def test_all_negative_have_gate_loop_interaction(self):
        """All negative cases have gates touching loop wires."""
        for name, term in mk_phase4b_negative_corpus().items():
            res = compile_goi(term, materialize=False, enable_zx=True)
            assert isinstance(res, GOIArtifact)

            # Check that at least one atom has a wire in the loop range
            loop_size = sum(loop.k for loop in res.loops)
            external_size = res.n_out - loop_size

            has_loop_touch = False
            for atom in res.atoms:
                for w in atom.wires:
                    if w >= external_size:
                        has_loop_touch = True
                        break
                if has_loop_touch:
                    break

            assert has_loop_touch, f"{name}: no gate touches loop (shouldn't be negative)"

    @pytest.mark.phase4b
    @pytest.mark.parametrize("name,term", list(mk_phase4b_negative_corpus().items()))
    def test_negative_deterministic(self, name, term):
        """Negative corpus produces deterministic residuals."""
        fingerprints = []
        for _ in range(3):
            res = compile_goi(term, materialize=False, enable_zx=True)
            assert isinstance(res, GOIArtifact)
            fingerprints.append(residual_fingerprint(res))

        assert all(fp == fingerprints[0] for fp in fingerprints), \
            f"{name}: non-deterministic residual"


class TestPhase4BNoPartialNormalization:
    """Test that ZX pass doesn't leak partial normalization into residuals."""

    @pytest.mark.phase4b
    def test_no_partial_normalization(self):
        """ZX pass must not partially normalize then return modified residual."""
        # Pick a case without structure that remaps wires
        q3 = qpow(3)
        term = Feedback(
            k=1,
            body=Seq(H(0, q3), S(1, q3), H(2, q3))  # H(2) on loop
        )

        res_off = compile_goi(term, materialize=False, enable_zx=False)
        res_on = compile_goi(term, materialize=False, enable_zx=True)

        assert isinstance(res_off, GOIArtifact)
        assert isinstance(res_on, GOIArtifact)

        # Structure must be identical - no partial rewriting
        assert len(res_off.atoms) == len(res_on.atoms)
        assert [a.gate_name for a in res_off.atoms] == [a.gate_name for a in res_on.atoms]
        assert [a.wires for a in res_off.atoms] == [a.wires for a in res_on.atoms]
        assert list(res_off.perm.new_to_old) == list(res_on.perm.new_to_old)
