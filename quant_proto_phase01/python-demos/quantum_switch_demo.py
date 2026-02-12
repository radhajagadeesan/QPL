#!/usr/bin/env python3
"""
Quantum Switch Demo: Surface → Elaboration → Circuit

Demonstrates the Granthi compiler pipeline on QSwitch, a higher-order
quantum program that coherently superimposes causal orders.

Usage:
    python quantum_switch_demo.py              # Run demo
    python quantum_switch_demo.py --circuits   # Show circuit diagrams
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from lang.types import Unit, Q, Ten, Plus, width
from lang.terms import (
    Id, Seq, TenTerm,
    TwistPlus, TwistTen,
    H, S, X,
    CH, CS,  # Controlled gates
)

from demo_utils import DemoRunner

# Global runner instance
runner = None


def main():
    global runner
    runner = DemoRunner(
        "Quantum Switch: Surface → Circuit",
        "Full compilation pipeline demonstration"
    )
    runner.print_header()

    # =========================================================================
    # PART 1: Source Program
    # =========================================================================
    print("\n" + "="*74)
    print("  PART 1: Source Program")
    print("="*74 + "\n")

    print("""
The quantum switch takes a control qubit and two operations f, g.
It applies them in different orders depending on the control:

  - Control = |0⟩: apply g then f
  - Control = |1⟩: apply f then g
  - Control = superposition: coherent mixture of both orders!

SOURCE SYNTAX (Linear Lambda Calculus):

  (* Type: control qubit + target qubit *)
  QSwitch : (I + I) ⊗ Q  →  (I + I) ⊗ Q

  def QSwitch(f, g) =
    λx. let (ctrl ⊗ tgt) : (I + I) ⊗ Q = x in
      case ctrl of
        | Left(u)  => Left(u)  ⊗ (g ; f) tgt   (* order: g then f *)
        | Right(u) => Right(u) ⊗ (f ; g) tgt   (* order: f then g *)

  (* Instantiated with H and S *)
  def QSwitch_HS = QSwitch(H, S)

TYPE LAYOUT:

  Input/Output: (I + I) ⊗ Q

  Wire 0: tag qubit 1 (one-hot: Left)
  Wire 1: tag qubit 2 (one-hot: Right)
  Wire 2: target qubit — where H and S are applied

  width((I + I) ⊗ Q) = 2 (tags) + 1 (Q) = 3 wires
""")

    # =========================================================================
    # PART 2: Elaboration (Source → Core IR)
    # =========================================================================
    print("\n" + "="*74)
    print("  PART 2: Elaboration (Source → Core IR)")
    print("="*74 + "\n")

    print("""
STEP 2.1: Lambda/Let Elimination

  Lambdas and lets are MACROS — they elaborate away via substitution.
  After elaboration, only compositional structure remains.

STEP 2.2: Case on Quantum Superposition

  The key transformation! When the scrutinee (ctrl) can be in superposition,
  case elaborates to CONTROLLED GATES:

    case ctrl of
      | Left(u)  => body_L        Elaborates    Anti-controlled body_L
      | Right(u) => body_R        ─────────►    Controlled body_R

  For QSwitch_HS:
    - Left branch:  g;f = S;H  (anti-controlled, i.e., control=0)
    - Right branch: f;g = H;S  (controlled, i.e., control=1)

STEP 2.3: Controlled Gate Decomposition

  The decomposition uses the identity:

    "If control=0 do L, if control=1 do R"
    = X[ctrl] ; C-L ; X[ctrl] ; C-R

  where C-L means "controlled-L" and X[ctrl] flips the control.

ELABORATED CORE IR:

  X[0] ; C0-S[1] ; C0-H[1] ; X[0] ; C0-H[1] ; C0-S[1]
  ────   ───────────────   ────   ───────────────────
   │           │            │              │
   │     anti-controlled    │       controlled
   │       (S ; H)          │        (H ; S)
   flip control        flip back
""")

    # =========================================================================
    # PART 3: Coherent Control (Interface Structure)
    # =========================================================================
    print("\n" + "="*74)
    print("  PART 3: Coherent Control (Interface Structure)")
    print("="*74 + "\n")

    print("""
CONCEPTUAL BACKGROUND: Compact-Closed Categories

  In linear type theory, all types are self-dual: A* = A.
  A function f : A → B is physically a wire bundle of width(A) + width(B).

  For quantum types:
  - Q* = Q (self-dual)
  - f : Q → Q is physically 2 wires

WHY THIS MATTERS FOR QSWITCH:

  QSwitch doesn't just apply H and S — it applies them in SUPERPOSED ORDER.

  The key insight:

  1. H : Q → Q acts on the target qubit
  2. S : Q → Q acts on the target qubit
  3. Sequential composition f;g chains the operations
  4. The control qubit SELECTS which composition to use!

