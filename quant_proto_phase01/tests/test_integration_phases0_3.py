# tests/test_integration_phases0_3.py
from __future__ import annotations

import pytest

from lang.types import Q, Ten
from lang.terms import (
    Seq, TenTerm,
    TwistTen, AssocTenL, AssocTenR,
    DistL,
    H, S, CX,
    Feedback,
)
from compile.to_pytket import compile, compile_goi
from compile.goi import GOIArtifact

from .utils_integration import extract_cmd_stream, has_swaps, perm_equal


def qpow(n: int):
    """Build Q ⊗ Q ⊗ ... ⊗ Q (n times, right-associated)."""
    ty = Q()
    for _ in range(n - 1):
        ty = Ten(ty, Q())
    return ty


def mk_terms():
    q = Q()
    qq = Ten(Q(), Q())
    q3 = qpow(3)

    # Phase 0–2 representative terms (acyclic)
    t0_pure_structure = TwistTen(Q(), Q())

    t1_pure_gates = Seq(
        H(0, qq),
        CX(0, 1, qq),
        S(1, qq),
    )

    t2_structure_plus_gate = Seq(
        TwistTen(Q(), Q()),
        H(0, qq),
        TwistTen(Q(), Q()),
    )

    # Phase 2: TenTerm offsets on Q ⊗ Q
    t3_tenterm_offsets = TenTerm(
        H(0, q),
        S(0, q),
    )

    t4_tenterm_plus_structure = Seq(
        t3_tenterm_offsets,
        TwistTen(Q(), Q()),
    )

    # Assoc shuffles but remains structural; gate on 3-wire context
    t5_assoc_tensor_mix = Seq(
        AssocTenL(Q(), Q(), Q()),
        H(0, q3),
        AssocTenR(Q(), Q(), Q()),
    )

    # Phase 3 feedback
    feedback_yankable_body = Seq(
        H(0, q3),
        S(1, q3),
    )
    feedback_yankable = Feedback(k=1, body=feedback_yankable_body)

    # Single gate touching loop wire - no Seq needed for single term
    feedback_residual_body = H(2, q3)
    feedback_residual = Feedback(k=1, body=feedback_residual_body)

    dist_deferred = DistL(Q(), Q(), Q())

    return {
        "t0_pure_structure": t0_pure_structure,
        "t1_pure_gates": t1_pure_gates,
        "t2_structure_plus_gate": t2_structure_plus_gate,
        "t3_tenterm_offsets": t3_tenterm_offsets,
        "t4_tenterm_plus_structure": t4_tenterm_plus_structure,
        "t5_assoc_tensor_mix": t5_assoc_tensor_mix,
        "feedback_yankable_body": feedback_yankable_body,
        "feedback_yankable": feedback_yankable,
        "feedback_residual_body": feedback_residual_body,
        "feedback_residual": feedback_residual,
        "dist_deferred": dist_deferred,
    }


@pytest.fixture(scope="module")
def terms():
    return mk_terms()


ACYCLIC = [
    "t0_pure_structure",
    "t1_pure_gates",
    "t2_structure_plus_gate",
    "t3_tenterm_offsets",
    "t4_tenterm_plus_structure",
    "t5_assoc_tensor_mix",
]


@pytest.mark.parametrize("name", ACYCLIC)
def test_phase0_2_no_swaps_by_default(terms, name):
    term = terms[name]
    r = compile(term, materialize=False)
    assert not has_swaps(r.circuit), f"compile(..., materialize=False) must emit zero SWAPs ({name})"


@pytest.mark.parametrize("name", ACYCLIC)
def test_phase3_matches_phase0_2_on_acyclic_terms(terms, name):
    term = terms[name]
    r0 = compile(term, materialize=False)

    out = compile_goi(term, materialize=False)
    assert not isinstance(out, GOIArtifact), f"compile_goi must extract for acyclic term: {name}"
    r3 = out

    assert extract_cmd_stream(r3.circuit) == extract_cmd_stream(r0.circuit), f"command stream mismatch for {name}"
    assert perm_equal(r3.perm, r0.perm), f"final permutation mismatch for {name}"
    assert not has_swaps(r3.circuit), f"compile_goi(..., materialize=False) must emit zero SWAPs when extracted ({name})"


def test_phase3_extractable_feedback_collapses_routing_only(terms):
    term = terms["feedback_yankable"]
    body = terms["feedback_yankable_body"]

    out = compile_goi(term, materialize=False)
    assert not isinstance(out, GOIArtifact), "yankable feedback must extract"
    r = out
    assert not has_swaps(r.circuit)

    r_body = compile(body, materialize=False)
    assert extract_cmd_stream(r.circuit) == extract_cmd_stream(r_body.circuit), "feedback must not add gates"


def test_phase3_nonextractable_feedback_returns_residual(terms):
    term = terms["feedback_residual"]
    out = compile_goi(term, materialize=False)
    assert isinstance(out, GOIArtifact), "non-yankable feedback must return ResidualGOI (GOIArtifact)"
    assert len(out.loops) >= 1
    assert len(out.atoms) >= 1


def test_materialize_policy_phase0_2(terms):
    term = terms["t4_tenterm_plus_structure"]
    r0 = compile(term, materialize=False)
    assert not has_swaps(r0.circuit)

    r1 = compile(term, materialize=True)
    assert r1.circuit.n_qubits == r0.circuit.n_qubits


def test_materialize_policy_phase3(terms):
    term = terms["t4_tenterm_plus_structure"]
    out = compile_goi(term, materialize=True)
    assert not isinstance(out, GOIArtifact)

    term2 = terms["feedback_residual"]
    out2 = compile_goi(term2, materialize=True)
    assert isinstance(out2, GOIArtifact)


def test_determinism_compile_and_compile_goi(terms):
    term = terms["t5_assoc_tensor_mix"]

    r1 = compile(term, materialize=False)
    r2 = compile(term, materialize=False)
    assert extract_cmd_stream(r1.circuit) == extract_cmd_stream(r2.circuit)
    assert perm_equal(r1.perm, r2.perm)

    out1 = compile_goi(term, materialize=False)
    out2 = compile_goi(term, materialize=False)

    assert type(out1) is type(out2)
    if isinstance(out1, GOIArtifact):
        assert out1 == out2
    else:
        assert extract_cmd_stream(out1.circuit) == extract_cmd_stream(out2.circuit)
        assert perm_equal(out1.perm, out2.perm)


@pytest.mark.xfail(reason="Distributivity is deferred by design; compilation must fail loudly.")
def test_distributivity_still_deferred_under_compile(terms):
    compile(terms["dist_deferred"], materialize=False)


@pytest.mark.xfail(reason="Distributivity is deferred by design; compilation must fail loudly (also under GOI).")
def test_distributivity_still_deferred_under_compile_goi(terms):
    compile_goi(terms["dist_deferred"], materialize=False)
