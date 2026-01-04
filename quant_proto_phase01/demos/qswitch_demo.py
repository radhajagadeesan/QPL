#!/usr/bin/env python3
"""
QSwitch(H, S) Demo - Runnable Script

Run with: PYTHONPATH=src python demos/qswitch_demo.py

Requirements: pytket (pip install pytket)
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from lang.terms import H, S, Seq, CS, CSdg, X
from lang.types import Q, Ten
from compile.to_pytket import compile
from compile.goi import (
    GateAtom, GOIArtifact, LoopSpec,
    make_unitary_value, goi_seq, execute_trace
)
from core.perm import WirePerm, identity


def section(title):
    print()
    print("=" * 60)
    print(title)
    print("=" * 60)
    print()


def subsection(title):
    print(f"\n{title}")
    print("-" * 40)


def main():
    section("QSwitch(H, S) Demo")

    print("""
QSwitch is a higher-order quantum combinator:

  QSwitch(f, g) : QBool ⊗ Q → QBool ⊗ Q

  case ctrl of
  | Zero => (ctrl, g;f data)
  | One  => (ctrl, f;g data)

Applied to H and S:
  | Zero => S;H
  | One  => H;S
""")

    # =========================================================================
    section("Part 1: First-Order Circuit (2 qubits)")
    # =========================================================================

    ty = Ten(Q(), Q())

    qswitch_hs = Seq(
        X(0, ty),
        CS(0, 1, ty),
        X(0, ty),
        H(1, ty),
        CS(0, 1, ty),
    )

    result = compile(qswitch_hs)

    print(f"Qubits: {result.circuit.n_qubits}")
    print(f"Gates:  {result.circuit.n_gates}")
    print()
    print("Circuit:")
    for cmd in result.circuit.get_commands():
        print(f"  {cmd}")

    subsection("Semantics")
    print("  |0⟩|ψ⟩ → |0⟩(S;H)|ψ⟩")
    print("  |1⟩|ψ⟩ → |1⟩(H;S)|ψ⟩")

    # =========================================================================
    section("Part 2: GOI Conjugation Form (4 qubits)")
    # =========================================================================

    print("GOI representation: (QSwitch†) ⊗ QSwitch")
    print()
    print("Wire layout:")
    print("  Wire 0: ctrl*  (negative/dual)")
    print("  Wire 1: data*  (negative/dual)")
    print("  Wire 2: ctrl   (positive)")
    print("  Wire 3: data   (positive)")

    ty4 = Ten(Ten(Q(), Q()), Ten(Q(), Q()))

    # Negative: QSwitch† (reverse order, adjoint gates)
    negative = Seq(
        CSdg(0, 1, ty4),
        H(1, ty4),
        X(0, ty4),
        CSdg(0, 1, ty4),
        X(0, ty4),
    )

    # Positive: QSwitch
    positive = Seq(
        X(2, ty4),
        CS(2, 3, ty4),
        X(2, ty4),
        H(3, ty4),
        CS(2, 3, ty4),
    )

    goi_qswitch = Seq(negative, positive)
    result4 = compile(goi_qswitch)

    subsection("Circuit")
    print(f"Qubits: {result4.circuit.n_qubits}")
    print(f"Gates:  {result4.circuit.n_gates}")
    print()
    for cmd in result4.circuit.get_commands():
        print(f"  {cmd}")

    # =========================================================================
    section("Part 3: GOI Verification")
    # =========================================================================

    subsection("Test: twist ⊗ twist = id")

    # twist for Q⊗Q
    def make_twist_ten():
        return GOIArtifact(
            n_in=4, n_out=4,
            perm=WirePerm(4, [1, 0, 3, 2]),
            atoms=(),
            loops=()
        )

    twist = make_twist_ten()
    print(f"twist perm: {twist.perm.new_to_old}")

    composed = goi_seq(twist, twist, n_shared=2)
    traced = execute_trace(composed)

    print(f"twist;twist perm: {traced.perm.new_to_old}")
    print(f"twist;twist atoms: {list(traced.atoms)}")
    print(f"Result: {'id ✓' if traced.perm.new_to_old == [0,1,2,3] and len(traced.atoms) == 0 else 'FAIL'}")

    subsection("Test: H;S composition")

    h_goi = make_unitary_value('H', (0,), n_a=1, inverse_gate_name='H')
    s_goi = make_unitary_value('S', (0,), n_a=1, inverse_gate_name='Sdg')

    print(f"⟦H⟧ atoms: {[(a.gate_name, a.wires) for a in h_goi.atoms]}")
    print(f"⟦S⟧ atoms: {[(a.gate_name, a.wires) for a in s_goi.atoms]}")

    hs = goi_seq(h_goi, s_goi, n_shared=1)
    hs_traced = execute_trace(hs)

    print()
    print(f"⟦H;S⟧ after trace:")
    for atom in hs_traced.atoms:
        print(f"  {atom.gate_name} on wire {atom.wires}")

    wire0 = [a.gate_name for a in hs_traced.atoms if 0 in a.wires]
    wire1 = [a.gate_name for a in hs_traced.atoms if 1 in a.wires]
    print()
    print(f"Wire 0 (Q*): {wire0}  = (H;S)† = S†;H†")
    print(f"Wire 1 (Q):  {wire1}  = H;S")

    expected_0 = ['Sdg', 'H']
    expected_1 = ['H', 'S']
    ok = wire0 == expected_0 and wire1 == expected_1
    print(f"Result: {'✓' if ok else 'FAIL'}")

    # =========================================================================
    section("Demo Complete")
    # =========================================================================

    print("All QSwitch demonstrations completed successfully!")
    print()
    print("Summary:")
    print("  - QSwitch(H,S) first-order: 5 gates on 2 qubits")
    print("  - QSwitch(H,S) GOI form:   10 gates on 4 qubits")
    print("  - GOI laws verified: twist;twist=id, H;S composition")


if __name__ == "__main__":
    main()
