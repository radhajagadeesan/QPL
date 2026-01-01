# tests/integration/test_phase4c_backend_lowering.py
"""Phase 4C Backend Lowering Tests

Tests for lowering Phase 4C gates to pytket:
- Unitary-only operations
- Correct arity
- Deterministic emission order
- No SWAPs when materialize=False
"""

from __future__ import annotations

import math
import pytest

from lang.types import Q, Ten
from lang.terms import (
    Seq, TenTerm,
    X, Y, Z, T, Tdg, Sdg, CZ, CCX,
    Rz, Rx, Ry, Phase, CRz,
    H, S, CX,
)
from compile.to_pytket import compile, compile_goi

from .helpers import (
    qpow, has_swaps, is_unitary_only, get_gate_names,
    extract_cmd_stream, extract_cmd_stream_with_params,
    mk_phase4c_fixed_gates_corpus,
    mk_phase4c_param_gates_corpus,
    mk_phase4c_with_structure_corpus,
)


class TestPhase4CBackendLoweringFixed:
    """Backend lowering for fixed gates."""

    @pytest.fixture
    def corpus(self):
        return mk_phase4c_fixed_gates_corpus()

    @pytest.mark.parametrize("name", list(mk_phase4c_fixed_gates_corpus().keys()))
    def test_fixed_gates_lower_to_pytket(self, corpus, name):
        """Fixed gates lower to valid pytket circuits."""
        term = corpus[name]
        r = compile(term, materialize=False)
        assert is_unitary_only(r.circuit)
        assert not has_swaps(r.circuit)

    def test_x_gate_correct_op(self):
        """X gate produces X operation."""
        q = Q()
        r = compile(X(0, q), materialize=False)
        gates = get_gate_names(r.circuit)
        assert "X" in gates

    def test_cz_gate_correct_op(self):
        """CZ gate produces CZ operation."""
        qq = Ten(Q(), Q())
        r = compile(CZ(0, 1, qq), materialize=False)
        gates = get_gate_names(r.circuit)
        assert "CZ" in gates

    def test_ccx_gate_correct_op(self):
        """CCX gate produces CCX operation."""
        q3 = qpow(3)
        r = compile(CCX(0, 1, 2, q3), materialize=False)
        gates = get_gate_names(r.circuit)
        assert "CCX" in gates

    def test_ccx_arity(self):
        """CCX gate has 3-qubit arity."""
        q3 = qpow(3)
        r = compile(CCX(0, 1, 2, q3), materialize=False)
        cmds = r.circuit.get_commands()
        assert len(cmds) == 1
        assert len(cmds[0].qubits) == 3


class TestPhase4CBackendLoweringParam:
    """Backend lowering for parameterized gates."""

    @pytest.fixture
    def corpus(self):
        return mk_phase4c_param_gates_corpus()

    @pytest.mark.parametrize("name", list(mk_phase4c_param_gates_corpus().keys()))
    def test_param_gates_lower_to_pytket(self, corpus, name):
        """Parameterized gates lower to valid pytket circuits."""
        term = corpus[name]
        r = compile(term, materialize=False)
        assert is_unitary_only(r.circuit)
        assert not has_swaps(r.circuit)

    def test_rz_gate_preserves_param(self):
        """Rz gate preserves parameter value."""
        qq = Ten(Q(), Q())
        theta = 0.12345
        r = compile(Rz(theta, 0, qq), materialize=False)
        cmds = r.circuit.get_commands()
        assert len(cmds) == 1
        params = list(cmds[0].op.params)
        assert len(params) == 1
        assert abs(params[0] - theta) < 1e-10

    def test_rx_gate_preserves_param(self):
        """Rx gate preserves parameter value."""
        q = Q()
        theta = math.pi / 3
        r = compile(Rx(theta, 0, q), materialize=False)
        cmds = r.circuit.get_commands()
        params = list(cmds[0].op.params)
        assert abs(params[0] - theta) < 1e-10

    def test_crz_gate_correct_arity_and_param(self):
        """CRz gate has 2-qubit arity and preserves param."""
        qq = Ten(Q(), Q())
        theta = 0.789
        r = compile(CRz(theta, 0, 1, qq), materialize=False)
        cmds = r.circuit.get_commands()
        assert len(cmds) == 1
        assert len(cmds[0].qubits) == 2
        params = list(cmds[0].op.params)
        assert abs(params[0] - theta) < 1e-10

    def test_phase_gate_lowers_to_u1(self):
        """Phase gate lowers to U1 in pytket."""
        qq = Ten(Q(), Q())
        phi = math.pi / 4
        r = compile(Phase(phi, 0, qq), materialize=False)
        gates = get_gate_names(r.circuit)
        assert "U1" in gates


