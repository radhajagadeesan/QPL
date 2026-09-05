"""NF-1 Part Q: Complete and Block consume the per-polarity projections.

Milestone-2 gates. Complete consumes the active branch's own per-polarity
BranchMainProjection UNCHANGED -- same main alphabet, same labels -- and
appends each inactive resource exactly once, to the fibre only. Block's cut
face is DEFINED by the antecedent branch projections, tagged and
concatenated in summand order; the completed rows only validate
bidirectional coverage and can never define, shrink or reorder the
alphabet. First-appearance alphabet construction no longer exists, and the
binary and n-ary adapters share one module-level face rule.

The ctrl_ho pins are exact, in both modes.
"""

import dataclasses
import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(__file__))

from lang.types import Q, Ten
import compile.to_pytket as TP
from compile.to_pytket import compile, _issue_block_face
from compile.frames import (
    BranchRoleContext, ChartFactor, FactorSource, ProvenanceError,
    ProvenanceScope, RowProjection, SourcePortRef, TypedBinding,
    UnsupportedFrame, antecedent_main_alphabet, branch_cut_symbols,
    chart_of_frame, canonical_frame, complete_branch, complete_projection,
    gather_code, par_then_repart, project_branch_root, scatter_repart,
    semantic_action, leakage,
)
from test_nf1_partK_use_block_emission import (
    ctrl_ho_plan, emit_fresh, expected_blockdiag,
)

q = Q()
ATOL = 1e-10
MODES = [False, True]


def _main_wires(pl):
    return tuple(pl.tag_wires) + tuple(pl.workspace_wires)


# ===========================================================================
# the exact ctrl_ho pins, both modes
# ===========================================================================

@pytest.mark.parametrize("materialize", MODES)
def test_Q1_ctrl_ho_layout_and_dimensions(materialize):
    pl = ctrl_ho_plan(materialize)
    assert _main_wires(pl) == (4, 5, 6, 7)
    assert {b.index: b.dim for b in pl.branches} == {0: 64, 1: 16}
    assert pl.ingress.dim == pl.egress.dim == 64 + 16 == 80


@pytest.mark.parametrize("materialize", MODES)
def test_Q2_ctrl_ho_completed_branch_projections(materialize):
    """Branch 0: four main symbols, active fibre 1, inactive f multiplying
    the fibre by 16, on BOTH sides. Branch 1: eight symbols with fibre 2 at
    ingress and two symbols with fibre 8 at egress -- the polarity asymmetry
    that proves ingress and egress were constructed independently."""
    pl = ctrl_ho_plan(materialize)
    main = _main_wires(pl)
    b0, b1 = pl.branches

    assert b0.ingress_projection.alphabet == (0, 1, 2, 3)
    assert b0.egress_projection.alphabet == (0, 1, 2, 3)
    assert b0.ingress_projection.fibre_sizes == (16,) * 4
    assert b0.egress_projection.fibre_sizes == (16,) * 4
    # the four main symbols expressed on the cut coordinates
    assert branch_cut_symbols(b0.ingress_projection, pl.tag_bit(0), main,
                              pl.ambient_width) == (0, 2, 1, 3)
    assert branch_cut_symbols(b0.egress_projection, pl.tag_bit(0), main,
                              pl.ambient_width) == (0, 4, 1, 5)

    assert b1.ingress_projection.alphabet == (0, 1, 2, 3, 4, 5, 6, 7)
    assert b1.ingress_projection.fibre_sizes == (2,) * 8
    assert b1.egress_projection.alphabet == (0, 1)
    assert b1.egress_projection.fibre_sizes == (8, 8)
    # untagged, the egress alphabet sits at (0, 4) on the cut; tagged into
    # its sector it becomes (8, 12)
    assert branch_cut_symbols(b1.egress_projection, 0, main,
                              pl.ambient_width) == (0, 4)
    assert branch_cut_symbols(b1.ingress_projection, pl.tag_bit(1), main,
                              pl.ambient_width) == tuple(range(8, 16))
    assert branch_cut_symbols(b1.egress_projection, pl.tag_bit(1), main,
                              pl.ambient_width) == (8, 12)


