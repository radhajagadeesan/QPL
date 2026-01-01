# tests/integration/test_determinism_matrix.py
"""Determinism Matrix Tests

Tests for determinism across all compilation paths:
- Same AST => identical outputs
- Stable across N runs
- Consistent across flag combinations
"""

from __future__ import annotations

import math
import hashlib
import pytest

from lang.types import Q, Ten
from lang.terms import (
    Seq, TenTerm, Feedback,
    TwistTen, AssocTenL,
    X, Y, Z, T, Tdg, Sdg, CZ,
    Rz, Rx, Ry, Phase, CRz,
    H, S, CX,
)
from compile.to_pytket import compile, compile_goi

from .helpers import (
    qpow,
    extract_cmd_stream,
    extract_cmd_stream_with_params,
    perm_to_list,
    residual_fingerprint,
    residual_fingerprint_with_params,
    assert_extracted,
    assert_residual,
)

N_RUNS = 5


class TestDeterminismStructuralOnly:
    """Determinism for structural-only (perm-only) programs."""

    def test_twist_deterministic(self):
        """TwistTen is deterministic."""
        prog = TwistTen(Q(), Q())
        perms = []
        for _ in range(N_RUNS):
            r = compile(prog, materialize=False)
            perms.append(perm_to_list(r.perm))
        for i in range(1, N_RUNS):
            assert perms[0] == perms[i]

    def test_assoc_deterministic(self):
        """AssocTenL is deterministic."""
        prog = AssocTenL(Q(), Q(), Q())
        perms = []
        for _ in range(N_RUNS):
            r = compile(prog, materialize=False)
            perms.append(perm_to_list(r.perm))
        for i in range(1, N_RUNS):
            assert perms[0] == perms[i]

    def test_structure_sequence_deterministic(self):
        """Sequence of structure is deterministic."""
        prog = Seq(TwistTen(Q(), Q()), TwistTen(Q(), Q()))
        perms = []
        for _ in range(N_RUNS):
            r = compile(prog, materialize=False)
            perms.append(perm_to_list(r.perm))
        for i in range(1, N_RUNS):
            assert perms[0] == perms[i]


class TestDeterminismFlatExtraction:
    """Determinism for gates, no feedback (flat extraction)."""

    def test_phase0_gates_deterministic(self):
        """Phase 0 gates are deterministic."""
        qq = Ten(Q(), Q())
        prog = Seq(H(0, qq), CX(0, 1, qq), S(1, qq))
        results = []
        for _ in range(N_RUNS):
            r = compile(prog, materialize=False)
            results.append((extract_cmd_stream(r.circuit), perm_to_list(r.perm)))
        for i in range(1, N_RUNS):
            assert results[0] == results[i]

    def test_phase4c_fixed_gates_deterministic(self):
        """Phase 4C fixed gates are deterministic."""
        qq = Ten(Q(), Q())
        prog = Seq(X(0, qq), Y(1, qq), T(0, qq))
        results = []
        for _ in range(N_RUNS):
            r = compile(prog, materialize=False)
            results.append(extract_cmd_stream(r.circuit))
        for i in range(1, N_RUNS):
            assert results[0] == results[i]

    def test_phase4c_param_gates_deterministic(self):
        """Phase 4C parameterized gates are deterministic."""
        qq = Ten(Q(), Q())
        theta = math.pi / 4
        prog = Seq(Rz(theta, 0, qq), Rx(theta, 1, qq))
        results = []
        for _ in range(N_RUNS):
            r = compile(prog, materialize=False)
            results.append(extract_cmd_stream_with_params(r.circuit))
        for i in range(1, N_RUNS):
            assert results[0] == results[i]


class TestDeterminismFeedbackExtracted:
    """Determinism for feedback extracted by v1/v2."""

    def test_yankable_feedback_deterministic(self):
        """Yankable feedback extraction is deterministic."""
        q3 = qpow(3)
        body = Seq(H(0, q3), S(1, q3))
        fb = Feedback(k=1, body=body)
        results = []
        for _ in range(N_RUNS):
            r = compile_goi(fb, materialize=False)
            assert_extracted(r)
            results.append(extract_cmd_stream(r.circuit))
        for i in range(1, N_RUNS):
            assert results[0] == results[i]

    def test_phase4c_yankable_deterministic(self):
        """Phase 4C yankable feedback is deterministic."""
        q3 = qpow(3)
        body = Seq(X(0, q3), T(1, q3))
        fb = Feedback(k=1, body=body)
        results = []
        for _ in range(N_RUNS):
            r = compile_goi(fb, materialize=False)
            assert_extracted(r)
            results.append(extract_cmd_stream(r.circuit))
        for i in range(1, N_RUNS):
            assert results[0] == results[i]


