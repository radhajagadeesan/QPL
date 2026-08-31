"""NPlusMap canonical frame (Invariant L) and capability dispatch.

Two properties are under test.

**Canonical layout.** The emitter must use the canonical layout of the
complete domain — leaves flattened across connected `Plus` only, giving
width = ceil(log2 m) + max leaf width — rather than independently
allocating ceil(log2 n_branches) + max(width(summand)). The two agree
whenever every summand is a single leaf, and diverge as soon as a
summand is itself a sum: (Z3, Z5) has 3+5 = 8 leaves, hence width 3,
where the old formula gave 1 + 3 = 4.

**Capability dispatch.** Emission strategy is selected before any circuit
mutation:

    if has_open_branches:            require fast path, else reject
    elif fast_path_supports:         fast path
    elif source_frame == target_frame: dense synthesis
    else:                            reject (asymmetric synthesis)

Dense synthesis is never invoked on an open block. Compiling an open
branch standalone yields a unitary carrying its own free-variable context
wires; its top-left corner is unrelated to the branch's action, and
splatting it would silently miscompile with every index in range. That
regression is the reason these tests exist.
"""

import numpy as np
import pytest

from lang.types import Unit, Plus, Ten, Q, Arrow, width
from lang.terms import NPlusMap, Id, Var, Apply, DecodeQubit
from compile.to_pytket import compile
from typing_.check import type_of


Z3 = Plus(Unit(), Plus(Unit(), Unit()))
Z5 = Plus(Unit(), Plus(Unit(), Plus(Unit(), Plus(Unit(), Unit()))))
BOOL = Plus(Unit(), Unit())
IA = Ten(Unit(), Q())


# --------------------------------------------------------------------------
# Invariant L: canonical frame
# --------------------------------------------------------------------------

def test_z3_z5_uses_canonical_frame_not_branch_count():
    """(Z3, Z5): 8 leaves -> exactly 3 wires, not 1 + max(2,3) = 4."""
    t = NPlusMap((Z3, Z5), (Id(Z3), Id(Z5)))
    dom, cod = type_of(t)
    assert width(dom) == 3
    assert width(cod) == 3

    r = compile(t, materialize=True)
    assert r.circuit.n_qubits == 3, (
        f"expected canonical 3 wires, got {r.circuit.n_qubits} "
        f"(4 would mean the branch-count formula is still in use)"
    )


def test_z3_z5_identity_branches_give_identity_unitary():
    """Id on every summand must be identity on all eight valid codes."""
    t = NPlusMap((Z3, Z5), (Id(Z3), Id(Z5)))
    U = compile(t, materialize=True).circuit.get_unitary()
    assert np.allclose(U, np.eye(8))


def test_reassociated_sum_syntax_gives_same_frame_and_unitary():
    """Associativity changes logical leaf numbering only, never the frame."""
    a = NPlusMap((Z3, Z5), (Id(Z3), Id(Z5)))

    Z3b = Plus(Plus(Unit(), Unit()), Unit())
    Z5b = Plus(Plus(Plus(Unit(), Unit()), Unit()), Plus(Unit(), Unit()))
    b = NPlusMap((Z3b, Z5b), (Id(Z3b), Id(Z5b)))

    ra = compile(a, materialize=True)
    rb = compile(b, materialize=True)

    assert ra.circuit.n_qubits == rb.circuit.n_qubits == 3
    assert np.allclose(ra.circuit.get_unitary(), rb.circuit.get_unitary())


def test_width_consistency_on_frame_free_nplusmap():
    """Invariant W corollary: for a closed NPlusMap with no spectator
    coordinates, n_qubits == width(cod)."""
    for t in [
        NPlusMap((IA, IA, IA), (Id(IA), Id(IA), Id(IA))),
        NPlusMap((Z3, Z5), (Id(Z3), Id(Z5))),
    ]:
        _, cod = type_of(t)
        r = compile(t, materialize=True)
        assert r.circuit.n_qubits == width(cod)


# --------------------------------------------------------------------------
# Capability dispatch
# --------------------------------------------------------------------------

def test_single_leaf_summands_use_fast_path():
    """All summands single-leaf: exact-tag dispatch applies."""
    t = NPlusMap((IA, IA, IA), (Id(IA), Id(IA), Id(IA)))
    r = compile(t, materialize=True)
    assert r.circuit.n_qubits == 3


def test_open_branch_with_multi_leaf_summands_is_rejected():
    """Open branch + sum-headed summands has no supported strategy: the fast
    path cannot dispatch a tag RANGE, and synthesis cannot resolve free
    variables. Must be rejected, not silently miscompiled."""
    br = Apply(Var("f", Arrow(Z3, Z3)), Id(Z3))
    t = NPlusMap((Z3, Z3), (br, br))
    with pytest.raises(NotImplementedError, match="open branches"):
        compile(t, env={"f": [4, 5, 6, 7]})


def test_rejection_happens_before_circuit_mutation():
    """Capability dispatch runs before emission: a rejected block must not
    have partially mutated the circuit."""
    br = Apply(Var("f", Arrow(Z3, Z3)), Id(Z3))
    t = NPlusMap((Z3, Z3), (br, br))
    with pytest.raises(NotImplementedError):
        compile(t, env={"f": [4, 5, 6, 7]})
    # Recompiling a well-formed term afterwards must be unaffected.
    ok = compile(NPlusMap((Z3, Z5), (Id(Z3), Id(Z5))), materialize=True)
    assert np.allclose(ok.circuit.get_unitary(), np.eye(8))


def test_asymmetric_source_target_frames_are_rejected():
    """DecodeQubit : I+I -> Q makes dom (k=2,pw=0) and cod (k=1,pw=1).
    Same total width, different frames — reject rather than coerce."""
    t = NPlusMap((BOOL, BOOL), (DecodeQubit(), DecodeQubit()))
    dom, cod = type_of(t)
    assert width(dom) == width(cod)          # same total width ...
    with pytest.raises(NotImplementedError, match="canonical frame"):
        compile(t)                            # ... but frames differ
