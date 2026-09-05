"""NF-1 Part L: Seq across cuts -- relays, general composition, and the
Block as one aggregate factor.

  L0  Seq relays a DERIVED boundary across a CERTIFIED IDENTITY leg -- a leg
      that emitted nothing, carries no phase, does not permute, and whose
      ingress chart is its egress chart -- across a strictly identity Align.

  L1  Seq relays across a bound-variable ROUTING handoff, on a certificate the
      variable's own emitter issues. This is NOT "any gate-free permutation":
      an arbitrary structural permutation carries no certificate -- and since
      Milestone 4 it is COMPOSED through the cut's own wire-permutation
      transport rather than refused.

  L2  An open sum's Block is exposed as ONE aggregate factor over its own
      direct-sum alphabet, with a genuine one-factor scatter route. It is
      never a product of its sectors, and TenPack is not weakened to accept
      route-less charts.

  L3  (Milestone 4) When no relay applies, the cut is GENERAL: identity,
      wire-permutation and code-permutation cuts all select ONE CutTransport
      and compose through the one seq_cut authority, transactionally --
      the consumer and any Align are staged, and the parent circuit commits
      only after the composition validates.
"""

import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(__file__))

from lang.types import Q, Ten, Arrow, Plus, Unit
from lang.terms import LetPair, Apply, Var, Id, Seq, Pair, H as Hg, S as Sg
import compile.to_pytket as TP
from compile.to_pytket import compile, compile_with_artifacts
from compile.frames import (semantic_action, leakage, ProvenanceError,
                            UnsupportedFrame, FRAME_DEFAULT, DERIVED,
                            RoutingOnly, BlockDescriptor,
                            aggregate_block_chart, ChartFactor,
                            check_binding_consistency, TypedBinding,
                            ProvenanceScope, OpenUseBlockPlan)

q = Q()
endo = Arrow(q, q)
MODES = [False, True]
ATOL = 1e-10


def arts_of(term, materialize=False, env=None):
    _, a = compile_with_artifacts(term, materialize=materialize, env=env)
    return a


def seqs(arts):
    return [a for a in arts if isinstance(a.term, Seq)]


# ===========================================================================
# 0. The strict-identity relay: cases A, B, C, D
# ===========================================================================

def test_L1_case_B_relays_a_derived_right_across_an_identity_left():
    """Seq(Id, <derived>) -- the left leg emits nothing and does not permute."""
    inner = LetPair("h", "y", endo, q, Id(Ten(endo, q)),
                    Apply(Var("h", endo), Var("y", q)))
    t = Seq(Id(Ten(endo, q)), inner)
    arts = arts_of(t)
    root = [a for a in arts if a.occurrence == 0][0]
    sb = root.selected_boundary
    assert sb.authority == DERIVED
    assert sb.origin.startswith("seq:relay-right<-"), sb.origin
    body = [a for a in arts if isinstance(a.term, LetPair)][0]
    assert sb.ingress.codes == body.selected_boundary.ingress.codes
    assert sb.egress.codes == body.selected_boundary.egress.codes


def test_L2_case_A_relays_a_derived_left_across_an_identity_right():
    """Seq(<derived>, Id) -- the right leg is the certified identity."""
    inner = LetPair("h", "y", endo, q, Id(Ten(endo, q)),
                    Apply(Var("h", endo), Var("y", q)))
    t = Seq(inner, Id(q))
    arts = arts_of(t)
    root = [a for a in arts if a.occurrence == 0][0]
    sb = root.selected_boundary
    assert sb.authority == DERIVED
    assert sb.origin.startswith("seq:relay-left<-"), sb.origin
    assert sb.ingress.dim == 4 and sb.egress.dim == 4


def test_L3_case_C_is_exactly_frame_default_on_both_legs():
    t = Seq(Id(q), Hg(0, q))
    arts = arts_of(t)
    root = [a for a in arts if a.occurrence == 0][0]
    sb = root.selected_boundary
    assert sb.authority == FRAME_DEFAULT
    assert sb.origin == "seq:frame-default"


def test_L4_case_D_composes_two_derived_legs_exactly():
    """Both legs derived and NEITHER a certified identity: nothing is
    relayed -- the two boundaries COMPOSE through the cut's own transport,
    and the composed action is exactly (S H) (x) I. This replaces the
    Milestone-4 refusal: general SeqCut transport is implemented."""
    t = Seq(Pair(Hg(0, q), Id(q)), Pair(Sg(0, q), Id(q)))
    for mat in MODES:
        r, arts = compile_with_artifacts(t, materialize=mat)
        root = [a for a in arts if a.occurrence == 0][0]
        sb = root.selected_boundary
        assert sb.authority == DERIVED
        assert sb.origin.startswith("seq:cut<-"), sb.origin
        U = r.circuit.get_unitary()
        SH = np.array([[1, 0], [0, 1j]]) @ (
            np.array([[1, 1], [1, -1]]) / np.sqrt(2))
        want = np.kron(SH, np.eye(2))
        got = semantic_action(sb.ingress, U, sb.egress)
        assert np.allclose(got, want, atol=ATOL, rtol=0.0)
        assert not np.allclose(got, np.eye(4), atol=ATOL)
        assert leakage(sb.ingress, U, sb.egress) < ATOL
        assert abs(float(r.circuit.phase)) < ATOL


