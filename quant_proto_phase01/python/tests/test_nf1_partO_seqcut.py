"""NF-1 Part O: general SeqCut -- composing selected boundaries across a cut.

A Seq splices a producer's output onto a consumer's input, emitting a real
Align when their embeddings disagree. The physical circuit is

    A G A^dagger F      (F, then A^dagger, then G, then A)

and the composed boundary has to describe THAT circuit, without emitting
anything of its own.

Two things this part exists to keep straight:

  * An artifact's ACTION and its two LAYOUTS are different records. A cut
    composes the layouts. Deriving the composite ingress by inverting the
    producer's physical action gauges that action away -- an X before a
    completed identity would compose to a reported identity -- so the
    producer's action stays in the composed morphism where an oracle can
    see it.

  * WHERE a cut-facing interface lives is a recorded fact, not a width. An
    open sum's effective output Frame spans the whole register while its
    result occupies three coordinates; a nested splice's five-wire output
    genuinely needs all five. Nothing about their shapes tells them apart.
"""

import os
import sys

import numpy as np
import pytest
from pytket import Circuit

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from lang.types import Q, Arrow, Ten, Unit, Plus
from compile.to_pytket import compile, compile_with_artifacts
import compile.to_pytket as TP
from compile.frames import (Frame, BoundaryChart, SelectedBoundary,
                            InterfaceEmbedding, interface_from_frame,
                            restrict_to_cut, CutTransport, seq_cut,
                            ProvenanceError, ProvenanceScope,
                            semantic_action, leakage, scatter_code,
                            gather_code, FRAME_DEFAULT, DERIVED)

q = Q()
MODES = [False, True]
ATOL = 1e-10


# ---------------------------------------------------------------------------
# A. InterfaceEmbedding integrity.
# ---------------------------------------------------------------------------

def _iface(**kw):
    base = dict(ambient_width=4, ordered_wires=(1, 2), local_codes=(0, 1, 2, 3),
                frame_width=2, logical=Ten(q, q), cut_id="cut:here",
                origin_cut="cut:here", polarity="ingress")
    base.update(kw)
    return InterfaceEmbedding(**base)


def test_O1_reconstruction_requires_the_recorded_TYPE():
    """Q(x)Q and Q-oQ are both four states on two wires. An interface that
    validated against either would let a cut splice a pair onto a function."""
    f_ten = Frame(logical=Ten(q, q), n_qubits=2, codes=(0, 1, 2, 3))
    f_arr = Frame(logical=Arrow(q, q), n_qubits=2, codes=(0, 1, 2, 3))
    rec = _iface()
    assert rec.check_reconstructs(f_ten, "t: ")
    with pytest.raises(ProvenanceError) as ei:
        rec.check_reconstructs(f_arr, "t: ")
    assert "typed" in str(ei.value)
    # ... and the codes/width checks still bite
    with pytest.raises(ProvenanceError):
        rec.check_reconstructs(Frame(logical=Ten(q, q), n_qubits=2,
                                     codes=(0, 1, 3, 2)), "t: ")


def test_O2_a_production_record_carries_its_own_identity():
    """A missing cut is not a benign default: it is an interface nobody can
    say they selected."""
    assert _iface().require_provenance("t: ")
    for bad in (dict(cut_id=None), dict(cut_id=""), dict(origin_cut=None),
                dict(origin_cut="")):
        with pytest.raises(ProvenanceError) as ei:
            _iface(**bad).require_provenance("t: ")
        assert "cut identity" in str(ei.value) or "origin" in str(ei.value)


def test_O3_malformed_placements_are_refused():
    with pytest.raises(ProvenanceError):                  # repeated wire
        _iface(ordered_wires=(1, 1))
    with pytest.raises(ProvenanceError):                  # out of range
        _iface(ordered_wires=(1, 9))
    with pytest.raises(ProvenanceError):                  # repeated code
        _iface(local_codes=(0, 1, 1, 3))
    with pytest.raises(ProvenanceError):                  # code out of space
        _iface(local_codes=(0, 1, 2, 9))
    with pytest.raises(ProvenanceError):                  # unknown polarity
        _iface(polarity="sideways")


def test_O4_only_two_frame_shapes_are_supported():
    """Interface width or ambient width. A third shape fails closed rather
    than being widened or injected into one of them."""
    assert _iface(frame_width=2).width == 2
    assert _iface(frame_width=4, complement=0).frame_width == 4
    with pytest.raises(ProvenanceError) as ei:
        _iface(frame_width=3)
    assert "neither its own" in str(ei.value)


def test_O5_the_complement_never_claims_interface_wires():
    """The fixed part and the interface are disjoint by construction."""
    # wire 0 is outside (1,2): legal
    assert _iface(frame_width=4, complement=1 << 3).complement == 8
    with pytest.raises(ProvenanceError) as ei:
        _iface(frame_width=4, complement=1 << 2)      # that is wire 1
    assert "the interface itself occupies" in str(ei.value)
    with pytest.raises(ProvenanceError):
        _iface(frame_width=2, complement=1)           # none at interface width


def test_O6_a_transported_interface_keeps_its_origin():
    """The transport MOVED it; it did not re-select it."""
    tr = CutTransport(wires=(1, 2), ambient_width=4, consumer_codes=(0, 1, 2, 3),
                      producer_codes=(0, 2, 1, 3), forward=(0, 2, 1, 3),
                      inverse=(0, 2, 1, 3), kind="code-permutation", label="t")
    rec = _iface(origin_cut="cut:child")
    moved = rec.transported(tr, cut_id="cut:parent", polarity="egress")
    assert moved.local_codes == (0, 2, 1, 3)
    assert moved.cut_id == "cut:parent"
    assert moved.origin_cut == "cut:child", "the origin was re-minted"
    assert moved.polarity == "egress"
    assert rec.local_codes == (0, 1, 2, 3), "the original was mutated"
    # a transport for a different placement is not this interface's
    other = CutTransport(wires=(0, 3), ambient_width=4,
                         consumer_codes=(0,), producer_codes=(0,),
                         forward=(0, 1, 2, 3), inverse=(0, 1, 2, 3),
                         kind="identity", label="o")
    with pytest.raises(ProvenanceError) as ei:
        rec.transported(other)
    assert "not the same placement" in str(ei.value)


