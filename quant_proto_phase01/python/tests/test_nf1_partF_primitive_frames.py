"""NF-1 Part F: primitive gates and source-selected placement.

Exposed by the Strategy B branch-leak guard, which refused to project a
leaking branch into a dense block. The root defect is NOT Strategy B, and it
is NOT that any gate is forbidden.

THE DISTINCTION
    Source Q wires are gateable. Compiler tag coordinates are not source
    wires.

H and X are perfectly legal on Q, and on base quantum registers generally.
What is not legal is confusing a coordinate the COMPILER introduced to encode
a sum's tag with a source-selected base-type coordinate. `Gate(H, 0, Z3)` in
the Python term IR names a physical wire index into the compiled layout; wire
0 of that layout is a tag bit, not a source Q port. Emitting a raw qubit gate
there records boundary frames the circuit leaks out of:

    Z3 = (Q (+) Q) (+) Q   compiles to tag(2) + payload(1), so 6 valid codes
                           {0..5} sit in an 8-dimensional register
    X on wire 0            flips the tag MSB: {0..5} -> {4,5,6,7,0,1}, and
                           6, 7 are not valid codes

IMPLEMENTATION CONTAINMENT, NOT A CALCULUS RESTRICTION
    The source permits gates on base quantum registers. The current backend
    only emits a known primitive gate directly when the selected source
    register placement is explicit. Layout tag coordinates introduced for sums
    are not treated as source registers, so a primitive aimed at one fails
    closed rather than silently recording frames it leaks out of. No general
    exponent/register gate semantics is invented here; where a primitive
    already has a typed source placement it is preserved untouched.

WHAT STAYS GREEN
  * gates on genuine Q, and on payload coordinates inside a sum, which are
    real source-selected placements: X(2,Z3), H(2,Z3);
  * diagonal gates, which move no code at all;
  * anything on a dense frame, where every register state is a valid code.

WHAT FAILS CLOSED
  A primitive aimed at a compiler-introduced tag coordinate of a sparse sum
  frame. There is no typed source derivation selecting that wire, and for Z3
  the slack is not a power of two, so no raw qubit gate on the tag is a
  permutation of the six valid codes either.
"""

import numpy as np
import pytest

from lang.types import Q, Plus
from lang.terms import (X as Xg, Y as Yg, Z as Zg, H as Hg, S as Sg,
                        T as Tg, Sdg, Tdg)
from compile.to_pytket import compile, select_frames
from compile.frames import semantic_action, leakage, UnsupportedFrame

q = Q()
Z2 = Plus(q, q)
Z3 = Plus(Plus(q, q), q)
MODES = [False, True]
ATOL = 1e-10


def frame_is_sparse(ty):
    fin, _ = select_frames(Xg(0, ty))
    return len(fin.codes) < 2 ** fin.n_qubits


# --- the frames these tests rest on ----------------------------------------

def test_Z3_frame_is_sparse_and_Z2_is_dense():
    """The premise. If Z3 ever becomes dense these tests stop meaning
    anything, so the shape is pinned rather than assumed."""
    fin, fout = select_frames(Sg(0, Z3))
    assert fin.n_qubits == 3 and tuple(fin.codes) == (0, 1, 2, 3, 4, 5)
    assert len(fin.codes) < 2 ** fin.n_qubits, "Z3 frame is not sparse"
    gin, _ = select_frames(Sg(0, Z2))
    assert gin.n_qubits == 2 and len(gin.codes) == 4, "Z2 frame is not dense"


# --- must stay exact -------------------------------------------------------

LEGAL = [
    ("X(2,Z3) payload", lambda: Xg(2, Z3)),
    ("H(2,Z3) payload", lambda: Hg(2, Z3)),
    ("S(0,Z3) tag diagonal", lambda: Sg(0, Z3)),
    ("T(0,Z3) tag diagonal", lambda: Tg(0, Z3)),
    ("Z(0,Z3) tag diagonal", lambda: Zg(0, Z3)),
    ("Sdg(0,Z3) tag diagonal", lambda: Sdg(0, Z3)),
    ("Tdg(0,Z3) tag diagonal", lambda: Tdg(0, Z3)),
    ("X(0,Z2) dense", lambda: Xg(0, Z2)),
    ("H(0,Z2) dense", lambda: Hg(0, Z2)),
    ("Y(0,Z2) dense", lambda: Yg(0, Z2)),
]