@pytest.mark.parametrize("materialize", MODES)
def test_Q3_ctrl_ho_parent_alphabets(materialize):
    """The parent's cut alphabets are the tagged branch alphabets
    concatenated in summand order -- built antecedently, and equal to the
    faces the compile actually issued."""
    pl = ctrl_ho_plan(materialize)
    main = _main_wires(pl)
    want_in = (0, 2, 1, 3, 8, 9, 10, 11, 12, 13, 14, 15)
    want_out = (0, 4, 1, 5, 8, 12)
    assert antecedent_main_alphabet(pl, main, "ingress") == want_in
    assert antecedent_main_alphabet(pl, main, "egress") == want_out
    # ... and the artifact's recorded faces agree, fibres included
    from test_nf1_beta_tensor import _fixture
    from compile.to_pytket import compile_with_artifacts
    TP._USE_BLOCK_OBSERVED.clear()
    _r, arts = compile_with_artifacts(_fixture("ctrl_ho_closed_plus_map"),
                                      materialize=materialize)
    a = [x for x in arts if x.placement is not None][-1]
    assert a.ingress_face.alphabet == want_in
    assert a.egress_face.alphabet == want_out
    assert a.ingress_face.fibre_sizes == (16,) * 4 + (2,) * 8
    assert a.egress_face.fibre_sizes == (16,) * 4 + (8, 8)
    assert a.ingress_face.interface_wires == (4, 5, 6, 7)
    assert a.egress_face.interface_wires == (4, 5, 6, 7)


@pytest.mark.parametrize("materialize", MODES)
def test_Q4_ctrl_ho_exact_action_zero_leakage_zero_phase(materialize):
    pl = ctrl_ho_plan(materialize)
    c = emit_fresh(pl)
    U = c.get_unitary()
    W = semantic_action(pl.ingress, U, pl.egress)
    expected, _ = expected_blockdiag(pl)
    assert W.shape == (80, 80) == expected.shape
    np.testing.assert_allclose(W, expected, atol=ATOL, rtol=0.0)
    assert leakage(pl.ingress, U, pl.egress) < ATOL
    assert abs(float(c.phase)) < ATOL


@pytest.mark.parametrize("materialize", MODES)
def test_Q5_ctrl_ho_padding_is_preserved_not_promoted(materialize):
    """Branch 0's workspace carries one FIXED coordinate. The completed
    projection records it as padding, its bit stays fixed in every cut
    symbol, and the alphabet has exactly the branch's four symbols -- the
    padding never becomes semantic states."""
    pl = ctrl_ho_plan(materialize)
    b0 = pl.branches[0]
    for proj in (b0.ingress_projection, b0.egress_projection):
        assert len(proj.alphabet) == 4, (
            "a padded coordinate was promoted to semantic states")
        assert proj.padding, "the fixed coordinate is recorded as padding"
        for w, b in proj.padding:
            assert b == 0
    # ... and the promoted-alphabet mutation cannot even be constructed:
    # an alphabet that claims the padded coordinate varies has symbols with
    # no rows behind them.
    p = b0.ingress_projection
    padded_wire = p.padding[0][0]
    with pytest.raises(ProvenanceError) as ei:
        RowProjection(
            port=p.port, polarity=p.polarity,
            alphabet=tuple(range(2 * len(p.alphabet))),
            labels=tuple(gather_code(r, (padded_wire,) + p.label_wires,
                                     p.row_width) for r in p.rows),
            fibre_keys=p.fibre_keys, presenters=p.presenters,
            support=tuple(sorted(set(p.support) | {padded_wire})),
            rows=p.rows, padding=(),
            label_wires=(padded_wire,) + p.label_wires,
            fibre_wires=p.fibre_wires, row_width=p.row_width)
    assert "no rows" in str(ei.value)


# ===========================================================================
# Complete: unit gates on a small synthetic branch
# ===========================================================================

R_IN, R_OUT, R_FIB = "own:test.in", "own:test.out", "own:test.fib"


def _factor(fid, root, *, role="operand"):
    return ChartFactor(
        factor_id=fid, source=FactorSource((SourcePortRef(
            ref=f"ref:{fid}", origin_cut="cut:test", path=("test",),
            root=root),)),
        name=fid, owner=None, n_qubits=1, codes=(0, 1), role=role, logical=q)


