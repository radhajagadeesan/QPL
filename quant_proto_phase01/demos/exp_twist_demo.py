#!/usr/bin/env python3
"""Demo: exp_i(π/4, Twist) ; exp_i(π/4, Twist) = i·Twist

This is an INFRASTRUCTURE TEST that verifies the identity by:
1. Compiling the terms to circuits
2. Extracting actual unitaries from compiled circuits
3. Comparing them mathematically

Usage:
    python exp_twist_demo.py              # Run demo
    python exp_twist_demo.py --circuits   # Show circuit diagrams
"""

import sys
import numpy as np
from math import pi
from pathlib import Path

# Add src to path
src_path = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_path))

from lang.types import Q, Ten
from lang.terms import TwistTen, ExpInvolution, Seq

from demo_utils import DemoRunner

# Global runner instance
runner = None


def matrices_equal_up_to_phase(A: np.ndarray, B: np.ndarray, tol: float = 1e-10) -> tuple[bool, complex]:
    """Check if A = e^{iφ} · B for some phase φ.

    Returns (is_equal, phase_factor).
    """
    # Find first non-zero entry in B
    for i in range(B.shape[0]):
        for j in range(B.shape[1]):
            if np.abs(B[i, j]) > tol:
                # Compute phase from this entry
                if np.abs(A[i, j]) < tol:
                    return False, 0
                phase = A[i, j] / B[i, j]
                # Check if A = phase * B
                diff = np.abs(A - phase * B).max()
                return diff < tol, phase
    return False, 0


def print_matrix(name: str, m: np.ndarray) -> None:
    """Pretty print a matrix."""
    print(f"\n{name}:")
    for row in m:
        formatted = [f"{x.real:+.4f}{x.imag:+.4f}i" for x in row]
        print("  [" + ", ".join(formatted) + "]")


def demo_twist_compilation():
    """Demo 1: Compile TwistTen and verify it equals SWAP."""
    print("\n" + "="*60)
    print("Demo 1: TwistTen Compilation")
    print("="*60)

    twist = TwistTen(Q(), Q())
    result = runner.compile(twist, "TwistTen(Q, Q)", materialize=True)
    runner.print_circuit_details(result, "Compiled Circuit")
    runner.show_circuit(result, "TwistTen(Q, Q)")

    # Extract unitary from compiled circuit
    U_twist = result.circuit.get_unitary()
    print_matrix("U_twist (from compiled circuit)", U_twist)

    # The expected SWAP matrix
    SWAP = np.array([
        [1, 0, 0, 0],
        [0, 0, 1, 0],
        [0, 1, 0, 0],
        [0, 0, 0, 1]
    ], dtype=complex)

    # VERIFY: compiled twist = SWAP
    match, phase = matrices_equal_up_to_phase(U_twist, SWAP)
    print(f"\n✓ VERIFY: U_twist = SWAP? {match} (phase={phase:.4f})")
    assert match, "TwistTen should compile to SWAP!"

    return result, U_twist, SWAP


def demo_exp_single():
    """Demo 2: Compile exp_i(π/4, Twist) and verify unitary."""
    print("\n" + "="*60)
    print("Demo 2: exp_i(π/4, Twist) Compilation")
    print("="*60)

    ty = Ten(Q(), Q())
    twist = TwistTen(Q(), Q())
    theta = pi / 4
    exp_twist = ExpInvolution(theta=theta, body=twist, ty_total=ty)

    result = runner.compile(exp_twist, "ExpInvolution(π/4, TwistTen)")
    runner.print_circuit_details(result, "Compiled Circuit")
    runner.show_circuit(result, "ExpInvolution(π/4, TwistTen)")

    # Extract unitary
    U_exp_single = result.circuit.get_unitary()
    print_matrix("U_exp_single (from compiled circuit)", U_exp_single)

    # Expected: exp(iπ/4 · SWAP) = cos(π/4)·I + i·sin(π/4)·SWAP
    SWAP = np.array([
        [1, 0, 0, 0],
        [0, 0, 1, 0],
        [0, 1, 0, 0],
        [0, 0, 0, 1]
    ], dtype=complex)
    I4 = np.eye(4, dtype=complex)
    expected_single = np.cos(theta) * I4 + 1j * np.sin(theta) * SWAP
    print_matrix("Expected exp(iπ/4 · SWAP)", expected_single)

    # VERIFY: compiled circuit = expected
    match, phase = matrices_equal_up_to_phase(U_exp_single, expected_single)
    print(f"\n✓ VERIFY: U_exp_single = exp(iπ/4·SWAP)? {match} (phase={phase:.4f})")
    assert match, "exp_i(π/4, twist) should equal exp(iπ/4·SWAP)!"

    return result, U_exp_single


