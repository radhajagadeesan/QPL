"""NF-1 Part J: open-occurrence Complete / Block PLANNING.

Each alternative is completed against the context it does NOT use, and the
parent is the TAGGED DIRECT SUM of those completed blocks:

    uses(u0) = {}            Complete(u0 | f)     = 4 x 16 = 64
    uses(u1) = {owner(f)}    Complete({} | u1)    = 1 x 16 = 16
                             Block                = 64 (+) 16 = 80

independently on ingress and egress.

WHAT THIS REFUSES. The withdrawn model completed the whole occurrence against
one uniform context factor and produced 256 on the ingress and 64 on the
egress, then went looking for a missing factor of 4 -- an "h residual" that is
not a separate resource at all, but the S_h factor already inside u1's
selected root. The uniform reading (4 + 16) x 16 = 320 is refused here too.

This module is PLANNING ONLY: no gate, no phase, no allocation, no emission.
"""

import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(__file__))

from lang.types import Q, Ten, Arrow, Plus, Unit
from lang.terms import PlusMap, Apply, Var, Id
import compile.to_pytket as TP
from compile.to_pytket import compile
from compile.frames import (ProvenanceError, ProvenanceScope, TypedBinding,
                            UseBlockLayout,
                            ChartFactor, BoundaryChart, CompletedBranch,
                            OpenUseBlockPlan, complete_branch, plan_use_block,
                            par_then_repart, scatter_repart)

q = Q()
MODES = [False, True]

CTRL_HO_LEFT = 64
CTRL_HO_RIGHT = 16
CTRL_HO_PARENT = 80


def ctrl_ho_plan(materialize=False):
    from test_nf1_beta_tensor import _fixture
    TP._USE_BLOCK_OBSERVED.clear()
    compile(_fixture("ctrl_ho_closed_plus_map"), materialize=materialize)
    assert TP._USE_BLOCK_OBSERVED, "no use-block plan was produced"
    return TP._USE_BLOCK_OBSERVED[-1]


# ===========================================================================
# 1. The pinned dimensions
# ===========================================================================

@pytest.mark.parametrize("materialize", MODES)
def test_J1_block_dimensions_are_64_and_16(materialize):
    pl = ctrl_ho_plan(materialize)
    blocks = {b.index: b for b in pl.branches}
    assert blocks[0].dim == CTRL_HO_LEFT
    assert blocks[1].dim == CTRL_HO_RIGHT
    assert blocks[0].ingress.dim == blocks[0].egress.dim == CTRL_HO_LEFT
    assert blocks[1].ingress.dim == blocks[1].egress.dim == CTRL_HO_RIGHT


@pytest.mark.parametrize("materialize", MODES)
def test_J2_parent_is_eighty_on_both_polarities(materialize):
    pl = ctrl_ho_plan(materialize)
    assert pl.ingress.dim == CTRL_HO_PARENT
    assert pl.egress.dim == CTRL_HO_PARENT
    assert pl.ingress.dim == pl.egress.dim


@pytest.mark.parametrize("materialize", MODES)
def test_J3_inclusion_sizes(materialize):
    pl = ctrl_ho_plan(materialize)
    for side in ("ingress", "egress"):
        assert len(pl.inclusion(0, side)) == CTRL_HO_LEFT
        assert len(pl.inclusion(1, side)) == CTRL_HO_RIGHT


# ===========================================================================
# 2. Anti-oracles
# ===========================================================================

@pytest.mark.parametrize("materialize", MODES)
def test_J4_the_withdrawn_uniform_models_are_refused(materialize):
    """256 and (4+16) x 16 = 320 are different claims, not this one."""
    pl = ctrl_ho_plan(materialize)
    blocks = {b.index: b for b in pl.branches}
    assert pl.ingress.dim not in (256, 320)
    total_main = blocks[0].artifact.selected_boundary.ingress.dim \
        + blocks[1].artifact.selected_boundary.ingress.dim
    assert total_main == 4 + 16 == 20
    assert total_main * 16 == 320 != pl.ingress.dim, (
        "a uniform (sum of branch dims) x T_f product is not the Block")
    assert CTRL_HO_LEFT != CTRL_HO_RIGHT, (
        "the two blocks are completed against OPPOSITE contexts and must not "
        "collapse into one multiplier")