def test_L4b_two_derived_certified_identities_compose_without_picking():
    """A derived boundary on BOTH legs, both contributing nothing: which one
    a relay would carry is not determined -- so NOTHING is relayed. The two
    boundaries compose through the cut, which needs no such choice, and the
    result is the exact identity."""
    t = Seq(Pair(Id(q), Id(q)), Pair(Id(q), Id(q)))
    for mat in MODES:
        r, arts = compile_with_artifacts(t, materialize=mat)
        root = [a for a in arts if a.occurrence == 0][0]
        sb = root.selected_boundary
        assert sb.authority == DERIVED
        assert sb.origin.startswith("seq:cut<-"), (
            "the ambiguity was resolved by picking a relay; it must be "
            "resolved by composing")
        U = r.circuit.get_unitary()
        assert np.allclose(semantic_action(sb.ingress, U, sb.egress),
                           np.eye(4), atol=ATOL, rtol=0.0)
        assert leakage(sb.ingress, U, sb.egress) < ATOL
        assert len(r.circuit.get_commands()) == 0


def test_L4d_the_seq_transaction_validates_before_the_parent_commits():
    """The WHOLE general cut is transactional: the consumer and any Align
    are staged, and the composition validates through seq_cut before the
    parent circuit gains a command. A composition that refuses aborts the
    compilation -- no completed parent ever contains a half-committed Seq."""
    class _Sentinel(Exception):
        pass

    def bomb(*a, **k):
        raise _Sentinel()

    real = TP.seq_cut
    TP.seq_cut = bomb
    try:
        with pytest.raises(_Sentinel):
            compile(Seq(Pair(Hg(0, q), Id(q)), Pair(Sg(0, q), Id(q))))
    finally:
        TP.seq_cut = real


def test_L4c_a_derived_but_inert_leg_is_still_a_valid_identity_relay():
    """A Pair that emits no gate, no phase and no permutation is a certified
    identity even though it carries a derived Par boundary of its own.
    Refusing to relay past it would reject a legitimate cut -- which is what
    regressed ctrl_lambda_e2e until this was corrected."""
    # left: derived (Par) but inert.  right: derived and ACTIVE (emits H).
    t = Seq(Pair(Id(q), Id(q)), Pair(Hg(0, q), Id(q)))
    r, arts = compile_with_artifacts(t)
    root = [a for a in arts if a.occurrence == 0][0]
    left = next(a for a in arts if a.term is root.term.f)
    right = next(a for a in arts if a.term is root.term.g)
    assert left.selected_boundary.authority == DERIVED
    assert left.n_cmds == 0 and right.n_cmds == 1
    assert root.selected_boundary.authority == DERIVED
    assert root.selected_boundary.origin.startswith("seq:relay-right<-"), (
        root.selected_boundary.origin)
    assert root.selected_boundary.ingress.codes == \
        right.selected_boundary.ingress.codes


def test_L5_case_D_composes_a_command_bearing_sibling():
    """A derived leg beside a gate-emitting leg is not a relay -- it is a
    GENERAL cut, and it composes: the sibling's command is emitted, the
    producer's derived boundary survives into the composite, and the
    composition leaks nothing."""
    inner = LetPair("h", "y", endo, q, Id(Ten(endo, q)),
                    Apply(Var("h", endo), Var("y", q)))
    for mat in MODES:
        r, arts = compile_with_artifacts(Seq(inner, Hg(0, q)),
                                         materialize=mat)
        root = [a for a in arts if a.occurrence == 0][0]
        sb = root.selected_boundary
        assert sb.authority == DERIVED
        assert sb.origin.startswith("seq:cut<-letpair:splice"), sb.origin
        U = r.circuit.get_unitary()
        assert leakage(sb.ingress, U, sb.egress) < ATOL
        assert abs(float(r.circuit.phase)) < ATOL
        assert any(c.op.type.name == "H" for c in r.circuit.get_commands())


def test_L6_case_D_composes_a_phase_bearing_sibling():
    """A phase-only sibling composes, and its scalar arrives EXACTLY: the
    composite's phase is the sibling's own compiled phase, neither dropped
    nor doubled."""
    from lang.terms import ExpInvolution
    inner = LetPair("h", "y", endo, q, Id(Ten(endo, q)),
                    Apply(Var("h", endo), Var("y", q)))
    sibling = ExpInvolution(0.3, Id(q))          # scalar: phase only
    own = float(compile(sibling).circuit.phase)
    assert abs(own) > 1e-6, "the witness sibling must actually carry phase"
    for mat in MODES:
        r, arts = compile_with_artifacts(Seq(inner, sibling),
                                         materialize=mat)
        root = [a for a in arts if a.occurrence == 0][0]
        sb = root.selected_boundary
        assert sb.authority == DERIVED
        assert sb.origin.startswith("seq:cut<-"), sb.origin
        assert abs(float(r.circuit.phase) - own) < ATOL, (
            "the sibling's phase was dropped or altered by the cut")
        U = r.circuit.get_unitary()
        assert leakage(sb.ingress, U, sb.egress) < ATOL


