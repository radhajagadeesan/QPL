"""NF-1 Part G: open/context provenance. RED TABLE ONLY -- no production change.

This is a CORRECTNESS repair, not a limitation exercise. The acceptance
condition is successful, exact compilation of valid open and coherently shared
contexts. Failing closed is acceptable only for genuinely invalid placements or
missing bindings.

The question: can an open PlusMap/NPlusMap retain, FROM THE DERIVATION,

  1. the branch artifact's local ingress and egress frames;
  2. its occurrence-selected placement in the ambient register;
  3. every live context/residual cell's logical type, binder owner, and cut
     lineage;

without reconstructing any of it from `type_of`, free-variable widths, names,
fixed/varying bit patterns, canonical frames, or physical-wire identity.

COMPLETED-CUT EQUATIONS. For every decisive open branch,

    A_pre  J_i^- = K_i^-
    B_i    K_i^- = K_i^+ G_i
    A_post K_i^+ = J_i^+

J is the derivation-selected parent sector; K is the local branch artifact
PLACED at this occurrence. Context coordinates participate through their
recorded ports -- checking bare main-frame codes only is insufficient, which is
precisely why a bare-code check would pass today while the artifact is untruthful.

WHAT THIS MODULE IS. Desired-state tests, red today. Nothing is implemented.
No test here weakens an existing guard, and none is an xfail or a skip.
"""

import json
import os
import sys

import numpy as np
import pytest

from lang.types import Q, Unit, Ten, Plus, Arrow
from lang.terms import Id, Seq, TenTerm, TwistTen, PlusMap, NPlusMap, Var, H as Hg
from pytket import Circuit
from compile.to_pytket import compile, compile_with_artifacts, select_frames
from compile.frames import (OpenUseBlockPlan,
                            Frame, Port, semantic_action, leakage, pretty,
                            UnsupportedFrame, ProvenanceScope,
                            completed_dimension, ProvenanceError,
                            OccurrencePlacement, SidePlacement,
                            apply_wire_perm, with_spectators, tensor_frame)

q = Q()
I = Unit()
MODES = [False, True]
ATOL = 1e-10

FIX = os.path.join(os.path.dirname(__file__), "fixtures")

# One scope per test module run: ids are scope-local, never module-global.
SC = ProvenanceScope()


def _fixture(name):
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..",
                                    "ocaml"))
    from bridge import parse_term
    with open(os.path.join(FIX, name + ".json")) as f:
        return parse_term(json.load(f))


# ===========================================================================
# A. Data-model gates      classification: MISSING DATA MODEL
# ===========================================================================

def test_A1_frame_exposes_completed_dimension():
    assert hasattr(Frame, "completed_dimension"), (
        "Frame has no completed_dimension; the completed cut cannot be "
        "balanced without it")


def test_A2_port_carries_owner_and_cut_identity():
    fields = set(Port.__dataclass_fields__)
    assert "owner_id" in fields, "Port has no owner_id (binder ownership)"
    assert "cut_id" in fields, "Port has no cut_id (cut lineage)"


def test_A3_port_json_round_trip_preserves_provenance():
    p = Port("f", Arrow(q, q), (3, 4), role="context",
             owner_id=SC.owner(), cut_id=SC.cut())
    j = p.to_json()
    back = Port.from_json(j)
    assert back.name == p.name and back.role == p.role
    assert back.wires == p.wires
    assert back.logical == p.logical
    assert back.by_sector == p.by_sector
    assert j.get("owner_id") is not None, "owner_id is not serialized"
    assert j.get("cut_id") is not None, "cut_id is not serialized"
    assert back.owner_id == p.owner_id and back.cut_id == p.cut_id


def test_A4_two_equal_typed_binders_get_distinct_owners():
    """Same type, same name even -- ownership is MINTED, not derived.

    Non-vacuous: the ids come from the API, not from constants written here,
    so a type- or name-derived implementation would collide.
    """
    a = Port("f", Arrow(q, q), (0,), role="context",
             owner_id=SC.owner(), cut_id=SC.cut())
    b = Port("f", Arrow(q, q), (1,), role="context",
             owner_id=SC.owner(), cut_id=SC.cut())
    assert a.owner_id and b.owner_id
    assert a.owner_id != b.owner_id, "equal-typed binders share an owner_id"
    assert a.cut_id != b.cut_id


def test_A5_two_occurrences_of_one_AST_object_get_distinct_cuts():
    """Repeated use of ONE AST object must not collapse cut identity."""
    shared = Hg(0, q)
    t = TenTerm(shared, shared)
    _, arts = compile_with_artifacts(t)
    cuts = [a.cut_id for a in arts if a.term is shared]
    assert len(cuts) == 2, f"expected two occurrences, got {len(cuts)}"
    assert all(c is not None for c in cuts), "occurrences carry no cut_id"
    assert cuts[0] != cuts[1], "two occurrences collapsed to one cut lineage"


def test_A6_completed_dimension_counts_context_once_and_ignores_spectators():
    own, cut = SC.owner(), SC.cut()
    ctx = Port("f", Arrow(q, q), (2, 3), role="context",
               owner_id=own, cut_id=cut)
    spec = Port("pad", Unit(), (4,), role="residual")
    f = Frame(logical=Plus(q, q), n_qubits=5, codes=(0, 1, 2, 3),
              ports=(ctx, spec))
    assert f.completed_dimension == 4 * 4, (
        "completed_dimension must count each unconditional typed context "
        "exactly once (f:Q-oQ contributes 4) and ignore true spectators")

    # one binder mentioned twice is ONE resource
    again = Frame(logical=Plus(q, q), n_qubits=5, codes=(0, 1, 2, 3),
                  ports=(ctx, Port("f", Arrow(q, q), (2, 3), role="context",
                                   owner_id=own, cut_id=cut), spec))
    assert again.completed_dimension == 16, "one owner counted twice"

    # two DISTINCT owners are two resources
    two = Frame(logical=Plus(q, q), n_qubits=5, codes=(0, 1, 2, 3),
                ports=(ctx, Port("g", Arrow(q, q), (0, 1), role="context",
                                 owner_id=SC.owner(),
                                 cut_id=SC.cut())))
    assert two.completed_dimension == 4 * 4 * 4


def test_A7_completed_dimension_refuses_to_guess():
    """Missing provenance and sector-conditioned context both RAISE."""
    noprov = Frame(logical=q, n_qubits=3, codes=(0, 1),
                   ports=(Port("f", Arrow(q, q), (2,), role="context"),))
    with pytest.raises(ProvenanceError) as ei:
        noprov.completed_dimension
    assert "owner_id" in str(ei.value) or "cut_id" in str(ei.value)

    cond = Frame(logical=q, n_qubits=3, codes=(0, 1),
                 ports=(Port("f", Arrow(q, q), (), role="context",
                             by_sector=((0, (2,)), (1, (2,))),
                             owner_id=SC.owner(), cut_id=SC.cut()),))
    with pytest.raises(ProvenanceError) as ei2:
        cond.completed_dimension
    assert "sector-conditioned" in str(ei2.value)


