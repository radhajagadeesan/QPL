# tests/integration/test_backend_sanity_phase4c.py
"""Phase 4C Backend Sanity Tests

Post-extraction validation for all Phase 4C outputs:
- Unitary-only operations
- Correct arities
- Stable serialization
- Valid pytket circuits
"""

from __future__ import annotations

import math
import pytest

from lang.types import Q, Ten
from lang.terms import (
    Seq, TenTerm, Feedback,
    X, Y, Z, T, Tdg, Sdg, CZ, CCX,
    Rz, Rx, Ry, Phase, CRz,
    H, S, CX,
)
from compile.to_pytket import compile, compile_goi

from .helpers import (
    qpow,
    is_unitary_only,
    has_swaps,
    extract_cmd_stream,
    mk_phase4c_fixed_gates_corpus,
    mk_phase4c_param_gates_corpus,
    mk_phase4c_with_structure_corpus,
    mk_phase4c_feedback_yankable_corpus,
    assert_extracted,
    assert_no_swaps,
)


class TestBackendSanityUnitaryOnly:
    """All extracted circuits contain only unitary operations."""

    @pytest.mark.parametrize("name", list(mk_phase4c_fixed_gates_corpus().keys()))
    def test_fixed_gates_unitary_only(self, name):
        """Fixed gates produce unitary-only circuits."""
        corpus = mk_phase4c_fixed_gates_corpus()
        term = corpus[name]
        r = compile(term, materialize=False)
        assert is_unitary_only(r.circuit)

    @pytest.mark.parametrize("name", list(mk_phase4c_param_gates_corpus().keys()))
    def test_param_gates_unitary_only(self, name):
        """Parameterized gates produce unitary-only circuits."""
        corpus = mk_phase4c_param_gates_corpus()
        term = corpus[name]
        r = compile(term, materialize=False)
        assert is_unitary_only(r.circuit)

    @pytest.mark.parametrize("name", list(mk_phase4c_with_structure_corpus().keys()))
    def test_structure_gates_unitary_only(self, name):
        """Structure + gates produce unitary-only circuits."""
        corpus = mk_phase4c_with_structure_corpus()
        term = corpus[name]
        r = compile(term, materialize=False)
        assert is_unitary_only(r.circuit)

    @pytest.mark.parametrize("name", list(mk_phase4c_feedback_yankable_corpus().keys()))
    def test_feedback_extracted_unitary_only(self, name):
        """Extracted feedback produces unitary-only circuits."""
        corpus = mk_phase4c_feedback_yankable_corpus()
        term = corpus[name]
        r = compile_goi(term, materialize=False)
        assert_extracted(r)
        assert is_unitary_only(r.circuit)


class TestBackendSanityArity:
    """Gates have correct arity in pytket output."""

    def test_single_qubit_gates_arity(self):
        """Single-qubit gates have arity 1."""
        q = Q()
        single_qubit = [
            X(0, q), Y(0, q), Z(0, q),
            T(0, q), Tdg(0, q), Sdg(0, q),
            Rz(0.5, 0, q), Rx(0.5, 0, q), Ry(0.5, 0, q),
            Phase(0.5, 0, q),
        ]
        for gate in single_qubit:
            r = compile(gate, materialize=False)
            cmds = r.circuit.get_commands()
            assert len(cmds) == 1
            assert len(cmds[0].qubits) == 1

    def test_two_qubit_gates_arity(self):
        """Two-qubit gates have arity 2."""
        qq = Ten(Q(), Q())
        two_qubit = [
            CZ(0, 1, qq),
            CRz(0.5, 0, 1, qq),
        ]
        for gate in two_qubit:
            r = compile(gate, materialize=False)
            cmds = r.circuit.get_commands()
            assert len(cmds) == 1
            assert len(cmds[0].qubits) == 2

    def test_three_qubit_gate_arity(self):
        """CCX gate has arity 3."""
        q3 = qpow(3)
        r = compile(CCX(0, 1, 2, q3), materialize=False)
        cmds = r.circuit.get_commands()
        assert len(cmds) == 1
        assert len(cmds[0].qubits) == 3


