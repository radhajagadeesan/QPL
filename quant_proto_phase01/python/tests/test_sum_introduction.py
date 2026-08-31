"""Coherent ⊕-introduction: Block^sum_{α,β}.

    Γ₁ ⊢ R₁ : A     Γ₂ ⊢ R₂ : B
    ────────────────────────────
    Γ₁, Γ₂ ⊢ [α R₁ | β R₂] : A ⊕ B

Two properties matter and are easy to get wrong in opposite directions.

**Typing is logical, not physical.** type_of returns (Γ₁ ⊗ Γ₂, A ⊕ B). It must
NOT return Plus(Complete(Γ₁,Γ₂), Complete(Γ₂,Γ₁)): that confuses a physical
boundary packing with an object-language type and exposes the branch-selection
tag as source data. The branch packing P^br is a compilation frame.

**This is not state preparation.** It does not prepare α|0⟩ + β|1⟩. The input
selected boundary is already an orthogonal direct sum of the branch-completed
source sectors; the tag is its physical coordinate. The operation is the
unitary block map α W̃₁ ⊕ β W̃₂ with |α| = |β| = 1 — so the constraint is
unit modulus, NOT |α|² + |β|² = 1, and no Hadamard or amplitude preparation
is emitted.

An earlier revision of the design document described this as fresh-tag
amplitude preparation. It was wrong; these tests pin the correct reading.
"""

import math

import numpy as np
import pytest

from lang.types import Unit, Plus, Q, Ten, width
from lang.terms import Sum, Id, GlobalPhase
from compile.to_pytket import compile
from typing_.check import type_of


PI = math.pi


# --------------------------------------------------------------------------
# The indispensable phase test
# --------------------------------------------------------------------------

def test_sum_i_one_gives_diag_i_1_not_identity():
    """Sum_{i,1}(Id₁, Id₁) ⟿ diag(i, 1) on the two valid codewords.

    A build that yields identity here has dropped the branch coefficients.
    """
    t = Sum(PI / 2, 0.0, Id(Unit()), Id(Unit()))
    U = compile(t, materialize=True).circuit.get_unitary()
    assert np.allclose(np.diag(U), [1j, 1.0])
    assert not np.allclose(U, np.eye(2)), "branch coefficients were dropped"


@pytest.mark.parametrize("a_th,b_th,expected", [
    (0.0,      0.0,      [1.0,  1.0]),
    (PI,       0.0,      [-1.0, 1.0]),
    (0.0,      PI,       [1.0, -1.0]),
    (PI / 2,   PI,       [1j,  -1.0]),
    (PI,       PI / 2,   [-1.0, 1j]),
])
def test_branch_coefficients_land_on_their_own_blocks(a_th, b_th, expected):
    """α scales branch 1's whole block, β branch 2's — never mixed."""
    t = Sum(a_th, b_th, Id(Unit()), Id(Unit()))
    U = compile(t, materialize=True).circuit.get_unitary()
    assert np.allclose(np.diag(U), expected)


# --------------------------------------------------------------------------
# Typing: logical endpoints
# --------------------------------------------------------------------------

def test_type_of_returns_logical_endpoints():
    """(Γ₁ ⊗ Γ₂, A ⊕ B), with tensor_context collapsing units."""
    t = Sum(0.0, 0.0, Id(Unit()), Id(Unit()))
    dom, cod = type_of(t)
    assert isinstance(dom, Unit)                    # I ⊗ I collapses to I
    assert cod == Plus(Unit(), Unit())


def test_codomain_is_a_sum_not_a_packed_boundary():
    """The codomain must be A ⊕ B, never a packing of completed contexts."""
    t = Sum(0.0, 0.0, Id(Unit()), Id(Unit()))
    _, cod = type_of(t)
    assert isinstance(cod, Plus)
    assert isinstance(cod.left, Unit) and isinstance(cod.right, Unit)


# --------------------------------------------------------------------------
# Unitarity, and the absence of amplitude preparation
# --------------------------------------------------------------------------

@pytest.mark.parametrize("a_th,b_th", [
    (0.0, 0.0), (PI, 0.0), (PI / 2, PI / 3), (2.0, -1.3),
])
def test_result_is_unitary(a_th, b_th):
    t = Sum(a_th, b_th, Id(Unit()), Id(Unit()))
    U = compile(t, materialize=True).circuit.get_unitary()
    assert np.allclose(U.conj().T @ U, np.eye(U.shape[0]))


def test_no_superposition_is_created():
    """No Hadamard, no amplitude preparation: the map is diagonal on the
    valid codewords, so basis states stay basis states."""
    t = Sum(PI / 2, 0.0, Id(Unit()), Id(Unit()))
    U = compile(t, materialize=True).circuit.get_unitary()
    off_diagonal = U - np.diag(np.diag(U))
    assert np.allclose(off_diagonal, 0), (
        "Sum created superposition; it must be a block map, not state prep")


def test_unit_modulus_weights_not_amplitudes():
    """|α| = |β| = 1 — so both branches keep magnitude 1, which is exactly
    what an amplitude-normalised reading (|α|²+|β|²=1) would NOT give."""
    t = Sum(PI / 3, -PI / 4, Id(Unit()), Id(Unit()))
    U = compile(t, materialize=True).circuit.get_unitary()
    assert np.allclose(np.abs(np.diag(U)), [1.0, 1.0])


# --------------------------------------------------------------------------
# Premise global phases are preserved (Invariant P)
# --------------------------------------------------------------------------

def test_premise_global_phase_is_promoted_not_dropped():
    """A GlobalPhase premise must compose with that branch's coefficient."""
    with_phase = Sum(0.0, 0.0, GlobalPhase(PI, Unit()), Id(Unit()))
    equivalent = Sum(PI, 0.0, Id(Unit()), Id(Unit()))
    Uw = compile(with_phase, materialize=True).circuit.get_unitary()
    Ue = compile(equivalent, materialize=True).circuit.get_unitary()
    assert np.allclose(Uw, Ue), "premise scalar was dropped or misplaced"


# --------------------------------------------------------------------------
# Deferred coverage is explicit, not silent
# --------------------------------------------------------------------------

def test_open_premises_are_rejected_before_emission():
    """Open premises need (Sum-complete)'s identity transport via the frame
    inclusions j_i^ε, which are deferred. Reject rather than approximate."""
    t = Sum(0.0, 0.0, Id(Q()), Id(Unit()))
    with pytest.raises(NotImplementedError, match="open premises"):
        compile(t)