def _chart(*factors_and_places, n=2):
    factors = tuple(f for f, _ in factors_and_places)
    places = tuple(pl for _, pl in factors_and_places)
    rep, pl = scatter_repart(places, n)
    return par_then_repart(factors, rep, n, "t", placements=pl,
                           kind="scatter")


def _branch_bits(pol, root):
    chart = _chart((_factor("s", root), (0,)), (_factor("y", R_FIB), (1,)))
    roles = BranchRoleContext(polarity=pol, payload=(root,), fibre=(R_FIB,),
                              branch_index=0)
    port = SourcePortRef(ref="cut:test", origin_cut="cut:test",
                        path=("branch", "0", pol), root=root)
    bp = project_branch_root(chart, roles, branch_index=0, polarity=pol,
                             port=port)
    return chart, bp


def _artifact(ch_in, ch_out):
    class _Sb:
        ingress = ch_in
        egress = ch_out

    class _Art:
        selected_boundary = _Sb
    return _Art


def _binding(wires=(2,)):
    sc = ProvenanceScope()
    return TypedBinding("z", q, tuple(wires), sc.owner(), sc.cut())


def test_Q6_complete_consumes_the_projection_unchanged():
    ch_in, bp_in = _branch_bits("ingress", R_IN)
    ch_out, bp_out = _branch_bits("egress", R_OUT)
    z = _binding()
    done = complete_branch(
        index=0, artifact=_artifact(ch_in, ch_out), uses=(), inactive=(z,),
        local_to_ambient=(0, 1), tag_value=0, ambient_width=3,
        projections={"ingress": bp_in, "egress": bp_out})
    for proj, bp in ((done.ingress_projection, bp_in),
                     (done.egress_projection, bp_out)):
        # the MAIN alphabet and every row's label are the branch's own
        assert proj.alphabet == bp.projection.alphabet
        m = len(z.codes)
        assert proj.labels == tuple(
            L for L in bp.projection.labels for _ in range(m))
        # the inactive resource extends the FIBRE only
        assert proj.label_wires == bp.projection.label_wires
        assert set(proj.fibre_wires) == set(bp.projection.fibre_wires) | \
            set(z.wires)
        assert proj.fibre_sizes == tuple(
            f * m for f in bp.projection.fibre_sizes)
    assert done.dim == 2 * 2 * 2


def test_Q6b_one_owner_is_appended_exactly_once():
    ch_in, bp_in = _branch_bits("ingress", R_IN)
    ch_out, bp_out = _branch_bits("egress", R_OUT)
    z = _binding()
    z_again = TypedBinding("z2", q, z.wires, z.owner_id, z.intro_cut)
    done = complete_branch(
        index=0, artifact=_artifact(ch_in, ch_out), uses=(),
        inactive=(z, z_again), local_to_ambient=(0, 1), tag_value=0,
        ambient_width=3,
        projections={"ingress": bp_in, "egress": bp_out})
    assert done.dim == 8, "one owner contributed twice to the completion"
    assert done.ingress_projection.fibre_sizes == (4, 4), (
        "the branch fibre of 2 times ONE inactive of dimension 2")


def test_Q7_swapped_polarities_are_refused():
    ch_in, bp_in = _branch_bits("ingress", R_IN)
    ch_out, bp_out = _branch_bits("egress", R_OUT)
    with pytest.raises(ProvenanceError) as ei:
        complete_branch(
            index=0, artifact=_artifact(ch_in, ch_out), uses=(),
            inactive=(_binding(),), local_to_ambient=(0, 1), tag_value=0,
            ambient_width=3,
            projections={"ingress": bp_out, "egress": bp_in})
    assert "must not be swapped" in str(ei.value)


