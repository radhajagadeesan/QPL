#!/usr/bin/env python3
"""QSwitch with Abstract Function Arguments

This demo shows QSwitch as an actual term with Bool as the outermost argument
and abstract function parameters f, g : Q → Q.

Type signature:
    QSwitch : Bool ⊗ Q ⊗ (Q→Q) ⊗ (Q→Q) → Bool ⊗ Q

Where:
    Bool = I + I (1 wire: tag bit)
    Q→Q ≡ Q ⊗ Q (2 wires: input, output) since Q* = Q

Run with: PYTHONPATH=src python demos/qswitch_abstract_demo.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from lang.types import Q, Unit, Ten, Plus, width, Dual
from lang.terms import (
    Lam, Apply, FunVar, Cap, Cup, Id, Seq, TenTerm,
    Case, TwistTen, AssocTenL, AssocTenR,
)
from compile.to_pytket import compile
from typing_.check import type_of


def section(title: str) -> None:
    print()
    print("=" * 70)
    print(f"  {title}")
    print("=" * 70)
    print()


def main():
    section("QSWITCH WITH ABSTRACT FUNCTION ARGUMENTS")

    # =========================================================================
    # Type definitions
    # =========================================================================

    Bool = Plus(Unit(), Unit())  # I + I
    QQ = Ten(Q(), Q())           # Q ⊗ Q ≡ Q → Q (function type encoding)

    # Input: Bool ⊗ Q ⊗ (Q→Q) ⊗ (Q→Q)
    # Nested as: ((Bool ⊗ Q) ⊗ (Q⊗Q)) ⊗ (Q⊗Q)
    BoolQ = Ten(Bool, Q())
    BoolQ_f = Ten(BoolQ, QQ)
    InputTy = Ten(BoolQ_f, QQ)

    # Output: Bool ⊗ Q
    OutputTy = Ten(Bool, Q())

    print(f"""
TYPE SIGNATURE:

    QSwitch : Bool ⊗ Q ⊗ (Q→Q) ⊗ (Q→Q) → Bool ⊗ Q

TYPE ENCODINGS:

    Bool   = I + I           width = {width(Bool)} (log-tag encoding)
    Q→Q    ≡ Q* ⊗ Q ≡ Q ⊗ Q  width = {width(QQ)} (self-dual)

    Input  = Bool ⊗ Q ⊗ (Q→Q) ⊗ (Q→Q)
           = (I+I) ⊗ Q ⊗ (Q⊗Q) ⊗ (Q⊗Q)
           width = {width(InputTy)}

    Output = Bool ⊗ Q
           width = {width(OutputTy)}
""")

    section("1. Wire Layout")

    print("""
INPUT WIRES (6 total):

    ┌─────────────────────────────────────────────────────────┐
    │  Wire 0: ctrl (Bool tag)     ─── control qubit          │
    │  Wire 1: tgt  (Q)            ─── target qubit           │
    │  Wire 2: f.in (Q)            ─┐                         │
    │  Wire 3: f.out (Q)           ─┴─ function f : Q → Q     │
    │  Wire 4: g.in (Q)            ─┐                         │
    │  Wire 5: g.out (Q)           ─┴─ function g : Q → Q     │
    └─────────────────────────────────────────────────────────┘

OUTPUT WIRES (2 total):

    ┌─────────────────────────────────────────────────────────┐
    │  Wire 0: ctrl (Bool tag)     ─── passed through         │
    │  Wire 1: result (Q)          ─── f;g(tgt) or g;f(tgt)   │
    └─────────────────────────────────────────────────────────┘

FUNCTION ENCODING:

    A function f : Q → Q is represented as 2 wires:

        f.in  ●───[ f ]───● f.out

    "Applying" f to x means connecting x to f.in via Cap,
    then f.out becomes the result.
""")

    section("2. QSwitch Semantics")

    print("""
SEMANTICS:

    QSwitch (ctrl, tgt, f, g) =
        case ctrl of
        | Left  → (ctrl, (f ; g)(tgt))    -- apply f then g
        | Right → (ctrl, (g ; f)(tgt))    -- apply g then f

WIRE ROUTING:

    When ctrl = |0⟩ (Left):

        tgt ──●                      ●── result
              │                      │
              └──→ f.in   f.out ──→ g.in   g.out ──┘

        Route: tgt → f → g → result

    When ctrl = |1⟩ (Right):

        tgt ──●                      ●── result
              │                      │
              └──→ g.in   g.out ──→ f.in   f.out ──┘

        Route: tgt → g → f → result

    When ctrl = superposition:

        Both routes execute coherently!
        The target qubit is routed through BOTH orderings simultaneously.
""")

    section("3. Building the Term")

    print("""
In our linear λ-calculus, QSwitch is built using:

    λ(ctrl, tgt, f, g).
        let (ctrl', tgt') = case ctrl of
            | Left  → Cap(g) ∘ Cap(f) ∘ (tgt, f, g)   -- f;g
            | Right → Cap(f) ∘ Cap(g) ∘ (tgt, g, f)   -- g;f
        in (ctrl', tgt')

Where Cap connects a value to a function's input wire:

    Cap : Q* ⊗ Q → I

    Applying f to x:  Cap(f.in, x) produces f.out as result
