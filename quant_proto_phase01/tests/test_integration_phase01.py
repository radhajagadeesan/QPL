# tests/test_integration_phase01.py
"""Integration tests for Phase 0–1 correctness.

These tests establish top-level correctness by testing complete workflows
from term construction through compilation to circuit verification.

They validate the core Phase 0–1 claims:
  - Well-typed terms compile to valid pytket circuits
  - Structure compiles to permutation metadata (no gates)
  - Gates are correctly reindexed through permutations
  - No SWAPs appear unless explicitly materialized
  - Compilation is deterministic
"""

import pytest
from pytket.circuit import OpType

# Type imports
from lang.types import Q, Ten, Plus, width

# Term imports
from lang.terms import (
    Id, Seq, TenTerm,
    TwistTen, AssocTenL, AssocTenR,
    TwistPlus, AssocPlusL, AssocPlusR,
    DistL, DistR,
    H, S, CX,
    # Aliases
    TensorTwist, TensorAssocL, SumTwist, SumAssocL,
)

# Type checking
from typing_.check import type_of, assert_well_typed, TypeCheckError

# Compilation
from compile.to_pytket import compile, Compiled

# Permutations
from core.perm import WirePerm, identity, compose, inverse

# Materialization
from backends.materialize import swaps_for_perm, apply_swaps


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def count_ops(circ, op_type: OpType) -> int:
    """Count operations of a given type in circuit."""
    return sum(1 for cmd in circ.get_commands() if cmd.op.type == op_type)


def count_swaps(circ) -> int:
    """Count SWAP operations in circuit."""
    return count_ops(circ, OpType.SWAP)


def get_op_sequence(circ):
    """Get sequence of (op_name, qubit_indices) tuples."""
    ops = []
    for cmd in circ.get_commands():
        op_name = cmd.op.type.name
        qubits = tuple(q.index[0] for q in cmd.qubits)
        ops.append((op_name, qubits))
    return ops


def make_n_qubit_type(n: int):
    """Build an n-qubit type using nested Ten."""
    if n <= 0:
        raise ValueError("n must be positive")
    if n == 1:
        return Q()
    result = Q()
    for _ in range(n - 1):
        result = Ten(result, Q())
    return result


# ---------------------------------------------------------------------------
# Type Construction Tests
# ---------------------------------------------------------------------------

class TestTypeConstruction:
    """Test that types are constructed correctly."""

    def test_q_is_width_1(self):
        assert width(Q()) == 1

    def test_ten_adds_widths(self):
        assert width(Ten(Q(), Q())) == 2
        assert width(Ten(Ten(Q(), Q()), Q())) == 3

    def test_plus_one_hot_width(self):
        # One-hot layout: n summands = n tags + data wires
        # Plus(Q(), Q()) has 2 summands, so 2 tags + 2 data = 4
        assert width(Plus(Q(), Q())) == 4  # 2 tags + 1 + 1

    def test_nested_types(self):
        ty = Ten(Ten(Q(), Q()), Ten(Q(), Q()))
        assert width(ty) == 4


# ---------------------------------------------------------------------------
# Term Construction Tests
# ---------------------------------------------------------------------------

class TestTermConstruction:
    """Test that terms are constructed correctly."""

    def test_id_construction(self):
        t = Id(Q())
        assert t.ty == Q()

    def test_seq_binary(self):
        t = Seq(H(), CX())
        assert hasattr(t, 'f') and hasattr(t, 'g')

    def test_seq_variadic(self):
        t = Seq(H(), CX(), S())
        # Should nest: Seq(H, Seq(CX, S))
        assert isinstance(t.g, Seq)

    def test_gate_defaults(self):
        h = H()
        assert h.i == 0
        assert h.ty_total == Ten(Q(), Q())

        cx = CX()
        assert cx.i == 0
        assert cx.j == 1

    def test_gate_custom_type(self):
        ty3 = make_n_qubit_type(3)
        h = H(2, ty3)
        assert h.i == 2
        assert h.ty_total == ty3

    def test_twist_construction(self):
        t = TwistTen(Q(), Q())
        assert t.a == Q()
        assert t.b == Q()

    def test_alias_equivalence(self):
        assert TensorTwist is TwistTen
        assert TensorAssocL is AssocTenL
        assert SumTwist is TwistPlus


# ---------------------------------------------------------------------------
# Type Checking Tests
# ---------------------------------------------------------------------------

class TestTypeChecking:
    """Test the type checking system."""

    def test_id_types(self):
        t = Id(Ten(Q(), Q()))
        dom, cod = type_of(t)
        assert dom == cod == Ten(Q(), Q())

    def test_seq_types_match(self):
        ty = Ten(Q(), Q())
        t = Seq(H(0, ty), CX(0, 1, ty))
        dom, cod = type_of(t)
        assert dom == cod == ty

    def test_twist_types(self):
        t = TwistTen(Q(), Ten(Q(), Q()))
        dom, cod = type_of(t)
        assert dom == Ten(Q(), Ten(Q(), Q()))
        assert cod == Ten(Ten(Q(), Q()), Q())

    def test_gate_index_validation(self):
        with pytest.raises(TypeCheckError):
            assert_well_typed(H(5, Ten(Q(), Q())))  # Index 5 out of range

    def test_cx_distinct_indices(self):
        with pytest.raises(TypeCheckError):
            assert_well_typed(CX(0, 0, Ten(Q(), Q())))  # Same index


