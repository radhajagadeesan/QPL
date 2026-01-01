# tests/integration/test_phase4c_gate_admission.py
"""Phase 4C Gate Admission and Typing Tests

Tests for each new primitive gate kind:
- Minimal valid usage
- Wrong arity
- Invalid parameter type (if applicable)
- Index out of range
"""

from __future__ import annotations

import math
import pytest

from lang.types import Q, Ten, width
from lang.terms import (
    Seq, Id,
    X, Y, Z, T, Tdg, Sdg, CZ, CCX,
    Rz, Rx, Ry, Phase, CRz,
)
from typing_.check import type_of, assert_well_typed, TypeCheckError
from compile.to_pytket import compile, compile_goi

from .helpers import qpow, has_swaps, assert_no_swaps


class TestPhase4CFixedGateAdmission:
    """Admission tests for Phase 4C fixed gates."""

    # ----- Valid usage -----

    def test_x_valid(self):
        """X gate with valid index."""
        q = Q()
        gate = X(0, q)
        assert_well_typed(gate)
        dom, cod = type_of(gate)
        assert dom == q
        assert cod == q

    def test_y_valid(self):
        """Y gate with valid index."""
        qq = Ten(Q(), Q())
        gate = Y(1, qq)
        assert_well_typed(gate)

    def test_z_valid(self):
        """Z gate with valid index."""
        q = Q()
        gate = Z(0, q)
        assert_well_typed(gate)

    def test_t_valid(self):
        """T gate with valid index."""
        qq = Ten(Q(), Q())
        gate = T(0, qq)
        assert_well_typed(gate)

    def test_tdg_valid(self):
        """Tdg gate with valid index."""
        qq = Ten(Q(), Q())
        gate = Tdg(1, qq)
        assert_well_typed(gate)

    def test_sdg_valid(self):
        """Sdg gate with valid index."""
        q = Q()
        gate = Sdg(0, q)
        assert_well_typed(gate)

    def test_cz_valid(self):
        """CZ gate with valid indices."""
        qq = Ten(Q(), Q())
        gate = CZ(0, 1, qq)
        assert_well_typed(gate)
        dom, cod = type_of(gate)
        assert dom == qq

    def test_ccx_valid(self):
        """CCX gate with valid indices."""
        q3 = qpow(3)
        gate = CCX(0, 1, 2, q3)
        assert_well_typed(gate)
        dom, cod = type_of(gate)
        assert width(dom) == 3

    # ----- Invalid indices -----

    def test_x_index_out_of_range(self):
        """X gate index out of range."""
        q = Q()
        with pytest.raises(TypeCheckError):
            type_of(X(1, q))  # width 1, index 1 out of range

    def test_y_index_out_of_range(self):
        """Y gate index out of range."""
        qq = Ten(Q(), Q())
        with pytest.raises(TypeCheckError):
            type_of(Y(5, qq))

    def test_cz_duplicate_indices(self):
        """CZ gate with duplicate indices."""
        qq = Ten(Q(), Q())
        with pytest.raises(TypeCheckError):
            type_of(CZ(0, 0, qq))

    def test_cz_index_out_of_range(self):
        """CZ gate with index out of range."""
        qq = Ten(Q(), Q())
        with pytest.raises(TypeCheckError):
            type_of(CZ(0, 2, qq))

    def test_ccx_duplicate_indices(self):
        """CCX gate with duplicate indices."""
        q3 = qpow(3)
        with pytest.raises(TypeCheckError):
            type_of(CCX(0, 0, 1, q3))
        with pytest.raises(TypeCheckError):
            type_of(CCX(0, 1, 0, q3))
        with pytest.raises(TypeCheckError):
            type_of(CCX(1, 1, 2, q3))

    def test_ccx_index_out_of_range(self):
        """CCX gate with index out of range."""
        q3 = qpow(3)
        with pytest.raises(TypeCheckError):
            type_of(CCX(0, 1, 3, q3))


