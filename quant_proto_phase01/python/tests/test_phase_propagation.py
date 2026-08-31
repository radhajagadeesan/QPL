"""Invariant P: phase propagation through controlled emission.

A scalar z·I is unobservable standing alone and fully observable inside a
branch. Dropping it is therefore silent in isolated tests and wrong in
composition — which is why it was dropped independently at six sites and
each fix missed the others.

Every emission of a compiled subcircuit under coherent control must preserve
that subcircuit's accumulated global phase, promoted to an exact-tag relative
phase on each tag value the branch covers.

Audited sites, all covered below:

  1. PlusMap closed branches            (k=1 and Strategy A k>=2)
  2. PlusMap open branches              (deferred-Lam and plain arms)
  3. NPlusMap                           (open and closed)
  4. PhasedPlusMap                      (own phase parameter AND branch scalar)
  5. Ctrl general fallback
  6. ExpInvolution with identity body   exp(i.theta.I) = e^{i.theta} I
  7. Strategy B width-0 branch          (identity fill must carry the scalar)

Plus the Strategy A tag-base correction: P sends right summand i to tag
(half + i), not (n_left + i). These coincide only when n_left == half.
"""

import math

import numpy as np
import pytest

from lang.types import Unit, Plus, Q, Ten, width
from lang.terms import (
    Id, Seq, PlusMap, NPlusMap, PhasedPlusMap, GlobalPhase,
    Ctrl, ExpInvolution, TwistPlus, X,
)
from compile.to_pytket import compile


QB = Plus(Unit(), Unit())                       # 2 leaves
Z3 = Plus(Unit(), Plus(Unit(), Unit()))         # 3 leaves
Z5 = Plus(Unit(), Plus(Unit(), Plus(Unit(), Plus(Unit(), Unit()))))

PI = math.pi


def _diag(term, n=None):
    U = compile(term, materialize=True).circuit.get_unitary()
    d = np.diag(U)
    return d if n is None else d[:n]


# --------------------------------------------------------------------------
# Strategy A tag base:  right summand i lives at tag (half + i)
# --------------------------------------------------------------------------

def test_asymmetric_strategy_a_phases_every_right_tag():
    """PlusMap(Z3, QBool, Id, GlobalPhase(pi)).

    n_left=3, n_right=2, k=3, half=4. The right summand's two codes live at
    permuted tags 4 and 5. Using base n_left=3 phased tag 3 (an unused filler
    word) and tag 4, missing tag 5 — giving diag(1,1,1,-1,1) where
    diag(1,1,1,-1,-1) is required.
    """
    t = PlusMap(Z3, QB, Id(Z3), GlobalPhase(PI, QB))
    assert np.allclose(np.real(_diag(t, 5)), [1, 1, 1, -1, -1])


def test_symmetric_split_still_correct():
    """The n_left == half case, where the old and new bases coincide."""
    t = PlusMap(QB, QB, Id(QB), GlobalPhase(PI, QB))
    assert np.allclose(np.real(_diag(t, 4)), [1, 1, -1, -1])


# --------------------------------------------------------------------------
# Branch scalars survive controlled emission
# --------------------------------------------------------------------------

def test_plusmap_branch_scalar_is_not_dropped():
    """A GlobalPhase branch must change the compiled unitary."""
    phased = PlusMap(QB, QB, GlobalPhase(PI, QB), Id(QB))
    plain = PlusMap(QB, QB, Id(QB), Id(QB))
    Up = compile(phased, materialize=True).circuit.get_unitary()
    Ui = compile(plain, materialize=True).circuit.get_unitary()
    assert not np.allclose(Up, Ui), "branch scalar was dropped"


def test_nplusmap_branch_scalar_is_not_dropped():
    a = NPlusMap((Q(), Q(), Q()), (GlobalPhase(PI, Q()), Id(Q()), Id(Q())))
    b = NPlusMap((Q(), Q(), Q()), (Id(Q()), Id(Q()), Id(Q())))
    Ua = compile(a, materialize=True).circuit.get_unitary()
    Ub = compile(b, materialize=True).circuit.get_unitary()
    assert not np.allclose(Ua, Ub)


