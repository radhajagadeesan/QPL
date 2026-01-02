# tests/test_integration_with_goldens.py
from __future__ import annotations

import pytest
from pathlib import Path

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

from .utils_integration import extract_cmd_stream, has_swaps, perm_to_list, load_json

GOLDEN_DIR = Path(__file__).parent / "golden"

def qpow(n: int):
    ty = Q()
    for _ in range(n - 1):
        ty = Ten(ty, Q())
    return ty

def mk_terms():
    q = Q()
    qq = Ten(Q(), Q())
    q3 = qpow(3)

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

    t3_tenterm_offsets = TenTerm(
        H(0, q),
        S(0, q),
    )

    t4_tenterm_plus_structure = Seq(
        t3_tenterm_offsets,
        TwistTen(Q(), Q()),
    )

    t5_assoc_tensor_mix = Seq(
        AssocTenL(Q(), Q(), Q()),
        H(0, q3),
        AssocTenR(Q(), Q(), Q()),
    )

    feedback_yankable_body = Seq(
        H(0, q3),
        S(1, q3),
    )
    feedback_yankable = Feedback(k=1, body=feedback_yankable_body)

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

def load_golden(case: str):
    cmds_path = GOLDEN_DIR / f"{case}.cmds.json"
    perm_path = GOLDEN_DIR / f"{case}.perm.json"
    assert cmds_path.exists(), f"Missing golden cmds: {cmds_path}. Run scripts/generate_goldens.py"
    assert perm_path.exists(), f"Missing golden perm: {perm_path}. Run scripts/generate_goldens.py"
    return load_json(cmds_path), load_json(perm_path)

@pytest.mark.parametrize("name", ACYCLIC)
def test_compile_matches_goldens_phase0_2(terms, name):
    term = terms[name]
    golden_cmds, golden_perm = load_golden(name)

    r = compile(term, materialize=False)
    assert not has_swaps(r.circuit)
    assert extract_cmd_stream(r.circuit) == golden_cmds
    assert perm_to_list(r.perm) == golden_perm

@pytest.mark.parametrize("name", ACYCLIC)
def test_compile_goi_matches_goldens_on_acyclic(terms, name):
    term = terms[name]
    golden_cmds, golden_perm = load_golden(name)

    out = compile_goi(term, materialize=False)
    assert not isinstance(out, GOIArtifact), f"compile_goi must extract for acyclic term: {name}"
    r = out

    assert not has_swaps(r.circuit)
    assert extract_cmd_stream(r.circuit) == golden_cmds
    assert perm_to_list(r.perm) == golden_perm

def test_feedback_yankable_extracts_and_has_no_new_gates(terms):
    out = compile_goi(terms["feedback_yankable"], materialize=False)
    assert not isinstance(out, GOIArtifact)
    r = out
    assert not has_swaps(r.circuit)

    # Compare to body goldens, if present (recommended)
    # Otherwise fall back to compile(body) behavior.
    body = terms["feedback_yankable_body"]
    r_body = compile(body, materialize=False)
    assert extract_cmd_stream(r.circuit) == extract_cmd_stream(r_body.circuit)

def test_feedback_non_yankable_is_residual(terms):
    out = compile_goi(terms["feedback_residual"], materialize=False)
    assert isinstance(out, GOIArtifact)

def test_distributivity_compiles_with_tagged_layout(terms):
    """Distributivity now compiles with tagged layout model."""
    result = compile(terms["dist_deferred"], materialize=False)
    # DistL is identity on wires under the tagged layout model
    assert result.circuit is not None
    assert len(result.circuit.get_commands()) == 0
    assert not has_swaps(result.circuit)

def test_distributivity_compiles_under_compile_goi(terms):
    """Distributivity now compiles under compile_goi with tagged layout model."""
    from compile.to_pytket import CompiledGOI
    result = compile_goi(terms["dist_deferred"], materialize=False)
    # Should return CompiledGOI since it extracts successfully
    assert isinstance(result, CompiledGOI)
    assert not has_swaps(result.circuit)
