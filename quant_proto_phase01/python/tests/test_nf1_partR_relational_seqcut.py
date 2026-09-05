"""NF-1 Part R: the completed relational SeqCut.

Milestone-3 gates. `seq_cut` validates its own inputs before constructing a
row; cut symbols are matched SEMANTICALLY through the CutTransport, never by
label ordinal; presenters are resolved by recorded factor ids through one
split_at_face rule, several factors and noncontiguous placements included;
the join retains every unmatched factor and every (producer, consumer)
source pair; a shared non-cut resource is coequalized exactly once under
exact lineage agreement; and a non-Cartesian result STAYS a JoinRoute.
"""

import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(__file__))

from pytket import Circuit

from lang.terms import Apply, H, Id, Lam, LetPair, Pair, Seq, Var, X
from lang.types import Q, Ten, Unit
import compile.to_pytket as TP
from compile.to_pytket import compile
from compile.frames import (
    BoundaryChart, ChartFactor, CutFace, CutTransport, FactorSource,
    JoinRoute, ProvenanceError, SelectedBoundary, SourcePortRef,
    DERIVED, FRAME_DEFAULT, gather_code, leakage, par_then_repart,
    scatter_code, scatter_repart, semantic_action, seq_cut, split_at_face,
    tenpack,
)

q = Q()
ATOL = 1e-10
MODES = [False, True]


# ---------------------------------------------------------------------------
# builders (Part O conventions)
# ---------------------------------------------------------------------------

def _amb(codes, n, label, support=None):
    return BoundaryChart(n_qubits=n, codes=tuple(codes), route=None,
                         label=label, space="ambient",
                         support_wires=tuple(range(n) if support is None
                                             else support))


def _factor(fid, codes, w=1, *, role="operand", ref=None, root=None,
            owner=None, logical=None):
    src = None
    if ref is not None:
        src = FactorSource((SourcePortRef(ref=ref, origin_cut="cut:t",
                                          path=("t",), root=root),))
    return ChartFactor(factor_id=fid, source=src, name=fid, owner=owner,
                       n_qubits=w, codes=tuple(codes), role=role,
                       logical=logical)


def _routed(factors_and_places, n, label):
    factors = tuple(f for f, _ in factors_and_places)
    places = tuple(tuple(pl) for _, pl in factors_and_places)
    rep, pl = scatter_repart(places, n)
    return par_then_repart(factors, rep, n, label, placements=pl,
                           kind="scatter")


def _aface(codes, place, iface, pol, labels, alphabet, cut="cut:t"):
    """An EXHAUSTIVE atomic face."""
    sizes = [0] * len(alphabet)
    for L in labels:
        sizes[L] += 1
    return CutFace(factor_ids=(f"t:{pol}:{cut}",), polarity=pol, cut_id=cut,
                   origin_cut=cut, codes=tuple(codes),
                   placement=tuple(place), labels=tuple(labels),
                   n_labels=len(alphabet), alphabet=tuple(alphabet),
                   interface_wires=tuple(iface), fibre_sizes=tuple(sizes),
                   role="residual", whole_chart=True)


def _rface(fids, codes, place, iface, pol, labels, alphabet, cut="cut:t"):
    """A ROUTED face naming its presenters by recorded factor id."""
    sizes = [0] * len(alphabet)
    for L in labels:
        sizes[L] += 1
    return CutFace(factor_ids=tuple(fids), polarity=pol, cut_id=cut,
                   origin_cut=cut, codes=tuple(codes),
                   placement=tuple(place), labels=tuple(labels),
                   n_labels=len(alphabet), alphabet=tuple(alphabet),
                   interface_wires=tuple(iface), fibre_sizes=tuple(sizes),
                   whole_chart=False)


def _idtr(wires, n):
    size = 1 << len(wires)
    return CutTransport(wires=tuple(wires), ambient_width=n,
                        consumer_codes=tuple(range(size)),
                        producer_codes=tuple(range(size)),
                        forward=tuple(range(size)),
                        inverse=tuple(range(size)), kind="identity",
                        label="t")


def _sb(ing, egr, authority=DERIVED, origin="t"):
    return SelectedBoundary(ingress=ing, egress=egr, origin=origin,
                            authority=authority)


def _sup(ch):
    return tuple(ch.support("t: "))


# ---------------------------------------------------------------------------
# the four atomic/routed mirror cases, 2-vs-4 over one two-symbol cut
# ---------------------------------------------------------------------------

def _atomic_producer(n=2, cut=(0,)):
    prod = _sb(_amb((0, 2), n, "P-", cut), _amb((0, 2), n, "P+", cut),
               FRAME_DEFAULT)
    fi = _aface((0, 1), cut, cut, "ingress", (0, 1), (0, 1))
    fe = _aface((0, 1), cut, cut, "egress", (0, 1), (0, 1))
    return prod, fi, fe


def _atomic_consumer(n=2):
    cons = _sb(_amb((0, 1, 2, 3), n, "C-"), _amb((0, 1, 2, 3), n, "C+"))
    fi = _aface((0, 1, 2, 3), (0, 1), (0,), "ingress", (0, 0, 1, 1), (0, 1))
    fe = _aface((0, 1, 2, 3), (0, 1), (0,), "egress", (0, 0, 1, 1), (0, 1))
    return cons, fi, fe