def test_L7_a_derived_boundary_is_never_replaced_by_a_frame_default():
    """Whatever else happens, case D never silently defaults: the composite
    carries the producer's DERIVED authority and its recorded origin, not a
    frame default wearing its width."""
    inner = LetPair("h", "y", endo, q, Id(Ten(endo, q)),
                    Apply(Var("h", endo), Var("y", q)))
    for mat in MODES:
        _r, arts = compile_with_artifacts(Seq(inner, Hg(0, q)),
                                          materialize=mat)
        root = [a for a in arts if a.occurrence == 0][0]
        sb = root.selected_boundary
        assert sb.authority == DERIVED, (
            "the derived boundary was replaced by a frame default")
        assert sb.origin != "seq:frame-default"
        assert "letpair:splice" in sb.origin, sb.origin


# ===========================================================================
# 1. The bound-variable routing certificate
# ===========================================================================

def test_L8_the_certificate_is_issued_by_the_variable_emitter():
    """It is recorded by the emitter that does the routing, and carries the
    binding identity, both handoffs and both permutations."""
    t = LetPair("h", "y", endo, q, Id(Ten(endo, q)),
                Apply(Var("h", endo), Var("y", q)))
    arts = arts_of(t)
    certs = [a.routing for a in arts if a.routing is not None]
    assert certs, "no bound Var issued a routing certificate"
    for c, a in ((a.routing, a) for a in arts if a.routing is not None):
        assert isinstance(c, RoutingOnly)
        assert c.n_cmds == 0 and abs(c.phase_delta) < 1e-12
        assert c.ingress_wires == c.wires == c.egress_wires
        assert tuple(c.perm_at_entry) == tuple(a.perm_at_entry)
        assert tuple(c.perm_at_exit) == tuple(a.perm_at_exit)
        assert c.validate()


def test_L9_only_a_bound_variable_carries_a_certificate():
    """An arbitrary gate-free structural permutation does NOT get one."""
    from lang.terms import TwistTen
    Z = Plus(Plus(Unit(), Unit()), Unit())
    t = Seq(Id(Ten(q, Z)), TwistTen(q, Z))
    arts = arts_of(t)
    for a in arts:
        if isinstance(a.term, TwistTen):
            assert a.routing is None, (
                "a structural permutation must not be certified as routing")
            assert tuple(a.perm_at_entry) != tuple(a.perm_at_exit), (
                "this witness needs a term that really permutes")


def test_L10_an_uncertified_permuting_leg_composes_through_the_transport():
    """Same SHAPE as the routing relay -- a gate-free permuting left leg
    beside a derived right one -- but with no certificate. It is NOT
    relayed and NOT refused: the boundaries compose through the SAME
    transport + seq_cut authority as every other cut. The structural
    permutation folds into the running WirePerm BEFORE the cut forms, so
    both premises' recorded interfaces already agree and the truthful
    cut-local transport kind is "identity" -- the twist is visible in the
    artifact's exit permutation, never gauged into the cut."""
    from lang.terms import TwistTen
    import compile.align as AL
    made = []
    real_make = AL.make_cut_transport

    def spy_make(*a, **k):
        tr = real_make(*a, **k)
        made.append(tr)
        return tr

    consumed = []
    real_cut = TP.seq_cut

    def spy_cut(prod, cons, transport, **kw):
        consumed.append(transport)
        return real_cut(prod, cons, transport, **kw)

    AL.make_cut_transport = spy_make
    TP.make_cut_transport = spy_make
    TP.seq_cut = spy_cut
    try:
        for mat in MODES:
            made.clear()
            consumed.clear()
            r, arts = compile_with_artifacts(
                Seq(TwistTen(q, q), Pair(Id(q), Id(q))), materialize=mat)
            root = [a for a in arts if a.occurrence == 0][0]
            sb = root.selected_boundary
            assert sb.authority == DERIVED
            assert sb.origin.startswith("seq:cut<-"), sb.origin
            # ONE authority: the transport seq_cut consumed IS the object
            # the cut selection minted
            assert consumed and made
            assert consumed[0] is made[-1]
            assert consumed[0].kind == "identity", (
                "the pre-cut fold makes this cut identity; a non-identity "
                "kind here would mean the twist leaked into the cut")
            # ... and the twist is REAL, recorded in the routing
            assert tuple(root.perm_at_entry) != tuple(root.perm_at_exit)
            U = r.circuit.get_unitary()
            assert leakage(sb.ingress, U, sb.egress) < ATOL
            assert abs(float(r.circuit.phase)) < ATOL
    finally:
        AL.make_cut_transport = real_make
        TP.make_cut_transport = real_make
        TP.seq_cut = real_cut


def test_L11_the_certificate_refuses_a_gate_or_a_phase():
    c = RoutingOnly(name="z", wires=(0,), owner_id="own:1",
                    ingress_wires=(0,), egress_wires=(0,), n_cmds=1)
    with pytest.raises(ProvenanceError) as e:
        c.validate()
    assert "gate-free" in str(e.value)
    c2 = RoutingOnly(name="z", wires=(0,), owner_id="own:1",
                     ingress_wires=(0,), egress_wires=(0,), phase_delta=0.5)
    with pytest.raises(ProvenanceError):
        c2.validate()
    c3 = RoutingOnly(name="z", wires=(0,), owner_id="own:1",
                     ingress_wires=(1,), egress_wires=(1,))
    with pytest.raises(ProvenanceError) as e:
        c3.validate()
    assert "binding sits on" in str(e.value)


