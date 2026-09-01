"""Boundary frames: exact embeddings, serialization, semantic harness.

Checkpoint 1 of the boundary-frame / Align repair. No compilation behaviour
changes here — these tests pin the frame objects themselves.

The property under test is the central invariant: a judgment type determines
the semantic boundary *space* but not its physical *embedding*. Two frames may
share a logical interface, a register width, and a dimension while embedding
the valid basis at different physical indices. Reconciling them is Align's job
(checkpoint 2), never the source type's.
"""

import numpy as np
import pytest

from lang.types import Unit, Q, Ten, Plus, Arrow, width
from compile.frames import (
    Frame, canonical_frame, tensor_frame, flat_frame,
    semantic_action, leakage, assert_framed_semantics,
    ty_to_json, ty_from_json,
)


Z3 = Plus(Unit(), Plus(Unit(), Unit()))
Z5 = Plus(Unit(), Plus(Unit(), Plus(Unit(), Plus(Unit(), Unit()))))
QBOOL = Plus(Unit(), Unit())

X = np.array([[0, 1], [1, 0]], dtype=complex)
Z = np.array([[1, 0], [0, -1]], dtype=complex)


# ---------------------------------------------------------------------------
# Canonical frames agree with the layout policy (Invariant L)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("ty,n,codes", [
    (Unit(),            0, (0,)),
    (Q(),               1, (0, 1)),
    (QBOOL,             1, (0, 1)),
    (Z3,                2, (0, 1, 2)),
    (Z5,                3, (0, 1, 2, 3, 4)),
    (Plus(Q(), Q()),    2, (0, 1, 2, 3)),
    (Ten(Q(), Q()),     2, (0, 1, 2, 3)),
])
def test_canonical_frames(ty, n, codes):
    f = canonical_frame(ty)
    assert f.n_qubits == n == width(ty)
    assert f.codes == codes
    assert f.dim == len(codes)


def test_sum_leaves_get_consecutive_tags():
    """Flat sum: leaf i occupies tag i, payload shared."""
    f = canonical_frame(Plus(Z3, Z5))       # 3 + 5 = 8 leaves
    assert f.n_qubits == 3
    assert f.codes == tuple(range(8))


def test_narrow_leaf_payload_is_high_order():
    """A leaf narrower than the shared payload occupies the FIRST payload
    wires, i.e. the high-order bits of the payload field."""
    f = canonical_frame(Plus(Unit(), Q()))   # leaves: Unit (w0), Q (w1)
    assert f.n_qubits == 2                   # 1 tag + 1 payload
    # Unit leaf at tag 0 payload 0; Q leaf at tag 1 payloads 0,1
    assert f.codes == (0, 2, 3)


# ---------------------------------------------------------------------------
# THE central invariant
# ---------------------------------------------------------------------------

def test_one_interface_admits_two_legitimate_frames():
    """Ten(Z3,Z3): tensor codes [0,1,2,4,5,6,8,9,10] vs flat codes [0..8].

    Same logical interface, same register width, same dimension, different
    embedding. Neither is "the" encoding; Align reconciles them.
    """
    f3 = canonical_frame(Z3)
    tens = tensor_frame(f3, f3)
    flat = flat_frame(Ten(Z3, Z3), 4)

    assert tens.logical == flat.logical
    assert tens.n_qubits == flat.n_qubits == 4
    assert tens.dim == flat.dim == 9

    assert tens.codes == (0, 1, 2, 4, 5, 6, 8, 9, 10)
    assert flat.codes == tuple(range(9))
    assert tens.codes != flat.codes


def test_tensor_frame_matches_canonical_for_that_type():
    """The positional tensor frame IS the canonical frame of the tensor type —
    the divergence is against the *flat* frame, not against canonicity."""
    f3 = canonical_frame(Z3)
    assert tensor_frame(f3, f3).codes == canonical_frame(Ten(Z3, Z3)).codes


def test_unused_codes_are_the_complement():
    tens = tensor_frame(canonical_frame(Z3), canonical_frame(Z3))
    assert tens.unused_codes() == (3, 7, 11, 12, 13, 14, 15)
    assert len(tens.codes) + len(tens.unused_codes()) == 16


# ---------------------------------------------------------------------------
# Isometries
# ---------------------------------------------------------------------------

def test_isometry_is_an_isometry():
    for ty in (Q(), Z3, Ten(Z3, Z3), Plus(Z3, Z5)):
        u = canonical_frame(ty).isometry()
        assert np.allclose(u.conj().T @ u, np.eye(u.shape[1]))


