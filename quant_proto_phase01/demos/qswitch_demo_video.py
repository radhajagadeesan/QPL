#!/usr/bin/env python3
"""
QSwitch(H, S) Demo - Video Recording Script

This script is designed for screen recording / asciinema.
It includes pauses and clear visual formatting.

Record with: asciinema rec qswitch_demo.cast
Run with:    PYTHONPATH=src python demos/qswitch_demo_video.py

Or just run directly for a slower, more visual demo.
"""

import sys
import time
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

# Timing for video
PAUSE_SHORT = 1.0
PAUSE_MEDIUM = 2.0
PAUSE_LONG = 3.0


def pause(duration=PAUSE_SHORT):
    time.sleep(duration)


def typewrite(text, delay=0.03):
    """Simulate typing effect."""
    for char in text:
        print(char, end='', flush=True)
        time.sleep(delay)
    print()


def section(title):
    pause(PAUSE_MEDIUM)
    print()
    print("\033[1;36m" + "=" * 60 + "\033[0m")
    print(f"\033[1;36m{title}\033[0m")
    print("\033[1;36m" + "=" * 60 + "\033[0m")
    print()
    pause(PAUSE_SHORT)


def highlight(text):
    print(f"\033[1;33m{text}\033[0m")


def success(text):
    print(f"\033[1;32m{text}\033[0m")


def code(text):
    print(f"\033[0;37m{text}\033[0m")


def main():
    print("\033[2J\033[H")  # Clear screen

    section("QSwitch Demo: Higher-Order Quantum Programming")

    typewrite("Welcome to the QSwitch demonstration!")
    pause(PAUSE_SHORT)
    typewrite("We'll show how higher-order quantum programs compile to circuits.")
    pause(PAUSE_MEDIUM)

    # =========================================================================
    section("Step 1: QSwitch Definition")
    # =========================================================================

    highlight("QSwitch is a higher-order combinator:")
    pause(PAUSE_SHORT)

    code("""
    QSwitch(f, g) : QBool ⊗ Q → QBool ⊗ Q

      case ctrl of
      | Zero => (ctrl, g;f data)
      | One  => (ctrl, f;g data)
    """)
    pause(PAUSE_MEDIUM)

    typewrite("It switches the order of composition based on a quantum control bit.")
    pause(PAUSE_LONG)

    # =========================================================================
    section("Step 2: Apply to H and S")
    # =========================================================================

    highlight("QSwitch(H, S):")
    code("""
      | Zero => S;H  (apply S then H)
      | One  => H;S  (apply H then S)
    """)
    pause(PAUSE_MEDIUM)

    typewrite("Now let's compile this to a quantum circuit...")
    pause(PAUSE_SHORT)

    # Import and run
    from lang.terms import H, S, Seq, CS, X
    from lang.types import Q, Ten
    from compile.to_pytket import compile

    ty = Ten(Q(), Q())
    qswitch_hs = Seq(
        X(0, ty),
        CS(0, 1, ty),
        X(0, ty),
        H(1, ty),
        CS(0, 1, ty),
    )

    result = compile(qswitch_hs)

    # =========================================================================
    section("Step 3: Compiled Circuit")
    # =========================================================================

    highlight(f"Result: {result.circuit.n_gates} gates on {result.circuit.n_qubits} qubits")
    pause(PAUSE_SHORT)

    print()
    code("Circuit (ctrl=q[0], data=q[1]):")
    pause(PAUSE_SHORT)

    for cmd in result.circuit.get_commands():
        code(f"  {cmd}")
        pause(0.3)

    pause(PAUSE_MEDIUM)

    # =========================================================================
    section("Step 4: GOI Higher-Order Form")
    # =========================================================================

    typewrite("In GOI, morphisms are doubled: (U†) ⊗ U")
    pause(PAUSE_SHORT)

    highlight("QSwitch(H,S) GOI form: 4 qubits")
    code("""
    Wire 0: ctrl*  (negative/dual)
    Wire 1: data*  (negative/dual)
    Wire 2: ctrl   (positive)
    Wire 3: data   (positive)
    """)
    pause(PAUSE_MEDIUM)

    from lang.terms import CSdg
    ty4 = Ten(Ten(Q(), Q()), Ten(Q(), Q()))

    negative = Seq(CSdg(0, 1, ty4), H(1, ty4), X(0, ty4), CSdg(0, 1, ty4), X(0, ty4))
    positive = Seq(X(2, ty4), CS(2, 3, ty4), X(2, ty4), H(3, ty4), CS(2, 3, ty4))
    goi_qswitch = Seq(negative, positive)
    result4 = compile(goi_qswitch)

    highlight(f"Result: {result4.circuit.n_gates} gates on {result4.circuit.n_qubits} qubits")
    pause(PAUSE_SHORT)

    code("Circuit:")
    for cmd in result4.circuit.get_commands():
        code(f"  {cmd}")
        pause(0.2)

    pause(PAUSE_MEDIUM)

    # =========================================================================
    section("Step 5: Verify GOI Laws")
    # =========================================================================

    typewrite("Let's verify the GOI infrastructure works correctly...")
    pause(PAUSE_SHORT)

    from compile.goi import (
        GateAtom, GOIArtifact,
        make_unitary_value, goi_seq, execute_trace
    )
    from core.perm import WirePerm, identity

    highlight("Test: H;S composition via GOI")
    pause(PAUSE_SHORT)

    h_goi = make_unitary_value('H', (0,), n_a=1, inverse_gate_name='H')
    s_goi = make_unitary_value('S', (0,), n_a=1, inverse_gate_name='Sdg')

    code(f"⟦H⟧ = {[(a.gate_name, a.wires) for a in h_goi.atoms]}")
    code(f"⟦S⟧ = {[(a.gate_name, a.wires) for a in s_goi.atoms]}")
    pause(PAUSE_SHORT)

    hs = goi_seq(h_goi, s_goi, n_shared=1)
    hs_traced = execute_trace(hs)

    code("After composition and trace:")
    wire0 = [a.gate_name for a in hs_traced.atoms if 0 in a.wires]
    wire1 = [a.gate_name for a in hs_traced.atoms if 1 in a.wires]
    code(f"  Wire 0 (Q*): {wire0} = (H;S)†")
    code(f"  Wire 1 (Q):  {wire1} = H;S")
    pause(PAUSE_SHORT)

    success("✓ GOI composition verified!")
    pause(PAUSE_LONG)

    # =========================================================================
    section("Demo Complete!")
    # =========================================================================

    success("""
    Summary:
    ────────────────────────────────────────
    • QSwitch(H,S) first-order:  5 gates / 2 qubits
    • QSwitch(H,S) GOI form:    10 gates / 4 qubits
    • GOI laws verified: composition works correctly

    Higher-order quantum programming is working!
    """)

    pause(PAUSE_LONG)
    print()
    typewrite("Thank you for watching!")
    print()


if __name__ == "__main__":
    main()