def test_A8_placement_represents_both_sides_independently():
    cin, cout = SC.cut(), SC.cut()
    ing = SidePlacement(cut_id=cin, ambient_width=5, local_to_ambient=(1, 2),
                        tag_wires=(1,), payload_wires=(2,),
                        ports=(Port("f", Arrow(q, q), (3,), role="context",
                                    owner_id=SC.owner(), cut_id=cin),))
    egr = SidePlacement(cut_id=cout, ambient_width=5, local_to_ambient=(0, 2),
                        tag_wires=(0,), payload_wires=(2,),
                        ports=(Port("f", Arrow(q, q), (4,), role="context",
                                    owner_id=SC.owner(), cut_id=cout),))
    op = OccurrencePlacement(ingress=ing, egress=egr)
    assert op.ambient_width == 5
    assert op.ingress.cut_id != op.egress.cut_id
    assert op.ingress.local_to_ambient != op.egress.local_to_ambient
    assert op.ingress.ports[0].wires != op.egress.ports[0].wires
    assert op.ingress.ambient(0) == 1 and op.egress.ambient(0) == 0

    with pytest.raises(ProvenanceError):        # non-injective injection
        SidePlacement(cut_id=cin, ambient_width=4, local_to_ambient=(1, 1))
    with pytest.raises(ProvenanceError):        # out of range
        SidePlacement(cut_id=cin, ambient_width=2, local_to_ambient=(0, 5))
    with pytest.raises(ProvenanceError):        # tag/main overlap
        SidePlacement(cut_id=cin, ambient_width=3, tag_wires=(0,),
                      main_wires=(0,))
    with pytest.raises(ProvenanceError):        # live port with no provenance
        SidePlacement(cut_id=cin, ambient_width=4,
                      ports=(Port("f", Arrow(q, q), (2,), role="context"),))
    with pytest.raises(ProvenanceError):        # port from the other side
        SidePlacement(cut_id=cin, ambient_width=4,
                      ports=(Port("f", Arrow(q, q), (2,), role="context",
                                  owner_id=SC.owner(), cut_id=cout),))
    with pytest.raises(ProvenanceError):        # widths disagree
        OccurrencePlacement(ingress=ing,
                            egress=SidePlacement(cut_id=cout, ambient_width=4))


def test_A9_main_placement_can_be_selected_AROUND_an_owned_context():
    """The B case, at the data model: z owns wire 0, so tag/payload go
    elsewhere. Representing this -- not merely detecting the old collision --
    is what the next stage needs."""
    cut = SC.cut()
    z = Port("z", q, (0,), role="context", owner_id=SC.owner(), cut_id=cut)
    side = SidePlacement(cut_id=cut, ambient_width=3, local_to_ambient=(1, 2),
                         tag_wires=(1,), payload_wires=(2,), ports=(z,))
    assert side.ports[0].wires == (0,)
    assert side.tag_wires == (1,) and side.payload_wires == (2,)
    with pytest.raises(ProvenanceError) as ei:
        SidePlacement(cut_id=cut, ambient_width=3, local_to_ambient=(0, 1),
                      tag_wires=(0,), payload_wires=(1,), ports=(z,))
    assert "collides" in str(ei.value)


def test_A10_provenance_is_compile_scoped_and_forkable():
    """Not module-global: identities depend only on the traversal."""
    root = ProvenanceScope()
    a, b = root.fork(), root.fork()
    assert a.owner() != b.owner(), "sibling subcompiles minted one owner"
    assert a.cut() != b.cut(), "sibling subcompiles minted one cut"
    again = ProvenanceScope()
    x, y = again.fork(), again.fork()
    assert (a.path, b.path) == (x.path, y.path), "scopes are not reproducible"
    s1 = ProvenanceScope()
    assert s1.owner() != s1.owner(), "two mints in one scope collided"


def test_A11_compiling_the_same_derivation_twice_is_reproducible():
    shared = Hg(0, q)
    t = TenTerm(shared, shared)
    a = [x.cut_id for x in compile_with_artifacts(t)[1]]
    b = [x.cut_id for x in compile_with_artifacts(t)[1]]
    assert a == b, f"serialized provenance drifted between runs: {a} vs {b}"
    assert len(set(a)) == len(a), "occurrences collapsed"


# --- provenance TRANSPORT: every helper that rebuilds a Port ---------------

def _sentinel_port(name="f", wires=(1,)):
    return Port(name, Arrow(q, q), wires, role="context",
                owner_id="OWN-SENTINEL", cut_id="CUT-SENTINEL",
                origin_cut="ORIGIN-SENTINEL")


def _assert_survives(ports, where):
    assert ports, f"{where}: the port vanished"
    for p in ports:
        assert p.owner_id == "OWN-SENTINEL", f"{where}: owner_id dropped"
        assert p.cut_id == "CUT-SENTINEL", f"{where}: cut_id dropped"
        assert p.origin_cut == "ORIGIN-SENTINEL", (
            f"{where}: origin_cut dropped -- lineage cannot be reconstructed")


def test_A17_recut_changes_only_the_current_cut():
    """origin_cut is never laundered from whatever cut the port sat on."""
    p = _sentinel_port()
    r = p.recut("CUT-PARENT")
    assert r.cut_id == "CUT-PARENT"
    assert r.origin_cut == "ORIGIN-SENTINEL", "origin was rewritten"
    bare = Port("h", Arrow(q, q), (0,), role="residual",
                owner_id="o", cut_id="cut:wherever")
    assert bare.recut("cut:other").origin_cut is None, (
        "an absent origin was laundered from the current cut")


def test_A18_live_port_without_origin_fails_and_spectators_do_not():
    from lang.types import Unit as U
    live = Port("h", Arrow(q, q), (0,), role="residual", owner_id="o",
                cut_id="c")
    with pytest.raises(ProvenanceError) as ei:
        live.require_origin("test")
    assert "origin_cut" in str(ei.value)
    assert Port("pad", U(), (2,), role="residual").require_origin() is None


def test_A19_EMPTY_SELECTION_is_only_legal_for_a_closed_occurrence():
    from compile.frames import EMPTY_SELECTION
    from lang.terms import Var as V
    assert select_frames(Id(q), ctx=EMPTY_SELECTION)
    with pytest.raises(ProvenanceError) as ei:
        select_frames(V("z", q), ctx=EMPTY_SELECTION)
    msg = str(ei.value)
    assert "OPEN term" in msg and "z" in msg


def test_A12_provenance_survives_json_round_trip():
    p = _sentinel_port()
    _assert_survives((Port.from_json(p.to_json()),), "to_json/from_json")


def test_A13_provenance_survives_apply_wire_perm():
    f = Frame(logical=q, n_qubits=2, codes=(0, 1), ports=(_sentinel_port(),))
    _assert_survives(apply_wire_perm(f, [1, 0]).ports, "apply_wire_perm")


def test_A14_provenance_survives_with_spectators():
    f = Frame(logical=q, n_qubits=2, codes=(0, 1), ports=(_sentinel_port(),))
    out = with_spectators(f, 4)
    _assert_survives([p for p in out.ports if p.name == "f"],
                     "with_spectators")


def test_A15_provenance_survives_tensor_frame():
    a = Frame(logical=q, n_qubits=2, codes=(0, 1), ports=(_sentinel_port(),))
    b = Frame(logical=q, n_qubits=2, codes=(0, 1),
              ports=(_sentinel_port("g", (0,)),))
    out = tensor_frame(a, b)
    _assert_survives([p for p in out.ports if p.name.endswith(".f")],
                     "tensor_frame left")
    _assert_survives([p for p in out.ports if p.name.endswith(".g")],
                     "tensor_frame right")


def test_A16_provenance_survives_lift_port():
    from compile.to_pytket import _lift_port
    _assert_survives((_lift_port(_sentinel_port(wires=(0,)), (2, 3)),),
                     "_lift_port")


# ===========================================================================
# B. Direct bound-open NPlusMap    classification: LOCAL-TO-OCCURRENCE PLACEMENT
# ===========================================================================

def B_witness():
    return NPlusMap((q, q), (Var("z", q), Hg(0, q)))


@pytest.mark.parametrize("wire", [0, 1, 2])
@pytest.mark.parametrize("materialize", MODES)
def test_B1_bound_open_nplusmap_compiles_without_a_backend_error(wire, materialize):
    """z at wire 0 or 1 currently raises a raw pytket RuntimeError.

    The main sum placement must be SELECTED AROUND the owned context rather
    than blindly claiming the same coordinate. z at wire 0 is a valid binding,
    not an invalid placement, so failing closed is not the right answer here.
    """
    try:
        compile(B_witness(), env={"z": [wire]}, materialize=materialize)
    except RuntimeError as e:
        pytest.fail(f"raw backend error for a valid binding z@{wire}: {e}")
    except UnsupportedFrame as e:
        pytest.fail(f"valid binding z@{wire} rejected: {e}")