def test_O7_recut_preserves_lineage():
    rec = _iface(cut_id="cut:child", origin_cut="cut:child")
    out = rec.recut("cut:parent")
    assert (out.cut_id, out.origin_cut) == ("cut:parent", "cut:child")
    assert out.ordered_wires == rec.ordered_wires
    assert out.local_codes == rec.local_codes


def test_O8_interface_from_frame_validates_what_it_records():
    """It restricts onto an already-chosen placement and refuses a frame that
    is not constant away from it."""
    f = Frame(logical=Ten(q, q), n_qubits=4, codes=(0, 1, 2, 3))
    rec = interface_from_frame(f, (2, 3), 4, cut_id="c", where="t: ")
    assert rec.ordered_wires == (2, 3) and rec.local_codes == (0, 1, 2, 3)
    assert rec.frame_width == 4 and rec.complement == 0
    assert rec.origin_cut == "c", "selecting here IS the origin"
    rec.check_reconstructs(f, "t: ")
    varying = Frame(logical=Ten(q, q), n_qubits=4, codes=(0, 1, 4, 5))
    with pytest.raises(ProvenanceError) as ei:
        interface_from_frame(varying, (2, 3), 4, cut_id="c", where="t: ")
    assert "varies off the cut" in str(ei.value)


# ---------------------------------------------------------------------------
# B. The action stays in the morphism.
# ---------------------------------------------------------------------------

def _amb(codes, n, label, support=None):
    """An ambient chart MUST say which coordinates it claims."""
    return BoundaryChart(n_qubits=n, codes=tuple(codes), route=None,
                         label=label, space="ambient",
                         support_wires=tuple(range(n) if support is None
                                             else support))



def _tface(codes, place, iface, pol, labels=None, alphabet=(0, 1)):
    """A face over an EXPLICIT cut alphabet.

    The alphabet is the CUT's, not the premise's dimension: a two-state
    producer and a four-state consumer meet at the same one-wire, two-symbol
    cut, with fibres of one and two respectively.
    """
    labels = tuple(range(len(codes))) if labels is None else tuple(labels)
    sizes = [0] * len(alphabet)
    for L in labels:
        sizes[L] += 1
    return CutFace(factor_ids=(f"t:{pol}",), polarity=pol, cut_id="cut:t",
                   origin_cut="cut:t", codes=tuple(codes),
                   placement=tuple(place), labels=labels,
                   n_labels=len(alphabet), alphabet=tuple(alphabet),
                   interface_wires=tuple(iface),
                   fibre_sizes=tuple(sizes), role="residual",
                   whole_chart=True)

def _identity_transport(wires, n):
    size = 1 << len(wires)
    return CutTransport(wires=tuple(wires), ambient_width=n,
                        consumer_codes=tuple(range(size)),
                        producer_codes=tuple(range(size)),
                        forward=tuple(range(size)),
                        inverse=tuple(range(size)), kind="identity", label="t")


@pytest.mark.parametrize("gate,build", [
    ("X", lambda c: c.X(0)),
    ("H", lambda c: c.H(0)),
    ("S", lambda c: c.S(0)),
    ("T", lambda c: c.T(0)),
])
def test_O9_a_producer_action_is_never_gauged_into_the_layout(gate, build):
    """THE soundness gate.

    Producer: a one-qubit gate on the cut coordinate, whose recorded boundary
    is the identity embedding on both polarities -- the gate lives in its
    ACTION. Consumer: a completed identity over the cut AND a carried wire.

    The composed action must be that gate tensored with the identity. A
    construction that pulled the consumer's embedding back through the
    producer would report plain identity for X, and would not even be
    expressible for H.
    """
    N = 2
    CUT = (0,)
    prod = SelectedBoundary(ingress=_amb((0, 2), N, "P-", CUT),
                            egress=_amb((0, 2), N, "P+", CUT),
                            origin="t:producer", authority=FRAME_DEFAULT)
    cons = SelectedBoundary(ingress=_amb((0, 1, 2, 3), N, "C-"),
                            egress=_amb((0, 1, 2, 3), N, "C+"),
                            origin="t:consumer", authority=DERIVED)
    sb, _if, _ef = seq_cut(prod, cons, _identity_transport(CUT, N),
                 producer_support=(CUT, CUT),
                 consumer_support=((0, 1), (0, 1)),
                 producer_face=_tface((0, 1), CUT, CUT, "egress",
                                      labels=(0, 1)),
                 producer_ingress_face=_tface((0, 1), CUT, CUT, "ingress",
                                              labels=(0, 1)),
                 consumer_face=_tface((0, 1, 2, 3), (0, 1), CUT, "ingress",
                                      labels=(0, 0, 1, 1)),
                 consumer_egress_face=_tface((0, 1, 2, 3), (0, 1), CUT,
                                             "egress", labels=(0, 0, 1, 1)),
                 where="t: ", label="t:cut")
    c = Circuit(N)
    build(c)
    U = c.get_unitary()
    got = semantic_action(sb.ingress, U, sb.egress)
    one = Circuit(1)
    build(one)
    want = np.kron(one.get_unitary(), np.eye(2))
    assert np.allclose(got, want, atol=ATOL, rtol=0.0), (
        f"{gate}: composed action is not {gate} (x) I; the producer's action "
        f"was absorbed into a layout")
    assert not np.allclose(got, np.eye(4), atol=ATOL), (
        f"{gate}: composed action collapsed to the identity")
    assert leakage(sb.ingress, U, sb.egress) < ATOL
    assert sb.authority == DERIVED, "a derived premise did not carry through"


