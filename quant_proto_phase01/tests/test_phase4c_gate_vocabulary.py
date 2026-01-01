# tests/test_phase4c_gate_vocabulary.py
"""Phase 4C Tests: Extended Gate Vocabulary

Tests for the new primitive unitary gate atoms added in Phase 4C:
- Fixed gates: X, Y, Z, T, Tdg, Sdg, CZ, CCX
- Parameterized gates: Rz, Rx, Ry, Phase, CRz

Key invariants tested:
1. Gate opacity (gates are opaque, never rewritten)
2. Determinism (same term -> same output)
3. Compilation correctness (compile and compile_goi)
4. Parameter preservation through compilation
5. Type checking for new gates
"""

from __future__ import annotations

import math
import pytest
from typing import List

from lang.types import Q, Ten, width
from lang.terms import (
    Seq, TenTerm, Id, TwistTen, Feedback,
    # Phase 0 gates
    H, S, CX,
    # Phase 4C fixed gates
    X, Y, Z, T, Tdg, Sdg, CZ, CCX,
    # Phase 4C parameterized gates
    Rz, Rx, Ry, Phase, CRz,
)
from compile.to_pytket import compile, compile_goi, Compiled, CompiledGOI
from compile.goi import GateAtom, GOIArtifact
from typing_.check import type_of, assert_well_typed, TypeCheckError


# Helper functions
def qpow(n: int):
    """Build Q^n type."""
    ty = Q()
    for _ in range(n - 1):
        ty = Ten(ty, Q())
    return ty


def extract_cmds(circ) -> List[str]:
    """Extract command stream from circuit."""
    result = []
    for cmd in circ.get_commands():
        name = cmd.op.type.name
        wires = [q.index[0] for q in cmd.qubits]
        params = list(cmd.op.params)
        if params:
            result.append(f"{name}({','.join(map(str, wires))})[{','.join(map(str, params))}]")
        else:
            result.append(f"{name}({','.join(map(str, wires))})")
    return result


def has_swaps(circ) -> bool:
    """Check if circuit has any SWAP gates."""
    return any(cmd.op.type.name.upper() == "SWAP" for cmd in circ.get_commands())


# =============================================================================
# Type Checking Tests
# =============================================================================

class TestPhase4CTypeChecking:
    """Type checking for Phase 4C gates."""

    def test_single_wire_fixed_gates_typecheck(self):
        """Single-wire fixed gates type check correctly."""
        qq = Ten(Q(), Q())
        for gate_cls in [X, Y, Z, T, Tdg, Sdg]:
            gate = gate_cls(0, qq)
            assert_well_typed(gate)
            dom, cod = type_of(gate)
            assert dom == qq
            assert cod == qq

    def test_two_wire_fixed_gates_typecheck(self):
        """Two-wire fixed gates type check correctly."""
        qq = Ten(Q(), Q())
        cz = CZ(0, 1, qq)
        assert_well_typed(cz)
        dom, cod = type_of(cz)
        assert dom == qq
        assert cod == qq

    def test_ccx_typechecks(self):
        """CCX (Toffoli) gate type checks correctly."""
        qqq = qpow(3)
        ccx = CCX(0, 1, 2, qqq)
        assert_well_typed(ccx)
        dom, cod = type_of(ccx)
        assert width(dom) == 3
        assert width(cod) == 3

    def test_single_wire_parameterized_gates_typecheck(self):
        """Single-wire parameterized gates type check correctly."""
        qq = Ten(Q(), Q())
        for gate_cls in [(Rz, 0.5), (Rx, 0.5), (Ry, 0.5), (Phase, 0.5)]:
            cls, theta = gate_cls
            if cls == Phase:
                gate = cls(theta, 0, qq)
            else:
                gate = cls(theta, 0, qq)
            assert_well_typed(gate)
            dom, cod = type_of(gate)
            assert dom == qq
            assert cod == qq

    def test_crz_typechecks(self):
        """CRz gate type checks correctly."""
        qq = Ten(Q(), Q())
        crz = CRz(0.5, 0, 1, qq)
        assert_well_typed(crz)
        dom, cod = type_of(crz)
        assert dom == qq
        assert cod == qq

    def test_out_of_range_index_fails(self):
        """Out of range indices fail type checking."""
        qq = Ten(Q(), Q())
        with pytest.raises(TypeCheckError):
            type_of(X(5, qq))  # index 5 out of range for width 2

    def test_duplicate_indices_fail(self):
        """Duplicate indices fail for multi-wire gates."""
        qq = Ten(Q(), Q())
        with pytest.raises(TypeCheckError):
            type_of(CZ(0, 0, qq))  # same index twice

    def test_ccx_duplicate_indices_fail(self):
        """CCX with duplicate indices fails."""
        qqq = qpow(3)
        with pytest.raises(TypeCheckError):
            type_of(CCX(0, 0, 1, qqq))
        with pytest.raises(TypeCheckError):
            type_of(CCX(0, 1, 1, qqq))


