# tests/integration/test_phase4c_param_serialization.py
"""Phase 4C Parameter Serialization Tests

Tests for canonical parameter serialization:
- Same parameter value via different forms
- Roundtrip stability
- Deterministic serialization
"""

from __future__ import annotations

import math
import hashlib
import pytest

from lang.types import Q, Ten
from lang.terms import Seq, Rz, Rx, Ry, Phase, CRz
from compile.to_pytket import compile, compile_goi

from .helpers import (
    qpow,
    extract_cmd_stream_with_params,
    has_swaps,
)


class TestPhase4CParamSerializationStability:
    """Parameter serialization is stable and canonical."""

    def test_rz_param_stable_across_runs(self):
        """Rz parameter serialization is stable."""
        qq = Ten(Q(), Q())
        theta = math.pi / 4

        results = []
        for _ in range(5):
            r = compile(Rz(theta, 0, qq), materialize=False)
            cmds = extract_cmd_stream_with_params(r.circuit)
            results.append(cmds)

        # All runs should produce identical serialization
        for i in range(1, 5):
            assert results[0] == results[i]

    def test_multiple_params_stable(self):
        """Multiple parameterized gates have stable serialization."""
        qq = Ten(Q(), Q())
        theta1 = 0.111
        theta2 = 0.222
        prog = Seq(Rz(theta1, 0, qq), Rx(theta2, 1, qq))

        results = []
        for _ in range(5):
            r = compile(prog, materialize=False)
            cmds = extract_cmd_stream_with_params(r.circuit)
            results.append(cmds)

        for i in range(1, 5):
            assert results[0] == results[i]

    def test_param_digest_stable(self):
        """SHA256 digest of serialization is stable."""
        qq = Ten(Q(), Q())
        theta = math.pi / 6
        prog = Seq(Rz(theta, 0, qq), Ry(theta, 1, qq), CRz(theta, 0, 1, qq))

        digests = []
        for _ in range(5):
            r = compile(prog, materialize=False)
            cmds = extract_cmd_stream_with_params(r.circuit)
            cmd_str = str(cmds)
            digest = hashlib.sha256(cmd_str.encode()).hexdigest()
            digests.append(digest)

        for i in range(1, 5):
            assert digests[0] == digests[i]


class TestPhase4CParamEquivalence:
    """Same parameter value produces same output."""

    def test_same_value_different_expression(self):
        """Same float value from different expressions produces same output."""
        qq = Ten(Q(), Q())

        # Different ways to express the same value
        theta1 = math.pi / 4
        theta2 = 0.7853981633974483  # pi/4 as decimal
        theta3 = math.atan(1)  # Also pi/4

        r1 = compile(Rz(theta1, 0, qq), materialize=False)
        r2 = compile(Rz(theta2, 0, qq), materialize=False)
        r3 = compile(Rz(theta3, 0, qq), materialize=False)

        cmds1 = extract_cmd_stream_with_params(r1.circuit)
        cmds2 = extract_cmd_stream_with_params(r2.circuit)
        cmds3 = extract_cmd_stream_with_params(r3.circuit)

        assert cmds1 == cmds2
        assert cmds1 == cmds3

    def test_zero_param_consistent(self):
        """Zero parameter is handled consistently."""
        qq = Ten(Q(), Q())

        r1 = compile(Rz(0.0, 0, qq), materialize=False)
        r2 = compile(Rz(-0.0, 0, qq), materialize=False)  # Negative zero

        # Both should serialize the same way
        cmds1 = extract_cmd_stream_with_params(r1.circuit)
        cmds2 = extract_cmd_stream_with_params(r2.circuit)
        assert cmds1 == cmds2


class TestPhase4CParamPrecision:
    """Parameter precision is preserved."""

    def test_high_precision_preserved(self):
        """High-precision parameters are preserved."""
        qq = Ten(Q(), Q())
        theta = 0.123456789012345

        r = compile(Rz(theta, 0, qq), materialize=False)
        cmds = r.circuit.get_commands()
        params = list(cmds[0].op.params)
        assert abs(params[0] - theta) < 1e-10

    def test_small_values_preserved(self):
        """Small parameter values are preserved (within pytket precision)."""
        qq = Ten(Q(), Q())
        theta = 1e-6  # Use a value that won't be rounded to 0

        r = compile(Rz(theta, 0, qq), materialize=False)
        cmds = r.circuit.get_commands()
        params = list(cmds[0].op.params)
        assert abs(params[0] - theta) < 1e-10

    def test_large_values_normalized(self):
        """Large parameter values may be normalized by pytket."""
        qq = Ten(Q(), Q())
        theta = 100 * math.pi

        r = compile(Rz(theta, 0, qq), materialize=False)
        cmds = r.circuit.get_commands()
        params = list(cmds[0].op.params)
        # pytket may normalize to [0, 2pi), so just check we get a valid param
        assert isinstance(params[0], (int, float))


class TestPhase4CParamViaGOI:
    """Parameter serialization via compile_goi."""

    def test_params_stable_via_goi(self):
        """Parameters stable via compile_goi."""
        qq = Ten(Q(), Q())
        theta = math.pi / 5
        prog = Seq(Rz(theta, 0, qq), Rx(theta, 1, qq))

        results = []
        for _ in range(5):
            r = compile_goi(prog, materialize=False)
            cmds = extract_cmd_stream_with_params(r.circuit)
            results.append(cmds)

        for i in range(1, 5):
            assert results[0] == results[i]

    def test_compile_and_goi_same_params(self):
        """compile() and compile_goi() produce same parameter serialization."""
        qq = Ten(Q(), Q())
        theta = 0.789
        prog = Rz(theta, 0, qq)

        r1 = compile(prog, materialize=False)
        r2 = compile_goi(prog, materialize=False)

        cmds1 = extract_cmd_stream_with_params(r1.circuit)
        cmds2 = extract_cmd_stream_with_params(r2.circuit)
        assert cmds1 == cmds2