SELECT4_ENTRY = (6, 7, 8, 9, 10, 4, 5, 2, 3, 0, 1, 11, 12, 13)
SELECT4_EXIT = (8, 9, 10, 6, 7, 4, 5, 2, 3, 0, 1, 11, 12, 13)
SELECT4_HANDOFF = (8, 9, 10)


def select_4():
    """The EXACT term the nested_select_e2e demo compiles.

    Dumped from `abstract_select_4` in ocaml/demos/nested_select_e2e.ml via
    Bridge.term_to_json, so this is the real derivation and not a proxy.
    """
    from test_nf1_beta_tensor import _fixture
    return _fixture("select_4_abstract")


def routing_relay_occurrence(arts):
    """The one occurrence whose boundary came from the routing relay."""
    rel = [a for a in arts if a.selected_boundary is not None
           and a.selected_boundary.origin.startswith("seq:routing-relay")]
    assert len(rel) == 1, f"expected one routing relay, got {len(rel)}"
    return rel[0]


@pytest.mark.parametrize("materialize", MODES)
def test_L12_the_routing_certificate_of_the_real_select_4(materialize):
    """The certificate the bound Var actually issued, pinned exactly."""
    arts = arts_of(select_4(), materialize=materialize)
    certs = [a for a in arts if a.routing is not None
             and tuple(a.routing.wires) == SELECT4_HANDOFF]
    assert certs, "the routed bound Var issued no certificate"
    a = certs[0]
    c = a.routing
    assert tuple(c.perm_at_entry) == SELECT4_ENTRY, c.perm_at_entry
    assert tuple(c.perm_at_exit) == SELECT4_EXIT, c.perm_at_exit
    assert tuple(c.perm_at_entry) != tuple(c.perm_at_exit), (
        "this witness must exercise the NONIDENTITY routing case")
    assert tuple(c.ingress_wires) == SELECT4_HANDOFF
    assert tuple(c.egress_wires) == SELECT4_HANDOFF
    assert c.n_cmds == 0 and abs(c.phase_delta) < 1e-12
    assert c.owner_id, "the binder identity was not threaded to the Var"
    assert c.validate(artifact=a)
    assert len(c.perm_at_entry) == 14


@pytest.mark.parametrize("materialize", MODES)
def test_L12b_the_relay_carries_the_right_childs_chart_payload(materialize):
    """Chart PAYLOAD unchanged -- codes, space, route kind, factors,
    placements and descriptor identities are the right child's. Only the
    diagnostic origin differs, so this is not literally byte-for-byte."""
    r, arts = compile_with_artifacts(select_4(), materialize=materialize)
    rel = routing_relay_occurrence(arts)
    right = next(a for a in arts if a.term is rel.term.g)
    left = next(a for a in arts if a.term is rel.term.f)
    assert tuple(left.egress_wires) == SELECT4_HANDOFF
    assert tuple(right.ingress_wires) == SELECT4_HANDOFF
    rb, sb = right.selected_boundary, rel.selected_boundary
    assert sb.authority == DERIVED
    assert sb.origin == f"seq:routing-relay<-{rb.origin}"
    for side in ("ingress", "egress"):
        a_ch, b_ch = getattr(sb, side), getattr(rb, side)
        assert a_ch.codes == b_ch.codes
        assert a_ch.space == b_ch.space == "ambient"
        assert a_ch.n_qubits == b_ch.n_qubits == 14
        assert a_ch.route.kind == b_ch.route.kind
        assert a_ch.route.placements == b_ch.route.placements
        assert [f.role for f in a_ch.route.parts] == \
            [f.role for f in b_ch.route.parts]
        for fa, fb in zip(a_ch.route.parts, b_ch.route.parts):
            assert fa.descriptor is fb.descriptor
    assert rb.ingress.dim == 1024, f"right dim {rb.ingress.dim}"


def test_L12c_materialisation_transports_the_egress_exactly_once():
    """Ingress unchanged; egress moved forward through the swap network. The
    routing permutation is a 3-cycle, so no transport, inverse transport and
    double transport are three DIFFERENT answers."""
    from compile.frames import permute_index
    r0, a0 = compile_with_artifacts(select_4(), materialize=False)
    r1, a1 = compile_with_artifacts(select_4(), materialize=True)
    p0 = routing_relay_occurrence(a0).selected_boundary
    p1 = routing_relay_occurrence(a1).selected_boundary
    assert p0.ingress.codes == p1.ingress.codes, "the ingress must not move"
    assert p0.egress.codes != p1.egress.codes, "the egress must move once"
    pre = tuple(r0.perm.new_to_old)
    n = p0.egress.n_qubits
    fwd = tuple(permute_index(c, pre, n) for c in p0.egress.codes)
    assert fwd == p1.egress.codes, "the egress was not transported forward"
    inv = [0] * n
    for j, o in enumerate(pre):
        inv[o] = j
    twice = tuple(permute_index(c, pre, n) for c in fwd)
    assert twice != p1.egress.codes, "double transport must differ"
    # select_4's MATERIALISATION permutation is a product of disjoint
    # transpositions, so inverse transport coincides with forward here of
    # necessity, not because the check is missing. Recorded so the gate
    # tightens automatically if that ever stops being true; the direction is
    # discriminated on a genuinely non-involutive permutation in L12e.
    from core.perm import is_involution
    assert is_involution(r0.perm), (
        f"the materialisation permutation {pre} is no longer an involution, "
        f"so inverse transport must now be discriminated here too")
    back = tuple(permute_index(c, inv, n) for c in p0.egress.codes)
    assert back == fwd, "an involution must transport both ways alike"
    # No leakage assertion here: select_4 is 14 qubits, so materialising its
    # full unitary is not simulable. Framed leakage IS checked where it can
    # be -- the emission preflight rejects any prepared branch that leaks out
    # of its own selected boundary, and the demo's partial-trace checks cover
    # the whole term.
    assert r1.circuit.n_qubits == 14