def test_isometry_places_codes():
    f = tensor_frame(canonical_frame(Z3), canonical_frame(Z3))
    u = f.isometry()
    for label, code in enumerate(f.codes):
        assert u[code, label] == 1.0
        assert np.isclose(np.linalg.norm(u[:, label]), 1.0)


def test_encode_decode_round_trip():
    f = tensor_frame(canonical_frame(Z3), canonical_frame(Z3))
    for label in range(f.dim):
        assert f.decode(f.encode(label)) == label
    for unused in f.unused_codes():
        assert f.decode(unused) is None


# ---------------------------------------------------------------------------
# Semantic harness: exact, with leakage
# ---------------------------------------------------------------------------

def test_semantic_comparison_is_exact_not_projective():
    """(iX)(iX) = -I must be distinguishable from +I."""
    fq = canonical_frame(Q())
    got = semantic_action(fq, (1j * X) @ (1j * X), fq)
    assert np.allclose(got, -np.eye(2))
    assert not np.allclose(got, np.eye(2))


def test_z_times_ix_ix_is_minus_z():
    fq = canonical_frame(Q())
    got = semantic_action(fq, Z @ (1j * X) @ (1j * X), fq)
    assert np.allclose(got, -Z)


def test_leakage_zero_for_full_register_frames():
    fq = canonical_frame(Q())
    assert leakage(fq, X, fq) < 1e-12


def test_leakage_detects_escape_from_the_code_space():
    """A gate that maps a valid code onto an unused one must show leakage."""
    f = canonical_frame(Z3)                  # codes (0,1,2) of 4
    G = np.eye(4, dtype=complex)
    G[[2, 3]] = G[[3, 2]]                    # swap code 2 with unused code 3
    assert leakage(f, G, f) > 0.5


def test_assert_framed_semantics_accepts_and_rejects():
    fq = canonical_frame(Q())
    assert_framed_semantics(fq, X, fq, X)
    with pytest.raises(AssertionError, match="framed semantics mismatch"):
        assert_framed_semantics(fq, X, fq, np.eye(2))


def test_semantic_action_rejects_wrong_sized_operator():
    fq = canonical_frame(Q())
    with pytest.raises(ValueError, match="qubits"):
        semantic_action(fq, np.eye(4), fq)


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("ty", [
    Unit(), Q(), QBOOL, Z3, Z5,
    Ten(Z3, Z5), Plus(Z3, Z5), Arrow(Q(), Z3), Ten(Q(), Plus(Q(), Unit())),
])
def test_type_json_round_trip(ty):
    assert ty_from_json(ty_to_json(ty)) == ty


@pytest.mark.parametrize("make", [
    lambda: canonical_frame(Z3),
    lambda: canonical_frame(Ten(Z3, Z5)),
    lambda: tensor_frame(canonical_frame(Z3), canonical_frame(Z3)),
    lambda: flat_frame(Ten(Z3, Z3), 4),
])
def test_frame_json_round_trip(make):
    f = make()
    back = Frame.from_json(f.to_json())
    assert back.logical == f.logical
    assert back.n_qubits == f.n_qubits
    assert back.codes == f.codes
    assert np.allclose(back.isometry(), f.isometry())


def test_round_trip_preserves_the_distinction_between_frames():
    """Serialization must not collapse two frames of the same interface."""
    tens = tensor_frame(canonical_frame(Z3), canonical_frame(Z3))
    flat = flat_frame(Ten(Z3, Z3), 4)
    assert Frame.from_json(tens.to_json()).codes != \
           Frame.from_json(flat.to_json()).codes


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def test_duplicate_codes_rejected():
    with pytest.raises(ValueError, match="not distinct"):
        Frame(logical=Q(), n_qubits=2, codes=(0, 0))


def test_out_of_register_code_rejected():
    with pytest.raises(ValueError, match="outside register"):
        Frame(logical=Q(), n_qubits=1, codes=(0, 5))


# ---------------------------------------------------------------------------
# Compiled carries frames and an explicit global phase
# ---------------------------------------------------------------------------

def test_compiled_tracks_global_phase_explicitly():
    """The backend representation may discard global phase, so Compiled
    records it — required for exact semantic comparison."""
    import math
    from lang.terms import GlobalPhase
    from compile.to_pytket import compile
    r = compile(GlobalPhase(math.pi, Q()), materialize=True)
    assert abs(r.global_phase - 1.0) < 1e-12       # pi radians = 1 half-turn