@pytest.mark.parametrize("wire", [0, 1, 2])
def test_B2_exactly_one_unconditional_typed_z_context_port(wire):
    r = compile(B_witness(), env={"z": [wire]}, materialize=False)
    ctx = [p for p in r.input_frame.ports if p.role == "context"]
    assert len(ctx) == 1, (
        f"expected one typed context port, got "
        f"{[(p.name, p.role, p.logical) for p in r.input_frame.ports]}")
    p = ctx[0]
    assert p.logical == q, f"context port type is {pretty(p.logical)}, not Q"
    assert p.by_sector == (), "coherently shared context was copied per sector"
    assert getattr(p, "owner_id", None) is not None
    assert getattr(p, "cut_id", None) is not None


@pytest.mark.parametrize("wire", [0, 1, 2])
def test_B3_no_live_resource_is_an_untyped_spectator(wire):
    """Today z survives as ('fn_layout', 'residual') -- an untyped generic
    cell standing in for a live typed resource."""
    r = compile(B_witness(), env={"z": [wire]}, materialize=False)
    bad = [p for p in r.input_frame.ports
           if p.name in ("fn_layout", "ancilla") or p.logical == Unit()]
    assert not bad, (
        f"live resources represented as untyped spectators: "
        f"{[(p.name, p.role, p.wires) for p in bad]}")


@pytest.mark.parametrize("wire", [0, 1, 2])
def test_B4_tag_payload_and_context_are_disjoint(wire):
    r = compile(B_witness(), env={"z": [wire]}, materialize=False)
    groups = {}
    for p in r.input_frame.ports:
        groups.setdefault(p.role, []).extend(p.wires)
    seen = set()
    for role, ws in groups.items():
        assert len(set(ws)) == len(ws), f"{role} placement is not injective"
        assert not (seen & set(ws)), f"{role} overlaps another role at this cut"
        seen |= set(ws)


@pytest.mark.parametrize("wire", [0, 1, 2])
def test_B5_no_context_driven_double_widening(wire):
    """One context cell of width 1 must not grow the register twice."""
    r = compile(B_witness(), env={"z": [wire]}, materialize=False)
    assert r.circuit.n_qubits <= 3, (
        f"register widened to {r.circuit.n_qubits} for a 2-qubit sum plus one "
        f"context wire")


@pytest.mark.parametrize("wire", [0, 1, 2])
def test_B6_branch_artifact_frames_stay_local(wire):
    """BranchArtifact frames must not be widened with with_spectators; ambient
    context belongs to the occurrence placement."""
    import compile.to_pytket as TP
    seen = []
    orig = TP._compile_branch_artifact

    def spy(br, *, env=None, **kw):
        a = orig(br, env=env, **kw)
        seen.append((type(br).__name__, a.fin.n_qubits, a.fout.n_qubits))
        return a

    TP._compile_branch_artifact = spy
    try:
        compile(B_witness(), env={"z": [wire]}, materialize=False)
    except Exception:
        pass
    finally:
        TP._compile_branch_artifact = orig
    assert seen, "no branch artifact was produced"
    for name, ni, no in seen:
        assert ni <= 1 and no <= 1, (
            f"{name} artifact frame widened to {ni}/{no} qubits; ambient "
            f"context leaked into the branch-local frame")


# ===========================================================================
# D. Organic ctrl_ho              classification: DERIVATION SELECTION
# ===========================================================================

def D_term():
    return _fixture("ctrl_ho_closed_plus_map")


@pytest.mark.parametrize("materialize", MODES)
def test_D1_ctrl_ho_compiles(materialize):
    """The current F1 rejection is containment, not the final behavior.

    Today: UnsupportedFrame -- 'physical wire 0 is claimed by both the tag
    placement [0] and the context placement [0,1,2,3]'. Same seam as B: the
    main placement is not selected around the owned context.
    """
    compile(D_term(), materialize=materialize)


def test_D2_internal_plusmap_occurrence_is_exposed():
    _, arts = compile_with_artifacts(D_term())
    pms = [a for a in arts if isinstance(a.term, (PlusMap, NPlusMap))]
    assert pms, "no internal PlusMap/NPlusMap occurrence is exposed"


def test_D3_block_dimensions_are_64_and_16_with_parent_80():
    """SUPERSEDES the uniform 256/256 model.

    That model completed the whole occurrence against one context factor:
    ingress (8+8) x 16_f = 256, egress (2+2) x 16_f x 4_h = 256, where the
    "4_h" was a residual that does not exist -- h is the S_h operand factor
    inside the right branch's own selected root. The completion is per block,
    against the context each branch does NOT use.
    """
    _, arts = compile_with_artifacts(D_term())
    pms = [a for a in arts if isinstance(a.placement, OpenUseBlockPlan)]
    assert pms, "no sum occurrence carries a use-block plan"
    pl = pms[0].placement
    dims = {b.index: b.dim for b in pl.branches}
    assert dims == {0: 64, 1: 16}, f"block dims {dims}, want 64 and 16"
    assert pl.ingress.dim == 80 and pl.egress.dim == 80
    assert pl.ingress.dim not in (256, 320)
    assert sum(dims.values()) == 80


def test_D4_ambient_support_and_spectators():
    """Read from the PLAN, not from Frame ports.

    The Block spans 8 wires inside the occurrence's real 10-wire register.
    """
    _, arts = compile_with_artifacts(D_term())
    pl = [a.placement for a in arts
          if isinstance(a.placement, OpenUseBlockPlan)][0]
    assert pl.ambient_width == 10, f"register width {pl.ambient_width}"
    assert pl.block_width == 8, f"block width {pl.block_width}"
    assert pl.support == tuple(range(8)), f"support {pl.support}"
    assert pl.spectators == (8, 9), f"spectators {pl.spectators}"
    assert pl.tag_wires == (4,)
    assert pl.workspace_wires == (5, 6, 7)


def test_D5_f_completes_one_block_and_h_stays_inside_the_other():
    """SUPERSEDES the fabricated h-port expectation.

    f occurs ONCE, as a typed inactive completion of the block that does not
    use it, and that same owner is in the other block's use set. h is never a
    completion port: it is the typed, provenanced operand factor inside the
    right block's own selected root.
    """
    _, arts = compile_with_artifacts(D_term())
    pl = [a.placement for a in arts
          if isinstance(a.placement, OpenUseBlockPlan)][0]
    blocks = {b.index: b for b in pl.branches}

    inactive = [x for x in blocks[0].inactive]
    assert len(inactive) == 1 and isinstance(inactive[0].logical, Arrow), (
        f"block 0 must be completed against exactly one typed f, got "
        f"{[(x.name, x.logical) for x in inactive]}")
    f_owner = inactive[0].owner_id
    assert f_owner is not None
    assert blocks[1].uses == (f_owner,), (
        f"the owner completing block 0 must be the one block 1 uses; got "
        f"{blocks[1].uses}")
    assert blocks[1].inactive == (), "f must not complete both blocks"

    ys = [f for f in blocks[0].ingress.route.parts if f.role == "residual"
          and isinstance(f.logical, Arrow)]
    assert len(ys) == 1 and ys[0].owner == f_owner

    endo = Arrow(q, q)
    s_h = [f for f in blocks[1].ingress.route.parts
           if f.role == "operand" and f.logical == endo]
    assert len(s_h) == 1, (
        f"h must be a typed operand factor inside the right block's root; "
        f"factors are "
        f"{[(x.name, x.role, x.logical, x.dim) for x in blocks[1].ingress.route.parts]}")
    assert s_h[0].owner is not None
    for b in pl.branches:
        for side in (b.ingress, b.egress):
            for f in side.route.parts:
                assert f.name not in ("h", "Y_h"), (
                    f"an h completion port was invented: {f.name}")