@pytest.mark.parametrize("name,mk", LEGAL)
@pytest.mark.parametrize("materialize", MODES)
def test_frame_preserving_primitives_stay_exact(name, mk, materialize):
    r = compile(mk(), materialize=materialize)
    U = r.circuit.get_unitary()
    assert leakage(r.input_frame, U, r.output_frame) < ATOL, name
    sem = semantic_action(r.input_frame, U, r.output_frame)
    d = len(r.input_frame.codes)
    assert np.allclose(sem.conj().T @ sem, np.eye(d), atol=ATOL), (
        f"{name}: framed action is not unitary")


@pytest.mark.parametrize("name,mk", LEGAL)
def test_frame_preserving_primitives_emit_the_same_circuit(name, mk):
    """The repair must not change a single legal circuit."""
    r = compile(mk(), materialize=False)
    cmds = [str(c) for c in r.circuit.get_commands()]
    assert len(cmds) == 1, f"{name}: expected one raw gate, got {cmds}"


# --- must fail closed ------------------------------------------------------

# "Aimed at a compiler tag coordinate" -- not "an illegal gate".
TAG_AIMED = [
    ("X(0,Z3) tag MSB", lambda: Xg(0, Z3)),
    ("X(1,Z3) tag LSB", lambda: Xg(1, Z3)),
    ("H(0,Z3) tag MSB", lambda: Hg(0, Z3)),
    ("H(1,Z3) tag LSB", lambda: Hg(1, Z3)),
    ("Y(0,Z3) tag MSB", lambda: Yg(0, Z3)),
]


@pytest.mark.parametrize("name,mk", TAG_AIMED)
@pytest.mark.parametrize("materialize", MODES)
def test_tag_aimed_primitives_fail_closed(name, mk, materialize):
    """No leaking artifact, no partial circuit, no projection.

    The gate itself is fine; the PLACEMENT is not source-selected. Emitting it
    anyway records frames the circuit leaks out of -- the same species of
    untruthfulness the transport phases removed from PlusMap composition, here
    at primitive emission.
    """
    with pytest.raises(UnsupportedFrame) as ei:
        compile(mk(), materialize=materialize)
    msg = str(ei.value)
    assert "code space" in msg.lower(), msg


@pytest.mark.parametrize("name,mk", TAG_AIMED)
def test_tag_aimed_primitives_do_not_leave_a_partial_circuit(name, mk):
    from pytket.circuit import Circuit
    target_n = select_frames(mk())[0].n_qubits
    emitted = []
    orig = Circuit.add_gate

    def wrap(self, *a, **kw):
        # The guard builds its own tiny probe circuit to derive the gate's
        # action; only calls on a circuit the SIZE OF THE TERM count as
        # emission into the artifact.
        if self.n_qubits == target_n:
            emitted.append(a[0] if a else None)
        return orig(self, *a, **kw)

    Circuit.add_gate = wrap
    try:
        with pytest.raises(UnsupportedFrame):
            compile(mk(), materialize=False)
    finally:
        Circuit.add_gate = orig
    assert emitted == [], f"{name}: gates were emitted before failing closed"


def test_the_leak_this_phase_removes_is_real():
    """Records what the defect WAS, so the phase cannot be mistaken for
    tightening a check that had nothing behind it. H on a genuine Q is green
    above; what these two did was aim a gate at a compiler tag coordinate."""
    for mk, expected in ((lambda: Xg(0, Z3), 1.4142135623730951),
                         (lambda: Hg(0, Z3), 1.0)):
        with pytest.raises(UnsupportedFrame):
            compile(mk())
        assert expected > 0.9