@pytest.mark.parametrize("term_of", [
    lambda: __import__("lang.terms", fromlist=["Id"]).Id(Q()),
    lambda: __import__("lang.terms", fromlist=["Id"]).Id(Z3),
    lambda: __import__("lang.terms", fromlist=["TwistPlus"]).TwistPlus(Q(), Q()),
    lambda: __import__("lang.terms", fromlist=["H"]).H(0, Q()),
])
def test_frames_are_required_not_optional(term_of):
    """Every successful compilation returns both boundary frames. A missing
    frame is an error, never a silent None to be reconstructed downstream."""
    from compile.to_pytket import compile
    r = compile(term_of())
    assert r.input_frame is not None, "input frame not recorded"
    assert r.output_frame is not None, "output frame not recorded"
    assert isinstance(r.input_frame, Frame)
    assert isinstance(r.output_frame, Frame)


def test_recorded_frames_match_the_compiled_register():
    """A recorded frame must describe the register the artifact actually has."""
    from lang.terms import Id
    from compile.to_pytket import compile
    for ty in (Q(), Z3, Ten(Z3, Z3), Plus(Z3, Z5)):
        r = compile(Id(ty), materialize=True)
        assert r.output_frame.n_qubits == r.circuit.n_qubits
        assert r.output_frame.dim == canonical_frame(ty).dim


def test_missing_frame_is_an_error_not_a_default():
    """The requirement is enforced at the boundary: an artifact with no
    recorded frames raises rather than returning None."""
    import compile.to_pytket as tp
    from lang.terms import Id
    from typing_.check import TypeCheckError
    orig = tp.select_frames
    tp.select_frames = lambda t: (_ for _ in ()).throw(RuntimeError("no frame"))
    try:
        with pytest.raises(TypeCheckError, match="cannot select boundary frames"):
            tp.compile(Id(Q()))
    finally:
        tp.select_frames = orig


# ---------------------------------------------------------------------------
# The unequal-width distributivity mismatch, pinned
# ---------------------------------------------------------------------------

def test_distl_transported_vs_canonical_frames_differ():
    """The §6 mismatch, made visible as two explicit embeddings."""
    from compile.frames import distl_transported_frame, frames_agree
    A, B, C = QBOOL, Ten(QBOOL, QBOOL), QBOOL
    transported = distl_transported_frame(A, B, C)
    consumer = canonical_frame(Plus(Ten(A, C), Ten(B, C)))
    assert transported.codes == (0, 1, 4, 5, 8, 9, 10, 11, 12, 13, 14, 15)
    assert consumer.codes == (0, 2, 4, 6, 8, 9, 10, 11, 12, 13, 14, 15)
    assert transported.logical == consumer.logical
    assert transported.n_qubits == consumer.n_qubits == 4
    assert transported.dim == consumer.dim == 12
    assert not frames_agree(transported, consumer)


def test_distl_transported_sectors_are_recorded():
    from compile.frames import distl_transported_frame
    f = distl_transported_frame(QBOOL, Ten(QBOOL, QBOOL), QBOOL)
    assert [s.codes for s in f.sectors] == [(0, 1, 4, 5),
                                            (8, 9, 10, 11, 12, 13, 14, 15)]
    assert [list(s.tag_values) for s in f.sectors] == [[0], [1]]


@pytest.mark.parametrize("materialize", [False, True])
def test_unequal_width_distl_is_gate_free_and_exact(materialize):
    """The standalone four-qubit gate-free distributor.

    Sizing from judgment types gave a 5-qubit domain against a 4-qubit
    codomain and wrongly suggested no gate-free distributor exists. With the
    derivation-selected shared layout [tag | payload | C], input and output
    carry IDENTICAL physical codes and differ only logically, so dist_l moves
    nothing and its framed semantics is exactly the identity on all 12 valid
    codes, with zero leakage, in both materialization modes.
    """
    from lang.terms import DistL
    from compile.to_pytket import compile
    A, B, C = QBOOL, Ten(QBOOL, QBOOL), QBOOL
    r = compile(DistL(A, B, C), materialize=materialize)

    assert r.circuit.n_qubits == 4
    assert r.circuit.n_gates == 0
    assert r.input_frame.codes == r.output_frame.codes
    assert r.input_frame.logical != r.output_frame.logical
    assert r.output_frame.codes == (0, 1, 4, 5, 8, 9, 10, 11, 12, 13, 14, 15)

    U = r.circuit.get_unitary()
    assert_framed_semantics(r.input_frame, U, r.output_frame, np.eye(12))
    assert leakage(r.input_frame, U, r.output_frame) < 1e-10