# ===========================================================================
# E. Negatives and anti-vacuity
# ===========================================================================

def test_E1_unresolved_free_var_on_the_PlusMap_path_fails_closed():
    """NPlusMap already fails closed here; the PlusMap open path does not --
    it compiles silently with no context port at all."""
    t = PlusMap(q, q, Var("z", q), Hg(0, q))
    with pytest.raises(UnsupportedFrame) as ei:
        compile(t)
    assert "unresolved" in str(ei.value).lower(), str(ei.value)


def test_E2_contradictory_ownership_overlap_is_rejected():
    """Two DISTINCT owners claiming one coordinate is invalid.

    Deliberately NOT the valid z-at-wire-0 case, which must SUCCEED -- a
    binding that happens to sit on wire 0 is not a contradiction, it is a
    placement the occurrence must be selected around.
    """
    cut = SC.cut()
    a = Port("f", Arrow(q, q), (2,), role="context",
             owner_id=SC.owner(), cut_id=cut)
    b = Port("g", Arrow(q, q), (2,), role="context",
             owner_id=SC.owner(), cut_id=cut)
    with pytest.raises(ProvenanceError) as ei:
        SidePlacement(cut_id=cut, ambient_width=3, local_to_ambient=(0, 1),
                      ports=(a, b))
    assert "two distinct owner/cut pairs" in str(ei.value)


def test_E3_unbalanced_completed_dimensions_are_visible():
    """An unbalanced cut must be DETECTABLE, which is what G1 supplies."""
    fin = Frame(logical=q, n_qubits=2, codes=(0, 1),
                ports=(Port("f", Arrow(q, q), (1,), role="context",
                            owner_id=SC.owner(),
                            cut_id=SC.cut()),))
    fout = Frame(logical=q, n_qubits=2, codes=(0, 1))
    assert fin.completed_dimension == 2 * 4
    assert fout.completed_dimension == 2
    assert fin.completed_dimension != fout.completed_dimension


def test_E4_local_branch_frames_are_offset_independent():
    """The same branch at offset 0 and at a nonzero offset must yield
    IDENTICAL local artifact frames."""
    import compile.to_pytket as TP
    br = Hg(0, q)
    a = TP._compile_branch_artifact(br)
    seen = []
    orig = TP._compile_branch_artifact

    def spy(b2, *, env=None, **kw):
        r = orig(b2, env=env, **kw)
        seen.append((tuple(r.fin.codes), tuple(r.fout.codes), r.fin.n_qubits))
        return r

    TP._compile_branch_artifact = spy
    try:
        compile(TenTerm(Id(q), PlusMap(q, q, br, Id(q))), materialize=False)
    finally:
        TP._compile_branch_artifact = orig
    assert seen, "no artifact produced at the nonzero offset"
    assert (tuple(a.fin.codes), tuple(a.fout.codes), a.fin.n_qubits) in seen, (
        f"branch frames differ by offset: standalone "
        f"{tuple(a.fin.codes)}/{tuple(a.fout.codes)} vs placed {seen}")


def test_E5_at_least_one_witness_has_a_command_bearing_branch():
    """Anti-vacuity: a table of gate-free branches proves nothing about
    emission."""
    import compile.to_pytket as TP
    a = TP._compile_branch_artifact(Hg(0, q))
    assert len(a.cmds) >= 1, "the H branch emits no commands"


def test_E6_python_serialization_exposes_nested_occurrence_frames():
    """RENAMED HONESTLY. This exercises the PYTHON nested-artifact
    serialization path, not the OCaml bridge. Nothing here shows that the
    bridge was fixed, and the earlier name claimed it did.

    The OCaml bridge must round-trip nested artifact frames, not only the
    root. Recorded as its own red: a Python-only round-trip is not a
    substitute."""
    t = D_term()
    _, arts = compile_with_artifacts(t)
    nested = [a for a in arts if a.occurrence != 0]
    assert nested, "no nested occurrences produced"
    assert all(hasattr(a.input_frame, "to_json") for a in nested)
    payloads = [a.input_frame.to_json() for a in nested]
    assert all("ports" in p for p in payloads), (
        "nested occurrence frames do not serialize their ports")


# ===========================================================================
# G2b: the LIVE open-occurrence placement -- ONE authority.
#
# The shared shadow planner is gone. Open PlusMap and open NPlusMap both
# select their coordinates through `use_block_layout` and both emit from the
# `OpenUseBlockPlan` built on top of it, so there is no second algorithm that
# could agree with the compiler by accident. Every pin below therefore drives
# the real compiler, or the live layout/plan the compiler itself calls, and
# reads the plan object the emission actually consumed.
#
# The B witness is the decisive case: its completed blocks are 4 and 4 and its
# parent is their direct sum, 8.
# ===========================================================================

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))            # noqa
from dataclasses import replace as _replace                              # noqa
from compile.frames import (TypedBinding, canonical_frame,               # noqa
                            BoundaryChart, use_block_layout,             # noqa
                            complete_branch, plan_use_block,             # noqa
                            CompletedBranch, BranchParameter,            # noqa
                            classify_factorization, check_context_ports, # noqa
                            FACTORIZED, BLOCK_ONLY)                      # noqa
import compile.to_pytket as TP                                            # noqa


def _live(wire=2, materialize=False, term=None, env=None):
    """Drive the REAL compiler; hand back what it actually emitted."""
    TP._USE_BLOCK_OBSERVED.clear()
    res, arts = compile_with_artifacts(
        term if term is not None else B_witness(),
        env=env if env is not None else {"z": [wire]},
        materialize=materialize)
    assert TP._USE_BLOCK_OBSERVED, (
        "the compiler never reached the use-block planner")
    return res, arts, TP._USE_BLOCK_OBSERVED[-1]


def _ctx_ports(frame):
    return [p for p in frame.ports if p.role == "context"]


# --- the external oracle, built from the primitive branch actions ----------
# Assembled from the two branch morphisms and the explicit sector inclusions,
# with no reference to the plan-building helpers under test. Semantic index
# is (tag, payload, z) in every placement, because that is the order the
# parent chart enumerates.
def _B_oracle():
    Hm = np.array([[1, 1], [1, -1]], dtype=complex) / np.sqrt(2)
    O = np.zeros((8, 8), dtype=complex)
    for pay in (0, 1):
        for z in (0, 1):
            O[0 * 4 + z * 2 + pay, 0 * 4 + pay * 2 + z] = 1.0
            for out in (0, 1):
                O[1 * 4 + out * 2 + z, 1 * 4 + pay * 2 + z] = Hm[out, pay]
    return O


