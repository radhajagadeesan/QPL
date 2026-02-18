#!/usr/bin/env python3
"""QSwitch Curried Derivation Demo (THEORY ONLY - no compilation)

Derives QSwitch with the lambda structure:
  λb. λf. λg. λx. case b of
    | Left(u)  => (Left(u), f(g(x)))
    | Right(u) => (Right(u), g(f(x)))

This is a theory-only demo explaining type derivation. No circuits are compiled.
For demos with actual compilation, see: qswitch_instantiation_demo.py

Run with: PYTHONPATH=python/src python python/demos/qswitch_curried_theory_demo.py
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
    section("QSWITCH CURRIED TYPE DERIVATION")

    # Base types
    I = Unit()
    A = Q()  # Using Q for concreteness
    Bool = Plus(I, I)

    print("""
We want to derive the type of:

    QSwitch = λb. λf. λg. λx. case b of
                | Left(u)  => (Left(u), f(g(x)))
                | Right(u) => (Right(u), g(f(x)))

Working inside-out...
""")

    section("1. TYPING THE BRANCHES")

    print("""
In the Left branch, we have in scope:
    u : I           (payload from Left)
    x : A           (from λx)
    f : A ⊸ A       (from λf)
    g : A ⊸ A       (from λg)

Derivation:
    ─────────────────────────────────────
    x : A
    ─────────────────────────────────────  (App)
    g(x) : A
    ─────────────────────────────────────  (App)
    f(g(x)) : A
    ─────────────────────────────────────  (Inj-L)
    Left(u) : I + I = Bool
    ─────────────────────────────────────  (Pair)
    (Left(u), f(g(x))) : Bool ⊗ A


Similarly, Right branch:
    ─────────────────────────────────────
    (Right(u), g(f(x))) : Bool ⊗ A

Both branches have the same type: Bool ⊗ A  ✓
""")

    section("2. TYPING THE CASE")

    print("""
The case expression:

    b : Bool
    ───────────────────────────────────────────────────────────
    Left branch  : Bool ⊗ A    (consuming u : I from b)
    Right branch : Bool ⊗ A    (consuming u : I from b)
    ───────────────────────────────────────────────────────────
    case b of Left(u) => ... | Right(u) => ...  :  Bool ⊗ A


LINEARITY CHECK:
    • b is consumed by the case (its tag controls the branches)
    • u : I has width 0 (unit payload)
    • Left(u)/Right(u) reconstructs a Bool in output
    • The tag qubit "passes through" — not duplicated!
""")

    section("3. BUILDING UP THE LAMBDAS")

    # Compute types step by step
    AtoA = Arrow(A, A)
    BoolA = Ten(Bool, A)

    print("Types we'll use:")
    print(f"    A = Q                      width = {width(A)}")
    print(f"    Bool = I + I               width = {width(Bool)}")
    print(f"    A ⊸ A                      width = {width(AtoA)}")
    print(f"    Bool ⊗ A                   width = {width(BoolA)}")
    print()

    # Step by step
    print("Lambda abstraction (inside-out):")
    print()

    # λx. case ...
    inner1 = Arrow(A, BoolA)
    print(f"    λx. case b of ...          : A ⊸ (Bool ⊗ A)")
    print(f"                                 width = {width(inner1)}")
    print(f"                                 (uses b, f, g from outer scope)")
    print()

    # λg. λx. case ...
    inner2 = Arrow(AtoA, inner1)
    print(f"    λg. λx. case b of ...      : (A ⊸ A) ⊸ A ⊸ (Bool ⊗ A)")
    print(f"                                 width = {width(inner2)}")
    print(f"                                 (uses b, f from outer scope)")
    print()

    # λf. λg. λx. case ...
    inner3 = Arrow(AtoA, inner2)
    print(f"    λf. λg. λx. case b of ...  : (A ⊸ A) ⊸ (A ⊸ A) ⊸ A ⊸ (Bool ⊗ A)")
    print(f"                                 width = {width(inner3)}")
    print(f"                                 (uses b from outer scope)")
    print()

    # λb. λf. λg. λx. case ...
    full_type = Arrow(Bool, inner3)
    print(f"    λb. λf. λg. λx. case ...   : Bool ⊸ (A ⊸ A) ⊸ (A ⊸ A) ⊸ A ⊸ (Bool ⊗ A)")
    print(f"                                 width = {width(full_type)}")
    print()

    section("4. THE FULL TYPE")

    print("""
