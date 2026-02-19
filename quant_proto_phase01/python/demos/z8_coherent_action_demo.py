#!/usr/bin/env python3
"""Z_8 coherent group action demo using NPlusMap.

Demonstrates the n-ary coherent sum eliminator (NPlusMap) by implementing
the Z_8 cyclic group acting on a qubit via phase rotations.

Z_8 = Q + Q + Q + Q + Q + Q + Q + Q   (8 summands, each a 1-qubit type)

The action: for element m ∈ {0,...,7}, apply Rz(m/4) to the payload qubit.
This gives phase rotation e^{±i·m·π/8} on the |0⟩/|1⟩ components.

Wire layout: [tag₀ | tag₁ | tag₂ | payload]  (3 tag qubits + 1 payload = 4 qubits)

Key insight: NPlusMap compiles directly against the flat tag encoding,
avoiding the binary-tree nesting problem that makes PlusMap inadequate
for n > 2 coherent dispatch.
"""

import sys
from pathlib import Path
import math
import numpy as np

# Add src to path
src_path = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_path))

from demo_utils import DemoRunner
from lang.types import Q, Plus, width, flatten_plus, build_plus_tree, tag_width
from lang.terms import NPlusMap, PlusMap, Id, Seq, Rz, H, X, Z
from typing_.check import type_of
from compile.to_pytket import compile as qpl_compile