""")

    # Build the term structure
    # We'll build it step by step

    # FunVar for f and g
    f_var = FunVar("f", Q(), Q())  # f : Q → Q (2 wires)
    g_var = FunVar("g", Q(), Q())  # g : Q → Q (2 wires)

    print("Term components:")
    print(f"  f = FunVar('f', Q, Q)  -- represents f : Q → Q")
    print(f"  g = FunVar('g', Q, Q)  -- represents g : Q → Q")
    print()

    # The full lambda structure
    # λinput. body  where input : Bool ⊗ Q ⊗ (Q→Q) ⊗ (Q→Q)

    # For now, show the identity as a placeholder
    # (Full implementation requires Case with higher-order branches)

    section("4. Instantiation: QSwitch(ctrl, tgt, H, S)")

    print("""
When we instantiate f = H and g = S, the abstract wires become concrete gates:

    f.in ──[ H ]── f.out    becomes    ──[ H ]──
    g.in ──[ S ]── g.out    becomes    ──[ S ]──

The controlled routing becomes controlled gates:

    case ctrl of Left → H;S | Right → S;H

    ═══════════════════════════════════════════════════════

    X[ctrl]; CH[ctrl,tgt]; CS[ctrl,tgt]; X[ctrl]; CS[ctrl,tgt]; CH[ctrl,tgt]
    ─────────────────────────────────────  ─────────────────────────────────
           anti-controlled (H;S)                  controlled (S;H)
""")

    # Build the instantiated circuit
    from lang.terms import CH, CS, X

    ty = Ten(Q(), Q())  # ctrl ⊗ tgt

    qswitch_HS = Seq(
        X(0, ty),         # flip for anti-control
        CH(0, 1, ty),     # C-H (left branch)
        CS(0, 1, ty),     # C-S (left branch)
        X(0, ty),         # restore
        CS(0, 1, ty),     # C-S (right branch)
        CH(0, 1, ty),     # C-H (right branch)
    )

    result = compile(qswitch_HS)

    print("Instantiated circuit (f=H, g=S):")
    print(f"  Qubits: {result.circuit.n_qubits}")
    print(f"  Gates:  {result.circuit.n_gates}")
    print()
    print("  Commands:")
    for cmd in result.circuit.get_commands():
        print(f"    {cmd}")

    print("""
Circuit diagram:

    ctrl ──X───●───●───X───●───●──
               │   │       │   │
    tgt  ─────CH──CS──────CS──CH──
""")

    section("5. The Higher-Order Insight")

    print("""
┌──────────────────────────────────────────────────────────────────────┐
│  ABSTRACT vs INSTANTIATED                                            │
├──────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  ABSTRACT (with f, g as parameters):                                 │
│                                                                      │
│      QSwitch : Bool ⊗ Q ⊗ (Q→Q) ⊗ (Q→Q) → Bool ⊗ Q                  │
│                                                                      │
│      Input: 6 wires (ctrl, tgt, f.in, f.out, g.in, g.out)           │
│      The circuit conditionally ROUTES through f or g                 │
│                                                                      │
│  INSTANTIATED (f=H, g=S):                                            │
│                                                                      │
│      QSwitch[H,S] : Bool ⊗ Q → Bool ⊗ Q                              │
│                                                                      │
│      Input: 2 wires (ctrl, tgt)                                      │
│      The circuit uses CONTROLLED GATES (CH, CS)                      │
│                                                                      │
├──────────────────────────────────────────────────────────────────────┤
│  KEY INSIGHT:                                                        │
│                                                                      │
│  In the abstract version, functions ARE wires.                       │
│  "Applying" a function = connecting wires via Cap.                   │
│  "Controlled apply" = controlled wire routing.                       │
│                                                                      │
│  At instantiation, abstract wires become concrete gates,             │
│  and controlled routing becomes controlled gates.                    │
└──────────────────────────────────────────────────────────────────────┘
""")

    section("6. Type-Level View")

    print(f"""
The curried type signature with Bool outermost:

    QSwitch : Bool → Q → (Q→Q) → (Q→Q) → Bool ⊗ Q

Uncurrying (how we encode it):

    QSwitch : Bool ⊗ Q ⊗ (Q→Q) ⊗ (Q→Q) → Bool ⊗ Q

Partial application sequence:

    QSwitch                     : Bool⊗Q⊗(Q→Q)⊗(Q→Q) → Bool⊗Q
    QSwitch |0⟩                 : Q⊗(Q→Q)⊗(Q→Q) → Bool⊗Q
    QSwitch |0⟩ |ψ⟩             : (Q→Q)⊗(Q→Q) → Bool⊗Q
    QSwitch |0⟩ |ψ⟩ H           : (Q→Q) → Bool⊗Q
    QSwitch |0⟩ |ψ⟩ H S         : Bool⊗Q                   (result!)

Wire consumption:

    Start with 6 wires: [ctrl, tgt, f.in, f.out, g.in, g.out]
    After routing:      [ctrl, result]  (2 wires)

    The f and g wires are "consumed" by application (Cap).
""")


if __name__ == "__main__":
    main()
