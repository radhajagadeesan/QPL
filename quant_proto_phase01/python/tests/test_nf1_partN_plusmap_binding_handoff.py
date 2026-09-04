"""NF-1 Part N: typed binding identity across an open PLUSMAP branch boundary.

The n-ary adapter was repaired first; this closes the identical hole in the
binary one. The defect it fixes is invisible from the outside: the parent's
`TypedBinding`, the block's `used_bindings` and every `inactive` record all
agreed on the parent owner, while the branch's own selected root carried a
freshly minted one. The basis was right, so the ordered-code certificate was
satisfied; only the identities differed.

The repair is a handoff, not a reconciliation. The parent's binding is
relocated into the branch's coordinates -- wires change, nothing else does --
and the nested compilation ADOPTS that owner and introduction lineage instead
of minting its own. Both adapters go through one shared localiser, because two
formulations of this drift and the drift is unobservable.

`ctrl_ho` alone cannot witness the carried case: its open branch CONSUMES f
into an Apply spine, so no f factor survives to carry an owner. That is the
case the recorded handoff exists for, and the binary witnesses below supply
the carried case directly.
"""

import os
import sys

import numpy as np
import pytest
from pytket import Circuit

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from lang.types import Q, Arrow
from lang.terms import PlusMap, Var, H as Hg
from compile.to_pytket import compile, compile_with_artifacts
import compile.to_pytket as TP
from compile.frames import (ProvenanceError, ProvenanceScope, TypedBinding,
                            BindingTransport, issue_binding_transport,
                            localize_bindings, check_block_resource_identity,
                            semantic_action, leakage)
from dataclasses import replace as _replace

q = Q()
MODES = [False, True]
ATOL = 1e-10


def _plan(term, env=None, materialize=False):
    TP._USE_BLOCK_OBSERVED.clear()
    res, arts = compile_with_artifacts(term, env=env, materialize=materialize)
    assert TP._USE_BLOCK_OBSERVED, "the open PlusMap reached no Block plan"
    return res, arts, TP._USE_BLOCK_OBSERVED[-1]


def _ctrl_ho_plan(materialize=False):
    from test_nf1_beta_tensor import _fixture
    TP._USE_BLOCK_OBSERVED.clear()
    try:
        compile(_fixture("ctrl_ho_closed_plus_map"), materialize=materialize)
    except Exception:
        pass
    assert TP._USE_BLOCK_OBSERVED, "no use-block plan was produced"
    return TP._USE_BLOCK_OBSERVED[-1]


def _carried_witness():
    """A binary open PlusMap whose left branch CARRIES its resource."""
    return PlusMap(q, q, Var("z", q), Hg(0, q))


def _two_resource_witness():
    """Two equal-typed resources, one per branch. Interchanging them must not
    go unnoticed, and equal type is exactly what makes that possible."""
    return PlusMap(q, q, Var("z", q), Var("w", q))


def _factor(artifact, side, name):
    sb = artifact.selected_boundary
    chart = sb.ingress if side == "ingress" else sb.egress
    if chart.route is None:
        return []
    return [f for f in chart.route.parts if f.name == name]


# ---------------------------------------------------------------------------
# N1-N5: the carried case, which ctrl_ho cannot show.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("wire", [0, 1, 2])
@pytest.mark.parametrize("materialize", MODES)
def test_N1_one_owner_across_an_open_plusmap(wire, materialize):
    """THE gate. Before the handoff, the last row here read own:4.1.1."""
    res, _arts, pl = _plan(_carried_witness(), {"z": [wire]}, materialize)
    b0, b1 = pl.branches
    parent = b0.used_bindings[0]
    owner, origin = parent.owner_id, parent.intro_cut

    assert [x.owner_id for x in b1.inactive] == [owner]
    assert [t.owner_id for t in b0.binding_transport] == [owner]
    for side in ("ingress", "egress"):
        yz = _factor(b0.artifact, side, "Y_z")
        assert len(yz) == 1, f"{side}: the branch root carries no Y_z"
        assert yz[0].owner == owner, (
            f"{side}: the branch root's Y_z is {yz[0].owner}, not the "
            f"parent's {owner}")
        assert yz[0].logical == q
        assert tuple(yz[0].codes) == tuple(parent.codes)
        s = _factor(b0.artifact, side, "S")
        assert len(s) == 1 and s[0].owner != owner, (
            f"{side}: the summand parameter and z share an owner")

    # type, encoding and lineage survive the relocation
    t = b0.binding_transport[0]
    assert t.logical == q and t.intro_cut == origin
    assert tuple(t.codes) == tuple(parent.codes)
    for x in tuple(b0.used_bindings) + tuple(b1.inactive):
        assert x.logical == q and x.intro_cut == origin

    # THE TRANSPORT EQUATION, in exactly that order
    assert tuple(b0.local_to_ambient[w] for w in t.local_wires) == \
        t.ambient_wires == tuple(parent.wires) == (wire,)

    assert b0.dim == 4 and b1.dim == 4 and pl.ingress.dim == 8
    assert check_block_resource_identity(pl, (parent,), (), "t: ")


