#!/usr/bin/env python3
"""QSwitch as a Higher-Order Combinator

This demo shows QSwitch as a parametric combinator that takes two single-qubit
operations f, g and produces a circuit that applies them in different orders
depending on a control qubit.

    QSwitch : (Q → Q) → (Q → Q) → (Q ⊗ Q → Q ⊗ Q)

    QSwitch f g (ctrl, tgt) =
        | ctrl = |0⟩  →  (f ; g)(tgt)
        | ctrl = |1⟩  →  (g ; f)(tgt)
        | superposition → coherent combination

Run with: PYTHONPATH=src python demos/qswitch_higher_order_demo.py
"""

import sys
from pathlib import Path
from typing import Callable, Tuple

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from lang.terms import (
    Term, Seq, H, S, X, Z,
    CH, CS, CX, CZ,
)
from lang.types import Q, Ten, Ty
from compile.to_pytket import compile


def section(title: str) -> None:
    print()
    print("=" * 74)
    print(f"  {title}")
    print("=" * 74)
    print()


# =============================================================================
# Gate lifting: single-qubit gate → controlled gate
# =============================================================================

# Map from single-qubit gates to their controlled versions
CONTROLLED_GATES = {
    'H': CH,
    'S': CS,
    'X': CX,
    'Z': CZ,
}


def controlled_version(gate_name: str):
    """Get the controlled version of a gate.

    H  → CH
    S  → CS
    T  → CT
    X  → CX
    etc.
    """
    if gate_name not in CONTROLLED_GATES:
        raise ValueError(f"No controlled version for gate: {gate_name}")
    return CONTROLLED_GATES[gate_name]


# =============================================================================
# QSwitch combinator
# =============================================================================

def QSwitch(f_name: str, g_name: str, ty: Ty) -> Term:
    """QSwitch : (Q→Q) → (Q→Q) → (Q⊗Q → Q⊗Q)

    Takes two single-qubit gate names and produces a circuit that:
    - When ctrl=|0⟩: applies f then g to target
    - When ctrl=|1⟩: applies g then f to target
    - On superposition: coherent combination

    The circuit uses the anti-control pattern:
        X[ctrl]; C-f[ctrl,tgt]; C-g[ctrl,tgt]; X[ctrl]; C-g[ctrl,tgt]; C-f[ctrl,tgt]

    Wire layout: [ctrl=0, tgt=1]
    """
    Cf = controlled_version(f_name)
    Cg = controlled_version(g_name)

    return Seq(
        X(0, ty),         # flip ctrl for anti-control
        Cf(0, 1, ty),     # C-f (left branch, part 1)
        Cg(0, 1, ty),     # C-g (left branch, part 2)
        X(0, ty),         # restore ctrl
        Cg(0, 1, ty),     # C-g (right branch, part 1)
        Cf(0, 1, ty),     # C-f (right branch, part 2)
    )


def QSwitch_curried(f_name: str):
    """Partial application: QSwitch(f) returns a function waiting for g.

    QSwitch : (Q→Q) → ((Q→Q) → (Q⊗Q → Q⊗Q))
    QSwitch f : (Q→Q) → (Q⊗Q → Q⊗Q)
    """
    def with_g(g_name: str, ty: Ty) -> Term:
        return QSwitch(f_name, g_name, ty)
    return with_g


# =============================================================================
# Main demo
# =============================================================================

