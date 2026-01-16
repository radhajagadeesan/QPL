#!/usr/bin/env python3
"""
Quantum Switch Demo: Surface → Elaboration → Circuit

Demonstrates the Granthi compiler pipeline on QSwitch, a higher-order
quantum program that coherently superimposes causal orders.

Run: source ../venv/bin/activate && PYTHONPATH=src python demos/quantum_switch_demo.py
"""

from lang.types import Unit, Q, Ten, Plus, width
from lang.terms import (
    Id, Seq, TenTerm,
    TwistPlus, TwistTen,
    H, S, X,
    CH, CS,  # Controlled gates
)
from compile.to_pytket import compile


def banner(title: str) -> None:
    print("\n" + "=" * 74)
    print(f"  {title}")
    print("=" * 74)


def section(title: str) -> None:
    print(f"\n--- {title} ---\n")


def show_circuit(result, label: str = "") -> None:
    """Display circuit gates and final permutation."""
    cmds = result.circuit.get_commands()
    if label:
        print(f"{label}")
    print("  Gates: ", end="")
    if cmds:
        gate_strs = []
        for c in cmds:
            qubits = [q.index[0] for q in c.qubits]
            if len(qubits) == 1:
                gate_strs.append(f"{c.op.type.name}[{qubits[0]}]")
            else:
                gate_strs.append(f"{c.op.type.name}{qubits}")
        print(" ; ".join(gate_strs))
    else:
        print("(identity)")
    print(f"  Perm:  {list(result.perm.new_to_old)}")