@pytest.mark.parametrize("materialize", MODES)
def test_N2_two_equal_typed_resources_are_not_interchangeable(materialize):
    """ANTI-SWAP. Each branch consumes the owner actually handed to IT.

    Both resources are Q on one wire, so type, dimension and encoding cannot
    tell them apart -- only the recorded identity can, which is the point.
    """
    _res, _arts, pl = _plan(_two_resource_witness(), {"z": [0], "w": [1]},
                            materialize)
    b0, b1 = pl.branches
    z = b0.used_bindings[0]
    w = b1.used_bindings[0]
    assert z.owner_id != w.owner_id, "two resources collapsed to one owner"
    assert z.logical == w.logical == q, "the witness is not equal-typed"

    for blk, mine, theirs, nm in ((b0, z, w, "z"), (b1, w, z, "w")):
        assert [t.owner_id for t in blk.binding_transport] == [mine.owner_id]
        assert [x.owner_id for x in blk.inactive] == [theirs.owner_id]
        for side in ("ingress", "egress"):
            f = _factor(blk.artifact, side, f"Y_{nm}")
            assert len(f) == 1 and f[0].owner == mine.owner_id, (
                f"branch {blk.index} {side}: its own resource is not the one "
                f"it was handed")
            assert not _factor(blk.artifact, side, f"Y_{'w' if nm == 'z' else 'z'}")
        t = blk.binding_transport[0]
        assert tuple(blk.local_to_ambient[i] for i in t.local_wires) == \
            tuple(mine.wires)
    assert check_block_resource_identity(pl, (z, w), (), "t: ")

    # Handing branch 0 the resource branch 1 was given is refused at the
    # moment the block is built -- the handoffs and `uses` must name the same
    # owners, so the swap cannot even be represented.
    with pytest.raises(ProvenanceError) as ei:
        _replace(b0, binding_transport=b1.binding_transport)
    assert "handoffs were recorded for" in str(ei.value)
    # ... and forcing it past that, by swapping `uses` too, is caught by the
    # factor standing on the coordinates the handoff recorded.
    forced = _replace(pl, branches=(
        _replace(b0, uses=b1.uses, used_bindings=b1.used_bindings,
                 binding_transport=b1.binding_transport,
                 inactive=b0.used_bindings),
        b1))
    with pytest.raises(ProvenanceError) as ei:
        check_block_resource_identity(forced, (z, w), (), "t: ")
    # w is held on wire 1 by the parent; branch 0's placement takes its
    # branch-local wire to wire 0, where z lives. Equal type and equal
    # dimension cannot see that; the recorded transport does.
    assert "transports from" in str(ei.value), str(ei.value)


@pytest.mark.parametrize("materialize", MODES)
def test_N3_ctrl_ho_keeps_its_consumed_resource_by_recorded_handoff(materialize):
    """ctrl_ho's open branch CONSUMES f into an Apply spine, so no f factor
    survives. The handoff is the proof -- and no f factor is invented."""
    pl = _ctrl_ho_plan(materialize)
    b0, b1 = pl.branches
    assert b0.uses == () and len(b1.uses) == 1
    parent = b0.inactive[0]
    assert b1.uses == (parent.owner_id,)
    assert [x.owner_id for x in b1.used_bindings] == [parent.owner_id]

    assert len(b1.binding_transport) == 1
    t = b1.binding_transport[0]
    assert t.owner_id == parent.owner_id
    assert t.intro_cut == parent.intro_cut
    assert t.logical == parent.logical == Arrow(Arrow(q, q), Arrow(q, q))
    assert tuple(t.codes) == tuple(parent.codes)
    assert tuple(t.ambient_wires) == tuple(parent.wires)
    assert tuple(b1.local_to_ambient[w] for w in t.local_wires) == \
        t.ambient_wires

    # consumed: absent from its own chart, and NOT fabricated as a factor
    for side in ("ingress", "egress"):
        chart = b1.ingress if side == "ingress" else b1.egress
        assert parent.owner_id not in {f.owner for f in chart.route.parts}
        carried = b0.ingress if side == "ingress" else b0.egress
        assert parent.owner_id in {f.owner for f in carried.route.parts}, (
            f"{side}: the branch that carries f untouched lost it")

    assert b0.dim == 64 and b1.dim == 16
    assert pl.ingress.dim == 80 and pl.egress.dim == 80
    assert check_block_resource_identity(pl, (parent,), (), "t: ")


