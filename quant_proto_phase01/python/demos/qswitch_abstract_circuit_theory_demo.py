#!/usr/bin/env python3
"""Abstract QSwitch Circuit Demo (THEORY ONLY - no compilation)

Shows the ABSTRACT QSwitch circuit structure - NO instantiation.
This is the pure higher-order term before any concrete functions are applied.

This is a theory-only demo explaining wire layouts and semantics. No circuits are compiled.
For demos with actual compilation, see: qswitch_instantiation_demo.py

Run with: PYTHONPATH=python/src python python/demos/qswitch_abstract_circuit_theory_demo.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from lang.types import Q, Unit, Ten, Plus, Arrow, width


def section(title: str) -> None:
    print()
    print("=" * 74)
    print(f"  {title}")
    print("=" * 74)
    print()


def main():
    section("ABSTRACT QSWITCH - Pure Higher-Order Structure")

    # Type definitions
    I = Unit()
    Bool = Plus(I, I)           # I + I (control qubit)
    QtoQ = Arrow(Q(), Q())      # Q ⊸ Q = 2 wires [arg | res]

    # Curried type (built inside-out)
    A = Q()
    BoolA = Ten(Bool, A)                    # Bool ⊗ A
    inner1 = Arrow(A, BoolA)                # A ⊸ (Bool ⊗ A)
    inner2 = Arrow(QtoQ, inner1)            # (A⊸A) ⊸ A ⊸ (Bool ⊗ A)
    inner3 = Arrow(QtoQ, inner2)            # (A⊸A) ⊸ (A⊸A) ⊸ A ⊸ (Bool ⊗ A)
    full_type = Arrow(Bool, inner3)         # Bool ⊸ (A⊸A) ⊸ (A⊸A) ⊸ A ⊸ (Bool ⊗ A)

    print(f"""
TYPE SIGNATURE (Curried Form):
──────────────────────────────

    QSwitch : Bool ⊸ (A ⊸ A) ⊸ (A ⊸ A) ⊸ A ⊸ (Bool ⊗ A)

    Where:
      A ⊸ A  = linear function type, width = {width(QtoQ)} wires
      Bool   = I + I (sum type), width = {width(Bool)} wire
      A      = single qubit, width = {width(A)} wire
      Bool⊗A = output pair, width = {width(BoolA)} wires

    Total width: {width(full_type)} wires

    Note: Bool appears in BOTH input and output!
    The control qubit is not consumed — it passes through.
""")

    section("1. Wire Layout (Curried Form)")

    print("""
For the curried type:  Bool ⊸ (A ⊸ A) ⊸ (A ⊸ A) ⊸ A ⊸ (Bool ⊗ A)

Each lambda exposes its argument wires in order:

INPUT WIRES (6 total):
──────────────────────

    ┌─────────────────────────────────────────────────────────────────┐
    │                                                                 │
    │  Wire 0  │  Wire 1   Wire 2  │  Wire 3   Wire 4  │   Wire 5    │
    │ ┌──────┐ │ ┌──────┬────────┐ │ ┌──────┬────────┐ │ ┌────────┐  │
    │ │  b   │ │ │f_arg │ f_res  │ │ │g_arg │ g_res  │ │ │   x    │  │
    │ └──────┘ │ └──────┴────────┘ │ └──────┴────────┘ │ └────────┘  │
    │   Bool   │      A ⊸ A        │      A ⊸ A        │     A       │
    │   (λb)   │      (λf)         │      (λg)         │    (λx)     │
    │                                                                 │
    └─────────────────────────────────────────────────────────────────┘

    Layout follows lambda nesting (outermost first):
      • b occupies wire  [0]     — control qubit
      • f occupies wires [1, 2]  — first function bundle
      • g occupies wires [3, 4]  — second function bundle
      • x occupies wire  [5]     — target qubit

    Functions are WIRE BUNDLES:  A ⊸ B  ≅  A* ⊗ B  ≅  A ⊗ B  (self-dual)


OUTPUT WIRES (2 total):
───────────────────────

    ┌─────────────────────────────────────────────────────────────────┐
    │                                                                 │
    │                                       Wire 6       Wire 7      │
    │                                     ┌───────────┬────────────┐ │
    │                                     │    b'     │   result   │ │
    │                                     └───────────┴────────────┘ │
    │                                          Bool ⊗ A              │
    │                                                                 │
    └─────────────────────────────────────────────────────────────────┘

    The control qubit b passes through to the output!