@pytest.mark.parametrize("wire,ctx,tag,pay", [
    (0, (0,), (1,), (2,)),
    (1, (1,), (0,), (2,)),
    (2, (2,), (0,), (1,)),
])
def test_G2b_placement_pins(wire, ctx, tag, pay):
    """Owned context preserved; tag then workspace take the remaining wires in
    ascending order. Now read off the LIVE plan and the successful artifact."""
    res, _arts, pl = _live(wire)
    assert pl.tag_wires == tag, f"tag {pl.tag_wires} != {tag}"
    assert pl.workspace_wires == pay, f"workspace {pl.workspace_wires} != {pay}"
    assert pl.ambient_width == 3 and pl.spectators == ()
    assert {b.index: b.dim for b in pl.branches} == {0: 4, 1: 4}
    assert pl.ingress.dim == 8 and pl.egress.dim == 8
    assert sum(b.dim for b in pl.branches) == pl.ingress.dim, (
        "the parent is the DIRECT SUM of its blocks")
    # Both polarities, independently.
    for label, frame in (("ingress", res.input_frame),
                         ("egress", res.output_frame)):
        ports = _ctx_ports(frame)
        assert len(ports) == 1, (
            f"{label}: expected one typed context port, got "
            f"{[(p.name, p.role, p.logical) for p in frame.ports]}")
        p0 = ports[0]
        assert p0.wires == ctx and p0.logical == q
        assert p0.by_sector == (), f"{label}: context was copied per sector"
        assert p0.owner_id is not None and p0.cut_id is not None
        assert p0.origin_cut is not None, f"{label}: lineage was dropped"
        assert completed_dimension(frame) == 8, "4_main x 2_z = 8"
    a_in, a_out = _ctx_ports(res.input_frame)[0], _ctx_ports(res.output_frame)[0]
    assert a_in.owner_id == a_out.owner_id, (
        "one binding became two owners across the two sides")
    assert a_in.origin_cut == a_out.origin_cut


@pytest.mark.parametrize("wire", [0, 1, 2])
def test_G2b_the_expected_ports_exist_before_disjointness_is_tested(wire):
    """ANTI-VACUITY for B4. Grouping wires by role passes trivially when the
    roles are absent, so the roles are asserted present first."""
    res, _arts, pl = _live(wire)
    for frame in (res.input_frame, res.output_frame):
        roles = {p.role for p in frame.ports}
        assert "context" in roles, f"no context port to be disjoint from: {roles}"
    occupied = set(pl.tag_wires) | set(pl.workspace_wires)
    owned = {w for p in _ctx_ports(res.input_frame) for w in p.wires}
    assert owned, "no owned coordinate was recorded"
    assert not (occupied & owned), (
        f"tag/workspace {sorted(occupied)} overlaps the owned context "
        f"{sorted(owned)}")


def test_G2b_two_equal_typed_resources_stay_distinct():
    """Two equal-typed binders are two resources; the live layout preserves
    both and the completion counts both."""
    sc = ProvenanceScope()
    a = TypedBinding("z", q, (0,), sc.owner(), sc.cut())
    b = TypedBinding("w", q, (1,), sc.owner(), sc.cut())
    lay = use_block_layout((a, b), 2, 1, 4)
    assert lay.owned_wires == (0, 1)
    assert lay.tag_wires == (2,) and lay.workspace_wires == (3,)
    cut = sc.cut()
    f = Frame(logical=Plus(q, q), n_qubits=4, codes=(0, 1, 2, 3),
              ports=tuple(Port(x.name, x.logical, x.wires, role="context",
                               owner_id=x.owner_id, cut_id=cut,
                               origin_cut=x.intro_cut)
                          for x in (a, b)))
    assert len({p.owner_id for p in f.ports}) == 2, (
        "two equal-typed resources collapsed")
    assert completed_dimension(f) == 4 * 2 * 2


def test_G2b_same_context_mentioned_twice_is_one_factor():
    """One binder named twice is ONE resource: distinctness is decided by
    recorded (owner, cut), never by how often a port appears."""
    sc = ProvenanceScope()
    own, cut = sc.owner(), sc.cut()
    dup = tuple(Port("z", q, (0,), role="context", owner_id=own, cut_id=cut,
                     origin_cut=cut) for _ in range(2))
    f = Frame(logical=Plus(q, q), n_qubits=3, codes=(0, 1, 2, 3), ports=dup)
    assert completed_dimension(f) == 8, "one owner counted twice"


def test_G2b_nonzero_offset_placement():
    """A wider ambient register with the context high up: tag and workspace
    still take the lowest unowned wires in ascending order."""
    res, _arts, pl = _live(4)
    assert pl.ambient_width == 5
    assert _ctx_ports(res.input_frame)[0].wires == (4,)
    assert pl.tag_wires == (0,) and pl.workspace_wires == (1,)
    assert completed_dimension(res.input_frame) == 8
    assert pl.ingress.dim == 8


@pytest.mark.parametrize("wire", [0, 1, 2])
def test_G2b_both_modes_agree_and_each_matches_the_external_oracle(wire):
    """REPLACES the dead `pending_perm` field pin.

    Ownership is recorded in AMBIENT coordinates, so materialising -- which
    appends a swap network and empties the pending permutation -- must not
    relocate it. Agreement between the two modes is necessary but NOT
    sufficient (both could be identically wrong), so each mode is also
    checked against the external oracle above, which was built from the
    branch morphisms and the sector inclusions alone.
    """
    O = _B_oracle()
    shots = []
    for mode in (False, True):
        res, _arts, pl = _live(wire, materialize=mode)
        sb = res.selected_boundary
        U = res.circuit.get_unitary()
        act = semantic_action(sb.ingress, U, sb.egress)
        assert np.allclose(act, O, atol=ATOL, rtol=0.0), (
            f"materialize={mode}: framed action differs from the external "
            f"oracle by {np.max(np.abs(act - O)):.3e}")
        assert leakage(sb.ingress, U, sb.egress) < ATOL
        assert abs(float(res.circuit.phase)) < ATOL
        shots.append((pl.tag_wires, pl.workspace_wires, pl.block_to_ambient,
                      tuple(sb.ingress.codes), tuple(sb.egress.codes),
                      tuple(res.input_frame.codes),
                      tuple(p.wires for p in _ctx_ports(res.input_frame))))
    assert shots[0] == shots[1], (
        f"the two materialization modes disagree on the live layout or the "
        f"ordered boundary codes:\n  {shots[0]}\n  {shots[1]}")


@pytest.mark.parametrize("wire", [0, 1, 2])
def test_G2b_artifact_preflight_and_emission_share_one_plan_object(wire):
    """ANTI-VACUITY. Not "a plan was produced" -- the SAME object reaches the
    preflight, the emitter and the artifact, by identity."""
    saw = {}
    o_pre, o_emit = TP._preflight_open_use_block, TP._emit_open_use_block

    def spy_pre(plan, amb):
        saw.setdefault("pre", []).append(plan)
        return o_pre(plan, amb)

    def spy_emit(circ, plan):
        saw.setdefault("emit", []).append(plan)
        return o_emit(circ, plan)

    TP._preflight_open_use_block, TP._emit_open_use_block = spy_pre, spy_emit
    try:
        _res, arts, pl = _live(wire)
    finally:
        TP._preflight_open_use_block, TP._emit_open_use_block = o_pre, o_emit
    placed = [a for a in arts if a.placement is not None]
    assert len(placed) == 1, f"{len(placed)} occurrences claim a placement"
    assert placed[0].placement is pl, "the artifact carries a different plan"
    assert saw["emit"] and all(x is pl for x in saw["emit"])
    assert saw["pre"] and all(x is pl for x in saw["pre"])
    # and the plan holds the prepared branch artifacts themselves
    for b in pl.branches:
        assert b.artifact is not None and b.artifact.selected_boundary is not None


@pytest.mark.parametrize("wire", [0, 1, 2])
def test_G2b_each_branch_is_compiled_exactly_once(wire):
    """Counted on the real `compile()` invocations, not on a wrapper."""
    t = B_witness()
    counts = {}
    orig = TP.compile

    def spy(term, **kw):
        for i, br in enumerate(t.branches):
            if term is br:
                counts[i] = counts.get(i, 0) + 1
        return orig(term, **kw)

    TP.compile = spy
    try:
        TP.compile(t, env={"z": [wire]})
    finally:
        TP.compile = orig
    assert counts == {0: 1, 1: 1}, (
        f"branch compile() counts {counts}; each alternative is prepared "
        f"exactly once")