@pytest.mark.parametrize("materialize", MODES)
def test_N4_ctrl_ho_action_is_unchanged(materialize):
    """The repair is provenance-only: the circuit must not move."""
    pl = _ctrl_ho_plan(materialize)
    c = Circuit(pl.ambient_width)
    TP._emit_open_use_block(c, pl)
    U = c.get_unitary()
    W = semantic_action(pl.ingress, U, pl.egress)
    assert W.shape == (80, 80)
    assert leakage(pl.ingress, U, pl.egress) < ATOL
    assert abs(float(c.phase)) < 1e-12
    # Each block is its branch's OWN action tensored with the identity on the
    # resources that branch does not touch -- built from the branch artifact
    # and the recorded inactive dimensions, not read back out of W.
    for b in pl.branches:
        Jm = list(pl.inclusion(b.index, "ingress"))
        Jp = list(pl.inclusion(b.index, "egress"))
        sb = b.artifact.selected_boundary
        G = semantic_action(sb.ingress, b.artifact.unitary, sb.egress)
        carried = 1
        for x in {y.owner_id: y for y in b.inactive}.values():
            carried *= len(x.codes)
        expected = np.kron(G, np.eye(carried))
        sub = W[np.ix_(Jp, Jm)]
        assert sub.shape == expected.shape == (b.dim, b.dim)
        assert np.allclose(sub, expected, atol=ATOL, rtol=0.0), (
            f"block {b.index} action moved by "
            f"{np.max(np.abs(sub - expected)):.3e}")
    kept = sum(
        np.abs(W[np.ix_(list(pl.inclusion(b.index, "egress")),
                        list(pl.inclusion(b.index, "ingress")))]).sum()
        for b in pl.branches)
    assert abs(float(np.abs(W).sum()) - float(kept)) < ATOL, (
        "the blocks are not orthogonal")


def test_N5_the_parameter_is_never_the_captured_binding():
    """The live summand payload and the context a branch captured are two
    resources; sharing an owner would count one factor twice."""
    _res, _arts, pl = _plan(_carried_witness(), {"z": [2]})
    parent = pl.branches[0].used_bindings[0]
    assert check_block_resource_identity(pl, (parent,), ("own:elsewhere",))
    with pytest.raises(ProvenanceError) as ei:
        check_block_resource_identity(pl, (parent,), (parent.owner_id,))
    assert "not the context it uses" in str(ei.value)


# ---------------------------------------------------------------------------
# N6-N10: mutation gates. Each must fail BEFORE the parent gains a command.
# ---------------------------------------------------------------------------

def _emit_guard():
    """Spy that records whether emission was ever reached."""
    seen = []
    orig = TP._emit_open_use_block

    def spy(circ, plan):
        seen.append(plan)
        return orig(circ, plan)

    return seen, orig, spy


def test_N6_reminting_the_branch_local_owner_is_refused():
    """Give the branch's z factor a fresh owner. The ordered codes are
    untouched, so the BASIS still agrees exactly -- and it is still refused."""
    _res, _arts, pl = _plan(_carried_witness(), {"z": [2]})
    b0 = pl.branches[0]
    parent = b0.used_bindings[0]
    assert check_block_resource_identity(pl, (parent,), (), "t: ")

    fresh = ProvenanceScope().owner()
    assert fresh != parent.owner_id
    mutated = {}
    for side in ("ingress", "egress"):
        chart = b0.ingress if side == "ingress" else b0.egress
        parts = tuple(_replace(f, owner=fresh) if f.owner == parent.owner_id
                      else f for f in chart.route.parts)
        mutated[side] = _replace(chart,
                                 route=_replace(chart.route, parts=parts))
    bad = _replace(pl, branches=(_replace(b0, **mutated),) + pl.branches[1:])
    assert tuple(bad.branches[0].ingress.codes) == tuple(b0.ingress.codes), (
        "the mutation changed the basis; it must change only the identity")
    with pytest.raises(ProvenanceError) as ei:
        check_block_resource_identity(bad, (parent,), (), "t: ")
    assert "carry the PARENT'S resource" in str(ei.value)


