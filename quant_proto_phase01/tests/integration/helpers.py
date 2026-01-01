# tests/integration/helpers.py
"""Integration test helpers for Phases 0-4A."""
from __future__ import annotations

from typing import List, Dict, Any, Tuple
from dataclasses import dataclass
import hashlib
import json

from pytket import Circuit

from lang.types import Q, Ten, width
from lang.terms import (
    Term, Id, Seq, TenTerm,
    TwistTen, AssocTenL, AssocTenR,
    TwistPlus, AssocPlusL, AssocPlusR,
    DistL, DistR,
    H, S, CX,
    Feedback,
)
from compile.to_pytket import compile, compile_goi, Compiled, CompiledGOI
from compile.goi import GOIArtifact, GateAtom, try_extract
from compile.extract_v2 import try_extract_v2
from core.perm import WirePerm, identity


# -----------------------------------------------------------------
# Type builders
# -----------------------------------------------------------------

def qpow(n: int):
    """Build Q ⊗ Q ⊗ ... ⊗ Q (n times, right-associated)."""
    assert n >= 1
    ty = Q()
    for _ in range(n - 1):
        ty = Ten(ty, Q())
    return ty


# -----------------------------------------------------------------
# Circuit introspection
# -----------------------------------------------------------------

def extract_cmd_stream(circ: Circuit) -> List[str]:
    """Canonical command stream for determinism/equality checks."""
    result: List[str] = []
    for cmd in circ.get_commands():
        name = cmd.op.type.name
        wires = [q.index[0] for q in cmd.qubits]
        result.append(f"{name}({','.join(map(str, wires))})")
    return result


def has_swaps(circ: Circuit) -> bool:
    """Check if circuit contains any SWAP operations."""
    return any(cmd.op.type.name.upper() == "SWAP" for cmd in circ.get_commands())


def get_gate_names(circ: Circuit) -> List[str]:
    """Get list of gate operation names."""
    return [cmd.op.type.name for cmd in circ.get_commands()]


def is_unitary_only(circ: Circuit) -> bool:
    """Check if circuit contains only unitary gates (no measurements, etc.)."""
    # For now, just check for known unitary gates
    allowed = {"H", "S", "CX", "SWAP", "X", "Y", "Z", "T", "Tdg", "Sdg", "Rz", "Rx", "Ry"}
    for cmd in circ.get_commands():
        if cmd.op.type.name.upper() not in {g.upper() for g in allowed}:
            return False
    return True


# -----------------------------------------------------------------
# Permutation helpers
# -----------------------------------------------------------------

def perm_equal(p: WirePerm, q: WirePerm) -> bool:
    """Check if two permutations are equal."""
    return (p.n == q.n) and (list(p.new_to_old) == list(q.new_to_old))


def perm_is_identity(p: WirePerm) -> bool:
    """Check if permutation is identity."""
    return list(p.new_to_old) == list(range(p.n))


def perm_to_list(p: WirePerm) -> List[int]:
    """Convert perm to list for serialization."""
    return list(p.new_to_old)


# -----------------------------------------------------------------
# Residual fingerprinting
# -----------------------------------------------------------------

def residual_fingerprint(goi: GOIArtifact) -> str:
    """Generate a deterministic fingerprint for a residual GOIArtifact.

    This is used for regression testing - same input should always
    produce the same fingerprint.
    """
    data = {
        "n_in": goi.n_in,
        "n_out": goi.n_out,
        "perm": list(goi.perm.new_to_old),
        "atoms": [(a.gate_name, list(a.wires)) for a in goi.atoms],
        "loops": [l.k for l in goi.loops],
    }
    # Use sorted keys for determinism
    json_str = json.dumps(data, sort_keys=True)
    return hashlib.sha256(json_str.encode()).hexdigest()[:32]