def demo_composition():
    """Demo 3: Compile exp;exp and verify = i·SWAP."""
    print("\n" + "="*60)
    print("Demo 3: exp_i(π/4, twist) ; exp_i(π/4, twist) Composition")
    print("="*60)

    ty = Ten(Q(), Q())
    twist = TwistTen(Q(), Q())
    theta = pi / 4
    exp_twist = ExpInvolution(theta=theta, body=twist, ty_total=ty)
    composed = Seq(exp_twist, exp_twist)

    result = runner.compile(composed, "exp;exp composition")
    runner.print_circuit_details(result, "Compiled Circuit")
    runner.show_circuit(result, "exp;exp composition")

    # Extract unitary
    U_composed = result.circuit.get_unitary()
    print_matrix("U_composed (from compiled circuit)", U_composed)

    # Expected: exp(iπ/2 · SWAP) = i·SWAP
    SWAP = np.array([
        [1, 0, 0, 0],
        [0, 0, 1, 0],
        [0, 1, 0, 0],
        [0, 0, 0, 1]
    ], dtype=complex)
    expected_composed = 1j * SWAP
    print_matrix("Expected i·SWAP", expected_composed)

    # VERIFY: compiled composition = i·SWAP
    match, phase = matrices_equal_up_to_phase(U_composed, expected_composed)
    print(f"\n✓ VERIFY: U_composed = i·SWAP? {match} (phase={phase:.4f})")
    assert match, "exp_i(π/4,twist);exp_i(π/4,twist) should equal i·SWAP!"

    return result, U_composed, SWAP


def demo_composition_law():
    """Demo 4: Verify composition law exp;exp = exp(2θ)."""
    print("\n" + "="*60)
    print("Demo 4: Composition Law exp_i(θ);exp_i(θ) = exp_i(2θ)")
    print("="*60)

    ty = Ten(Q(), Q())
    twist = TwistTen(Q(), Q())

    # Composed: exp_i(π/4, twist) ; exp_i(π/4, twist)
    theta = pi / 4
    exp_twist = ExpInvolution(theta=theta, body=twist, ty_total=ty)
    composed = Seq(exp_twist, exp_twist)
    result_composed = runner.compile(composed, "exp(π/4);exp(π/4)")
    U_composed = result_composed.circuit.get_unitary()

    # Direct: exp_i(π/2, twist)
    exp_half_pi = ExpInvolution(theta=pi/2, body=twist, ty_total=ty)
    result_half_pi = runner.compile(exp_half_pi, "exp(π/2) direct")
    runner.print_circuit_details(result_half_pi, "exp_i(π/2, twist) Circuit")
    runner.show_circuit(result_half_pi, "exp_i(π/2) direct")

    U_half_pi = result_half_pi.circuit.get_unitary()
    print_matrix("U_exp_half_pi (from compiled circuit)", U_half_pi)

    # VERIFY: composition equals direct exp_i(π/2)
    match, phase = matrices_equal_up_to_phase(U_composed, U_half_pi)
    print(f"\n✓ VERIFY: (exp_i(π/4);exp_i(π/4)) = exp_i(π/2)? {match} (phase={phase:.4f})")
    assert match, "Composition should equal exp_i(2θ)!"

    return result_half_pi


def main():
    global runner
    runner = DemoRunner(
        "Exponential of Involution Test",
        "Verifies: exp_i(π/4, Twist) ; exp_i(π/4, Twist) = i·Twist"
    )
    runner.print_header()
    print("\nVerifies exp_i(π/4, Twist) ; exp_i(π/4, Twist) = i·Twist")
    print("by extracting unitaries from compiled circuits.")

    # Run all demos
    demo_twist_compilation()
    demo_exp_single()
    demo_composition()
    demo_composition_law()

    print("\n" + "="*60)
    print("✓ ALL INFRASTRUCTURE TESTS PASSED")
    print("="*60)
    print("""
Verified by extracting unitaries from compiled circuits:

  1. TwistTen(Q,Q) compiles to SWAP
  2. exp_i(π/4, twist) compiles to exp(iπ/4·SWAP) (up to phase)
  3. exp_i(π/4, twist) ; exp_i(π/4, twist) = SWAP (up to phase)
  4. exp_i(π/4, twist) ; exp_i(π/4, twist) = exp_i(π/2, twist)

The composition law exp_i(θ,P) ; exp_i(θ,P) = exp_i(2θ,P) is verified!
""")

    runner.print_footer()
    return 0


if __name__ == "__main__":
    sys.exit(main())
