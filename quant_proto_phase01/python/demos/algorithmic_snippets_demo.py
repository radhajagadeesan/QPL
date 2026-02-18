#!/usr/bin/env python3
"""Demo: Algorithmic Snippets from Surface Language

This demo compiles the examples from ocaml/demos/algorithmic_snippets.ml
and verifies they produce the expected circuits.

Examples:
1. twoQubitCircuit: H[0] ; CX[0,1] ; H[0]
2. bellState: H[0] ; CX[0,1]
3. ghzState: H[0] ; CX[0,1] ; CX[0,2]
4. swap (via TwistPlus): swaps Bool constructors

Usage:
    python algorithmic_snippets_demo.py              # Run demo
    python algorithmic_snippets_demo.py --circuits   # Show circuit diagrams
"""

import sys
from pathlib import Path

# Add src to path
src_path = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_path))

from lang.types import Q, Ten, Plus, Unit, width
from lang.terms import Id, Seq, H, S, CX, TwistPlus
from typing_.check import type_of
import numpy as np

from demo_utils import DemoRunner

# Global runner instance
runner = None


def get_unitary(result):
    """Extract unitary matrix from compiled circuit."""
    return result.circuit.get_unitary()


def demo_two_qubit_circuit():
    """Demo 1: twoQubitCircuit = H[0] ; CX[0,1] ; H[0]

    From algorithmic_snippets.surf:
        def twoQubitCircuit : (Q ⊗ Q) → (Q ⊗ Q) =
          H[0] ; CX[0,1] ; H[0]
    """
    print("\n" + "="*60)
    print("Demo 1: twoQubitCircuit")
    print("="*60)
    print("\nSurface syntax: H[0] ; CX[0,1] ; H[0]")

    ty = Ten(Q(), Q())  # Q ⊗ Q

    # Build: H[0] ; CX[0,1] ; H[0]
    term = Seq(H(0, ty), Seq(CX(0, 1, ty), H(0, ty)))

    dom, cod = type_of(term)
    print(f"Type: {dom} → {cod}")
    print(f"  width = {width(dom)}")

    result = runner.compile(term, "twoQubitCircuit")
    runner.print_circuit_details(result, "Compiled Circuit")
    runner.show_circuit(result, "twoQubitCircuit")

    # Verify: 3 gates (H, CX, H)
    assert result.circuit.n_gates == 3, f"Expected 3 gates, got {result.circuit.n_gates}"
    print("\n✓ Verified: 3 gates (H, CX, H)")

    # Get and display unitary
    U = get_unitary(result)
    print("\nUnitary matrix (showing |00⟩, |01⟩, |10⟩, |11⟩ columns):")
    print(np.round(U, 3))

    return result


def demo_bell_state():
    """Demo 2: bellState = H[0] ; CX[0,1]

    From algorithmic_snippets.surf:
        def bellState : (Q ⊗ Q) → (Q ⊗ Q) =
          H[0] ; CX[0,1]

    Creates entanglement: |00⟩ → (|00⟩ + |11⟩)/√2
    """
    print("\n" + "="*60)
    print("Demo 2: bellState (Bell State Preparation)")
    print("="*60)
    print("\nSurface syntax: H[0] ; CX[0,1]")

    ty = Ten(Q(), Q())

    # Build: H[0] ; CX[0,1]
    term = Seq(H(0, ty), CX(0, 1, ty))

    dom, cod = type_of(term)
    print(f"Type: {dom} → {cod}")

    result = runner.compile(term, "bellState")
    runner.print_circuit_details(result, "Compiled Circuit")
    runner.show_circuit(result, "bellState")

    # Verify: 2 gates
    assert result.circuit.n_gates == 2
    print("\n✓ Verified: 2 gates (H, CX)")

    # Get unitary and verify Bell state creation
    U = get_unitary(result)
    print("\nUnitary matrix:")
    print(np.round(U, 3))

    # |00⟩ column should be (1/√2)[1, 0, 0, 1]
    col_00 = U[:, 0]
    expected = np.array([1, 0, 0, 1]) / np.sqrt(2)
    assert np.allclose(np.abs(col_00), np.abs(expected)), "Bell state not correct"
    print("\n✓ Verified: |00⟩ → (|00⟩ + |11⟩)/√2")

    return result


