# tests/integration/test_phase4c_regression_no_change.py
"""Phase 4C Regression: Old Programs Must Not Change

Verifies that Phase 0-4B behavior is unchanged after adding Phase 4C code paths.
"""

from __future__ import annotations

import pytest

from .helpers import (
    mk_phase0_2_corpus,
    mk_phase3_extractable_corpus,
    mk_phase3_residual_corpus,
    mk_phase4a_extracts_more_corpus,
    mk_phase4a_stays_residual_corpus,
    mk_dist_failure_corpus,
    compile_term,
    compile_goi_safe,
    extract_cmd_stream,
    perm_to_list,
    has_swaps,
    is_goi_artifact,
    residual_fingerprint,
    assert_extracted,
    assert_residual,
    assert_no_swaps,
)
from compile.to_pytket import CompiledGOI
from compile.goi import GOIArtifact


class TestPhase4CRegressionPhase0_2:
    """Phase 0-2 behavior unchanged after 4C."""

    @pytest.fixture
    def corpus(self):
        return mk_phase0_2_corpus()

    @pytest.mark.parametrize("name", list(mk_phase0_2_corpus().keys()))
    def test_compile_unchanged(self, corpus, name):
        """Phase 0-2 terms compile identically."""
        term = corpus[name]
        r1 = compile_term(term, materialize=False)
        r2 = compile_term(term, materialize=False)
        assert extract_cmd_stream(r1.circuit) == extract_cmd_stream(r2.circuit)
        assert perm_to_list(r1.perm) == perm_to_list(r2.perm)
        assert_no_swaps(r1.circuit)

    @pytest.mark.parametrize("name", list(mk_phase0_2_corpus().keys()))
    def test_compile_goi_unchanged(self, corpus, name):
        """Phase 0-2 terms via compile_goi are identical."""
        term = corpus[name]
        r1 = compile_goi_safe(term, materialize=False)
        r2 = compile_goi_safe(term, materialize=False)
        assert not is_goi_artifact(r1)
        assert not is_goi_artifact(r2)
        assert extract_cmd_stream(r1.circuit) == extract_cmd_stream(r2.circuit)


class TestPhase4CRegressionPhase3Extractable:
    """Phase 3 extractable cases unchanged."""

    @pytest.fixture
    def corpus(self):
        return mk_phase3_extractable_corpus()

    @pytest.mark.parametrize("name", list(mk_phase3_extractable_corpus().keys()))
    def test_still_extracts(self, corpus, name):
        """Phase 3 yankable cases still extract."""
        term = corpus[name]
        result = compile_goi_safe(term, materialize=False)
        assert_extracted(result, f"{name} should extract")
        assert_no_swaps(result.circuit)


class TestPhase4CRegressionPhase3Residual:
    """Phase 3 residual cases unchanged."""

    @pytest.fixture
    def corpus(self):
        return mk_phase3_residual_corpus()

    @pytest.mark.parametrize("name", list(mk_phase3_residual_corpus().keys()))
    def test_still_residual(self, corpus, name):
        """Phase 3 non-yankable cases still residual."""
        term = corpus[name]
        result = compile_goi_safe(term, materialize=False)
        assert_residual(result, f"{name} should remain residual")


class TestPhase4CRegressionPhase4A:
    """Phase 4A behavior unchanged."""

    @pytest.mark.parametrize("name", list(mk_phase4a_extracts_more_corpus().keys()))
    def test_4a_extracts_still_extract(self, name):
        """Phase 4A extractable cases still extract."""
        corpus = mk_phase4a_extracts_more_corpus()
        term = corpus[name]
        result = compile_goi_safe(term, materialize=False)
        assert_extracted(result, f"{name} should still extract")

    @pytest.mark.parametrize("name", list(mk_phase4a_stays_residual_corpus().keys()))
    def test_4a_residual_still_residual(self, name):
        """Phase 4A residual cases still residual."""
        corpus = mk_phase4a_stays_residual_corpus()
        term = corpus[name]
        result = compile_goi_safe(term, materialize=False)
        assert_residual(result, f"{name} should still be residual")


class TestPhase4CRegressionDistFailures:
    """DistL/DistR failures unchanged."""

    @pytest.fixture
    def corpus(self):
        return mk_dist_failure_corpus()

    @pytest.mark.parametrize("name", list(mk_dist_failure_corpus().keys()))
    def test_dist_still_fails_compile(self, corpus, name):
        """Distributivity still fails with compile()."""
        term = corpus[name]
        with pytest.raises(NotImplementedError):
            compile_term(term, materialize=False)

    @pytest.mark.parametrize("name", list(mk_dist_failure_corpus().keys()))
    def test_dist_still_fails_compile_goi(self, corpus, name):
        """Distributivity still fails with compile_goi()."""
        term = corpus[name]
        result = compile_goi_safe(term, materialize=False)
        assert isinstance(result, NotImplementedError)


class TestPhase4CRegressionWithZX:
    """Phase 4B (enable_zx) unchanged for old programs."""

    @pytest.mark.parametrize("name", list(mk_phase0_2_corpus().keys()))
    def test_phase0_2_unchanged_with_zx(self, name):
        """Phase 0-2 terms identical with enable_zx=True."""
        corpus = mk_phase0_2_corpus()
        term = corpus[name]
        r_no_zx = compile_goi_safe(term, materialize=False, enable_zx=False)
        r_zx = compile_goi_safe(term, materialize=False, enable_zx=True)
        # Both should extract identically
        assert not is_goi_artifact(r_no_zx)
        assert not is_goi_artifact(r_zx)
        assert extract_cmd_stream(r_no_zx.circuit) == extract_cmd_stream(r_zx.circuit)