def test_distl_mismatch_lives_at_the_splice_not_in_the_distributor():
    """The residual mismatch is against the CANONICAL consumer, which is
    Align's job at the splice -- not the distributor's."""
    from lang.terms import DistL
    from compile.to_pytket import compile
    from compile.frames import frames_agree
    A, B, C = QBOOL, Ten(QBOOL, QBOOL), QBOOL
    out = compile(DistL(A, B, C)).output_frame
    consumer = canonical_frame(Plus(Ten(A, C), Ten(B, C)))
    assert out.n_qubits == consumer.n_qubits == 4
    assert out.dim == consumer.dim == 12
    assert not frames_agree(out, consumer)
    assert consumer.codes == (0, 2, 4, 6, 8, 9, 10, 11, 12, 13, 14, 15)


def test_distl_summand_port_is_sector_conditioned():
    """A fixed wire tuple cannot say 'wire 1 in sector 0, wires 1-2 in
    sector 1'; the sector-conditioned placement can."""
    from lang.terms import DistL
    from compile.to_pytket import compile
    r = compile(DistL(QBOOL, Ten(QBOOL, QBOOL), QBOOL))
    ports = {pt.name: pt for pt in r.output_frame.ports}
    summand = ports["summand"]
    assert summand.is_sector_conditioned
    assert summand.wires_in_sector(0) == (1,)
    assert summand.wires_in_sector(1) == (1, 2)


# ---------------------------------------------------------------------------
# Deterministic complement extension (was the exploratory ToffoliBox probe)
# ---------------------------------------------------------------------------

def test_partial_alignment_is_rejected_by_the_backend():
    """ToffoliBox requires a TOTAL permutation, so extending an alignment over
    the unused code space is a backend requirement, not a tidiness clause."""
    from pytket.circuit import ToffoliBox
    bits = lambda v: tuple(bool((v >> (3 - b)) & 1) for b in range(4))
    partial = {bits(s): bits(t) for s, t in
               zip((0, 1, 2, 4, 5, 6, 8, 9, 10), range(9))}
    with pytest.raises(ValueError, match="not complete"):
        ToffoliBox(partial)


def test_extended_alignment_is_representable_and_correct():
    from pytket import Circuit
    from pytket.circuit import ToffoliBox
    src = tensor_frame(canonical_frame(Z3), canonical_frame(Z3)).codes
    tgt = flat_frame(Ten(Z3, Z3), 4).codes
    rest_s = [i for i in range(16) if i not in set(src)]
    rest_t = [i for i in range(16) if i not in set(tgt)]
    total = dict(zip(src, tgt)); total.update(dict(zip(rest_s, rest_t)))
    bits = lambda v: tuple(bool((v >> (3 - b)) & 1) for b in range(4))
    c = Circuit(4)
    c.add_toffolibox(ToffoliBox({bits(k): bits(v) for k, v in total.items()}),
                     [0, 1, 2, 3])
    U = c.get_unitary()
    for s in src:
        assert abs(U[total[s], s] - 1.0) < 1e-9


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def test_code_count_must_match_semantic_dimension():
    from compile.frames import semantic_dim
    assert semantic_dim(Ten(Z3, Z3)) == 9
    with pytest.raises(ValueError, match="semantic dimension"):
        Frame(logical=Ten(Z3, Z3), n_qubits=4, codes=(0, 1, 2))


def test_bad_port_role_and_repeated_wire_rejected():
    from compile.frames import Port
    with pytest.raises(ValueError, match="role"):
        Port("p", Q(), (0,), role="bogus")
    with pytest.raises(ValueError, match="repeated wire"):
        Port("p", Q(), (0, 0))


def test_port_beyond_register_rejected():
    from compile.frames import Port
    with pytest.raises(ValueError, match="beyond"):
        Frame(logical=Q(), n_qubits=1, codes=(0, 1),
              ports=(Port("p", Q(), (7,)),))