def atoms_equal(a1: Tuple[GateAtom, ...], a2: Tuple[GateAtom, ...]) -> bool:
    """Check if two atom tuples are equal."""
    if len(a1) != len(a2):
        return False
    for x, y in zip(a1, a2):
        if x.gate_name != y.gate_name or x.wires != y.wires:
            return False
    return True


# -----------------------------------------------------------------
# Rendering for golden comparisons
# -----------------------------------------------------------------

def render_extracted(result: CompiledGOI) -> Dict[str, Any]:
    """Render an extracted result for golden comparison."""
    return {
        "commands": extract_cmd_stream(result.circuit),
        "perm": perm_to_list(result.perm),
        "n_qubits": result.circuit.n_qubits,
    }


def render_residual(goi: GOIArtifact) -> Dict[str, Any]:
    """Render a residual GOIArtifact for golden comparison."""
    return {
        "n_in": goi.n_in,
        "n_out": goi.n_out,
        "perm": perm_to_list(goi.perm),
        "atoms": [(a.gate_name, list(a.wires)) for a in goi.atoms],
        "loops": [l.k for l in goi.loops],
        "fingerprint": residual_fingerprint(goi),
    }


# -----------------------------------------------------------------
# Standard test corpora
# -----------------------------------------------------------------

def mk_phase0_2_corpus() -> Dict[str, Term]:
    """Phase 0-2 acyclic test corpus."""
    q = Q()
    qq = Ten(Q(), Q())
    q3 = qpow(3)
    q4 = qpow(4)

    return {
        # Pure structure
        "p0_struct_twist": TwistTen(Q(), Q()),
        "p0_struct_assoc_l": AssocTenL(Q(), Q(), Q()),
        "p0_struct_assoc_r": AssocTenR(Q(), Q(), Q()),
        "p0_struct_seq_twists": Seq(TwistTen(Q(), Q()), TwistTen(Q(), Q())),

        # Pure gates
        "p1_gate_h": H(0, q),
        "p1_gate_s": S(0, q),
        "p1_gate_cx": CX(0, 1, qq),
        "p1_gate_seq": Seq(H(0, qq), CX(0, 1, qq), S(1, qq)),

        # Mixed structure + gates
        "p1_mixed_twist_h": Seq(TwistTen(Q(), Q()), H(0, qq)),
        "p1_mixed_h_twist_h": Seq(H(0, qq), TwistTen(Q(), Q()), H(0, qq)),
        "p1_mixed_assoc_h": Seq(AssocTenL(Q(), Q(), Q()), H(0, q3)),

        # TenTerm (Phase 2)
        "p2_tenterm_basic": TenTerm(H(0, q), S(0, q)),
        "p2_tenterm_cx": TenTerm(CX(0, 1, qq), H(0, q)),
        "p2_tenterm_seq": Seq(TenTerm(H(0, q), S(0, q)), TwistTen(Q(), Q())),
        "p2_tenterm_nested": TenTerm(Seq(H(0, q), S(0, q)), H(0, q)),
    }


def mk_phase3_extractable_corpus() -> Dict[str, Term]:
    """Phase 3 extractable feedback corpus (yankable).

    IMPORTANT: These must be truly yankable - gates must not touch loop wires
    AND external wires must not map to loop wires after structure.
    """
    q3 = qpow(3)
    q4 = qpow(4)

    # Feedback with gates NOT touching loop wires AND no structure that
    # remaps external wires to loop wires
    return {
        # Basic: H and S on wires 0,1, loop on wire 2
        "p3_feedback_yankable_basic": Feedback(k=1, body=Seq(H(0, q3), S(1, q3))),
        # CX on wires 0,1, loop on wire 2
        "p3_feedback_yankable_cx": Feedback(k=1, body=CX(0, 1, q3)),
        # Pure identity (no gates, no structure) - trivially yankable
        "p3_feedback_yankable_id": Feedback(k=1, body=Id(q3)),
        # k=2 with gates on wires 0,1, loop on wires 2,3
        "p3_feedback_k2_yankable": Feedback(k=2, body=Seq(H(0, q4), S(1, q4))),
    }


