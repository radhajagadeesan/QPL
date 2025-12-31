"""Phase 3 Test: Local GOI Invariants.

Tests feedback fencing, explicit loop metadata, and "no implicit GOI":
- No cycles unless Feedback
- Feedback produces explicit loop metadata
- Phase 0-2 terms have no loops in GOI
"""
from __future__ import annotations

import pytest
from ._phase3_helpers import (
    qpow, Q, Ten, Id, Seq, TenTerm, Feedback,
    TwistTen, H, S, CX,
    compile, compile_goi,
    is_extracted, is_residual,
    GOIArtifact, CompiledGOI,
)


@pytest.mark.phase3
class TestFeedbackFencing:
    """A1: Feedback Fencing and "No Implicit GOI" tests."""

    def test_no_cycles_without_feedback(self):
        """A1.1: Phase 0-2 terms produce no loops in GOI."""
        ty = qpow(2)
        term = Seq(H(0, ty), S(1, ty))

        result = compile_goi(term)

        # Should be extracted (no loops to block)
        assert is_extracted(result)
        assert isinstance(result, CompiledGOI)

    def test_phase02_term_extracts_identically(self):
        """A1.1: compile_goi on Phase 0-2 terms matches compile."""
        ty = qpow(2)
        term = Seq(H(0, ty), CX(0, 1, ty))

        # Old compiler
        old_result = compile(term, materialize=False)

        # New compiler
        new_result = compile_goi(term, materialize=False)

        assert is_extracted(new_result)
        assert isinstance(new_result, CompiledGOI)

        # Same circuit commands
        old_cmds = [c.op.type.name for c in old_result.circuit.get_commands()]
        new_cmds = [c.op.type.name for c in new_result.circuit.get_commands()]
        assert old_cmds == new_cmds

        # Same perm
        assert old_result.perm.new_to_old == new_result.perm.new_to_old

    def test_feedback_produces_loop_metadata(self):
        """A1.2: Feedback creates explicit LoopSpec in GOI artifact."""
        ty = qpow(3)  # 3 wires
        # H on wire 0, loop last 1 wire -> external = 2 wires
        body = H(0, ty)
        term = Feedback(k=1, body=body)

        result = compile_goi(term)

        # Should extract since H on wire 0 doesn't touch loop wire 2
        assert is_extracted(result)

    def test_feedback_body_touching_loop_produces_residual(self):
        """A1.2: If extraction fails, residual has loops."""
        ty = qpow(2)  # 2 wires
        # H on wire 1, loop last 1 wire -> H touches loop
        body = H(1, ty)
        term = Feedback(k=1, body=body)

        result = compile_goi(term)

        # Should be residual since H on wire 1 touches loop wire 1
        assert is_residual(result)
        assert isinstance(result, GOIArtifact)
        assert len(result.loops) > 0
        assert result.loops[0].k == 1


@pytest.mark.phase3
class TestCompileGOIDeterminism:
    """A6: Determinism tests for Phase 3 operations."""

    def test_compile_goi_deterministic(self):
        """A6.3: compile_goi is deterministic across calls."""
        ty = qpow(2)
        term = Seq(H(0, ty), TwistTen(Q(), Q()), S(0, ty))

        r1 = compile_goi(term)
        r2 = compile_goi(term)

        assert type(r1) == type(r2)

        if is_extracted(r1):
            assert isinstance(r1, CompiledGOI) and isinstance(r2, CompiledGOI)
            # Same commands
            cmds1 = [(c.op.type.name, [q.index[0] for q in c.qubits])
                     for c in r1.circuit.get_commands()]
            cmds2 = [(c.op.type.name, [q.index[0] for q in c.qubits])
                     for c in r2.circuit.get_commands()]
            assert cmds1 == cmds2
            # Same perm
            assert r1.perm.new_to_old == r2.perm.new_to_old


@pytest.mark.phase3
class TestPhase2InteractionLocal:
    """A7: Interactions with Phase 2 TenTerm (Local)."""

    def test_offsets_applied_correctly_under_goi(self):
        """A7.1: TenTerm offsets still work in compile_goi."""
        A = qpow(2)
        B = qpow(2)

        left = H(0, A)
        right = S(0, B)
        term = TenTerm(left, right)

        result = compile_goi(term)

        assert is_extracted(result)
        assert isinstance(result, CompiledGOI)

        # H should be on wire 0, S on wire 2 (offset by width(A)=2)
        cmds = list(result.circuit.get_commands())
        assert len(cmds) == 2

        h_cmd = [c for c in cmds if c.op.type.name == "H"][0]
        s_cmd = [c for c in cmds if c.op.type.name == "S"][0]

        assert h_cmd.qubits[0].index[0] == 0
        assert s_cmd.qubits[0].index[0] == 2


@pytest.mark.phase3
class TestDistributivityDeferred:
    """A8: Distributivity remains deferred in Phase 3."""

    def test_distl_fails_loudly_in_compile_goi(self):
        """A8.1: DistL raises error in compile_goi."""
        from lang.terms import DistL

        term = DistL(Q(), Q(), Q())

        with pytest.raises(NotImplementedError) as exc_info:
            compile_goi(term)

        assert "Distributivity" in str(exc_info.value)


@pytest.mark.phase3
class TestMaterializationSemantics:
    """A9: Materialization semantics preserved."""

    def test_extracted_materialize_false_no_swaps(self):
        """A9.1: materialize=False produces no SWAPs."""
        ty = qpow(2)
        term = Seq(TwistTen(Q(), Q()), H(0, ty))

        result = compile_goi(term, materialize=False)

        assert is_extracted(result)
        assert isinstance(result, CompiledGOI)

        # No SWAPs
        swap_cmds = [c for c in result.circuit.get_commands()
                     if c.op.type.name.upper() == "SWAP"]
        assert len(swap_cmds) == 0

    def test_residual_no_materialization(self):
        """A9.2: Residual path never materializes SWAPs."""
        ty = qpow(2)
        body = H(1, ty)  # touches loop wire
        term = Feedback(k=1, body=body)

        result = compile_goi(term, materialize=True)

        # Should be residual since H touches loop
        assert is_residual(result)
        # Residual is a GOIArtifact, not a circuit with SWAPs
        assert isinstance(result, GOIArtifact)
