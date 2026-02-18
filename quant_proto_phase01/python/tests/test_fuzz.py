# tests/test_fuzz.py
"""§9 Property-based fuzz suite (NEWTESTS.md §9).

Generate random well-typed linear terms biased toward nested sums
and check compilation properties:

  PROP-COMP-01: Determinism — same term → same circuit each run
  PROP-EQ-01:   Identity composition laws — id;f == f == f;id
  PROP-COH-01:  Coherence under reassociation — roundtrip == id
"""

import random
import math

import numpy as np
import pytest

from lang.types import Q, Plus, Ten, Unit, width, flatten_plus
from lang.terms import (
    Id, Seq, TenTerm,
    TwistTen, AssocTenL, AssocTenR,
    TwistPlus, AssocPlusL, AssocPlusR,
    H, S, X, CX, PlusMap,
)
from compile.to_pytket import compile
from typing_.check import type_of
from tests.helpers import circuit_fingerprint


# ================================================================
# Type generators
# ================================================================

def plus_depth(ty):
    """Maximum nesting depth of Plus constructors."""
    if isinstance(ty, Plus):
        return 1 + max(plus_depth(ty.left), plus_depth(ty.right))
    if isinstance(ty, Ten):
        return max(plus_depth(ty.left), plus_depth(ty.right))
    return 0


def rand_deep_sum(rng, depth, max_width=4):
    """Generate a left-leaning Plus type with nesting depth >= `depth`.

    Uses Q as the base summand. Width constraint:
      width(Plus^d(Q)) = ceil(log2(2^d)) + 1 = d + 1
    So max depth for width 4 is 3.
    """
    if depth <= 1:
        ty = Plus(Q(), Q())
        return ty if width(ty) <= max_width else Q()
    # Left-biased recursive building
    left = rand_deep_sum(rng, depth - 1, max_width)
    ty = Plus(left, Q())
    if width(ty) <= max_width:
        return ty
    # Try right-biased
    right = rand_deep_sum(rng, depth - 1, max_width)
    ty = Plus(Q(), right)
    if width(ty) <= max_width:
        return ty
    return left  # fallback to whatever we got


def _rand_type(rng, max_width):
    """Generate a random type with width <= max_width."""
    if max_width <= 0:
        return Unit()
    if max_width == 1:
        return Q()

    choice = rng.choice(["Q", "Plus", "Plus", "Ten"])

    if choice == "Q":
        return Q()
    elif choice == "Plus":
        # Binary sum: width = ceil(log2(2)) + max(w_l, w_r) = 1 + max(w_l, w_r)
        max_payload = max_width - 1
        if max_payload <= 0:
            return Q()
        left = _rand_type(rng, max_payload)
        right = _rand_type(rng, max_payload)
        ty = Plus(left, right)
        if width(ty) <= max_width:
            return ty
        return Q()
    elif choice == "Ten":
        split = rng.randint(1, max_width - 1)
        left = _rand_type(rng, split)
        remaining = max_width - width(left)
        if remaining <= 0:
            return left
        right = _rand_type(rng, remaining)
        ty = Ten(left, right)
        if width(ty) <= max_width:
            return ty
        return Q()
    return Q()


def rand_type(rng, max_width=4, sum_bias=True):
    """Generate a random type with width <= max_width.

    If sum_bias is True, 50% of generated types have >= 3 nested Plus layers.
    """
    if sum_bias and rng.random() < 0.5:
        return rand_deep_sum(rng, 3, max_width)
    return _rand_type(rng, max_width)


# ================================================================
# Term generators
# ================================================================

def rand_gate(rng, ty):
    """Random single-qubit gate as an endomorphism on ty."""
    w = width(ty)
    if w == 0:
        return Id(ty)
    gate = rng.choice(["H", "S", "X"])
    i = rng.randrange(w)
    if gate == "H":
        return H(i, ty)
    elif gate == "S":
        return S(i, ty)
    return X(i, ty)


def rand_endo(rng, ty, depth=4):
    """Generate a random endomorphism ty -> ty by composing steps."""
    w = width(ty)
    if w == 0:
        return Id(ty)

    term = Id(ty)
    for _ in range(depth):
        ops = ["gate"]
        # TwistPlus is endomorphic on symmetric sums (A + A)
        if isinstance(ty, Plus) and ty.left == ty.right:
            ops.append("twist_plus")
        # PlusMap with per-branch endomorphisms
        if isinstance(ty, Plus):
            ops.append("plusmap")
        # TwistTen is endomorphic on symmetric tensors (A ⊗ A)
        if isinstance(ty, Ten) and ty.left == ty.right:
            ops.append("twist_ten")

        choice = rng.choice(ops)

        if choice == "twist_plus":
            step = TwistPlus(ty.left, ty.right)
        elif choice == "twist_ten":
            step = TwistTen(ty.left, ty.right)
        elif choice == "plusmap":
            a, b = ty.left, ty.right
            f = rand_gate(rng, a) if width(a) > 0 else Id(a)
            g = rand_gate(rng, b) if width(b) > 0 else Id(b)
            step = PlusMap(a, b, f, g)
        else:
            step = rand_gate(rng, ty)

        term = Seq(term, step)
    return term


# ================================================================
# Unitary comparison
# ================================================================

