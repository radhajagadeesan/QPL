# tests/integration/test_swap_policy_end_to_end.py
"""SWAP Policy End-to-End Tests

Tests for SWAP policy across all phases including Phase 4C:
- materialize=False => zero swaps
- materialize=True => swaps only at materialization
- Residuals never materialize
"""

from __future__ import annotations

import math
import pytest

from lang.types import Q, Ten
from lang.terms import (
    Seq, TenTerm, Feedback,
    TwistTen, AssocTenL,
    X, Y, Z, T, Tdg, Sdg, CZ, CCX,
    Rz, Rx, Ry, Phase, CRz,
    H, S, CX,
)
from compile.to_pytket import compile, compile_goi, Compiled, CompiledGOI
from compile.goi import GOIArtifact

from .helpers import (
    qpow, has_swaps,
    mk_phase0_2_corpus,
    mk_phase3_extractable_corpus,
    mk_phase4a_extracts_more_corpus,
    mk_phase4c_fixed_gates_corpus,
    mk_phase4c_param_gates_corpus,
    mk_phase4c_feedback_yankable_corpus,
    mk_phase4c_feedback_residual_corpus,
    assert_extracted,
    assert_residual,
    assert_no_swaps,
)


class TestSwapPolicyMaterializeFalse:
    """materialize=False => zero swaps for all extracted circuits."""

    @pytest.mark.parametrize("name", list(mk_phase0_2_corpus().keys()))
    def test_phase0_2_no_swaps(self, name):
        """Phase 0-2 programs have no swaps."""
        corpus = mk_phase0_2_corpus()
        term = corpus[name]
        r = compile(term, materialize=False)
        assert_no_swaps(r.circuit)

    @pytest.mark.parametrize("name", list(mk_phase3_extractable_corpus().keys()))
    def test_phase3_extractable_no_swaps(self, name):
        """Phase 3 extractable feedback has no swaps."""
        corpus = mk_phase3_extractable_corpus()
        term = corpus[name]
        r = compile_goi(term, materialize=False)
        assert_extracted(r)
        assert_no_swaps(r.circuit)

    @pytest.mark.parametrize("name", list(mk_phase4a_extracts_more_corpus().keys()))
    def test_phase4a_extracted_no_swaps(self, name):
        """Phase 4A extracted cases have no swaps."""
        corpus = mk_phase4a_extracts_more_corpus()
        term = corpus[name]
        r = compile_goi(term, materialize=False)
        assert_extracted(r)
        assert_no_swaps(r.circuit)

    @pytest.mark.parametrize("name", list(mk_phase4c_fixed_gates_corpus().keys()))
    def test_phase4c_fixed_no_swaps(self, name):
        """Phase 4C fixed gates have no swaps."""
        corpus = mk_phase4c_fixed_gates_corpus()
        term = corpus[name]
        r = compile(term, materialize=False)
        assert_no_swaps(r.circuit)

    @pytest.mark.parametrize("name", list(mk_phase4c_param_gates_corpus().keys()))
    def test_phase4c_param_no_swaps(self, name):
        """Phase 4C parameterized gates have no swaps."""
        corpus = mk_phase4c_param_gates_corpus()
        term = corpus[name]
        r = compile(term, materialize=False)
        assert_no_swaps(r.circuit)

    @pytest.mark.parametrize("name", list(mk_phase4c_feedback_yankable_corpus().keys()))
    def test_phase4c_feedback_yankable_no_swaps(self, name):
        """Phase 4C yankable feedback has no swaps."""
        corpus = mk_phase4c_feedback_yankable_corpus()
        term = corpus[name]
        r = compile_goi(term, materialize=False)
        assert_extracted(r)
        assert_no_swaps(r.circuit)


