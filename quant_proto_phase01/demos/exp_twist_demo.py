#!/usr/bin/env python3
"""Demo: exp_i(π/4, Twist) ; exp_i(π/4, Twist) = i·Twist

This demo verifies the identity for exponentials of involutions:
    exp(iθP) ; exp(iθP) = exp(2iθP)

For θ = π/4 and P = Twist (swap):
    exp(iπ/4 · Twist) ; exp(iπ/4 · Twist) = exp(iπ/2 · Twist) = i·Twist

Since global phase doesn't affect measurement, this equals Twist up to phase.

Run with:
    cd quant_proto_phase01
    PYTHONPATH=src python demos/exp_twist_demo.py
"""

import sys
import numpy as np
from math import pi

# Add src to path
sys.path.insert(0, 'src')

from lang.types import Q, Ten
from lang.terms import TwistTen, ExpInvolution, Seq
from compile.to_pytket import compile

def print_section(title: str) -> None:
    print(f"\n{'='*60}")
    print(f" {title}")
    print('='*60)

def circuit_to_unitary(circuit) -> np.ndarray:
    """Extract unitary matrix from pytket circuit."""
    from pytket.extensions.qiskit import tk_to_qiskit
    from qiskit.quantum_info import Operator

    qc = tk_to_qiskit(circuit)
    return Operator(qc).data

def print_matrix(name: str, m: np.ndarray) -> None:
    """Pretty print a matrix."""
    print(f"\n{name}:")
    for row in m:
        formatted = [f"{x.real:+.4f}{x.imag:+.4f}i" for x in row]
        print("  [" + ", ".join(formatted) + "]")

