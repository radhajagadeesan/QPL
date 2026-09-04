"""Tests for NPlusMap with open branches (free variables).

Verifies the Python compiler extension allowing n-ary PlusMap branches to
reference outer-bound variables.
"""

import numpy as np
import pytest
from pytket import Circuit

from lang.terms import (
    Apply, H, Id, Lam, LetPair, NPlusMap, Pair, S, Seq, T, Var, X,
)
from lang.types import Arrow, Plus, Q, Ten, Unit, build_plus_tree
from compile.to_pytket import compile
import compile.to_pytket as TP
from compile.frames import leakage, scatter_code, semantic_action

ATOL = 1e-10
MODES = [False, True]


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


def _three_branch_open_pm():
    """The open occurrence itself: three branches, each USING its own f."""
    ia_ty = Ten(Unit(), Q())
    return NPlusMap((ia_ty, ia_ty, ia_ty),
                    (_apply_f_branch("f0"), _apply_f_branch("f1"),
                     _apply_f_branch("f2")))


def _abstract_three_branch():
    """λinput:((Q⊸Q)⊗((Q⊸Q)⊗((Q⊸Q)⊗sum))). let f0,f1,f2,s = input in s; pm"""
    qq = _qq_ty()
    ia_ty = Ten(Unit(), Q())
    sum_ty = build_plus_tree([ia_ty, ia_ty, ia_ty])
    input_ty = Ten(qq, Ten(qq, Ten(qq, sum_ty)))
    body = LetPair(
        "f0", "rest1", qq, Ten(qq, Ten(qq, sum_ty)), Var("input", input_ty),
        LetPair(
            "f1", "rest2", qq, Ten(qq, sum_ty),
            Var("rest1", Ten(qq, Ten(qq, sum_ty))),
            LetPair(
                "f2", "s", qq, sum_ty, Var("rest2", Ten(qq, sum_ty)),
                Seq(Var("s", sum_ty), _three_branch_open_pm()),
            ),
        ),
    )
    return Lam("input", input_ty, sum_ty, body)


def _applied_three_branch():
    """The same abstraction, applied to concrete H, S and T function values."""
    ia_ty = Ten(Unit(), Q())
    sum_ty = build_plus_tree([ia_ty, ia_ty, ia_ty])
    arg = Pair(_h_value(), Pair(_s_value(), Pair(_t_value(), Id(sum_ty))))
    return Apply(_abstract_three_branch(), arg)


def _closed_reference():
    """The INDEPENDENT reference: an NPlusMap whose branches apply H, S and T
    directly as morphisms. Nothing about it comes from the open path."""
    ia_ty = Ten(Unit(), Q())

    def closed_branch(gate_term):
        return LetPair(
            "i", "a", Unit(), Q(),
            Id(ia_ty),
            Pair(Var("i", Unit()), Seq(Var("a", Q()), gate_term)),
        )

    return NPlusMap(
        (ia_ty, ia_ty, ia_ty),
        (closed_branch(H(0, Q())), closed_branch(S(0, Q())),
         closed_branch(T(0, Q()))))


def _reference_action():
    """The closed reference's own exact framed action -- and it is checked to
    BE exact, so the oracle is not merely "some matrix"."""
    r = compile(_closed_reference(), materialize=True)
    sb = r.selected_boundary
    U = r.circuit.get_unitary()
    assert leakage(sb.ingress, U, sb.egress) < ATOL, (
        "the closed reference itself leaks, so it cannot serve as an oracle")
    assert abs(float(r.circuit.phase)) < ATOL
    A = semantic_action(sb.ingress, U, sb.egress)
    assert A.shape == (6, 6)
    assert np.allclose(A.conj().T @ A, np.eye(6), atol=ATOL, rtol=0.0)
    return A


def _live_plan(term, materialize):
    TP._USE_BLOCK_OBSERVED.clear()
    res = compile(term, materialize=materialize)
    assert TP._USE_BLOCK_OBSERVED, "the open occurrence reached no Block plan"
    return res, TP._USE_BLOCK_OBSERVED[-1]


