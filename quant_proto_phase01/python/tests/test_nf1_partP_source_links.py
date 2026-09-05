"""NF-1 Part P: the source-link dataflow behind prepared branch projections.

Milestone-1 gates. Every factor a prepared branch's row projection consumes
must reach an ISSUED external semantic root through recorded links alone --
no type, width, code, wire or matrix ever selects. The two polarities are
projected INDEPENDENTLY: ctrl_ho's live branch presents eight symbols on the
way in and two on the way out, and that asymmetry is the direct evidence the
polarity was not collapsed.

The mutation battery checks the constructors are TRANSPORT ONLY: Par,
Repart, TenPack, Splice and Complete carry a factor's recorded source
forward by identity -- an unlinked or reminted source survives them
unchanged and is refused at classification, never silently repaired,
re-rooted or classified by placement.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))

from lang.terms import Apply, H, Id, Lam, LetPair, NPlusMap, Pair, Seq, Var
from lang.types import Arrow, Q, Ten, Unit, build_plus_tree
import compile.to_pytket as TP
from compile.to_pytket import compile
from compile.frames import (
    BoundaryChart, BranchRoleContext, ChartFactor, FactorSource,
    ProvenanceError, ProvenanceScope, RowProjection, SourcePortRef,
    TypedBinding, complete_branch, par_then_repart, project_branch_root,
    scatter_repart, tenpack, tensor_splice,
)

q = Q()


# ---------------------------------------------------------------------------
# capture helpers
# ---------------------------------------------------------------------------

def _captured_projections(term, env=None):
    """Compile `term` with the LIVE production path and capture every
    prepared-branch projection it issues, keyed (branch_index, polarity)."""
    real = TP.project_branch_root
    captured = {}

    def spy(chart, roles, *, branch_index, polarity, port, where=""):
        bp = real(chart, roles, branch_index=branch_index, polarity=polarity,
                  port=port, where=where)
        captured[(branch_index, polarity)] = (chart, roles, bp)
        return bp

    TP.project_branch_root = spy
    try:
        if env is None:
            compile(term, materialize=False)
        else:
            compile(term, materialize=False, env=env)
    finally:
        TP.project_branch_root = real
    assert captured, "no prepared-branch projection was issued"
    return captured


def _ctrl_ho_projections():
    from test_nf1_beta_tensor import _fixture
    return _captured_projections(_fixture("ctrl_ho_closed_plus_map"))


def _roots_of(chart):
    return tuple(f.source.sole.reaches() for f in chart.route.parts)


# ---------------------------------------------------------------------------
# the live ctrl_ho gates
# ---------------------------------------------------------------------------

def test_P1_every_ctrl_ho_factor_reaches_an_issued_root():
    """THE dataflow gate: zero factors fail to reach an issued external
    semantic root, on both branches and both polarities, measured on the
    live compile -- and each reached root is one the role context issued."""
    caps = _ctrl_ho_projections()
    assert set(caps) == {(0, "ingress"), (0, "egress"),
                         (1, "ingress"), (1, "egress")}
    for (bi, pol), (chart, roles, bp) in caps.items():
        issued = set(roles.payload) | set(roles.fibre)
        for f in chart.route.parts:
            r = f.source.sole.reaches(f"branch {bi} {pol}: ")
            assert r in issued, (
                f"branch {bi} {pol}: factor {f.factor_id} reaches {r}, "
                f"which was not issued by the role context {sorted(issued)}")


def test_P2_ctrl_ho_branch1_is_8x2_in_and_2x8_out():
    """THE polarity-independence pin. Branch 1 presents EIGHT payload
    symbols with a fibre of two at ingress, and TWO payload symbols with a
    fibre of eight at egress. One shared projection cannot say both."""
    caps = _ctrl_ho_projections()
    b1_in = caps[(1, "ingress")][2]
    b1_out = caps[(1, "egress")][2]
    assert len(b1_in.alphabet) == 8, b1_in.alphabet
    assert b1_in.fibre_sizes == (2,) * 8
    assert len(b1_out.alphabet) == 2, b1_out.alphabet
    assert b1_out.fibre_sizes == (8, 8)
    # independence is structural, not just numeric: the two projections
    # select different coordinates for label and fibre
    assert b1_in.projection.label_wires != b1_out.projection.label_wires
    assert b1_in.projection.fibre_wires != b1_out.projection.fibre_wires
    # and each polarity classifies against ITS OWN issued payload root
    assert caps[(1, "ingress")][1].payload != caps[(1, "egress")][1].payload


def test_P3_var_headed_spine_lineage():
    """Branch 1's spine has a captured head. Its consumption is what the
    links record: the result port's INGRESS face descends from the captured
    binding (the head's B half at entry), the operands' EGRESS faces descend
    from it too (the consumed head took them), while the ingress operands
    are the branch's own payload and the egress residual is its result."""
    caps = _ctrl_ho_projections()
    ch_in, roles_in, _ = caps[(1, "ingress")]
    ch_out, roles_out, _ = caps[(1, "egress")]
    fibre_root = roles_in.fibre[0]
    assert roles_out.fibre == (fibre_root,), (
        "the captured binding's identity is polarity-independent")

    def parts(chart, role):
        return [f for f in chart.route.parts
                if f.role == role and f.n_qubits > 0]

    for f in parts(ch_in, "operand"):
        assert f.source.sole.reaches() == roles_in.payload[0], f.factor_id
    for f in parts(ch_in, "residual"):
        assert f.source.sole.reaches() == fibre_root, f.factor_id
    for f in parts(ch_out, "operand"):
        assert f.source.sole.reaches() == fibre_root, f.factor_id
    for f in parts(ch_out, "residual"):
        assert f.source.sole.reaches() == roles_out.payload[0], f.factor_id


def test_P4_nested_apply_spine_lineage():
    """Branch 1's spine is NESTED: the outer application carries the inner
    one's accumulated operand as a prefix factor. The transported prefix
    keeps per-polarity lineage exactly like the operand minted here -- and
    the issued result occurrence is a DIFFERENT minted ref per polarity,
    each linked to the port its own face descends from."""
    caps = _ctrl_ho_projections()
    ch_in = caps[(1, "ingress")][0]
    ch_out = caps[(1, "egress")][0]
    ops_in = [f for f in ch_in.route.parts
              if f.role == "operand" and f.n_qubits > 0]
    ops_out = [f for f in ch_out.route.parts
               if f.role == "operand" and f.n_qubits > 0]
    assert len(ops_in) == len(ops_out) == 2, (
        "the nested spine accumulates two operand factors")
    # one factor lineage per operand across the two polarities...
    assert [f.factor_id for f in ops_in] == [f.factor_id for f in ops_out]
    # ...with per-polarity roots that DIFFER (payload in, fibre out)
    for fi, fo in zip(ops_in, ops_out):
        assert fi.source.sole.reaches() != fo.source.sole.reaches(), (
            f"{fi.factor_id}: the operand's two faces descend from two "
            f"different ports and must not share one link")
    res_in = [f for f in ch_in.route.parts if f.role == "residual"]
    res_out = [f for f in ch_out.route.parts if f.role == "residual"]
    assert len(res_in) == len(res_out) == 1
    assert res_in[0].source.sole.ref != res_out[0].source.sole.ref, (
        "the result occurrence is minted per polarity")


def test_P5_context_free_branch_has_an_explicit_payload_root():
    """Branch 0 captures nothing -- and still classifies every factor to an
    EXPLICITLY issued payload root, one per polarity. 'No context' is not
    'no payload', and the two polarities do not share one root."""
    caps = _ctrl_ho_projections()
    r0_in, r0_out = caps[(0, "ingress")][1], caps[(0, "egress")][1]
    assert r0_in.fibre == () and r0_out.fibre == ()
    assert len(r0_in.payload) == 1 and r0_in.payload[0] is not None
    assert len(r0_out.payload) == 1 and r0_out.payload[0] is not None
    assert r0_in.payload != r0_out.payload
    for pol in ("ingress", "egress"):
        bp = caps[(0, pol)][2]
        assert bp.fibre_sizes == (1,) * len(bp.alphabet)


def test_P6_the_ctrl_ho_factor_table():
    """The full per-factor, per-polarity table, pinned structurally:
    (name, role, root-kind, placement) for every factor, plus each
    projection's label/fibre coordinates and alphabet shape."""
    caps = _ctrl_ho_projections()
    table = {}
    for (bi, pol), (chart, roles, bp) in caps.items():
        rows = []
        for f, pl in zip(chart.route.parts, chart.route.placements):
            root = f.source.sole.reaches()
            kind = "payload" if root in set(roles.payload) else "fibre"
            rows.append((f.name, f.role, kind, tuple(pl)))
        table[(bi, pol)] = (tuple(rows), bp.projection.label_wires,
                            bp.projection.fibre_wires, len(bp.alphabet),
                            bp.fibre_sizes)
    assert table[(0, "ingress")] == ((
        ("S_Var", "operand", "payload", ()),
        ("S_y", "operand", "payload", (2,)),
        ("Y_B", "residual", "payload", (1,)),
    ), (2, 1), (), 4, (1, 1, 1, 1))
    assert table[(0, "egress")] == ((
        ("S_Var", "operand", "payload", ()),
        ("S_y", "operand", "payload", (2,)),
        ("Y_B", "residual", "payload", (0,)),
    ), (2, 0), (), 4, (1, 1, 1, 1))
    assert table[(1, "ingress")] == ((
        ("S_Var", "operand", "payload", ()),
        ("S_y", "operand", "payload", (0, 1)),
        ("S_y", "operand", "payload", (2,)),
        ("Y_B", "residual", "fibre", (6,)),
    ), (0, 1, 2), (6,), 8, (2,) * 8)
    assert table[(1, "egress")] == ((
        ("S_Var", "operand", "payload", ()),
        ("S_y", "operand", "fibre", (4, 5)),
        ("S_y", "operand", "fibre", (6,)),
        ("Y_B", "residual", "payload", (0,)),
    ), (0,), (4, 5, 6), 2, (8, 8))


# ---------------------------------------------------------------------------
# a live witness crossing Seq, LetPair/Splice and a captured spine
# ---------------------------------------------------------------------------

def _seq_and_spine_witness():
    """Two alternatives: a CLOSED branch whose pair carries a Seq child, and
    an OPEN branch applying the captured g -- so one compile drives lineage
    through the Seq relay, the Pair pullback, the LetPair splice and a
    captured-head spine at once."""
    qq = Arrow(q, q)
    ia = Ten(Unit(), q)
    sum_ty = build_plus_tree([ia, ia])
    pm = NPlusMap((ia, ia), (
        LetPair("i", "a", Unit(), q, Id(ia),
                Pair(Var("i", Unit()), Seq(Var("a", q), H(0, q)))),
        LetPair("i", "a", Unit(), q, Id(ia),
                Pair(Var("i", Unit()),
                     Apply(Var("g", qq), Var("a", q)))),
    ))
    body = LetPair("g", "s", qq, sum_ty, Var("input", Ten(qq, sum_ty)),
                   Seq(Var("s", sum_ty), pm))
    return Lam("input", Ten(qq, sum_ty), sum_ty, body)


def test_P16_lineage_crosses_seq_splice_and_captured_spine():
    caps = _captured_projections(_seq_and_spine_witness())
    assert set(caps) == {(0, "ingress"), (0, "egress"),
                         (1, "ingress"), (1, "egress")}
    # the closed Seq-carrying branch: everything is its own payload
    for pol in ("ingress", "egress"):
        _, roles, bp = caps[(0, pol)]
        assert roles.fibre == ()
        assert bp.fibre_sizes == (1,) * len(bp.alphabet)
    # the open branch: the captured head's consumption flips sides
    _, roles_in, b_in = caps[(1, "ingress")]
    _, roles_out, b_out = caps[(1, "egress")]
    assert roles_in.fibre == roles_out.fibre != ()
    assert b_in.fibre_sizes == (2, 2)
    assert b_out.fibre_sizes == (2, 2)
    # In this one-argument spine the label and fibre COORDINATE sets happen
    # to coincide across polarities; what proves the two projections are
    # independent is WHICH factor presents the payload on each side: the
    # operand at ingress, the residual at egress.
    assert set(b_in.projection.presenters) != \
        set(b_out.projection.presenters), (
            "ingress presents the argument, egress presents the result; a "
            "shared presenter set would mean one projection served both "
            "polarities")
    ops_in = {f.factor_id for f in caps[(1, "ingress")][0].route.parts
              if f.role == "operand" and f.n_qubits > 0}
    assert ops_in <= set(b_in.projection.presenters)
    assert ops_in.isdisjoint(b_out.projection.presenters)


# ---------------------------------------------------------------------------
# classification mutations, at the projection itself
# ---------------------------------------------------------------------------

R_IN, R_OUT, R_FIB = "own:test.in", "own:test.out", "own:test.fib"


def _factor(fid, wire_codes, root, *, role="operand", refs=None):
    src = FactorSource(refs) if refs is not None else FactorSource((
        SourcePortRef(ref=f"ref:{fid}", origin_cut="cut:test",
                      path=("test",), root=root),))
    return ChartFactor(factor_id=fid, source=src, name=fid, owner=None,
                       n_qubits=1, codes=tuple(wire_codes), role=role,
                       logical=q)


def _chart(*factors_and_places, n=2):
    factors = tuple(f for f, _ in factors_and_places)
    places = tuple(pl for _, pl in factors_and_places)
    rep, pl = scatter_repart(places, n)
    return par_then_repart(factors, rep, n, "t", placements=pl,
                           kind="scatter")


def _roles(pol="ingress"):
    return BranchRoleContext(polarity=pol, payload=(R_IN,), fibre=(R_FIB,),
                             branch_index=0)


def _port(root=R_IN):
    return SourcePortRef(ref="cut:test", origin_cut="cut:test",
                        path=("branch", "0", "ingress"), root=root)


def test_P7_mixed_ancestry_requires_a_constructor_issued_projection():
    refs = (SourcePortRef(ref="a", origin_cut="c", root=R_IN),
            SourcePortRef(ref="b", origin_cut="c", root=R_FIB))
    ch = _chart((_factor("m", (0, 1), None, refs=refs), (0,)),
                (_factor("y", (0, 1), R_FIB), (1,)))
    with pytest.raises(ProvenanceError) as ei:
        project_branch_root(ch, _roles(), branch_index=0,
                            polarity="ingress", port=_port())
    assert "combines source ports" in str(ei.value)


def test_P8_an_unlinked_source_fails_at_a_prepared_branch_root():
    ch = _chart((_factor("s", (0, 1), None), (0,)),
                (_factor("y", (0, 1), R_FIB), (1,)))
    with pytest.raises(ProvenanceError) as ei:
        project_branch_root(ch, _roles(), branch_index=0,
                            polarity="ingress", port=_port())
    assert "records no link" in str(ei.value)


def test_P9_a_reminted_non_none_source_is_refused():
    """The remint trap: the link EXISTS, but names an occurrence the role
    context never issued. Nothing about the factor itself distinguishes it
    from the honest one."""
    fresh = ProvenanceScope().owner()
    ch = _chart((_factor("s", (0, 1), fresh), (0,)),
                (_factor("y", (0, 1), R_FIB), (1,)))
    with pytest.raises(ProvenanceError) as ei:
        project_branch_root(ch, _roles(), branch_index=0,
                            polarity="ingress", port=_port())
    assert "has no recorded role" in str(ei.value)


def test_P10_the_wrong_polarity_root_is_refused_despite_identical_geometry():
    """Two factors with IDENTICAL type, codes, width and placement, differing
    only in which issued root their source records. The one linked to this
    polarity's root classifies; the one linked to the OTHER polarity's root
    is refused -- geometry can never rescue a wrong link."""
    good = _chart((_factor("s", (0, 1), R_IN), (0,)),
                  (_factor("y", (0, 1), R_FIB), (1,)))
    bp = project_branch_root(good, _roles(), branch_index=0,
                             polarity="ingress", port=_port())
    assert bp.alphabet == (0, 1) and bp.fibre_sizes == (2, 2)
    bad = _chart((_factor("s", (0, 1), R_OUT), (0,)),
                 (_factor("y", (0, 1), R_FIB), (1,)))
    assert tuple(bad.codes) == tuple(good.codes)
    assert bad.route.placements == good.route.placements
    with pytest.raises(ProvenanceError) as ei:
        project_branch_root(bad, _roles(), branch_index=0,
                            polarity="ingress", port=_port())
    assert "has no recorded role" in str(ei.value)


def test_P11_row_reconstruction_is_independent_of_the_recorded_triples():
    """`check_rows` REBUILDS each row from the recorded assembly schedule.
    A projection whose (label, fibre_key, row) triples disagree with that
    schedule is refused, even though the triples agree with themselves."""
    port = _port()
    ok = RowProjection(port=port, polarity="ingress", alphabet=(0, 1),
                       labels=(0, 1), fibre_keys=(0, 0), presenters=("f",),
                       support=(0,), rows=(0, 1), padding=(),
                       label_wires=(0,), fibre_wires=(), row_width=1)

    class _Ch:
        codes = (0, 1)
        n_qubits = 1

    assert ok.check_rows(_Ch())
    swapped = RowProjection(port=port, polarity="ingress", alphabet=(0, 1),
                            labels=(0, 1), fibre_keys=(0, 0),
                            presenters=("f",), support=(0,), rows=(1, 0),
                            padding=(), label_wires=(0,), fibre_wires=(),
                            row_width=1)

    class _ChS:
        codes = (1, 0)
        n_qubits = 1

    with pytest.raises(ProvenanceError) as ei:
        swapped.check_rows(_ChS())
    assert "assembles" in str(ei.value)


# ---------------------------------------------------------------------------
# transport-only mutations, per constructor
# ---------------------------------------------------------------------------

def test_P12_par_and_repart_transport_sources_by_identity():
    s = _factor("s", (0, 1), R_IN)
    y = _factor("y", (0, 1), R_FIB)
    # a NON-TRIVIAL repart: the second factor leads the wire order
    ch = _chart((s, (2,)), (y, (0,)), n=3)
    assert ch.route.parts == (s, y)
    assert ch.route.parts[0].source is s.source
    assert ch.route.parts[1].source is y.source
    # ... and an unlinked factor stays unlinked: Par/Repart never repair
    u = _factor("u", (0, 1), None)
    ch2 = _chart((u, (2,)), (y, (0,)), n=3)
    assert ch2.route.parts[0].source.sole.root is None
    with pytest.raises(ProvenanceError):
        project_branch_root(ch2, _roles(), branch_index=0,
                            polarity="ingress", port=_port())


def test_P13_tenpack_transports_sources_by_identity():
    s = _factor("s", (0, 1), R_IN)
    y = _factor("y", (0, 1), None)
    ch = _chart((s, (0,)), (y, (1,)))
    packed = tenpack(ch, (0, 1), (1, 0))
    assert packed.route.parts == (s, y)
    assert packed.route.parts[0].source is s.source
    assert packed.route.placements == ((1,), (0,)), (
        "TenPack re-addresses the binder coordinate and nothing else")
    assert packed.route.parts[1].source.sole.root is None, (
        "TenPack never repairs a missing link")


def test_P14_splice_transports_surviving_sources_and_consumes_the_port():
    tensor_ty = Ten(q, q)
    pref_in = _factor("p", (0, 1), R_FIB)
    pref_out = _factor("p", (0, 1), R_FIB)

    def _matched():
        return ChartFactor(
            factor_id="m", source=FactorSource((SourcePortRef(
                ref="m", origin_cut="c", root=R_IN),)),
            name="Y", owner=None, n_qubits=2, codes=(0, 1, 2, 3),
            role="residual", logical=tensor_ty)

    prod_in = _chart((pref_in, (0,)), (_matched(), (1, 2)), n=3)
    prod_out = _chart((pref_out, (0,)), (_matched(), (1, 2)), n=3)
    body = ChartFactor(
        factor_id="b", source=FactorSource((SourcePortRef(
            ref="b", origin_cut="c", root=R_IN),)),
        name="B", owner=None, n_qubits=2, codes=(0, 1, 2, 3),
        role="operand", logical=tensor_ty)
    body_in = _chart((body, (1, 2)), n=3)
    body_out = _chart((body, (1, 2)), n=3)
    ing, egr = tensor_splice(prod_in, prod_out, body_in, body_out, tensor_ty)
    # the survivors carry their EXACT sources; the matched port is consumed
    assert [f.factor_id for f in ing.route.parts] == ["p", "b"]
    assert ing.route.parts[0].source is pref_in.source
    assert ing.route.parts[1].source is body.source
    assert [f.factor_id for f in egr.route.parts] == ["p", "b"]
    assert egr.route.parts[0].source is pref_out.source
    assert all(f.factor_id != "m" for f in ing.route.parts)


def test_P15_complete_transports_branch_sources_and_links_the_inactive():
    s = _factor("s", (0, 1), R_IN)
    branch_chart = _chart((s, (0,)), n=1)

    class _Art:
        class selected_boundary:
            ingress = branch_chart
            egress = branch_chart

    sc = ProvenanceScope()
    z = TypedBinding("z", q, (2,), sc.owner(), sc.cut())
    done = complete_branch(index=0, artifact=_Art, uses=(),
                           inactive=(z,), local_to_ambient=(0,),
                           tag_value=0, ambient_width=3)
    for side in (done.ingress, done.egress):
        assert side.route.parts[0].source is s.source, (
            "Complete transports the branch's own factor sources by identity")
        inact = side.route.parts[-1]
        assert inact.factor_id == f"inactive:{z.owner_id}"
        assert inact.source.sole.reaches() == z.owner_id, (
            "the inactive resource links to its own binding occurrence")
        assert side.route.placements[-1] == (2,), (
            "the inactive resource is appended on ITS OWN wires -- fibre "
            "only, never among the main coordinates")