def main():
    section("QUANTUM SWITCH AS A HIGHER-ORDER COMBINATOR")

    print("""
TYPE SIGNATURE:

    QSwitch : (Q → Q) → (Q → Q) → (Q ⊗ Q → Q ⊗ Q)

In curried form:

    QSwitch : (Q → Q) → ((Q → Q) → (Q ⊗ Q → Q ⊗ Q))

SEMANTICS:

    QSwitch f g (ctrl, tgt) =
        | ctrl = |0⟩  →  (f ; g)(tgt)      -- f then g
        | ctrl = |1⟩  →  (g ; f)(tgt)      -- g then f
        | α|0⟩ + β|1⟩ →  α|0⟩(f;g)|ψ⟩ + β|1⟩(g;f)|ψ⟩   -- superposition!

The quantum switch applies two operations in BOTH ORDERS simultaneously
when the control qubit is in superposition.
""")

    # =========================================================================
    section("1. QSwitch as a combinator (before instantiation)")
    # =========================================================================

    print("""
QSwitch is a higher-order function that takes two operations and returns
a quantum circuit. Before we give it concrete gates, it's just a recipe:

    QSwitch : (Q → Q) → (Q → Q) → (Q ⊗ Q → Q ⊗ Q)

    QSwitch f g = λ(ctrl, tgt).
        case ctrl of
            | |0⟩ → (f ; g)(tgt)
            | |1⟩ → (g ; f)(tgt)

IMPLEMENTATION via controlled gates:

    QSwitch f g = X[0] ; C-f[0,1] ; C-g[0,1] ; X[0] ; C-g[0,1] ; C-f[0,1]
                  ───────────────────────────   ─────────────────────────
                        anti-ctrl (f;g)               ctrl (g;f)
                     fires when ctrl=|0⟩           fires when ctrl=|1⟩
""")

    # =========================================================================
    section("2. Partial application: QSwitch(H)")
    # =========================================================================

    print("""
Apply QSwitch to just the first argument:

    QSwitch H : (Q → Q) → (Q ⊗ Q → Q ⊗ Q)

This is still a function waiting for the second operation g.
It "remembers" that f = H and will apply H in both branches.

Conceptually:

    QSwitch H = λg. λ(ctrl, tgt).
        case ctrl of
            | |0⟩ → (H ; g)(tgt)
            | |1⟩ → (g ; H)(tgt)
""")

    qswitch_H = QSwitch_curried('H')
    print(f"qswitch_H = QSwitch('H')  -- partially applied")
    print(f"qswitch_H : (Q → Q) → (Q ⊗ Q → Q ⊗ Q)")

    # =========================================================================
    section("3. Full application: QSwitch(H)(S)")
    # =========================================================================

    print("""
Apply the second argument:

    QSwitch H S : Q ⊗ Q → Q ⊗ Q

Now we have a concrete circuit:
    - When ctrl=|0⟩: apply H then S to target
    - When ctrl=|1⟩: apply S then H to target
""")

    ty = Ten(Q(), Q())
    qswitch_HS = qswitch_H('S', ty)

    print(f"QSwitch H S : Q ⊗ Q → Q ⊗ Q")
    print()
    print(f"Term: {qswitch_HS}")

    # =========================================================================
    section("4. Compiled circuit")
    # =========================================================================

    result = compile(qswitch_HS)

    print(f"Qubits: {result.circuit.n_qubits}")
    print(f"Gates:  {result.circuit.n_gates}")
    print()
    print("Commands:")
    for cmd in result.circuit.get_commands():
        print(f"  {cmd}")

    print("""
Circuit diagram:

  q[0] ──X───●───●───X───●───●──
            │   │       │   │
  q[1] ────CH──CS──────CS──CH──

Trace:
  - X[0] flips ctrl
  - CH[0,1]; CS[0,1] = controlled H;S (fires when ctrl now |1⟩, was |0⟩)
  - X[0] restores ctrl
  - CS[0,1]; CH[0,1] = controlled S;H (fires when ctrl is |1⟩)
""")

    # =========================================================================
    section("5. Other instantiations")
    # =========================================================================

    print("QSwitch is parametric — we can instantiate with different gates:\n")

    examples = [
        ('H', 'S', "Hadamard and S-gate"),
        ('X', 'Z', "Pauli X and Z"),
        ('H', 'X', "Hadamard and Pauli X"),
    ]

    for f, g, desc in examples:
        term = QSwitch(f, g, ty)
        result = compile(term)
        cmds = [str(cmd).split()[0] for cmd in result.circuit.get_commands()]
        print(f"  QSwitch({f}, {g}): {desc}")
        print(f"    Gates: {' → '.join(cmds)}")
        print()

    # =========================================================================
    section("6. Summary")
    # =========================================================================

    print("""
┌──────────────────────────────────────────────────────────────────────────┐
│  QSWITCH AS A HIGHER-ORDER COMBINATOR                                    │
├──────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  Type:    QSwitch : (Q→Q) → (Q→Q) → (Q⊗Q → Q⊗Q)                         │
│                                                                          │
│  Partial: QSwitch H : (Q→Q) → (Q⊗Q → Q⊗Q)      -- waiting for g         │
│                                                                          │
│  Full:    QSwitch H S : Q⊗Q → Q⊗Q              -- concrete circuit      │
│                                                                          │
│  Circuit: X[0]; CH[0,1]; CS[0,1]; X[0]; CS[0,1]; CH[0,1]                │
│                                                                          │
├──────────────────────────────────────────────────────────────────────────┤
│  KEY INSIGHT: Higher-order quantum programming!                          │
│                                                                          │
│  QSwitch takes FUNCTIONS as arguments and produces a circuit that        │
│  applies them in superposition of different orders.                      │
│                                                                          │
│  This is impossible classically — you can only apply f-then-g OR         │
│  g-then-f, not both simultaneously.                                      │
└──────────────────────────────────────────────────────────────────────────┘
""")


if __name__ == "__main__":
    main()
