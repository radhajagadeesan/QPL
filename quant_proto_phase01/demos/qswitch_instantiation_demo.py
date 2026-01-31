#!/usr/bin/env python3
"""QSwitch Instantiation Demo

Shows QSwitch instantiated with concrete functions:
1. ONE function (f = g) - with simplification analysis
2. TWO functions (f ≠ g) - with explanation of why no simplification

Prerequisites: See qswitch_abstract_circuit_demo.py for the abstract structure.

Usage:
    python qswitch_instantiation_demo.py              # Run demo
    python qswitch_instantiation_demo.py --circuits   # Show circuit diagrams
"""

import sys
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from lang.types import Q, Unit, Ten, Plus, Arrow, width
from lang.terms import Id, Seq, Case, DistL, H, S
from typing_.check import type_of

from demo_utils import DemoRunner

# Global runner instance
runner = None


def main():
    global runner
    runner = DemoRunner(
        "QSwitch Instantiation Demo",
        "QSwitch with concrete functions (H,H) vs (H,S)"
    )
    runner.print_header()

    # Type definitions used throughout
    I = Unit()
    Bool = Plus(I, I)
    IQ = Ten(I, Q())

    print("""
This demo shows QSwitch instantiated with concrete functions.
For the abstract QSwitch structure, see: qswitch_abstract_circuit_demo.py

Recall the abstract QSwitch semantics:
    |0⟩|ψ⟩  →  |0⟩ f(g(ψ))     (apply g then f)
    |1⟩|ψ⟩  →  |1⟩ g(f(ψ))     (apply f then g)
""")

    # =========================================================================
    # SECTION 1: ONE FUNCTION (f = g)
    # =========================================================================
    print("\n" + "="*74)
    print("  SECTION 1: QSwitch with ONE Function (f = g)")
    print("="*74 + "\n")

    print("""
SIMPLIFICATION ANALYSIS (before compiling)
──────────────────────────────────────────

When f = g (same function applied to both slots), the QSwitch semantics
become:

    |0⟩|ψ⟩  →  |0⟩ f(f(ψ))     (apply f then f)
    |1⟩|ψ⟩  →  |1⟩ f(f(ψ))     (apply f then f)
                  ─────────
                  IDENTICAL!

OBSERVATION: Both branches compute the SAME thing: f ∘ f

CONSEQUENCE: The control qubit has NO EFFECT on the output!
             The QSwitch degenerates to unconditional f ∘ f.


ALGEBRAIC SIMPLIFICATION:
─────────────────────────

    QSwitch[f, f] ≡ Id_ctrl ⊗ (f ∘ f)

    The control qubit passes through unchanged.
    The target gets f applied twice, regardless of control.


SPECIAL CASE: f = H (Hadamard)
──────────────────────────────

    H ∘ H = H² = I    (Hadamard is self-inverse)

    Therefore:
        QSwitch[H, H] ≡ Id_ctrl ⊗ I = Id

    The ENTIRE circuit simplifies to IDENTITY!
""")

    print("""
CIRCUIT (QSwitch[H, H])
───────────────────────
""")

    # Build QSwitch[H, H]
    left_branch_hh = Seq(H(0, IQ), H(0, IQ))   # H;H when ctrl=|0⟩
    right_branch_hh = Seq(H(0, IQ), H(0, IQ))  # H;H when ctrl=|1⟩

    case_hh = Case(IQ, IQ, left_branch_hh, right_branch_hh)
    dist = DistL(I, I, Q())  # Bool ⊗ Q → (I⊗Q) + (I⊗Q)
    qswitch_hh = Seq(dist, case_hh)

    # Verify types
    dom, cod = type_of(qswitch_hh)
    print(f"Type: {dom} → {cod}")
    print(f"      (width {width(dom)} → width {width(cod)})")

    result_hh = runner.compile(qswitch_hh, "QSwitch[H, H]", materialize=True)
    runner.print_circuit_details(result_hh, "Compiled Circuit")
    runner.show_circuit(result_hh, "QSwitch[H, H]")

    print("""
CIRCUIT DIAGRAM:
────────────────

    ctrl ──X───●───●───X───●───●──
           │   │   │   │   │   │
    tgt  ─────CH──CH─────CH──CH───


VERIFICATION:
─────────────
""")

    # Verify it's identity
    u_hh = result_hh.circuit.get_unitary()
    is_identity = np.allclose(u_hh, np.eye(4), atol=1e-10)
    print(f"    Unitary equals identity matrix? {is_identity}")

    if is_identity:
        print("""
    CONFIRMED: QSwitch[H, H] = Identity

    The 6 gates completely cancel:
      - X;X = I (the two X gates cancel)
      - CH;CH = I (controlled-H squared is identity)
      - CH;CH = I (second pair also cancels)
""")

    # =========================================================================
    # SECTION 2: TWO FUNCTIONS (f ≠ g)
    # =========================================================================
    print("\n" + "="*74)
    print("  SECTION 2: QSwitch with TWO Functions (f ≠ g)")
    print("="*74 + "\n")

    print("""
SIMPLIFICATION ANALYSIS (before compiling)
──────────────────────────────────────────

When f ≠ g (different functions), the QSwitch semantics are:

    |0⟩|ψ⟩  →  |0⟩ f(g(ψ))     (apply g then f)
    |1⟩|ψ⟩  →  |1⟩ g(f(ψ))     (apply f then g)
                  ─────────
                  DIFFERENT!

QUESTION: Can we simplify?

ANSWER: Only if f and g COMMUTE, i.e., f ∘ g = g ∘ f


EXAMPLE: f = H, g = S
─────────────────────

    H ∘ S  =  HS  (Hadamard then S-gate)
    S ∘ H  =  SH  (S-gate then Hadamard)

    Do they commute?

    H = 1/√2 [1   1]      S = [1  0]
             [1  -1]          [0  i]

    HS = 1/√2 [1   i]     SH = 1/√2 [1   1]
              [1  -i]               [i  -i]

    HS ≠ SH   →   H and S do NOT commute!


CONSEQUENCE: NO SIMPLIFICATION POSSIBLE
───────────────────────────────────────

    Since H ∘ S ≠ S ∘ H, the two branches produce genuinely
    different results. The control qubit MATTERS.

    Both branches must be compiled with controlled gates.
    This is the TRUE quantum switch with indefinite causal order.
""")

    print("""
CIRCUIT (QSwitch[H, S])
───────────────────────
""")

    # Build QSwitch[H, S]
    # Abstract semantics: Left => f(g(x)), Right => g(f(x))
    # With f=H, g=S: Left => H(S(x)) = S;H, Right => S(H(x)) = H;S
    left_branch_hs = Seq(S(0, IQ), H(0, IQ))   # S;H when ctrl=|0⟩ → H(S(x)) = f(g(x))
    right_branch_hs = Seq(H(0, IQ), S(0, IQ))  # H;S when ctrl=|1⟩ → S(H(x)) = g(f(x))

    case_hs = Case(IQ, IQ, left_branch_hs, right_branch_hs)
    qswitch_hs = Seq(dist, case_hs)

    # Verify types
    dom, cod = type_of(qswitch_hs)
    print(f"Type: {dom} → {cod}")
    print(f"      (width {width(dom)} → width {width(cod)})")

    result_hs = runner.compile(qswitch_hs, "QSwitch[H, S]", materialize=True)
    runner.print_circuit_details(result_hs, "Compiled Circuit")
    runner.show_circuit(result_hs, "QSwitch[H, S]")

    print("""
CIRCUIT DIAGRAM:
────────────────

    ctrl ──X───●───●───X───●───●──
           │   │   │   │   │   │
    tgt  ─────CS──CH─────CH──CS───

    Where:
      X       = Pauli-X (bit flip) for anti-control
      CH      = Controlled-Hadamard
      CS      = Controlled-S (phase gate)


EXECUTION TRACE:
────────────────

    Input |0⟩|ψ⟩ (Left branch → f(g(x)) = H(S(x))):
      X         →  |1⟩|ψ⟩
      CS        →  |1⟩ S|ψ⟩      (fires, ctrl=1)
      CH        →  |1⟩ HS|ψ⟩     (fires, ctrl=1)
      X         →  |0⟩ HS|ψ⟩
      CH        →  |0⟩ HS|ψ⟩     (skips, ctrl=0)
      CS        →  |0⟩ HS|ψ⟩     (skips, ctrl=0)
      Output: |0⟩ H(S|ψ⟩)   (applied S then H = f∘g)

    Input |1⟩|ψ⟩ (Right branch → g(f(x)) = S(H(x))):
      X         →  |0⟩|ψ⟩
      CS        →  |0⟩|ψ⟩        (skips, ctrl=0)
      CH        →  |0⟩|ψ⟩        (skips, ctrl=0)
      X         →  |1⟩|ψ⟩
      CH        →  |1⟩ H|ψ⟩      (fires, ctrl=1)
      CS        →  |1⟩ SH|ψ⟩     (fires, ctrl=1)
      Output: |1⟩ S(H|ψ⟩)   (applied H then S = g∘f)

    Input |+⟩|ψ⟩ = (|0⟩ + |1⟩)/√2 |ψ⟩:
      BOTH branches execute coherently!
      Output: (|0⟩ H(S|ψ⟩) + |1⟩ S(H|ψ⟩)) / √2
      This is INDEFINITE CAUSAL ORDER!
""")

    # =========================================================================
    # SUMMARY
    # =========================================================================
    print("\n" + "="*74)
    print("  SUMMARY")
    print("="*74 + "\n")

    print("""
QSWITCH INSTANTIATION COMPARISON
────────────────────────────────

  QSwitch[f, f]  (ONE function, f = g):
  ─────────────────────────────────────
    Simplification: Both branches identical → f ∘ f
    Control qubit: IRRELEVANT (passes through)
    Example: QSwitch[H, H] = Identity (H² = I)
    Gates: 6 (but all cancel to identity)

  QSwitch[f, g]  (TWO functions, f ≠ g, non-commuting):
  ─────────────────────────────────────────────────────
    Simplification: NONE (f∘g ≠ g∘f)
    Control qubit: ESSENTIAL (determines operation order)
    Example: QSwitch[H, S] → genuine quantum switch
    Gates: 6 (X; CS; CH; X; CH; CS)

  KEY INSIGHT:
    QSwitch is only non-trivial when f and g DON'T commute.
    Commutativity [f,g] = 0  →  QSwitch[f,g] = f∘g (no switch)
    Non-commutativity        →  true indefinite causal order
""")

    runner.print_footer()


if __name__ == "__main__":
    main()