def main():
    runner = DemoRunner(
        "Z₈ Coherent Group Action via NPlusMap",
        "Demonstrates n-ary coherent sum elimination with Z_8 phase kicks"
    )
    runner.print_header()

    # ── Section 1: Z_8 type ──────────────────────────────────────────────
    print("\n" + "─" * 60)
    print("Section 1: Z₈ type structure")
    print("─" * 60)

    summands = tuple(Q() for _ in range(8))
    z8_q = build_plus_tree(list(summands))

    print(f"  Z₈ ⊗ Q = Q + Q + Q + Q + Q + Q + Q + Q")
    print(f"  Number of summands: {len(flatten_plus(z8_q))}")
    print(f"  Tag qubits: {tag_width(z8_q)}")
    print(f"  Total width: {width(z8_q)} qubits")

    # ── Section 2: Z_8 phase action ─────────────────────────────────────
    print("\n" + "─" * 60)
    print("Section 2: Z₈ phase action — Rz(m/4) per branch")
    print("─" * 60)

    # Each element m applies Rz(m/4) in half-turns = Rz(m·π/4) rotation
    branches = tuple(Rz(m * 0.25, i=0, ty_total=Q()) for m in range(8))
    action = NPlusMap(summands, branches)

    dom, cod = type_of(action)
    print(f"  NPlusMap type: {dom} → {cod}")
    print(f"  Domain width: {width(dom)}, Codomain width: {width(cod)}")

    result = runner.compile(action, "Z₈ action (NPlusMap)")
    runner.show_circuit(result, "Z₈ action")

    # Verify unitary
    U = result.circuit.get_unitary()
    print(f"\n  Unitary shape: {U.shape[0]}×{U.shape[1]}")

    print("\n  Block diagonal verification (each 2×2 block for tag m):")
    all_ok = True
    for m in range(8):
        alpha = m * 0.25  # half-turns
        expected = np.diag([
            np.exp(-1j * alpha * np.pi / 2),
            np.exp(1j * alpha * np.pi / 2),
        ])
        actual = U[m*2:(m+1)*2, m*2:(m+1)*2]
        match = np.allclose(actual, expected, atol=1e-7)
        phase_str = f"Rz({m}/4)" if m > 0 else "Id"
        status = "✓" if match else "✗"
        diag0 = actual[0, 0]
        diag1 = actual[1, 1]
        print(f"    m={m} ({phase_str:>7s}): "
              f"diag = [{diag0.real:+.4f}{diag0.imag:+.4f}j, "
              f"{diag1.real:+.4f}{diag1.imag:+.4f}j]  {status}")
        if not match:
            all_ok = False

    # Verify off-diagonal blocks are zero
    off_diag_ok = True
    for m1 in range(8):
        for m2 in range(8):
            if m1 != m2:
                block = U[m1*2:(m1+1)*2, m2*2:(m2+1)*2]
                if not np.allclose(block, 0, atol=1e-7):
                    off_diag_ok = False

    print(f"\n  Off-diagonal blocks zero: {'YES' if off_diag_ok else 'NO'}")
    print(f"  All diagonal blocks correct: {'YES' if all_ok else 'NO'}")
    assert all_ok and off_diag_ok, "Z₈ unitary verification failed!"

    # ── Section 3: Z_4 for comparison ────────────────────────────────────
    print("\n" + "─" * 60)
    print("Section 3: Z₄ phase action for comparison")
    print("─" * 60)

    summands_4 = tuple(Q() for _ in range(4))
    branches_4 = tuple(Rz(m * 0.5, i=0, ty_total=Q()) for m in range(4))
    action_4 = NPlusMap(summands_4, branches_4)

    result_4 = runner.compile(action_4, "Z₄ action (NPlusMap)")
    runner.show_circuit(result_4, "Z₄ action")

    U4 = result_4.circuit.get_unitary()
    print(f"\n  Unitary shape: {U4.shape[0]}×{U4.shape[1]}")
    z4_ok = True
    for m in range(4):
        alpha = m * 0.5
        expected = np.diag([
            np.exp(-1j * alpha * np.pi / 2),
            np.exp(1j * alpha * np.pi / 2),
        ])
        actual = U4[m*2:(m+1)*2, m*2:(m+1)*2]
        match = np.allclose(actual, expected, atol=1e-7)
        status = "✓" if match else "✗"
        print(f"    m={m}: Rz({m}/2) block correct  {status}")
        if not match:
            z4_ok = False
    assert z4_ok, "Z₄ unitary verification failed!"

    # ── Section 4: Functoriality check ───────────────────────────────────
    print("\n" + "─" * 60)
    print("Section 4: Functoriality — Seq(NPlusMap(f), NPlusMap(g)) = NPlusMap(Seq(f,g))")
    print("─" * 60)

    fs = tuple(Rz(m * 0.125, i=0, ty_total=Q()) for m in range(8))
    gs = tuple(Rz(m * 0.125, i=0, ty_total=Q()) for m in range(8))

    lhs = Seq(NPlusMap(summands, fs), NPlusMap(summands, gs))
    rhs = NPlusMap(summands, tuple(Seq(f, g) for f, g in zip(fs, gs)))

    result_lhs = runner.compile(lhs, "Seq(NPlusMap(f), NPlusMap(g))")
    result_rhs = runner.compile(rhs, "NPlusMap(Seq(f,g))")

    U_lhs = result_lhs.circuit.get_unitary()
    U_rhs = result_rhs.circuit.get_unitary()

    # Check up to global phase
    func_ok = True
    for i in range(16):
        for j in range(16):
            if abs(U_lhs[i, j]) > 1e-10 and abs(U_rhs[i, j]) > 1e-10:
                phase = U_rhs[i, j] / U_lhs[i, j]
                func_ok = np.allclose(U_lhs * phase, U_rhs, atol=1e-7)
                break
        if not func_ok or abs(U_lhs[i, j]) > 1e-10:
            break

    print(f"\n  Unitaries match (up to global phase): {'YES' if func_ok else 'NO'}")
    assert func_ok, "Functoriality check failed!"

    # ── Section 5: Non-power-of-2 (Z₅) ──────────────────────────────────
    print("\n" + "─" * 60)
    print("Section 5: Z₅ action (non-power-of-2, k=3 tag qubits)")
    print("─" * 60)

    summands_5 = tuple(Q() for _ in range(5))
    branches_5 = tuple(Rz(m * 0.4, i=0, ty_total=Q()) for m in range(5))
    action_5 = NPlusMap(summands_5, branches_5)

    result_5 = runner.compile(action_5, "Z₅ action (NPlusMap)")

    U5 = result_5.circuit.get_unitary()
    print(f"\n  Unitary shape: {U5.shape[0]}×{U5.shape[1]}")
    print(f"  Active branches: 5, unused tag values: 3")

    z5_ok = True
    for m in range(5):
        alpha = m * 0.4
        expected = np.diag([
            np.exp(-1j * alpha * np.pi / 2),
            np.exp(1j * alpha * np.pi / 2),
        ])
        actual = U5[m*2:(m+1)*2, m*2:(m+1)*2]
        match = np.allclose(actual, expected, atol=1e-7)
        status = "✓" if match else "✗"
        print(f"    m={m}: Rz({m}*0.4) block correct  {status}")
        if not match:
            z5_ok = False

    # Verify unused branches are identity
    for m in range(5, 8):
        block = U5[m*2:(m+1)*2, m*2:(m+1)*2]
        match = np.allclose(block, np.eye(2), atol=1e-7)
        status = "✓" if match else "✗"
        print(f"    m={m}: unused (identity)  {status}")
        if not match:
            z5_ok = False

    assert z5_ok, "Z₅ unitary verification failed!"

    # ── Summary ──────────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("  ALL VERIFICATIONS PASSED")
    print("=" * 60)
    print(f"""
  NPlusMap enables n-ary coherent dispatch on flat tag encodings:
    - Z₄:  2 tag qubits + 1 payload = 3 qubits  ({result_4.circuit.n_gates} gates)
    - Z₅:  3 tag qubits + 1 payload = 4 qubits  ({result_5.circuit.n_gates} gates)
    - Z₈:  3 tag qubits + 1 payload = 4 qubits  ({result.circuit.n_gates} gates)

  Key properties verified:
    - Block-diagonal structure (each branch acts independently)
    - Correct phase rotations per branch
    - Functoriality (composition law)
    - Non-power-of-2 support (unused tags = identity)
""")

    runner.print_footer()


if __name__ == "__main__":
    main()