def _routed_producer(n=2, cut=(0,)):
    s = _factor("p:cut", (0, 1), role="residual", ref="p:port", root="own:p")
    y = _factor("p:fib", (0, 1), ref="p:fib", root="own:pf", owner="own:pf")
    ing = _routed(((s, cut), (y, (1,))), n, "P-")
    egr = _routed(((s, cut), (y, (1,))), n, "P+")
    prod = _sb(ing, egr, FRAME_DEFAULT)
    fi = _rface(("p:cut",), (0, 1), cut, cut, "ingress", (0, 1), (0, 1))
    fe = _rface(("p:cut",), (0, 1), cut, cut, "egress", (0, 1), (0, 1))
    return prod, fi, fe


def _routed_consumer(n=2, cut=(0,)):
    s = _factor("c:cut", (0, 1), ref="c:port", root="own:c")
    z = _factor("c:ctx", (0, 1), ref="c:ctx", root="own:cz", owner="own:cz")
    ing = _routed(((s, cut), (z, (1,))), n, "C-")
    egr = _routed(((s, cut), (z, (1,))), n, "C+")
    cons = _sb(ing, egr)
    fi = _rface(("c:cut",), (0, 1), cut, cut, "ingress", (0, 1), (0, 1))
    fe = _rface(("c:cut",), (0, 1), cut, cut, "egress", (0, 1), (0, 1))
    return cons, fi, fe


def _cut(prod, pfi, pfe, cons, cfi, cfe, tr=None, n=2):
    return seq_cut(
        prod, cons, tr or _idtr((0,), n),
        producer_support=(_sup(prod.ingress), _sup(prod.egress)),
        consumer_support=(_sup(cons.ingress), _sup(cons.egress)),
        producer_face=pfe, producer_ingress_face=pfi,
        consumer_face=cfi, consumer_egress_face=cfe,
        where="t: ", label="t:cut")


def test_R1_atomic_to_atomic_two_meets_four():
    prod, pfi, pfe = _atomic_producer()
    cons, cfi, cfe = _atomic_consumer()
    sb, fin, fout = _cut(prod, pfi, pfe, cons, cfi, cfe)
    assert tuple(sb.ingress.codes) == (0, 1, 2, 3)
    assert tuple(sb.egress.codes) == (0, 1, 2, 3)
    jr = sb.ingress.route
    assert isinstance(jr, JoinRoute)
    # producer-major deterministic order, every source pair kept
    assert jr.sources == ((0, 0), (0, 1), (1, 2), (1, 3))
    assert len(jr.codes) == len(set(jr.codes)) == 4


def test_R2_atomic_to_routed_keeps_the_consumer_context():
    prod, pfi, pfe = _atomic_producer()
    cons, cfi, cfe = _routed_consumer()
    sb, fin, fout = _cut(prod, pfi, pfe, cons, cfi, cfe)
    for side in (sb.ingress, sb.egress):
        assert side.dim == 4
        assert side.route is not None, "the join degraded to route=None"
        ids = [f.factor_id for f in side.route.parts]
        assert "c:ctx" in ids, "the consumer's context factor was dropped"


def test_R3_routed_to_atomic_keeps_the_producer_fibre():
    prod, pfi, pfe = _routed_producer()
    # a NARROW atomic consumer: two states on the cut wire alone
    cons = _sb(_amb((0, 2), 2, "C-", (0,)), _amb((0, 2), 2, "C+", (0,)))
    cfi = _aface((0, 1), (0,), (0,), "ingress", (0, 1), (0, 1))
    cfe = _aface((0, 1), (0,), (0,), "egress", (0, 1), (0, 1))
    sb, fin, fout = _cut(prod, pfi, pfe, cons, cfi, cfe)
    assert sb.ingress.dim == 4, "a producer fibre state was dropped"
    for side in (sb.ingress, sb.egress):
        ids = [f.factor_id for f in side.route.parts]
        assert "p:fib" in ids, "the producer's fibre factor was dropped"


def _routed_producer3(n=3, cut=(0,)):
    s = _factor("p:cut", (0, 1), role="residual", ref="p:port", root="own:p")
    y = _factor("p:fib", (0, 1), ref="p:fib", root="own:pf", owner="own:pf")
    ing = _routed(((s, cut), (y, (2,))), n, "P-")
    egr = _routed(((s, cut), (y, (2,))), n, "P+")
    prod = _sb(ing, egr, FRAME_DEFAULT)
    fi = _rface(("p:cut",), (0, 1), cut, cut, "ingress", (0, 1), (0, 1))
    fe = _rface(("p:cut",), (0, 1), cut, cut, "egress", (0, 1), (0, 1))
    return prod, fi, fe


def test_R4_routed_to_routed_records_the_grafts():
    n = 3
    prod, pfi, pfe = _routed_producer3(n)
    cons, cfi, cfe = _routed_consumer(n)
    sb, fin, fout = _cut(prod, pfi, pfe, cons, cfi, cfe, tr=_idtr((0,), n),
                         n=n)
    assert sb.ingress.dim == 8
    for side in (sb.ingress, sb.egress):
        ids = [f.factor_id for f in side.route.parts]
        assert "p:fib" in ids and "c:ctx" in ids
    # the grafts are recorded on the relation the join carries; a fully
    # Cartesian result records them on the faces' premises instead, so read
    # them where the join stored them
    jr = sb.ingress.route
    subs = jr.substitutions if isinstance(jr, JoinRoute) else ()
    if subs:
        polar = {s.polarity: s for s in subs}
        assert polar["ingress"].replaced == "c:port"
        assert polar["ingress"].by == "p:port"
        assert polar["egress"].replaced == "p:port"
        assert polar["egress"].by == "c:port"
    # both original SourcePortRefs survive, unrelinked
    ing_ids = {f.factor_id: f for f in sb.ingress.route.parts}
    assert ing_ids["p:cut"].source.sole.ref == "p:port"
    assert ing_ids["p:cut"].source.sole.root == "own:p"
    assert ing_ids["c:ctx"].source.sole.ref == "c:ctx"