def mk_phase3_residual_corpus() -> Dict[str, Term]:
    """Phase 3 residual feedback corpus (not yankable)."""
    q3 = qpow(3)
    q4 = qpow(4)

    # Feedback with gates TOUCHING loop wires
    return {
        "p3_feedback_residual_h_on_loop": Feedback(k=1, body=H(2, q3)),
        "p3_feedback_residual_s_on_loop": Feedback(k=1, body=S(2, q3)),
        "p3_feedback_residual_cx_spans": Feedback(k=1, body=CX(1, 2, q3)),
        "p3_feedback_residual_cx_both_loop": Feedback(k=2, body=CX(2, 3, q4)),
        "p3_feedback_residual_mixed": Feedback(
            k=1,
            body=Seq(H(0, q3), H(2, q3))  # H(0) ok, H(2) touches loop
        ),
    }


def mk_phase4a_extracts_more_corpus() -> Dict[str, Term]:
    """Phase 4A cases that extract more than Phase 3.

    With effective wire semantics, Phase 4A checks if gates already
    avoid loop wires via their effective positions.

    Note: With effective wire semantics, there's no additional "routing"
    analysis beyond what Phase 3 does. Phase 4A just provides a cleaner
    architecture but extracts the same cases as Phase 3 for feedback.
    """
    q3 = qpow(3)
    q4 = qpow(4)

    # Cases where gates are positioned to avoid loop wires
    return {
        # Gate on wire 0, loop on wire 2 - clearly disjoint
        "p4a_extracts_h_disjoint": Feedback(k=1, body=H(0, q3)),

        # Multiple gates, all avoiding loop (wires 0,1 for gates, wire 2 for loop)
        "p4a_extracts_multi_gate": Feedback(
            k=1,
            body=Seq(H(0, q3), S(0, q3), CX(0, 1, q3))
        ),

        # Single S gate avoiding loop
        "p4a_extracts_s_disjoint": Feedback(k=1, body=S(1, q3)),
    }


def mk_phase4a_stays_residual_corpus() -> Dict[str, Term]:
    """Phase 4A cases that must remain residual.

    These are cases where gates genuinely touch loop wires.
    """
    q3 = qpow(3)
    q4 = qpow(4)

    return {
        # Gate directly on loop wire
        "p4a_residual_h_on_loop": Feedback(k=1, body=H(2, q3)),

        # CX spans into loop
        "p4a_residual_cx_spans_loop": Feedback(k=1, body=CX(1, 2, q3)),

        # Multiple gates, one on loop
        "p4a_residual_mixed_touch": Feedback(
            k=1,
            body=Seq(H(0, q3), H(2, q3))
        ),

        # CX with both on loop wires
        "p4a_residual_cx_both_loop": Feedback(k=2, body=CX(2, 3, q4)),
    }


def mk_dist_failure_corpus() -> Dict[str, Term]:
    """Distributivity cases that must fail loudly."""
    return {
        "dist_distl": DistL(Q(), Q(), Q()),
        "dist_distr": DistR(Q(), Q(), Q()),
        "dist_seq_distl": Seq(Id(Ten(Q(), Q())), DistL(Q(), Q(), Q())),
    }


# -----------------------------------------------------------------
# Assertion helpers
# -----------------------------------------------------------------

def assert_no_swaps(circ: Circuit, msg: str = "") -> None:
    """Assert circuit has no SWAPs."""
    assert not has_swaps(circ), f"Expected no SWAPs{': ' + msg if msg else ''}"


def assert_unitary_only(circ: Circuit, msg: str = "") -> None:
    """Assert circuit contains only unitary ops."""
    assert is_unitary_only(circ), f"Expected only unitary ops{': ' + msg if msg else ''}"