def test_L12e_transport_direction_on_a_non_involutive_permutation():
    """The aggregate Block chart, transported by a genuine 3-cycle: no
    transport, forward, inverse and double are four different answers."""
    from compile.frames import permute_index
    arts = ctrl_ho_arts(False)
    pm = [a for a in arts if isinstance(a.placement, OpenUseBlockPlan)][0]
    ch = pm.selected_boundary.egress
    n = ch.n_qubits
    perm = list(range(n))
    perm[0], perm[1], perm[2] = 1, 2, 0            # a 3-cycle
    perm = tuple(perm)
    from core.perm import WirePerm, is_involution
    assert not is_involution(WirePerm(n, list(perm)))
    inv = [0] * n
    for j, o in enumerate(perm):
        inv[o] = j
    fwd = ch.transport(perm)
    back = ch.transport(tuple(inv))
    twice = fwd.transport(perm)
    assert fwd.codes != ch.codes
    assert back.codes != fwd.codes, "inverse transport must differ"
    assert twice.codes != fwd.codes, "double transport must differ"
    assert twice.codes != ch.codes


def test_L12d_the_certificate_rejects_a_forged_or_broken_claim():
    from compile.frames import RoutingOnly as RO
    base = dict(name="z", wires=(0, 1), owner_id="own:1",
                ingress_wires=(0, 1), egress_wires=(0, 1),
                perm_at_entry=(0, 1), perm_at_exit=(1, 0))
    assert RO(**base).validate()
    for bad, frag in (
            (dict(egress_wires=(1, 0)), "handoff"),
            (dict(owner_id=None), "binder identity"),
            (dict(wires=(0, 0), ingress_wires=(0, 0), egress_wires=(0, 0)),
             "twice"),
            (dict(perm_at_exit=(0, 1, 2)), "describe"),
            (dict(wires=(0, 5), ingress_wires=(0, 5), egress_wires=(0, 5)),
             "outside")):
        d = dict(base)
        d.update(bad)
        with pytest.raises(ProvenanceError) as e:
            RO(**d).validate()
        assert frag in str(e.value), f"{bad}: {e.value}"

    class _FakeArt:
        perm_at_entry = (0, 1)
        perm_at_exit = (0, 1)          # DISAGREES with the certificate
        n_cmds = 0
        phase_delta = 0.0
        egress_wires = (0, 1)
    with pytest.raises(ProvenanceError) as e:
        RO(**base).validate(artifact=_FakeArt())
    assert "but the occurrence recorded" in str(e.value)


# ===========================================================================
# 2. The Block as ONE aggregate factor
# ===========================================================================

def ctrl_ho_arts(materialize=False):
    from test_nf1_beta_tensor import _fixture
    _, arts = compile_with_artifacts(_fixture("ctrl_ho_closed_plus_map"),
                                     materialize=materialize)
    return arts


@pytest.mark.parametrize("materialize", MODES)
def test_L13_ctrl_ho_block_is_one_factor_of_dimension_80(materialize):
    arts = ctrl_ho_arts(materialize)
    pm = [a for a in arts if isinstance(a.placement, OpenUseBlockPlan)][0]
    sb = pm.selected_boundary
    for side, ch in (("ingress", sb.ingress), ("egress", sb.egress)):
        parts = ch.route.parts
        assert len(parts) == 1, (
            f"{side}: {len(parts)} factors; a direct sum is ONE aggregate, "
            f"never a product of its sectors")
        f = parts[0]
        assert f.role == "block", f"{side}: role {f.role!r}"
        assert f.dim == 80, f"{side}: block factor dim {f.dim}, want 80"
        assert f.dim != 64 * 16, "the Block is not 64 x 16"
        assert f.logical is None, (
            "a block is not a source-typed residual and must carry no "
            "logical type")
        d = f.descriptor
        assert isinstance(d, BlockDescriptor)
        assert d.block_width == 8 and d.ambient_width == 10
        assert d.block_to_ambient == (4, 5, 6, 7, 0, 1, 2, 3)
        assert d.block_dims == (64, 16)
        assert ch.route.kind == "scatter" and ch.route.reconstructible
        assert len(ch.route.placements) == 1
    # The INGRESS placement is the recorded injection. The egress placement
    # moves under materialisation, because the root transports the egress
    # once through the appended swap network -- that is the existing final
    # rule, not something this aggregate does.
    assert sb.ingress.route.placements == ((4, 5, 6, 7, 0, 1, 2, 3),)
    if not materialize:
        assert sb.egress.route.placements == ((4, 5, 6, 7, 0, 1, 2, 3),)


