# tests/integration/test_phase4c_feedback_negative.py
"""Phase 4C Feedback Negative Tests

Tests for feedback cases where Phase 4C gates touch loop wires:
- Extraction remains residual
- Residual is unchanged (byte-identical)
- No partial rewrites
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
    mk_phase4c_feedback_residual_corpus,
    assert_residual,
    residual_fingerprint,
    residual_fingerprint_with_params,
)


class TestPhase4CFeedbackResidual:
    """Feedback with gates on loop wires remains residual."""

    @pytest.fixture
    def corpus(self):
        return mk_phase4c_feedback_residual_corpus()

    @pytest.mark.parametrize("name", list(mk_phase4c_feedback_residual_corpus().keys()))
    def test_remains_residual(self, corpus, name):
        """Feedback with gate on loop wire is residual."""
        term = corpus[name]
        result = compile_goi(term, materialize=False)
        assert_residual(result, f"{name} should remain residual")

    @pytest.mark.parametrize("name", list(mk_phase4c_feedback_residual_corpus().keys()))
    def test_residual_unchanged_with_enable_zx(self, corpus, name):
        """Residual unchanged with enable_zx=True."""
        term = corpus[name]
        r1 = compile_goi(term, materialize=False, enable_zx=False)
        r2 = compile_goi(term, materialize=False, enable_zx=True)
        assert_residual(r1)
        assert_residual(r2)
        # Fingerprints should match
        fp1 = residual_fingerprint_with_params(r1)
        fp2 = residual_fingerprint_with_params(r2)
        assert fp1 == fp2


class TestPhase4CFeedbackFixedGatesResidual:
    """Specific tests for fixed gates on loop wires."""

    def test_x_on_loop_residual(self):
        """X gate on loop wire is residual."""
        q3 = qpow(3)
        fb = Feedback(k=1, body=X(2, q3))
        result = compile_goi(fb, materialize=False)
        assert_residual(result)

    def test_t_on_loop_residual(self):
        """T gate on loop wire is residual."""
        q3 = qpow(3)
        fb = Feedback(k=1, body=T(2, q3))
        result = compile_goi(fb, materialize=False)
        assert_residual(result)

    def test_cz_spans_loop_residual(self):
        """CZ spanning into loop is residual."""
        q3 = qpow(3)
        fb = Feedback(k=1, body=CZ(1, 2, q3))
        result = compile_goi(fb, materialize=False)
        assert_residual(result)

    def test_ccx_with_target_on_loop_residual(self):
        """CCX with target on loop wire is residual."""
        q3 = qpow(3)
        fb = Feedback(k=1, body=CCX(0, 1, 2, q3))
        result = compile_goi(fb, materialize=False)
        assert_residual(result)


class TestPhase4CFeedbackParamGatesResidual:
    """Specific tests for parameterized gates on loop wires."""

    def test_rz_on_loop_residual(self):
        """Rz gate on loop wire is residual."""
        q3 = qpow(3)
        theta = math.pi / 4
        fb = Feedback(k=1, body=Rz(theta, 2, q3))
        result = compile_goi(fb, materialize=False)
        assert_residual(result)

    def test_crz_spans_loop_residual(self):
        """CRz spanning into loop is residual."""
        q3 = qpow(3)
        theta = 0.5
        fb = Feedback(k=1, body=CRz(theta, 1, 2, q3))
        result = compile_goi(fb, materialize=False)
        assert_residual(result)

    def test_param_preserved_in_residual(self):
        """Parameters preserved in residual atoms."""
        q3 = qpow(3)
        theta = 0.12345
        fb = Feedback(k=1, body=Rz(theta, 2, q3))
        result = compile_goi(fb, materialize=False)
        assert_residual(result)
        # Check atoms have the parameter
        for atom in result.atoms:
            if atom.gate_name == "Rz":
                assert len(atom.params) == 1
                assert abs(atom.params[0] - theta) < 1e-10


class TestPhase4CFeedbackResidualStability:
    """Residual stability and fingerprinting."""

    @pytest.mark.parametrize("name", list(mk_phase4c_feedback_residual_corpus().keys()))
    def test_residual_fingerprint_stable(self, name):
        """Residual fingerprint is stable across runs."""
        corpus = mk_phase4c_feedback_residual_corpus()
        term = corpus[name]

        fingerprints = []
        for _ in range(5):
            result = compile_goi(term, materialize=False)
            assert_residual(result)
            fp = residual_fingerprint_with_params(result)
            fingerprints.append(fp)

        for i in range(1, 5):
            assert fingerprints[0] == fingerprints[i]

    def test_residual_atoms_preserved(self):
        """Residual atoms are preserved exactly."""
        q3 = qpow(3)
        theta = 0.789
        body = Seq(X(0, q3), Rz(theta, 2, q3))
        fb = Feedback(k=1, body=body)
        result = compile_goi(fb, materialize=False)
        assert_residual(result)
        # Should have 2 atoms
        assert len(result.atoms) == 2


class TestPhase4CFeedbackMixedResidual:
    """Mixed gates where one touches loop wire."""

    def test_one_on_loop_is_residual(self):
        """One gate on loop makes entire feedback residual."""
        q3 = qpow(3)
        body = Seq(X(0, q3), Y(2, q3))  # X ok, Y on loop
        fb = Feedback(k=1, body=body)
        result = compile_goi(fb, materialize=False)
        assert_residual(result)

    def test_phase0_plus_phase4c_on_loop_residual(self):
        """Phase 0 gate + Phase 4C gate on loop is residual."""
        q3 = qpow(3)
        body = Seq(H(0, q3), T(2, q3))  # H ok, T on loop
        fb = Feedback(k=1, body=body)
        result = compile_goi(fb, materialize=False)
        assert_residual(result)


class TestPhase4CFeedbackNoPartialRewrite:
    """No partial rewrites in residual cases."""

    def test_residual_unchanged_structure(self):
        """Residual has same structural information."""
        q3 = qpow(3)
        theta = 0.5
        fb = Feedback(k=1, body=Rz(theta, 2, q3))

        r1 = compile_goi(fb, materialize=False)
        r2 = compile_goi(fb, materialize=False)

        assert r1.n_in == r2.n_in
        assert r1.n_out == r2.n_out
        assert list(r1.perm.new_to_old) == list(r2.perm.new_to_old)
        assert len(r1.atoms) == len(r2.atoms)
        assert len(r1.loops) == len(r2.loops)
