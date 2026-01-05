#!/usr/bin/env python3
"""Demo: exp_i(π/4, X) ; Z ; exp_i(-π/4, X) = Y

Verifies the Pauli conjugation identity using qubit as I + I (one-hot encoding).

Representation:
  - Qubit type: I + I (width 2: two one-hot tag wires [t₀, t₁])
  - Logical |0⟩ = physical |10⟩ (t₀=1, t₁=0)
  - Logical |1⟩ = physical |01⟩ (t₀=0, t₁=1)

Pauli matrices on this encoding:
  - X = twist+[I,I] (structural: swaps the two tags)
  - Z = Z gate on wire 1 (phase flip when t₁=1)
  - Y = twist+[I,I] ; S[1] ; Sdg[0] (swap + phases i, -i)

The identity:
  exp_i(π/4, X) ; Z ; exp_i(-π/4, X) = Y

Run with:
    cd quant_proto_phase01
    PYTHONPATH=src python demos/pauli_conjugation_demo.py
"""

import sys
import numpy as np
from math import pi

sys.path.insert(0, 'src')

from lang.types import Unit, Plus
from lang.terms import TwistPlus, ExpInvolution, Seq, Z, S, Sdg

# Alias for readability
I = Unit
from compile.to_pytket import compile


def print_section(title: str) -> None:
    print(f"\n{'='*60}")
    print(f" {title}")
    print('='*60)


def extract_logical_submatrix(U: np.ndarray) -> np.ndarray:
    """Extract the 2x2 logical qubit submatrix from 4x4 physical unitary.

    One-hot encoding: |0⟩_L = |10⟩_P (idx 2), |1⟩_L = |01⟩_P (idx 1)
    """
    # Logical indices in physical basis
    idx_0 = 2  # |10⟩
    idx_1 = 1  # |01⟩

    return np.array([
        [U[idx_0, idx_0], U[idx_0, idx_1]],
        [U[idx_1, idx_0], U[idx_1, idx_1]]
    ])


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


def print_matrix(name: str, m: np.ndarray, labels: list = None) -> None:
    print(f"\n{name}:")
    if labels and len(labels) == m.shape[0]:
        # Print header
        header = "       " + "  ".join(f"{l:>12}" for l in labels)
        print(header)
    for i, row in enumerate(m):
        formatted = [f"{x.real:+.4f}{x.imag:+.4f}i" for x in row]
        prefix = f"  {labels[i]:>4} " if labels else "  "
        print(prefix + "[" + ", ".join(formatted) + "]")


def print_physical_and_logical(name: str, U_full: np.ndarray) -> np.ndarray:
    """Print both the 4x4 physical and 2x2 logical matrices."""
    # Physical 4x4
    phys_labels = ["|00⟩", "|01⟩", "|10⟩", "|11⟩"]
    print_matrix(f"{name} (physical 4×4)", U_full, phys_labels)

    # Logical 2x2
    U_logical = extract_logical_submatrix(U_full)
    log_labels = ["|0⟩_L", "|1⟩_L"]
    print_matrix(f"{name} (logical 2×2)", U_logical, log_labels)

    return U_logical