@pytest.mark.parametrize("materialize", MODES)
def test_J5_f_is_not_multiplied_into_both_branches(materialize):
    """f is inactive in u0 and USED by u1, so it completes exactly one."""
    pl = ctrl_ho_plan(materialize)
    blocks = {b.index: b for b in pl.branches}
    assert blocks[0].uses == ()
    assert len(blocks[1].uses) == 1
    assert [b.name for b in blocks[0].inactive] == ["f"]
    assert blocks[1].inactive == ()
    names0 = [f.name for f in blocks[0].ingress.route.parts]
    names1 = [f.name for f in blocks[1].ingress.route.parts]
    assert names0.count("Y_f") == 1, f"u0 factors {names0}"
    assert "Y_f" not in names1, (
        f"u1 already binds f; completing it against f again would count the "
        f"same resource twice: {names1}")


@pytest.mark.parametrize("materialize", MODES)
def test_J6_no_h_residual_is_fabricated(materialize):
    """h is already an operand factor inside u1's selected root, not a port.

    It is identified by RECORDED TYPE and PROVENANCE -- an operand factor of
    logical type Q-oQ with a real owner -- never by "dimension 4", which
    Q(x)Q also is.
    """
    pl = ctrl_ho_plan(materialize)
    blocks = {b.index: b for b in pl.branches}
    for b in pl.branches:
        for side in (b.ingress, b.egress):
            for f in side.route.parts:
                assert f.name not in ("h", "Y_h"), (
                    f"a residual was fabricated for the head: {f.name}")
                if f.role == "residual" and f.name.startswith("Y_"):
                    assert f.logical is not None

    endo = Arrow(q, q)
    s_h = [f for f in blocks[1].ingress.route.parts
           if f.role == "operand" and f.logical == endo]
    assert len(s_h) == 1, (
        f"u1 must carry exactly one operand factor typed Q-oQ; got "
        f"{[(f.name, f.role, f.logical, f.dim) for f in blocks[1].ingress.route.parts]}")
    assert s_h[0].owner is not None and ":" in str(s_h[0].owner), (
        f"S_h carries no recorded provenance: owner={s_h[0].owner!r}")
    assert s_h[0].dim == 4

    # NEGATIVE CONTROL: Q(x)Q is also dimension 4 and must NOT satisfy the
    # test, so the identification cannot be reading the dimension.
    decoy = ChartFactor(name="S", owner="cut:decoy", n_qubits=2,
                        codes=(0, 1, 2, 3), role="operand", logical=Ten(q, q))
    assert decoy.dim == s_h[0].dim == 4
    assert decoy.logical != endo, (
        "the decoy must be a different type of the same dimension")
    assert not [f for f in (decoy,) if f.logical == endo], (
        "an equal-dimension Q(x)Q factor must not be accepted as S_h")


@pytest.mark.parametrize("materialize", MODES)
def test_J7_branch_use_is_read_from_recorded_provenance(materialize):
    """The use set is a set of owner ids, not a type or a dimension."""
    pl = ctrl_ho_plan(materialize)
    blocks = {b.index: b for b in pl.branches}
    for oid in blocks[1].uses:
        assert isinstance(oid, str) and ":" in oid, (
            f"branch use {oid!r} is not a scoped provenance id")
    owners = {b.owner_id for b in blocks[0].inactive}
    assert owners.isdisjoint(set(blocks[0].uses))
    assert set(blocks[1].uses) == {b.owner_id for b in blocks[0].inactive}, (
        "the resource u1 uses must be exactly the one u0 is completed against")