def test_Q8_dropped_or_duplicated_inactive_is_refused():
    ch_in, bp_in = _branch_bits("ingress", R_IN)
    z = _binding()
    done = complete_branch(
        index=0, artifact=_artifact(ch_in, ch_in), uses=(), inactive=(z,),
        local_to_ambient=(0, 1), tag_value=0, ambient_width=3)
    # DROPPED: the completed chart carries z but the completion claims none
    with pytest.raises(ProvenanceError) as ei:
        complete_projection(bp_in, local_to_ambient=(0, 1), ambient_width=3,
                            inactive=(), completed_chart=done.ingress)
    assert "dropped or duplicated" in str(ei.value)
    # DUPLICATED: a second distinct owner the chart does not carry
    z2 = _binding(wires=(2,))
    with pytest.raises(ProvenanceError):
        complete_projection(bp_in, local_to_ambient=(0, 1), ambient_width=3,
                            inactive=(z, z2), completed_chart=done.ingress)


def test_Q9_a_route_less_completed_lift_transports_the_projection_port():
    """A branch root that defaulted to its Frame is completed by
    TRANSPORTING its preparation-issued projection port -- never by minting
    a fresh unlinked occurrence for it."""
    fr = canonical_frame(q, "u")
    ch = chart_of_frame(fr)
    assert ch.route is None
    port = SourcePortRef(ref="cut:test", origin_cut="cut:test",
                        path=("branch", "0", "ingress"), root=R_IN)
    proj = RowProjection(
        port=port, polarity="ingress", alphabet=tuple(ch.codes),
        labels=tuple(range(ch.dim)), fibre_keys=(0,) * ch.dim,
        presenters=("cut:test",), support=(0,), rows=tuple(ch.codes),
        padding=(), label_wires=(0,), fibre_wires=(), row_width=1)
    from compile.frames import BranchMainProjection
    bp = BranchMainProjection(
        branch_index=0, polarity="ingress", projection=proj,
        roles=BranchRoleContext(polarity="ingress", payload=(R_IN,),
                                fibre=(), branch_index=0))
    bp_out = BranchMainProjection(
        branch_index=0, polarity="egress",
        projection=dataclasses.replace(proj, polarity="egress"),
        roles=BranchRoleContext(polarity="egress", payload=(R_IN,),
                                fibre=(), branch_index=0))
    done = complete_branch(
        index=0, artifact=_artifact(ch, ch), uses=(), inactive=(),
        local_to_ambient=(0,), tag_value=0, ambient_width=2,
        projections={"ingress": bp, "egress": bp_out})
    for side in (done.ingress, done.egress):
        lifted = side.route.parts[0]
        assert lifted.source.sole is port, (
            "the lift minted a replacement occurrence instead of "
            "transporting the projection's own port")
        assert lifted.source.sole.reaches() == R_IN


# ===========================================================================
# Block face: the antecedent defines, rows validate, one shared rule
# ===========================================================================

def _face_call(materialize=False):
    """Capture the real arguments of one production face issuance."""
    calls = []
    real = TP._issue_block_face

    def spy(chart, plan, main_codes, main_in_block, main_wires, cut, pol):
        calls.append((chart, plan, main_codes, main_in_block, main_wires,
                      cut, pol))
        return real(chart, plan, main_codes, main_in_block, main_wires,
                    cut, pol)

    TP._issue_block_face = spy
    try:
        ctrl_ho_plan(materialize)
    finally:
        TP._issue_block_face = real
    assert calls, "no Block face was issued"
    return calls[0]


def test_Q10_missing_antecedent_main_codes_fails():
    chart, plan, main_codes, mib, mw, cut, pol = _face_call()
    assert main_codes is not None
    with pytest.raises(UnsupportedFrame) as ei:
        _issue_block_face(chart, plan, None, mib, mw, cut, pol)
    assert "no antecedent main interface" in str(ei.value)


def test_Q11_a_missing_branch_projection_fails():
    chart, plan, main_codes, mib, mw, cut, pol = _face_call()
    bare = dataclasses.replace(plan.branches[0], ingress_projection=None)
    broken = dataclasses.replace(plan, branches=(bare,) + plan.branches[1:])
    with pytest.raises(UnsupportedFrame) as ei:
        _issue_block_face(chart, broken, main_codes, mib, mw, cut, pol)
    assert "no completed ingress projection" in str(ei.value)