def test_G2b_a_malformed_live_plan_is_refused_before_parent_mutation():
    """REPLACES the old "no partial artifact after a failed z@0 compile".

    z@0 is a valid binding and now compiles, so the witness has to be
    genuinely invalid: a recorded branch placement perturbed to collide with
    the tag. The parent must be untouched, not partially written.
    """
    _res, _arts, pl = _live(2)
    bad_b = _replace(pl.branches[1], local_to_ambient=(pl.tag_wires[0],))
    bad = _replace(pl, branches=(pl.branches[0], bad_b))
    circ = Circuit(pl.ambient_width)
    circ.X(0)
    before = circ.n_gates
    with pytest.raises(UnsupportedFrame) as ei:
        TP._emit_open_use_block(circ, bad)
    assert "tag" in str(ei.value)
    assert circ.n_gates == before, "the parent gained commands on a failure path"


def test_G2b_a_perturbed_recorded_placement_is_discriminated():
    """Move ONE recorded coordinate and require the emission to change.

    The H branch is the one with commands, so its placement is the one whose
    perturbation is observable: sending it to the owned context wire instead
    of the workspace is still a legal placement as far as the tag and the
    spectators are concerned, and it must produce a different circuit.
    """
    _res, _arts, pl = _live(2)
    assert TP._preflight_open_use_block(pl, pl.ambient_width)
    b1 = pl.branches[1]
    assert b1.artifact.cmds, "the perturbed branch emits nothing to observe"
    owned = tuple(w for w in range(pl.ambient_width)
                  if w not in set(pl.tag_wires) | set(pl.workspace_wires))
    moved = _replace(b1, local_to_ambient=owned[:1])
    assert moved.local_to_ambient != b1.local_to_ambient
    bad = _replace(pl, branches=pl.branches[:1] + (moved,))
    circ = Circuit(pl.ambient_width)
    TP._emit_open_use_block(circ, bad)
    ref = Circuit(pl.ambient_width)
    TP._emit_open_use_block(ref, pl)
    assert not np.allclose(circ.get_unitary(), ref.get_unitary(), atol=ATOL), (
        "moving a branch's recorded placement changed nothing, so the "
        "emitter is not consuming it")


def test_G2b_unbalanced_blocks_are_never_attachable():
    """A block whose two polarities do not balance must not become a
    CompletedBranch at all."""
    _res, _arts, pl = _live(2)
    b = pl.branches[0]
    thin = BoundaryChart(n_qubits=b.ingress.n_qubits,
                         codes=tuple(b.ingress.codes)[:-1], route=None,
                         label="thin", space="ambient")
    with pytest.raises(ProvenanceError) as ei:
        _replace(b, egress=thin)
    assert "balance" in str(ei.value)


def test_G2a_ctrl_ho_is_completed_blockwise_not_uniformly():
    """SUPERSEDES the 256 / 64-incomplete assertion.

    That gate recorded the OLD uniform-product reading, in which the whole
    occurrence was completed against one context factor:
    ingress 256 = (8+8) x 16_f, egress 64, short by 4. Both numbers were
    artefacts of that model, and the h : Q-oQ residual it went looking for is
    not a separate resource at all -- it is already the S_h factor inside
    u1's selected root.

    The completion is now PER BLOCK, against the context each branch does
    NOT use:

        Complete(u0 | f)     = 4 x 16 = 64
        Complete(empty | u1) = 1 x 16 = 16
        Block                = 64 (+) 16 = 80

    The withdrawn 256 and the uniform (4+16) x 16 = 320 are both refused
    below.
    """
    TP._USE_BLOCK_OBSERVED.clear()
    try:
        compile(D_term())
    except Exception:
        pass                      # controlled emission is a later phase
    assert TP._USE_BLOCK_OBSERVED, "the use-block planner was never reached"
    pl = TP._USE_BLOCK_OBSERVED[-1]
    dims = {b.index: b.dim for b in pl.branches}
    assert dims == {0: 64, 1: 16}, f"block dims {dims}, want 64 and 16"
    assert pl.ingress.dim == 80 and pl.egress.dim == 80
    assert pl.ingress.dim not in (256, 320), (
        "the withdrawn uniform-product readings must not reappear")
    assert sum(dims.values()) == pl.ingress.dim, (
        "the parent is the DIRECT SUM of its blocks")
    assert (4 + 16) * 16 != pl.ingress.dim, (
        "a uniform (sum of branch dims) x T_f product gives 320, not 80")
    assert pl.validate()


# ===========================================================================
# G2c: FACTORIZED vs BLOCK_ONLY.
#
# The Block is ALWAYS the complete cut. A Frame is a possibly-factorized VIEW
# of it, and whether that view exists is decided positively, per polarity, by
# comparing two exact embeddings -- never by catching an error, and never by
# equal dimension.
# ===========================================================================

@pytest.mark.parametrize("wire", [0, 1, 2])
@pytest.mark.parametrize("materialize", MODES)
def test_G2c_B_witness_is_FACTORIZED(wire, materialize):
    res, _arts, pl = _live(wire, materialize=materialize)
    cin, cout = res.factorization
    assert (cin.status, cout.status) == (FACTORIZED, FACTORIZED)
    assert (cin.side, cout.side) == ("ingress", "egress")
    for c in (cin, cout):
        assert c.omitted == () and len(c.factors) == 1
        assert c.factors[0][1] == "z"
        assert c.frame_dim == 4 and c.block_dim == 8
        assert c.ambient_width == 3
    assert [p.name for p in _ctx_ports(res.input_frame)] == ["z"]
    assert [p.name for p in _ctx_ports(res.output_frame)] == ["z"]


def test_G2c_three_branch_witness_is_BLOCK_ONLY():
    """The f0/f1/f2 occurrence: each branch CONSUMES its own function through
    an Apply spine, so its completed block is not that branch's payload times
    a uniform f-factor. The Frame cannot present that, and says so."""
    import test_n_plusmap_open as NPO
    TP._USE_BLOCK_OBSERVED.clear()
    res, arts = compile_with_artifacts(NPO._abstract_three_branch())
    assert TP._USE_BLOCK_OBSERVED, "the use-block planner was never reached"
    pl = TP._USE_BLOCK_OBSERVED[-1]
    placed = [a for a in arts if a.factorization]
    assert placed, "no occurrence recorded a factorization verdict"
    a = placed[-1]
    cin, cout = a.factorization
    assert (cin.status, cout.status) == (BLOCK_ONLY, BLOCK_ONLY)
    for c in (cin, cout):
        assert c.factors == (), "a BLOCK_ONLY frame presents no context port"
        assert len(c.omitted) == 3
        assert {n for _, n in c.omitted} == {"f0", "f1", "f2"}
        assert c.reason, "BLOCK_ONLY recorded no reason"
        assert c.frame_dim == 6
        assert c.block_dim == 192
        assert c.block_dim != 384, "the withdrawn uniform value reappeared"
    # The Frame says only what it can: the main interface, no misleading
    # unconditional f0/f1/f2 ports.
    for frame in (a.input_frame, a.output_frame):
        assert frame.dim == 6
        assert _ctx_ports(frame) == []
        assert completed_dimension(frame) == 6
    assert {b.index: b.dim for b in pl.branches} == {0: 64, 1: 64, 2: 64}
    assert pl.ingress.dim == 192 and pl.egress.dim == 192
    assert sum(b.dim for b in pl.branches) == pl.ingress.dim