def test_O10_the_composite_ingress_is_the_producers_own_embedding():
    """Concretely, for the X witness: K^- is the producer's ingress, not its
    inverse image. (2,3,0,1) was the defect; (0,1,2,3) is the repair."""
    N, CUT = 2, (0,)
    prod = SelectedBoundary(ingress=_amb((0, 2), N, "P-", CUT),
                            egress=_amb((0, 2), N, "P+", CUT),
                            origin="t:p", authority=FRAME_DEFAULT)
    cons = SelectedBoundary(ingress=_amb((0, 1, 2, 3), N, "C-"),
                            egress=_amb((0, 1, 2, 3), N, "C+"),
                            origin="t:c", authority=DERIVED)
    sb, _if, _ef = seq_cut(prod, cons, _identity_transport(CUT, N),
                 producer_support=(CUT, CUT),
                 consumer_support=((0, 1), (0, 1)),
                 producer_face=_tface((0, 1), CUT, CUT, "egress",
                                      labels=(0, 1)),
                 producer_ingress_face=_tface((0, 1), CUT, CUT, "ingress",
                                              labels=(0, 1)),
                 consumer_face=_tface((0, 1, 2, 3), (0, 1), CUT, "ingress",
                                      labels=(0, 0, 1, 1)),
                 consumer_egress_face=_tface((0, 1, 2, 3), (0, 1), CUT,
                                             "egress", labels=(0, 0, 1, 1)),
                 where="t: ")
    assert tuple(sb.ingress.codes) == (0, 1, 2, 3)
    assert tuple(sb.egress.codes) == (0, 1, 2, 3)


# ---------------------------------------------------------------------------
# C. The recorded interface, not the shape, selects the cut.
# ---------------------------------------------------------------------------

def _production(name, materialize=False):
    from test_nf1_beta_tensor import _fixture
    return compile_with_artifacts(_fixture(name), materialize=materialize)


@pytest.mark.parametrize("materialize", MODES)
def test_O11_an_open_sums_interface_is_narrower_than_its_frame(materialize):
    """GATE 1. The effective output Frame spans the register; the result
    occupies three coordinates. Only the record can say which."""
    _res, arts = _production("curried_select_3_abstract", materialize)
    nps = [a for a in arts if type(a.term).__name__ == "NPlusMap"
           and a.egress_interface is not None
           and a.output_frame.n_qubits > a.egress_interface.width]
    assert nps, "no open sum recorded a narrower interface than its frame"
    a = nps[-1]
    assert a.output_frame.n_qubits == 12
    assert a.egress_interface.ordered_wires == (6, 7, 8)
    assert a.egress_interface.local_codes == (0, 1, 2, 3, 4, 5)
    assert a.ingress_interface.ordered_wires == (6, 7, 8)
    a.egress_interface.check_reconstructs(a.output_frame, "t: ")
    a.ingress_interface.check_reconstructs(a.input_frame, "t: ")
    for r in (a.ingress_interface, a.egress_interface):
        assert r.require_provenance("t: ")


def _nested_splice_term():
    """The witness `test_align_acceptance::test_nested_splice` compiles."""
    from lang.terms import Seq, Id, DistL
    from typing_.check import type_of
    QB = Plus(Unit(), Unit())
    d = DistL(QB, Ten(QB, QB), QB)
    dom, cod = type_of(d)
    return Seq(Seq(Id(dom), d), Id(cod))


@pytest.mark.parametrize("materialize", MODES)
def test_O12_a_nested_splice_interface_is_its_whole_frame(materialize):
    """GATE 2, and the ANTI-GEOMETRY discriminator's other half.

    Same shape signature as the open sum -- an effective output Frame at the
    register width, with a narrower nominal result slot -- and the opposite
    answer, because the record says so. Here every coordinate is genuinely
    part of the interface.
    """
    _res, arts = compile_with_artifacts(_nested_splice_term(),
                                        materialize=materialize)
    inner = [a for a in arts if type(a.term).__name__ == "Seq"
             and a.egress_interface is not None]
    assert inner, "no Seq recorded an egress interface"
    a = inner[0]
    rec = a.egress_interface
    assert a.output_frame.n_qubits == rec.width, (
        f"the interface is {rec.width} wide for a "
        f"{a.output_frame.n_qubits}-wire frame; this witness needs all of it")
    assert rec.width == 5, f"expected a 5-wire interface, got {rec.width}"
    rec.check_reconstructs(a.output_frame, "t: ")


def test_O12b_the_record_alone_decides_the_cut_width():
    """ANTI-GEOMETRY. Two interfaces with the SAME ambient width, the same
    frame width, the same nominal slot width and the same logical dimension,
    differing only in what was recorded -- and the recorded wires are what a
    cut would span. Changing only the codes must not move the support.
    """
    n = 5
    narrow_frame = Frame(logical=Ten(q, q), n_qubits=n,
                         codes=(0, 1, 2, 3))          # varies on wires 3,4
    wide_frame = Frame(logical=Ten(q, q), n_qubits=n,
                       codes=(0, 1, 8, 9))            # varies on wires 1,4
    narrow = interface_from_frame(narrow_frame, (3, 4), n, cut_id="c")
    wide = interface_from_frame(wide_frame, (1, 4), n, cut_id="c")
    assert narrow.ambient_width == wide.ambient_width == n
    assert narrow.frame_width == wide.frame_width == n
    assert len(narrow.local_codes) == len(wide.local_codes) == 4
    assert narrow.ordered_wires != wide.ordered_wires, (
        "the two records must differ in exactly the recorded placement")
    # changing only the codes leaves the recorded support alone
    moved = interface_from_frame(
        Frame(logical=Ten(q, q), n_qubits=n, codes=(3, 2, 1, 0)), (3, 4), n,
        cut_id="c")
    assert moved.ordered_wires == narrow.ordered_wires
    assert moved.local_codes != narrow.local_codes