def test_duplicate_sector_tag_rejected():
    from compile.frames import Sector
    with pytest.raises(ValueError, match="claimed by more than one sector"):
        Frame(logical=QBOOL, n_qubits=1, codes=(0, 1),
              sectors=(Sector(0, Unit(), (0,), (0,)),
                       Sector(1, Unit(), (1,), (0,))))


def test_frames_agree_is_not_is_identity_embedding():
    from compile.frames import frames_agree
    tens = tensor_frame(canonical_frame(Z3), canonical_frame(Z3))
    flat = flat_frame(Ten(Z3, Z3), 4)
    assert flat.is_identity_embedding() and not tens.is_identity_embedding()
    assert not frames_agree(tens, flat)
    assert frames_agree(tens, tensor_frame(canonical_frame(Z3),
                                           canonical_frame(Z3)))


def test_expr_validates_against_authoritative_codes():
    from compile.frames import FIdentity
    f = canonical_frame(Ten(Z3, Z3))
    assert f.validate_expr()
    bad = Frame(logical=Ten(Z3, Z3), n_qubits=4, codes=f.codes, expr=FIdentity(4))
    assert not bad.validate_expr()


# ---------------------------------------------------------------------------
# Exactness against COMPILED circuits
# ---------------------------------------------------------------------------

def test_compiled_circuit_exact_phase_ix_ix():
    """(iX)(iX) = -I on a compiled circuit. get_unitary() already includes the
    circuit phase -- one source of truth, not applied twice."""
    import math
    from lang.terms import X as Xg, Seq, GlobalPhase
    from compile.to_pytket import compile
    iX = Seq(Xg(0, Q()), GlobalPhase(math.pi / 2, Q()))
    U = compile(Seq(iX, iX), materialize=True).circuit.get_unitary()
    assert np.allclose(U, -np.eye(2), atol=1e-10, rtol=0.0)
    assert not np.allclose(U, np.eye(2), atol=1e-10, rtol=0.0)


def test_compiled_framed_semantics_with_recorded_frames():
    from lang.terms import X as Xg
    from compile.to_pytket import compile
    r = compile(Xg(0, Q()), materialize=True)
    U = r.circuit.get_unitary()
    assert_framed_semantics(r.input_frame, U, r.output_frame, X)
    assert leakage(r.input_frame, U, r.output_frame) < 1e-12


def test_global_phase_round_trips_through_serialization():
    import json, math
    from lang.terms import GlobalPhase
    from compile.to_pytket import compile
    r = compile(GlobalPhase(math.pi, Q()), materialize=True)
    back = json.loads(json.dumps({"global_phase": r.global_phase,
                                  "output_frame": r.output_frame.to_json()}))
    assert abs(back["global_phase"] - r.global_phase) < 1e-12
    assert Frame.from_json(back["output_frame"]).codes == r.output_frame.codes


# ---------------------------------------------------------------------------
# Truthful frames: pending permutations and spectator registers
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("materialize", [False, True])
def test_twistten_framed_semantics_is_swap_in_both_modes(materialize):
    """Unmaterialized TwistTen emits zero gates and carries a pending perm.
    If the frames claim identity, framed semantics reports identity and the
    perm's meaning is lost -- i.e. WirePerm would still be semantics. The
    output frame must carry the perm, so both modes report SWAP exactly.
    """
    from lang.terms import TwistTen
    from compile.to_pytket import compile
    SWAP = np.array([[1, 0, 0, 0], [0, 0, 1, 0],
                     [0, 1, 0, 0], [0, 0, 0, 1]], dtype=complex)
    r = compile(TwistTen(Q(), Q()), materialize=materialize)
    U = r.circuit.get_unitary()
    assert_framed_semantics(r.input_frame, U, r.output_frame, SWAP)
    assert leakage(r.input_frame, U, r.output_frame) < 1e-12


def test_twistten_unmaterialized_really_has_a_pending_perm():
    """Guards the test above from passing vacuously."""
    from lang.terms import TwistTen
    from compile.to_pytket import compile
    r = compile(TwistTen(Q(), Q()), materialize=False)
    assert r.circuit.n_gates == 0
    assert list(r.perm.new_to_old) == [1, 0]
    assert r.output_frame.codes != r.input_frame.codes


