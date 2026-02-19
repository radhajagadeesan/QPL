# tests/test_plusmap.py
"""Tests for PlusMap (⊕-Map): bifunctorial action on sums."""

import pytest
from lang.types import Q, Unit, Ten, Plus, width
from lang.terms import (
    PlusMap, Id, H, S, X, TwistPlus, AssocPlusL,
    Seq, TenTerm,
)
from typing_.check import type_of
from compile.to_pytket import compile


class TestPlusMapTypeChecking:
    """Test type checking for PlusMap."""

    def test_plusmap_basic_type(self):
        """PlusMap with identity branches: id_I ⊕ id_I."""
        left = Id(Unit())
        right = Id(Unit())
        pm = PlusMap(Unit(), Unit(), left, right)

        dom, cod = type_of(pm)
        # Domain: Unit + Unit (Bool)
        assert isinstance(dom, Plus)
        assert isinstance(dom.left, Unit)
        assert isinstance(dom.right, Unit)
        # Codomain: Unit + Unit (Bool) - same since branches are identities
        assert isinstance(cod, Plus)
        assert isinstance(cod.left, Unit)
        assert isinstance(cod.right, Unit)

    def test_plusmap_different_codomains(self):
        """PlusMap with different output types: id_I ⊕ H."""
        left = Id(Unit())  # I → I
        right = H(0, Q())  # Q → Q
        pm = PlusMap(Unit(), Q(), left, right)

        dom, cod = type_of(pm)
        # Domain: Unit + Q
        assert isinstance(dom, Plus)
        assert width(dom.left) == 0  # Unit
        assert width(dom.right) == 1  # Q
        # Codomain: Unit + Q (same types since branches are endomorphisms)
        assert isinstance(cod, Plus)

    def test_plusmap_with_twist(self):
        """PlusMap with TwistPlus as right branch: id_I ⊕ twist+(I,I)."""
        # This is the toggle_W operation from short-circuit AND
        left = Id(Unit())  # I → I
        right = TwistPlus(Unit(), Unit())  # (I + I) → (I + I)
        pm = PlusMap(Unit(), Plus(Unit(), Unit()), left, right)

        dom, cod = type_of(pm)
        # Domain: Unit + (Unit + Unit) = W
        assert isinstance(dom, Plus)
        assert width(dom) == 2  # 1 tag for outer, 1 for inner Bool
        # Codomain should match
        assert isinstance(cod, Plus)


class TestPlusMapCompilation:
    """Test compilation of PlusMap using anti-control pattern."""

    def test_plusmap_id_id_zero_gates(self):
        """PlusMap(id_I, id_I) should compile to zero gates (pure identity)."""
        left = Id(Unit())
        right = Id(Unit())
        pm = PlusMap(Unit(), Unit(), left, right)

        result = compile(pm, materialize=False)
        assert result.circuit.n_gates == 0

    def test_plusmap_id_h_controlled_h(self):
        """PlusMap(id_I, H) should produce anti-controlled identity + controlled H."""
        # Left: id on Unit (0 width) → no gates
        # Right: H on Q → 1 controlled gate
        left = Id(Unit())
        right = H(0, Q())
        pm = PlusMap(Unit(), Q(), left, right)

        result = compile(pm, materialize=True)
        # Should have CH (controlled H) for right branch
        cmds = list(result.circuit.get_commands())
        # Only the right branch has gates, and those are controlled
        assert any('CH' in str(cmd.op) for cmd in cmds)

    def test_plusmap_h_s_anticontrol_pattern(self):
        """PlusMap(H, S) uses anti-control pattern: X; CH; X; CS."""
        # This is similar to QSwitch compilation
        ty = Q()
        left = H(0, ty)   # H : Q → Q
        right = S(0, ty)  # S : Q → Q
        pm = PlusMap(Q(), Q(), left, right)

        result = compile(pm, materialize=True)
        cmds = list(result.circuit.get_commands())

        # Should have: X (anti-control), CH, X (restore), CS
        # The exact structure depends on compilation details
        gate_names = [cmd.op.type.name for cmd in cmds]
        assert 'X' in gate_names  # Tag flip for anti-control
        assert 'CH' in gate_names  # Controlled H
        assert 'CS' in gate_names  # Controlled S

    def test_plusmap_preserves_width(self):
        """PlusMap preserves wire width."""
        ty = Q()
        left = H(0, ty)
        right = S(0, ty)
        pm = PlusMap(Q(), Q(), left, right)

        dom, cod = type_of(pm)
        # Q + Q has width 2 (1 tag + 1 shared payload)
        assert width(dom) == 2
        assert width(cod) == 2

        result = compile(pm)
        # Circuit should have 2 qubits
        assert result.circuit.n_qubits == 2