def compile_unitary(term):
    """Compile term with materialization and return the unitary matrix."""
    compiled = compile(term, materialize=True)
    return compiled.circuit.get_unitary()


# ================================================================
# PROP-COMP-01: Determinism
# ================================================================

NUM_FUZZ = 50


@pytest.mark.parametrize("trial", range(NUM_FUZZ))
def test_prop_comp_01_determinism(trial):
    """Same term compiles to identical circuit each run."""
    rng = random.Random(12345 + trial)
    ty = rand_type(rng, max_width=4, sum_bias=True)
    term = rand_endo(rng, ty, depth=rng.randint(2, 5))

    c1 = compile(term)
    c2 = compile(term)

    assert circuit_fingerprint(c1.circuit) == circuit_fingerprint(c2.circuit), \
        f"Non-deterministic on type {ty}"


# ================================================================
# PROP-EQ-01: Identity composition laws
# ================================================================

@pytest.mark.parametrize("trial", range(NUM_FUZZ))
def test_prop_eq_01_identity_left(trial):
    """id ; f == f (left identity law)."""
    rng = random.Random(54321 + trial)
    ty = rand_type(rng, max_width=4, sum_bias=True)
    f = rand_endo(rng, ty, depth=rng.randint(1, 4))

    lhs = Seq(Id(ty), f)

    u_f = compile_unitary(f)
    u_lhs = compile_unitary(lhs)

    assert np.allclose(u_f, u_lhs, atol=1e-8), \
        f"id;f != f for type {ty}"


@pytest.mark.parametrize("trial", range(NUM_FUZZ))
def test_prop_eq_01_identity_right(trial):
    """f ; id == f (right identity law)."""
    rng = random.Random(67890 + trial)
    ty = rand_type(rng, max_width=4, sum_bias=True)
    f = rand_endo(rng, ty, depth=rng.randint(1, 4))

    rhs = Seq(f, Id(ty))

    u_f = compile_unitary(f)
    u_rhs = compile_unitary(rhs)

    assert np.allclose(u_f, u_rhs, atol=1e-8), \
        f"f;id != f for type {ty}"


# ================================================================
# PROP-COH-01: Coherence under reassociation
# ================================================================

@pytest.mark.parametrize("trial", range(NUM_FUZZ // 2))
def test_prop_coh_01_assoc_plus_roundtrip(trial):
    """assocPL ; assocPR == id on (A+B)+C."""
    rng = random.Random(11111 + trial)
    a = _rand_type(rng, 1)
    b = _rand_type(rng, 1)
    c = _rand_type(rng, 1)

    src_ty = Plus(Plus(a, b), c)
    if width(src_ty) > 4:
        pytest.skip("type too wide")

    roundtrip = Seq(AssocPlusL(a, b, c), AssocPlusR(a, b, c))

    u_rt = compile_unitary(roundtrip)
    u_id = compile_unitary(Id(src_ty))

    assert np.allclose(u_rt, u_id, atol=1e-8), \
        f"assocPL;assocPR != id on {src_ty}"


@pytest.mark.parametrize("trial", range(NUM_FUZZ // 2))
def test_prop_coh_01_twist_plus_involution(trial):
    """twistPlus ; twistPlus == id on A+A."""
    rng = random.Random(22222 + trial)
    a = _rand_type(rng, 2)
    ty = Plus(a, a)
    if width(ty) > 4:
        pytest.skip("type too wide")

    double_twist = Seq(TwistPlus(a, a), TwistPlus(a, a))

    u_dt = compile_unitary(double_twist)
    u_id = compile_unitary(Id(ty))

    assert np.allclose(u_dt, u_id, atol=1e-8), \
        f"twistPlus;twistPlus != id on {ty}"


@pytest.mark.parametrize("trial", range(NUM_FUZZ // 2))
def test_prop_coh_01_assoc_ten_roundtrip(trial):
    """assocTL ; assocTR == id on (A⊗B)⊗C."""
    rng = random.Random(33333 + trial)
    a = _rand_type(rng, 1)
    b = _rand_type(rng, 1)
    c = _rand_type(rng, 1)

    src_ty = Ten(Ten(a, b), c)
    if width(src_ty) > 4:
        pytest.skip("type too wide")

    roundtrip = Seq(AssocTenL(a, b, c), AssocTenR(a, b, c))

    u_rt = compile_unitary(roundtrip)
    u_id = compile_unitary(Id(src_ty))

    assert np.allclose(u_rt, u_id, atol=1e-8), \
        f"assocTL;assocTR != id on {src_ty}"


@pytest.mark.parametrize("trial", range(NUM_FUZZ // 2))
def test_prop_coh_01_plusmap_id_id(trial):
    """PlusMap(Id(A), Id(B)) == Id(A+B)."""
    rng = random.Random(44444 + trial)
    a = _rand_type(rng, 2)
    b = _rand_type(rng, 2)
    ty = Plus(a, b)
    if width(ty) > 4:
        pytest.skip("type too wide")

    plusmap_id = PlusMap(a, b, Id(a), Id(b))

    u_pm = compile_unitary(plusmap_id)
    u_id = compile_unitary(Id(ty))

    assert np.allclose(u_pm, u_id, atol=1e-8), \
        f"PlusMap(Id,Id) != Id on {ty}"
