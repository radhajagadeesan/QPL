# tests/integration/test_phase4c_support_reindexing.py
"""Phase 4C Support Reindexing Tests

Tests that new 4C atoms respect the Phase 4A decision:
- GateAtom wires are logical
- Commutes with routing by support reindexing
"""

from __future__ import annotations

import math
import pytest

from lang.types import Q, Ten
from lang.terms import (
    Seq, TenTerm,
    TwistTen, AssocTenL, AssocTenR,
    X, Y, Z, T, Tdg, Sdg, CZ, CCX,
    Rz, Rx, Ry, Phase, CRz,
    H, S, CX,
)
from compile.to_pytket import compile, compile_goi

from .helpers import (
    qpow,
    has_swaps,
    extract_cmd_stream,
    perm_to_list,
    perm_is_identity,
)


class TestPhase4CRoutingCommutation:
    """Pure routing commutation with Phase 4C gates."""

    def test_twist_then_gate(self):
        """Twist followed by gate: perm accumulates, gate reindexed."""
        qq = Ten(Q(), Q())
        # Twist swaps wires, then X on wire 0
        prog = Seq(TwistTen(Q(), Q()), X(0, qq))
        r = compile(prog, materialize=False)
        assert not has_swaps(r.circuit)
        # X should appear at physical wire 1 (after twist reindexing)
        cmds = extract_cmd_stream(r.circuit)
        assert len(cmds) == 1
        assert "X(1)" in cmds[0]

    def test_gate_then_twist(self):
        """Gate followed by twist: gate at original position."""
        qq = Ten(Q(), Q())
        prog = Seq(X(0, qq), TwistTen(Q(), Q()))
        r = compile(prog, materialize=False)
        assert not has_swaps(r.circuit)
        cmds = extract_cmd_stream(r.circuit)
        assert len(cmds) == 1
        assert "X(0)" in cmds[0]

    def test_twist_gate_twist(self):
        """Perm ; Gate ; Perm^{-1}: perm cancels."""
        qq = Ten(Q(), Q())
        # TwistTen is its own inverse
        prog = Seq(TwistTen(Q(), Q()), X(0, qq), TwistTen(Q(), Q()))
        r = compile(prog, materialize=False)
        assert not has_swaps(r.circuit)
        cmds = extract_cmd_stream(r.circuit)
        assert len(cmds) == 1
        # X at wire 0 through twist -> physical 1, then twist back
        # Final perm should reflect the composition
        assert "X(1)" in cmds[0]

    def test_parameterized_gate_with_routing(self):
        """Parameterized gate with routing."""
        qq = Ten(Q(), Q())
        theta = math.pi / 4
        prog = Seq(TwistTen(Q(), Q()), Rz(theta, 0, qq))
        r = compile(prog, materialize=False)
        assert not has_swaps(r.circuit)
        cmds = extract_cmd_stream(r.circuit)
        assert len(cmds) == 1
        # Rz on wire 0 appears at physical 1 after twist
        assert "Rz(1)" in cmds[0]

    def test_assoc_then_gate(self):
        """AssocTenL followed by gate."""
        q3 = qpow(3)
        # AssocL: (a⊗b)⊗c -> a⊗(b⊗c) - logical perm change
        prog = Seq(AssocTenL(Q(), Q(), Q()), T(0, q3))
        r = compile(prog, materialize=False)
        assert not has_swaps(r.circuit)
        cmds = extract_cmd_stream(r.circuit)
        assert len(cmds) == 1


class TestPhase4CRoutingWithTenTerm:
    """Routing with TenTerm offset semantics."""

    def test_tenterm_fixed_gates_offset(self):
        """TenTerm applies correct offsets to Phase 4C gates."""
        q = Q()
        # Left: X on wire 0, Right: Y on wire 0
        prog = TenTerm(X(0, q), Y(0, q))
        r = compile(prog, materialize=False)
        cmds = extract_cmd_stream(r.circuit)
        assert len(cmds) == 2
        assert "X(0)" in cmds[0]
        assert "Y(1)" in cmds[1]

    def test_tenterm_param_gates_offset(self):
        """TenTerm applies correct offsets to parameterized gates."""
        q = Q()
        theta = 0.5
        prog = TenTerm(Rz(theta, 0, q), Rx(theta, 0, q))
        r = compile(prog, materialize=False)
        cmds = extract_cmd_stream(r.circuit)
        assert len(cmds) == 2
        assert "Rz(0)" in cmds[0]
        assert "Rx(1)" in cmds[1]

    def test_tenterm_with_structure_in_branch(self):
        """TenTerm with structure in one branch."""
        q = Q()
        qq = Ten(Q(), Q())
        # Left: twist + T, Right: X
        left = Seq(TwistTen(Q(), Q()), T(0, qq))
        right = X(0, q)
        prog = TenTerm(left, right)
        r = compile(prog, materialize=False)
        assert not has_swaps(r.circuit)
        cmds = extract_cmd_stream(r.circuit)
        # T at wire 0 after twist goes to physical 1
        # X at offset 2 (width of left=2)
        assert len(cmds) == 2


class TestPhase4CRoutingDeterminism:
    """Determinism of routing + gate reindexing."""

    def test_routing_deterministic(self):
        """Same program produces same reindexed output."""
        qq = Ten(Q(), Q())
        theta = 0.5
        prog = Seq(TwistTen(Q(), Q()), Rz(theta, 0, qq), TwistTen(Q(), Q()))

        results = []
        for _ in range(5):
            r = compile(prog, materialize=False)
            cmds = extract_cmd_stream(r.circuit)
            perm = perm_to_list(r.perm)
            results.append((cmds, perm))

        for i in range(1, 5):
            assert results[0] == results[i]

    def test_complex_routing_deterministic(self):
        """Complex routing with multiple gates is deterministic."""
        q3 = qpow(3)
        theta = math.pi / 6
        prog = Seq(
            AssocTenL(Q(), Q(), Q()),
            T(0, q3),
            Rz(theta, 1, q3),
            AssocTenR(Q(), Q(), Q()),
            Sdg(2, q3),
        )

        results = []
        for _ in range(5):
            r = compile(prog, materialize=False)
            cmds = extract_cmd_stream(r.circuit)
            results.append(cmds)

        for i in range(1, 5):
            assert results[0] == results[i]


class TestPhase4CRoutingViaGOI:
    """Routing behavior via compile_goi."""

    def test_goi_routing_same_as_compile(self):
        """compile_goi produces same routing as compile for acyclic."""
        qq = Ten(Q(), Q())
        theta = 0.5
        prog = Seq(TwistTen(Q(), Q()), Rz(theta, 0, qq))

        r1 = compile(prog, materialize=False)
        r2 = compile_goi(prog, materialize=False)

        cmds1 = extract_cmd_stream(r1.circuit)
        cmds2 = extract_cmd_stream(r2.circuit)
        assert cmds1 == cmds2