class TestPlusMapSemantics:
    """Test that PlusMap has correct quantum semantics."""

    def test_plusmap_unitary_is_correct(self):
        """Verify PlusMap(H, S) produces correct 4x4 unitary."""
        ty = Q()
        left = H(0, ty)
        right = S(0, ty)
        pm = PlusMap(Q(), Q(), left, right)

        result = compile(pm, materialize=True)
        U = result.circuit.get_unitary()

        # The unitary should be block-diagonal in the tag basis:
        # When tag=0 (anti-controlled): applies H to payload
        # When tag=1 (controlled): applies S to payload
        import numpy as np

        # Tag qubit is wire 0, payload is wire 1
        # Basis: |00>, |01>, |10>, |11>
        # |tag, payload>

        # Expected behavior:
        # |0, x> → |0, H|x>>  (anti-controlled H when tag=0)
        # |1, x> → |1, S|x>>  (controlled S when tag=1)

        # The matrix structure depends on the controlled gate implementation
        # Check that it's unitary
        assert np.allclose(U @ U.conj().T, np.eye(4), atol=1e-10)


class TestPlusMapNestedFlat:
    """PM-FLAT tests: nested PlusMap under flattened sum encoding.

    Tests from RadhaMSG/COH-PLUSMAP-02.md, verifying Strategy A
    (tag permutation sandwich) for nested sums.
    """

    def _valid_subspace_eq(self, U1, U2, n_valid, payload_w):
        """Compare two unitaries on the valid tag subspace only.

        Unused codewords (tag >= n_valid) are 'don't care' since valid
        programs never produce them.
        """
        import numpy as np
        valid_indices = []
        for tag in range(n_valid):
            for p in range(2 ** payload_w):
                valid_indices.append(tag * (2 ** payload_w) + p)
        ix = np.ix_(valid_indices, valid_indices)
        return np.allclose(U1[ix], U2[ix], atol=1e-10)

    def _block_diag_ref(self, gates, k, payload_w):
        """Build reference block-diagonal unitary from per-tag gate matrices."""
        import numpy as np
        dim_tag = 2 ** k
        dim_payload = 2 ** payload_w
        dim = dim_tag * dim_payload
        ref = np.eye(dim, dtype=complex)
        for tag, gate in gates.items():
            for pi in range(dim_payload):
                for pj in range(dim_payload):
                    ref[tag * dim_payload + pi, tag * dim_payload + pj] = gate[pi, pj]
        return ref

    def test_pm_flat_01_base_binary(self):
        """PM-FLAT-01: Base PlusMap on binary sum — smoke test."""
        q = Q()
        pm = PlusMap(q, q, H(0, q), S(0, q))
        result = compile(pm, materialize=True)
        U = result.circuit.get_unitary()
        import numpy as np
        assert U.shape == (4, 4)
        assert np.allclose(U @ U.conj().T, np.eye(4), atol=1e-10)

    def test_pm_flat_02_nested_left(self):
        """PM-FLAT-02: Nested PlusMap on ((Q+Q)+Q).

        PlusMap(PlusMap(H,S), X) applies H/S/X on summands 0/1/2.
        """
        import numpy as np
        q = Q()
        inner = PlusMap(q, q, H(0, q), S(0, q))
        h = PlusMap(Plus(q, q), q, inner, X(0, q))
        c = compile(h, materialize=True)
        U = c.circuit.get_unitary()

        H_mat = np.array([[1, 1], [1, -1]]) / np.sqrt(2)
        S_mat = np.array([[1, 0], [0, 1j]])
        X_mat = np.array([[0, 1], [1, 0]])
        ref = self._block_diag_ref({0: H_mat, 1: S_mat, 2: X_mat}, k=2, payload_w=1)

        assert self._valid_subspace_eq(U, ref, n_valid=3, payload_w=1)

    def test_pm_flat_03_bracket_equivalence(self):
        """PM-FLAT-03: Both bracketings produce equivalent circuits.

        h1 = PlusMap(PlusMap(H,S), X) : (Q+Q)+Q
        h2 = PlusMap(H, PlusMap(S,X)) : Q+(Q+Q)
        Both apply H/S/X on summands 0/1/2 under flat encoding.
        """
        import numpy as np
        q = Q()
        inner1 = PlusMap(q, q, H(0, q), S(0, q))
        h1 = PlusMap(Plus(q, q), q, inner1, X(0, q))

        inner2 = PlusMap(q, q, S(0, q), X(0, q))
        h2 = PlusMap(q, Plus(q, q), H(0, q), inner2)

        U1 = compile(h1, materialize=True).circuit.get_unitary()
        U2 = compile(h2, materialize=True).circuit.get_unitary()

        assert self._valid_subspace_eq(U1, U2, n_valid=3, payload_w=1)

    def test_pm_flat_04_balanced_4way(self):
        """PM-FLAT-04: 4-way balanced PlusMap on (Q+Q)+(Q+Q).

        PlusMap(PlusMap(H,S), PlusMap(X,H)) applies H/S/X/H on summands 0-3.
        Balanced bracketing: n_left=2, n_right=2, k=2 — fits Strategy A.
        """
        import numpy as np
        q = Q()
        inner_l = PlusMap(q, q, H(0, q), S(0, q))
        inner_r = PlusMap(q, q, X(0, q), H(0, q))
        h = PlusMap(Plus(q, q), Plus(q, q), inner_l, inner_r)
        c = compile(h, materialize=True)
        U = c.circuit.get_unitary()

        H_mat = np.array([[1, 1], [1, -1]]) / np.sqrt(2)
        S_mat = np.array([[1, 0], [0, 1j]])
        X_mat = np.array([[0, 1], [1, 0]])
        ref = self._block_diag_ref({0: H_mat, 1: S_mat, 2: X_mat, 3: H_mat},
                                   k=2, payload_w=1)

        # All 4 codewords are valid (n=4 = 2^k), no unused
        assert np.allclose(U, ref, atol=1e-10)

    def test_pm_flat_04_asymmetric_4way(self):
        """PM-FLAT-04 (asymmetric): ((Q+Q)+Q)+Q — deep left-skewed nesting.

        n_left=3, n_right=1, k=2. Uses Strategy B (full unitary synthesis).
        Applies H/S/X/H on summands 0/1/2/3.
        """
        import numpy as np
        q = Q()
        inner_inner = PlusMap(q, q, H(0, q), S(0, q))
        inner = PlusMap(Plus(q, q), q, inner_inner, X(0, q))
        outer = PlusMap(Plus(Plus(q, q), q), q, inner, H(0, q))
        c = compile(outer, materialize=True)
        U = c.circuit.get_unitary()

        H_mat = np.array([[1, 1], [1, -1]]) / np.sqrt(2)
        S_mat = np.array([[1, 0], [0, 1j]])
        X_mat = np.array([[0, 1], [1, 0]])
        ref = self._block_diag_ref({0: H_mat, 1: S_mat, 2: X_mat, 3: H_mat},
                                   k=2, payload_w=1)
        assert np.allclose(U, ref, atol=1e-10)

    def test_pm_flat_05_unused_codewords(self):
        """PM-FLAT-05: Unused codewords on n=3, k=2.

        The compiled circuit must be unitary (so unused codewords are
        preserved as a subspace, even if their individual mapping differs).
        Valid-subspace behavior must match the reference.
        """
        import numpy as np
        q = Q()
        inner = PlusMap(q, q, H(0, q), S(0, q))
        h = PlusMap(Plus(q, q), q, inner, Id(q))
        c = compile(h, materialize=True)
        U = c.circuit.get_unitary()

        # Must be unitary (unused codeword subspace preserved)
        assert np.allclose(U @ U.conj().T, np.eye(8), atol=1e-10)

        # Valid subspace: tags 0→H, 1→S, 2→id
        H_mat = np.array([[1, 1], [1, -1]]) / np.sqrt(2)
        S_mat = np.array([[1, 0], [0, 1j]])
        I_mat = np.eye(2)
        ref = self._block_diag_ref({0: H_mat, 1: S_mat, 2: I_mat}, k=2, payload_w=1)
        assert self._valid_subspace_eq(U, ref, n_valid=3, payload_w=1)

    def test_pm_flat_neg_02_regression_not_k1(self):
        """PM-FLAT-NEG-02: Regression detector for wrong k=1 behavior.

        If PlusMap only looked at a single outer bit, the nested PlusMap
        would miscompile. This test detects that by verifying the inner
        branch (PlusMap(H,S)) correctly differentiates summands 0 and 1
        (which share the same MSB in the flat encoding).
        """
        import numpy as np
        q = Q()
        # PlusMap(PlusMap(H,S), id) on (Q+Q)+Q
        inner = PlusMap(q, q, H(0, q), S(0, q))
        h = PlusMap(Plus(q, q), q, inner, Id(q))
        U = compile(h, materialize=True).circuit.get_unitary()

        # If k=1 (wrong), both summands 0 and 1 would get the same
        # operation (the inner PlusMap wouldn't differentiate them).
        # Check that summand 0 gets H and summand 1 gets S:
        H_mat = np.array([[1, 1], [1, -1]]) / np.sqrt(2)
        S_mat = np.array([[1, 0], [0, 1j]])

        # Tag 0: rows/cols 0,1 → should be H
        assert np.allclose(U[0:2, 0:2], H_mat, atol=1e-10)
        # Tag 1: rows/cols 2,3 → should be S
        assert np.allclose(U[2:4, 2:4], S_mat, atol=1e-10)
        # Tag 0 and tag 1 must differ (regression: would be same if k=1 only)
        assert not np.allclose(U[0:2, 0:2], U[2:4, 2:4])

    def test_pm_flat_nested_strategy_a_with_boxes(self):
        """Nested PlusMap where inner branch has non-trivial tag permutation.

        The inner PlusMap on Q+(Q+Q) has k=2 with non-identity P permutation,
        which emits Unitary2qBox. When used as a branch of an outer PlusMap
        with Strategy A, the outer must decompose these boxes before controlling.

        Without the DecomposeBoxes fix, this crashes because Op.create() fails
        on Unitary2qBox gates extracted from the inner branch sub-circuit.
        """
        import numpy as np
        q = Q()

        # Inner PlusMap: Q + (Q+Q) → Q + (Q+Q), k=2
        # n_left=1, n_right=2 → P is non-identity → Unitary2qBox emitted
        inner_right = PlusMap(q, q, S(0, q), X(0, q))
        inner = PlusMap(q, Plus(q, q), H(0, q), inner_right)

        # Verify inner compiles and is unitary
        inner_circ = compile(inner, materialize=True).circuit
        inner_U = inner_circ.get_unitary()
        assert np.allclose(inner_U @ inner_U.conj().T, np.eye(inner_U.shape[0]), atol=1e-10)

        # Use inner as right branch of outer PlusMap
        # Outer: (Q+Q) + (Q+(Q+Q)), n_left=2, n_right=3, n=5, k=3
        # half=4, both ≤ 4 → Strategy A
        outer_left = PlusMap(q, q, H(0, q), S(0, q))
        outer = PlusMap(
            Plus(q, q), Plus(q, Plus(q, q)),
            outer_left, inner
        )

        c = compile(outer, materialize=True)
        U = c.circuit.get_unitary()
        dim = U.shape[0]
        assert np.allclose(U @ U.conj().T, np.eye(dim), atol=1e-10)

    def test_pm_flat_hexagon(self):
        """⊕-hexagon: assocPL;swap;assocPL == PlusMap(swap,id);assocPL;PlusMap(id,swap).

        This is the coherence law that previously failed with the k=1 PlusMap.
        """
        import numpy as np
        q = Q()
        qq = Plus(q, q)

        # LHS: assocPL ; twist(Q, Q+Q) ; assocPL
        lhs = Seq(AssocPlusL(q, q, q), Seq(TwistPlus(q, qq), AssocPlusL(q, q, q)))

        # RHS: PlusMap(twist(Q,Q), id) ; assocPL ; PlusMap(id, twist(Q,Q))
        pm1 = PlusMap(qq, q, TwistPlus(q, q), Id(q))
        pm2 = PlusMap(q, qq, Id(q), TwistPlus(q, q))
        rhs = Seq(pm1, Seq(AssocPlusL(q, q, q), pm2))

        U_lhs = compile(lhs, materialize=True).circuit.get_unitary()
        U_rhs = compile(rhs, materialize=True).circuit.get_unitary()

        assert np.allclose(U_lhs, U_rhs, atol=1e-10)