def _fibred_consumer3(n=3):
    """A consumer whose presenter carries its OWN fibre behind the cut."""
    s = _factor("c:cut", (0, 1, 2, 3), w=2, ref="c:port")
    ing = _routed(((s, (0, 2)),), n, "C-")
    egr = _routed(((s, (0, 2)),), n, "C+")
    cons = _sb(ing, egr)
    cfi = _rface(("c:cut",), (0, 1, 2, 3), (0, 2), (0,), "ingress",
                 (0, 0, 1, 1), (0, 1))
    cfe = _rface(("c:cut",), (0, 1, 2, 3), (0, 2), (0,), "egress",
                 (0, 0, 1, 1), (0, 1))
    return cons, cfi, cfe


def _fibred_join(n=3):
    s = _factor("p:cut", (0, 1), role="residual", ref="p:port", root="own:p")
    y = _factor("p:fib", (0, 1), ref="p:fib", root="own:pf", owner="own:pf")
    prod = _sb(_routed(((s, (0,)), (y, (1,))), n, "P-"),
               _routed(((s, (0,)), (y, (1,))), n, "P+"), FRAME_DEFAULT)
    pfi = _rface(("p:cut",), (0, 1), (0,), (0,), "ingress", (0, 1), (0, 1))
    pfe = _rface(("p:cut",), (0, 1), (0,), (0,), "egress", (0, 1), (0, 1))
    cons, cfi, cfe = _fibred_consumer3(n)
    return _cut(prod, pfi, pfe, cons, cfi, cfe, tr=_idtr((0,), n), n=n)


def test_R4b_the_join_route_records_the_grafts():
    """On a genuinely correlated join the substitutions ride the relation:
    both premises carry a two-state fibre, so eight rows meet a sixteen-way
    product and the result cannot be Cartesian."""
    sb, fin, fout = _fibred_join()
    assert sb.ingress.dim == 8
    jr = sb.ingress.route
    assert isinstance(jr, JoinRoute), "8 rows over a 16-product is a relation"
    assert len(jr.sources) == 8
    polar = {s_.polarity: s_ for s_ in jr.substitutions}
    assert polar["ingress"].replaced == "c:port"
    assert polar["ingress"].by == "p:port"
    assert polar["egress"].replaced == "p:port"
    assert polar["egress"].by == "c:port"


# ---------------------------------------------------------------------------
# multi-factor, noncontiguous presenters
# ---------------------------------------------------------------------------

def _multi_consumer(n=3):
    a = _factor("c:a", (0, 1), ref="c:a")
    b = _factor("c:b", (0, 1), ref="c:b", owner="own:b")
    cfac = _factor("c:c", (0, 1), ref="c:c")
    ing = _routed(((a, (0,)), (b, (1,)), (cfac, (2,))), n, "C-")
    egr = _routed(((a, (0,)), (b, (1,)), (cfac, (2,))), n, "C+")
    cons = _sb(ing, egr)
    # the face names A and C -- NONCONTIGUOUS -- as one joint presenter
    joint = (0, 1, 2, 3)
    fi = _rface(("c:a", "c:c"), joint, (0, 2), (0, 2), "ingress",
                (0, 1, 2, 3), (0, 1, 2, 3))
    fe = _rface(("c:a", "c:c"), joint, (0, 2), (0, 2), "egress",
                (0, 1, 2, 3), (0, 1, 2, 3))
    return cons, fi, fe


def test_R5_multiple_noncontiguous_presenter_factors():
    n = 3
    cut = (0, 2)
    prod = _sb(_amb((0, 1, 4, 5), n, "P-", cut),
               _amb((0, 1, 4, 5), n, "P+", cut), FRAME_DEFAULT)
    pfi = _aface((0, 1, 2, 3), cut, cut, "ingress", (0, 1, 2, 3),
                 (0, 1, 2, 3))
    pfe = _aface((0, 1, 2, 3), cut, cut, "egress", (0, 1, 2, 3),
                 (0, 1, 2, 3))
    cons, cfi, cfe = _multi_consumer(n)
    sb, fin, fout = _cut(prod, pfi, pfe, cons, cfi, cfe,
                         tr=_idtr(cut, n), n=n)
    # a single-factor-only or first-match split would have taken c:a alone
    sp = split_at_face(cons.ingress, cfi, n, "t: ")
    assert [f.factor_id for f in sp.presenters] == ["c:a", "c:c"]
    assert sp.presenter_places == ((0,), (2,))
    assert [f.factor_id for f in sp.rest] == ["c:b"]
    assert sb.ingress.dim == 8            # 4 cut states x context 2
    for side in (sb.ingress, sb.egress):
        ids = [f.factor_id for f in side.route.parts]
        assert "c:b" in ids, "the in-between context factor was dropped"


# ---------------------------------------------------------------------------
# sparse and reordered alphabets: semantic symbols, not label positions
# ---------------------------------------------------------------------------

def _sparse_tr(n=3, wires=(0, 1), consumer=(0, 3), producer=None):
    producer = producer or consumer
    size = 1 << len(wires)
    return CutTransport(wires=wires, ambient_width=n,
                        consumer_codes=tuple(consumer),
                        producer_codes=tuple(producer),
                        forward=tuple(range(size)),
                        inverse=tuple(range(size)), kind="identity",
                        label="t")