def test_encodequbit_frames_match_the_register():
    """EncodeQubit compiles into two wires while its interface names one; the
    ancilla is recorded as a residual port rather than misdescribed away."""
    from lang.terms import EncodeQubit
    from compile.to_pytket import compile
    r = compile(EncodeQubit())
    assert r.input_frame.n_qubits == r.circuit.n_qubits
    assert r.output_frame.n_qubits == r.circuit.n_qubits
    # The one-hot output is a genuine selection, not a widened input frame:
    # |0> -> |10> and |1> -> |01>.
    assert r.output_frame.codes == (2, 1)
    assert r.input_frame.codes == (0, 2)


@pytest.mark.parametrize("n", [3, 5])
def test_nplusmap_sectors_are_disjoint_exhaustive_and_matched(n):
    from lang.terms import NPlusMap, Id
    from compile.to_pytket import compile
    ia = Ten(Unit(), Q())
    r = compile(NPlusMap(tuple([ia] * n), tuple([Id(ia)] * n)))
    secs = r.output_frame.sectors
    assert len(secs) == n
    codes = [c for s in secs for c in s.codes]
    assert len(codes) == len(set(codes))                 # disjoint
    assert set(codes) == set(r.output_frame.codes)       # exhaustive
    assert [list(s.tag_values) for s in secs] == [[i] for i in range(n)]


# ---------------------------------------------------------------------------
# Occurrence keys and fail-closed selection
# ---------------------------------------------------------------------------

def test_repeated_ast_object_gets_distinct_occurrences():
    """The same AST object used twice is two derivation occurrences at two
    offsets; keying on id() would collapse them."""
    from lang.terms import Id, TenTerm
    from compile.to_pytket import compile
    shared = Id(Q())
    r = compile(TenTerm(shared, shared))
    assert r.circuit.n_qubits == 2
    assert r.output_frame.n_qubits == 2


def test_frame_selection_is_fail_closed():
    """A selection failure raises; it never falls back to sizing from the
    judgment types and proceeding with frames that misdescribe the artifact."""
    import compile.to_pytket as tp
    from lang.terms import Id
    from typing_.check import TypeCheckError
    orig = tp.select_frames
    tp.select_frames = lambda t: (_ for _ in ()).throw(RuntimeError("boom"))
    try:
        with pytest.raises(TypeCheckError, match="cannot select boundary frames"):
            tp.compile(Id(Q()))
    finally:
        tp.select_frames = orig


# ---------------------------------------------------------------------------
# Closed witnesses from review round 2
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("materialize", [False, True])
def test_asymmetric_twistten_agrees_in_both_modes(materialize):
    """TwistTen(Q, Z3) -- asymmetric, so an inverse-direction error in the
    pending-permutation transport cannot hide behind SWAP's self-inverseness.
    Previously: unmaterialized leakage 1.0, semantic difference 1.0."""
    from lang.terms import TwistTen
    from compile.to_pytket import compile
    r = compile(TwistTen(Q(), Z3), materialize=materialize)
    U = r.circuit.get_unitary()
    assert leakage(r.input_frame, U, r.output_frame) < 1e-12
    sem = semantic_action(r.input_frame, U, r.output_frame)
    # The cross-mode comparison lives in the companion test below; here just
    # pin that the framed action is a genuine unitary of the right dimension.
    assert sem.shape == (6, 6)
    assert np.allclose(sem @ sem.conj().T, np.eye(6), atol=1e-12, rtol=0.0)


def test_asymmetric_twistten_modes_agree_exactly():
    from lang.terms import TwistTen
    from compile.to_pytket import compile
    sems = []
    for m in (False, True):
        r = compile(TwistTen(Q(), Z3), materialize=m)
        sems.append(semantic_action(r.input_frame, r.circuit.get_unitary(),
                                    r.output_frame))
    assert np.allclose(sems[0], sems[1], atol=1e-12, rtol=0.0)


@pytest.mark.parametrize("name", ["Encode", "Decode"])
def test_encode_decode_exact_framed_semantics(name):
    """The one-hot pair needs an explicit frame SELECTION: |0>->|10> is not
    the input frame's embedding, so widening could never produce it.
    Previously both recorded codes (0,2) with leakage 1.0."""
    from lang.terms import EncodeQubit, DecodeQubit
    from compile.to_pytket import compile
    t = EncodeQubit() if name == "Encode" else DecodeQubit()
    r = compile(t, materialize=True)
    U = r.circuit.get_unitary()
    assert leakage(r.input_frame, U, r.output_frame) < 1e-12
    sem = semantic_action(r.input_frame, U, r.output_frame)
    assert np.allclose(sem, np.eye(2), atol=1e-10, rtol=0.0)