# =============================================================================
# Compilation Tests (compile function)
# =============================================================================

class TestPhase4CCompile:
    """Compilation of Phase 4C gates via compile()."""

    def test_single_fixed_gates_compile(self):
        """Single-wire fixed gates compile correctly."""
        qq = Ten(Q(), Q())
        for gate_cls, name in [(X, "X"), (Y, "Y"), (Z, "Z"), (T, "T"), (Tdg, "Tdg"), (Sdg, "Sdg")]:
            gate = gate_cls(0, qq)
            r = compile(gate, materialize=False)
            assert isinstance(r, Compiled)
            assert not has_swaps(r.circuit)
            cmds = extract_cmds(r.circuit)
            assert len(cmds) == 1
            assert cmds[0] == f"{name}(0)"

    def test_cz_compiles(self):
        """CZ gate compiles correctly."""
        qq = Ten(Q(), Q())
        r = compile(CZ(0, 1, qq), materialize=False)
        cmds = extract_cmds(r.circuit)
        assert cmds == ["CZ(0,1)"]

    def test_ccx_compiles(self):
        """CCX (Toffoli) gate compiles correctly."""
        qqq = qpow(3)
        r = compile(CCX(0, 1, 2, qqq), materialize=False)
        cmds = extract_cmds(r.circuit)
        assert cmds == ["CCX(0,1,2)"]

    def test_parameterized_gates_compile(self):
        """Parameterized gates compile with correct parameters."""
        qq = Ten(Q(), Q())
        theta = math.pi / 4

        for gate_cls, name in [(Rz, "Rz"), (Rx, "Rx"), (Ry, "Ry")]:
            gate = gate_cls(theta, 0, qq)
            r = compile(gate, materialize=False)
            cmds = extract_cmds(r.circuit)
            assert len(cmds) == 1
            assert name in cmds[0]

    def test_crz_compiles(self):
        """CRz gate compiles correctly."""
        qq = Ten(Q(), Q())
        theta = math.pi / 4
        r = compile(CRz(theta, 0, 1, qq), materialize=False)
        cmds = extract_cmds(r.circuit)
        assert len(cmds) == 1
        assert "CRz" in cmds[0]

    def test_phase_gate_compiles_as_u1(self):
        """Phase gate compiles to U1."""
        qq = Ten(Q(), Q())
        phi = math.pi / 3
        r = compile(Phase(phi, 0, qq), materialize=False)
        cmds = extract_cmds(r.circuit)
        assert len(cmds) == 1
        # Phase maps to U1 in pytket
        assert "U1" in cmds[0]


# =============================================================================
# GOI Compilation Tests (compile_goi function)
# =============================================================================