@pytest.mark.parametrize("materialize", MODES)
def test_O13_every_recorded_interface_reconstructs_its_frame(materialize):
    """Across a whole production compilation, not one hand-picked occurrence."""
    _res, arts = _production("curried_select_3_abstract", materialize)
    seen = 0
    for a in arts:
        for rec, frame, pol in ((a.ingress_interface, a.input_frame, "ingress"),
                                (a.egress_interface, a.output_frame, "egress")):
            if rec is None:
                continue
            seen += 1
            assert rec.polarity == pol
            rec.check_reconstructs(frame, f"occ {a.occurrence} {pol}: ")
            assert rec.require_provenance(f"occ {a.occurrence} {pol}: ")
    assert seen > 10, f"only {seen} interfaces recorded; the pass is vacuous"


@pytest.mark.parametrize("materialize", MODES)
def test_O14_production_part_1_compiles_to_its_pre_migration_circuit(materialize):
    """The complete Part 1 is 25 gates; the inner derived pipeline is 23."""
    res, _arts = _production("curried_select_3_abstract", materialize)
    # 12, not 16: the direct-boundary Lam repair removed the double-counted
    # context wires 12-15, which were fixed points of the permutation and
    # untouched by every gate; the 25 gates and the retained perm entries
    # are unchanged wire-for-wire.
    assert res.circuit.n_qubits == 12
    if not materialize:
        assert res.circuit.n_gates == 25
        assert list(res.perm.new_to_old) == [10, 11, 5, 9, 3, 4,
                                             0, 1, 2, 6, 7, 8]


@pytest.mark.parametrize("materialize", MODES)
def test_O15_part_2_is_unchanged(materialize):
    res, _arts = _production("curried_select_3_applied_hst", materialize)
    assert res.circuit.n_qubits == 6
    if not materialize:
        assert res.circuit.n_gates == 25
        assert list(res.perm.new_to_old) == [3, 4, 5, 0, 1, 2]


# ---------------------------------------------------------------------------
# D. The cut is bound by two ORDERED typed interfaces -- never by containment.
# ---------------------------------------------------------------------------

from dataclasses import replace as _dc                                    # noqa
from compile.frames import CutCompletion                                  # noqa
from compile.align import make_cut_transport                              # noqa


def _tr_kw(**kw):
    """An identity transport over `wires`; both placements follow it unless
    a test overrides them deliberately."""
    w = kw.get("wires", (0, 1))
    size = 1 << len(w)
    base = dict(wires=w, ambient_width=kw.get("ambient_width", 4),
                consumer_codes=(0,), producer_codes=(0,),
                forward=tuple(range(size)), inverse=tuple(range(size)),
                kind="identity", label="t",
                producer_wires=w, consumer_wires=w)
    base.update(kw)
    return base


def test_O16_the_same_wire_set_in_two_orders_is_one_cut():
    """GATE 1. A producer that leaves its result on (2,0,1) and a consumer
    that receives on (0,1,2) meet at one cut. Both orders are recorded and
    kept apart -- collapsing them into a single tuple would silently reorder
    the codes."""
    tr = CutTransport(**_tr_kw(wires=(0, 1, 2), ambient_width=3,
                               consumer_codes=(0,), producer_codes=(0,),
                               forward=tuple(range(8)),
                               inverse=tuple(range(8)),
                               producer_wires=(2, 0, 1),
                               consumer_wires=(0, 1, 2)))
    assert tr.producer_wires == (2, 0, 1)
    assert tr.consumer_wires == (0, 1, 2)
    assert tr.producer_wires != tr.consumer_wires, "the orders were merged"
    assert set(tr.producer_wires) == set(tr.consumer_wires)
    assert tr.completion is None, "same cut needs no completion"


def test_O17_strict_containment_without_a_certificate_fails_closed():
    """GATE 2. One wire set containing another is a coincidence, not a
    derivation. Without a recorded reconciliation there is no common cut."""
    with pytest.raises(ProvenanceError) as ei:
        CutTransport(**_tr_kw(wires=(0, 1, 2), producer_wires=(0, 1, 2),
                              consumer_wires=(0, 1)))
    assert "not a containment" in str(ei.value)


@pytest.mark.parametrize("materialize", MODES)
def test_O18_nested_splice_completes_explicitly_to_five_wires(materialize):
    """GATE 3. The fifth coordinate exists because the splice's own typed
    frame reconciliation says so, and it says why."""
    seen = []
    o = TP.make_cut_transport

    def spy(ci, co, wires, amb, label="", **kw):
        tr = o(ci, co, wires, amb, label=label, **kw)
        seen.append(tr)
        return tr

    TP.make_cut_transport = spy
    try:
        compile(_nested_splice_term(), materialize=materialize)
    finally:
        TP.make_cut_transport = o
    assert seen, "no cut transport was selected"
    tr = seen[0]
    assert tr.wires == (0, 1, 2, 3, 4), f"cut is {tr.wires}, want five wires"
    assert tr.completion is not None, "the fifth coordinate has no certificate"
    c = tr.completion
    assert c.widened == "consumer" and (c.from_width, c.to_width) == (4, 5)
    assert "splice_pad" in c.reason and "common" in c.reason
    assert c.producer_wires == (0, 1, 2, 3, 4)
    assert c.consumer_wires == (0, 1, 2, 3)


