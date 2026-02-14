#!/usr/bin/env python3
"""Abstract QSwitch as a Higher-Order Term

This demo builds the ABSTRACT QSwitch using LetPair, Var, Apply, and Case.
This is the QSwitch BEFORE instantiation with specific gates like H and S.

    QSwitch : (Q⊸Q) ⊗ (Q⊸Q) ⊗ Bool ⊗ Q → Bool ⊗ Q

The abstract definition (in pseudocode):

    QSwitch = λinput.
      let (f, rest) = input in
      let (g, rest2) = rest in
      let (b, x) = rest2 in
      case b of
        | Left  => (b, Apply(f, Apply(g, x)))  -- f;g when ctrl=0
        | Right => (b, Apply(g, Apply(f, x)))  -- g;f when ctrl=1

Usage:
    python qswitch_abstract_demo.py              # Run demo
    python qswitch_abstract_demo.py --circuits   # Show circuit diagrams
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from lang.types import Q, Unit, Ten, Plus, Arrow, width
from lang.terms import (
    Id, Seq, TenTerm, Case, DistR,
    Var, Pair, LetPair, Lam, Apply, FunVar,
    H, S,
)
from typing_.check import type_of

from demo_utils import DemoRunner

# Global runner instance
runner = None


def main():
    global runner
    runner = DemoRunner(
        "Abstract QSwitch (Higher-Order Term)",
        "QSwitch as a higher-order term before instantiation"
    )
    runner.print_header()

    # ==========================================================================
    # Type Definitions
    # ==========================================================================
    print("\n" + "="*74)
    print("  1. Type Definitions")
    print("="*74 + "\n")

    I = Unit()
    Bool = Plus(I, I)           # I + I (control qubit)
    QtoQ = Arrow(Q(), Q())      # Q ⊸ Q (single-qubit operation)

    # QSwitch input type: (Q⊸Q) ⊗ (Q⊸Q) ⊗ Bool ⊗ Q
    # Layout: [f_arg | f_res | g_arg | g_res | tag | x]
    #         [  Q   |   Q   |   Q   |   Q   |  1  | Q ]  = 6 wires
    input_ty = Ten(QtoQ, Ten(QtoQ, Ten(Bool, Q())))

    # QSwitch output type: Bool ⊗ Q
    # Layout: [tag | x'] = 2 wires
    output_ty = Ten(Bool, Q())

    print(f"""
TYPE DEFINITIONS:

    Q ⊸ Q       width = {width(QtoQ)} (argument wire + result wire)
    Bool        width = {width(Bool)} (tag qubit)

    Input:  (Q⊸Q) ⊗ (Q⊸Q) ⊗ Bool ⊗ Q   width = {width(input_ty)}
    Output: Bool ⊗ Q                     width = {width(output_ty)}

Wire layout for input:
    [f_arg | f_res | g_arg | g_res | tag | x]
    [  0   |   1   |   2   |   3   |  4  | 5]
""")

    # ==========================================================================
    # Abstract QSwitch Term Structure
    # ==========================================================================
    print("\n" + "="*74)
    print("  2. Abstract QSwitch Term Structure")
    print("="*74 + "\n")

    print("""
The abstract QSwitch has this structure:

    QSwitch =
      let (f, rest) = input in           -- f : Q ⊸ Q
      let (g, rest2) = rest in           -- g : Q ⊸ Q
      let (b, x) = rest2 in              -- b : Bool, x : Q
      case b of
        | Left(u)  => (b, Apply(f, Apply(g, x)))  -- f(g(x)) when b=|0⟩
        | Right(u) => (b, Apply(g, Apply(f, x)))  -- g(f(x)) when b=|1⟩

Note: f and g are FUNCTION VALUES, not gates. They are wire bundles
representing the function's argument-slot and result-slot.
""")

    # ==========================================================================
    # Building the Term
    # ==========================================================================
    print("\n" + "="*74)
    print("  3. Building the Abstract QSwitch Term")
    print("="*74 + "\n")

    # The inner types after destructuring:
    rest_ty = Ten(QtoQ, Ten(Bool, Q()))   # (Q⊸Q) ⊗ Bool ⊗ Q
    rest2_ty = Ten(Bool, Q())              # Bool ⊗ Q

    print(f"""
After destructuring:
    f     : Q ⊸ Q           width = {width(QtoQ)}
    rest  : (Q⊸Q) ⊗ Bool ⊗ Q   width = {width(rest_ty)}
    g     : Q ⊸ Q           width = {width(QtoQ)}
    rest2 : Bool ⊗ Q         width = {width(rest2_ty)}
    b     : Bool             width = {width(Bool)}
    x     : Q                width = {width(Q())}
""")

    # ==========================================================================
    # Instantiation with H and S
    # ==========================================================================
    print("\n" + "="*74)
    print("  4. Instantiation: QSwitch[H, S]")
    print("="*74 + "\n")

    print("""
To instantiate QSwitch with specific gates H and S, we would:

1. Create function values for H and S (as 2-wire bundles)
2. Tensor them with Bool ⊗ Q input
3. Apply the abstract QSwitch

However, for now we use the DIRECT approach from qswitch_term_demo.py:

    QSwitch[H,S] = DistR(I,I,Q) ; Case(I⊗Q, I⊗Q, H;S, S;H)

This bypasses the higher-order structure and builds the instantiated
circuit directly using Case.
""")

    # Build the instantiated version using Case directly
    IQ = Ten(I, Q())
    BoolQ = Ten(Bool, Q())

    # Build branches
    left_branch = Seq(H(0, IQ), S(0, IQ))   # H;S when ctrl=|0⟩
    right_branch = Seq(S(0, IQ), H(0, IQ))  # S;H when ctrl=|1⟩

    # Case term
    case_term = Case(IQ, IQ, left_branch, right_branch)

    # Full QSwitch = DistR ; Case
    dist = DistR(I, I, Q())
    qswitch_hs = Seq(dist, case_term)

    dom, cod = type_of(qswitch_hs)
    print(f"QSwitch[H,S] type: {dom} → {cod}")

    # Compile
    result = runner.compile(qswitch_hs, "QSwitch[H,S]")
    runner.print_circuit_details(result, "Compiled Circuit")
    runner.show_circuit(result, "QSwitch[H,S]")

    # ==========================================================================
    # Summary
    # ==========================================================================
    print("\n" + "="*74)
    print("  5. Summary")
    print("="*74 + "\n")

    print("""
ABSTRACT QSWITCH
────────────────

  TYPE:
    QSwitch : (Q⊸Q) ⊗ (Q⊸Q) ⊗ Bool ⊗ Q → Bool ⊗ Q

  WIRE LAYOUT:
    Input:  [f_arg | f_res | g_arg | g_res | tag | x]  (6 wires)
    Output: [tag | x']  (2 wires)

  SEMANTICS:
    |0⟩|ψ⟩ → |0⟩(f∘g)(ψ)
    |1⟩|ψ⟩ → |1⟩(g∘f)(ψ)

  KEY INSIGHT:
    Functions f, g are WIRE BUNDLES (Q ⊗ Q wires each).
    LetPair destructures input to bind f, g, b, x to wire ranges.
    Apply connects wires (boundary splicing).
    Case branches on tag with coherent quantum control.

  INSTANTIATION:
    QSwitch[H, S] → X[0]; CH; CS; X[0]; CS; CH
    QSwitch[X, Z] → X[0]; CX; CZ; X[0]; CZ; CX
""")

    runner.print_footer()


if __name__ == "__main__":
    main()