class TestPhase4CCompileGOI:
    """Compilation of Phase 4C gates via compile_goi()."""

    def test_fixed_gates_through_goi(self):
        """Fixed gates compile correctly through compile_goi."""
        qq = Ten(Q(), Q())
        prog = Seq(X(0, qq), Y(1, qq), Z(0, qq))
        result = compile_goi(prog, materialize=False)
        assert isinstance(result, CompiledGOI)
        assert not has_swaps(result.circuit)
        cmds = extract_cmds(result.circuit)
        assert len(cmds) == 3

    def test_parameterized_gates_through_goi(self):
        """Parameterized gates compile correctly through compile_goi."""
        qq = Ten(Q(), Q())
        theta = math.pi / 4
        prog = Seq(Rz(theta, 0, qq), Rx(theta, 1, qq))
        result = compile_goi(prog, materialize=False)
        assert isinstance(result, CompiledGOI)
        cmds = extract_cmds(result.circuit)
        assert len(cmds) == 2

    def test_mixed_phase0_and_phase4c_gates(self):
        """Mixed Phase 0 and Phase 4C gates compile together."""
        qq = Ten(Q(), Q())
        prog = Seq(H(0, qq), T(1, qq), CX(0, 1, qq), S(0, qq))
        result = compile_goi(prog, materialize=False)
        assert isinstance(result, CompiledGOI)
        cmds = extract_cmds(result.circuit)
        assert len(cmds) == 4


# =============================================================================
# Parameter Preservation Tests
# =============================================================================

class TestPhase4CParameterPreservation:
    """Tests that gate parameters are preserved through compilation."""

    def test_rz_parameter_preserved(self):
        """Rz angle is preserved in compiled circuit."""
        qq = Ten(Q(), Q())
        theta = 0.12345
        r = compile(Rz(theta, 0, qq), materialize=False)
        cmds = r.circuit.get_commands()
        assert len(cmds) == 1
        params = list(cmds[0].op.params)
        assert len(params) == 1
        assert abs(params[0] - theta) < 1e-10

    def test_multiple_params_preserved(self):
        """Multiple parameterized gates preserve their parameters."""
        qq = Ten(Q(), Q())
        theta1 = 0.111
        theta2 = 0.222
        prog = Seq(Rz(theta1, 0, qq), Rx(theta2, 1, qq))
        r = compile(prog, materialize=False)
        cmds = r.circuit.get_commands()
        assert len(cmds) == 2
        assert abs(list(cmds[0].op.params)[0] - theta1) < 1e-10
        assert abs(list(cmds[1].op.params)[0] - theta2) < 1e-10


# =============================================================================
# Structure + Gate Interleaving Tests
# =============================================================================

class TestPhase4CStructureInterleaving:
    """Tests for structure + Phase 4C gate interleaving."""

    def test_structure_then_phase4c_gate(self):
        """Structure followed by Phase 4C gate compiles correctly."""
        qq = Ten(Q(), Q())
        prog = Seq(TwistTen(Q(), Q()), X(0, qq))
        r = compile(prog, materialize=False)
        assert not has_swaps(r.circuit)
        cmds = extract_cmds(r.circuit)
        # X should appear (structure doesn't emit gates)
        assert len(cmds) == 1
        assert "X" in cmds[0]

    def test_tenterm_with_phase4c_gates(self):
        """TenTerm with Phase 4C gates uses correct offsets."""
        q = Q()
        qq = Ten(Q(), Q())
        # Left: T on wire 0, Right: Sdg on wire 0
        # Compiled: T(0), Sdg(1)
        prog = TenTerm(T(0, q), Sdg(0, q))
        r = compile(prog, materialize=False)
        cmds = extract_cmds(r.circuit)
        assert len(cmds) == 2
        # Left emits first at offset 0, right at offset 1
        assert "T(0)" in cmds[0]
        assert "Sdg(1)" in cmds[1]


# =============================================================================
# Determinism Tests
# =============================================================================