@pytest.mark.parametrize("materialize", MODES)
def test_O19_the_open_sum_cut_stays_three_wires_with_no_completion(materialize):
    """GATE 4. Both premises already describe the same typed cut, so nothing
    is completed and the register's other thirteen wires stay out of it."""
    seen = []
    o = TP.make_cut_transport

    def spy(ci, co, wires, amb, label="", **kw):
        tr = o(ci, co, wires, amb, label=label, **kw)
        seen.append(tr)
        return tr

    TP.make_cut_transport = spy
    try:
        _production("curried_select_3_abstract", materialize)
    finally:
        TP.make_cut_transport = o
    assert seen, "no cut transport was selected"
    for tr in seen:
        assert tr.wires == (6, 7, 8), f"cut widened to {tr.wires}"
        assert tr.producer_wires == tr.consumer_wires == (6, 7, 8)
        assert tr.completion is None, (
            "a completion was issued for premises that already agree")
        assert tr.ambient_width == 12


def test_O20_a_forged_completion_is_refused():
    """GATE 5. Every way the certificate can fail to describe the cut it is
    attached to."""
    good = CutCompletion(ordered_wires=(0, 1, 2), ambient_width=4,
                         producer_wires=(0, 1, 2), consumer_wires=(0, 1),
                         widened="consumer", from_width=2, to_width=3,
                         reason="test", cut_id="cut:here")
    assert good.to_width == 3
    # a well-formed certificate for THIS cut is accepted
    ok = CutTransport(**_tr_kw(wires=(0, 1, 2), producer_wires=(0, 1, 2),
                               consumer_wires=(0, 1), completion=good))
    assert ok.completion is good
    # one describing a different common placement is not
    other = CutCompletion(ordered_wires=(0, 1, 3), ambient_width=4,
                          producer_wires=(0, 1, 3), consumer_wires=(0, 1),
                          widened="consumer", from_width=2, to_width=3,
                          reason="test")
    with pytest.raises(ProvenanceError) as ei:
        CutTransport(**_tr_kw(wires=(0, 1, 2), producer_wires=(0, 1, 2),
                              consumer_wires=(0, 1), completion=other))
    assert "but the cut is" in str(ei.value)
    bad_amb = CutCompletion(ordered_wires=(0, 1, 2), ambient_width=8,
                            producer_wires=(0, 1, 2), consumer_wires=(0, 1),
                            widened="consumer", from_width=2, to_width=3,
                            reason="test")
    with pytest.raises(ProvenanceError) as ei:
        CutTransport(**_tr_kw(wires=(0, 1, 2), producer_wires=(0, 1, 2),
                              consumer_wires=(0, 1), completion=bad_amb))
    assert "is over 8 wires" in str(ei.value)
    # ... and the certificate's own integrity
    with pytest.raises(ProvenanceError):                    # widens nothing
        CutCompletion(ordered_wires=(0, 1), ambient_width=4,
                      producer_wires=(0, 1), consumer_wires=(0, 1),
                      widened="consumer", from_width=2, to_width=2,
                      reason="r")
    with pytest.raises(ProvenanceError):                    # no reason
        CutCompletion(ordered_wires=(0, 1, 2), ambient_width=4,
                      producer_wires=(0, 1, 2), consumer_wires=(0, 1),
                      widened="consumer", from_width=2, to_width=3, reason="")
    with pytest.raises(ProvenanceError) as ei:              # order destroyed
        CutCompletion(ordered_wires=(0, 1, 2), ambient_width=4,
                      producer_wires=(2, 1, 0), consumer_wires=(0, 1),
                      widened="consumer", from_width=2, to_width=3,
                      reason="r")
    assert "in its own order" in str(ei.value)
    with pytest.raises(ProvenanceError):                    # neither premise
        CutCompletion(ordered_wires=(0, 1, 2), ambient_width=4,
                      producer_wires=(0, 1, 2), consumer_wires=(0, 1),
                      widened="somebody", from_width=2, to_width=3,
                      reason="r")


def test_O21_a_stale_polarity_or_lineage_is_refused_before_mutation():
    """An interface from another cut, or read at the wrong polarity, is not
    this cut's -- and the refusal happens while building the transport, so no
    gate has been emitted."""
    tr = CutTransport(**_tr_kw(wires=(1, 2)))
    rec = _iface(ordered_wires=(1, 2), cut_id="cut:elsewhere",
                 origin_cut="cut:elsewhere")
    assert rec.require_provenance("t: ")
    moved = rec.transported(tr, cut_id="cut:here", polarity="egress")
    assert moved.origin_cut == "cut:elsewhere"
    # a record whose placement is not the transport's is refused outright
    with pytest.raises(ProvenanceError) as ei:
        _iface(ordered_wires=(0, 3)).transported(tr)
    assert "not the same placement" in str(ei.value)
    # ... as is one over a different register
    with pytest.raises(ProvenanceError) as ei:
        _iface(ordered_wires=(1, 2), ambient_width=8).transported(tr)
    assert "the transport is over 4 wires" in str(ei.value)


def _completion(**kw):
    base = dict(ordered_wires=(0, 1, 2), ambient_width=4,
                producer_wires=(0, 1, 2), consumer_wires=(0, 1),
                widened="consumer", from_width=2, to_width=3,
                reason="test reason", cut_id="cut:here",
                producer_logical=Ten(q, Ten(q, q)), consumer_logical=Ten(q, q),
                residual_name="splice_pad")
    base.update(kw)
    return CutCompletion(**base)


def _pad_frame(name="splice_pad"):
    from compile.frames import Port
    return Frame(logical=Ten(q, Ten(q, q)), n_qubits=3,
                 codes=tuple(range(8)),
                 ports=(Port(name, Unit(), (2,), role="residual"),))


