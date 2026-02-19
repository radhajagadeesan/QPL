# tests/test_nplusmap.py
"""Tests for NPlusMap (n-ary coherent sum eliminator)."""

import math
import numpy as np
import pytest

from lang.types import Q, Plus, Ten, Unit, width, flatten_plus, build_plus_tree, tag_width, payload_width
from lang.terms import (
    NPlusMap, PlusMap, Id, Seq, TenTerm, H, S, X, Z, Rz, Ctrl,
)
from typing_.check import type_of, TypeCheckError
from compile.to_pytket import compile


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def get_unitary(term):
    """Compile a term and return its unitary matrix."""
    result = compile(term, materialize=True)
    return result.circuit.get_unitary()


def unitaries_close(U, V, atol=1e-7):
    """Check if two unitaries are equal up to global phase."""
    if U.shape != V.shape:
        return False
    # Find first nonzero element to determine global phase
    for i in range(U.shape[0]):
        for j in range(U.shape[1]):
            if abs(U[i, j]) > 1e-10 and abs(V[i, j]) > 1e-10:
                phase = V[i, j] / U[i, j]
                return np.allclose(U * phase, V, atol=atol)
    return np.allclose(U, V, atol=atol)


# ===========================================================================
# Type Checking
# ===========================================================================

class TestNPlusMapTypeChecking:

    def test_basic_4way(self):
        """NPlusMap with 4 Q() summands, Id on each."""
        summands = tuple(Q() for _ in range(4))
        branches = tuple(Id(Q()) for _ in range(4))
        t = NPlusMap(summands, branches)
        dom, cod = type_of(t)
        # Domain and codomain are balanced Plus trees of 4 Q()s
        assert flatten_plus(dom) == [Q(), Q(), Q(), Q()]
        assert flatten_plus(cod) == [Q(), Q(), Q(), Q()]

    def test_mixed_widths(self):
        """Summands of different widths."""
        summands = (Q(), Ten(Q(), Q()))
        branches = (Id(Q()), Id(Ten(Q(), Q())))
        t = NPlusMap(summands, branches)
        dom, cod = type_of(t)
        assert dom == Plus(Q(), Ten(Q(), Q()))
        assert cod == Plus(Q(), Ten(Q(), Q()))

    def test_mismatch_count(self):
        """Wrong number of branches raises error."""
        summands = (Q(), Q(), Q())
        branches = (Id(Q()), Id(Q()))  # Only 2, need 3
        t = NPlusMap(summands, branches)
        with pytest.raises(TypeCheckError, match="3 summand types but 2 branches"):
            type_of(t)

    def test_dom_width_mismatch(self):
        """Branch domain doesn't match summand width."""
        summands = (Q(), Q())
        branches = (Id(Q()), Id(Ten(Q(), Q())))  # second branch has width 2
        t = NPlusMap(summands, branches)
        with pytest.raises(TypeCheckError, match="branch 1.*domain width 2.*summand width 1"):
            type_of(t)

    def test_too_few_summands(self):
        """NPlusMap with <2 summands raises error."""
        t = NPlusMap((Q(),), (Id(Q()),))
        with pytest.raises(TypeCheckError, match="at least 2"):
            type_of(t)

    def test_8way_type(self):
        """NPlusMap with 8 Q() summands has correct type structure."""
        summands = tuple(Q() for _ in range(8))
        branches = tuple(Id(Q()) for _ in range(8))
        t = NPlusMap(summands, branches)
        dom, cod = type_of(t)
        assert len(flatten_plus(dom)) == 8
        assert width(dom) == 3 + 1  # 3 tag bits + 1 payload


# ===========================================================================
# Compilation: Identity Tests
# ===========================================================================

