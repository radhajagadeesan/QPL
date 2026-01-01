# tests/integration/test_phase4c_feedback_positive.py
"""Phase 4C Feedback Positive Tests

Tests for feedback cases where Phase 4C gates are off loop wires:
- Extraction succeeds
- Output is (Circuit, WirePerm)
- Gate atoms preserved
- Determinism
"""

from __future__ import annotations

import math
import pytest

from lang.types import Q, Ten
from lang.terms import (
    Seq, Feedback,
    X, Y, Z, T, Tdg, Sdg, CZ, CCX,
    Rz, Rx, Ry, Phase, CRz,
    H, S, CX,
)
from compile.to_pytket import compile_goi, CompiledGOI
from compile.goi import GOIArtifact

from .helpers import (
    qpow,
    has_swaps,
    extract_cmd_stream,
    extract_cmd_stream_with_params,
    mk_phase4c_feedback_yankable_corpus,
    assert_extracted,
    assert_no_swaps,
)


class TestPhase4CFeedbackYankable:
    """Feedback with gates off loop wires extracts."""

    @pytest.fixture
    def corpus(self):
        return mk_phase4c_feedback_yankable_corpus()

    @pytest.mark.parametrize("name", list(mk_phase4c_feedback_yankable_corpus().keys()))
    def test_extracts_successfully(self, corpus, name):
        """Yankable feedback with Phase 4C gates extracts."""
        term = corpus[name]
        result = compile_goi(term, materialize=False)
        assert_extracted(result, f"{name} should extract")
        assert_no_swaps(result.circuit)

    @pytest.mark.parametrize("name", list(mk_phase4c_feedback_yankable_corpus().keys()))
    def test_produces_circuit_and_perm(self, corpus, name):
        """Extracted result has circuit and perm."""
        term = corpus[name]
        result = compile_goi(term, materialize=False)
        assert hasattr(result, 'circuit')
        assert hasattr(result, 'perm')

    @pytest.mark.parametrize("name", list(mk_phase4c_feedback_yankable_corpus().keys()))
    def test_gates_present_in_output(self, corpus, name):
        """Phase 4C gates are present in extracted circuit."""
        term = corpus[name]
        result = compile_goi(term, materialize=False)
        cmds = extract_cmd_stream(result.circuit)
        assert len(cmds) > 0  # At least one gate


class TestPhase4CFeedbackFixedGatesYankable:
    """Specific tests for fixed gates in yankable feedback."""

    def test_x_off_loop_extracts(self):
        """X gate off loop wire extracts."""
        q3 = qpow(3)
        fb = Feedback(k=1, body=X(0, q3))
        result = compile_goi(fb, materialize=False)
        assert_extracted(result)
        cmds = extract_cmd_stream(result.circuit)
        assert any("X" in cmd for cmd in cmds)

    def test_t_off_loop_extracts(self):
        """T gate off loop wire extracts."""
        q3 = qpow(3)
        fb = Feedback(k=1, body=T(1, q3))
        result = compile_goi(fb, materialize=False)
        assert_extracted(result)

    def test_cz_off_loop_extracts(self):
        """CZ gate with both wires off loop extracts."""
        q3 = qpow(3)
        fb = Feedback(k=1, body=CZ(0, 1, q3))
        result = compile_goi(fb, materialize=False)
        assert_extracted(result)

    def test_multiple_fixed_gates_yankable(self):
        """Multiple fixed gates all off loop extract."""
        q4 = qpow(4)
        body = Seq(X(0, q4), Y(1, q4), T(0, q4), Sdg(1, q4))
        fb = Feedback(k=2, body=body)
        result = compile_goi(fb, materialize=False)
        assert_extracted(result)
        cmds = extract_cmd_stream(result.circuit)
        assert len(cmds) == 4


class TestPhase4CFeedbackParamGatesYankable:
    """Specific tests for parameterized gates in yankable feedback."""

    def test_rz_off_loop_extracts(self):
        """Rz gate off loop wire extracts."""
        q3 = qpow(3)
        theta = math.pi / 4
        fb = Feedback(k=1, body=Rz(theta, 0, q3))
        result = compile_goi(fb, materialize=False)
        assert_extracted(result)

    def test_rx_off_loop_extracts(self):
        """Rx gate off loop wire extracts."""
        q3 = qpow(3)
        theta = 0.5
        fb = Feedback(k=1, body=Rx(theta, 1, q3))
        result = compile_goi(fb, materialize=False)
        assert_extracted(result)

    def test_crz_off_loop_extracts(self):
        """CRz gate with both wires off loop extracts."""
        q4 = qpow(4)
        theta = 0.789
        fb = Feedback(k=2, body=CRz(theta, 0, 1, q4))
        result = compile_goi(fb, materialize=False)
        assert_extracted(result)

    def test_param_preserved_in_extraction(self):
        """Parameters are preserved through extraction."""
        q3 = qpow(3)
        theta = 0.12345
        fb = Feedback(k=1, body=Rz(theta, 0, q3))
        result = compile_goi(fb, materialize=False)
        assert_extracted(result)
        cmds = result.circuit.get_commands()
        params = list(cmds[0].op.params)
        assert abs(params[0] - theta) < 1e-10


class TestPhase4CFeedbackYankableDeterminism:
    """Determinism of yankable feedback extraction."""

    @pytest.mark.parametrize("name", list(mk_phase4c_feedback_yankable_corpus().keys()))
    def test_extraction_deterministic(self, name):
        """Extraction produces same output across runs."""
        corpus = mk_phase4c_feedback_yankable_corpus()
        term = corpus[name]

        results = []
        for _ in range(5):
            r = compile_goi(term, materialize=False)
            assert_extracted(r)
            cmds = extract_cmd_stream_with_params(r.circuit)
            results.append(cmds)

        for i in range(1, 5):
            assert results[0] == results[i]


class TestPhase4CFeedbackMixedGatesYankable:
    """Mixed Phase 0 and Phase 4C gates in yankable feedback."""

    def test_mixed_phase0_phase4c_extracts(self):
        """Mixed Phase 0 and Phase 4C gates extract."""
        q3 = qpow(3)
        body = Seq(H(0, q3), T(1, q3))
        fb = Feedback(k=1, body=body)
        result = compile_goi(fb, materialize=False)
        assert_extracted(result)
        cmds = extract_cmd_stream(result.circuit)
        assert len(cmds) == 2

    def test_phase0_and_param_extracts(self):
        """Phase 0 gate + parameterized gate extract."""
        q3 = qpow(3)
        theta = math.pi / 3
        body = Seq(CX(0, 1, q3), Rz(theta, 0, q3))
        fb = Feedback(k=1, body=body)
        result = compile_goi(fb, materialize=False)
        assert_extracted(result)
