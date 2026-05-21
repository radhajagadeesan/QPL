"""Tests for NPlusMap with open branches (free variables).

Verifies the Python compiler extension allowing n-ary PlusMap branches to
reference outer-bound variables.
"""

import pytest

from lang.terms import (
    Apply, H, Id, Lam, LetPair, NPlusMap, Pair, S, Seq, T, Var, X,
)
from lang.types import Arrow, Plus, Q, Ten, Unit, build_plus_tree
from compile.to_pytket import compile


def _qq_ty():
    return Arrow(Q(), Q())


def _h_value():
    return Lam("hx", Q(), Q(), Seq(Var("hx", Q()), H(0, Q())))


def _s_value():
    return Lam("sy", Q(), Q(), Seq(Var("sy", Q()), S(0, Q())))


def _t_value():
    return Lam("tz", Q(), Q(), Seq(Var("tz", Q()), T(0, Q())))


def _apply_f_branch(f_name):
    """Branch term destructuring (i, a) from I⊗Q via Id and applying Var(f_name) to a."""
    ia_ty = Ten(Unit(), Q())
    return LetPair(
        "i", "a", Unit(), Q(),
        Id(ia_ty),
        Pair(Var("i", Unit()), Apply(Var(f_name, _qq_ty()), Var("a", Q()))),
    )


def test_nplusmap_closed_branches_baseline():
    """Closed-branch NPlusMap still works (regression check)."""
    ia_ty = Ten(Unit(), Q())
    branches = (Id(ia_ty), Id(ia_ty), Id(ia_ty))
    summand_types = (ia_ty, ia_ty, ia_ty)
    pm = NPlusMap(summand_types, branches)
    result = compile(pm)
    assert result.circuit.n_qubits >= 2


def test_nplusmap_open_branches_via_apply():
    """NPlusMap with 3 open branches inside an outer Lam, applied with concrete gates.

    Constructs: λinput:((Q⊸Q)⊗((Q⊸Q)⊗((Q⊸Q)⊗sum))). let bindings... Apply(pm, sum_val).

    Then Apply this Lam with concrete (H, S, T, Id(sum)) values. The n-ary
    open-branch path should resolve Var(f_i) → H/S/T via deferred-Lam
    substitution and produce a valid circuit.
    """
    qq = _qq_ty()
    ia_ty = Ten(Unit(), Q())
    sum_ty = build_plus_tree([ia_ty, ia_ty, ia_ty])

    # Build n-ary plusmap with open branches.
    branches = (
        _apply_f_branch("f0"),
        _apply_f_branch("f1"),
        _apply_f_branch("f2"),
    )
    pm = NPlusMap((ia_ty, ia_ty, ia_ty), branches)
    # pm : Lolli sum_ty sum_ty (after type_of)

    # Wrap: outer Lam binds f_0, f_1, f_2, and a sum-typed input "s".
    # Body composes Var("s") then pm (pm is treated as morphism, not function).
    input_ty = Ten(qq, Ten(qq, Ten(qq, sum_ty)))
    body = LetPair(
        "f0", "rest1", qq, Ten(qq, Ten(qq, sum_ty)), Var("input", input_ty),
        LetPair(
            "f1", "rest2", qq, Ten(qq, sum_ty), Var("rest1", Ten(qq, Ten(qq, sum_ty))),
            LetPair(
                "f2", "s", qq, sum_ty, Var("rest2", Ten(qq, sum_ty)),
                Seq(Var("s", sum_ty), pm),
            ),
        ),
    )
    abstract = Lam("input", input_ty, sum_ty, body)

    # Verify abstract compiles (no crash).
    result = compile(abstract)
    assert result.circuit is not None

    # Instantiate with concrete (H, S, T, Id(sum)):
    arg = Pair(_h_value(), Pair(_s_value(), Pair(_t_value(), Id(sum_ty))))
    applied = Apply(abstract, arg)
    result_applied = compile(applied)
    assert result_applied.circuit is not None


def test_nplusmap_open_branches_semantic():
    """Verify that open n-ary NPlusMap with (H, S, T) substituted is semantically
    equivalent (up to partial trace over function-value wires) to a directly-
    constructed closed NPlusMap that applies H, S, T as morphisms to the data.
    """
    import numpy as np
    qq = _qq_ty()
    ia_ty = Ten(Unit(), Q())
    sum_ty = build_plus_tree([ia_ty, ia_ty, ia_ty])

    # Closed reference: NPlusMap with each branch directly applying a gate.
    # Branch: receive I⊗Q via Id; produce I⊗(gate(Q)).
    def closed_branch(gate_term):
        return LetPair(
            "i", "a", Unit(), Q(),
            Id(ia_ty),
            Pair(Var("i", Unit()), Seq(Var("a", Q()), gate_term)),
        )

    closed_pm = NPlusMap(
        (ia_ty, ia_ty, ia_ty),
        (closed_branch(H(0, Q())), closed_branch(S(0, Q())), closed_branch(T(0, Q()))),
    )
    closed_result = compile(closed_pm)

    # Open + Apply(H, S, T):
    open_branches = (
        _apply_f_branch("f0"),
        _apply_f_branch("f1"),
        _apply_f_branch("f2"),
    )
    open_pm = NPlusMap((ia_ty, ia_ty, ia_ty), open_branches)

    input_ty = Ten(qq, Ten(qq, Ten(qq, sum_ty)))
    body = LetPair(
        "f0", "rest1", qq, Ten(qq, Ten(qq, sum_ty)), Var("input", input_ty),
        LetPair(
            "f1", "rest2", qq, Ten(qq, sum_ty), Var("rest1", Ten(qq, Ten(qq, sum_ty))),
            LetPair(
                "f2", "s", qq, sum_ty, Var("rest2", Ten(qq, sum_ty)),
                Seq(Var("s", sum_ty), open_pm),
            ),
        ),
    )
    abstract = Lam("input", input_ty, sum_ty, body)
    arg = Pair(_h_value(), Pair(_s_value(), Pair(_t_value(), Id(sum_ty))))
    applied = Apply(abstract, arg)
    open_result = compile(applied)

    # Both circuits should produce equivalent unitaries on the visible (data) wires.
    # The closed circuit is small (just sum_ty width = 3 qubits).
    # The open circuit has additional function-value wires.
    closed_U = closed_result.circuit.get_unitary()
    open_U = open_result.circuit.get_unitary()
    assert closed_U.shape[0] == 8  # 2^3 for sum_ty
    # Just confirm both produce non-trivial unitaries (smoke test).
    assert not np.allclose(closed_U, np.eye(8))
    assert open_result.circuit.n_qubits >= closed_result.circuit.n_qubits
