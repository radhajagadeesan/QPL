# tests/integration/test_firewall_canary.py
"""Firewall Canary Tests (Section 9 of Integration Plan).

Tests verify that the compiler never inspects gate internals beyond
the declared interface (gate_name, wires/support).

The "firewall" principle: structural rewrites never enter gate atoms.

These tests use:
1. Normal gates to verify behavior
2. Property checks that gate atoms are treated opaquely
"""

from __future__ import annotations

import pytest
from dataclasses import dataclass
from typing import Tuple, Set

from .helpers import (
    qpow, Q, Ten,
    Id, Seq, TenTerm, H, S, CX, TwistTen, AssocTenL, Feedback,
    extract_cmd_stream, perm_to_list, residual_fingerprint,
)
from compile.to_pytket import compile_goi, CompiledGOI
from compile.goi import GOIArtifact, GateAtom
from compile.extract_zx import is_pyzx_available


pytestmark = pytest.mark.skipif(
    not is_pyzx_available(),
    reason="PyZX not installed"
)


class TestFirewallGateOpacity:
    """Test that gates are treated as opaque boxes."""

    @pytest.mark.phase4b
    def test_gate_names_preserved_exactly(self):
        """Gate names are preserved exactly through compilation."""
        q3 = qpow(3)
        term = Feedback(k=1, body=Seq(H(0, q3), S(1, q3), CX(0, 1, q3)))

        res = compile_goi(term, materialize=False, enable_zx=True)

        if isinstance(res, GOIArtifact):
            gate_names = [a.gate_name for a in res.atoms]
            assert gate_names == ["H", "S", "CX"], "Gate names must be preserved"
        else:
            # Extracted - check circuit
            cmd_stream = extract_cmd_stream(res.circuit)
            assert "H(0)" in cmd_stream[0]
            assert "S(1)" in cmd_stream[1]
            assert "CX(0,1)" in cmd_stream[2]

    @pytest.mark.phase4b
    def test_gate_wire_order_preserved(self):
        """Gate wire order is preserved (not reordered)."""
        q3 = qpow(3)
        # CX with control=0, target=1
        term = Feedback(k=1, body=CX(0, 1, q3))

        res = compile_goi(term, materialize=False, enable_zx=True)

        if isinstance(res, GOIArtifact):
            cx_atom = [a for a in res.atoms if a.gate_name == "CX"][0]
            # Wire order must be preserved (control, target)
            assert cx_atom.wires[0] == 0  # control
            assert cx_atom.wires[1] == 1  # target
        else:
            cmd_stream = extract_cmd_stream(res.circuit)
            # CX(control,target)
            assert "CX(0,1)" in cmd_stream[0]

    @pytest.mark.phase4b
    def test_gate_sequence_order_preserved(self):
        """Gate emission order is preserved through all phases."""
        # Use non-feedback term with gates on same wire
        qq = Ten(Q(), Q())
        term = Seq(H(0, qq), S(0, qq), CX(0, 1, qq), H(0, qq))

        res = compile_goi(term, materialize=False, enable_zx=True)

        assert isinstance(res, CompiledGOI)
        cmd_stream = extract_cmd_stream(res.circuit)
        # Gates on same wire must be in order
        assert cmd_stream == ["H(0)", "S(0)", "CX(0,1)", "H(0)"]