def test_R6_sparse_alphabet():
    n = 2
    cut = (0, 1)
    prod = _sb(_amb((0, 3), n, "P-", cut), _amb((0, 3), n, "P+", cut),
               FRAME_DEFAULT)
    pfi = _aface((0, 3), cut, cut, "ingress", (0, 1), (0, 3))
    pfe = _aface((0, 3), cut, cut, "egress", (0, 1), (0, 3))
    cons = _sb(_amb((0, 3), n, "C-", cut), _amb((0, 3), n, "C+", cut))
    cfi = _aface((0, 3), cut, cut, "ingress", (0, 1), (0, 3))
    cfe = _aface((0, 3), cut, cut, "egress", (0, 1), (0, 3))
    sb, fin, fout = _cut(prod, pfi, pfe, cons, cfi, cfe,
                         tr=_sparse_tr(n=n), n=n)
    assert tuple(sb.ingress.codes) == (0, 3)
    # the composite ingress face keeps the producer's own sparse alphabet
    assert fin is not None and tuple(fin.alphabet) == (0, 3)


def test_R7_reordered_alphabet_matches_semantically():
    """The producer presents the SAME two symbols in the opposite order.
    Positional matching would pair label 0 with label 0 -- symbol 1 against
    symbol 0 -- and is killed here: the join follows the symbols, and the
    surviving source pairs say so."""
    n = 2
    cut = (0,)
    # producer states in order (sym1, sym0): state 0 carries symbol 1
    prod = _sb(_amb((2, 0), n, "P-", cut), _amb((2, 0), n, "P+", cut),
               FRAME_DEFAULT)
    pfi = _aface((1, 0), cut, cut, "ingress", (0, 1), (1, 0))
    pfe = _aface((1, 0), cut, cut, "egress", (0, 1), (1, 0))
    cons, cfi, cfe = _atomic_consumer()
    tr = CutTransport(wires=cut, ambient_width=n,
                      consumer_codes=(0, 1), producer_codes=(0, 1),
                      forward=(0, 1), inverse=(0, 1), kind="identity",
                      label="t")
    sb, fin, fout = _cut(prod, pfi, pfe, cons, cfi, cfe, tr=tr)
    jr = sb.ingress.route
    assert isinstance(jr, JoinRoute)
    # producer state 0 (symbol 1) joins consumer states 2, 3 (symbol 1)
    assert jr.sources == ((0, 2), (0, 3), (1, 0), (1, 1))
    # ... and the composite ingress face keeps the PRODUCER's own recorded
    # order (1, 0) -- never a first-appearance image of the composed rows
    assert fin is not None and tuple(fin.alphabet) == (1, 0)
    assert tuple(fin.labels) == tuple(pfi.labels)


