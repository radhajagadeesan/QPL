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
from compile.to_pytket import compile, compile_with_artifacts, select_frames
from compile.frames import (Frame, Port, semantic_action, leakage, pretty,
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
                owner_id="OWN-SENTINEL", cut_id="CUT-SENTINEL")


def _assert_survives(ports, where):
    assert ports, f"{where}: the port vanished"
    for p in ports:
        assert p.owner_id == "OWN-SENTINEL", f"{where}: owner_id dropped"
        assert p.cut_id == "CUT-SENTINEL", f"{where}: cut_id dropped"


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

    def spy(br, *, env=None):
        a = orig(br, env=env)
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


def test_D3_completed_dimensions_balance():
    _, arts = compile_with_artifacts(D_term())
    pms = [a for a in arts if isinstance(a.term, (PlusMap, NPlusMap))]
    assert pms, "no internal sum occurrence"
    a = pms[0]
    assert a.input_frame.completed_dimension == 256, (
        "ingress completed dimension must be (8+8)*16_f = 256")
    assert a.output_frame.completed_dimension == 256, (
        "egress completed dimension must be (2+2)*16_f*4_h = 256")


def test_D4_ambient_support_and_spectators():
    _, arts = compile_with_artifacts(D_term())
    pms = [a for a in arts if isinstance(a.term, (PlusMap, NPlusMap))]
    a = pms[0]
    assert a.input_frame.n_qubits == 10, "ambient width is not 10"
    support = {w for p in a.input_frame.ports for w in p.all_wires()}
    assert len(support) == 8, f"support cardinality {len(support)}, not 8"
    spectators = [p for p in a.input_frame.ports if p.role == "residual"]
    assert len(spectators) == 2, f"{len(spectators)} spectators, not 2"


def test_D5_typed_f_context_and_h_residual_with_provenance():
    _, arts = compile_with_artifacts(D_term())
    pms = [a for a in arts if isinstance(a.term, (PlusMap, NPlusMap))]
    ports = pms[0].input_frame.ports + pms[0].output_frame.ports
    typed = [p for p in ports if p.logical not in (Unit(),)]
    assert any(isinstance(p.logical, Arrow) for p in typed), (
        "no typed f:EndoOp context port")
    for p in typed:
        assert p.name not in ("fn_layout", "ancilla"), (
            f"live resource kept a generic name: {p.name}")
        assert getattr(p, "owner_id", None) is not None, f"{p.name}: no owner"
        assert getattr(p, "cut_id", None) is not None, f"{p.name}: no cut"


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

    def spy(b2, *, env=None):
        r = orig(b2, env=env)
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


def test_E6_bridge_exposes_nested_occurrence_frames():
    """The OCaml bridge must round-trip nested artifact frames, not only the
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