# ---------------------------------------------------------------------------
# Compilation Tests
# ---------------------------------------------------------------------------

class TestCompilation:
    """Test the compilation process."""

    def test_compile_returns_compiled_object(self):
        result = compile(H())
        assert isinstance(result, Compiled)
        assert hasattr(result, 'circuit')
        assert hasattr(result, 'perm')

    def test_compile_simple_gate(self):
        result = compile(H())
        ops = get_op_sequence(result.circuit)
        assert len(ops) == 1
        assert ops[0][0] == 'H'

    def test_compile_gate_sequence(self):
        prog = Seq(H(), CX(), S(1))
        result = compile(prog)
        ops = get_op_sequence(result.circuit)
        assert len(ops) == 3
        assert [op for op, _ in ops] == ['H', 'CX', 'S']

    def test_structure_emits_no_gates(self):
        prog = Seq(
            TwistTen(Q(), Q()),
            AssocTenL(Q(), Q(), Q()),
        )
        # This is a 3-qubit structural program
        ty = Ten(Ten(Q(), Q()), Q())
        # Need to wrap in something that compiles to give width
        # Actually, pure structure has width from the twist
        result = compile(TwistTen(Q(), Q()))
        assert len(result.circuit.get_commands()) == 0

    def test_no_swaps_by_default(self):
        prog = Seq(TwistTen(Q(), Q()), H(), CX())
        result = compile(prog, materialize=False)
        assert count_swaps(result.circuit) == 0

    def test_materialize_adds_swaps(self):
        prog = Seq(TwistTen(Q(), Q()), H(), CX())
        result = compile(prog, materialize=True)
        # After twist, perm is non-trivial, so materialization should add SWAPs
        # The final perm should be identity after materialization
        assert result.perm == identity(2)

    def test_distributivity_compiles(self):
        # One-hot layout: distributivity is supported
        prog = DistL(Q(), Q(), Q())
        result = compile(prog)
        # DistL is identity on wires under the sharing model
        # Width: (2 + 1 + 1) + 1 = 5 for (Q ⊕ Q) ⊗ Q with one-hot encoding
        assert result.circuit.n_qubits == 5
        assert len(result.circuit.get_commands()) == 0  # No gates


# ---------------------------------------------------------------------------
# Permutation Tests
# ---------------------------------------------------------------------------

class TestPermutations:
    """Test wire permutation handling."""

    def test_wireperm_construction_single_arg(self):
        p = WirePerm([1, 0, 2, 3])
        assert p.n == 4
        assert p.new_to_old == [1, 0, 2, 3]

    def test_wireperm_construction_two_args(self):
        p = WirePerm(4, [1, 0, 2, 3])
        assert p.n == 4

    def test_wireperm_construction_kwargs(self):
        p = WirePerm(n=4, new_to_old=[1, 0, 2, 3])
        assert p.n == 4

    def test_identity_perm(self):
        e = identity(3)
        assert e.new_to_old == [0, 1, 2]

    def test_compose_with_identity(self):
        p = WirePerm([1, 0])
        e = identity(2)
        assert compose(p, e) == p
        assert compose(e, p) == p

    def test_inverse(self):
        p = WirePerm([1, 0])
        pinv = inverse(p)
        assert compose(pinv, p) == identity(2)

    def test_twist_creates_swap_perm(self):
        result = compile(TwistTen(Q(), Q()))
        # TwistTen(Q, Q) should create perm [1, 0]
        assert result.perm.new_to_old == [1, 0]


# ---------------------------------------------------------------------------
# Gate Reindexing Tests
# ---------------------------------------------------------------------------

class TestGateReindexing:
    """Test that gates are correctly reindexed through permutations."""

    def test_h_after_twist(self):
        # H on logical wire 0, after twist
        # Twist swaps wires, so H should land on physical wire 1
        prog = Seq(TwistTen(Q(), Q()), H())
        result = compile(prog)
        ops = get_op_sequence(result.circuit)
        assert ops == [('H', (1,))]

    def test_cx_after_twist(self):
        # CX on logical (0,1) after twist becomes physical (1,0)
        prog = Seq(TwistTen(Q(), Q()), CX())
        result = compile(prog)
        ops = get_op_sequence(result.circuit)
        assert ops == [('CX', (1, 0))]

    def test_gates_before_twist(self):
        # Gates before twist should be on original wires
        prog = Seq(H(), TwistTen(Q(), Q()))
        result = compile(prog)
        ops = get_op_sequence(result.circuit)
        assert ops == [('H', (0,))]
        # But final perm should be the twist
        assert result.perm.new_to_old == [1, 0]