""")

    section("2. Abstract Term Structure")

    print("""
QSWITCH AS A TERM (Curried Form):
─────────────────────────────────

    QSwitch = λb. λf. λg. λx. case b of
                | Left(u)  ⇒ (Left(u), f(g(x)))
                | Right(u) ⇒ (Right(u), g(f(x)))

    Where:
      b : Bool        (control qubit)
      f : A ⊸ A       (first function)
      g : A ⊸ A       (second function)
      x : A           (target)


TYPE:
─────

    QSwitch : Bool ⊸ (A ⊸ A) ⊸ (A ⊸ A) ⊸ A ⊸ (Bool ⊗ A)

    Note: Bool appears in BOTH input and output!
    The control qubit passes through — it's not consumed.


SEMANTICS:
──────────

    │0⟩ f g ψ  ↦  │0⟩ ⊗ f(g(ψ))        (g first, then f)
    │1⟩ f g ψ  ↦  │1⟩ ⊗ g(f(ψ))        (f first, then g)
    │+⟩ f g ψ  ↦  (│0⟩⊗f(g(ψ)) + │1⟩⊗g(f(ψ))) / √2
                   SUPERPOSITION of causal orders!


LINEARITY:
──────────

    Each variable is used exactly once:
      • b — consumed by case, reconstructed as Left(u)/Right(u) in output
      • f — used once in each branch (f(g(x)) or f(x))
      • g — used once in each branch (g(x) or g(f(x)))
      • x — used once (passed to first function in chain)
      • u — unit payload, width 0
""")

    section("3. Abstract Circuit Diagram")

    print("""
ABSTRACT QSWITCH CIRCUIT (Curried Wire Layout):
───────────────────────────────────────────────

    b     (0) ────┬─────────────────────────────────────────────────────────┬─── b'
                  │                                                         │
    f_arg (1) ════╪═════════════════════════════════════════════════════╗   │
                  │                                                     ║   │
    f_res (2) ════╪═════════════════════════════════════════════════════╬═══╪═══╗
                  │                                                     ║   │   ║
    g_arg (3) ════╪═════════════════════════════════════════════════╗   ║   │   ║
                  │                                                 ║   ║   │   ║
    g_res (4) ════╪═════════════════════════════════════════════════╬═══╬═══╪═══╬═══╗
                  │                                                 ║   ║   │   ║   ║
                  └─────────────────────────────────────────────────╨───╨───┼───╨───╨──┐
                                        QUANTUM CASE                        │          │
                                                                            │          │
                    │0⟩: route  x → g_arg → g_res → f_arg → f_res → result │          │
                    │1⟩: route  x → f_arg → f_res → g_arg → g_res → result │          │
                                                                            │          │
                  ┌─────────────────────────────────────────────────────────┘          │
    x     (5) ────┴────────────────────────────────────────────────────────────────────┴─── result


    Legend:
      ════  Function wires (routed differently based on b)
      ────  Data wires (b passes through, x is transformed)
""")

    section("4. Routing per Branch")

    print("""
BRANCH Left (b = │0⟩): Apply g then f
──────────────────────────────────────

    Wiring: x → g_arg,  g_res → f_arg,  f_res → result

    ┌─────────────────────────────────────────────────────────────────┐
    │                                                                 │
    │   b     (0) ────────────────────────────────────────→ b'        │
    │                                                                 │
    │   f_arg (1) ←───────────────────────────┐                       │
    │                                         │                       │
    │   f_res (2) ────────────────────────────┼───────────→ result    │
    │                                         │                       │
    │   g_arg (3) ←───────────┐               │                       │
    │                         │               │                       │
    │   g_res (4) ────────────┼───────────────┘                       │
    │                         │                                       │
    │   x     (5) ────────────┘                                       │
    │                                                                 │
    │   Flow: x ──→ [g] ──→ [f] ──→ result                           │
    │                                                                 │
    └─────────────────────────────────────────────────────────────────┘