def test_O22_completion_pins_side_widths_and_order():
    assert _completion().to_width == 3
    # naming the wrong side is caught by the widths it then has to satisfy:
    # the producer occupies the whole common placement, so it is neither
    # 2 wide nor widened by anything.
    with pytest.raises(ProvenanceError) as ei:
        _completion(widened="producer")
    assert "the producer was 2 wide" in str(ei.value)
    with pytest.raises(ProvenanceError) as ei:
        _completion(widened="producer", from_width=3)
    assert "does not widen anything" in str(ei.value)
    with pytest.raises(ProvenanceError) as ei:                # wrong source
        _completion(from_width=1)
    assert "coordinates" in str(ei.value)
    with pytest.raises(ProvenanceError) as ei:                # wrong target
        _completion(to_width=4)
    assert "records 3 coordinates" in str(ei.value)
    with pytest.raises(ProvenanceError) as ei:                # reordered
        _completion(producer_wires=(2, 0, 1))
    assert "in its own order" in str(ei.value)


def test_O23_completion_pins_type_lineage_and_polarity():
    c = _completion()
    p_if = _iface(ordered_wires=(0, 1, 2), local_codes=tuple(range(8)),
                  frame_width=3, logical=Ten(q, Ten(q, q)),
                  cut_id="cut:here", origin_cut="cut:here", polarity="egress")
    c_if = _iface(ordered_wires=(0, 1), local_codes=(0, 1, 2, 3),
                  frame_width=2, logical=Ten(q, q), cut_id="cut:here",
                  origin_cut="cut:here", polarity="ingress")
    assert c.check_against(p_if, c_if, "cut:here", _pad_frame(), "t: ")

    with pytest.raises(ProvenanceError) as ei:                # wrong type
        c.check_against(_dc(p_if, logical=Arrow(q, q)), c_if, "cut:here",
                        _pad_frame(), "t: ")
    assert "the completion types the producer" in str(ei.value)

    with pytest.raises(ProvenanceError) as ei:                # other occurrence
        c.check_against(p_if, c_if, "cut:elsewhere", _pad_frame(), "t: ")
    assert "another occurrence is not this completion" in str(ei.value)

    with pytest.raises(ProvenanceError) as ei:                # stale polarity
        c.check_against(_dc(p_if, polarity="ingress"), c_if, "cut:here",
                        _pad_frame(), "t: ")
    assert "not egress" in str(ei.value)
    with pytest.raises(ProvenanceError) as ei:
        c.check_against(p_if, _dc(c_if, polarity="egress"), "cut:here",
                        _pad_frame(), "t: ")
    assert "not ingress" in str(ei.value)


def test_O24_absent_typed_pad_evidence_is_refused():
    """The completion claims the narrow premise was padded with typed
    residual ports. If the widened frame does not carry them, the claim is
    unsupported and the cut fails rather than trusting the certificate."""
    c = _completion()
    p_if = _iface(ordered_wires=(0, 1, 2), local_codes=tuple(range(8)),
                  frame_width=3, logical=Ten(q, Ten(q, q)),
                  cut_id="cut:here", origin_cut="cut:here", polarity="egress")
    c_if = _iface(ordered_wires=(0, 1), local_codes=(0, 1, 2, 3),
                  frame_width=2, logical=Ten(q, q), cut_id="cut:here",
                  origin_cut="cut:here", polarity="ingress")
    with pytest.raises(ProvenanceError) as ei:
        c.check_against(p_if, c_if, "cut:here", _pad_frame("something_else"),
                        "t: ")
    assert "the evidence is absent" in str(ei.value)
    bare = Frame(logical=Ten(q, Ten(q, q)), n_qubits=3, codes=tuple(range(8)))
    with pytest.raises(ProvenanceError):
        c.check_against(p_if, c_if, "cut:here", bare, "t: ")


def test_O25_the_reason_is_diagnostic_only():
    """It must be present -- a completion cannot be issued saying nothing --
    but nothing may branch on its content."""
    a = _completion(reason="because the registers differ")
    b = _completion(reason="zzz")
    for f in ("ordered_wires", "producer_wires", "consumer_wires", "widened",
              "from_width", "to_width", "cut_id", "residual_name"):
        assert getattr(a, f) == getattr(b, f)
    p_if = _iface(ordered_wires=(0, 1, 2), local_codes=tuple(range(8)),
                  frame_width=3, logical=Ten(q, Ten(q, q)),
                  cut_id="cut:here", origin_cut="cut:here", polarity="egress")
    c_if = _iface(ordered_wires=(0, 1), local_codes=(0, 1, 2, 3),
                  frame_width=2, logical=Ten(q, q), cut_id="cut:here",
                  origin_cut="cut:here", polarity="ingress")
    assert a.check_against(p_if, c_if, "cut:here", _pad_frame(), "t: ")
    assert b.check_against(p_if, c_if, "cut:here", _pad_frame(), "t: ")
    with pytest.raises(ProvenanceError):
        _completion(reason="")
    # no production source parses it
    import inspect
    import compile.frames as F
    src = inspect.getsource(F.CutCompletion)
    assert ".reason ==" not in src and "in self.reason" not in src


def test_O26_the_production_completion_carries_its_evidence():
    """The real nested_splice certificate, end to end."""
    seen = []
    o = TP.make_cut_transport

    def spy(ci, co, wires, amb, label="", **kw):
        tr = o(ci, co, wires, amb, label=label, **kw)
        seen.append(tr)
        return tr

    TP.make_cut_transport = spy
    try:
        compile(_nested_splice_term())
    finally:
        TP.make_cut_transport = o
    c = seen[0].completion
    assert c.residual_name == "splice_pad"
    assert c.cut_id is not None and c.cut_id != ""
    assert c.producer_logical is not None and c.consumer_logical is not None
    assert c.widened == "consumer" and (c.from_width, c.to_width) == (4, 5)


