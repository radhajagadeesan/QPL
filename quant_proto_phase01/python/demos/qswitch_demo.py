#!/usr/bin/env python3
"""
QSwitch Demo - End-to-End from Source to Gates

Usage:
    python qswitch_demo.py              # Run demo
    python qswitch_demo.py --circuits   # Show circuit diagrams

This demo shows the quantum switch circuit structure.
For the full elaboration pipeline (source AST → Core IR → circuit),
see the OCaml demo: ocaml/demos/qswitch_demo.ml
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from lang.terms import H, S, Seq, CH, CS, X
from lang.types import Q, Ten

from demo_utils import DemoRunner

# Global runner instance
runner = None


def main():
    global runner
    runner = DemoRunner(
        "QSwitch: Source to Gates",
        "Demonstrates quantum switch circuit compilation"
    )
    runner.print_header()

    # =========================================================================
    print("\n" + "="*70)
    print("  Part 1: Source Definition")
    print("="*70 + "\n")
    # =========================================================================

    print("""
QSwitch : (Q→Q) → (Q→Q) → (QBool ⊗ Q → QBool ⊗ Q)

In surface syntax (OCaml):

  def QSwitch_HS : (I + I) ⊗ Q → (I + I) ⊗ Q =
    λx. let (ctrl ⊗ tgt) : (I + I) ⊗ Q = x in
      case ctrl of
        | Left(u)  => S[1] ; H[1]    (* when ctrl=0: S then H *)
        | Right(u) => H[1] ; S[1]    (* when ctrl=1: H then S *)

Type layout:
  Wire 0: tag qubit (control) — encodes Left (0) vs Right (1)
  Wire 1: payload qubit — where gates are applied
""")

    # =========================================================================
    print("\n" + "="*70)
    print("  Part 2: Elaboration (OCaml → Core IR)")
    print("="*70 + "\n")
    # =========================================================================

    print("""
The OCaml elaborator transforms case expressions into controlled gates:

  case ctrl of Left => body_L | Right => body_R
  ─────────────────────────────────────────────
  Anti-controlled(body_L) ; Controlled(body_R)

For QSwitch(H, S):

  case ctrl of Left => S;H | Right => H;S
  ─────────────────────────────────────────
  X[0]; CS[0,1]; CH[0,1]; X[0]; CH[0,1]; CS[0,1]
       ───────────────────     ─────────────────
       anti-ctrl (S;H)         ctrl (H;S)

Anti-control pattern: X[tag] ; Controlled ; X[tag]
  - Flips tag so |0⟩ becomes |1⟩
  - Controlled gates fire on |1⟩
  - Flips tag back

Run `dune exec demos/abstract_qswitch_oterm_e2e.exe` in ocaml/ for full E2E pipeline.
""")

    # =========================================================================
    print("\n" + "="*70)
    print("  Part 3: Compiled Circuit")
    print("="*70 + "\n")
    # =========================================================================

    ty = Ten(Q(), Q())

    qswitch_hs = Seq(
        X(0, ty),        # flip tag for anti-control
        CS(0, 1, ty),    # controlled-S (left branch, part 1)
        CH(0, 1, ty),    # controlled-H (left branch, part 2)
        X(0, ty),        # restore tag
        CH(0, 1, ty),    # controlled-H (right branch, part 1)
        CS(0, 1, ty),    # controlled-S (right branch, part 2)
    )

    result = runner.compile(qswitch_hs, "QSwitch(H, S)")
    runner.print_circuit_details(result, "Compiled Circuit")
    runner.show_circuit(result, "QSwitch(H, S)")

    print("""
Diagram:

  q[0] ──X───●───●───X───●───●──
            │   │       │   │
  q[1] ─────CS──CH──────CH──CS──
""")

    # =========================================================================
    print("\n" + "="*70)
    print("  Part 4: Semantics")
    print("="*70 + "\n")
    # =========================================================================

    print("""
Execution trace:

  When ctrl = |0⟩ (Left):
    X[0] flips to |1⟩ → CS and CH fire → X[0] flips back to |0⟩
    Target gets: S then H
    (Right branch gates don't fire because ctrl is |0⟩)

  When ctrl = |1⟩ (Right):
    X[0] flips to |0⟩ → CS and CH don't fire → X[0] flips back to |1⟩
    Then: CH and CS fire
    Target gets: H then S

  When ctrl = superposition:
    Both branches execute coherently
    |α|0⟩ + β|1⟩⟩|ψ⟩ → α|0⟩(S;H)|ψ⟩ + β|1⟩(H;S)|ψ⟩

The quantum switch applies operations in BOTH orders simultaneously!
""")

    # =========================================================================
    print("\n" + "="*70)
    print("  Summary")
    print("="*70 + "\n")
    # =========================================================================

    print("""
COMPILATION PIPELINE
────────────────────

  SOURCE        λx. let (ctrl ⊗ tgt) = x in
  (AST)           case ctrl of Left => S;H | Right => H;S

      ↓         elaborate() — β-reduce, substitute, case transform

  CORE IR       X[0]; C0-S[1]; C0-H[1]; X[0]; C0-H[1]; C0-S[1]

      ↓         compile() — emit gates, track permutation

  CIRCUIT       X q[0]; CS q[0],q[1]; CH q[0],q[1]; ...
  (pytket)      6 gates, 2 qubits, identity permutation

Key insight: case on superposition → controlled gates
""")

    runner.print_footer()


if __name__ == "__main__":
    main()