┌─────────────────────────────────────────────────────────────────────────┐
│                                                                         │
│  QSwitch : Bool ⊸ (A ⊸ A) ⊸ (A ⊸ A) ⊸ A ⊸ (Bool ⊗ A)                 │
│                                                                         │
│  Or with explicit parentheses (⊸ is right-associative):                │
│                                                                         │
│  QSwitch : Bool ⊸ ((A ⊸ A) ⊸ ((A ⊸ A) ⊸ (A ⊸ (Bool ⊗ A))))           │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
""")

    print(f"Total width: {width(full_type)} wires")
    print()

    section("5. WIRE LAYOUT")

    print("""
Since A ⊸ B has width = width(A) + width(B), we can compute the wire layout.

For A = Q:
    • Bool    = 1 wire   (tag qubit)
    • A ⊸ A   = 2 wires  (argument slot + result slot)
    • A       = 1 wire   (target qubit)
    • Bool⊗A  = 2 wires  (output tag + output value)

Full layout (8 wires):

    INPUT SIDE (exposed by lambdas):
    ┌─────────────────────────────────────────────────────────────────┐
    │  Wire 0   │  Wire 1   Wire 2  │  Wire 3   Wire 4  │   Wire 5   │
    │ ┌───────┐ │ ┌───────┬───────┐ │ ┌───────┬───────┐ │ ┌────────┐ │
    │ │   b   │ │ │ f_arg │ f_res │ │ │ g_arg │ g_res │ │ │   x    │ │
    │ └───────┘ │ └───────┴───────┘ │ └───────┴───────┘ │ └────────┘ │
    │   Bool    │      A ⊸ A        │      A ⊸ A        │     A      │
    └─────────────────────────────────────────────────────────────────┘

    OUTPUT SIDE (result of computation):
    ┌─────────────────────────────────────────────────────────────────┐
    │                                       Wire 6       Wire 7      │
    │                                     ┌───────────┬────────────┐ │
    │                                     │   ctrl'   │   result   │ │
    │                                     └───────────┴────────────┘ │
    │                                          Bool ⊗ A              │
    └─────────────────────────────────────────────────────────────────┘
""")

    section("6. COMPARISON WITH TENSORED VERSION")

    # Tensored version
    tensored_input = Ten(AtoA, Ten(AtoA, Ten(Bool, A)))
    tensored_output = Ten(Bool, A)
    tensored_type = Arrow(tensored_input, tensored_output)

    print("The tensored version from earlier:")
    print()
    print("    QSwitch : (A ⊸ A) ⊗ (A ⊸ A) ⊗ Bool ⊗ A  →  Bool ⊗ A")
    print()
    print(f"    Input width:  {width(tensored_input)}")
    print(f"    Output width: {width(tensored_output)}")
    print(f"    Total width:  {width(tensored_type)}")
    print()

    print("The curried version:")
    print()
    print("    QSwitch : Bool ⊸ (A ⊸ A) ⊸ (A ⊸ A) ⊸ A ⊸ (Bool ⊗ A)")
    print()
    print(f"    Total width:  {width(full_type)}")
    print()

    print("""
Both have 8 wires total! This is the currying isomorphism at work:

    A ⊸ B ⊸ C  ≅  A ⊗ B ⊸ C