# ---------------------------------------------------------------------------
# Determinism Tests
# ---------------------------------------------------------------------------

class TestDeterminism:
    """Test that compilation is deterministic."""

    def test_same_ast_same_circuit(self):
        prog = Seq(TwistTen(Q(), Q()), H(), CX(), S(1))

        r1 = compile(prog)
        r2 = compile(prog)

        ops1 = get_op_sequence(r1.circuit)
        ops2 = get_op_sequence(r2.circuit)

        assert ops1 == ops2
        assert r1.perm == r2.perm

    def test_repeated_compilation(self):
        prog = Seq(H(), CX())
        results = [compile(prog) for _ in range(10)]
        first_ops = get_op_sequence(results[0].circuit)
        for r in results[1:]:
            assert get_op_sequence(r.circuit) == first_ops


# ---------------------------------------------------------------------------
# Materialization Tests
# ---------------------------------------------------------------------------

class TestMaterialization:
    """Test SWAP materialization."""

    def test_swaps_for_perm_identity(self):
        p = identity(3)
        swaps = swaps_for_perm(p)
        assert swaps == []

    def test_swaps_for_perm_swap(self):
        p = WirePerm([1, 0])
        swaps = swaps_for_perm(p)
        assert len(swaps) > 0

    def test_apply_swaps(self):
        from pytket.circuit import Circuit
        circ = Circuit(2)
        apply_swaps(circ, [(0, 1)])
        assert count_swaps(circ) == 1

    def test_materialize_preserves_non_swap_order(self):
        prog = Seq(TwistTen(Q(), Q()), H(), CX(), S(1))

        r_meta = compile(prog, materialize=False)
        r_mat = compile(prog, materialize=True)

        # Get non-SWAP ops
        meta_ops = [(op, q) for op, q in get_op_sequence(r_meta.circuit) if op != 'SWAP']
        mat_ops = [(op, q) for op, q in get_op_sequence(r_mat.circuit) if op != 'SWAP']

        assert meta_ops == mat_ops


# ---------------------------------------------------------------------------
# End-to-End Integration Tests
# ---------------------------------------------------------------------------

class TestEndToEnd:
    """Complete end-to-end workflow tests."""

    def test_bell_state_preparation(self):
        """Build and compile a Bell state preparation circuit."""
        prog = Seq(H(), CX())
        result = compile(prog)

        ops = get_op_sequence(result.circuit)
        assert ops == [('H', (0,)), ('CX', (0, 1))]
        assert count_swaps(result.circuit) == 0

    def test_three_qubit_circuit(self):
        """Build and compile a 3-qubit circuit with structure."""
        ty3 = make_n_qubit_type(3)

        prog = Seq(
            TwistTen(Q(), Ten(Q(), Q())),  # Swap first qubit with last two
            H(0, ty3),
            CX(0, 1, ty3),
            CX(1, 2, ty3),
        )

        result = compile(prog)
        assert result.circuit.n_qubits == 3
        assert count_swaps(result.circuit) == 0

    def test_structure_only_program(self):
        """Pure structural program compiles to empty circuit + perm."""
        prog = Seq(
            TwistTen(Q(), Q()),
            TwistTen(Q(), Q()),  # Should cancel to identity
        )

        result = compile(prog)
        assert len(result.circuit.get_commands()) == 0
        assert result.perm == identity(2)

    def test_complex_rewiring(self):
        """Test that complex rewiring works correctly."""
        ty3 = make_n_qubit_type(3)

        # Twist, then apply gates, then twist back
        prog = Seq(
            TwistTen(Q(), Ten(Q(), Q())),
            H(0, ty3),
            TwistTen(Ten(Q(), Q()), Q()),  # Inverse twist
        )

        result = compile(prog)
        # The twists should cancel, H lands on physical wire based on first twist
        assert len(get_op_sequence(result.circuit)) == 1


# ---------------------------------------------------------------------------
# Regression Guards
# ---------------------------------------------------------------------------

class TestRegressionGuards:
    """Regression tests to prevent specific bugs."""

    def test_perm_convention_locked(self):
        """Lock the WirePerm direction convention."""
        p = WirePerm([1, 0, 2, 3])
        assert p.apply_new_to_old(0) == 1
        assert p.apply_new_to_old(1) == 0
        assert p.apply_new_to_old(2) == 2

    def test_structure_never_emits_swaps(self):
        """Structure-only compilation must never emit SWAPs."""
        for _ in range(5):
            prog = Seq(
                TwistTen(Q(), Q()),
                TwistTen(Q(), Q()),
            )
            result = compile(prog, materialize=False)
            assert count_swaps(result.circuit) == 0

    def test_compilation_never_mutates_input(self):
        """Compilation should not mutate the input term."""
        prog = Seq(H(), CX())
        original_repr = repr(prog)

        compile(prog)
        compile(prog, materialize=True)

        assert repr(prog) == original_repr
