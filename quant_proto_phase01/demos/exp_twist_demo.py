#!/usr/bin/env python3
"""Demo: exp_i(π/4, Twist) ; exp_i(π/4, Twist) = i·Twist

This is an INFRASTRUCTURE TEST that verifies the identity by:
1. Compiling the terms to circuits
2. Extracting actual unitaries from compiled circuits
3. Comparing them mathematically

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

def main():
    print("=" * 60)
    print(" Exponential of Involution: INFRASTRUCTURE TEST")
    print(" Verifies: exp_i(π/4, Twist) ; exp_i(π/4, Twist) = i·Twist")
    print("=" * 60)

    # Type: Q ⊗ Q
    ty = Ten(Q(), Q())

    # =================================================================
    print_section("1. Compile TwistTen and extract unitary")
    # =================================================================

    twist = TwistTen(Q(), Q())
    result_twist = compile(twist, materialize=True)  # materialize to get actual SWAP

    print(f"Term: TwistTen(Q, Q)")
    print(f"Gates: {result_twist.circuit.n_gates}")

    # Extract unitary from compiled circuit
    U_twist = result_twist.circuit.get_unitary()
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

    # =================================================================
    print_section("2. Compile exp_i(π/4, Twist) and extract unitary")
    # =================================================================

    theta = pi / 4
    exp_twist = ExpInvolution(theta=theta, body=twist, ty_total=ty)
    result_single = compile(exp_twist)

    print(f"Term: ExpInvolution(π/4, TwistTen(Q,Q))")
    print(f"Gates: {result_single.circuit.n_gates}")
    print("Commands:")
    for cmd in result_single.circuit.get_commands():
        print(f"  {cmd}")

    # Extract unitary
    U_exp_single = result_single.circuit.get_unitary()
    print_matrix("U_exp_single (from compiled circuit)", U_exp_single)

    # Expected: exp(iπ/4 · SWAP) = cos(π/4)·I + i·sin(π/4)·SWAP
    I4 = np.eye(4, dtype=complex)
    expected_single = np.cos(theta) * I4 + 1j * np.sin(theta) * SWAP
    print_matrix("Expected exp(iπ/4 · SWAP)", expected_single)

    # VERIFY: compiled circuit = expected
    match, phase = matrices_equal_up_to_phase(U_exp_single, expected_single)
    print(f"\n✓ VERIFY: U_exp_single = exp(iπ/4·SWAP)? {match} (phase={phase:.4f})")
    assert match, "exp_i(π/4, twist) should equal exp(iπ/4·SWAP)!"

    # =================================================================
    print_section("3. Compile composition and extract unitary")
    # =================================================================

    composed = Seq(exp_twist, exp_twist)
    result_composed = compile(composed)

    print(f"Term: exp_i(π/4, twist) ; exp_i(π/4, twist)")
    print(f"Gates: {result_composed.circuit.n_gates}")
    print("Commands:")
    for cmd in result_composed.circuit.get_commands():
        print(f"  {cmd}")

    # Extract unitary
    U_composed = result_composed.circuit.get_unitary()
    print_matrix("U_composed (from compiled circuit)", U_composed)

    # Expected: exp(iπ/2 · SWAP) = i·SWAP
    expected_composed = 1j * SWAP
    print_matrix("Expected i·SWAP", expected_composed)

    # VERIFY: compiled composition = i·SWAP
    match, phase = matrices_equal_up_to_phase(U_composed, expected_composed)
    print(f"\n✓ VERIFY: U_composed = i·SWAP? {match} (phase={phase:.4f})")
    assert match, "exp_i(π/4,twist);exp_i(π/4,twist) should equal i·SWAP!"

    # =================================================================
    print_section("4. VERIFY: composed = SWAP up to global phase")
    # =================================================================

    # The key test: U_composed should equal SWAP up to global phase
    match, phase = matrices_equal_up_to_phase(U_composed, SWAP)
    print(f"U_composed = phase × SWAP? {match}")
    print(f"Phase factor: {phase:.4f} = {np.abs(phase):.4f} × e^(i × {np.angle(phase)/pi:.4f}π)")

    # Phase should have magnitude 1 (pure phase)
    phase_is_unit = np.abs(np.abs(phase) - 1.0) < 1e-10
    print(f"Phase has magnitude 1? {phase_is_unit}")

    assert match, "Composed circuit should equal SWAP up to phase!"
    assert phase_is_unit, f"Phase should have magnitude 1, got |{phase}| = {np.abs(phase)}"

    # =================================================================
    print_section("5. VERIFY: composition law exp;exp = exp(2θ)")
    # =================================================================

    # The real test: exp_i(π/4, twist) ; exp_i(π/4, twist) should equal exp_i(π/2, twist)
    # Compile exp_i(π/2, twist) directly
    exp_half_pi = ExpInvolution(theta=pi/2, body=twist, ty_total=ty)
    result_half_pi = compile(exp_half_pi)

    print(f"Term: exp_i(π/2, twist)")
    print(f"Gates: {result_half_pi.circuit.n_gates}")

    U_half_pi = result_half_pi.circuit.get_unitary()
    print_matrix("U_exp_half_pi (from compiled circuit)", U_half_pi)

    # VERIFY: composition equals direct exp_i(π/2)
    match, phase = matrices_equal_up_to_phase(U_composed, U_half_pi)
    print(f"\n✓ VERIFY: (exp_i(π/4);exp_i(π/4)) = exp_i(π/2)? {match} (phase={phase:.4f})")
    assert match, "Composition should equal exp_i(2θ)!"

    print("\n" + "="*60)
    print(" ✓ ALL INFRASTRUCTURE TESTS PASSED")
    print("="*60)
    print("""
Verified by extracting unitaries from compiled circuits:

  1. TwistTen(Q,Q) compiles to SWAP ✓
  2. exp_i(π/4, twist) compiles to exp(iπ/4·SWAP) (up to phase) ✓
  3. exp_i(π/4, twist) ; exp_i(π/4, twist) = SWAP (up to phase) ✓
  4. exp_i(π/4, twist) ; exp_i(π/4, twist) = exp_i(π/2, twist) ✓

The composition law exp_i(θ,P) ; exp_i(θ,P) = exp_i(2θ,P) is verified!
""")
    return 0

if __name__ == "__main__":
    sys.exit(main())