# ===========================================================================
# 3. Structure of the Block
# ===========================================================================

@pytest.mark.parametrize("materialize", MODES)
def test_J8_blocks_are_orthogonal_and_exhaust_the_parent(materialize):
    pl = ctrl_ho_plan(materialize)
    for side in ("ingress", "egress"):
        parent = (pl.ingress if side == "ingress" else pl.egress).codes
        c0 = pl.tagged_codes(0, side)
        c1 = pl.tagged_codes(1, side)
        assert not (set(c0) & set(c1)), "the blocks are not orthogonal"
        assert tuple(c0) + tuple(c1) == tuple(parent), (
            "the parent is not the ordered exhaustion of its blocks")
        assert len(set(parent)) == len(parent)


@pytest.mark.parametrize("materialize", MODES)
def test_J9_sparse_order_is_preserved_blockwise(materialize):
    pl = ctrl_ho_plan(materialize)
    for side in ("ingress", "egress"):
        for b in pl.branches:
            js = pl.inclusion(b.index, side)
            assert list(js) == sorted(js), (
                f"block {b.index} {side}: codes do not appear in the parent "
                f"in their own order")


@pytest.mark.parametrize("materialize", MODES)
def test_J10_vhat_factorisations(materialize):
    """Vhat_0 = V_u0 (x) Y_f  and  Vhat_1 = Y_empty (x) V_u1."""
    pl = ctrl_ho_plan(materialize)
    blocks = {b.index: b for b in pl.branches}

    v0 = blocks[0].artifact.selected_boundary.ingress.dim
    prod0 = 1
    for f in blocks[0].ingress.route.parts:
        prod0 *= f.dim
    assert prod0 == blocks[0].dim == v0 * 16, (
        f"Vhat_0 must factor as V_u0({v0}) x Y_f(16)")
    y_f = [f for f in blocks[0].ingress.route.parts if f.name == "Y_f"]
    assert len(y_f) == 1 and y_f[0].dim == 16 and y_f[0].role == "residual"

    v1 = blocks[1].artifact.selected_boundary.ingress.dim
    prod1 = 1
    for f in blocks[1].ingress.route.parts:
        prod1 *= f.dim
    assert prod1 == blocks[1].dim == 1 * v1, (
        f"Vhat_1 must factor as Y_empty(1) x V_u1({v1})")

    # the same ordered factorisation on both polarities: W J^- = J^+ Vhat
    for b in pl.branches:
        fi = [(f.name, f.role, f.dim) for f in b.ingress.route.parts]
        fe = [(f.name, f.role, f.dim) for f in b.egress.route.parts]
        assert fi == fe, f"block {b.index}: Vhat differs between polarities"


@pytest.mark.parametrize("materialize", MODES)
def test_J11_tag_placement_is_stable_and_outside_every_block(materialize):
    pl = ctrl_ho_plan(materialize)
    assert len(pl.tag_wires) == 1
    for b in pl.branches:
        for side in (b.ingress, b.egress):
            placed = {w for g in side.route.placements for w in g}
            assert not (placed & set(pl.tag_wires)), (
                f"block {b.index} occupies the tag wire {pl.tag_wires}")
    assert ctrl_ho_plan(not materialize).tag_wires == pl.tag_wires, (
        "the tag placement must not depend on materialisation")


@pytest.mark.parametrize("materialize", MODES)
def test_J12_support_and_spectators_partition_the_register(materialize):
    pl = ctrl_ho_plan(materialize)
    assert set(pl.support) | set(pl.spectators) == set(range(pl.ambient_width))
    assert not (set(pl.support) & set(pl.spectators))
    assert set(pl.tag_wires) <= set(pl.support)


@pytest.mark.parametrize("materialize", MODES)
def test_J13_the_plan_validates(materialize):
    assert ctrl_ho_plan(materialize).validate()