def test_G2c_BLOCK_ONLY_keeps_every_resource_typed_and_identified():
    """Nothing may disappear merely because the Frame cannot factorize it."""
    import test_n_plusmap_open as NPO
    TP._USE_BLOCK_OBSERVED.clear()
    _res, arts = compile_with_artifacts(NPO._abstract_three_branch())
    pl = TP._USE_BLOCK_OBSERVED[-1]
    a = [x for x in arts if x.factorization][-1]
    omitted = {oid for oid, _ in a.factorization[0].omitted}
    assert len(omitted) == 3
    typed = {}
    for b in pl.branches:
        for tb in tuple(b.used_bindings) + tuple(b.inactive):
            typed[tb.owner_id] = tb
    assert omitted <= set(typed), (
        f"resources {sorted(omitted - set(typed))} vanished from the Block "
        f"when the Frame could not present them")
    for oid in omitted:
        tb = typed[oid]
        assert tb.logical == Arrow(q, q), f"{tb.name} lost its type"
        assert tb.wires and tb.intro_cut and tb.codes
    # and every block records BOTH the resources it uses and those it does not
    for b in pl.branches:
        assert {x.owner_id for x in b.used_bindings} == set(b.uses)
        assert len(b.used_bindings) == 1 and len(b.inactive) == 2


def test_G2c_a_reordered_completion_is_not_FACTORIZED():
    """NEGATIVE ORDER TEST. Equal cardinality is not a factorization: a Frame
    completing to the same states in a different order would have every
    consumer composing against the wrong basis."""
    sc = ProvenanceScope()
    cut = sc.cut()
    b = TypedBinding("z", q, (2,), sc.owner(), sc.cut())
    port = Port("z", q, (2,), role="context", owner_id=b.owner_id,
                cut_id=cut, origin_cut=b.intro_cut)
    main = Frame(logical=Plus(q, q), n_qubits=3, codes=(0, 2, 4, 6))
    good = BoundaryChart(n_qubits=3, codes=tuple(range(8)), route=None,
                         label="good", space="ambient")
    cert, ports = classify_factorization(
        side="ingress", main_frame=main, ports=(port,), bindings=(b,),
        chart=good, cut_id=cut, main_wires=(0, 1), where="t: ")
    assert cert.status == FACTORIZED and ports == (port,)

    swapped = tuple(range(8))
    swapped = swapped[:2] + (swapped[3], swapped[2]) + swapped[4:]
    assert sorted(swapped) == sorted(good.codes) and swapped != good.codes
    perm = BoundaryChart(n_qubits=3, codes=swapped, route=None,
                         label="perm", space="ambient")
    cert2, ports2 = classify_factorization(
        side="ingress", main_frame=main, ports=(port,), bindings=(b,),
        chart=perm, cut_id=cut, main_wires=(0, 1), where="t: ")
    assert cert2.status == BLOCK_ONLY, (
        "a differently ORDERED completion of the same cardinality was "
        "certified as FACTORIZED")
    assert ports2 == () and "different order" in cert2.reason
    assert cert2.block_dim == cert.block_dim == 8


def test_G2c_malformed_provenance_raises_and_never_becomes_BLOCK_ONLY():
    """Malformed provenance is not a factorization verdict. Every one of
    these must raise, and none may be laundered into BLOCK_ONLY."""
    sc = ProvenanceScope()
    cut, other = sc.cut(), sc.cut()
    b = TypedBinding("z", q, (2,), sc.owner(), sc.cut())
    main = Frame(logical=Plus(q, q), n_qubits=3, codes=(0, 2, 4, 6))
    chart = BoundaryChart(n_qubits=3, codes=tuple(range(8)), route=None,
                          label="c", space="ambient")

    def run(port, bindings=(b,), main_wires=(0, 1)):
        return classify_factorization(
            side="ingress", main_frame=main, ports=(port,),
            bindings=bindings, chart=chart, cut_id=cut,
            main_wires=main_wires, where="t: ")

    ok = dict(name="z", logical=q, wires=(2,), role="context",
              owner_id=b.owner_id, cut_id=cut, origin_cut=b.intro_cut)
    cases = {
        "role": dict(ok, role="residual"),
        "type": dict(ok, logical=Arrow(q, q)),
        "placement": dict(ok, wires=(1,)),
        "owner": dict(ok, owner_id=sc.owner()),
        "cut": dict(ok, cut_id=other),
        "origin": dict(ok, origin_cut=other),
        "sector-conditioned": dict(ok, by_sector=((0, (2,)),)),
    }
    for label, kw in cases.items():
        with pytest.raises(ProvenanceError):
            run(Port(**kw))
    # a collision between the main placement and the owned resource
    with pytest.raises(ProvenanceError):
        run(Port(**ok), main_wires=(0, 2))
    # and the well-formed control still classifies
    assert run(Port(**ok))[0].status == FACTORIZED


# ===========================================================================
# G2d: resource IDENTITY across the branch boundary.
#
# Ordered-code agreement is about the BASIS. A flattened chart carries no
# identities, so a Block whose factors belong to freshly minted owners
# satisfies it exactly as well as one carrying the parent's own resources.
# These gates are what make the difference observable: the resource inside a
# branch must BE the resource outside it, established by handing the parent's
# binding down, never by matching a name, a type, a dimension, an encoding or
# a wire afterwards.
# ===========================================================================

from compile.frames import (BindingTransport, issue_binding_transport,   # noqa
                            check_block_resource_identity,               # noqa
                            ChartFactor, ChartRoute)                     # noqa


def _b_parts(blk, side):
    chart = blk.ingress if side == "ingress" else blk.egress
    return dict(zip(chart.route.parts, chart.route.placements))


def _named_factor(artifact, side, name):
    sb = artifact.selected_boundary
    chart = sb.ingress if side == "ingress" else sb.egress
    return [f for f in chart.route.parts if f.name == name]


@pytest.mark.parametrize("wire", [0, 1, 2])
@pytest.mark.parametrize("materialize", MODES)
def test_G2d_one_owner_across_the_whole_occurrence(wire, materialize):
    """THE gate. Four records of z, one identity -- on both polarities.

    Before the handoff existed the outer Frame, `used_bindings` and
    `inactive` all agreed on the parent owner while the branch's own selected
    root carried a fresh one, so the certificate proved basis-code equality
    and nothing about the resource.
    """
    res, _arts, pl = _live(wire, materialize=materialize)
    b0, b1 = pl.branches
    outer = [p for p in res.input_frame.ports if p.role == "context"]
    outer_out = [p for p in res.output_frame.ports if p.role == "context"]
    assert len(outer) == len(outer_out) == 1
    owner = outer[0].owner_id
    origin = outer[0].origin_cut

    assert outer_out[0].owner_id == owner
    assert outer_out[0].origin_cut == origin
    assert [x.owner_id for x in b0.used_bindings] == [owner]
    assert [x.owner_id for x in b1.inactive] == [owner]
    assert [t.owner_id for t in b0.binding_transport] == [owner]

    # the branch's OWN selected root, both polarities
    for side in ("ingress", "egress"):
        yz = _named_factor(b0.artifact, side, "Y_z")
        assert len(yz) == 1, f"{side}: the branch root has no Y_z factor"
        assert yz[0].owner == owner, (
            f"{side}: the branch root's Y_z is {yz[0].owner}, not the "
            f"parent's {owner}")
        assert yz[0].logical == q
        # ... and the live summand payload is a DIFFERENT resource
        s = _named_factor(b0.artifact, side, "S")
        assert len(s) == 1 and s[0].owner != owner, (
            f"{side}: the summand parameter and z share an owner")

    # lineage and type, everywhere
    for rec in (outer[0], outer_out[0]):
        assert rec.logical == q
    for tb in tuple(b0.used_bindings) + tuple(b1.inactive):
        assert tb.logical == q and tb.intro_cut == origin
    for t in b0.binding_transport:
        assert t.logical == q and t.intro_cut == origin

    # the branch-local placement transports onto the parent's
    t = b0.binding_transport[0]
    assert tuple(b0.local_to_ambient[w] for w in t.local_wires) == \
        t.ambient_wires == (wire,)
    for side in ("ingress", "egress"):
        placed = {f.owner: pl_ for f, pl_ in _b_parts(b0, side).items()}
        assert placed[owner] == (wire,), (
            f"{side}: z landed on {placed[owner]}, not the parent's ({wire},)")

    # and the shape is unchanged
    assert b0.dim == 4 and b1.dim == 4
    assert pl.ingress.dim == 8 and pl.egress.dim == 8
    assert all(c.status == FACTORIZED for c in res.factorization)
    assert check_block_resource_identity(
        pl, tuple(b0.used_bindings), tuple(), "t: ")


