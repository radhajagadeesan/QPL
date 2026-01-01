# tests/integration/test_phase4b_positive_goldens.py
"""Phase 4B Positive Corpus Tests (Section 3 of Integration Plan).

Tests for cases where:
- v1 fails → v2 fails → residual
- 4B structural ZX pass succeeds
- output becomes extracted (Circuit, WirePerm)

Note: Phase 4B with deterministic rewrites (id_simp, spider_simp) may not
extract more cases than Phase 4A in practice, since:
1. We treat gates as opaque boxes (Z_BOX)
2. We only use structural rewrites, not gate-aware simplifications

The positive corpus tests cases that COULD be extracted by ZX if the
structural simplification exposes extractable form.
"""

from __future__ import annotations

import pytest

from .helpers import (
    qpow, Q, Ten,
    Id, Seq, TenTerm, H, S, CX, TwistTen, AssocTenL, AssocTenR, Feedback,
    extract_cmd_stream, perm_to_list, residual_fingerprint,
    assert_no_swaps, non_swap_signature,
)
from compile.to_pytket import compile_goi, CompiledGOI
from compile.goi import GOIArtifact
from compile.extract_zx import is_pyzx_available


pytestmark = pytest.mark.skipif(
    not is_pyzx_available(),
    reason="PyZX not installed"
)


def mk_phase4b_potential_positive_corpus():
    """Cases that might benefit from ZX structural simplification.

    These are cases where feedback exists but gates don't touch loop wires.

    Note: With our current conservative ZX approach (opaque gates, structural
    rewrites only), these may still remain residual. The tests verify that
    if extraction succeeds, it produces valid output.

    IMPORTANT: We avoid structure that remaps external wires to loop wires,
    as that causes issues with collapse_feedback.
    """
    q3 = qpow(3)
    q4 = qpow(4)
    qq = Ten(Q(), Q())

    return {
        # Pure identity feedback - trivially extractable
        "p4b_identity_feedback": Feedback(k=1, body=Id(q3)),

        # Gates well away from loop
        "p4b_gates_far_from_loop": Feedback(
            k=1,
            body=Seq(H(0, q3), S(0, q3))  # Only on wire 0, loop is wire 2
        ),

        # CX on external wires only
        "p4b_cx_external_only": Feedback(
            k=1,
            body=CX(0, 1, q3)  # Wires 0,1 are external, loop is wire 2
        ),

        # Multiple gates all on external wires
        "p4b_multi_gate_external": Feedback(
            k=1,
            body=Seq(H(0, q3), S(1, q3), H(0, q3))
        ),
    }


class TestPhase4BPositiveCorpus:
    """Test Phase 4B positive corpus behavior."""

    @pytest.mark.phase4b
    @pytest.mark.parametrize("name,term", list(mk_phase4b_potential_positive_corpus().items()))
    def test_positive_case_with_enable_zx_false_is_baseline(self, name, term):
        """With enable_zx=False, positive cases produce Phase 4A baseline."""
        res = compile_goi(term, materialize=False, enable_zx=False)
        # Record the baseline - either extracted or residual
        # This establishes what Phase 4A does
        if isinstance(res, CompiledGOI):
            # Phase 4A extracted it
            assert_no_swaps(res.circuit)
        else:
            # Phase 4A left it as residual
            assert isinstance(res, GOIArtifact)

    @pytest.mark.phase4b
    @pytest.mark.parametrize("name,term", list(mk_phase4b_potential_positive_corpus().items()))
    def test_positive_case_with_enable_zx_true_extracts_or_matches(self, name, term):
        """With enable_zx=True, positive cases either extract or match baseline."""
        res_off = compile_goi(term, materialize=False, enable_zx=False)
        res_on = compile_goi(term, materialize=False, enable_zx=True)

        if isinstance(res_off, CompiledGOI):
            # If Phase 4A extracted, Phase 4B should too (same result)
            assert isinstance(res_on, CompiledGOI), f"{name}: was extracted, should still extract"
            assert extract_cmd_stream(res_off.circuit) == extract_cmd_stream(res_on.circuit)
            assert perm_to_list(res_off.perm) == perm_to_list(res_on.perm)
        else:
            # Phase 4A left as residual
            # Phase 4B might extract OR might still be residual
            if isinstance(res_on, CompiledGOI):
                # ZX extracted! Verify valid output
                assert_no_swaps(res_on.circuit)
            else:
                # Still residual - structure should match
                assert residual_fingerprint(res_off) == residual_fingerprint(res_on)

    @pytest.mark.phase4b
    @pytest.mark.parametrize("name,term", list(mk_phase4b_potential_positive_corpus().items()))
    def test_positive_case_deterministic(self, name, term):
        """Positive cases produce deterministic results."""
        results = []
        for _ in range(3):
            res = compile_goi(term, materialize=False, enable_zx=True)
            if isinstance(res, CompiledGOI):
                results.append(("extracted", extract_cmd_stream(res.circuit), perm_to_list(res.perm)))
            else:
                results.append(("residual", residual_fingerprint(res)))

        for r in results[1:]:
            assert r == results[0], f"{name}: non-deterministic"


class TestPhase4BPositiveGoldenProperties:
    """Test properties that positive goldens must satisfy."""

    @pytest.mark.phase4b
    def test_identity_feedback_extracts(self):
        """Pure identity feedback should extract to empty circuit + identity perm."""
        q3 = qpow(3)
        term = Feedback(k=1, body=Id(q3))

        res = compile_goi(term, materialize=False, enable_zx=True)

        assert isinstance(res, CompiledGOI), "Identity feedback should extract"
        # Should have no gates (just routing)
        assert len(res.circuit.get_commands()) == 0

    @pytest.mark.phase4b
    def test_extracted_has_no_swaps(self):
        """Any extracted result must have no SWAPs when materialize=False."""
        for name, term in mk_phase4b_potential_positive_corpus().items():
            res = compile_goi(term, materialize=False, enable_zx=True)

            if isinstance(res, CompiledGOI):
                assert_no_swaps(res.circuit)

    @pytest.mark.phase4b
    def test_extracted_perm_is_valid(self):
        """Extracted permutation must be a valid permutation of correct size."""
        for name, term in mk_phase4b_potential_positive_corpus().items():
            res = compile_goi(term, materialize=False, enable_zx=True)

            if isinstance(res, CompiledGOI):
                perm = res.perm
                # Check it's a valid permutation
                perm_list = list(perm.new_to_old)
                assert sorted(perm_list) == list(range(perm.n)), \
                    f"{name}: perm is not valid bijection"