# ===========================================================================
# 4. Planning is pure
# ===========================================================================

def test_J14_planning_leaves_every_prepared_artifact_unchanged():
    """Snapshot each exact BranchArtifact BEFORE planning; compare after.

    Counting gates only shows the branches were compiled; this shows planning
    did not touch them -- same object, same commands, same phase, same
    circuit and same unitary.
    """
    from test_nf1_beta_tensor import _fixture
    import numpy as _np
    snaps = []
    orig = TP._compile_branch_artifact

    def spy(branch, *, env=None, scope=None, **kw):
        a = orig(branch, env=env, scope=scope, **kw)
        snaps.append((a, len(a.cmds), a.phase, a.circuit,
                      _np.array(a.circuit.get_unitary(), copy=True),
                      [str(c) for c in a.cmds]))
        return a

    TP._compile_branch_artifact = spy
    TP._USE_BLOCK_OBSERVED.clear()
    try:
        compile(_fixture("ctrl_ho_closed_plus_map"), materialize=False)
    finally:
        TP._compile_branch_artifact = orig
    assert TP._USE_BLOCK_OBSERVED, "the planner was not reached"
    assert len(snaps) == 2
    for a, n, ph, circ, U, cmds in snaps:
        assert len(a.cmds) == n, "planning changed a branch's command list"
        assert a.phase == ph, "planning changed a branch's phase"
        assert a.circuit is circ, "planning replaced a branch's circuit"
        _np.testing.assert_array_equal(
            _np.array(a.circuit.get_unitary()), U)
        assert [str(c) for c in a.cmds] == cmds
        assert abs(ph) < 1e-12
    assert sorted(n for _, n, _, _, _, _ in snaps) == [1, 5]


def test_J15_branches_are_prepared_once_and_used_by_identity():
    """The plan holds the EXACT BranchArtifact objects, not copies."""
    from test_nf1_beta_tensor import _fixture
    made = []
    orig = TP._compile_branch_artifact

    def spy(branch, *, env=None, scope=None, **kw):
        a = orig(branch, env=env, scope=scope, **kw)
        made.append(a)
        return a

    TP._compile_branch_artifact = spy
    TP._USE_BLOCK_OBSERVED.clear()
    try:
        compile(_fixture("ctrl_ho_closed_plus_map"), materialize=False)
    finally:
        TP._compile_branch_artifact = orig
    pl = TP._USE_BLOCK_OBSERVED[-1]
    assert len(made) == 2, f"{len(made)} branch preparations, want 2"
    for b in pl.branches:
        assert any(b.artifact is m for m in made), (
            "the plan holds a branch artifact this compilation did not make")


class _TwoFaced:
    """Same selected boundary, deliberately DIFFERENT frame data.

    Completion must consume the selected root only, so both of these must
    produce byte-identical completed charts. A reader of fin/fout diverges.
    """
    def __init__(self, ch, fin, fout):
        from compile.frames import SelectedBoundary
        self.selected_boundary = SelectedBoundary(ingress=ch, egress=ch,
                                                  origin="test")
        self.fin, self.fout = fin, fout
        self.input_frame, self.output_frame = fin, fout


def test_J16_completion_reads_the_selected_root_not_the_frames():
    """Two artifacts, one selected boundary, different Frames -> one plan."""
    from compile.frames import canonical_frame
    amb = 4
    ch = _synthetic(2, amb)
    lay = UseBlockLayout(ambient_width=amb, owned_wires=(0,),
                         tag_wires=(1,), workspace_wires=(2, 3))
    sc = ProvenanceScope()
    b = TypedBinding("z", q, (0,), sc.owner(), sc.cut())
    a1 = _TwoFaced(ch, canonical_frame(q), canonical_frame(q))
    a2 = _TwoFaced(ch, canonical_frame(Ten(q, q)),
                   canonical_frame(Plus(q, Ten(q, q))))
    assert a1.fin.dim != a2.fin.dim and a1.fout.dim != a2.fout.dim, (
        "the two artifacts must differ in their Frames, or this proves "
        "nothing")
    made = []
    for a in (a1, a2):
        blk = complete_branch(index=0, artifact=a, uses=(), inactive=(b,),
                              local_to_ambient=(2, 3), tag_value=0,
                              ambient_width=amb)
        made.append((blk.dim, blk.ingress.codes, blk.egress.codes,
                     tuple((f.name, f.role, f.dim)
                           for f in blk.ingress.route.parts),
                     blk.ingress.route.placements))
    assert made[0] == made[1], (
        "the completed block changed with the Frame, so a Frame was read "
        "where a selected root exists")
    assert made[0][0] == 4 * 2