def test_R8_block_of_six_labels_with_fibres_of_32():
    """All 192 producer states survive the six-symbol cut."""
    n = 8
    cut = (0, 1, 2)
    syms = (0, 1, 2, 3, 4, 5)
    p_codes = tuple((s << 5) | f for s in syms for f in range(32))
    labels = tuple(i // 32 for i in range(192))
    prod = _sb(_amb(p_codes, n, "P-"), _amb(p_codes, n, "P+"),
               FRAME_DEFAULT)
    pfi = _aface(p_codes, tuple(range(n)), cut, "ingress", labels, syms)
    pfe = _aface(p_codes, tuple(range(n)), cut, "egress", labels, syms)
    c_codes = tuple(s << 5 for s in syms)
    cons = _sb(_amb(c_codes, n, "C-", cut), _amb(c_codes, n, "C+", cut))
    cfi = _aface(syms, cut, cut, "ingress", (0, 1, 2, 3, 4, 5), syms)
    cfe = _aface(syms, cut, cut, "egress", (0, 1, 2, 3, 4, 5), syms)
    tr = CutTransport(wires=cut, ambient_width=n,
                      consumer_codes=syms, producer_codes=syms,
                      forward=tuple(range(8)), inverse=tuple(range(8)),
                      kind="identity", label="t")
    sb, fin, fout = _cut(prod, pfi, pfe, cons, cfi, cfe, tr=tr, n=n)
    assert sb.ingress.dim == 192, "a fibre was dropped"
    assert sb.egress.dim == 192
    assert tuple(sb.ingress.codes) == p_codes, (
        "the 192 producer states did not all survive in order")


# ---------------------------------------------------------------------------
# downstream Seq and associativity
# ---------------------------------------------------------------------------

def _wide_leg(name, n=2, wires=(0, 1)):
    """A four-state leg behind the one-wire, two-symbol cut, its own
    context on `wires[1]`."""
    codes = tuple(scatter_code(v, wires, n) for v in range(4))
    leg = _sb(_amb(codes, n, f"{name}-", wires),
              _amb(codes, n, f"{name}+", wires), DERIVED, origin=name)
    fi = _aface((0, 1, 2, 3), wires, (wires[0],), "ingress", (0, 0, 1, 1),
                (0, 1), cut=f"cut:{name}")
    fe = _aface((0, 1, 2, 3), wires, (wires[0],), "egress", (0, 0, 1, 1),
                (0, 1), cut=f"cut:{name}")
    return leg, fi, fe


def _cut_named(p, pfi_, pfe_, c, cfi_, cfe_, lbl, n=3):
    return seq_cut(
        p, c, _idtr((0,), n),
        producer_support=(_sup(p.ingress), _sup(p.egress)),
        consumer_support=(_sup(c.ingress), _sup(c.egress)),
        producer_face=pfe_, producer_ingress_face=pfi_,
        consumer_face=cfi_, consumer_egress_face=cfe_,
        where=f"{lbl}: ", label=lbl)


def test_R9_a_downstream_seq_consumes_a_join_route():
    """(F ; G) feeds a second cut as its producer, JoinRoute and all."""
    n = 3
    prod = _sb(_amb((0, 4), n, "P-", (0,)), _amb((0, 4), n, "P+", (0,)),
               FRAME_DEFAULT)
    pfi = _aface((0, 1), (0,), (0,), "ingress", (0, 1), (0, 1))
    pfe = _aface((0, 1), (0,), (0,), "egress", (0, 1), (0, 1))
    cons = _sb(_amb((0, 2, 4, 6), n, "C-", (0, 1)),
               _amb((0, 2, 4, 6), n, "C+", (0, 1)))
    cfi = _aface((0, 1, 2, 3), (0, 1), (0,), "ingress", (0, 0, 1, 1),
                 (0, 1))
    cfe = _aface((0, 1, 2, 3), (0, 1), (0,), "egress", (0, 0, 1, 1),
                 (0, 1))
    sb1, f1_in, f1_out = _cut(prod, pfi, pfe, cons, cfi, cfe,
                              tr=_idtr((0,), n), n=n)
    assert isinstance(sb1.ingress.route, JoinRoute)
    assert f1_out is not None and f1_in is not None
    # the downstream leg carries ITS context on a disjoint coordinate
    down = _sb(_amb((0, 1, 4, 5), n, "H-", (0, 2)),
               _amb((0, 1, 4, 5), n, "H+", (0, 2)), DERIVED, origin="H")
    hfi = _aface((0, 1, 2, 3), (0, 2), (0,), "ingress", (0, 0, 1, 1),
                 (0, 1), cut="cut:H")
    hfe = _aface((0, 1, 2, 3), (0, 2), (0,), "egress", (0, 0, 1, 1),
                 (0, 1), cut="cut:H")
    sb2, f2_in, f2_out = seq_cut(
        sb1, down, _idtr((0,), n),
        producer_support=(_sup(sb1.ingress), _sup(sb1.egress)),
        consumer_support=(_sup(down.ingress), _sup(down.egress)),
        producer_face=f1_out, producer_ingress_face=f1_in,
        consumer_face=hfi, consumer_egress_face=hfe,
        where="t2: ", label="t2:cut")
    # every upstream state survives the second cut, per downstream label
    assert sb2.ingress.dim == 8
    assert sb2.ingress.route is not None
    assert f2_in is not None


def test_R10_both_associativity_shapes_agree():
    n = 3
    F = _sb(_amb((0, 4), n, "F-", (0,)), _amb((0, 4), n, "F+", (0,)),
            FRAME_DEFAULT, origin="F")
    ffi = _aface((0, 1), (0,), (0,), "ingress", (0, 1), (0, 1), cut="cut:F")
    ffe = _aface((0, 1), (0,), (0,), "egress", (0, 1), (0, 1), cut="cut:F")
    G, gfi, gfe = _wide_leg("G", n, (0, 1))
    Hb, hfi, hfe = _wide_leg("Hh", n, (0, 2))
    fg, fg_in, fg_out = _cut_named(F, ffi, ffe, G, gfi, gfe, "fg")
    left, _li, _lo = _cut_named(fg, fg_in, fg_out, Hb, hfi, hfe, "fg_h")
    gh, gh_in, gh_out = _cut_named(G, gfi, gfe, Hb, hfi, hfe, "gh")
    right, _ri, _ro = _cut_named(F, ffi, ffe, gh, gh_in, gh_out, "f_gh")
    assert tuple(left.ingress.codes) == tuple(right.ingress.codes)
    assert tuple(left.egress.codes) == tuple(right.egress.codes)
    assert set(left.ingress.support("t")) == set(right.ingress.support("t"))
    assert left.ingress.dim == right.ingress.dim == 8


# ---------------------------------------------------------------------------
# shared resources
# ---------------------------------------------------------------------------

def _shared_z(root="own:z", codes=(0, 1), place=(1,), ref="z:ref"):
    return _factor("z:{}".format(ref), codes, role="operand", ref=ref,
                   root=root, owner="own:z", logical=q)


def test_R11_a_shared_resource_is_coequalized_exactly_once():
    n = 2
    zp = _factor("p:z", (0, 1), ref="z", root="own:z", owner="own:z",
                 logical=q)
    zc = _factor("c:z", (0, 1), ref="z", root="own:z", owner="own:z",
                 logical=q)
    s = _factor("p:cut", (0, 1), role="residual", ref="p:port")
    sc = _factor("c:cut", (0, 1), ref="c:port")
    prod = _sb(_routed(((s, (0,)), (zp, (1,))), n, "P-"),
               _routed(((s, (0,)), (zp, (1,))), n, "P+"), FRAME_DEFAULT)
    cons = _sb(_routed(((sc, (0,)), (zc, (1,))), n, "C-"),
               _routed(((sc, (0,)), (zc, (1,))), n, "C+"))
    pfi = _rface(("p:cut",), (0, 1), (0,), (0,), "ingress", (0, 1), (0, 1))
    pfe = _rface(("p:cut",), (0, 1), (0,), (0,), "egress", (0, 1), (0, 1))
    cfi = _rface(("c:cut",), (0, 1), (0,), (0,), "ingress", (0, 1), (0, 1))
    cfe = _rface(("c:cut",), (0, 1), (0,), (0,), "egress", (0, 1), (0, 1))
    sb, fin, fout = _cut(prod, pfi, pfe, cons, cfi, cfe)
    # ONE z factor, and only the diagonal in z survives: 2 cut x 2 z = 4
    assert sb.ingress.dim == 4
    for side in (sb.ingress, sb.egress):
        zs = [f for f in side.route.parts if f.owner == "own:z"]
        assert len(zs) == 1, "the shared resource appears twice or not at all"


def test_R12_a_shared_owner_without_exact_lineage_is_refused():
    n = 2
    zp = _factor("p:z", (0, 1), ref="z", root="own:z", owner="own:z",
                 logical=q)
    # same owner, DIFFERENT recorded lineage
    zc = _factor("c:z", (0, 1), ref="z2", root="own:other", owner="own:z",
                 logical=q)
    s = _factor("p:cut", (0, 1), role="residual", ref="p:port")
    sc = _factor("c:cut", (0, 1), ref="c:port")
    prod = _sb(_routed(((s, (0,)), (zp, (1,))), n, "P-"),
               _routed(((s, (0,)), (zp, (1,))), n, "P+"), FRAME_DEFAULT)
    cons = _sb(_routed(((sc, (0,)), (zc, (1,))), n, "C-"),
               _routed(((sc, (0,)), (zc, (1,))), n, "C+"))
    pfi = _rface(("p:cut",), (0, 1), (0,), (0,), "ingress", (0, 1), (0, 1))
    pfe = _rface(("p:cut",), (0, 1), (0,), (0,), "egress", (0, 1), (0, 1))
    cfi = _rface(("c:cut",), (0, 1), (0,), (0,), "ingress", (0, 1), (0, 1))
    cfe = _rface(("c:cut",), (0, 1), (0,), (0,), "egress", (0, 1), (0, 1))
    with pytest.raises(ProvenanceError) as ei:
        _cut(prod, pfi, pfe, cons, cfi, cfe)
    assert "refused rather than overwritten" in str(ei.value)


def test_R13_a_dim_one_resource_is_neither_lost_nor_duplicated():
    n = 2
    one = _factor("c:one", (1,), ref="one", owner="own:one")
    sc = _factor("c:cut", (0, 1), ref="c:port")
    cons = _sb(_routed(((sc, (0,)), (one, (1,))), n, "C-"),
               _routed(((sc, (0,)), (one, (1,))), n, "C+"))
    cfi = _rface(("c:cut",), (0, 1), (0,), (0,), "ingress", (0, 1), (0, 1))
    cfe = _rface(("c:cut",), (0, 1), (0,), (0,), "egress", (0, 1), (0, 1))
    prod, pfi, pfe = _atomic_producer()
    sb, fin, fout = _cut(prod, pfi, pfe, cons, cfi, cfe)
    assert sb.ingress.dim == 2
    for side in (sb.ingress, sb.egress):
        ones = [f for f in side.route.parts if f.factor_id == "c:one"]
        assert len(ones) == 1
        # the fixed bit is preserved in every composed code
        for c in side.codes:
            assert gather_code(c, (1,), n) == 1


# ---------------------------------------------------------------------------
# refusals: forged, stale, degraded
# ---------------------------------------------------------------------------

def test_R14_stale_and_forged_inputs_are_refused():
    prod, pfi, pfe = _atomic_producer()
    cons, cfi, cfe = _atomic_consumer()
    # stale: a face carried over from a chart this premise no longer is --
    # its recorded codes do not present this chart
    import dataclasses
    stale = dataclasses.replace(pfi, codes=(1, 0), labels=(1, 0))
    with pytest.raises(ProvenanceError) as ei:
        _cut(prod, stale, pfe, cons, cfi, cfe)
    assert "reassembles" in str(ei.value)
    # forged factor id on a routed premise
    rcons, rcfi, rcfe = _routed_consumer()
    forged = dataclasses.replace(rcfi, factor_ids=("c:forged",))
    with pytest.raises(ProvenanceError):
        _cut(prod, pfi, pfe, rcons, forged, rcfe)
    # wrong support
    with pytest.raises(ProvenanceError) as ei:
        seq_cut(prod, cons, _idtr((0,), 2),
                producer_support=((0, 1), (0,)),
                consumer_support=((0, 1), (0, 1)),
                producer_face=pfe, producer_ingress_face=pfi,
                consumer_face=cfi, consumer_egress_face=cfe, where="t: ")
    assert "support" in str(ei.value)
    # a transport built for other codes
    wrong_tr = CutTransport(wires=(0,), ambient_width=2,
                            consumer_codes=(1, 0), producer_codes=(0, 1),
                            forward=(1, 0), inverse=(1, 0),
                            kind="code-permutation", label="t")
    with pytest.raises(ProvenanceError) as ei:
        _cut(prod, pfi, pfe, cons, cfi, cfe, tr=wrong_tr)
    assert "transport" in str(ei.value)
    # a face of a different cut placement
    off = dataclasses.replace(cfi, interface_wires=(1,))
    with pytest.raises(ProvenanceError) as ei:
        _cut(prod, pfi, pfe, cons, off, cfe)
    assert "different cut" in str(ei.value)
    # an empty alphabet is not an alphabet
    bare = dataclasses.replace(cfi, alphabet=())
    with pytest.raises(ProvenanceError) as ei:
        _cut(prod, pfi, pfe, cons, bare, cfe)
    assert "no ordered cut alphabet" in str(ei.value)


def test_R15_a_completion_needs_its_evidence_here():
    """seq_cut is independently safe: a transport carrying a completion is
    refused unless the interfaces and the widened frame arrive with it."""
    from compile.frames import CutCompletion
    comp = CutCompletion(ordered_wires=(0, 1), ambient_width=2,
                         producer_wires=(0,), consumer_wires=(0, 1),
                         widened="producer", from_width=1, to_width=2,
                         reason="test", cut_id="cut:t")
    tr = CutTransport(wires=(0, 1), ambient_width=2,
                      consumer_codes=(0, 1, 2, 3),
                      producer_codes=(0, 1, 2, 3),
                      forward=(0, 1, 2, 3), inverse=(0, 1, 2, 3),
                      kind="identity", label="t",
                      producer_wires=(0,), consumer_wires=(0, 1),
                      completion=comp)
    cut = (0, 1)
    prod = _sb(_amb((0, 1, 2, 3), 2, "P-", cut),
               _amb((0, 1, 2, 3), 2, "P+", cut), FRAME_DEFAULT)
    pfi = _aface((0, 1, 2, 3), cut, cut, "ingress", (0, 1, 2, 3),
                 (0, 1, 2, 3))
    pfe = _aface((0, 1, 2, 3), cut, cut, "egress", (0, 1, 2, 3),
                 (0, 1, 2, 3))
    cons = _sb(_amb((0, 1, 2, 3), 2, "C-", cut),
               _amb((0, 1, 2, 3), 2, "C+", cut))
    cfi = _aface((0, 1, 2, 3), cut, cut, "ingress", (0, 1, 2, 3),
                 (0, 1, 2, 3))
    cfe = _aface((0, 1, 2, 3), cut, cut, "egress", (0, 1, 2, 3),
                 (0, 1, 2, 3))
    with pytest.raises(ProvenanceError) as ei:
        _cut(prod, pfi, pfe, cons, cfi, cfe, tr=tr)
    assert "cannot be validated here" in str(ei.value)


def test_R16_a_forged_wire_permutation_is_refused_at_construction():
    with pytest.raises(ProvenanceError) as ei:
        CutTransport(wires=(0, 1), ambient_width=2,
                     consumer_codes=(0, 1, 2, 3),
                     producer_codes=(0, 1, 3, 2),
                     forward=(0, 1, 3, 2), inverse=(0, 1, 3, 2),
                     kind="wire-permutation", wire_permutation=(1, 0),
                     label="t")
    assert "does not induce" in str(ei.value)
    # ... and the honest one passes: swapping the two cut wires induces
    # exactly the code map (0, 2, 1, 3)
    ok = CutTransport(wires=(0, 1), ambient_width=2,
                      consumer_codes=(0, 1, 2, 3),
                      producer_codes=(0, 2, 1, 3),
                      forward=(0, 2, 1, 3), inverse=(0, 2, 1, 3),
                      kind="wire-permutation", wire_permutation=(1, 0),
                      label="t")
    assert ok.forward == (0, 2, 1, 3)


def test_R17_the_join_never_degrades_to_route_none_or_cartesian_lies():
    prod, pfi, pfe = _atomic_producer()
    cons, cfi, cfe = _atomic_consumer()
    sb, _fi, _fo = _cut(prod, pfi, pfe, cons, cfi, cfe)
    for side in (sb.ingress, sb.egress):
        assert side.route is not None, "the join degraded to route=None"
        if isinstance(side.route, JoinRoute):
            assert side.route.as_chart_route() is None or \
                len(side.route.rows) == np.prod(
                    [len(f.codes) for f in side.route.parts])
    # 4 rows against a 2-state presenter: not a product, so it must have
    # STAYED a relation rather than pretending to be Cartesian
    jr = sb.ingress.route
    assert isinstance(jr, JoinRoute)
    assert len(jr.rows) == 4
    # ... and a JoinRoute refuses to drop a source pair
    import dataclasses
    with pytest.raises(ProvenanceError):
        dataclasses.replace(jr, sources=jr.sources[:-1])


def test_R18_production_seq_cannot_bypass_seq_cut():
    """The production general-Seq path routes through THE seq_cut."""
    from test_nf1_beta_tensor import _fixture

    class _Sentinel(Exception):
        pass

    def bomb(*a, **k):
        raise _Sentinel()

    real = TP.seq_cut
    TP.seq_cut = bomb
    try:
        with pytest.raises(_Sentinel):
            compile(_fixture("curried_select_3_abstract"))
    finally:
        TP.seq_cut = real


# ---------------------------------------------------------------------------
# actions: the producer's gate survives exactly (X does not collapse)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("gate,build", [
    ("X", lambda c: c.X(0)), ("H", lambda c: c.H(0)),
    ("S", lambda c: c.S(0)), ("T", lambda c: c.T(0)),
])
def test_R19_gate_actions_survive_the_relational_join(gate, build):
    prod, pfi, pfe = _atomic_producer()
    cons, cfi, cfe = _routed_consumer()
    sb, _fi, _fo = _cut(prod, pfi, pfe, cons, cfi, cfe)
    c = Circuit(2)
    build(c)
    U = c.get_unitary()
    got = semantic_action(sb.ingress, U, sb.egress)
    one = Circuit(1)
    build(one)
    want = np.kron(one.get_unitary(), np.eye(2))
    assert np.allclose(got, want, atol=ATOL, rtol=0.0)
    assert not np.allclose(got, np.eye(4), atol=ATOL), (
        f"{gate}: the producer's action was gauged into the layout")
    assert leakage(sb.ingress, U, sb.egress) < ATOL