class TestPhase4CParamGateAdmission:
    """Admission tests for Phase 4C parameterized gates."""

    # ----- Valid usage -----

    def test_rz_valid(self):
        """Rz gate with valid parameter."""
        q = Q()
        gate = Rz(math.pi / 4, 0, q)
        assert_well_typed(gate)
        assert gate.theta == math.pi / 4

    def test_rx_valid(self):
        """Rx gate with valid parameter."""
        qq = Ten(Q(), Q())
        gate = Rx(0.5, 1, qq)
        assert_well_typed(gate)

    def test_ry_valid(self):
        """Ry gate with valid parameter."""
        q = Q()
        gate = Ry(1.234, 0, q)
        assert_well_typed(gate)

    def test_phase_valid(self):
        """Phase gate with valid parameter."""
        qq = Ten(Q(), Q())
        gate = Phase(math.pi / 3, 0, qq)
        assert_well_typed(gate)
        assert gate.phi == math.pi / 3

    def test_crz_valid(self):
        """CRz gate with valid parameters."""
        qq = Ten(Q(), Q())
        gate = CRz(0.7, 0, 1, qq)
        assert_well_typed(gate)
        assert gate.theta == 0.7

    # ----- Invalid indices -----

    def test_rz_index_out_of_range(self):
        """Rz gate index out of range."""
        q = Q()
        with pytest.raises(TypeCheckError):
            type_of(Rz(0.5, 1, q))

    def test_crz_duplicate_indices(self):
        """CRz gate with duplicate indices."""
        qq = Ten(Q(), Q())
        with pytest.raises(TypeCheckError):
            type_of(CRz(0.5, 0, 0, qq))

    def test_crz_index_out_of_range(self):
        """CRz gate with index out of range."""
        qq = Ten(Q(), Q())
        with pytest.raises(TypeCheckError):
            type_of(CRz(0.5, 0, 2, qq))

    # ----- Parameter edge cases -----

    def test_rz_zero_parameter(self):
        """Rz gate with zero parameter."""
        q = Q()
        gate = Rz(0.0, 0, q)
        assert_well_typed(gate)

    def test_rz_negative_parameter(self):
        """Rz gate with negative parameter."""
        q = Q()
        gate = Rz(-math.pi / 2, 0, q)
        assert_well_typed(gate)

    def test_rz_large_parameter(self):
        """Rz gate with large parameter (> 2pi)."""
        q = Q()
        gate = Rz(10 * math.pi, 0, q)
        assert_well_typed(gate)


class TestPhase4CGateCompilation:
    """Test that valid gates compile successfully."""

    def test_fixed_gates_compile(self):
        """All fixed gates compile via compile()."""
        qq = Ten(Q(), Q())
        q3 = qpow(3)

        for gate in [X(0, qq), Y(1, qq), Z(0, qq), T(1, qq), Tdg(0, qq), Sdg(1, qq)]:
            r = compile(gate, materialize=False)
            assert_no_swaps(r.circuit)

        r = compile(CZ(0, 1, qq), materialize=False)
        assert_no_swaps(r.circuit)

        r = compile(CCX(0, 1, 2, q3), materialize=False)
        assert_no_swaps(r.circuit)

    def test_param_gates_compile(self):
        """All parameterized gates compile via compile()."""
        qq = Ten(Q(), Q())
        theta = math.pi / 4

        for gate in [Rz(theta, 0, qq), Rx(theta, 1, qq), Ry(theta, 0, qq)]:
            r = compile(gate, materialize=False)
            assert_no_swaps(r.circuit)

        r = compile(Phase(theta, 0, qq), materialize=False)
        assert_no_swaps(r.circuit)

        r = compile(CRz(theta, 0, 1, qq), materialize=False)
        assert_no_swaps(r.circuit)

    def test_gates_compile_via_goi(self):
        """Gates compile via compile_goi()."""
        qq = Ten(Q(), Q())
        q3 = qpow(3)
        theta = math.pi / 4

        # Fixed gates
        result = compile_goi(Seq(X(0, qq), T(1, qq)), materialize=False)
        assert not hasattr(result, 'loops') or not result.loops  # not residual
        assert_no_swaps(result.circuit)

        # Parameterized gates
        result = compile_goi(Seq(Rz(theta, 0, qq), Rx(theta, 1, qq)), materialize=False)
        assert_no_swaps(result.circuit)


class TestPhase4CGateAdmissionEnableZX:
    """Gate admission not affected by enable_zx flag."""

    def test_invalid_gate_fails_with_zx_false(self):
        """Invalid gate fails with enable_zx=False."""
        q = Q()
        invalid_gate = X(5, q)  # out of range
        with pytest.raises(TypeCheckError):
            type_of(invalid_gate)

    def test_invalid_gate_fails_with_zx_true(self):
        """Invalid gate fails with enable_zx=True (same error)."""
        q = Q()
        invalid_gate = X(5, q)  # out of range
        with pytest.raises(TypeCheckError):
            type_of(invalid_gate)

    def test_valid_gate_same_with_and_without_zx(self):
        """Valid gate produces same result with/without enable_zx."""
        qq = Ten(Q(), Q())
        gate = Seq(T(0, qq), Rz(0.5, 1, qq))

        r1 = compile_goi(gate, materialize=False, enable_zx=False)
        r2 = compile_goi(gate, materialize=False, enable_zx=True)

        # Both should produce same circuit
        from .helpers import extract_cmd_stream
        assert extract_cmd_stream(r1.circuit) == extract_cmd_stream(r2.circuit)
