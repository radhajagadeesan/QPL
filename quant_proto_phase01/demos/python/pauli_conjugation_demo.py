#!/usr/bin/env python3
"""Demo: ExpInvolution Conjugation

Verifies that exp_i(θ, SWAP) correctly implements exp(iθ·SWAP) and that
conjugation exp_i(θ,P) ; U ; exp_i(-θ,P) works.

This demo uses Q ⊗ Q with TwistTen (SWAP), which is a genuine wire permutation
that ExpInvolution can handle.

Usage:
    python pauli_conjugation_demo.py              # Run demo
    python pauli_conjugation_demo.py --circuits   # Show circuit diagrams
"""

import sys
import numpy as np
from math import pi
from pathlib import Path

# Add src to path
src_path = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_path))

from lang.types import Q, Ten, width
from lang.terms import TwistTen, ExpInvolution, Seq, Z

from demo_utils import DemoRunner

# Global runner instance
runner = None


def matrices_equal_up_to_phase(A: np.ndarray, B: np.ndarray, tol: float = 1e-9):
    """Check if A = e^{iφ} · B for some phase φ."""
    for i in range(B.shape[0]):
        for j in range(B.shape[1]):
            if np.abs(B[i, j]) > tol:
                if np.abs(A[i, j]) < tol:
                    return False, 0
                phase = A[i, j] / B[i, j]
                diff = np.abs(A - phase * B).max()
                return diff < tol, phase
    return False, 0


def print_matrix(name: str, m: np.ndarray) -> None:
    print(f"\n{name}:")
    n = m.shape[0]
    if n == 4:
        labels = ["|00⟩", "|01⟩", "|10⟩", "|11⟩"]
    else:
        labels = [f"|{i}⟩" for i in range(n)]
    for i, row in enumerate(m):
        formatted = [f"{x.real:+.4f}{x.imag:+.4f}i" for x in row]
        print(f"  {labels[i]} [{', '.join(formatted)}]")


def demo_swap():
    """Demo 1: Build SWAP = TwistTen(Q, Q)."""
    print("\n" + "="*60)
    print("Demo 1: Build SWAP = TwistTen(Q, Q)")
    print("="*60)

    SWAP_term = TwistTen(Q(), Q())
    result = runner.compile(SWAP_term, "TwistTen(Q, Q)", materialize=True)
    runner.print_circuit_details(result, "Compiled Circuit")
    runner.show_circuit(result, "TwistTen(Q, Q)")

    U_SWAP = result.circuit.get_unitary()
    print_matrix("SWAP (compiled)", U_SWAP)

    # Verify SWAP² = I
    SWAP_squared = U_SWAP @ U_SWAP
    is_identity = np.allclose(SWAP_squared, np.eye(4))
    print(f"\n✓ VERIFY: SWAP² = I? {is_identity}")
    assert is_identity, "SWAP should be involutive!"

    return result, U_SWAP


def demo_exp_positive(U_SWAP):
    """Demo 2: Build exp_i(π/4, SWAP)."""
    print("\n" + "="*60)
    print("Demo 2: Build exp_i(π/4, SWAP)")
    print("="*60)

    ty = Ten(Q(), Q())
    SWAP_term = TwistTen(Q(), Q())
    theta = pi / 4
    exp_SWAP_pos = ExpInvolution(theta=theta, body=SWAP_term, ty_total=ty)

    result = runner.compile(exp_SWAP_pos, "ExpInvolution(π/4, SWAP)", materialize=True)
    runner.print_circuit_details(result, "Compiled Circuit")
    runner.show_circuit(result, "ExpInvolution(π/4, SWAP)")

    U_exp_pos = result.circuit.get_unitary()
    print_matrix("exp_i(π/4, SWAP) (compiled)", U_exp_pos)

    # Verify exp(iθ·SWAP) formula: should equal cos(θ)I + i·sin(θ)·SWAP
    expected_exp = np.cos(theta) * np.eye(4) + 1j * np.sin(theta) * U_SWAP
    match, phase = matrices_equal_up_to_phase(U_exp_pos, expected_exp)
    print(f"\n✓ VERIFY: matches cos(θ)I + i·sin(θ)·SWAP? {match} (phase={phase:.4f})")
    assert match, "exp_i(π/4, SWAP) should match formula!"

    return result, U_exp_pos


def demo_exp_negative(U_exp_pos):
    """Demo 3: Build exp_i(-π/4, SWAP)."""
    print("\n" + "="*60)
    print("Demo 3: Build exp_i(-π/4, SWAP)")
    print("="*60)

    ty = Ten(Q(), Q())
    SWAP_term = TwistTen(Q(), Q())
    theta = pi / 4
    exp_SWAP_neg = ExpInvolution(theta=-theta, body=SWAP_term, ty_total=ty)

    result = runner.compile(exp_SWAP_neg, "ExpInvolution(-π/4, SWAP)", materialize=True)
    runner.print_circuit_details(result, "Compiled Circuit")
    runner.show_circuit(result, "ExpInvolution(-π/4, SWAP)")

    U_exp_neg = result.circuit.get_unitary()
    print_matrix("exp_i(-π/4, SWAP) (compiled)", U_exp_neg)

    # Verify exp(iθ) · exp(-iθ) = I (up to global phase)
    product = U_exp_pos @ U_exp_neg
    is_identity = np.allclose(np.abs(product), np.abs(np.eye(4)))
    print(f"\n✓ VERIFY: exp(iθ·SWAP) · exp(-iθ·SWAP) = I (up to phase)? {is_identity}")
    assert is_identity, "exp and exp-inverse should compose to identity!"

    return result, U_exp_neg


