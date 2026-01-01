# tests/integration/test_goi_checkpoint_invariant.py
"""GOI Checkpoint Invariant Tests (Section 8 of Integration Plan).

Tests verify the core GOI principle:
"GOI routes; it does not compute."

Key invariants:
1. Extracted cases collapse to boundary permutation (no residual GOI)
2. Structural-only terms produce WirePerm-only output (no gates)
3. Gate terms without feedback produce flat circuit + perm (no residual)
"""

from __future__ import annotations

import pytest

from .helpers import (
    qpow, Q, Ten,
    Id, Seq, TenTerm, H, S, CX, TwistTen, AssocTenL, AssocTenR, Feedback,
    extract_cmd_stream, perm_to_list, perm_is_identity,
    assert_no_swaps, non_swap_signature,
)
from compile.to_pytket import compile, compile_goi, Compiled, CompiledGOI
from compile.goi import GOIArtifact
from compile.extract_zx import is_pyzx_available


class TestGOICheckpointExtracted:
    """Test checkpoint consistency for extracted cases."""

    @pytest.mark.phase4b
    def test_extracted_has_circuit_and_perm(self):
        """Extracted output includes circuit and WirePerm."""
        qq = Ten(Q(), Q())
        term = Seq(H(0, qq), CX(0, 1, qq))

        res = compile_goi(term, materialize=False)

        assert isinstance(res, CompiledGOI)
        assert res.circuit is not None
        assert res.perm is not None
        assert res.perm.n == 2

    @pytest.mark.phase4b
    def test_extracted_no_residual_components(self):
        """Extracted output has no residual GOI components."""
        q3 = qpow(3)
        term = Feedback(k=1, body=Seq(H(0, q3), S(1, q3)))

        res = compile_goi(term, materialize=False, enable_zx=True)

        # Should extract (yankable)
        assert isinstance(res, CompiledGOI), "Yankable should extract"
        # No GOI artifact returned

    @pytest.mark.phase4b
    @pytest.mark.skipif(not is_pyzx_available(), reason="PyZX not installed")
    def test_phase4b_extracted_has_valid_perm(self):
        """Phase 4B extracted output has valid boundary permutation."""
        q3 = qpow(3)
        term = Feedback(k=1, body=Id(q3))

        res = compile_goi(term, materialize=False, enable_zx=True)

        assert isinstance(res, CompiledGOI)
        perm = res.perm
        # Valid permutation: bijection
        perm_list = list(perm.new_to_old)
        assert sorted(perm_list) == list(range(perm.n))


class TestGOIRoutesNotComputes:
    """Test the principle: GOI routes; it does not compute."""

    @pytest.mark.phase4b
    def test_structural_only_produces_perm_only(self):
        """Structural-only terms produce WirePerm-only output (no gates)."""
        # Pure structural terms
        struct_terms = [
            ("twist", TwistTen(Q(), Q())),
            ("assoc_l", AssocTenL(Q(), Q(), Q())),
            ("assoc_r", AssocTenR(Q(), Q(), Q())),
            ("seq_twist", Seq(TwistTen(Q(), Q()), TwistTen(Q(), Q()))),
            ("id", Id(Ten(Q(), Q()))),
        ]

        for name, term in struct_terms:
            res = compile_goi(term, materialize=False)

            assert isinstance(res, CompiledGOI), f"{name} should extract"
            # No gates emitted
            assert len(res.circuit.get_commands()) == 0, \
                f"{name}: structural-only should emit no gates"
            # Has a permutation
            assert res.perm is not None

    @pytest.mark.phase4b
    def test_structural_produces_correct_perm(self):
        """Structural terms produce correct routing permutation."""
        # Twist on 2 qubits: swaps wires
        term = TwistTen(Q(), Q())
        res = compile_goi(term, materialize=False)

        assert isinstance(res, CompiledGOI)
        assert len(res.circuit.get_commands()) == 0
        # Twist permutes: [0,1] -> [1,0]
        assert list(res.perm.new_to_old) == [1, 0]

    @pytest.mark.phase4b
    def test_gates_without_feedback_produce_flat_circuit(self):
        """Gate terms without feedback produce flat circuit + perm."""
        qq = Ten(Q(), Q())
        term = Seq(H(0, qq), CX(0, 1, qq), S(1, qq))

        res = compile_goi(term, materialize=False)

        assert isinstance(res, CompiledGOI)
        # Has gates
        cmds = res.circuit.get_commands()
        assert len(cmds) == 3
        # No residual - it's flat
        # Perm should be identity (no structure)
        assert perm_is_identity(res.perm)

    @pytest.mark.phase4b
    def test_structure_updates_perm_gates_use_it(self):
        """Structure updates perm; gates emit through the current perm."""
        qq = Ten(Q(), Q())
        # Twist then H(0) - H should go to physical wire 1
        term = Seq(TwistTen(Q(), Q()), H(0, qq))

        res = compile_goi(term, materialize=False)

        assert isinstance(res, CompiledGOI)
        cmds = res.circuit.get_commands()
        assert len(cmds) == 1
        # H was emitted to physical wire after twist
        h_cmd = cmds[0]
        assert h_cmd.op.type.name == "H"
        # Physical wire is perm.apply(0) = 1 after twist
        assert h_cmd.qubits[0].index[0] == 1