INTERFACE STRUCTURE:

  Input:    Wire 0: ctrl (tag)   Wire 1: target
                    ↓                    ↓
            QSwitch circuit (controlled)
                    ↓                    ↓
  Output:   Wire 0: ctrl (tag)   Wire 1: target

  The control qubit is PRESERVED (not measured).
  This enables coherent superposition of causal orders.
""")

    # =========================================================================
    # PART 4: Final Circuit
    # =========================================================================
    print("\n" + "="*74)
    print("  PART 4: Final Circuit")
    print("="*74 + "\n")

    # Type definitions
    Bit = Plus(Unit(), Unit())  # I + I
    BitQ = Ten(Bit, Q())        # (I + I) ⊗ Q

    print("Wire layout: (I + I) ⊗ Q")
    print(f"  Wire 0: tag qubit 1 (one-hot Left)")
    print(f"  Wire 1: tag qubit 2 (one-hot Right)")
    print(f"  Wire 2: target qubit")
    print(f"  Total width: {width(BitQ)}")

    print("\n--- Individual operations ---\n")

    # X on control
    print("X[0] — flip control (converts |0⟩-control to |1⟩-control)")
    x_ctrl = TenTerm(TwistPlus(Unit(), Unit()), Id(Q()))
    result = runner.compile(x_ctrl, "X[0] (TwistPlus)")
    runner.show_circuit(result, "X[0]")

    # Controlled-H
    print("\nC0-H[1] — controlled-H (H on target iff control=1)")
    ch = CH(0, 1, BitQ)
    result = runner.compile(ch, "CH[0,1]")
    runner.show_circuit(result, "CH[0,1]")

    # Controlled-S
    print("\nC0-S[1] — controlled-S (S on target iff control=1)")
    cs = CS(0, 1, BitQ)
    result = runner.compile(cs, "CS[0,1]")
    runner.show_circuit(result, "CS[0,1]")

    print("\n--- Complete QSwitch(H, S) circuit ---\n")

    # Full circuit: X[0] ; CS[0,1] ; CH[0,1] ; X[0] ; CH[0,1] ; CS[0,1]
    qswitch = Seq(
        TenTerm(TwistPlus(Unit(), Unit()), Id(Q())),  # X[0]
        CS(0, 1, BitQ),                                # C-S[0,1]
        CH(0, 1, BitQ),                                # C-H[0,1]
        TenTerm(TwistPlus(Unit(), Unit()), Id(Q())),  # X[0]
        CH(0, 1, BitQ),                                # C-H[0,1]
        CS(0, 1, BitQ),                                # C-S[0,1]
    )

    result = runner.compile(qswitch, "QSwitch(H, S)")
    runner.print_circuit_details(result, "QSwitch(H, S)")
    runner.show_circuit(result, "QSwitch(H, S)")

    print("""
CIRCUIT EXPLANATION:

  X[0] ; CS[0,1] ; CH[0,1] ; X[0] ; CH[0,1] ; CS[0,1]
  ────   ────────────────   ────   ────────────────────
   │            │            │              │
   │     Anti-controlled     │       Controlled
   │        S ; H            │         H ; S
   │     (when ctrl=0)       │      (when ctrl=1)
   flip      body         restore      body

  When control = |0⟩:
    X makes it |1⟩, CS and CH fire, X restores to |0⟩
    → Target gets S then H

  When control = |1⟩:
    X makes it |0⟩, CS and CH skip, X restores to |1⟩, then CS and CH fire
    → Target gets H then S

  When control = superposition:
    Both paths execute coherently!
    → Target is in superposition of (S;H)|ψ⟩ and (H;S)|ψ⟩
""")

    # =========================================================================
    # PART 5: Summary
    # =========================================================================
    print("\n" + "="*74)
    print("  SUMMARY: Compilation Pipeline")
    print("="*74 + "\n")

    print("""
  STAGE              REPRESENTATION
─────────────────────────────────────────────────────────────────────────

  1. SOURCE          λx. let (ctrl ⊗ tgt) = x in
     (Linear λ)        case ctrl of
                         | Left(u)  => Left(u) ⊗ (S;H) tgt
                         | Right(u) => Right(u) ⊗ (H;S) tgt

        ↓ elaboration (macro expansion + case → controlled)

  2. CORE IR         X[0] ; C0-S[1] ; C0-H[1] ; X[0] ; C0-H[1] ; C0-S[1]
     (Compositional)

        ↓ compile (emit gates, track permutation)

  3. CIRCUIT         pytket.Circuit with gates
     (Executable)    + identity permutation

KEY INSIGHT: Coherent Control

  The control qubit determines which order of operations applies:
  - H and S act on the target qubit (wire 1)
  - The control qubit (wire 0) SELECTS the composition order

  This is why quantum control over causal order works:
  the control is preserved through the circuit, enabling superposition.
""")

    runner.print_footer()


if __name__ == "__main__":
    main()