def assert_extracted(result, msg: str = "") -> CompiledGOI:
    """Assert result is extracted (not residual)."""
    assert not isinstance(result, GOIArtifact), f"Expected extraction{': ' + msg if msg else ''}"
    return result


def assert_residual(result, msg: str = "") -> GOIArtifact:
    """Assert result is residual."""
    assert isinstance(result, GOIArtifact), f"Expected residual{': ' + msg if msg else ''}"
    return result


# -----------------------------------------------------------------
# Additional corpus builders for Phase 4B
# -----------------------------------------------------------------

def mk_phase0_acyclic_corpus() -> Dict[str, Term]:
    """Phase 0 pure structure corpus."""
    return {
        "p0_struct_twist": TwistTen(Q(), Q()),
        "p0_struct_assoc_l": AssocTenL(Q(), Q(), Q()),
        "p0_struct_assoc_r": AssocTenR(Q(), Q(), Q()),
        "p0_struct_seq_twists": Seq(TwistTen(Q(), Q()), TwistTen(Q(), Q())),
    }


def mk_phase1_structure_corpus() -> Dict[str, Term]:
    """Phase 1 structure + gates corpus."""
    q = Q()
    qq = Ten(Q(), Q())
    q3 = qpow(3)

    return {
        "p1_gate_h": H(0, q),
        "p1_gate_s": S(0, q),
        "p1_gate_cx": CX(0, 1, qq),
        "p1_gate_seq": Seq(H(0, qq), CX(0, 1, qq), S(1, qq)),
        "p1_mixed_twist_h": Seq(TwistTen(Q(), Q()), H(0, qq)),
        "p1_mixed_h_twist_h": Seq(H(0, qq), TwistTen(Q(), Q()), H(0, qq)),
        "p1_mixed_assoc_h": Seq(AssocTenL(Q(), Q(), Q()), H(0, q3)),
    }


def mk_phase2_tenterm_corpus() -> Dict[str, Term]:
    """Phase 2 TenTerm corpus."""
    q = Q()
    qq = Ten(Q(), Q())

    return {
        "p2_tenterm_basic": TenTerm(H(0, q), S(0, q)),
        "p2_tenterm_cx": TenTerm(CX(0, 1, qq), H(0, q)),
        "p2_tenterm_seq": Seq(TenTerm(H(0, q), S(0, q)), TwistTen(Q(), Q())),
        "p2_tenterm_nested": TenTerm(Seq(H(0, q), S(0, q)), H(0, q)),
    }


def mk_phase4a_residual_corpus() -> Dict[str, Term]:
    """Phase 4A residual corpus - alias for mk_phase4a_stays_residual_corpus."""
    return mk_phase4a_stays_residual_corpus()


# -----------------------------------------------------------------
# Additional helpers for Phase 4B
# -----------------------------------------------------------------

def compile_goi_safe(term: Term, *, materialize: bool = False, enable_zx: bool = False):
    """Compile with error handling."""
    try:
        return compile_goi(term, materialize=materialize, enable_zx=enable_zx)
    except Exception as e:
        return e


def compile_term(term: Term, *, materialize: bool = False):
    """Compile with standard compile() function."""
    return compile(term, materialize=materialize)


def is_goi_artifact(result) -> bool:
    """Check if result is a GOI artifact (residual)."""
    return isinstance(result, GOIArtifact)


@dataclass(frozen=True)
class CmdSig:
    """Command signature for comparison."""
    op: str
    qubits: Tuple[int, ...]


def non_swap_signature(circ: Circuit) -> List[CmdSig]:
    """Extract non-SWAP command signature for comparison."""
    result = []
    for cmd in circ.get_commands():
        name = cmd.op.type.name
        if name.upper() == "SWAP":
            continue
        wires = tuple(int(q.index[0]) for q in cmd.qubits)
        result.append(CmdSig(op=name, qubits=wires))
    return result
