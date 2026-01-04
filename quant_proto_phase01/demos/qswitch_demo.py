#!/usr/bin/env python3
"""
QSwitch Demo - Runnable Script

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
    section("QSwitch Demo")

    # =========================================================================
    section("Part 1: QSwitch Definition")
    # =========================================================================

    print("""
QSwitch : (Q→Q) → (Q→Q) → (QBool ⊗ Q → QBool ⊗ Q)

QSwitch(f, g)(ctrl, data) =
  case ctrl of
  | Zero => (ctrl, g;f data)   -- apply g then f
  | One  => (ctrl, f;g data)   -- apply f then g
""")

    # =========================================================================
    section("Part 2: Abstract QSwitch(f, g) Circuit")
    # =========================================================================

    print("""The quantum case elaborates to controlled gates:

  anti-controlled-g ; f ; controlled-g

Expanded circuit structure:

  X q[0];        -- flip ctrl for anti-control
  C-g q[0],q[1]; -- g if ctrl was 0 (now 1)
  X q[0];        -- restore ctrl
  f q[1];        -- f unconditionally
  C-g q[0],q[1]; -- g if ctrl is 1

Wire 0: ctrl (control qubit)
Wire 1: data (target qubit)
""")

    subsection("Verification")
    print("""ctrl=0: X flips to 1, C-g fires, X flips back, f applied, C-g doesn't fire
        → data sees: g ; f ✓

ctrl=1: X flips to 0, C-g doesn't fire, X flips back, f applied, C-g fires
        → data sees: f ; g ✓
""")

    # =========================================================================
    section("Part 3: QSwitch(H, S) Instantiation")
    # =========================================================================

    print("""Substituting f=H, g=S:

QSwitch(H, S)(ctrl, data) =
  | Zero => (ctrl, S;H data)
  | One  => (ctrl, H;S data)

Circuit: X; CS; X; H; CS
""")

    # =========================================================================
    section("Part 4: QSwitch(H, S) Circuit (2 qubits)")
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
    section("Part 5: QSwitch(H, S) GOI Form (4 qubits)")
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
    section("Summary")
    # =========================================================================

    print("""
| Form                    | Qubits | Gates | Description           |
|-------------------------|--------|-------|-----------------------|
| QSwitch(f,g) abstract   | 2      | 5     | X; C-g; X; f; C-g     |
| QSwitch(H,S) first-order| 2      | 5     | X; CS; X; H; CS       |
| QSwitch(H,S) GOI        | 4      | 10    | Doubled conjugation   |
""")


if __name__ == "__main__":
    main()