def test_Q12_a_swapped_face_projection_fails():
    chart, plan, main_codes, mib, mw, cut, pol = _face_call()
    assert pol == "ingress"
    b0 = plan.branches[0]
    swapped = dataclasses.replace(b0,
                                  ingress_projection=b0.egress_projection)
    broken = dataclasses.replace(plan, branches=(swapped,) + plan.branches[1:])
    with pytest.raises(UnsupportedFrame) as ei:
        _issue_block_face(chart, broken, main_codes, mib, mw, cut, pol)
    assert "must not be swapped" in str(ei.value)


def test_Q13_a_first_appearance_alphabet_is_refused():
    """The historic construction, replayed as a mutation: an alphabet taken
    from the row image over label AND fibre coordinates. Its symbols lie
    outside the cut, and the face refuses to absorb them."""
    chart, plan, main_codes, mib, mw, cut, pol = _face_call()
    b0 = plan.branches[0]
    p = b0.ingress_projection
    fw = p.fibre_wires
    assert fw, "the mutation needs a fibre coordinate to promote"
    lw = p.label_wires + fw[:1]
    subs = [gather_code(r, lw, p.row_width) for r in p.rows]
    alpha, pos = [], {}
    for x in subs:
        if x not in pos:
            pos[x] = len(alpha)
            alpha.append(x)
    first_appearance = RowProjection(
        port=p.port, polarity=p.polarity, alphabet=tuple(alpha),
        labels=tuple(pos[x] for x in subs),
        fibre_keys=tuple(gather_code(r, fw[1:], p.row_width)
                         for r in p.rows),
        presenters=p.presenters,
        support=p.support, rows=p.rows, padding=p.padding,
        label_wires=lw, fibre_wires=fw[1:], row_width=p.row_width)
    mutated = dataclasses.replace(b0, ingress_projection=first_appearance)
    broken = dataclasses.replace(plan, branches=(mutated,) + plan.branches[1:])
    with pytest.raises((UnsupportedFrame, ProvenanceError)) as ei:
        _issue_block_face(chart, broken, main_codes, mib, mw, cut, pol)
    assert "outside the main coordinates" in str(ei.value)


def test_Q14_a_shrunken_alphabet_is_refused():
    """Collapse a branch's alphabet to one symbol by moving its label
    coordinates into the fibre. The projection itself is consistent, but the
    Block's rows then present symbols the projection never issued -- and the
    rows must CONFIRM the alphabet, never redefine it."""
    chart, plan, main_codes, mib, mw, cut, pol = _face_call()
    b0 = plan.branches[0]
    p = b0.ingress_projection
    shrunk = RowProjection(
        port=p.port, polarity=p.polarity, alphabet=(0,),
        labels=(0,) * len(p.rows),
        fibre_keys=tuple(gather_code(r, p.label_wires + p.fibre_wires,
                                     p.row_width) for r in p.rows),
        presenters=p.presenters, support=p.support, rows=p.rows,
        padding=p.padding, label_wires=(),
        fibre_wires=p.label_wires + p.fibre_wires, row_width=p.row_width)
    mutated = dataclasses.replace(b0, ingress_projection=shrunk)
    broken = dataclasses.replace(plan, branches=(mutated,) + plan.branches[1:])
    with pytest.raises(UnsupportedFrame) as ei:
        _issue_block_face(chart, broken, main_codes, mib, mw, cut, pol)
    assert "never redefine" in str(ei.value)


def test_Q15_binary_and_nary_adapters_share_one_face_rule():
    """Both open-sum adapters route through THE one module-level
    `_issue_block_face`. A sentinel planted there interrupts both."""
    import test_n_plusmap_open as NPO
    from test_nf1_beta_tensor import _fixture

    class _Sentinel(Exception):
        pass

    def bomb(*a, **k):
        raise _Sentinel()

    real = TP._issue_block_face
    TP._issue_block_face = bomb
    try:
        with pytest.raises(_Sentinel):
            compile(_fixture("ctrl_ho_closed_plus_map"))     # binary PlusMap
        with pytest.raises(_Sentinel):
            compile(NPO._abstract_three_branch())            # n-ary NPlusMap
    finally:
        TP._issue_block_face = real