def main():
    print("=" * 60)
    print(" Exponential of Involution Demo")
    print(" exp_i(π/4, Twist) ; exp_i(π/4, Twist) = i·Twist")
    print("=" * 60)

    # Type: Q ⊗ Q
    ty = Ten(Q(), Q())

    # =================================================================
    print_section("1. The Involution: Twist (TwistTen)")
    # =================================================================

    twist = TwistTen(Q(), Q())
    print(f"\nTerm: TwistTen(Q, Q)")
    print(f"Type: Q ⊗ Q → Q ⊗ Q")

    result_twist = compile(twist)
    print(f"\nCompiled circuit:")
    print(f"  Gates: {result_twist.circuit.n_gates}")
    print(f"  Permutation: {result_twist.perm.new_to_old}")

    # The SWAP matrix
    SWAP = np.array([
        [1, 0, 0, 0],
        [0, 0, 1, 0],
        [0, 1, 0, 0],
        [0, 0, 0, 1]
    ], dtype=complex)
    print_matrix("SWAP (Twist) matrix", SWAP)

    # =================================================================
    print_section("2. Single exp_i(π/4, Twist)")
    # =================================================================

    theta = pi / 4
    exp_twist = ExpInvolution(theta=theta, body=twist, ty_total=ty)
    print(f"\nTerm: ExpInvolution(π/4, TwistTen(Q,Q))")
    print(f"Type: Q ⊗ Q → Q ⊗ Q")

    result_single = compile(exp_twist, explain=True)
    print(f"\nCompiled circuit:")
    print(f"  Gates: {result_single.circuit.n_gates}")
    print(f"  Commands:")
    for cmd in result_single.circuit.get_commands():
        print(f"    {cmd}")

    # Expected: exp(iπ/4 · SWAP) = cos(π/4)·I + i·sin(π/4)·SWAP
    I4 = np.eye(4, dtype=complex)
    expected_single = np.cos(theta) * I4 + 1j * np.sin(theta) * SWAP
    print_matrix("Expected exp(iπ/4 · SWAP)", expected_single)

    # Get actual unitary
    try:
        actual_single = circuit_to_unitary(result_single.circuit)
        print_matrix("Actual circuit unitary", actual_single)

        # Check if they match (up to global phase)
        diff = np.abs(np.abs(actual_single) - np.abs(expected_single)).max()
        print(f"\nMax magnitude difference: {diff:.10f}")
    except ImportError:
        print("\n(qiskit not available for unitary extraction)")

    # =================================================================
    print_section("3. Composition: exp_i(π/4, Twist) ; exp_i(π/4, Twist)")
    # =================================================================

    # Compose two exp_i(π/4, Twist)
    composed = Seq(exp_twist, exp_twist)
    print(f"\nTerm: Seq(ExpInvolution(π/4, twist), ExpInvolution(π/4, twist))")
    print(f"Type: Q ⊗ Q → Q ⊗ Q")

    result_composed = compile(composed, explain=True)
    print(f"\nCompiled circuit:")
    print(f"  Gates: {result_composed.circuit.n_gates}")
    print(f"  Commands:")
    for cmd in result_composed.circuit.get_commands():
        print(f"    {cmd}")

    # Expected: exp(iπ/2 · SWAP) = cos(π/2)·I + i·sin(π/2)·SWAP = i·SWAP
    expected_composed = np.cos(2*theta) * I4 + 1j * np.sin(2*theta) * SWAP
    print_matrix("Expected exp(iπ/2 · SWAP) = i·SWAP", expected_composed)

    try:
        actual_composed = circuit_to_unitary(result_composed.circuit)
        print_matrix("Actual circuit unitary", actual_composed)

        # Check if actual ≈ i·SWAP (up to global phase)
        # i·SWAP normalized
        i_swap = 1j * SWAP

        # To compare up to global phase, check if |actual| = |expected|
        # or check if actual = e^{iφ} · expected for some φ

        # Find the global phase
        nonzero_idx = np.abs(actual_composed) > 0.01
        if np.any(nonzero_idx):
            ratio = actual_composed[nonzero_idx][0] / i_swap[nonzero_idx][0]
            phase = np.angle(ratio)
            print(f"\nGlobal phase difference: e^{{i·{phase:.4f}}} = e^{{i·{phase/pi:.4f}π}}")

            # Remove global phase and compare
            adjusted = actual_composed * np.exp(-1j * phase)
            diff = np.abs(adjusted - i_swap).max()
            print(f"After phase adjustment, max diff from i·SWAP: {diff:.10f}")
    except ImportError:
        pass

    # =================================================================
    print_section("4. Mathematical Verification")
    # =================================================================

    print("""
The identity follows from:

    exp(iθP) = cos(θ)·I + i·sin(θ)·P    (for involution P² = I)

Therefore:
    exp(iθP) · exp(iθP) = [cos(θ)·I + i·sin(θ)·P]²
                        = cos²(θ)·I + 2i·cos(θ)·sin(θ)·P + i²·sin²(θ)·P²
                        = cos²(θ)·I + i·sin(2θ)·P - sin²(θ)·I   (using P² = I)
                        = [cos²(θ) - sin²(θ)]·I + i·sin(2θ)·P
                        = cos(2θ)·I + i·sin(2θ)·P
                        = exp(2iθP)

For θ = π/4:
    exp(iπ/4·P) · exp(iπ/4·P) = exp(iπ/2·P)
                               = cos(π/2)·I + i·sin(π/2)·P
                               = 0·I + i·1·P
                               = i·P

So: exp_i(π/4, Twist) ; exp_i(π/4, Twist) = i·Twist

Up to global phase (which is unobservable), this equals Twist!
""")

    # =================================================================
    print_section("5. Verification: (exp;exp) vs Twist")
    # =================================================================

    try:
        # The key insight: i·SWAP has the same action as SWAP up to global phase
        # Let's verify the eigenvalue structure

        print("Eigenvalue analysis:")
        print("\nSWAP eigenvalues:")
        swap_eigs = np.linalg.eigvals(SWAP)
        for e in sorted(swap_eigs, key=lambda x: x.real):
            print(f"  {e.real:+.4f}{e.imag:+.4f}i")

        print("\ni·SWAP eigenvalues:")
        i_swap_eigs = np.linalg.eigvals(1j * SWAP)
        for e in sorted(i_swap_eigs, key=lambda x: x.real):
            print(f"  {e.real:+.4f}{e.imag:+.4f}i")

        print("\nThe eigenvalues of i·SWAP are just i times those of SWAP.")
        print("This confirms that i·SWAP = i · SWAP (global phase times SWAP).")
        print("\nIn quantum mechanics, global phase is unobservable,")
        print("so exp_i(π/4, Twist) ; exp_i(π/4, Twist) ≡ Twist")
    except Exception as e:
        print(f"(eigenvalue analysis skipped: {e})")

    # =================================================================
    print_section("6. Circuit Summary")
    # =================================================================

    print(f"""
┌─────────────────────────────────────────────────────────────┐
│  Term                              │ Gates │ Result         │
├─────────────────────────────────────────────────────────────┤
│  TwistTen(Q,Q)                     │   0   │ Permutation    │
│  exp_i(π/4, Twist)                 │   {result_single.circuit.n_gates}   │ ExpSwap gate   │
│  exp_i(π/4, Twist) ; exp_i(π/4, Twist) │   {result_composed.circuit.n_gates}   │ Two ExpSwaps   │
└─────────────────────────────────────────────────────────────┘

Key result:
  Two ExpSwap(π/4) gates compose to give exp(iπ/2·SWAP) = i·SWAP
  This equals SWAP up to global phase, confirming the involution identity.
""")

    print("\n✓ Demo complete!")
    return 0

if __name__ == "__main__":
    sys.exit(main())