# ===========================================================================
# 5. A malformed plan fails closed
# ===========================================================================

def _synthetic(k, ambient):
    """A branch-LOCAL chart on its own wires 0..k-1, ready to be lifted."""
    f = ChartFactor(name="V", owner="cut:v", n_qubits=k,
                    codes=tuple(range(1 << k)))
    rep, pl = scatter_repart((tuple(range(k)),), ambient)
    return par_then_repart((f,), rep, ambient, "v", placements=pl,
                           kind="scatter")


class _FakeArt:
    def __init__(self, ch):
        from compile.frames import SelectedBoundary
        self.selected_boundary = SelectedBoundary(ingress=ch, egress=ch,
                                                  origin="test")


def test_J17_overlapping_blocks_are_refused():
    """Two blocks sharing a tag value are not a direct sum."""
    amb = 3
    ch = _synthetic(2, amb)
    sc = ProvenanceScope()
    blks = [complete_branch(index=i, artifact=_FakeArt(ch), uses=(),
                            inactive=(), local_to_ambient=(1, 2),
                            tag_value=0, ambient_width=amb)
            for i in (0, 1)]
    lay = UseBlockLayout(ambient_width=amb, owned_wires=(),
                         tag_wires=(0,), workspace_wires=(1, 2))
    with pytest.raises(ProvenanceError) as e:
        plan_use_block(blks, lay)
    assert "not disjoint" in str(e.value) or "orthogonal" in str(e.value)


def test_J18_a_block_on_its_own_tag_wire_is_refused():
    amb = 2
    ch = _synthetic(2, amb)
    blk = complete_branch(index=0, artifact=_FakeArt(ch), uses=(),
                          inactive=(), local_to_ambient=(0, 1),
                          tag_value=1, ambient_width=amb)
    lay = UseBlockLayout(ambient_width=amb, owned_wires=(),
                         tag_wires=(0,), workspace_wires=(1,))
    with pytest.raises(ProvenanceError) as e:
        plan_use_block([blk], lay)
    assert "tag" in str(e.value)


def test_J19_a_branch_cannot_be_used_and_inactive_at_once():
    amb = 3
    ch = _synthetic(2, amb)
    sc = ProvenanceScope()
    b = TypedBinding("z", q, (0,), sc.owner(), sc.cut())
    with pytest.raises(ProvenanceError) as e:
        complete_branch(index=0, artifact=_FakeArt(ch), uses=(b.owner_id,),
                        inactive=(b,), local_to_ambient=(1, 2),
                        tag_value=0, ambient_width=amb)
    assert "used and inactive" in str(e.value)


def test_J20_a_branch_without_a_selected_root_cannot_be_completed():
    class _NoRoot:
        selected_boundary = None
    with pytest.raises(ProvenanceError) as e:
        complete_branch(index=0, artifact=_NoRoot(), uses=(), inactive=(),
                        local_to_ambient=(0,), tag_value=0, ambient_width=1)
    assert "no selected boundary" in str(e.value)