# ---------------------------------------------------------------------------
# E. C0 -- factor identity and the per-polarity cut face.
# ---------------------------------------------------------------------------

from compile.frames import CutFace, ChartFactor, ChartRoute, scatter_repart   # noqa
from compile.frames import par_then_repart                                    # noqa


def _faces(name="curried_select_3_abstract", materialize=False):
    from test_nf1_beta_tensor import _fixture
    arts = []
    OA = TP.Artifact

    def spy(*a, **kw):
        x = OA(*a, **kw)
        arts.append(x)
        return x

    TP.Artifact = spy
    try:
        compile(_fixture(name), materialize=materialize)
    except Exception:
        pass
    finally:
        TP.Artifact = OA
    return arts


def test_O27_a_factor_id_is_not_a_resource_owner():
    """`owner` says which RESOURCE a factor carries; `factor_id` says which
    FACTOR it is. Two factors can carry one resource, and a frame-default
    factor carries none at all yet still has to be nameable."""
    with pytest.raises(ProvenanceError) as ei:
        ChartFactor(name="u", owner=None, n_qubits=1, codes=(0, 1))
    assert "without a factor_id" in str(ei.value)
    f = ChartFactor(factor_id="f:1", name="u", owner=None, n_qubits=1,
                    codes=(0, 1))
    assert f.factor_id == "f:1" and f.owner is None and f.logical is None
    g = ChartFactor(factor_id="f:2", name="u", owner="own:same", n_qubits=1,
                    codes=(0, 1))
    h = ChartFactor(factor_id="f:3", name="u", owner="own:same", n_qubits=1,
                    codes=(0, 1))
    assert g.owner == h.owner and g.factor_id != h.factor_id, (
        "one resource carried by two factors must stay two factors")


def test_O28_every_production_factor_is_named():
    arts = _faces()
    seen = 0
    for a in arts:
        sb = a.selected_boundary
        if sb is None:
            continue
        for ch in (sb.ingress, sb.egress):
            if ch.route is None:
                continue
            for f in ch.route.parts:
                seen += 1
                assert f.factor_id, f"{f.name} carries no factor_id"
    assert seen > 5, f"only {seen} routed factors seen; the pass is vacuous"


def test_O29_the_two_polarities_share_one_factor_lineage():
    """A face is per-polarity, but the factor it names is one lineage."""
    arts = _faces()
    both = [a for a in arts
            if a.ingress_face is not None and a.egress_face is not None]
    assert both, "no occurrence recorded both faces"
    for a in both:
        i, e = a.ingress_face, a.egress_face
        assert i.polarity == "ingress" and e.polarity == "egress"
        assert i.whole_chart == e.whole_chart, (
            f"occ {a.occurrence}: the two polarities disagree on form")
        # A Seq's external ingress comes from its PRODUCER and its external
        # egress from its CONSUMER, so the two polarities need not name one
        # factor. What each must do is keep the lineage of the premise that
        # actually presented it, through every recut.
        assert i.cut_id == e.cut_id, (
            f"occ {a.occurrence}: the two faces are read at different cuts")
        for f in (i, e):
            assert f.origin_cut is not None, (
                f"occ {a.occurrence}: a face lost its originating lineage")
            assert f.cut_id is not None


def _atomic_chart(n=2, codes=(0, 1, 2, 3)):
    return BoundaryChart(n_qubits=n, codes=tuple(codes), route=None,
                         label="c", space="local",
                         support_wires=tuple(range(n)))


def _atomic_face(**kw):
    base = dict(factor_ids=("mint:1",), polarity="ingress", cut_id="cut:here",
                origin_cut="cut:here", codes=(0, 1, 2, 3),
                placement=(0, 1), labels=(0, 1, 2, 3), n_labels=4,
                interface_wires=(6, 7), fibre_sizes=(1, 1, 1, 1),
                role="residual", whole_chart=True)
    base.update(kw)
    return CutFace(**base)


def test_O30_a_route_less_subface_or_hidden_state_is_refused():
    """A route-less premise cannot say what else it carries, so only an
    exhaustive face is acceptable."""
    ch = _atomic_chart()
    assert _atomic_face().check_against(ch, "cut:here", "t: ")
    # a proper subface: fewer states than the chart
    with pytest.raises(ProvenanceError) as ei:
        _atomic_face(codes=(0, 1), labels=(0, 1), n_labels=2,
                     fibre_sizes=(1, 1)).check_against(ch, "cut:here", "t: ")
    assert "does not exhaust the premise" in str(ei.value)
    # not marked exhaustive at all
    with pytest.raises(ProvenanceError) as ei:
        _atomic_face(whole_chart=False).check_against(ch, "cut:here", "t: ")
    assert "EXHAUSTIVE atomic face" in str(ei.value)
    # HIDDEN SUPPORT: the face claims a coordinate the chart does not record
    narrow = BoundaryChart(n_qubits=3, codes=(0, 1, 2, 3), route=None,
                           label="c", space="local", support_wires=(1, 2))
    with pytest.raises(ProvenanceError) as ei:
        _atomic_face(placement=(0, 1, 2)).check_against(narrow, "cut:here",
                                                        "t: ")
    assert "recorded support" in str(ei.value)
    # right count and right support, WRONG states
    reordered = BoundaryChart(n_qubits=2, codes=(0, 1, 3, 2), route=None,
                              label="c", space="local", support_wires=(0, 1))
    with pytest.raises(ProvenanceError) as ei:
        _atomic_face().check_against(reordered, "cut:here", "t: ")
    assert "reassembles" in str(ei.value)