@pytest.mark.parametrize("materialize", MODES)
def test_L14_the_aggregate_reproduces_the_plans_codes(materialize):
    arts = ctrl_ho_arts(materialize)
    pm = [a for a in arts if isinstance(a.placement, OpenUseBlockPlan)][0]
    pl, sb = pm.placement, pm.selected_boundary
    assert sb.ingress.codes == tuple(pl.ingress.codes)
    if not materialize:
        assert sb.egress.codes == tuple(pl.egress.codes)
    assert len(sb.ingress.codes) == 80


@pytest.mark.parametrize("materialize", MODES)
def test_L15_both_polarities_share_one_descriptor_identity(materialize):
    arts = ctrl_ho_arts(materialize)
    pm = [a for a in arts if isinstance(a.placement, OpenUseBlockPlan)][0]
    sb = pm.selected_boundary
    di = sb.ingress.route.parts[0].descriptor
    de = sb.egress.route.parts[0].descriptor
    assert di == de, "the two polarities record different Block identities"
    assert di.cut_id == de.cut_id
    # but the alphabets and placements are built independently
    assert sb.ingress.route.parts[0].codes is not sb.egress.route.parts[0].codes


def test_L16_a_block_code_outside_the_placement_is_refused():
    class _P:
        pass
    d = BlockDescriptor(cut_id="cut:x", branch_cuts=("a",), tag_values=(0,),
                        uses=((),), inactive=((),), block_dims=(2,),
                        tag_wires=(0,), block_to_ambient=(0,),
                        block_width=1, ambient_width=2)
    from compile.frames import BoundaryChart
    pl = _P()
    pl.ingress = BoundaryChart(n_qubits=2, codes=(0, 1), route=None,
                               label="p", space="ambient")
    pl.egress = pl.ingress
    with pytest.raises(ProvenanceError) as e:
        aggregate_block_chart(pl, "ingress", d)
    assert "does not name" in str(e.value)


def test_L17_a_block_factor_is_not_a_typed_residual():
    """Typed residual matching must skip role='block'."""
    from compile.frames import _matched_factor, par_then_repart, scatter_repart
    d = BlockDescriptor(cut_id="cut:x", branch_cuts=("a",), tag_values=(0,),
                        uses=((),), inactive=((),), block_dims=(2,),
                        tag_wires=(), block_to_ambient=(0,),
                        block_width=1, ambient_width=1)
    b = ChartFactor(factor_id="tblock0", name="B", owner="cut:x", n_qubits=1, codes=(0, 1),
                    role="block", descriptor=d)
    rep, pl = scatter_repart(((0,),), 1)
    ch = par_then_repart((b,), rep, 1, "b", placements=pl, kind="scatter")
    with pytest.raises(ProvenanceError) as e:
        _matched_factor(ch, Ten(q, q), "test")
    assert "no producer factor" in str(e.value)


def test_L18_a_block_factor_requires_its_descriptor():
    with pytest.raises(ProvenanceError) as e:
        ChartFactor(factor_id="tblock1", name="B", owner="c", n_qubits=1, codes=(0, 1),
                    role="block")
    assert "records no descriptor" in str(e.value)


# ===========================================================================
# 3. Integrity
# ===========================================================================

def test_L19_authority_is_validated():
    from compile.frames import SelectedBoundary, chart_of_frame, canonical_frame
    ch = chart_of_frame(canonical_frame(q))
    with pytest.raises(ProvenanceError) as e:
        SelectedBoundary(ingress=ch, egress=ch, origin="x", authority="maybe")
    assert "exactly" in str(e.value)


def test_L20_duplicate_owner_records_must_agree():
    sc = ProvenanceScope()
    own, cut = sc.owner(), sc.cut()
    a = TypedBinding("z", q, (0,), own, cut)
    same = TypedBinding("z", q, (0,), own, cut)
    assert check_binding_consistency((a, same))
    other = TypedBinding("z", Ten(q, q), (0, 1), own, cut)
    with pytest.raises(ProvenanceError) as e:
        check_binding_consistency((a, other))
    assert "recorded twice with different" in str(e.value)


def test_L21_binding_code_count_matches_its_semantic_dimension():
    sc = ProvenanceScope()
    with pytest.raises(ProvenanceError) as e:
        TypedBinding("z", Plus(q, Unit()), (0, 1), sc.owner(), sc.cut(),
                     codes=(0, 1, 2, 3))
    assert "semantic dimension" in str(e.value)
    ok = TypedBinding("z", Plus(q, Unit()), (0, 1), sc.owner(), sc.cut())
    assert ok.codes == (0, 1, 2)


# ===========================================================================
# 4. The aggregate preserves the direct-sum action, sector by sector
# ===========================================================================