def test_J21_inactive_completion_multiplies_exactly_once():
    """Two distinct owners multiply twice; one owner named twice, once."""
    amb = 5
    ch = _synthetic(2, amb)
    sc = ProvenanceScope()
    b1 = TypedBinding("z", q, (0,), sc.owner(), sc.cut())
    b2 = TypedBinding("w", q, (1,), sc.owner(), sc.cut())
    one = complete_branch(index=0, artifact=_FakeArt(ch), uses=(),
                          inactive=(b1,), local_to_ambient=(3, 4),
                          tag_value=0, ambient_width=amb)
    two = complete_branch(index=0, artifact=_FakeArt(ch), uses=(),
                          inactive=(b1, b2), local_to_ambient=(3, 4),
                          tag_value=0, ambient_width=amb)
    assert one.dim == 4 * 2 and two.dim == 4 * 2 * 2


# ===========================================================================
# 6. The parent codes, enumerated INDEPENDENTLY
# ===========================================================================
#
# From the Part-I pinned branch codes and the block->ambient injection alone.
# No production lifting helper is used as the oracle.

U0_ING = (0, 2, 1, 3)                       # 3-wire branch register
U0_EGR = (0, 4, 1, 5)
U1_ING = (0, 1, 16, 17, 32, 33, 48, 49,     # 7-wire branch register
          64, 65, 80, 81, 96, 97, 112, 113)
U1_EGR = (0, 64, 1, 65, 2, 66, 3, 67,
          4, 68, 5, 69, 6, 70, 7, 71)

AMBIENT = 10
TAG_WIRE = 4
WORKSPACE = (5, 6, 7)
F_WIRES = (0, 1, 2, 3)
BLOCK_TO_AMBIENT = (4, 5, 6, 7, 0, 1, 2, 3)


def _place(code, width, wires, n=AMBIENT):
    """Scatter a `width`-bit code onto `wires` of an n-wire register."""
    out = 0
    for i, w in enumerate(wires):
        if (code >> (width - 1 - i)) & 1:
            out |= 1 << (n - 1 - w)
    return out


def _expected(side):
    u0 = U0_ING if side == "ingress" else U0_EGR
    u1 = U1_ING if side == "ingress" else U1_EGR
    # block 0 : Complete(u0 | f) = u0 (x) Y_f, u0 major, tag value 0
    b0 = [_place(c, 3, WORKSPACE) | _place(k, 4, F_WIRES)
          for c in u0 for k in range(16)]
    # block 1 : Complete({} | u1) = u1 alone, tag value 1
    tag = 1 << (AMBIENT - 1 - TAG_WIRE)
    b1 = [_place(c, 7, WORKSPACE + F_WIRES) | tag for c in u1]
    return tuple(b0), tuple(b1)


@pytest.mark.parametrize("materialize", MODES)
@pytest.mark.parametrize("side", ["ingress", "egress"])
def test_J22_parent_codes_match_an_independent_enumeration(side, materialize):
    """Built from the Part-I pins and the recorded injection, not from the
    production lifter."""
    pl = ctrl_ho_plan(materialize)
    assert pl.ambient_width == AMBIENT and pl.block_width == 8
    assert pl.tag_wires == (TAG_WIRE,)
    assert pl.workspace_wires == WORKSPACE
    assert pl.block_to_ambient == BLOCK_TO_AMBIENT
    want0, want1 = _expected(side)
    assert len(want0) == 64 and len(want1) == 16
    assert pl.tagged_codes(0, side) == want0, (
        f"{side}: block 0 codes do not match the independent enumeration")
    assert pl.tagged_codes(1, side) == want1, (
        f"{side}: block 1 codes do not match the independent enumeration")
    parent = (pl.ingress if side == "ingress" else pl.egress)
    assert parent.codes == want0 + want1
    assert parent.n_qubits == AMBIENT, (
        f"{side}: the chart lives in a {parent.n_qubits}-wire register, but "
        f"the occurrence's register is {AMBIENT}")
    assert len(parent.codes) == 80


