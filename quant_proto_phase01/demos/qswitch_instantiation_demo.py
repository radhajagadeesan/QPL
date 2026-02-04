#!/usr/bin/env python3
"""QSwitch Instantiation Demo — Compositional Construction

Shows QSwitch built COMPOSITIONALLY:
1. Abstract QSwitch structure (parameterized over f and g)
2. Concrete gates H and S
3. Instantiation by plugging H, S into the abstract structure

The key insight: the final circuit is built by COMPOSING the abstract
QSwitch combinator with concrete gate terms, not by directly embedding
the gates.

Prerequisites: See qswitch_abstract_circuit_theory_demo.py for the abstract structure.

Usage:
    python qswitch_instantiation_demo.py              # Run demo
    python qswitch_instantiation_demo.py --circuits   # Show circuit diagrams
"""

import sys
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from lang.types import Q, Unit, Ten, Plus, Arrow, width
from lang.terms import Id, Seq, TenTerm, Case, DistL, H, S
from typing_.check import type_of

from demo_utils import DemoRunner

# Global runner instance
runner = None


# =============================================================================
# COMPOSITIONAL QSWITCH CONSTRUCTION
# =============================================================================

def make_qswitch(f_term, g_term):
    """Build QSwitch[f, g] compositionally from abstract structure + concrete gates.

    This is the KEY function demonstrating compositional construction:
    - The QSwitch STRUCTURE is fixed (DistL ; Case with anti-control pattern)
    - The GATES f and g are parameters that get plugged in

    Args:
        f_term: A term of type Q → Q (first function)
        g_term: A term of type Q → Q (second function)

    Returns:
        A term of type (Bool ⊗ Q) → (Bool ⊗ Q)

    Semantics:
        |0⟩|ψ⟩  →  |0⟩ f(g(ψ))     (apply g then f)
        |1⟩|ψ⟩  →  |1⟩ g(f(ψ))     (apply f then g)
    """
    I = Unit()
    IQ = Ten(I, Q())

    # ─────────────────────────────────────────────────────────────────────────
    # ABSTRACT STRUCTURE: The QSwitch combinator shape
    # ─────────────────────────────────────────────────────────────────────────

    # Left branch (ctrl = |0⟩): apply g then f
    # TenTerm(Id(I), gate) applies gate to the Q part, leaving I unchanged
    left_branch = Seq(
        TenTerm(Id(I), g_term),  # g on Q part
        TenTerm(Id(I), f_term)   # then f on Q part
    )

    # Right branch (ctrl = |1⟩): apply f then g
    right_branch = Seq(
        TenTerm(Id(I), f_term),  # f on Q part
        TenTerm(Id(I), g_term)   # then g on Q part
    )

    # Case combines branches with anti-control pattern
    case_body = Case(IQ, IQ, left_branch, right_branch)

    # Distribution: Bool ⊗ Q → (I⊗Q) + (I⊗Q)
    dist = DistL(I, I, Q())

    # Full QSwitch: DistL ; Case
    return Seq(dist, case_body)