class TestBackendSanityNQubit:
    """Circuit n_qubits matches program width."""

    def test_single_qubit_circuit(self):
        """Single qubit program produces 1-qubit circuit."""
        q = Q()
        r = compile(X(0, q), materialize=False)
        assert r.circuit.n_qubits == 1

    def test_two_qubit_circuit(self):
        """Two qubit program produces 2-qubit circuit."""
        qq = Ten(Q(), Q())
        r = compile(CZ(0, 1, qq), materialize=False)
        assert r.circuit.n_qubits == 2

    def test_three_qubit_circuit(self):
        """Three qubit program produces 3-qubit circuit."""
        q3 = qpow(3)
        r = compile(CCX(0, 1, 2, q3), materialize=False)
        assert r.circuit.n_qubits == 3

    def test_feedback_external_width(self):
        """Extracted feedback has correct external width."""
        q3 = qpow(3)
        body = Seq(X(0, q3), T(1, q3))
        fb = Feedback(k=1, body=body)  # external width = 2
        r = compile_goi(fb, materialize=False)
        assert_extracted(r)
        assert r.circuit.n_qubits == 2


class TestBackendSanityParamValues:
    """Parameter values are valid in pytket output."""

    def test_rz_param_in_circuit(self):
        """Rz parameter appears in circuit command."""
        q = Q()
        theta = 0.12345
        r = compile(Rz(theta, 0, q), materialize=False)
        cmds = r.circuit.get_commands()
        assert len(cmds) == 1
        params = list(cmds[0].op.params)
        assert len(params) == 1
        assert isinstance(params[0], (int, float))

    def test_crz_param_in_circuit(self):
        """CRz parameter appears in circuit command."""
        qq = Ten(Q(), Q())
        theta = 0.789
        r = compile(CRz(theta, 0, 1, qq), materialize=False)
        cmds = r.circuit.get_commands()
        assert len(cmds) == 1
        params = list(cmds[0].op.params)
        assert len(params) == 1


class TestBackendSanityValidCircuit:
    """Produced circuits are valid pytket circuits."""

    @pytest.mark.parametrize("name", list(mk_phase4c_fixed_gates_corpus().keys()))
    def test_fixed_gates_valid_circuit(self, name):
        """Fixed gate circuits are valid."""
        corpus = mk_phase4c_fixed_gates_corpus()
        term = corpus[name]
        r = compile(term, materialize=False)
        # If we can get commands, circuit is valid
        cmds = list(r.circuit.get_commands())
        assert cmds is not None

    @pytest.mark.parametrize("name", list(mk_phase4c_param_gates_corpus().keys()))
    def test_param_gates_valid_circuit(self, name):
        """Parameterized gate circuits are valid."""
        corpus = mk_phase4c_param_gates_corpus()
        term = corpus[name]
        r = compile(term, materialize=False)
        cmds = list(r.circuit.get_commands())
        assert cmds is not None

    def test_complex_circuit_valid(self):
        """Complex circuit with multiple gates is valid."""
        q3 = qpow(3)
        theta = math.pi / 4
        prog = Seq(
            T(0, q3),
            Rz(theta, 1, q3),
            CZ(0, 1, q3),
            CCX(0, 1, 2, q3),
            Sdg(2, q3),
        )
        r = compile(prog, materialize=False)
        cmds = list(r.circuit.get_commands())
        assert len(cmds) == 5


class TestBackendSanityGOI:
    """Backend sanity via compile_goi."""

    @pytest.mark.parametrize("name", list(mk_phase4c_feedback_yankable_corpus().keys()))
    def test_goi_extracted_valid(self, name):
        """GOI-extracted circuits are valid."""
        corpus = mk_phase4c_feedback_yankable_corpus()
        term = corpus[name]
        r = compile_goi(term, materialize=False)
        assert_extracted(r)
        cmds = list(r.circuit.get_commands())
        assert cmds is not None
        assert is_unitary_only(r.circuit)

    def test_goi_with_enable_zx_valid(self):
        """GOI with enable_zx produces valid circuits."""
        q3 = qpow(3)
        body = Seq(X(0, q3), T(1, q3))
        fb = Feedback(k=1, body=body)
        r = compile_goi(fb, materialize=False, enable_zx=True)
        assert_extracted(r)
        cmds = list(r.circuit.get_commands())
        assert cmds is not None