def test_R20_composite_embeddings_are_the_premises_own():
    prod, pfi, pfe = _atomic_producer()
    cons, cfi, cfe = _atomic_consumer()
    sb, _fi, _fo = _cut(prod, pfi, pfe, cons, cfi, cfe)
    # ingress: the producer's own ingress embedding widened by the
    # consumer's context -- never its inverse image (O10's defect)
    assert tuple(sb.ingress.codes) == (0, 1, 2, 3)
    # egress: the consumer's own egress embedding
    assert tuple(sb.egress.codes) == (0, 1, 2, 3)


# ---------------------------------------------------------------------------
# JoinRoute integration: TenPack / lift / conversion
# ---------------------------------------------------------------------------

def test_R21_tenpack_and_lift_re_address_a_join_route_without_loss():
    a = _factor("a", (0, 1))
    b = _factor("b", (0, 1))
    diag = JoinRoute(label="diag", parts=(a, b), placements=((0,), (1,)),
                     rows=((0, 1), (1, 0)), sources=((0, 1), (1, 0)),
                     codes=(1, 2), support=(0, 1), n_qubits=2)
    ch = BoundaryChart(n_qubits=2, codes=(1, 2), route=diag, label="diag",
                       space="ambient", support_wires=(0, 1))
    packed = tenpack(ch, (0, 1), (1, 0))
    assert isinstance(packed.route, JoinRoute)
    assert packed.route.rows == diag.rows
    assert packed.route.sources == diag.sources
    assert packed.route.parts == diag.parts
    # codes moved with the re-addressing: wires 0 and 1 swapped
    assert tuple(packed.codes) == (2, 1)
    # ... and the lift maps the same relation into a wider register
    from compile.frames import _lift_chart
    lifted = _lift_chart(ch, (2, 0), 3, "lifted")
    assert isinstance(lifted.route, JoinRoute)
    assert lifted.route.rows == diag.rows
    assert lifted.route.sources == diag.sources
    # a on wire 2, b on wire 0: row (0,1) -> code 4; row (1,0) -> code 1
    assert tuple(lifted.codes) == (4, 1)