def main():
    banner("QUANTUM SWITCH: From Surface Syntax to Circuit")

    # =========================================================================
    # PART 1: Source Program
    # =========================================================================
    banner("PART 1: Source Program")

    print("""
The quantum switch takes a control qubit and two operations f, g.
It applies them in different orders depending on the control:

  - Control = |0⟩: apply g then f
  - Control = |1⟩: apply f then g
  - Control = superposition: coherent mixture of both orders!

SOURCE SYNTAX (Linear Lambda Calculus):
┌─────────────────────────────────────────────────────────────────────┐
│                                                                     │
│  (* Type: control qubit + target qubit *)                           │
│  QSwitch : (I + I) ⊗ Q  →  (I + I) ⊗ Q                              │
│                                                                     │
│  def QSwitch(f, g) =                                                │
│    λx. let (ctrl ⊗ tgt) : (I + I) ⊗ Q = x in                        │
│      case ctrl of                                                   │
│        | Left(u)  => Left(u)  ⊗ (g ; f) tgt   (* order: g then f *) │
│        | Right(u) => Right(u) ⊗ (f ; g) tgt   (* order: f then g *) │
│                                                                     │
│  (* Instantiated with H and S *)                                    │
│  def QSwitch_HS = QSwitch(H, S)                                     │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘

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
    banner("PART 2: Elaboration (Source → Core IR)")

    print("""
STEP 2.1: Lambda/Let Elimination

  Lambdas and lets are MACROS — they elaborate away via substitution.
  After elaboration, only compositional structure remains.

STEP 2.2: Case on Quantum Superposition

  The key transformation! When the scrutinee (ctrl) can be in superposition,
  case elaborates to CONTROLLED GATES:

  ┌────────────────────────────────────────────────────────────────────┐
  │  case ctrl of                                                      │
  │    | Left(u)  => body_L        Elaborates    Anti-controlled body_L│
  │    | Right(u) => body_R        ─────────►    Controlled body_R     │
  └────────────────────────────────────────────────────────────────────┘

  For QSwitch_HS:
    - Left branch:  g;f = S;H  (anti-controlled, i.e., control=0)
    - Right branch: f;g = H;S  (controlled, i.e., control=1)

STEP 2.3: Controlled Gate Decomposition

  The decomposition uses the identity:

    "If control=0 do L, if control=1 do R"
    = X[ctrl] ; C-L ; X[ctrl] ; C-R

  where C-L means "controlled-L" and X[ctrl] flips the control.

ELABORATED CORE IR:
┌─────────────────────────────────────────────────────────────────────┐
│                                                                     │
│  X[0] ; C0-S[1] ; C0-H[1] ; X[0] ; C0-H[1] ; C0-S[1]                 │
│  ────   ───────────────   ────   ───────────────────                │
│   │           │            │              │                         │
│   │     anti-controlled    │       controlled                       │
│   │       (S ; H)          │        (H ; S)                         │
│   flip control        flip back                                     │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
""")

    # =========================================================================
    # PART 3: The Int Construction (Interface Duplication)
    # =========================================================================
    banner("PART 3: The Int Construction (Interface Duplication)")

    print("""
CONCEPTUAL BACKGROUND: Geometry of Interaction

  In standard λ-calculus, a function f : A → B is a "black box".
  In GOI/Int semantics, we OPEN the box:

  ┌──────────────────────────────────────────────────────────────────┐
  │                                                                  │
  │  f : A → B     becomes     f̂ : A† ⊗ B  →  A† ⊗ B                 │
  │                                                                  │
  │  (morphism)                (endomorphism on doubled boundary)    │
  │                                                                  │
  └──────────────────────────────────────────────────────────────────┘

  The † denotes the "input interface" (contravariantly).

  For quantum types: A† = A (self-dual).
  So f : Q → Q becomes f̂ : Q ⊗ Q → Q ⊗ Q.

WHY THIS MATTERS FOR QSWITCH:

  QSwitch doesn't just apply H and S — it applies them in SUPERPOSED ORDER.

  In the Int picture:

  1. H : Q → Q  becomes  Ĥ : Q ⊗ Q → Q ⊗ Q
     (H acts on the "output part", identity on "input part")

  2. S : Q → Q  becomes  Ŝ : Q ⊗ Q → Q ⊗ Q
     (S acts on the "output part", identity on "input part")

  3. Sequential composition f;g is matrix multiplication of endos

  4. The control qubit SELECTS which composition to use!

INTERFACE STRUCTURE:

  ┌─────────────────────────────────────────────────────────────────┐
  │                                                                 │
  │  Input:   ┌──────────────────────────────────────┐              │
  │           │ Wire 0: ctrl (tag)  │ Wire 1: target │              │
  │           └──────────────────────────────────────┘              │
  │                    ↓                    ↓                       │
  │           ┌──────────────────────────────────────┐              │
  │           │    QSwitch circuit (controlled)      │              │
  │           └──────────────────────────────────────┘              │
  │                    ↓                    ↓                       │
  │  Output:  ┌──────────────────────────────────────┐              │
  │           │ Wire 0: ctrl (tag)  │ Wire 1: target │              │
  │           └──────────────────────────────────────┘              │
  │                                                                 │
  │  The control qubit is PRESERVED (not measured).                 │
  │  This enables coherent superposition of causal orders.          │
  │                                                                 │
  └─────────────────────────────────────────────────────────────────┘
""")

    # =========================================================================
    # PART 4: Final Circuit
    # =========================================================================
    banner("PART 4: Final Circuit")

    section("Building the circuit step by step")

    # Type definitions
    Bit = Plus(Unit(), Unit())  # I + I
    BitQ = Ten(Bit, Q())        # (I + I) ⊗ Q

    print("Wire layout: (I + I) ⊗ Q")
    print(f"  Wire 0: tag qubit 1 (one-hot Left)")
    print(f"  Wire 1: tag qubit 2 (one-hot Right)")
    print(f"  Wire 2: target qubit")
    print(f"  Total width: {width(BitQ)}")

    section("Individual operations")

    # X on control
    print("X[0] — flip control (converts |0⟩-control to |1⟩-control)")
    x_ctrl = TenTerm(TwistPlus(Unit(), Unit()), Id(Q()))
    result = compile(x_ctrl)
    show_circuit(result)

    # Controlled-H
    print("\nC0-H[1] — controlled-H (H on target iff control=1)")
    ch = CH(0, 1, BitQ)
    result = compile(ch)
    show_circuit(result)

    # Controlled-S
    print("\nC0-S[1] — controlled-S (S on target iff control=1)")
    cs = CS(0, 1, BitQ)
    result = compile(cs)
    show_circuit(result)

    section("Complete QSwitch(H, S) circuit")

    # Full circuit: X[0] ; CS[0,1] ; CH[0,1] ; X[0] ; CH[0,1] ; CS[0,1]
    qswitch = Seq(
        TenTerm(TwistPlus(Unit(), Unit()), Id(Q())),  # X[0]
        CS(0, 1, BitQ),                                # C-S[0,1]
        CH(0, 1, BitQ),                                # C-H[0,1]
        TenTerm(TwistPlus(Unit(), Unit()), Id(Q())),  # X[0]
        CH(0, 1, BitQ),                                # C-H[0,1]
        CS(0, 1, BitQ),                                # C-S[0,1]
    )

    result = compile(qswitch)
    show_circuit(result, "QSwitch(H, S):")

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
    banner("SUMMARY: Compilation Pipeline")

    print("""
┌─────────────────────────────────────────────────────────────────────────┐
│  STAGE              REPRESENTATION                                      │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  1. SOURCE          λx. let (ctrl ⊗ tgt) = x in                         │
│     (Linear λ)        case ctrl of                                      │
│                         | Left(u)  => Left(u) ⊗ (S;H) tgt               │
│                         | Right(u) => Right(u) ⊗ (H;S) tgt              │
│                                                                         │
│        ↓ elaboration (macro expansion + case → controlled)              │
│                                                                         │
│  2. CORE IR         X[0] ; C0-S[1] ; C0-H[1] ; X[0] ; C0-H[1] ; C0-S[1] │
│     (Compositional)                                                     │
│                                                                         │
│        ↓ compile (emit gates, track permutation)                        │
│                                                                         │
│  3. CIRCUIT         pytket.Circuit with 4 gates                         │
│     (Executable)    + identity permutation [0, 1]                       │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘

KEY INSIGHT: Interface Duplication in Int/GOI

  The "trick" is that morphisms f : A → B become endos f̂ : A ⊗ B → A ⊗ B.

  For QSwitch:
  - H : Q → Q  becomes  Ĥ on boundary Q ⊗ Q (acts on wire 1, identity on wire 0)
  - S : Q → Q  becomes  Ŝ on boundary Q ⊗ Q
  - The control qubit lives on wire 0 and SELECTS the composition

  This is why quantum control over causal order works:
  the wires are doubled, and the control is EXPLICIT in the layout.
""")

    banner("DEMO COMPLETE")


if __name__ == "__main__":
    main()