class TestNPlusMapCompilation:

    def test_4way_identity(self):
        """NPlusMap with 4 Id branches produces identity unitary."""
        summands = tuple(Q() for _ in range(4))
        branches = tuple(Id(Q()) for _ in range(4))
        t = NPlusMap(summands, branches)
        U = get_unitary(t)
        # 4 summands, k=2 tag bits, pw=1 payload = 3 qubits total
        assert U.shape == (8, 8)
        assert np.allclose(U, np.eye(8), atol=1e-7)

    def test_8way_identity(self):
        """NPlusMap with 8 Id branches produces identity unitary."""
        summands = tuple(Q() for _ in range(8))
        branches = tuple(Id(Q()) for _ in range(8))
        t = NPlusMap(summands, branches)
        U = get_unitary(t)
        # 8 summands, k=3 tag bits, pw=1 payload = 4 qubits total
        assert U.shape == (16, 16)
        assert np.allclose(U, np.eye(16), atol=1e-7)

    def test_single_branch_gate(self):
        """Only one branch has a gate (X), rest Id."""
        summands = tuple(Q() for _ in range(4))
        branches = (
            Id(Q()),    # branch 0: identity
            X(i=0, ty_total=Q()),  # branch 1: X gate
            Id(Q()),    # branch 2: identity
            Id(Q()),    # branch 3: identity
        )
        t = NPlusMap(summands, branches)
        U = get_unitary(t)
        assert U.shape == (8, 8)

        # For tag=1 (binary 01, index 1), the X gate should be applied to payload
        # State |01,q⟩: tag=1, payload=q
        # In big-endian: state index = 1*2 + q = 2+q
        # So U[2,3] and U[3,2] should be nonzero (X gate swaps payload)
        assert abs(U[2, 3]) > 0.9  # |01,0⟩ → |01,1⟩
        assert abs(U[3, 2]) > 0.9  # |01,1⟩ → |01,0⟩

        # Other tags should be identity on payload
        for tag in [0, 2, 3]:
            r0 = tag * 2
            assert abs(U[r0, r0]) > 0.9     # |tag,0⟩ → |tag,0⟩
            assert abs(U[r0+1, r0+1]) > 0.9  # |tag,1⟩ → |tag,1⟩

    def test_all_branches_different(self):
        """Each branch has a different gate — block diagonal structure."""
        summands = tuple(Q() for _ in range(4))
        branches = (
            Id(Q()),
            X(i=0, ty_total=Q()),
            Z(i=0, ty_total=Q()),
            H(i=0, ty_total=Q()),
        )
        t = NPlusMap(summands, branches)
        U = get_unitary(t)

        # Verify block structure: each 2x2 block on the diagonal
        # Block 0 (tag=0): Id
        assert np.allclose(U[0:2, 0:2], np.eye(2), atol=1e-7)
        # Block 1 (tag=1): X
        X_mat = np.array([[0, 1], [1, 0]])
        assert np.allclose(U[2:4, 2:4], X_mat, atol=1e-7)
        # Block 2 (tag=2): Z
        Z_mat = np.array([[1, 0], [0, -1]])
        assert np.allclose(U[4:6, 4:6], Z_mat, atol=1e-7)
        # Block 3 (tag=3): H
        H_mat = np.array([[1, 1], [1, -1]]) / np.sqrt(2)
        assert np.allclose(U[6:8, 6:8], H_mat, atol=1e-7)


# ===========================================================================
# Semantics
# ===========================================================================