class TestPhase4CDeterminism:
    """Determinism tests for Phase 4C gates."""

    def test_compile_deterministic(self):
        """Compiling the same term twice produces identical output."""
        qq = Ten(Q(), Q())
        theta = math.pi / 4
        prog = Seq(T(0, qq), Rz(theta, 1, qq), CZ(0, 1, qq))

        r1 = compile(prog, materialize=False)
        r2 = compile(prog, materialize=False)

        cmds1 = extract_cmds(r1.circuit)
        cmds2 = extract_cmds(r2.circuit)
        assert cmds1 == cmds2
        assert list(r1.perm.new_to_old) == list(r2.perm.new_to_old)

    def test_compile_goi_deterministic(self):
        """compile_goi is deterministic for Phase 4C gates."""
        qq = Ten(Q(), Q())
        prog = Seq(X(0, qq), Y(1, qq), CZ(0, 1, qq))

        r1 = compile_goi(prog, materialize=False)
        r2 = compile_goi(prog, materialize=False)

        assert isinstance(r1, CompiledGOI)
        assert isinstance(r2, CompiledGOI)
        cmds1 = extract_cmds(r1.circuit)
        cmds2 = extract_cmds(r2.circuit)
        assert cmds1 == cmds2


# =============================================================================
# No SWAP Invariant Tests
# =============================================================================

class TestPhase4CNoSwapInvariant:
    """Tests that Phase 4C gates don't emit SWAPs by default."""

    def test_no_swaps_by_default(self):
        """Phase 4C gates emit no SWAPs when materialize=False."""
        qqq = qpow(3)
        prog = Seq(
            T(0, qqq),
            CCX(0, 1, 2, qqq),
            Rz(0.5, 2, qqq),
            Sdg(1, qqq),
        )
        r = compile(prog, materialize=False)
        assert not has_swaps(r.circuit)

    def test_structure_plus_phase4c_no_swaps(self):
        """Structure + Phase 4C gates emit no SWAPs."""
        qq = Ten(Q(), Q())
        prog = Seq(
            TwistTen(Q(), Q()),
            Z(0, qq),
            TwistTen(Q(), Q()),
            Tdg(1, qq),
        )
        r = compile(prog, materialize=False)
        assert not has_swaps(r.circuit)


# =============================================================================
# Gate Atom Tests
# =============================================================================

class TestPhase4CGateAtoms:
    """Tests for GateAtom with Phase 4C gates."""

    def test_gate_atom_params_preserved(self):
        """GateAtom preserves params for parameterized gates."""
        atom = GateAtom("Rz", (0,), (0.5,))
        assert atom.gate_name == "Rz"
        assert atom.wires == (0,)
        assert atom.params == (0.5,)

    def test_gate_atom_support(self):
        """GateAtom.support() works correctly."""
        atom = GateAtom("CCX", (0, 1, 2), ())
        assert atom.support() == {0, 1, 2}


# =============================================================================
# Feedback + Phase 4C Tests
# =============================================================================

class TestPhase4CFeedback:
    """Tests for Feedback with Phase 4C gates."""

    def test_feedback_yankable_with_phase4c_gates(self):
        """Feedback is yankable when Phase 4C gates don't touch loop wires."""
        q3 = qpow(3)
        # Gates on external wires 0 and 1, loop on wire 2
        body = Seq(X(0, q3), T(1, q3))
        fb = Feedback(k=1, body=body)
        result = compile_goi(fb, materialize=False)
        assert isinstance(result, CompiledGOI)
        assert not has_swaps(result.circuit)

    def test_feedback_residual_with_phase4c_gates(self):
        """Feedback is residual when Phase 4C gates touch loop wires."""
        q3 = qpow(3)
        # Gate on loop wire 2
        body = Z(2, q3)
        fb = Feedback(k=1, body=body)
        result = compile_goi(fb, materialize=False)
        assert isinstance(result, GOIArtifact)