def main():
    global runner
    runner = DemoRunner(
        "QSwitch Instantiation Demo",
        "Compositional construction: QSwitch[f,g] with f=H, g=S"
    )
    runner.print_header()

    # Type definitions
    I = Unit()
    Bool = Plus(I, I)
    IQ = Ten(I, Q())

    # =========================================================================
    # SECTION 1: COMPOSITIONAL CONSTRUCTION PRINCIPLE
    # =========================================================================
    print("\n" + "="*74)
    print("  SECTION 1: Compositional Construction")
    print("="*74 + "\n")

    print("""
KEY INSIGHT: QSwitch is built COMPOSITIONALLY
──────────────────────────────────────────────

The QSwitch circuit is NOT built by directly embedding gates.
Instead, it's built by COMPOSING:

  1. ABSTRACT STRUCTURE: The QSwitch combinator (fixed shape)
  2. CONCRETE GATES: The functions f and g (parameters)

ABSTRACT QSWITCH STRUCTURE:

    def make_qswitch(f, g):
        '''
        QSwitch = DistL ; Case(
            left  = (Id_I ⊗ g) ; (Id_I ⊗ f),   -- g then f
            right = (Id_I ⊗ f) ; (Id_I ⊗ g)    -- f then g
        )
        '''
        left_branch  = Seq(TenTerm(Id(I), g), TenTerm(Id(I), f))
        right_branch = Seq(TenTerm(Id(I), f), TenTerm(Id(I), g))
        return Seq(DistL, Case(left_branch, right_branch))

INSTANTIATION:

    QSwitch[H, S] = make_qswitch(H, S)

The circuit structure comes from the COMBINATOR.
The concrete behavior comes from the GATES.
""")

    # =========================================================================
    # SECTION 2: ABSTRACT QSWITCH TYPE
    # =========================================================================
    print("\n" + "="*74)
    print("  SECTION 2: Abstract QSwitch Type")
    print("="*74 + "\n")

    print("""
QSWITCH TYPE SIGNATURE:

    QSwitch : (Q → Q) → (Q → Q) → (Bool ⊗ Q) → (Bool ⊗ Q)
              ───────   ───────   ─────────────────────────
                 f         g           input → output

    Parameters:
      f : Q → Q    (first function, width 1)
      g : Q → Q    (second function, width 1)

    Input/Output: Bool ⊗ Q
      Wire 0: control qubit (Bool = I + I, width 1)
      Wire 1: target qubit (Q, width 1)
      Total width: 2

SEMANTICS:

    |0⟩|ψ⟩  →  |0⟩ f(g(ψ))     (g first, then f)
    |1⟩|ψ⟩  →  |1⟩ g(f(ψ))     (f first, then g)
    |+⟩|ψ⟩  →  superposition of both orders!
""")

    # Show that H and S are valid function terms
    H_term = H(0, Q())
    S_term = S(0, Q())

    print("CONCRETE GATE TERMS:")
    print(f"  H = H(0, Q())  :  {type_of(H_term)[0]} → {type_of(H_term)[1]}")
    print(f"  S = S(0, Q())  :  {type_of(S_term)[0]} → {type_of(S_term)[1]}")

    # =========================================================================
    # SECTION 3: QSwitch[H, H] — ONE FUNCTION
    # =========================================================================
    print("\n" + "="*74)
    print("  SECTION 3: QSwitch[H, H] — Same Function (f = g)")
    print("="*74 + "\n")

    print("""
SIMPLIFICATION ANALYSIS:

    When f = g, both branches compute the SAME thing:

        |0⟩|ψ⟩  →  |0⟩ f(f(ψ))
        |1⟩|ψ⟩  →  |1⟩ f(f(ψ))     ← IDENTICAL!

    The control qubit has NO EFFECT.

    For f = H:  H² = I (Hadamard is self-inverse)
    Therefore:  QSwitch[H, H] = Identity!


COMPOSITIONAL CONSTRUCTION:
""")

    # Build QSwitch[H, H] compositionally
    print("    qswitch_hh = make_qswitch(H, H)")
    qswitch_hh = make_qswitch(H_term, H_term)

    dom, cod = type_of(qswitch_hh)
    print(f"    Type: {dom} → ... (width {width(dom)})")

    result_hh = runner.compile(qswitch_hh, "QSwitch[H, H]", materialize=True)
    runner.print_circuit_details(result_hh, "Compiled Circuit")
    runner.show_circuit(result_hh, "QSwitch[H, H]")

    print("""
VERIFICATION:
""")
    # Verify it's identity
    u_hh = result_hh.circuit.get_unitary()
    is_identity = np.allclose(u_hh, np.eye(4), atol=1e-10)
    print(f"    Unitary equals identity matrix? {is_identity}")

    if is_identity:
        print("""
    CONFIRMED: QSwitch[H, H] = Identity

    The 6 gates completely cancel because H² = I.
    This demonstrates: when f = g, QSwitch degenerates.
""")

    # =========================================================================
    # SECTION 4: QSwitch[H, S] — TWO FUNCTIONS
    # =========================================================================
    print("\n" + "="*74)
    print("  SECTION 4: QSwitch[H, S] — Different Functions (f ≠ g)")
    print("="*74 + "\n")

    print("""
NON-COMMUTATIVITY CHECK:

    H ∘ S ≠ S ∘ H  (Hadamard and S-gate don't commute)

    Therefore the two branches produce DIFFERENT results:
        |0⟩|ψ⟩  →  |0⟩ H(S(ψ))     (S then H)
        |1⟩|ψ⟩  →  |1⟩ S(H(ψ))     (H then S)

    NO SIMPLIFICATION POSSIBLE — this is the true quantum switch!


COMPOSITIONAL CONSTRUCTION:
""")

    # Build QSwitch[H, S] compositionally
    print("    qswitch_hs = make_qswitch(H, S)")
    qswitch_hs = make_qswitch(H_term, S_term)

    dom, cod = type_of(qswitch_hs)
    print(f"    Type: {dom} → ... (width {width(dom)})")

    result_hs = runner.compile(qswitch_hs, "QSwitch[H, S]", materialize=True)
    runner.print_circuit_details(result_hs, "Compiled Circuit")
    runner.show_circuit(result_hs, "QSwitch[H, S]")

    print("""
CIRCUIT DERIVATION (from compositional structure):
──────────────────────────────────────────────────

The circuit comes from the QSwitch COMBINATOR structure:

    QSwitch = DistL ; Case(left, right)

    where Case compiles to anti-control pattern:
        X[ctrl] ; Controlled(left) ; X[ctrl] ; Controlled(right)

With f=H, g=S plugged in:

    left  = TenTerm(Id(I), S) ; TenTerm(Id(I), H)  →  CS ; CH
    right = TenTerm(Id(I), H) ; TenTerm(Id(I), S)  →  CH ; CS

Result:
    X[0] ; CS[0,1] ; CH[0,1] ; X[0] ; CH[0,1] ; CS[0,1]
    ────   ─────────────────   ────   ─────────────────
    flip   anti-controlled     flip   controlled
           (S;H branch)        back   (H;S branch)


EXECUTION TRACE:
────────────────

    Input |0⟩|ψ⟩ (left branch → S then H):
      X         →  |1⟩|ψ⟩
      CS        →  |1⟩ S|ψ⟩      (fires)
      CH        →  |1⟩ HS|ψ⟩     (fires)
      X         →  |0⟩ HS|ψ⟩
      CH, CS    →  (skip)
      Output: |0⟩ H(S|ψ⟩)   ✓

    Input |1⟩|ψ⟩ (right branch → H then S):
      X         →  |0⟩|ψ⟩
      CS, CH    →  (skip)
      X         →  |1⟩|ψ⟩
      CH        →  |1⟩ H|ψ⟩      (fires)
      CS        →  |1⟩ SH|ψ⟩     (fires)
      Output: |1⟩ S(H|ψ⟩)   ✓

    Input |+⟩|ψ⟩:
      BOTH branches execute coherently!
      Output: (|0⟩ H(S|ψ⟩) + |1⟩ S(H|ψ⟩)) / √2
      This is INDEFINITE CAUSAL ORDER!
""")

    # =========================================================================
    # SECTION 5: SUMMARY
    # =========================================================================
    print("\n" + "="*74)
    print("  SUMMARY: Compositional Construction")
    print("="*74 + "\n")

    print("""
COMPOSITIONAL CONSTRUCTION DEMONSTRATED
───────────────────────────────────────

    ┌─────────────────────────────────────────────────────────────────┐
    │                                                                 │
    │   ABSTRACT QSWITCH COMBINATOR                                   │
    │   ════════════════════════════                                  │
    │                                                                 │
    │   make_qswitch(f, g) =                                          │
    │       DistL ; Case(                                             │
    │           left  = (Id ⊗ g) ; (Id ⊗ f),                          │
    │           right = (Id ⊗ f) ; (Id ⊗ g)                           │
    │       )                                                         │
    │                                                                 │
    │   This structure is FIXED — it's the QSwitch combinator.        │
    │                                                                 │
    └─────────────────────────────────────────────────────────────────┘
                              │
                              │ plug in concrete gates
                              ▼
    ┌─────────────────────────────────────────────────────────────────┐
    │                                                                 │
    │   INSTANTIATION                                                 │
    │   ═════════════                                                 │
    │                                                                 │
    │   QSwitch[H, H] = make_qswitch(H, H)  →  Identity (H² = I)      │
    │   QSwitch[H, S] = make_qswitch(H, S)  →  6 gates, non-trivial   │
    │                                                                 │
    │   The circuit structure comes from COMPOSING:                   │
    │     • The abstract QSwitch combinator (provides shape)          │
    │     • The concrete gates H, S (provide behavior)                │
    │                                                                 │
    └─────────────────────────────────────────────────────────────────┘


KEY INSIGHT:

    The QSwitch circuit is built COMPOSITIONALLY:

        Circuit = Combinator(Structure) ∘ Gates(Behavior)

    NOT by directly embedding gates into a flat circuit.

    This is higher-order quantum programming:
    - QSwitch is a COMBINATOR that takes functions as arguments
    - H and S are FUNCTION TERMS that get composed in
    - The final circuit emerges from their composition
""")

    runner.print_footer()


if __name__ == "__main__":
    main()