def main():
    print("=" * 60)
    print(" Pauli Conjugation Identity: INFRASTRUCTURE TEST")
    print(" exp_i(π/4, X) ; Z ; exp_i(-π/4, X) = Y")
    print("=" * 60)
    print("""
Qubit as I + I (one-hot encoding):
  - Physical: 2 tag wires [t₀, t₁]
  - Logical |0⟩ = |10⟩, Logical |1⟩ = |01⟩
""")

    # Type: I + I (qubit as sum of units)
    ty = Plus(I(), I())
    print(f"Type: I + I (width = 2)")

    # =================================================================
    print_section("1. Build X = twist+[I,I]")
    # =================================================================

    X = TwistPlus(I(), I())
    result_X = compile(X, materialize=True)

    print("Term: TwistPlus(I, I)")
    print(f"Gates: {result_X.circuit.n_gates}")
    print(f"Permutation: {result_X.perm.new_to_old}")

    U_X_full = result_X.circuit.get_unitary()
    U_X = print_physical_and_logical("X", U_X_full)

    # Expected Pauli-X
    expected_X = np.array([[0, 1], [1, 0]], dtype=complex)
    match, phase = matrices_equal_up_to_phase(U_X, expected_X)
    print(f"\n✓ VERIFY: X = Pauli-X? {match}")
    assert match, "X should equal Pauli-X!"

    # =================================================================
    print_section("2. Build Z = Z gate on wire 1")
    # =================================================================

    Z_gate = Z(1, ty)
    result_Z = compile(Z_gate)

    print("Term: Z(1, I+I)")
    print(f"Gates: {result_Z.circuit.n_gates}")

    U_Z_full = result_Z.circuit.get_unitary()
    U_Z = print_physical_and_logical("Z", U_Z_full)

    # Expected Pauli-Z
    expected_Z = np.array([[1, 0], [0, -1]], dtype=complex)
    match, phase = matrices_equal_up_to_phase(U_Z, expected_Z)
    print(f"\n✓ VERIFY: Z = Pauli-Z? {match}")
    assert match, "Z should equal Pauli-Z!"

    # =================================================================
    print_section("3. Build Y = twist ; S[1] ; Sdg[0]")
    # =================================================================

    # Y = twist + phases (i on wire 1, -i on wire 0)
    Y_term = Seq(TwistPlus(I(), I()), S(1, ty), Sdg(0, ty))
    result_Y = compile(Y_term, materialize=True)  # materialize SWAP

    print("Term: Seq(TwistPlus(I,I), S(1), Sdg(0))")
    print(f"Gates: {result_Y.circuit.n_gates}")
    print("Commands:")
    for cmd in result_Y.circuit.get_commands():
        print(f"  {cmd}")

    U_Y_full = result_Y.circuit.get_unitary()
    U_Y = print_physical_and_logical("Y", U_Y_full)

    # Expected Pauli-Y
    expected_Y = np.array([[0, -1j], [1j, 0]], dtype=complex)
    match, phase = matrices_equal_up_to_phase(U_Y, expected_Y)
    print(f"\n✓ VERIFY: Y = Pauli-Y? {match} (phase={phase:.4f})")
    assert match, "Y should equal Pauli-Y!"

    # =================================================================
    print_section("4. Build exp_i(π/4, X)")
    # =================================================================

    exp_X_pos = ExpInvolution(theta=pi/4, body=X, ty_total=ty)
    result_exp_pos = compile(exp_X_pos, materialize=True)

    print("Term: ExpInvolution(π/4, TwistPlus(I,I))")
    print(f"Gates: {result_exp_pos.circuit.n_gates}")
    print("Commands:")
    for cmd in result_exp_pos.circuit.get_commands():
        print(f"  {cmd}")

    U_exp_pos_full = result_exp_pos.circuit.get_unitary()
    U_exp_pos = print_physical_and_logical("exp_i(π/4, X)", U_exp_pos_full)

    # Expected: cos(π/4)I + i·sin(π/4)X = (1/√2)(I + iX)
    expected_exp_pos = np.cos(pi/4) * np.eye(2) + 1j * np.sin(pi/4) * expected_X
    match, phase = matrices_equal_up_to_phase(U_exp_pos, expected_exp_pos)
    print(f"\n✓ VERIFY: matches exp(iπ/4·X)? {match}")
    assert match, "exp_i(π/4, X) should match expected!"

    # =================================================================
    print_section("5. Build exp_i(-π/4, X)")
    # =================================================================

    exp_X_neg = ExpInvolution(theta=-pi/4, body=X, ty_total=ty)
    result_exp_neg = compile(exp_X_neg, materialize=True)

    print("Term: ExpInvolution(-π/4, TwistPlus(I,I))")
    print(f"Gates: {result_exp_neg.circuit.n_gates}")

    U_exp_neg_full = result_exp_neg.circuit.get_unitary()
    U_exp_neg = print_physical_and_logical("exp_i(-π/4, X)", U_exp_neg_full)

    # =================================================================
    print_section("6. Build conjugation: exp_i(π/4,X) ; Z ; exp_i(-π/4,X)")
    # =================================================================

    conjugation = Seq(exp_X_pos, Z_gate, exp_X_neg)
    result_conj = compile(conjugation, materialize=True)

    print("Term: Seq(exp_i(π/4,X), Z, exp_i(-π/4,X))")
    print(f"Gates: {result_conj.circuit.n_gates}")
    print("Commands:")
    for cmd in result_conj.circuit.get_commands():
        print(f"  {cmd}")

    U_conj_full = result_conj.circuit.get_unitary()
    U_conj = print_physical_and_logical("Conjugation", U_conj_full)

    # =================================================================
    print_section("7. VERIFY: Conjugation = Y")
    # =================================================================

    log_labels = ["|0⟩_L", "|1⟩_L"]
    print_matrix("Conjugation result (logical)", U_conj, log_labels)
    print_matrix("Expected Pauli-Y", expected_Y, log_labels)

    match, phase = matrices_equal_up_to_phase(U_conj, expected_Y)
    print(f"\nConjugation = Y (up to phase)? {match}")
    print(f"Phase factor: {phase:.4f}")
    assert match, "Conjugation should equal Y!"

    # Also verify against our explicit Y construction
    match2, phase2 = matrices_equal_up_to_phase(U_conj, U_Y)
    print(f"\nConjugation = Y_explicit? {match2} (phase={phase2:.4f})")
    assert match2, "Conjugation should match explicit Y!"

    # =================================================================
    print_section("8. Summary")
    # =================================================================

    print("""
┌────────────────────────────────────────────────────────────┐
│  Qubit as I + I (one-hot encoding)                         │
├────────────────────────────────────────────────────────────┤
│  X = twist+[I,I]                  → Pauli-X ✓              │
│  Z = Z[1]                         → Pauli-Z ✓              │
│  Y = twist ; S[1] ; Sdg[0]        → Pauli-Y ✓              │
├────────────────────────────────────────────────────────────┤
│  exp_i(π/4, X) ; Z ; exp_i(-π/4, X) = Y ✓                  │
└────────────────────────────────────────────────────────────┘

Verified by:
  1. Compiling each term to pytket circuit
  2. Extracting unitary via circuit.get_unitary()
  3. Extracting logical 2x2 submatrix from physical 4x4
  4. Comparing matrices up to global phase
""")

    print("✓ ALL INFRASTRUCTURE TESTS PASSED!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