def test_N7_removing_the_typed_view_remints_and_is_caught():
    """END TO END. Withhold the handoff and the nested compilation mints its
    own owner again -- the exact defect this phase closed. Nothing may be
    emitted."""
    seen, orig_emit, spy = _emit_guard()
    o_art = TP._compile_branch_artifact

    def no_handoff(branch, *, env=None, scope=None, parameter=None,
                   typed_env=None, **kw):
        return o_art(branch, env=env, scope=scope, parameter=parameter,
                     typed_env=None, **kw)

    TP._compile_branch_artifact, TP._emit_open_use_block = no_handoff, spy
    try:
        with pytest.raises(ProvenanceError) as ei:
            compile(_carried_witness(), env={"z": [2]})
    finally:
        TP._compile_branch_artifact = o_art
        TP._emit_open_use_block = orig_emit
    assert not seen, "the parent was emitted despite an unproved resource"
    assert "carry the PARENT'S resource" in str(ei.value)


def test_N8_used_bindings_alone_do_not_satisfy_the_gate():
    """`used_bindings` is the parent's INTENTION. Dropping the handoff while
    keeping it must not pass, and the parent must gain nothing."""
    _res, _arts, pl = _plan(_carried_witness(), {"z": [2]})
    b0 = pl.branches[0]
    parent = b0.used_bindings[0]
    bare = _replace(b0, binding_transport=())
    assert bare.used_bindings == b0.used_bindings, "the intention is retained"
    bad = _replace(pl, branches=(bare,) + pl.branches[1:])
    circ = Circuit(pl.ambient_width)
    circ.X(0)
    before = circ.n_gates
    with pytest.raises(ProvenanceError) as ei:
        check_block_resource_identity(bad, (parent,), (), "t: ")
    assert "no recorded handoff" in str(ei.value)
    assert circ.n_gates == before


def test_N9_a_broken_transport_or_lineage_is_refused():
    """Alter the local wire order, the introduction cut, the type or the
    encoding: each is a different resource, or a different placement."""
    _res, _arts, pl = _plan(_two_resource_witness(), {"z": [0], "w": [1]})
    b0 = pl.branches[0]
    z = b0.used_bindings[0]
    w = pl.branches[1].used_bindings[0]

    # local wire order / transport
    moved = _replace(b0, local_to_ambient=tuple(reversed(b0.local_to_ambient)))
    with pytest.raises(ProvenanceError) as ei:
        check_block_resource_identity(
            _replace(pl, branches=(moved,) + pl.branches[1:]), (z, w), ())
    assert "transports from" in str(ei.value)

    # lineage, type and encoding, at the handoff itself
    sc = ProvenanceScope()
    parent = TypedBinding("z", q, (0,), sc.owner(), sc.cut())
    view_ok = TypedBinding("z", q, (1,), parent.owner_id, parent.intro_cut,
                           codes=tuple(parent.codes))
    assert issue_binding_transport(parent, view_ok, (2, 0), "t: ")
    for bad_view, why in (
            (TypedBinding("z", q, (1,), sc.owner(), parent.intro_cut),
             "owner_id"),
            (TypedBinding("z", q, (1,), parent.owner_id, sc.cut()),
             "intro_cut"),
            (TypedBinding("z", Arrow(q, q), (1, 2), parent.owner_id,
                          parent.intro_cut), "logical"),
            (TypedBinding("z", q, (1,), parent.owner_id, parent.intro_cut,
                          codes=(1, 0)), "codes")):
        with pytest.raises(ProvenanceError) as ei:
            issue_binding_transport(parent, bad_view, (2, 0, 1), "t: ")
        assert why in str(ei.value) and "keeps its identity" in str(ei.value)


def test_N10_one_shared_localiser_serves_both_adapters():
    """ANTI-DRIFT. Both open-sum adapters go through `localize_bindings`, so
    there is no second formulation of the relocation to diverge."""
    import inspect
    src = inspect.getsource(TP)
    for adapter in ("NPlusMap open branch", "PlusMap open branch"):
        assert adapter in src, f"{adapter} no longer labels a handoff"
    assert src.count("localize_bindings(") == 2, (
        f"expected exactly the two adapter call sites, found "
        f"{src.count('localize_bindings(')}")
    # the helper itself changes only the wires
    sc = ProvenanceScope()
    parent = TypedBinding("f", Arrow(q, q), (4, 5), sc.owner(), sc.cut())
    views, transports = localize_bindings(
        (parent,), {"f": (2, 3)}, (9, 9, 4, 5), "t: ")
    v = views["f"]
    assert v.wires == (2, 3)
    for fld in ("owner_id", "logical", "intro_cut", "codes"):
        assert getattr(v, fld) == getattr(parent, fld), f"{fld} was rewritten"
    assert len(transports) == 1
    assert transports[0].ambient_wires == (4, 5)
    with pytest.raises(ProvenanceError) as ei:
        localize_bindings((parent,), {}, (9, 9, 4, 5), "t: ")
    assert "no branch-local wires" in str(ei.value)