BRANCH Right (b = │1⟩): Apply f then g
───────────────────────────────────────

    Wiring: x → f_arg,  f_res → g_arg,  g_res → result

    ┌─────────────────────────────────────────────────────────────────┐
    │                                                                 │
    │   b     (0) ────────────────────────────────────────→ b'        │
    │                                                                 │
    │   f_arg (1) ←───────────┐                                       │
    │                         │                                       │
    │   f_res (2) ────────────┼───────────────┐                       │
    │                         │               │                       │
    │   g_arg (3) ←───────────┼───────────────┘                       │
    │                         │                                       │
    │   g_res (4) ────────────┼───────────────────────────→ result    │
    │                         │                                       │
    │   x     (5) ────────────┘                                       │
    │                                                                 │
    │   Flow: x ──→ [f] ──→ [g] ──→ result                           │
    │                                                                 │
    └─────────────────────────────────────────────────────────────────┘
""")

    section("5. The Quantum CASE Circuit")

    print("""
CASE STRUCTURE:
───────────────

    Case : (A + B) → (C + D)

    Input:  sum type with tag qubit
    Output: sum type, tag preserved

    │tag⟩ = │0⟩  :  apply LEFT routing
    │tag⟩ = │1⟩  :  apply RIGHT routing
    │tag⟩ = │+⟩  :  BOTH routings in superposition!


ANTI-CONTROL PATTERN:
─────────────────────

    Standard controlled operations fire when control = │1⟩.
    But LEFT branch must fire when control = │0⟩!

    Solution: X-gate sandwich (anti-control pattern)

    ┌─────────────────────────────────────────────────────────────────┐
    │                                                                 │
    │  ANTI-CONTROLLED OPERATION: fires when control = │0⟩            │
    │                                                                 │
    │      ctrl ───X───●───X───          Equivalent to:               │
    │              │   │   │                                          │
    │      tgt  ───────R───────          "Route R when ctrl = │0⟩"    │
    │                                                                 │
    │  How it works:                                                  │
    │    1. X flips ctrl:  │0⟩ → │1⟩,  │1⟩ → │0⟩                     │
    │    2. Controlled-R:  fires when ctrl = │1⟩ (original │0⟩)      │
    │    3. X restores:    │1⟩ → │0⟩,  │0⟩ → │1⟩                     │
    │                                                                 │
    │  Net effect: R applied iff original ctrl was │0⟩                │
    │                                                                 │
    └─────────────────────────────────────────────────────────────────┘


CASE COMPILATION STRUCTURE:
───────────────────────────

    ┌─────────────────────────────────────────────────────────────────┐
    │                                                                 │
    │   ctrl ───X───●─────────────X───●─────────────                  │
    │           │   │             │   │                               │
    │           │   │ LEFT        │   │ RIGHT                         │
    │           │   │ routing     │   │ routing                       │
    │           │   │             │   │                               │
    │   wires ──────┴─────────────────┴─────────────                  │
    │                                                                 │
    │           └─────────────┘   └─────────────┘                     │
    │            anti-control       control                           │
    │            (fires on 0)      (fires on 1)                       │
    │                                                                 │
    └─────────────────────────────────────────────────────────────────┘


COHERENCE PRESERVATION:
───────────────────────

    The X-gate trick preserves quantum coherence because:

    • X is self-inverse: X² = I
    • X│+⟩ = │+⟩  (superposition unchanged!)
    • Both branches execute coherently on superposition input

    For │+⟩ input:
      X creates temporary basis change, doesn't collapse superposition.
      Both routings happen simultaneously in different branches of
      the quantum state.
""")

    section("6. Function Application (Abstract)")

    print("""