class TestDeterminismResidual:
    """Determinism for residual cases."""

    def test_phase3_residual_deterministic(self):
        """Phase 3 residual is deterministic."""
        q3 = qpow(3)
        fb = Feedback(k=1, body=H(2, q3))
        fingerprints = []
        for _ in range(N_RUNS):
            r = compile_goi(fb, materialize=False)
            assert_residual(r)
            fingerprints.append(residual_fingerprint(r))
        for i in range(1, N_RUNS):
            assert fingerprints[0] == fingerprints[i]

    def test_phase4c_residual_deterministic(self):
        """Phase 4C residual is deterministic."""
        q3 = qpow(3)
        theta = 0.5
        fb = Feedback(k=1, body=Rz(theta, 2, q3))
        fingerprints = []
        for _ in range(N_RUNS):
            r = compile_goi(fb, materialize=False)
            assert_residual(r)
            fingerprints.append(residual_fingerprint_with_params(r))
        for i in range(1, N_RUNS):
            assert fingerprints[0] == fingerprints[i]


class TestDeterminismFlagToggle:
    """Determinism across flag toggles."""

    def test_enable_zx_toggle_acyclic(self):
        """enable_zx toggle on acyclic: should be identical."""
        qq = Ten(Q(), Q())
        prog = Seq(T(0, qq), Rz(0.5, 1, qq))

        r_no_zx = compile_goi(prog, materialize=False, enable_zx=False)
        r_zx = compile_goi(prog, materialize=False, enable_zx=True)

        assert extract_cmd_stream(r_no_zx.circuit) == extract_cmd_stream(r_zx.circuit)

    def test_enable_zx_toggle_yankable(self):
        """enable_zx toggle on yankable feedback: should be identical."""
        q3 = qpow(3)
        body = Seq(X(0, q3), T(1, q3))
        fb = Feedback(k=1, body=body)

        r_no_zx = compile_goi(fb, materialize=False, enable_zx=False)
        r_zx = compile_goi(fb, materialize=False, enable_zx=True)

        assert_extracted(r_no_zx)
        assert_extracted(r_zx)
        assert extract_cmd_stream(r_no_zx.circuit) == extract_cmd_stream(r_zx.circuit)

    def test_enable_zx_toggle_residual(self):
        """enable_zx toggle on residual: fingerprints should match."""
        q3 = qpow(3)
        fb = Feedback(k=1, body=X(2, q3))

        r_no_zx = compile_goi(fb, materialize=False, enable_zx=False)
        r_zx = compile_goi(fb, materialize=False, enable_zx=True)

        assert_residual(r_no_zx)
        assert_residual(r_zx)
        assert residual_fingerprint(r_no_zx) == residual_fingerprint(r_zx)

    def test_materialize_toggle_extracted(self):
        """materialize toggle on extracted: same gates, different perm."""
        qq = Ten(Q(), Q())
        prog = Seq(TwistTen(Q(), Q()), T(0, qq))

        r_no_mat = compile(prog, materialize=False)
        r_mat = compile(prog, materialize=True)

        # Gates should be same
        from .helpers import non_swap_signature
        sig_no_mat = non_swap_signature(r_no_mat.circuit)
        sig_mat = non_swap_signature(r_mat.circuit)
        assert sig_no_mat == sig_mat


class TestDeterminismDigest:
    """SHA256 digest stability."""

    def test_circuit_digest_stable(self):
        """Circuit command stream digest is stable."""
        qq = Ten(Q(), Q())
        theta = math.pi / 4
        prog = Seq(T(0, qq), Rz(theta, 1, qq), CZ(0, 1, qq))

        digests = []
        for _ in range(N_RUNS):
            r = compile(prog, materialize=False)
            cmds = extract_cmd_stream_with_params(r.circuit)
            digest = hashlib.sha256(str(cmds).encode()).hexdigest()
            digests.append(digest)

        for i in range(1, N_RUNS):
            assert digests[0] == digests[i]

    def test_perm_digest_stable(self):
        """Permutation digest is stable."""
        # Use compatible structure sequence (same width)
        prog = Seq(TwistTen(Q(), Q()), TwistTen(Q(), Q()))

        digests = []
        for _ in range(N_RUNS):
            r = compile(prog, materialize=False)
            perm = perm_to_list(r.perm)
            digest = hashlib.sha256(str(perm).encode()).hexdigest()
            digests.append(digest)

        for i in range(1, N_RUNS):
            assert digests[0] == digests[i]