@pytest.mark.parametrize("materialize", MODES)
def test_J23_ingress_and_egress_are_pinned_independently(materialize):
    pl = ctrl_ho_plan(materialize)
    assert _expected("ingress") != _expected("egress"), (
        "the two polarities must differ, or pinning them separately proves "
        "nothing")
    assert pl.ingress.codes != pl.egress.codes


@pytest.mark.parametrize("materialize", MODES)
def test_J24_block_width_is_not_the_register_width(materialize):
    """The Block spans 8 wires inside a 10-wire register. Conflating the two
    makes every chart code wrong by the difference."""
    pl = ctrl_ho_plan(materialize)
    assert pl.block_width == 8 and pl.ambient_width == 10
    assert pl.block_width != pl.ambient_width
    assert pl.spectators == (8, 9)
    assert set(pl.support) == set(range(8))
    assert pl.ingress.n_qubits == pl.ambient_width
    # a code placed as if the register were 8 wires would be a different number
    assert _place(1, 3, WORKSPACE, n=8) != _place(1, 3, WORKSPACE, n=10)


@pytest.mark.parametrize("materialize", MODES)
def test_J25_the_plan_records_each_branch_local_to_ambient_map(materialize):
    """Emission must not have to rebuild it from chart geometry."""
    pl = ctrl_ho_plan(materialize)
    blocks = {b.index: b for b in pl.branches}
    assert blocks[0].local_to_ambient == WORKSPACE
    assert blocks[1].local_to_ambient == WORKSPACE + F_WIRES
    for b in pl.branches:
        n_local = b.artifact.selected_boundary.ingress.n_qubits
        assert len(b.local_to_ambient) == n_local, (
            f"block {b.index}: the map names {len(b.local_to_ambient)} wires "
            f"for a {n_local}-wire branch register")
        assert len(set(b.local_to_ambient)) == len(b.local_to_ambient)


@pytest.mark.parametrize("materialize", MODES)
def test_J26_the_plan_is_the_authoritative_placement(materialize):
    """One object: the artifact's placement channel and the audit hook."""
    from test_nf1_beta_tensor import _fixture
    TP._USE_BLOCK_OBSERVED.clear()
    _, arts = TP.compile_with_artifacts(
        _fixture("ctrl_ho_closed_plus_map"), materialize=materialize)
    assert TP._USE_BLOCK_OBSERVED, "no plan was produced"
    pl = TP._USE_BLOCK_OBSERVED[-1]
    placed = [a.placement for a in arts if a.placement is not None]
    assert placed, "the occurrence records no placement at all"
    assert any(x is pl for x in placed), (
        "the audit hook and the artifact's placement are two objects")
    # The withdrawn uniform planner cannot coexist with the Block plan
    # because it no longer exists: every placement channel an occurrence has
    # is the OpenUseBlockPlan itself.
    assert all(isinstance(x, OpenUseBlockPlan) for x in placed), (
        f"an occurrence records a placement that is not its Block plan: "
        f"{[type(x).__name__ for x in placed]}")
    assert not hasattr(TP, "plan_open_occurrence"), (
        "the retired shadow planner is still reachable from the compiler")


@pytest.mark.parametrize("materialize", MODES)
def test_J27_the_plan_holds_the_prepared_artifacts_by_identity(materialize):
    from test_nf1_beta_tensor import _fixture
    made = []
    orig = TP._compile_branch_artifact

    def spy(branch, *, env=None, scope=None, **kw):
        a = orig(branch, env=env, scope=scope, **kw)
        made.append(a)
        return a

    TP._compile_branch_artifact = spy
    TP._USE_BLOCK_OBSERVED.clear()
    try:
        compile(_fixture("ctrl_ho_closed_plus_map"), materialize=materialize)
    finally:
        TP._compile_branch_artifact = orig
    pl = TP._USE_BLOCK_OBSERVED[-1]
    assert len(made) == 2
    for b in pl.branches:
        assert any(b.artifact is m for m in made)