APPLY OPERATION:
────────────────

    Apply(f, x) where f : A ⊸ B and x : A

    In our wire-bundle encoding:
      • f is represented as wires [f_arg │ f_res]
      • x is a value on some wire(s)

    Apply CONNECTS:
      • x → f_arg    (feed input to function's argument slot)
      • f_res → out  (function's result slot becomes output)

    ┌─────────────────────────────────────────────────────────────────┐
    │                                                                 │
    │  Before Apply:           After Apply:                           │
    │                                                                 │
    │  f_arg ─────────         x ──────┐                              │
    │                                  │                              │
    │  f_res ─────────                 ▼                              │
    │                          f_arg ──┴── f_res ──→ output           │
    │  x     ─────────                                                │
    │                          (wires connected/identified)           │
    │                                                                 │
    └─────────────────────────────────────────────────────────────────┘

    Apply is PURE WIRING - no gates, just wire identification.


NESTED APPLICATION f(g(x)):
───────────────────────────

    ┌─────────────────────────────────────────────────────────────────┐
    │                                                                 │
    │  x ─────────→ g_arg                                             │
    │                                                                 │
    │               g_res ─────────→ f_arg                            │
    │                                                                 │
    │                                 f_res ─────────→ output         │
    │                                                                 │
    │  Flow: x ──→ [g] ──→ [f] ──→ output                            │
    │                                                                 │
    └─────────────────────────────────────────────────────────────────┘
""")

    section("7. Type Verification")

    print("""
Verifying that computed types match the diagrams above:
""")

    # Verify all widths match what we printed
    print(f"  Bool = I + I                    width = {width(Bool)}  (claimed: 1) {'✓' if width(Bool) == 1 else '✗'}")
    print(f"  A = Q                           width = {width(A)}  (claimed: 1) {'✓' if width(A) == 1 else '✗'}")
    print(f"  A ⊸ A                           width = {width(QtoQ)}  (claimed: 2) {'✓' if width(QtoQ) == 2 else '✗'}")
    print(f"  Bool ⊗ A                        width = {width(BoolA)}  (claimed: 2) {'✓' if width(BoolA) == 2 else '✗'}")
    print(f"  Full curried type               width = {width(full_type)}  (claimed: 8) {'✓' if width(full_type) == 8 else '✗'}")
    print()

    # Verify wire layout
    # Input wires: b(1) + f(2) + g(2) + x(1) = 6
    input_wires = width(Bool) + width(QtoQ) + width(QtoQ) + width(A)
    print(f"  Input wires: {width(Bool)} + {width(QtoQ)} + {width(QtoQ)} + {width(A)} = {input_wires}  (claimed: 6) {'✓' if input_wires == 6 else '✗'}")

    # Output wires: Bool ⊗ A = 2
    output_wires = width(BoolA)
    print(f"  Output wires: {output_wires}  (claimed: 2) {'✓' if output_wires == 2 else '✗'}")
    print()

    all_correct = (width(Bool) == 1 and width(A) == 1 and width(QtoQ) == 2 and
                   width(BoolA) == 2 and width(full_type) == 8 and
                   input_wires == 6 and output_wires == 2)

    if all_correct:
        print("  ✓ ALL TYPE WIDTHS VERIFIED - diagrams match computed types")
    else:
        print("  ✗ MISMATCH DETECTED - diagrams do not match computed types")

    section("SUMMARY")

    print("""
┌─────────────────────────────────────────────────────────────────────────┐
│                                                                         │
│  ABSTRACT QSWITCH (Curried Form)                                       │
│                                                                         │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  TERM:                                                                  │
│      QSwitch = λb. λf. λg. λx. case b of                               │
│                  | Left(u)  ⇒ (Left(u), f(g(x)))                       │
│                  | Right(u) ⇒ (Right(u), g(f(x)))                      │
│                                                                         │
│  TYPE:                                                                  │
│      QSwitch : Bool ⊸ (A ⊸ A) ⊸ (A ⊸ A) ⊸ A ⊸ (Bool ⊗ A)             │
│                                                                         │
│  WIRES (8 total):                                                       │
│      Input:  [b│f_arg│f_res│g_arg│g_res│x]  (6 wires from lambdas)     │
│      Output: [b'│result]                     (2 wires)                  │
│                                                                         │
│  SEMANTICS:                                                             │
│      │0⟩ f g ψ  ↦  │0⟩ f(g(ψ))      (g then f)                         │
│      │1⟩ f g ψ  ↦  │1⟩ g(f(ψ))      (f then g)                         │
│      │+⟩ f g ψ  ↦  entangled superposition of both orders!             │
│                                                                         │
│  STRUCTURE:                                                             │
│      • b passes through (not consumed, appears in output)              │
│      • f, g are WIRE BUNDLES (2 wires each)                            │
│      • Case branches on b with coherent quantum control                │
│      • Apply connects wires (pure routing, no gates)                   │
│      • Anti-control pattern: X-sandwich for Left branch                │
│                                                                         │
│  KEY INSIGHT:                                                           │
│      The abstract QSwitch is pure ROUTING + CONTROL structure.         │
│      It defines HOW to compose f and g based on b,                     │
│      without specifying WHAT f and g are.                              │
│                                                                         │
│      This is INDEFINITE CAUSAL ORDER as a circuit primitive.           │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
""")


if __name__ == "__main__":
    main()
