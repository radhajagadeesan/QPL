# tests/integration/test_phase4b_with_phase4c.py
"""Phase 4B + Phase 4C Combined Integration Tests

Tests for residuals with Phase 4C gates where ZX may simplify structure
but must never inspect gates (opaque boxes).
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
    assert_extracted,
    assert_residual,
    residual_fingerprint,
    residual_fingerprint_with_params,
)


class TestPhase4BWith4CPositive:
    """4B positive corpus with Phase 4C gates as opaque boxes."""

    def test_zx_extracts_with_fixed_gates_off_loop(self):
        """ZX extraction works with Phase 4C fixed gates off loop."""
        q3 = qpow(3)
        # Gates on external wires, loop on wire 2
        body = Seq(X(0, q3), T(1, q3))
        fb = Feedback(k=1, body=body)

        # Without ZX
        r_no_zx = compile_goi(fb, materialize=False, enable_zx=False)
        # With ZX
        r_zx = compile_goi(fb, materialize=False, enable_zx=True)

        # Both should extract (yankable)
        assert_extracted(r_no_zx)
        assert_extracted(r_zx)

    def test_zx_extracts_with_param_gates_off_loop(self):
        """ZX extraction works with Phase 4C param gates off loop."""
        q3 = qpow(3)
        theta = math.pi / 4
        body = Seq(Rz(theta, 0, q3), Rx(theta, 1, q3))
        fb = Feedback(k=1, body=body)

        r_no_zx = compile_goi(fb, materialize=False, enable_zx=False)
        r_zx = compile_goi(fb, materialize=False, enable_zx=True)

        assert_extracted(r_no_zx)
        assert_extracted(r_zx)

    def test_gates_preserved_as_opaque_after_zx(self):
        """Phase 4C gates preserved as opaque after ZX extraction."""
        q3 = qpow(3)
        theta = 0.12345
        body = Rz(theta, 0, q3)
        fb = Feedback(k=1, body=body)

        result = compile_goi(fb, materialize=False, enable_zx=True)
        assert_extracted(result)

        # Parameter should be preserved
        cmds = result.circuit.get_commands()
        assert len(cmds) >= 1
        for cmd in cmds:
            if cmd.op.type.name == "Rz":
                params = list(cmd.op.params)
                assert abs(params[0] - theta) < 1e-10


class TestPhase4BWith4CNegative:
    """4B negative corpus with Phase 4C gates blocking simplification."""

    def test_residual_unchanged_with_gate_on_loop(self):
        """Residual unchanged when Phase 4C gate on loop."""
        q3 = qpow(3)
        fb = Feedback(k=1, body=X(2, q3))

        r_no_zx = compile_goi(fb, materialize=False, enable_zx=False)
        r_zx = compile_goi(fb, materialize=False, enable_zx=True)

        # Both should be residual
        assert_residual(r_no_zx)
        assert_residual(r_zx)

        # Fingerprints should match
        fp_no_zx = residual_fingerprint(r_no_zx)
        fp_zx = residual_fingerprint(r_zx)
        assert fp_no_zx == fp_zx

    def test_param_gate_on_loop_residual_with_zx(self):
        """Parameterized gate on loop remains residual with enable_zx."""
        q3 = qpow(3)
        theta = 0.5
        fb = Feedback(k=1, body=Rz(theta, 2, q3))

        r_no_zx = compile_goi(fb, materialize=False, enable_zx=False)
        r_zx = compile_goi(fb, materialize=False, enable_zx=True)

        assert_residual(r_no_zx)
        assert_residual(r_zx)

    def test_no_partial_rewrites_with_zx(self):
        """No partial rewrites leak with enable_zx."""
        q3 = qpow(3)
        theta = 0.789
        fb = Feedback(k=1, body=Rz(theta, 2, q3))

        r1 = compile_goi(fb, materialize=False, enable_zx=True)
        r2 = compile_goi(fb, materialize=False, enable_zx=True)

        # Structure should be identical
        assert_residual(r1)
        assert_residual(r2)
        fp1 = residual_fingerprint_with_params(r1)
        fp2 = residual_fingerprint_with_params(r2)
        assert fp1 == fp2


class TestPhase4BWith4COpacity:
    """Gate opacity tests - ZX must not inspect gate internals."""

    def test_gate_name_preserved(self):
        """Gate names preserved in residual after ZX attempt."""
        q3 = qpow(3)
        theta = 0.5
        body = Seq(X(0, q3), Rz(theta, 2, q3))  # X ok, Rz on loop
        fb = Feedback(k=1, body=body)

        result = compile_goi(fb, materialize=False, enable_zx=True)
        assert_residual(result)

        # Check gate names in atoms
        gate_names = [a.gate_name for a in result.atoms]
        assert "X" in gate_names
        assert "Rz" in gate_names

    def test_gate_params_preserved(self):
        """Gate parameters preserved in residual after ZX attempt."""
        q3 = qpow(3)
        theta = 0.12345
        fb = Feedback(k=1, body=Rz(theta, 2, q3))

        result = compile_goi(fb, materialize=False, enable_zx=True)
        assert_residual(result)

        # Find Rz atom and check param
        for atom in result.atoms:
            if atom.gate_name == "Rz":
                assert len(atom.params) == 1
                assert abs(atom.params[0] - theta) < 1e-10

    def test_gate_wires_preserved(self):
        """Gate wires preserved in residual after ZX attempt."""
        q3 = qpow(3)
        fb = Feedback(k=1, body=CZ(1, 2, q3))

        result = compile_goi(fb, materialize=False, enable_zx=True)
        assert_residual(result)

        # Check CZ atom wires
        for atom in result.atoms:
            if atom.gate_name == "CZ":
                assert len(atom.wires) == 2


class TestPhase4BWith4CMixed:
    """Mixed Phase 0 + Phase 4C in 4B context."""

    def test_mixed_gates_off_loop_extracts(self):
        """Mixed Phase 0 and Phase 4C gates off loop extract."""
        q3 = qpow(3)
        body = Seq(H(0, q3), T(1, q3), CX(0, 1, q3))
        fb = Feedback(k=1, body=body)

        r_zx = compile_goi(fb, materialize=False, enable_zx=True)
        assert_extracted(r_zx)
        assert not has_swaps(r_zx.circuit)

    def test_mixed_gates_one_on_loop_residual(self):
        """Mixed gates with one on loop stays residual."""
        q3 = qpow(3)
        body = Seq(H(0, q3), T(2, q3))  # H ok, T on loop
        fb = Feedback(k=1, body=body)

        r_zx = compile_goi(fb, materialize=False, enable_zx=True)
        assert_residual(r_zx)
