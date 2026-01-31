#!/usr/bin/env python3
"""QSwitch as a Term using Case

This demo builds QSwitch as an actual term using Case (copairing),
not just raw controlled gates.

    QSwitch : Bool ⊗ Q → Bool ⊗ Q

    QSwitch (ctrl, tgt) = case ctrl of
        | Left  → (ctrl, (H;S)(tgt))
        | Right → (ctrl, (S;H)(tgt))

Usage:
    python qswitch_term_demo.py              # Run demo
    python qswitch_term_demo.py --circuits   # Show circuit diagrams
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from lang.types import Q, Unit, Ten, Plus, width
from lang.terms import Id, Seq, TenTerm, Case, H, S, DistR, Lam
from typing_.check import type_of

from demo_utils import DemoRunner

# Global runner instance
runner = None


def main():
    global runner
    runner = DemoRunner(
        "QSwitch as a Term using Case",
        "Builds QSwitch using Case combinator"
    )
    runner.print_header()

    # Type definitions
    I = Unit()
    Bool = Plus(I, I)        # I + I (control qubit)
    IQ = Ten(I, Q())         # I ⊗ Q (payload after distribution)
    BoolQ = Ten(Bool, Q())   # Bool ⊗ Q = (I+I) ⊗ Q

    print(f"""
TYPE DEFINITIONS:

    Bool  = I + I           width = {width(Bool)}
    I ⊗ Q                   width = {width(IQ)}
    Bool ⊗ Q = (I+I) ⊗ Q    width = {width(BoolQ)}
""")

    print("\n" + "="*70)
    print("  1. The Distribution Step")
    print("="*70 + "\n")

    print("""
To use Case on Bool ⊗ Q, we first distribute:

    (I + I) ⊗ Q  ──DistR──→  (I ⊗ Q) + (I ⊗ Q)

This transforms the tensor-of-sum into a sum-of-tensors,
allowing Case to branch on the tag while keeping the Q payload.
""")

    dist = DistR(I, I, Q())
    dom, cod = type_of(dist)
    print(f"DistR(I, I, Q) : {dom} → {cod}")

    print("\n" + "="*70)
    print("  2. The Case Branches")
    print("="*70 + "\n")

    print("""
Each branch operates on I ⊗ Q (which has width 1, just the Q).
Since I has width 0, the payload is effectively just Q.

    Left branch:  I ⊗ Q → I ⊗ Q   applies H ; S
    Right branch: I ⊗ Q → I ⊗ Q   applies S ; H
""")

    # Build branches
    left_branch = Seq(H(0, IQ), S(0, IQ))   # H;S when ctrl=|0⟩
    right_branch = Seq(S(0, IQ), H(0, IQ))  # S;H when ctrl=|1⟩

    print(f"Left branch (H;S):  {type_of(left_branch)}")
    print(f"Right branch (S;H): {type_of(right_branch)}")

    print("\n" + "="*70)
    print("  3. The Case Term")
    print("="*70 + "\n")

    print("""
Case combines the branches into a copairing:

    Case(I⊗Q, I⊗Q, left, right) : (I⊗Q) + (I⊗Q) → (I⊗Q) + (I⊗Q)

When compiled, this becomes controlled gates:
    - Left branch: anti-controlled (fires when tag=0)
    - Right branch: controlled (fires when tag=1)
""")

    case_term = Case(IQ, IQ, left_branch, right_branch)
    print(f"Case term type: {type_of(case_term)}")

    print("\n" + "="*70)
    print("  4. Full QSwitch = DistR ; Case")
    print("="*70 + "\n")

    qswitch = Seq(dist, case_term)
    dom, cod = type_of(qswitch)

    print(f"""
QSwitch[H,S] = DistR ; Case[H;S, S;H]

Type: {dom} → {cod}
    ≅ Bool ⊗ Q → Bool ⊗ Q
""")

    print("\n" + "="*70)
    print("  5. Compilation")
    print("="*70 + "\n")

    result = runner.compile(qswitch, "QSwitch[H,S]")
    runner.print_circuit_details(result, "Compiled Circuit")
    runner.show_circuit(result, "QSwitch[H,S]")

    print("\n" + "="*70)
    print("  6. Circuit Diagram")
    print("="*70 + "\n")

    print("""
  ctrl ──X───●───●───X───●───●──
             │   │       │   │
  tgt  ─────CH──CS──────CS──CH──

Gate sequence:
  X q[0]        ← flip ctrl for anti-control
  CH q[0],q[1]  ← controlled H (left branch, part 1)
  CS q[0],q[1]  ← controlled S (left branch, part 2)
  X q[0]        ← restore ctrl
  CS q[0],q[1]  ← controlled S (right branch, part 1)
  CH q[0],q[1]  ← controlled H (right branch, part 2)
""")

    print("\n" + "="*70)
    print("  7. Execution Semantics")
    print("="*70 + "\n")

    print("""
When ctrl = |0⟩:
  - X flips to |1⟩ → CH;CS fire → X flips back to |0⟩
  - Target receives: H ; S

When ctrl = |1⟩:
  - X flips to |0⟩ → CH;CS skip → X flips back to |1⟩
  - CS;CH fire
  - Target receives: S ; H

When ctrl = |+⟩ = (|0⟩ + |1⟩)/√2:
  - BOTH branches execute coherently!
  - |0⟩|ψ⟩ → |0⟩(HS)|ψ⟩
  - |1⟩|ψ⟩ → |1⟩(SH)|ψ⟩
  - Result: (|0⟩(HS)|ψ⟩ + |1⟩(SH)|ψ⟩)/√2
""")

    print("\n" + "="*70)
    print("  8. Wrapping in Lambda")
    print("="*70 + "\n")

    # Wrap in lambda for a complete term
    output_ty = Plus(IQ, IQ)
    lam_qswitch = Lam("x", BoolQ, output_ty, qswitch)

    dom, cod = type_of(lam_qswitch)
    print(f"""
λx:(Bool⊗Q). DistR ; Case[H;S, S;H]

Type: {dom} → {cod}

This is a proper closed term representing QSwitch[H,S].
""")

    result2 = runner.compile(lam_qswitch, "λ-wrapped QSwitch")
    print(f"Compiled λ-term: {result2.circuit.n_gates} gates")

    print("\n" + "="*70)
    print("  Summary")
    print("="*70 + "\n")

    print("""
QSWITCH AS A TERM
─────────────────

  TERM:
    QSwitch[H,S] = DistR(I,I,Q) ; Case(I⊗Q, I⊗Q, H;S, S;H)

  TYPE:
    Bool ⊗ Q → (I⊗Q) + (I⊗Q) ≅ Bool ⊗ Q → Bool ⊗ Q

  COMPILATION:
    DistR → pure permutation (0 gates)
    Case  → controlled gates (6 gates total)

  CIRCUIT:
    X[0]; CH[0,1]; CS[0,1]; X[0]; CS[0,1]; CH[0,1]

  KEY INSIGHT:
    Case on a superposition → controlled gates
    Both branches execute coherently on |+⟩ control!
""")

    runner.print_footer()


if __name__ == "__main__":
    main()