def test_nplusmap_open_branches_via_apply():
    """NPlusMap with 3 open branches inside an outer Lam, applied with concrete
    gates.

    Each branch USES its own function resource and is completed against the
    two it does not, so the occurrence is a direct sum of three equal blocks:
    64 + 64 + 64 = 192. That is the shape the emission consumes, and it is
    pinned here rather than left to "a circuit came out".
    """
    # The abstraction's branches each carry an unreduced Apply spine; applying
    # concrete function values beta-reduces that spine, so the same occurrence
    # has a smaller root. Both are pinned, because "some block came out" is
    # not a claim about either.
    for term, want, parent in ((_abstract_three_branch(), 64, 192),
                               (_applied_three_branch(), 32, 96)):
        result, pl = _live_plan(term, materialize=False)
        assert result.circuit is not None
        assert {b.index: b.dim for b in pl.branches} == {0: want, 1: want,
                                                         2: want}
        assert pl.ingress.dim == parent and pl.egress.dim == parent
        assert sum(b.dim for b in pl.branches) == pl.ingress.dim, (
            "the parent is the DIRECT SUM of its blocks")
        assert pl.validate()
        # every alternative uses exactly one resource and carries the other two
        for b in pl.branches:
            assert len(b.uses) == 1 and len(b.inactive) == 2
            assert {x.owner_id for x in b.used_bindings} == set(b.uses)


@pytest.mark.parametrize("materialize", MODES)
def test_nplusmap_open_branches_semantic(materialize):
    """EXACT comparison against the independently compiled closed reference.

    "Both produce a non-trivial unitary" is not an oracle: it passes for
    almost any defect. What is compared here is the open occurrence's emitted
    Block, restricted to its OWN main coordinates with the owned function
    resources inactive -- which is precisely the interface the closed
    reference describes -- against that reference's exact framed action.

    The comparison is made at the Block because that is where this phase's
    claim lives. The enclosing beta-reduced Apply's ROOT boundary is a
    separate, pre-existing matter and is not asserted here.
    """
    A_ref = _reference_action()
    _res, pl = _live_plan(_applied_three_branch(), materialize)

    scratch = Circuit(pl.ambient_width)
    TP._emit_open_use_block(scratch, pl)
    W = scratch.get_unitary()
    assert abs(float(scratch.phase)) < ATOL, "the Block carries a global phase"

    main = tuple(pl.tag_wires) + tuple(pl.workspace_wires)
    codes = [scatter_code(c, main, pl.ambient_width) for c in range(6)]
    V = np.array([[W[b, a] for a in codes] for b in codes])
    assert np.allclose(V.conj().T @ V, np.eye(6), atol=ATOL, rtol=0.0), (
        "the visible action is not unitary, so the Block leaks off the sum")
    assert np.allclose(V, A_ref, atol=ATOL, rtol=0.0), (
        f"visible action differs from the independently compiled closed "
        f"H/S/T reference by {np.max(np.abs(V - A_ref)):.3e}")

    # ... and each sector equation, W J_i^- = J_i^+ Vhat_i, on the live plan.
    for b in pl.branches:
        Jm = pl.inclusion(b.index, "ingress")
        Jp = pl.inclusion(b.index, "egress")
        assert len(Jm) == len(Jp) == b.dim
        u_in = np.zeros((1 << pl.ambient_width, b.dim), dtype=complex)
        for j, c in enumerate(pl.tagged_codes(b.index, "ingress")):
            u_in[c, j] = 1.0
        u_out = np.zeros((1 << pl.ambient_width, b.dim), dtype=complex)
        for j, c in enumerate(pl.tagged_codes(b.index, "egress")):
            u_out[c, j] = 1.0
        Vhat = u_out.conj().T @ W @ u_in
        assert np.allclose(W @ u_in, u_out @ Vhat, atol=ATOL, rtol=0.0), (
            f"block {b.index} does not satisfy W J^- = J^+ Vhat: it leaks "
            f"out of its own sector")
        assert np.allclose(Vhat.conj().T @ Vhat, np.eye(b.dim), atol=ATOL,
                           rtol=0.0)