class TestGOIFeedbackSemantics:
    """Test GOI feedback semantics."""

    @pytest.mark.phase4b
    @pytest.mark.skipif(not is_pyzx_available(), reason="PyZX not installed")
    def test_yankable_feedback_collapses_to_perm(self):
        """Yankable feedback collapses to boundary permutation."""
        q3 = qpow(3)
        term = Feedback(k=1, body=Seq(H(0, q3), S(1, q3)))

        res = compile_goi(term, materialize=False, enable_zx=True)

        assert isinstance(res, CompiledGOI)
        # External width is 2 (3 - 1 loop)
        assert res.perm.n == 2
        # Gates preserved
        assert len(res.circuit.get_commands()) == 2

    @pytest.mark.phase4b
    @pytest.mark.skipif(not is_pyzx_available(), reason="PyZX not installed")
    def test_non_yankable_remains_goi_artifact(self):
        """Non-yankable feedback remains as GOI artifact."""
        q3 = qpow(3)
        term = Feedback(k=1, body=H(2, q3))

        res = compile_goi(term, materialize=False, enable_zx=True)

        assert isinstance(res, GOIArtifact)
        # Has loops
        assert len(res.loops) > 0
        # Has atoms
        assert len(res.atoms) > 0

    @pytest.mark.phase4b
    @pytest.mark.skipif(not is_pyzx_available(), reason="PyZX not installed")
    def test_identity_feedback_produces_identity_perm(self):
        """Identity feedback produces identity permutation."""
        q3 = qpow(3)
        term = Feedback(k=1, body=Id(q3))

        res = compile_goi(term, materialize=False, enable_zx=True)

        assert isinstance(res, CompiledGOI)
        # No gates
        assert len(res.circuit.get_commands()) == 0
        # Identity perm on external wires
        assert perm_is_identity(res.perm)


class TestGOIConsistencyAcrossPhases:
    """Test GOI consistency across compilation phases."""

    @pytest.mark.phase4b
    def test_same_term_same_output_phase0_2(self):
        """Same term produces same output in Phase 0-2 (no feedback)."""
        qq = Ten(Q(), Q())
        term = Seq(H(0, qq), TwistTen(Q(), Q()), CX(0, 1, qq))

        # Via compile (Phase 0-2 path)
        res1 = compile(term, materialize=False)

        # Via compile_goi (Phase 3+ path)
        res2 = compile_goi(term, materialize=False)

        # Both should be CompiledGOI (or Compiled)
        assert isinstance(res1, Compiled)
        assert isinstance(res2, CompiledGOI)

        # Same circuit commands
        assert extract_cmd_stream(res1.circuit) == extract_cmd_stream(res2.circuit)

        # Same permutation
        assert perm_to_list(res1.perm) == perm_to_list(res2.perm)

    @pytest.mark.phase4b
    @pytest.mark.skipif(not is_pyzx_available(), reason="PyZX not installed")
    def test_enable_zx_preserves_goi_semantics(self):
        """enable_zx=True preserves GOI semantics for extracted cases."""
        q3 = qpow(3)
        term = Feedback(k=1, body=Seq(H(0, q3), S(1, q3)))

        res_off = compile_goi(term, materialize=False, enable_zx=False)
        res_on = compile_goi(term, materialize=False, enable_zx=True)

        # Both should extract
        assert isinstance(res_off, CompiledGOI)
        assert isinstance(res_on, CompiledGOI)

        # Same semantics
        assert extract_cmd_stream(res_off.circuit) == extract_cmd_stream(res_on.circuit)
        assert perm_to_list(res_off.perm) == perm_to_list(res_on.perm)