def _blocks_local(plan, desc, side):
    """Each recorded block's own local codes, in order -- computed here, not
    by any production helper."""
    n = desc.ambient_width
    b2a = desc.block_to_ambient
    out = []
    for b in plan.branches:
        bit = 0
        for i, w in enumerate(desc.tag_wires):
            if (b.tag_value >> (len(desc.tag_wires) - 1 - i)) & 1:
                bit |= 1 << (n - 1 - w)
        chart = b.ingress if side == "ingress" else b.egress
        loc = []
        for c in chart.codes:
            a = c | bit
            v = 0
            for i, w in enumerate(b2a):
                v |= ((a >> (n - 1 - w)) & 1) << (len(b2a) - 1 - i)
            loc.append(v)
        out.append(tuple(loc))
    return out


@pytest.mark.parametrize("side", ["ingress", "egress"])
def test_L22_the_aggregate_alphabet_is_the_ordered_concatenation(side):
    """The one Block factor's alphabet IS the blocks' codes, concatenated in
    order -- which is what makes it a faithful direct sum rather than a
    product of the sectors."""
    arts = ctrl_ho_arts(False)
    pm = [a for a in arts if isinstance(a.placement, OpenUseBlockPlan)][0]
    sb, pl = pm.selected_boundary, pm.placement
    desc = sb.ingress.route.parts[0].descriptor
    agg = (sb.ingress if side == "ingress" else sb.egress).route.parts[0]
    per_block = _blocks_local(pl, desc, side)
    assert tuple(x for blk in per_block for x in blk) == agg.codes, (
        f"{side}: the aggregate alphabet is not the ordered concatenation of "
        f"its blocks")
    assert [len(b) for b in per_block] == list(desc.block_dims) == [64, 16]
    assert agg.dim == sum(desc.block_dims) == 80
    assert agg.dim != 64 * 16


@pytest.mark.parametrize("side", ["ingress", "egress"])
def test_L23_tenpack_of_the_aggregate_is_tenpack_of_each_block(side):
    """TenPack(aggregate) == ordered concatenation of TenPack(each block).

    TenPack re-addresses binder wires; applying it to the one aggregate
    factor must move every sector's codes exactly as applying it to that
    sector would. This is the non-vacuous check that treating the Block as
    one alphabet preserves its direct-sum action.
    """
    from compile.frames import tenpack, permute_index
    arts = ctrl_ho_arts(False)
    pm = [a for a in arts if isinstance(a.placement, OpenUseBlockPlan)][0]
    sb, pl = pm.selected_boundary, pm.placement
    desc = sb.ingress.route.parts[0].descriptor
    ch = sb.ingress if side == "ingress" else sb.egress
    n = desc.ambient_width
    # a genuine 3-CYCLE over three of the block's own ambient wires, not a
    # swap: an involution could not tell a direction error from its inverse.
    r_p = tuple(desc.block_to_ambient[:3])
    theta = (1, 2, 0)
    packed = tenpack(ch, r_p, theta)
    assert packed.codes != ch.codes, "this theta must actually move something"
    inv_theta = [0] * 3
    for _j, _o in enumerate(theta):
        inv_theta[_o] = _j
    assert tenpack(ch, r_p, tuple(inv_theta)).codes != packed.codes, (
        "the re-addressing must be non-involutive, or direction is untested")

    # the same re-addressing applied to each block's ambient codes
    move = {w: w for w in range(n)}
    for _i, _w in enumerate(r_p):
        move[_w] = r_p[theta[_i]]
    m = [0] * n
    for w in range(n):
        m[move[w]] = w
    want = []
    for b in pl.branches:
        bit = 0
        for i, w in enumerate(desc.tag_wires):
            if (b.tag_value >> (len(desc.tag_wires) - 1 - i)) & 1:
                bit |= 1 << (n - 1 - w)
        blk = b.ingress if side == "ingress" else b.egress
        want.extend(permute_index(c | bit, m, n) for c in blk.codes)
    assert tuple(packed.codes) == tuple(want), (
        f"{side}: packing the aggregate does not agree with packing each "
        f"block; the aggregate is not faithful to the direct sum")


def test_L24_the_four_surrounding_letpairs_carry_the_block_unchanged():
    """REPLACES a vacuous version that compiled ctrl_ho and whose `carriers`
    collection could be satisfied by the ORIGINATING PlusMap itself, proving
    that no surrounding LetPair consumed anything.

    Driven by the real select_4 term, this requires the four actual LetPair
    binders (f0, f1, f2, f3) and excludes the PlusMap that produced the Block.
    """
    from lang.terms import LetPair as _LP
    from compile.frames import _matched_factor
    from compile.to_pytket import _ambient_chart
    _, arts = compile_with_artifacts(select_4())
    origin = [a for a in arts if isinstance(a.placement, OpenUseBlockPlan)]
    assert origin, "no Block was produced"
    origin_occs = {a.occurrence for a in origin}

    def blocks_of(a, side):
        rt = getattr(a.selected_boundary, side).route
        return [] if rt is None else [f for f in rt.parts if f.role == "block"]

    carriers = [a for a in arts
                if isinstance(a.term, _LP)
                and a.selected_boundary is not None
                and a.occurrence not in origin_occs
                and blocks_of(a, "ingress")]
    assert len(carriers) == 4, (
        f"expected the four surrounding LetPair binders to carry the Block, "
        f"got {len(carriers)}")
    base = {side: blocks_of(origin[0], side)[0]
            for side in ("ingress", "egress")}

    for a in carriers:
        for side in ("ingress", "egress"):
            ch = getattr(a.selected_boundary, side)
            rt = ch.route
            fs = blocks_of(a, side)
            assert len(fs) == 1, (
                f"LetPair {a.occurrence} {side}: {len(fs)} block factors")
            f, b = fs[0], base[side]
            assert f.descriptor is b.descriptor, (
                f"LetPair {a.occurrence} {side}: descriptor identity lost")
            assert f.role == "block" and f.owner == b.owner
            assert f.dim == b.dim
            assert f.codes == b.codes, (
                f"LetPair {a.occurrence} {side}: sparse code order changed")
            assert rt.kind == "scatter" and rt.reconstructible, (
                f"LetPair {a.occurrence} {side}: the route became {rt.kind!r}")
            assert rt.reconstruct() == tuple(ch.codes)
        # the producer is the recorded whole-port yank, with no prefix left
        producer = next(x for x in arts if x.term is a.term.pair)
        n = a.selected_boundary.ingress.n_qubits
        pout = _ambient_chart(producer.selected_boundary.egress,
                              producer.egress_wires, n,
                              logical=producer.output_frame.logical)
        tt = Ten(a.term.ty_x, a.term.ty_y)
        m = _matched_factor(pout, tt, "L24")
        prefix = [x for k, x in enumerate(pout.route.parts) if k != m]
        assert not prefix, (
            f"LetPair {a.occurrence}: the producer has a surviving prefix "
            f"{[x.name for x in prefix]}, which a whole-port yank must not")