The difference is just in how we group the inputs:
    • Curried:  each λ exposes its argument wires sequentially
    • Tensored: all inputs arrive as one big tensor product
""")

    section("7. LINEARITY VERIFICATION")

    print("""
Let's verify each variable is used exactly once:

    λb. λf. λg. λx. case b of
      | Left(u)  => (Left(u), f(g(x)))
      | Right(u) => (Right(u), g(f(x)))

Variable usage:
    ┌──────────┬───────────────────────────────────────────────────────┐
    │ Variable │ Usage                                                 │
    ├──────────┼───────────────────────────────────────────────────────┤
    │ b        │ Consumed by case (tag qubit controls branch)         │
    │ u        │ Used once in Left(u) or Right(u) — width 0 anyway    │
    │ f        │ Used once: f(g(x)) in Left, f(x) in Right            │
    │ g        │ Used once: g(x) in Left, g(f(x)) in Right            │
    │ x        │ Used once: passed to g in Left, to f in Right        │
    └──────────┴───────────────────────────────────────────────────────┘

QUANTUM SUBTLETY:
    In superposition (b = |+⟩), both branches execute coherently!

    But this is OK because:
    • f and g are WIRE BUNDLES, not classical functions
    • The routing (which wires connect) is controlled by b
    • In superposition, both routings happen simultaneously
    • This is exactly "indefinite causal order"
""")

    section("8. SEMANTIC VERIFICATION")

    print("""
Let's trace the semantics for different inputs:

CASE 1: b = |0⟩ (Left)
────────────────────────
    Input:  |0⟩ |f⟩ |g⟩ |ψ⟩

    case |0⟩ of Left(u) => (Left(u), f(g(ψ)))

    Output: |0⟩ |f(g(ψ))⟩

    (Control passes through, operations applied as g then f)


CASE 2: b = |1⟩ (Right)
─────────────────────────
    Input:  |1⟩ |f⟩ |g⟩ |ψ⟩

    case |1⟩ of Right(u) => (Right(u), g(f(ψ)))

    Output: |1⟩ |g(f(ψ))⟩

    (Control passes through, operations applied as f then g)


CASE 3: b = |+⟩ (Superposition)
────────────────────────────────
    Input:  |+⟩ |f⟩ |g⟩ |ψ⟩  =  (|0⟩ + |1⟩)/√2 |f⟩ |g⟩ |ψ⟩

    BOTH branches execute coherently!

    Output: (|0⟩|f(g(ψ))⟩ + |1⟩|g(f(ψ))⟩) / √2

    The control qubit is now ENTANGLED with which order was applied.
    This is INDEFINITE CAUSAL ORDER!
""")

    section("SUMMARY")

    print("""
┌─────────────────────────────────────────────────────────────────────────┐
│                                                                         │
│  QSwitch = λb. λf. λg. λx. case b of                                   │
│              | Left(u)  => (Left(u), f(g(x)))                          │
│              | Right(u) => (Right(u), g(f(x)))                         │
│                                                                         │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  TYPE:  Bool ⊸ (A ⊸ A) ⊸ (A ⊸ A) ⊸ A ⊸ (Bool ⊗ A)                    │
│                                                                         │
│  WIDTH: 8 wires total (same as tensored version)                       │
│                                                                         │
│  SEMANTICS:                                                             │
│    |0⟩ f g ψ  ↦  |0⟩ f(g(ψ))        (g then f)                         │
│    |1⟩ f g ψ  ↦  |1⟩ g(f(ψ))        (f then g)                         │
│    |+⟩ f g ψ  ↦  entangled!         (indefinite causal order)          │
│                                                                         │
│  LINEARITY: ✓ All variables used exactly once                          │
│                                                                         │
│  KEY INSIGHT:                                                           │
│    The control qubit b appears in BOTH input and output.               │
│    It's not consumed — it passes through and becomes entangled         │
│    with the result. This preserves quantum information.                │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
""")


if __name__ == "__main__":
    main()