class TestNPlusMapSemantics:

    def test_block_diagonal_structure(self):
        """N-way NPlusMap produces block-diagonal unitary."""
        summands = tuple(Q() for _ in range(4))
        branches = tuple(Rz(m * 0.5, i=0, ty_total=Q()) for m in range(4))
        t = NPlusMap(summands, branches)
        U = get_unitary(t)

        # Off-diagonal blocks should be zero
        for m1 in range(4):
            for m2 in range(4):
                if m1 != m2:
                    block = U[m1*2:(m1+1)*2, m2*2:(m2+1)*2]
                    assert np.allclose(block, 0, atol=1e-7), \
                        f"Off-diagonal block ({m1},{m2}) nonzero"

    def test_z4_phase_kick(self):
        """Z_4 phase action: Rz(0), Rz(1/2), Rz(1), Rz(3/2) in half-turns."""
        summands = tuple(Q() for _ in range(4))
        branches = tuple(Rz(m * 0.5, i=0, ty_total=Q()) for m in range(4))
        t = NPlusMap(summands, branches)
        U = get_unitary(t)

        for m in range(4):
            alpha = m * 0.5  # half-turns
            expected_block = np.diag([
                np.exp(-1j * alpha * np.pi / 2),
                np.exp(1j * alpha * np.pi / 2),
            ])
            actual_block = U[m*2:(m+1)*2, m*2:(m+1)*2]
            assert np.allclose(actual_block, expected_block, atol=1e-7), \
                f"Z4 phase block {m} mismatch"

    def test_z8_phase_kick(self):
        """Z_8 phase action with Rz(m/4) for m=0..7 (half-turns)."""
        summands = tuple(Q() for _ in range(8))
        branches = tuple(Rz(m * 0.25, i=0, ty_total=Q()) for m in range(8))
        t = NPlusMap(summands, branches)
        U = get_unitary(t)

        # 16x16 matrix, 8 blocks of 2x2
        assert U.shape == (16, 16)

        for m in range(8):
            alpha = m * 0.25  # half-turns
            expected_block = np.diag([
                np.exp(-1j * alpha * np.pi / 2),
                np.exp(1j * alpha * np.pi / 2),
            ])
            actual_block = U[m*2:(m+1)*2, m*2:(m+1)*2]
            assert np.allclose(actual_block, expected_block, atol=1e-7), \
                f"Z8 phase block {m} mismatch"


# ===========================================================================
# Functoriality
# ===========================================================================

class TestNPlusMapFunctoriality:

    def test_composition_law(self):
        """Seq(NPlusMap(f₁,...), NPlusMap(g₁,...)) ≡ NPlusMap(Seq(f₁,g₁),...)."""
        summands = tuple(Q() for _ in range(4))

        # First: f_i = Rz(i * 0.25)
        fs = tuple(Rz(i * 0.25, i=0, ty_total=Q()) for i in range(4))
        # Second: g_i = Rz(i * 0.5)
        gs = tuple(Rz(i * 0.5, i=0, ty_total=Q()) for i in range(4))

        # Sequential composition of two NPlusMaps
        lhs = Seq(NPlusMap(summands, fs), NPlusMap(summands, gs))
        U_lhs = get_unitary(lhs)

        # Single NPlusMap with composed branches
        composed = tuple(Seq(f, g) for f, g in zip(fs, gs))
        rhs = NPlusMap(summands, composed)
        U_rhs = get_unitary(rhs)

        assert unitaries_close(U_lhs, U_rhs), "Composition law failed"

    def test_identity_law(self):
        """NPlusMap(Id,...,Id) ≡ Id on the sum type."""
        summands = tuple(Q() for _ in range(4))
        branches = tuple(Id(Q()) for _ in range(4))
        t = NPlusMap(summands, branches)
        U = get_unitary(t)
        assert np.allclose(U, np.eye(8), atol=1e-7)


# ===========================================================================
# Ctrl(NPlusMap)
# ===========================================================================

class TestNPlusMapWithCtrl:

    def test_ctrl_nplusmap(self):
        """Ctrl(NPlusMap(...)) compiles and produces correct unitary."""
        summands = tuple(Q() for _ in range(4))
        branches = (
            Id(Q()),
            X(i=0, ty_total=Q()),
            Id(Q()),
            Id(Q()),
        )
        inner = NPlusMap(summands, branches)
        t = Ctrl(inner)

        dom, cod = type_of(t)
        # Ctrl adds Bool = I+I (1 qubit) to the tensor
        assert width(dom) == 1 + width(type_of(inner)[0])

        U = get_unitary(t)
        dim = U.shape[0]

        # When control=0 (first half): identity
        half = dim // 2
        assert np.allclose(U[:half, :half], np.eye(half), atol=1e-7)

        # When control=1 (second half): the NPlusMap unitary
        U_inner = get_unitary(inner)
        assert np.allclose(U[half:, half:], U_inner, atol=1e-7)