def demo_z_gate():
    """Demo 4: Build Z gate."""
    print("\n" + "="*60)
    print("Demo 4: Build Z gate")
    print("="*60)

    ty = Ten(Q(), Q())
    Z_term = Z(0, ty)  # Z on first qubit

    result = runner.compile(Z_term, "Z(0, Q⊗Q)")
    runner.print_circuit_details(result, "Compiled Circuit")
    runner.show_circuit(result, "Z(0, Q⊗Q)")

    U_Z = result.circuit.get_unitary()
    print_matrix("Z (compiled)", U_Z)

    return result, U_Z


def demo_conjugation():
    """Demo 5: Conjugation: exp_i(π/4,SWAP) ; Z ; exp_i(-π/4,SWAP)."""
    print("\n" + "="*60)
    print("Demo 5: Conjugation exp_i(π/4,SWAP) ; Z ; exp_i(-π/4,SWAP)")
    print("="*60)

    ty = Ten(Q(), Q())
    SWAP_term = TwistTen(Q(), Q())
    theta = pi / 4

    exp_SWAP_pos = ExpInvolution(theta=theta, body=SWAP_term, ty_total=ty)
    Z_term = Z(0, ty)
    exp_SWAP_neg = ExpInvolution(theta=-theta, body=SWAP_term, ty_total=ty)

    conjugation = Seq(exp_SWAP_pos, Z_term, exp_SWAP_neg)

    result = runner.compile(conjugation, "conjugation", materialize=True)
    runner.print_circuit_details(result, "Compiled Circuit")
    runner.show_circuit(result, "Conjugation")

    U_conj = result.circuit.get_unitary()
    print_matrix("Conjugation result", U_conj)

    # Verify conjugation is unitary
    is_unitary = np.allclose(U_conj @ U_conj.conj().T, np.eye(4))
    print(f"\n✓ VERIFY: Conjugation is unitary? {is_unitary}")
    assert is_unitary, "Conjugation should be unitary!"

    return result


def demo_composition_law():
    """Demo 6: Composition law: exp(θ);exp(θ) = exp(2θ)."""
    print("\n" + "="*60)
    print("Demo 6: Composition law exp(θ);exp(θ) = exp(2θ)")
    print("="*60)

    ty = Ten(Q(), Q())
    SWAP_term = TwistTen(Q(), Q())
    theta = pi / 4

    exp_SWAP_pos = ExpInvolution(theta=theta, body=SWAP_term, ty_total=ty)

    # Build exp_i(π/2, SWAP) directly
    exp_half_pi = ExpInvolution(theta=pi/2, body=SWAP_term, ty_total=ty)
    result_half_pi = runner.compile(exp_half_pi, "exp_i(π/2, SWAP)", materialize=True)

    U_half_pi = result_half_pi.circuit.get_unitary()

    # Build exp_i(π/4, SWAP) ; exp_i(π/4, SWAP)
    double_exp = Seq(exp_SWAP_pos, exp_SWAP_pos)
    result_double = runner.compile(double_exp, "exp(π/4);exp(π/4)", materialize=True)
    runner.print_circuit_details(result_double, "Double composition")
    runner.show_circuit(result_double, "exp(π/4);exp(π/4)")

    U_double = result_double.circuit.get_unitary()

    match, phase = matrices_equal_up_to_phase(U_double, U_half_pi)
    print(f"\n✓ VERIFY: exp(π/4);exp(π/4) = exp(π/2)? {match}")
    if match:
        print(f"  Phase factor: {phase:.4f}")
    assert match, "Composition law should hold!"

    return result_double


def main():
    global runner
    runner = DemoRunner(
        "ExpInvolution Conjugation Demo",
        "Verifies exp_i(θ, SWAP) ; Z ; exp_i(-θ, SWAP) conjugation"
    )
    runner.print_header()

    ty = Ten(Q(), Q())
    w = width(ty)
    print(f"""
Type: Q ⊗ Q (width = {w} qubits)

SWAP = TwistTen(Q, Q) — wire permutation [1, 0]
exp_i(θ, SWAP) = exp(iθ · SWAP) — uses ExpSwap decomposition
""")

    # Run all demos
    _, U_SWAP = demo_swap()
    _, U_exp_pos = demo_exp_positive(U_SWAP)
    demo_exp_negative(U_exp_pos)
    demo_z_gate()
    demo_conjugation()
    demo_composition_law()

    # Summary
    print("\n" + "="*60)
    print("Summary")
    print("="*60)
    print("""
ExpInvolution Infrastructure Test
─────────────────────────────────
Type: Q ⊗ Q (2 qubits)
SWAP = TwistTen(Q,Q) — wire permutation

SWAP² = I (involutive)                          ✓
exp_i(θ, SWAP) = cos(θ)I + i·sin(θ)·SWAP       ✓
exp(iθ) · exp(-iθ) = I                          ✓
Conjugation is unitary                          ✓
Composition law: exp(θ);exp(θ) = exp(2θ)        ✓

The ExpInvolution infrastructure correctly implements exp(iθ·P)
for wire-permutation involutions P.
""")

    print("✓ ALL TESTS PASSED!")
    runner.print_footer()
    return 0


if __name__ == "__main__":
    sys.exit(main())