class TestFirewallNoGateRewriting:
    """Test that gates are never rewritten/modified."""

    @pytest.mark.phase4b
    def test_gates_not_fused(self):
        """Adjacent gates are not fused (e.g., H;H != Id)."""
        q3 = qpow(3)
        # H;H on same wire - should NOT be cancelled
        term = Feedback(k=1, body=Seq(H(0, q3), H(0, q3)))

        res = compile_goi(term, materialize=False, enable_zx=True)

        if isinstance(res, GOIArtifact):
            h_count = sum(1 for a in res.atoms if a.gate_name == "H")
            assert h_count == 2, "Gates must not be fused"
        else:
            cmd_stream = extract_cmd_stream(res.circuit)
            assert cmd_stream.count("H(0)") == 2, "Gates must not be fused"

    @pytest.mark.phase4b
    def test_gates_not_cancelled(self):
        """Inverse gates are not cancelled (e.g., S;S;S;S != Id)."""
        q3 = qpow(3)
        # S^4 = Id for phase gate, but we should NOT cancel
        term = Feedback(k=1, body=Seq(S(0, q3), S(0, q3), S(0, q3), S(0, q3)))

        res = compile_goi(term, materialize=False, enable_zx=True)

        if isinstance(res, GOIArtifact):
            s_count = sum(1 for a in res.atoms if a.gate_name == "S")
            assert s_count == 4, "Gates must not be cancelled"
        else:
            cmd_stream = extract_cmd_stream(res.circuit)
            assert cmd_stream.count("S(0)") == 4, "Gates must not be cancelled"

    @pytest.mark.phase4b
    def test_gates_not_commuted(self):
        """Gates are not commuted (order preserved)."""
        q3 = qpow(3)
        # H on wire 0, then S on wire 0 - order matters
        term = Feedback(k=1, body=Seq(H(0, q3), S(0, q3)))

        res = compile_goi(term, materialize=False, enable_zx=True)

        if isinstance(res, GOIArtifact):
            gate_seq = [a.gate_name for a in res.atoms]
            assert gate_seq == ["H", "S"], "Gate order must not change"
        else:
            cmd_stream = extract_cmd_stream(res.circuit)
            assert cmd_stream == ["H(0)", "S(0)"], "Gate order must not change"


class TestFirewallOnlyDeclaredInterface:
    """Test that only declared gate interface is used."""

    @pytest.mark.phase4b
    def test_gate_atom_support_is_wires(self):
        """GateAtom.support() returns exactly the wires set."""
        atom = GateAtom("CX", (0, 2))
        assert atom.support() == {0, 2}

        atom2 = GateAtom("H", (1,))
        assert atom2.support() == {1}

    @pytest.mark.phase4b
    def test_extraction_only_uses_support(self):
        """Extraction decision uses only wire support, not gate semantics."""
        q3 = qpow(3)

        # H on wire 0 (not loop) - should extract
        term1 = Feedback(k=1, body=H(0, q3))
        res1 = compile_goi(term1, materialize=False, enable_zx=True)
        assert isinstance(res1, CompiledGOI), "H on non-loop should extract"

        # H on wire 2 (loop) - should not extract
        term2 = Feedback(k=1, body=H(2, q3))
        res2 = compile_goi(term2, materialize=False, enable_zx=True)
        assert isinstance(res2, GOIArtifact), "H on loop should be residual"

        # Decision is based purely on wire position, not gate type


class TestFirewallZXOpaque:
    """Test that ZX translation treats gates as opaque boxes."""

    @pytest.mark.phase4b
    def test_zx_preserves_gate_identity(self):
        """ZX simplification doesn't change gate identity."""
        q3 = qpow(3)
        # H and S should remain H and S, not get converted
        term = Feedback(k=1, body=Seq(H(2, q3), S(2, q3)))

        res_off = compile_goi(term, materialize=False, enable_zx=False)
        res_on = compile_goi(term, materialize=False, enable_zx=True)

        assert isinstance(res_off, GOIArtifact)
        assert isinstance(res_on, GOIArtifact)

        # Gate names unchanged
        names_off = [a.gate_name for a in res_off.atoms]
        names_on = [a.gate_name for a in res_on.atoms]
        assert names_off == names_on == ["H", "S"]

    @pytest.mark.phase4b
    def test_zx_preserves_gate_count(self):
        """ZX simplification doesn't change gate count."""
        q3 = qpow(3)
        term = Feedback(k=1, body=Seq(H(0, q3), S(0, q3), CX(0, 1, q3), H(2, q3)))

        res_off = compile_goi(term, materialize=False, enable_zx=False)
        res_on = compile_goi(term, materialize=False, enable_zx=True)

        assert isinstance(res_off, GOIArtifact)
        assert isinstance(res_on, GOIArtifact)

        # Same number of atoms
        assert len(res_off.atoms) == len(res_on.atoms) == 4
