# scripts/generate_goldens.py
from __future__ import annotations

from pathlib import Path

from lang.types import Q, Ten
from lang.terms import (
    Seq, TenTerm,
    TwistTen, AssocTenL, AssocTenR,
    H, S, CX,
    Feedback,
)
from compile.to_pytket import compile
from tests.utils_integration import extract_cmd_stream, perm_to_list, save_json

GOLDEN_DIR = Path(__file__).resolve().parents[1] / "tests" / "golden"

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

    # Optional: store body goldens as well (useful reference for feedback)
    feedback_yankable_body = Seq(
        H(0, q3),
        S(1, q3),
    )

    return {
        "t0_pure_structure": t0_pure_structure,
        "t1_pure_gates": t1_pure_gates,
        "t2_structure_plus_gate": t2_structure_plus_gate,
        "t3_tenterm_offsets": t3_tenterm_offsets,
        "t4_tenterm_plus_structure": t4_tenterm_plus_structure,
        "t5_assoc_tensor_mix": t5_assoc_tensor_mix,
        "feedback_yankable_body": feedback_yankable_body,
    }

def main():
    GOLDEN_DIR.mkdir(parents=True, exist_ok=True)
    terms = mk_terms()
    for name, term in terms.items():
        r = compile(term, materialize=False)
        cmds = extract_cmd_stream(r.circuit)
        perm = perm_to_list(r.perm)
        save_json(GOLDEN_DIR / f"{name}.cmds.json", cmds)
        save_json(GOLDEN_DIR / f"{name}.perm.json", perm)
        print(f"Wrote goldens for {name}: {len(cmds)} cmds, perm n={len(perm)}")
    print(f"Goldens written to {GOLDEN_DIR}")

if __name__ == "__main__":
    main()