class TestPhase4CBackendLoweringDeterminism:
    """Deterministic emission order."""

    def test_sequential_gates_order_preserved(self):
        """Sequential gates maintain order."""
        qq = Ten(Q(), Q())
        theta = math.pi / 4
        prog = Seq(X(0, qq), Rz(theta, 1, qq), T(0, qq))

        r1 = compile(prog, materialize=False)
        r2 = compile(prog, materialize=False)

        cmds1 = extract_cmd_stream(r1.circuit)
        cmds2 = extract_cmd_stream(r2.circuit)
        assert cmds1 == cmds2

    def test_tenterm_offset_order(self):
        """TenTerm emits left-then-right."""
        q = Q()
        prog = TenTerm(X(0, q), Y(0, q))
        r = compile(prog, materialize=False)
        cmds = extract_cmd_stream(r.circuit)
        assert len(cmds) == 2
        assert "X(0)" in cmds[0]
        assert "Y(1)" in cmds[1]

    def test_mixed_phase0_phase4c_order(self):
        """Mixed Phase 0 and Phase 4C gates preserve order."""
        qq = Ten(Q(), Q())
        prog = Seq(H(0, qq), T(1, qq), CX(0, 1, qq), Sdg(0, qq))
        r = compile(prog, materialize=False)
        cmds = extract_cmd_stream(r.circuit)
        assert len(cmds) == 4
        assert "H" in cmds[0]
        assert "T" in cmds[1]
        assert "CX" in cmds[2]
        assert "Sdg" in cmds[3]


class TestPhase4CBackendLoweringGOI:
    """Backend lowering via compile_goi."""

    @pytest.fixture
    def corpus(self):
        return mk_phase4c_all_corpus()

    @pytest.mark.parametrize("name", list(mk_phase4c_fixed_gates_corpus().keys()))
    def test_fixed_gates_via_goi(self, name):
        """Fixed gates lower correctly via compile_goi."""
        corpus = mk_phase4c_fixed_gates_corpus()
        term = corpus[name]
        result = compile_goi(term, materialize=False)
        assert is_unitary_only(result.circuit)
        assert not has_swaps(result.circuit)

    @pytest.mark.parametrize("name", list(mk_phase4c_param_gates_corpus().keys()))
    def test_param_gates_via_goi(self, name):
        """Parameterized gates lower correctly via compile_goi."""
        corpus = mk_phase4c_param_gates_corpus()
        term = corpus[name]
        result = compile_goi(term, materialize=False)
        assert is_unitary_only(result.circuit)
        assert not has_swaps(result.circuit)


def mk_phase4c_all_corpus():
    """Combined corpus for parametrization."""
    result = {}
    result.update(mk_phase4c_fixed_gates_corpus())
    result.update(mk_phase4c_param_gates_corpus())
    return result


class TestPhase4CBackendNoSwaps:
    """No SWAPs when materialize=False."""

    @pytest.mark.parametrize("name", list(mk_phase4c_with_structure_corpus().keys()))
    def test_structure_plus_4c_no_swaps(self, name):
        """Structure + Phase 4C gates emit no SWAPs."""
        corpus = mk_phase4c_with_structure_corpus()
        term = corpus[name]
        r = compile(term, materialize=False)
        assert not has_swaps(r.circuit)