def test_O31_right_codes_with_the_wrong_factor_id_is_refused():
    """Identity, not geometry. A factor with the same codes on the same
    placement but a different recorded id is a different factor."""
    f = ChartFactor(factor_id="the:one", name="K", owner="own:k", n_qubits=2,
                    codes=(0, 1, 2, 3), role="operand", logical=Ten(q, q))
    rep, pl = scatter_repart(((0, 1),), 2)
    ch = par_then_repart((f,), rep, 2, "c", placements=pl, kind="scatter")
    face = CutFace(factor_ids=("the:one",), polarity="ingress",
                   cut_id="cut:here", origin_cut="cut:here",
                   codes=(0, 1, 2, 3), placement=(0, 1),
                   labels=(0, 1, 2, 3), n_labels=4, interface_wires=(0, 1),
                   role="operand", logical=Ten(q, q))
    assert face.check_against(ch, "cut:here", "t: ")
    wrong = _dc(face, factor_ids=("someone:else",))
    with pytest.raises(ProvenanceError) as ei:
        wrong.check_against(ch, "cut:here", "t: ")
    assert "resolves" in str(ei.value)


def test_O32_stale_wrong_polarity_and_uncovered_faces_are_refused():
    ch = _atomic_chart()
    with pytest.raises(ProvenanceError) as ei:                # stale
        _atomic_face().check_against(ch, "cut:elsewhere", "t: ")
    assert "stale face" in str(ei.value)
    with pytest.raises(ProvenanceError):                      # bad polarity
        _atomic_face(polarity="sideways")
    with pytest.raises(ProvenanceError) as ei:                # label uncovered
        _atomic_face(labels=(0, 0, 1, 1), n_labels=4, fibre_sizes=())
    assert "have no states" in str(ei.value)
    with pytest.raises(ProvenanceError) as ei:                # fibres disagree
        _atomic_face(labels=(0, 0, 1, 1), n_labels=2, fibre_sizes=(1, 3))
    assert "records fibre sizes" in str(ei.value)
    with pytest.raises(ProvenanceError):                      # no lineage
        _atomic_face(origin_cut=None)


@pytest.mark.parametrize("materialize", MODES)
def test_O33_frame_default_charts_still_have_no_route(materialize):
    """ANTI-REGRESSION for the 205. Giving every default chart a route
    reclassifies spines, terminal residuals, LetPair/TenPack and gate counts;
    the face carries the atomic description instead."""
    arts = _faces(materialize=materialize)
    atomic = 0
    for a in arts:
        sb = a.selected_boundary
        if sb is None or sb.authority != FRAME_DEFAULT:
            continue
        assert sb.ingress.route is None and sb.egress.route is None, (
            f"occ {a.occurrence}: a frame-default chart grew a route")
        if a.ingress_face is not None:
            atomic += 1
            assert a.ingress_face.whole_chart
    assert atomic > 3, f"only {atomic} atomic faces; the pass is vacuous"


@pytest.mark.parametrize("materialize", MODES)
def test_O34_the_block_face_has_six_fibres_of_exactly_32(materialize):
    """The projection is many-to-one and every state survives it."""
    arts = _faces(materialize=materialize)
    # THE BLOCK face, chosen by its recorded role and descriptor -- not by
    # "it happens to be routed", which now matches every composed cut too.
    # THE BLOCK's own occurrence: both polarities present the Block factor.
    # A composed Seq downstream keeps the Block on its egress while its
    # ingress comes from its producer, so "any routed face" is not the test.
    def _is_block(f):
        return (f is not None and not f.whole_chart and f.role == "block"
                and f.descriptor is not None)

    routed = [a for a in arts
              if _is_block(a.ingress_face) and _is_block(a.egress_face)]
    assert routed, "the Block issued no routed face"
    for a in routed:
        for f in (a.ingress_face, a.egress_face):
            assert len(f.codes) == 192, f"{len(f.codes)} Block states"
            assert f.n_labels == 6
            assert f.fibre_sizes == (32,) * 6, f.fibre_sizes
            fib = f.fibres
            assert sum(len(x) for x in fib) == 192, "states were lost"
            assert len({i for x in fib for i in x}) == 192, "states duplicated"
            assert f.descriptor is not None
            assert f.factor_ids[0].startswith("block:")


def test_O35_an_inconsistent_recorded_support_is_rejected():
    """The support validator ran in a SECOND `__post_init__`, which Python
    silently discarded in favour of the last definition, so none of this was
    being checked. Merged into one hook, these bite."""
    f = ChartFactor(factor_id="s:1", name="K", owner=None, n_qubits=2,
                    codes=(0, 1, 2, 3), role="residual")
    rep, pl = scatter_repart(((0, 1),), 3)
    good = par_then_repart((f,), rep, 3, "c", placements=pl, kind="scatter")
    assert good.support() == (0, 1)

    with pytest.raises(ProvenanceError) as ei:          # repeats a wire
        BoundaryChart(n_qubits=3, codes=(0, 1), route=None, label="c",
                      space="ambient", support_wires=(1, 1))
    assert "repeats a wire" in str(ei.value)
    with pytest.raises(ProvenanceError) as ei:          # outside the register
        BoundaryChart(n_qubits=2, codes=(0, 1), route=None, label="c",
                      space="ambient", support_wires=(0, 5))
    assert "outside a 2-wire space" in str(ei.value)
    with pytest.raises(ProvenanceError) as ei:          # disagrees with route
        BoundaryChart(n_qubits=3, codes=tuple(good.codes), route=good.route,
                      label="c", space="ambient", support_wires=(0, 2))
    assert "not the union of its scatter placements" in str(ei.value)