def test_mismatched_splice_is_reconciled_by_align():
    """Seq(dist_l, Id) is well typed but the two sides sit in different
    frames; it previously returned a 5-qubit circuit with leakage 2.449.

    Align now reconciles them at the splice, so this compiles and is exact.
    """
    from lang.terms import DistL, Seq, Id
    from compile.to_pytket import compile
    A, B, C = QBOOL, Ten(QBOOL, QBOOL), QBOOL
    r = compile(Seq(DistL(A, B, C), Id(Plus(Ten(A, C), Ten(B, C)))))
    U = r.circuit.get_unitary()
    assert leakage(r.input_frame, U, r.output_frame) < 1e-10
    sem = semantic_action(r.input_frame, U, r.output_frame)
    assert sem.shape == (12, 12)
    assert np.allclose(sem, np.eye(12), atol=1e-10, rtol=0.0)


@pytest.mark.parametrize("ctor", ["DistR", "UndistL", "UndistR"])
@pytest.mark.parametrize("materialize", [False, True])
def test_other_asymmetric_distributors_share_one_layout(ctor, materialize):
    """All four distributors select a shared gate-free layout at the sum
    side's width. These three previously returned successful circuits with
    leakage 2.0 / 2.449 / 2.0."""
    import lang.terms as lt
    from compile.to_pytket import compile
    A, B, C = QBOOL, Ten(QBOOL, QBOOL), QBOOL
    r = compile(getattr(lt, ctor)(A, B, C), materialize=materialize)
    assert r.circuit.n_qubits == 4
    assert r.circuit.n_gates == 0
    U = r.circuit.get_unitary()
    assert leakage(r.input_frame, U, r.output_frame) < 1e-10
    sem = semantic_action(r.input_frame, U, r.output_frame)
    # Only the LEFT distributors have coinciding label orders on the two
    # readings. dist_r's dom is A-outer while its cod is summand-outer, so
    # its frames legitimately carry different code lists and its semantics is
    # a non-trivial permutation -- asserting the identity here would hide a
    # wrong map behind a zero-gate circuit.
    assert np.allclose(sem @ sem.conj().T, np.eye(12), atol=1e-10, rtol=0.0)
    if ctor == "UndistL":
        assert r.input_frame.codes == r.output_frame.codes
        assert np.allclose(sem, np.eye(12), atol=1e-10, rtol=0.0)
    else:
        assert r.input_frame.codes != r.output_frame.codes
        assert not np.allclose(sem, np.eye(12), atol=1e-10, rtol=0.0)


def test_nested_sum_sectors_span_multiple_tag_words():
    """NPlusMap((Z3,Z5)): the second summand occupies tag words 3..7, so a
    single integer tag_value misdescribes it."""
    from lang.terms import NPlusMap, Id
    from compile.to_pytket import compile
    r = compile(NPlusMap((Z3, Z5), (Id(Z3), Id(Z5))), materialize=True)
    secs = r.output_frame.sectors
    assert [list(s.tag_values) for s in secs] == [[0, 1, 2], [3, 4, 5, 6, 7]]
    assert [list(s.codes) for s in secs] == [[0, 1, 2], [3, 4, 5, 6, 7]]


def test_allocator_drift_trips_invariant_w():
    """Over-allocating by a wire must trip W, not be relabelled an ancilla."""
    import compile.to_pytket as tp
    from lang.terms import Id, TenTerm
    from typing_.check import TypeCheckError
    orig = tp.select_frames

    def narrower(t):
        fi, fo = orig(t)
        from compile.frames import Frame as _F
        # An emitter reporting a frame NARROWER than the register it will
        # actually use -- exactly the drift W exists to catch.
        return _F(logical=Q(), n_qubits=1, codes=(0, 1), label="narrowed"), fo

    tp.select_frames = lambda t: narrower(t)
    try:
        with pytest.raises(TypeCheckError, match="Invariant W violated"):
            tp.compile(TenTerm(Id(Q()), Id(Q())))
    finally:
        tp.select_frames = orig


def test_compiled_ports_mirror_the_frame_ports():
    """One authoritative location for ports: Frame.ports."""
    from lang.terms import DistL
    from compile.to_pytket import compile
    r = compile(DistL(QBOOL, Ten(QBOOL, QBOOL), QBOOL))
    assert r.input_ports == r.input_frame.ports
    assert r.output_ports == r.output_frame.ports
    assert r.output_ports