def test_R22_as_chart_route_only_on_a_proven_cartesian_product():
    prod, pfi, pfe = _atomic_producer()
    cons, cfi, cfe = _atomic_consumer()
    sb, _fi, _fo = _cut(prod, pfi, pfe, cons, cfi, cfe)
    jr = sb.ingress.route
    if isinstance(jr, JoinRoute):
        cr = jr.as_chart_route()
        if cr is not None:
            assert cr.reconstruct() == tuple(sb.ingress.codes)
    # a correlated relation refuses conversion
    f1 = _factor("a", (0, 1))
    f2 = _factor("b", (0, 1))
    diag = JoinRoute(label="diag", parts=(f1, f2),
                     placements=((0,), (1,)),
                     rows=((0, 0), (1, 1)), sources=((0, 0), (1, 1)),
                     codes=(0, 3), support=(0, 1), n_qubits=2)
    assert diag.as_chart_route() is None, (
        "a diagonal pretended to be a product")
    assert diag.decode(3) == ((1, 1), (1, 1))
    with pytest.raises(ProvenanceError):
        diag.decode(2)


# ---------------------------------------------------------------------------
# production witnesses: Pair, LetPair, Apply as producer and consumer
# ---------------------------------------------------------------------------

def _framed(term, want, materialize):
    """Compile and compare the EXACT framed action, zero leakage and phase.

    The action is read in the term's own selected boundary, so a virtual
    (un-materialised) routing is part of the semantics either way.
    """
    r = compile(term, materialize=materialize)
    sb = r.selected_boundary
    assert sb is not None and not isinstance(sb, str)
    U = r.circuit.get_unitary()
    A = semantic_action(sb.ingress, U, sb.egress)
    assert A.shape == want.shape
    assert np.allclose(A, want, atol=ATOL, rtol=0.0), (
        f"framed action deviates by {float(np.max(np.abs(A - want))):.3e}")
    assert leakage(sb.ingress, U, sb.egress) < ATOL
    assert abs(float(r.circuit.phase)) < ATOL
    return r