# ===========================================================================
# Edge Cases
# ===========================================================================

class TestNPlusMapEdgeCases:

    def test_2way_matches_plusmap(self):
        """NPlusMap([A,B],[f,g]) should match PlusMap(A,B,f,g)."""
        A, B = Q(), Q()
        f = H(i=0, ty_total=Q())
        g = S(i=0, ty_total=Q())

        npm = NPlusMap((A, B), (f, g))
        pm = PlusMap(A, B, f, g)

        U_npm = get_unitary(npm)
        U_pm = get_unitary(pm)

        assert unitaries_close(U_npm, U_pm), \
            "2-way NPlusMap does not match PlusMap"

    def test_non_power_of_2_three(self):
        """NPlusMap with 3 summands (non-power-of-2)."""
        summands = tuple(Q() for _ in range(3))
        branches = (
            X(i=0, ty_total=Q()),
            Id(Q()),
            Z(i=0, ty_total=Q()),
        )
        t = NPlusMap(summands, branches)
        U = get_unitary(t)

        # k=2 tag bits, pw=1 payload → 3 qubits, dim=8
        assert U.shape == (8, 8)

        # Block 0 (tag=0): X gate
        X_mat = np.array([[0, 1], [1, 0]])
        assert np.allclose(U[0:2, 0:2], X_mat, atol=1e-7)
        # Block 1 (tag=1): Id
        assert np.allclose(U[2:4, 2:4], np.eye(2), atol=1e-7)
        # Block 2 (tag=2): Z gate
        Z_mat = np.array([[1, 0], [0, -1]])
        assert np.allclose(U[4:6, 4:6], Z_mat, atol=1e-7)
        # Block 3 (tag=3): unused, should be identity (no branch emits here)
        assert np.allclose(U[6:8, 6:8], np.eye(2), atol=1e-7)

    def test_non_power_of_2_five(self):
        """NPlusMap with 5 summands (non-power-of-2, k=3)."""
        summands = tuple(Q() for _ in range(5))
        branches = tuple(Rz(m * 0.4, i=0, ty_total=Q()) for m in range(5))
        t = NPlusMap(summands, branches)
        U = get_unitary(t)

        # k=3 tag bits, pw=1 payload → 4 qubits, dim=16
        assert U.shape == (16, 16)

        # Check each active branch
        for m in range(5):
            alpha = m * 0.4
            expected = np.diag([
                np.exp(-1j * alpha * np.pi / 2),
                np.exp(1j * alpha * np.pi / 2),
            ])
            actual = U[m*2:(m+1)*2, m*2:(m+1)*2]
            assert np.allclose(actual, expected, atol=1e-7), \
                f"Branch {m} mismatch for 5-way NPlusMap"

        # Unused branches (5,6,7) should be identity
        for m in range(5, 8):
            assert np.allclose(U[m*2:(m+1)*2, m*2:(m+1)*2], np.eye(2), atol=1e-7)

    def test_unit_summands(self):
        """NPlusMap with Unit() summands (width 0 payload)."""
        summands = tuple(Unit() for _ in range(4))
        branches = tuple(Id(Unit()) for _ in range(4))
        t = NPlusMap(summands, branches)
        U = get_unitary(t)

        # k=2 tag bits, pw=0 payload → 2 qubits, dim=4
        assert U.shape == (4, 4)
        assert np.allclose(U, np.eye(4), atol=1e-7)