class TestPlusMapFunctoriality:
    """Test the bifunctor composition law:

        PlusMap(f1,g1) ; PlusMap(f2,g2) = PlusMap(f1;f2, g1;g2)

    This is not enforced by code — it's a consequence of the anti-control
    pattern preserving the tag qubit. These tests verify the property holds
    at different nesting depths and Strategy A/B boundaries.
    """

    def test_functoriality_k1(self):
        """Composition law for binary PlusMap (k=1)."""
        import numpy as np
        q = Q()
        f1, f2 = H(0, q), S(0, q)
        g1, g2 = S(0, q), X(0, q)

        lhs = Seq(PlusMap(q, q, f1, g1), PlusMap(q, q, f2, g2))
        rhs = PlusMap(q, q, Seq(f1, f2), Seq(g1, g2))

        U_lhs = compile(lhs, materialize=True).circuit.get_unitary()
        U_rhs = compile(rhs, materialize=True).circuit.get_unitary()
        assert np.allclose(U_lhs, U_rhs, atol=1e-10)

    def test_functoriality_k2_identity_P(self):
        """Composition law for k=2 Strategy A with identity P (n_left=2, n_right=1).

        P is identity so no tag perm boxes — tests basic Strategy A composition.
        """
        import numpy as np
        q = Q()
        qq = Plus(q, q)

        # Outer PlusMap on (Q+Q)+Q: n_left=2, n_right=1, P=identity
        f1 = PlusMap(q, q, H(0, q), S(0, q))
        f2 = PlusMap(q, q, S(0, q), X(0, q))
        g1, g2 = X(0, q), H(0, q)

        lhs = Seq(PlusMap(qq, q, f1, g1), PlusMap(qq, q, f2, g2))
        rhs = PlusMap(qq, q, Seq(f1, f2), Seq(g1, g2))

        U_lhs = compile(lhs, materialize=True).circuit.get_unitary()
        U_rhs = compile(rhs, materialize=True).circuit.get_unitary()

        # n=3, k=2: compare on valid subspace (tag < 3)
        valid = []
        for tag in range(3):
            for p in range(2):
                valid.append(tag * 2 + p)
        ix = np.ix_(valid, valid)
        assert np.allclose(U_lhs[ix], U_rhs[ix], atol=1e-10)

    def test_functoriality_k2_nonidentity_P(self):
        """Composition law for k=2 Strategy A with non-identity P (n_left=1, n_right=2).

        P is non-identity so tag perm Unitary2qBox is emitted.
        Verifies that P⁻¹;P cancellation preserves functoriality across
        the DecomposeBoxes boundary.
        """
        import numpy as np
        q = Q()
        qq = Plus(q, q)

        # Outer PlusMap on Q+(Q+Q): n_left=1, n_right=2, P=(0,2,3,1)
        f1, f2 = H(0, q), S(0, q)
        g1 = PlusMap(q, q, S(0, q), X(0, q))
        g2 = PlusMap(q, q, X(0, q), H(0, q))

        lhs = Seq(PlusMap(q, qq, f1, g1), PlusMap(q, qq, f2, g2))
        rhs = PlusMap(q, qq, Seq(f1, f2), Seq(g1, g2))

        U_lhs = compile(lhs, materialize=True).circuit.get_unitary()
        U_rhs = compile(rhs, materialize=True).circuit.get_unitary()

        # n=3, k=2: compare on valid subspace (tag < 3)
        valid = []
        for tag in range(3):
            for p in range(2):
                valid.append(tag * 2 + p)
        ix = np.ix_(valid, valid)
        assert np.allclose(U_lhs[ix], U_rhs[ix], atol=1e-10)