@pytest.mark.parametrize("materialize", MODES)
def test_R23_letpair_and_pair_as_seq_producer_and_consumer(materialize):
    """LetPair (consuming its Pair body's producer through the splice) as a
    Seq leg on both sides of a certified-identity cut. The general
    two-derived-leg transport is Milestone 4 (the L4 refusals); what
    Milestone 3 pins is that the relational machinery composes these
    witnesses exactly, with no state lost and no phase invented.

    A pure routing term is WIRING: its framed action, read in its own
    selected boundary, is the identity, and the swap lives in the recorded
    egress addressing -- gauging it into the action would be the historic
    O9 defect in reverse."""
    qq = Ten(q, q)
    swap = LetPair("x", "y", q, q, Id(qq),
                   Pair(Var("y", q), Var("x", q)))
    I4 = np.eye(4, dtype=complex)
    r = _framed(swap, I4, materialize)
    sb = r.selected_boundary
    # the routing is REAL and recorded: the binder schedule crosses the two
    # halves between ingress and egress
    pk = sb.packing
    assert pk is not None
    assert tuple(pk.r_x_in) != tuple(pk.r_x_out), (
        "the swap's routing is not recorded in the packing schedule")
    # LetPair/Pair as PRODUCER, a certified identity as consumer
    _framed(Seq(swap, Id(qq)), I4, materialize)
    # ... and as CONSUMER of a certified identity producer
    _framed(Seq(Id(qq), swap), I4, materialize)


@pytest.mark.parametrize("materialize", MODES)
def test_R24_apply_as_seq_producer_and_consumer(materialize):
    hx = Lam("hz", q, q, Seq(Var("hz", q), H(0, q)))
    app = Apply(hx, Id(q))
    Hm = Circuit(1).H(0).get_unitary()
    _framed(app, Hm, materialize)
    # Apply as PRODUCER, then as CONSUMER, across a certified identity
    _framed(Seq(app, Id(q)), Hm, materialize)
    _framed(Seq(Id(q), app), Hm, materialize)