@pytest.mark.parametrize("materialize", MODES)
def test_J28_no_selected_root_is_densified(materialize):
    """Each block's factor product is the selected root times its inactive
    completion -- never 2^k for the branch register."""
    from compile.frames import semantic_dim
    pl = ctrl_ho_plan(materialize)
    for b in pl.branches:
        sb = b.artifact.selected_boundary
        for side, ch in (("ingress", b.ingress), ("egress", b.egress)):
            root = (sb.ingress if side == "ingress" else sb.egress)
            inactive = 1
            for x in b.inactive:
                inactive *= semantic_dim(x.logical)
            assert ch.dim == root.dim * inactive, (
                f"block {b.index} {side}: {ch.dim} != root {root.dim} x "
                f"inactive {inactive}")
            assert ch.dim != (1 << len(b.local_to_ambient)) * inactive or \
                root.dim == (1 << root.n_qubits), (
                f"block {b.index} {side}: the selected root was densified to "
                f"its whole register")


# ===========================================================================
# 7. Inactive resources are carried as they are RECORDED, not densified
# ===========================================================================

def test_J29_a_sparse_inactive_binding_is_not_densified():
    """Plus(Q,I) is dimension THREE on two wires.

    Completing against it must multiply by 3, not by 2^2. Manufacturing
    range(1 << len(wires)) turns a recorded resource into a bigger one and
    the block dimension stops describing the derivation.
    """
    from lang.types import Plus as _Plus, Unit as _Unit
    amb = 4
    ch = _synthetic(1, amb)                       # branch root, dimension 2
    sc = ProvenanceScope()
    b = TypedBinding("z", _Plus(q, _Unit()), (0, 1), sc.owner(), sc.cut())
    blk = complete_branch(index=0, artifact=_FakeArt(ch), uses=(),
                          inactive=(b,), local_to_ambient=(3,),
                          tag_value=0, ambient_width=amb)
    assert blk.dim == 6, (
        f"completed dimension {blk.dim}; want 2 x 3 = 6, not 2 x 4 = 8 -- "
        f"the sparse inactive resource was densified")
    y = [f for f in blk.ingress.route.parts if f.name == "Y_z"]
    assert len(y) == 1
    assert y[0].codes == (0, 1, 2), (
        f"inactive codes {y[0].codes}; the recorded ordered encoding of "
        f"Plus(Q,I) is (0,1,2)")
    assert y[0].dim == 3 and y[0].n_qubits == 2
    assert y[0].logical == _Plus(q, _Unit())
    assert y[0].owner == b.owner_id


def test_J30_one_owner_named_twice_is_one_inactive_factor():
    """Duplicate references to a single owner complete ONCE; two distinct
    owners of the same type complete separately."""
    amb = 5
    ch = _synthetic(1, amb)
    sc = ProvenanceScope()
    own, cut = sc.owner(), sc.cut()
    b1 = TypedBinding("z", q, (0,), own, cut)
    b1_again = TypedBinding("z", q, (0,), own, cut)
    twice = complete_branch(index=0, artifact=_FakeArt(ch), uses=(),
                            inactive=(b1, b1_again), local_to_ambient=(4,),
                            tag_value=0, ambient_width=amb)
    assert twice.dim == 2 * 2, (
        f"one owner mentioned twice gave {twice.dim}; it is ONE resource")
    names = [f.name for f in twice.ingress.route.parts if f.name == "Y_z"]
    assert len(names) == 1

    b2 = TypedBinding("w", q, (1,), sc.owner(), sc.cut())
    distinct = complete_branch(index=0, artifact=_FakeArt(ch), uses=(),
                               inactive=(b1, b2), local_to_ambient=(4,),
                               tag_value=0, ambient_width=amb)
    assert distinct.dim == 2 * 2 * 2, (
        "two DISTINCT owners of the same type are two resources")