def test_phasedplusmap_composes_own_phase_with_branch_scalar():
    """PhasedPlusMap's own parameter and a branch GlobalPhase multiply.

    phased_omap0(+i) with a phase(-1) left branch == phased_omap0(-i) with a
    plain left branch, since i * (-1) = -i.
    """
    lhs = PhasedPlusMap(PI / 2, QB, QB, GlobalPhase(PI, QB), Id(QB))
    rhs = PhasedPlusMap(-PI / 2, QB, QB, Id(QB), Id(QB))
    Ul = compile(lhs, materialize=True).circuit.get_unitary()
    Ur = compile(rhs, materialize=True).circuit.get_unitary()
    assert np.allclose(Ul, Ur)


def test_ctrl_preserves_body_scalar():
    """Ctrl(GlobalPhase) must become a control-conditional phase, not vanish."""
    c = Ctrl(GlobalPhase(PI, Q()))
    U = compile(c, materialize=True).circuit.get_unitary()
    assert not np.allclose(U, np.eye(U.shape[0])), (
        "Ctrl dropped its body's scalar phase")


def test_exp_involution_identity_body_keeps_scalar():
    """exp(i.theta.I) = e^{i.theta} I is a scalar, not nothing.

    Previously the identity-body shortcut returned early with the comment
    'global phase, skipped'.
    """
    e = ExpInvolution(PI, Id(Q()))
    r = compile(e, materialize=True)
    assert abs(float(r.circuit.phase)) > 1e-9, (
        "exp(i.pi.I) recorded no scalar")


# --------------------------------------------------------------------------
# Involution round-trips: a correctly propagated scalar must square away
# --------------------------------------------------------------------------

@pytest.mark.parametrize("term_pair", [
    ("plusmap", PlusMap(QB, QB, GlobalPhase(PI, QB), Id(QB)), Plus(QB, QB)),
    ("nplusmap", NPlusMap((Q(), Q()), (GlobalPhase(PI, Q()), Id(Q()))),
     Plus(Q(), Q())),
])
def test_negative_one_branch_squares_to_identity(term_pair):
    """(-1)^2 = 1 on every phased tag, so the square must be identity."""
    _, t, ty = term_pair
    U = compile(Seq(t, t), materialize=True).circuit.get_unitary()
    assert np.allclose(U, np.eye(U.shape[0]))


def test_fourth_root_branch_needs_four_applications():
    """A +i branch scalar: U^2 != I but U^4 == I."""
    t = PlusMap(QB, QB, GlobalPhase(PI / 2, QB), Id(QB))
    U2 = compile(Seq(t, t), materialize=True).circuit.get_unitary()
    U4 = compile(Seq(Seq(t, t), Seq(t, t)),
                 materialize=True).circuit.get_unitary()
    assert not np.allclose(U2, np.eye(U2.shape[0]))
    assert np.allclose(U4, np.eye(U4.shape[0]))


# --------------------------------------------------------------------------
# Standalone scalar semantics: phase z ty is z*I, not a per-wire Rz
# --------------------------------------------------------------------------

@pytest.mark.parametrize("ty", [Q(), Ten(Q(), Q()), Unit(), QB])
def test_global_phase_is_scalar_at_every_width(ty):
    """phase(-1, ty) must square to identity at every width.

    The original defect emitted Rz on width-1 payloads (a per-wire relative
    phase proportional to Z, not -I) and dropped the scalar entirely at
    widths 0 and >= 2.
    """
    g = GlobalPhase(PI, ty)
    U = compile(Seq(g, g), materialize=True).circuit.get_unitary()
    assert np.allclose(U, np.eye(U.shape[0]))


def test_global_phase_is_not_identity():
    """It must square to I without itself being I."""
    r = compile(GlobalPhase(PI, Q()), materialize=True)
    assert abs(float(r.circuit.phase)) > 1e-9