def test_G2d_three_branch_resources_keep_their_parent_identity():
    """The BLOCK_ONLY witness. Each f_i is CONSUMED by its branch's Apply
    spine, so there is no factor to point at -- the proof is the recorded
    handoff, which is why `used_bindings` alone was never enough."""
    import test_n_plusmap_open as NPO
    TP._USE_BLOCK_OBSERVED.clear()
    _res, arts = compile_with_artifacts(NPO._abstract_three_branch())
    pl = TP._USE_BLOCK_OBSERVED[-1]
    a = [x for x in arts if x.factorization][-1]
    assert all(c.status == BLOCK_ONLY for c in a.factorization)

    owners = {}
    for b in pl.branches:
        for x in b.inactive:
            owners.setdefault(x.owner_id, x)
    assert len(owners) == 3, "the three function resources are not distinct"

    for b in pl.branches:
        assert len(b.binding_transport) == 1
        t = b.binding_transport[0]
        parent = owners.get(t.owner_id)
        assert parent is not None, (
            f"branch {b.index} was handed {t.owner_id}, which no other block "
            f"records as an owned resource; its identity is unverifiable")
        assert t.intro_cut == parent.intro_cut, "introduction lineage changed"
        assert t.logical == parent.logical == Arrow(q, q)
        assert tuple(t.codes) == tuple(parent.codes)
        assert tuple(t.ambient_wires) == tuple(parent.wires)
        t.check_transport(b.local_to_ambient, "t: ")
        # consumed, so absent from its own chart -- and that is exactly the
        # case the handoff exists to cover
        carried = {f.owner for f in b.ingress.route.parts}
        assert t.owner_id not in carried
        assert {x.owner_id for x in b.inactive} <= carried
    assert check_block_resource_identity(
        pl, tuple(owners.values()), tuple(), "t: ")


def _reminted(pl, side_names=("ingress", "egress")):
    """Branch 0's chart with its z factor reassigned to a fresh owner."""
    b0 = pl.branches[0]
    owner = b0.used_bindings[0].owner_id
    fresh = ProvenanceScope().owner()
    assert fresh != owner
    out = {}
    for side in side_names:
        chart = b0.ingress if side == "ingress" else b0.egress
        parts = tuple(_replace(f, owner=fresh) if f.owner == owner else f
                      for f in chart.route.parts)
        out[side] = _replace(chart, route=_replace(chart.route, parts=parts))
    return _replace(b0, **out)


def test_G2d_a_reminted_resource_is_refused_and_not_downgraded():
    """MUTATION GATE. Give branch 0's z factor a fresh owner: the codes are
    untouched, so the BASIS still agrees exactly -- and that is the point.

    The identity gate must refuse it, and the refusal must NOT be absorbed as
    a BLOCK_ONLY verdict: a resource that is not the parent's is an error,
    not a frame that merely cannot factorize.
    """
    res, _arts, pl = _live(2)
    bindings = tuple(pl.branches[0].used_bindings)
    assert check_block_resource_identity(pl, bindings, (), "t: ")
    bad = _replace(pl, branches=(_reminted(pl),) + pl.branches[1:])

    # the BASIS is untouched: ordered codes still agree, so classification
    # would still say FACTORIZED. The two gates are independent.
    assert tuple(bad.branches[0].ingress.codes) == \
        tuple(pl.branches[0].ingress.codes)
    assert all(c.status == FACTORIZED for c in res.factorization)

    with pytest.raises(ProvenanceError) as ei:
        check_block_resource_identity(bad, bindings, (), "t: ")
    msg = str(ei.value)
    assert "carry the PARENT'S resource" in msg, msg
    assert BLOCK_ONLY not in msg, "an identity failure was reported as a verdict"


def test_G2d_omitting_the_handoff_fails_the_live_B_gate():
    """MUTATION GATE, end to end. Withhold the typed view and the nested
    compilation mints its own owner again -- which is exactly the defect this
    repair closed. The occurrence must fail before it emits anything."""
    emitted = []
    o_art, o_emit = TP._compile_branch_artifact, TP._emit_open_use_block

    def no_handoff(branch, *, env=None, scope=None, parameter=None,
                   typed_env=None, **kw):
        return o_art(branch, env=env, scope=scope, parameter=parameter,
                     typed_env=None, **kw)

    def spy_emit(circ, plan):
        emitted.append(plan)
        return o_emit(circ, plan)

    TP._compile_branch_artifact, TP._emit_open_use_block = no_handoff, spy_emit
    try:
        with pytest.raises(ProvenanceError) as ei:
            compile(B_witness(), env={"z": [2]})
    finally:
        TP._compile_branch_artifact, TP._emit_open_use_block = o_art, o_emit
    assert not emitted, "the parent was emitted despite an unproved resource"
    # The remint is now refused at branch-projection time, BEFORE the Block
    # identity gate ever sees a plan: the fresh owner reaches the branch's
    # role context, which names only the roots the parent actually issued.
    assert "has no recorded role at" in str(ei.value), str(ei.value)


def test_G2d_a_broken_local_to_ambient_transport_is_refused():
    """MUTATION GATE. Move the branch-local wires the binding was handed to,
    and the handoff no longer lands on the parent's placement."""
    _res, _arts, pl = _live(2)
    b0 = pl.branches[0]
    bindings = tuple(b0.used_bindings)
    swapped = _replace(b0, local_to_ambient=tuple(reversed(b0.local_to_ambient)))
    bad = _replace(pl, branches=(swapped,) + pl.branches[1:])
    with pytest.raises(ProvenanceError) as ei:
        check_block_resource_identity(bad, bindings, (), "t: ")
    assert "transport" in str(ei.value)


def test_G2d_a_handoff_may_not_mint_a_new_identity():
    """`issue_binding_transport` refuses to record a handoff that is not one:
    a fresh owner, a rewritten origin, a changed type or a re-encoding is a
    DIFFERENT resource wearing the same name."""
    sc = ProvenanceScope()
    parent = TypedBinding("z", q, (2,), sc.owner(), sc.cut())
    ok = TypedBinding("z", q, (1,), parent.owner_id, parent.intro_cut,
                      codes=tuple(parent.codes))
    assert issue_binding_transport(parent, ok, (0, 2), "t: ").ambient_wires == (2,)
    for bad in (TypedBinding("z", q, (1,), sc.owner(), parent.intro_cut),
                TypedBinding("z", q, (1,), parent.owner_id, sc.cut())):
        with pytest.raises(ProvenanceError) as ei:
            issue_binding_transport(parent, bad, (0, 2), "t: ")
        assert "keeps its identity" in str(ei.value)
    # ... and a view whose local wires do not reach the parent's placement
    with pytest.raises(ProvenanceError) as ei:
        issue_binding_transport(parent, ok, (0, 1), "t: ")
    assert "transports from" in str(ei.value)


def test_G2d_the_summand_parameter_is_never_the_context():
    """The payload a branch is GIVEN and the context it USES are two
    resources; sharing an owner would make the completion count one twice."""
    _res, _arts, pl = _live(2)
    bindings = tuple(pl.branches[0].used_bindings)
    owner = bindings[0].owner_id
    assert check_block_resource_identity(pl, bindings, ("own:elsewhere",), "t: ")
    with pytest.raises(ProvenanceError) as ei:
        check_block_resource_identity(pl, bindings, (owner,), "t: ")
    assert "not the context it uses" in str(ei.value)