def demo_ghz_state():
    """Demo 3: ghzState = H[0] ; CX[0,1] ; CX[0,2]

    From algorithmic_snippets.surf:
        def ghzState : (Q ⊗ Q ⊗ Q) → (Q ⊗ Q ⊗ Q) =
          H[0] ; CX[0,1] ; CX[0,2]

    Creates GHZ state: |000⟩ → (|000⟩ + |111⟩)/√2
    """
    print("\n" + "="*60)
    print("Demo 3: ghzState (GHZ State Preparation)")
    print("="*60)
    print("\nSurface syntax: H[0] ; CX[0,1] ; CX[0,2]")

    ty = Ten(Q(), Ten(Q(), Q()))  # Q ⊗ (Q ⊗ Q)

    # Build: H[0] ; CX[0,1] ; CX[0,2]
    term = Seq(H(0, ty), Seq(CX(0, 1, ty), CX(0, 2, ty)))

    dom, cod = type_of(term)
    print(f"Type: {dom} → {cod}")
    print(f"  width = {width(dom)}")

    result = runner.compile(term, "ghzState")
    runner.print_circuit_details(result, "Compiled Circuit")
    runner.show_circuit(result, "ghzState")

    # Verify: 3 gates
    assert result.circuit.n_gates == 3
    print("\n✓ Verified: 3 gates (H, CX, CX)")

    # Get unitary
    U = get_unitary(result)
    print("\nUnitary matrix (8x8, showing first 4 columns):")
    print(np.round(U[:, :4], 3))

    # |000⟩ column should be (1/√2)[1, 0, 0, 0, 0, 0, 0, 1]
    col_000 = U[:, 0]
    expected = np.zeros(8)
    expected[0] = 1 / np.sqrt(2)
    expected[7] = 1 / np.sqrt(2)
    assert np.allclose(np.abs(col_000), np.abs(expected)), "GHZ state not correct"
    print("\n✓ Verified: |000⟩ → (|000⟩ + |111⟩)/√2")

    return result


def demo_swap_structural():
    """Demo 4: swap (structural) via TwistPlus

    From algorithmic_snippets.surf:
        def swap : Bool['a, 'b] → Bool['b, 'a] =
          λx. case x of
            | F(a) => T(a)
            | T(b) => F(b)

    This elaborates to TwistPlus(A, B).
    With Q+Q, it swaps the two summands by flipping the tag.
    """
    print("\n" + "="*60)
    print("Demo 4: swap (TwistPlus - Structural)")
    print("="*60)
    print("\nSurface syntax:")
    print("  def swap : Bool['a, 'b] → Bool['b, 'a] =")
    print("    λx. case x of F(a) => T(a) | T(b) => F(b)")
    print("\nElaborates to: TwistPlus(Q, Q)")

    ty_q = Q()
    twist = TwistPlus(ty_q, ty_q)

    dom, cod = type_of(twist)
    print(f"\nType: {dom} → {cod}")
    print(f"  width = {width(dom)}")

    result = runner.compile(twist, "TwistPlus")
    runner.print_circuit_details(result, "Compiled Circuit")
    runner.show_circuit(result, "TwistPlus")

    # TwistPlus emits X gate for tag flip
    cmds = list(result.circuit.get_commands())
    gate_names = [cmd.op.type.name for cmd in cmds]
    assert gate_names == ['X'], f"Expected [X], got {gate_names}"
    print("\n✓ Verified: 1 X gate (tag flip)")

    # Get unitary - should be X ⊗ I (tag flipped, payload unchanged)
    U = get_unitary(result)
    print("\nUnitary matrix:")
    print(np.round(U, 3))

    # X ⊗ I swaps |0x⟩ ↔ |1x⟩
    expected = np.array([
        [0, 0, 1, 0],
        [0, 0, 0, 1],
        [1, 0, 0, 0],
        [0, 1, 0, 0]
    ])
    assert np.allclose(U, expected), "TwistPlus unitary incorrect"
    print("\n✓ Verified: U = X ⊗ I (swaps tag, preserves payload)")

    return result


def demo_swap_twice():
    """Demo 5: swapTwice = swap ; swap = Id

    From algorithmic_snippets.surf:
        def swapTwice : Bool['a, 'b] → Bool['a, 'b] =
          swap ; swap

    TwistPlus is an involution: twist ; twist = Id
    """
    print("\n" + "="*60)
    print("Demo 5: swapTwice = swap ; swap (Involution)")
    print("="*60)
    print("\nSurface syntax: swap ; swap")
    print("Expected: Identity (X ; X = I)")

    ty_q = Q()
    twist = TwistPlus(ty_q, ty_q)
    swap_twice = Seq(twist, twist)

    dom, cod = type_of(swap_twice)
    print(f"\nType: {dom} → {cod}")

    result = runner.compile(swap_twice, "swapTwice")
    runner.print_circuit_details(result, "Compiled Circuit")
    runner.show_circuit(result, "swapTwice")

    # Two X gates
    cmds = list(result.circuit.get_commands())
    assert len(cmds) == 2
    print("\n✓ Emitted 2 X gates (X ; X = I)")

    # Get unitary - should be identity
    U = get_unitary(result)
    print("\nUnitary matrix:")
    print(np.round(U, 3))

    assert np.allclose(U, np.eye(4)), "swapTwice should be identity"
    print("\n✓ Verified: U = I (involution property)")

    return result


def main():
    global runner
    runner = DemoRunner(
        "Algorithmic Snippets Demo",
        "Compiles examples from ocaml/demos/algorithmic_snippets.ml"
    )
    runner.print_header()
    print("\nCompiling examples from ocaml/demos/algorithmic_snippets.ml")

    demo_two_qubit_circuit()
    demo_bell_state()
    demo_ghz_state()
    demo_swap_structural()
    demo_swap_twice()

    print("\n" + "="*60)
    print("All algorithmic snippets verified!")
    print("="*60)

    runner.print_footer()


if __name__ == "__main__":
    main()