def test_L25_a_binder_wire_outside_the_aggregate_placement_fails_closed():
    """TenPack must refuse to re-address a wire the aggregate does not place,
    rather than inferring coverage from a dimension or an ambient width."""
    from compile.frames import tenpack
    arts = ctrl_ho_arts(False)
    pm = [a for a in arts if isinstance(a.placement, OpenUseBlockPlan)][0]
    ch = pm.selected_boundary.ingress
    placed = set(ch.route.placements[0])
    outside = [w for w in range(ch.n_qubits) if w not in placed]
    assert outside, "this witness needs a wire outside the block placement"
    with pytest.raises(ProvenanceError):
        tenpack(ch, (outside[0], ch.n_qubits + 5), (0, 1))
    inside = tuple(sorted(placed))[:2]
    assert tenpack(ch, inside, (1, 0)).dim == ch.dim


@pytest.mark.parametrize("side", ["ingress", "egress"])
def test_L26_splice_of_the_aggregate_is_splice_of_each_block(side):
    """Splice(whole-port Var, aggregate) == ordered concatenation of
    Splice(whole-port Var, each block).

    The producer here is a prefix-free whole-port yank, so the splice is the
    producer pullback of each selected code; doing it once on the aggregate
    alphabet must agree with doing it per sector, in branch order.
    """
    from compile.frames import (tensor_splice, ChartFactor as _CF,
                                par_then_repart as _par,
                                scatter_repart as _sc)
    arts = ctrl_ho_arts(False)
    pm = [a for a in arts if isinstance(a.placement, OpenUseBlockPlan)][0]
    sb, pl = pm.selected_boundary, pm.placement
    desc = sb.ingress.route.parts[0].descriptor
    ch = sb.ingress if side == "ingress" else sb.egress
    n = desc.ambient_width
    port = tuple(desc.block_to_ambient)
    tt = Ten(q, q)

    # a whole-port producer over the block's own placement, with a
    # deliberately NON-IDENTITY correspondence so the pullback is visible
    fwd = _CF(factor_id="tL-fwd", name="P", owner="cut:p", n_qubits=len(port),
              codes=tuple(range(1 << len(port))), role="residual", logical=tt)
    rev = _CF(factor_id="tL-rev", name="P", owner="cut:p", n_qubits=len(port),
              codes=tuple(reversed(range(1 << len(port)))),
              role="residual", logical=tt)
    rep, pls = _sc((port,), n)
    prod_out = _par((fwd,), rep, n, "po", placements=pls, kind="scatter")
    prod_in = _par((rev,), rep, n, "pi", placements=pls, kind="scatter")
    assert prod_in.codes != prod_out.codes

    agg_in, _ = tensor_splice(prod_in, prod_out, ch, ch, tt)

    # the same producer, applied to each block's ambient codes in order
    want = []
    for b in pl.branches:
        bit = 0
        for i, w in enumerate(desc.tag_wires):
            if (b.tag_value >> (len(desc.tag_wires) - 1 - i)) & 1:
                bit |= 1 << (n - 1 - w)
        blk = b.ingress if side == "ingress" else b.egress
        loc = []
        for c in blk.codes:
            a = c | bit
            v = 0
            for i, w in enumerate(port):
                v |= ((a >> (n - 1 - w)) & 1) << (len(port) - 1 - i)
            k = prod_out.route.parts[0].codes.index(v)
            pin = prod_in.route.parts[0].codes[k]
            out = 0
            for i, w in enumerate(port):
                if (pin >> (len(port) - 1 - i)) & 1:
                    out |= 1 << (n - 1 - w)
            loc.append(out)
        want.extend(loc)
    assert tuple(agg_in.codes) == tuple(want), (
        f"{side}: splicing the aggregate does not agree with splicing each "
        f"block in order")
    assert len(want) == sum(desc.block_dims) == 80