class TestSwapPolicyMaterializeTrue:
    """materialize=True => swaps appear only after extraction."""

    def test_structure_with_materialize_may_have_swaps(self):
        """Structure with non-identity perm may get swaps when materialized."""
        qq = Ten(Q(), Q())
        # TwistTen creates a non-identity perm
        prog = Seq(TwistTen(Q(), Q()), H(0, qq))

        r_no_mat = compile(prog, materialize=False)
        r_mat = compile(prog, materialize=True)

        # No swaps without materialize
        assert_no_swaps(r_no_mat.circuit)
        # With materialize, perm becomes identity (swaps may be inserted)
        from .helpers import perm_is_identity
        assert perm_is_identity(r_mat.perm)

    def test_phase4c_with_materialize(self):
        """Phase 4C gates with materialize=True."""
        qq = Ten(Q(), Q())
        prog = Seq(TwistTen(Q(), Q()), T(0, qq))

        r_mat = compile(prog, materialize=True)
        from .helpers import perm_is_identity
        assert perm_is_identity(r_mat.perm)

    def test_feedback_extracted_with_materialize(self):
        """Extracted feedback with materialize=True."""
        q3 = qpow(3)
        body = Seq(X(0, q3), T(1, q3))
        fb = Feedback(k=1, body=body)

        r_mat = compile_goi(fb, materialize=True)
        assert_extracted(r_mat)
        from .helpers import perm_is_identity
        assert perm_is_identity(r_mat.perm)


class TestSwapPolicyResidualsNeverMaterialize:
    """Residuals must never materialize or introduce swaps."""

    @pytest.mark.parametrize("name", list(mk_phase4c_feedback_residual_corpus().keys()))
    def test_residual_no_materialization(self, name):
        """Residual returns as GOIArtifact even with materialize=True."""
        corpus = mk_phase4c_feedback_residual_corpus()
        term = corpus[name]

        # With materialize=True, residual should still be residual
        r = compile_goi(term, materialize=True)
        assert_residual(r)

    def test_residual_no_swaps_in_atoms(self):
        """Residual atoms don't contain SWAP gates."""
        q3 = qpow(3)
        fb = Feedback(k=1, body=X(2, q3))
        r = compile_goi(fb, materialize=True)
        assert_residual(r)

        # No SWAP in atom gate names
        for atom in r.atoms:
            assert atom.gate_name.upper() != "SWAP"


class TestSwapPolicyStructureOnlyNoGates:
    """Structural-only programs emit no gates."""

    def test_pure_twist_no_gates(self):
        """Pure TwistTen emits no gates."""
        prog = TwistTen(Q(), Q())
        r = compile(prog, materialize=False)
        cmds = list(r.circuit.get_commands())
        assert len(cmds) == 0

    def test_pure_assoc_no_gates(self):
        """Pure AssocTenL emits no gates."""
        prog = AssocTenL(Q(), Q(), Q())
        r = compile(prog, materialize=False)
        cmds = list(r.circuit.get_commands())
        assert len(cmds) == 0

    def test_structure_sequence_no_gates(self):
        """Sequence of structure emits no gates."""
        prog = Seq(TwistTen(Q(), Q()), TwistTen(Q(), Q()))
        r = compile(prog, materialize=False)
        cmds = list(r.circuit.get_commands())
        assert len(cmds) == 0


class TestSwapPolicyWithZX:
    """SWAP policy with enable_zx flag."""

    def test_zx_extracted_no_swaps(self):
        """ZX-extracted circuits have no swaps with materialize=False."""
        q3 = qpow(3)
        body = Seq(X(0, q3), T(1, q3))
        fb = Feedback(k=1, body=body)

        r = compile_goi(fb, materialize=False, enable_zx=True)
        assert_extracted(r)
        assert_no_swaps(r.circuit)

    def test_zx_residual_no_swaps(self):
        """ZX residuals have no SWAP atoms."""
        q3 = qpow(3)
        fb = Feedback(k=1, body=X(2, q3))

        r = compile_goi(fb, materialize=False, enable_zx=True)
        assert_residual(r)
        for atom in r.atoms:
            assert atom.gate_name.upper() != "SWAP"
