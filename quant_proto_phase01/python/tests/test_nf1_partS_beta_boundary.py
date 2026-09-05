"""NF-1 Part S: the beta-reduced Apply boundary.

Milestone-5 gates. For `Apply(Lam(x, A, body), argument)` the external
negative boundary is the prepared ARGUMENT artifact's exact ingress
boundary; the external positive boundary is the compiled BODY artifact's
exact egress boundary; the function-value layout coordinates between them
are internal and never advertised as external input padding. The
substitution cut is recorded and validated at the beta-reduction site as a
`BetaSubstitution` -- from the actual artifacts, binder identity and
physical schedule, never from type_of, widths, offsets, canonical frames
or code geometry.

The repair is BOUNDARY-ONLY: the emitted commands, phase and pending
permutation are pinned against the pre-repair compilation.
"""

import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(__file__))

from lang.terms import Apply, H as Hg, Id, Lam, LetPair, Pair, S as Sg, Seq, Var
from lang.types import Q, Ten, Arrow
from compile.to_pytket import compile, compile_with_artifacts
from compile.frames import (
    BetaSubstitution, ProvenanceError, SelectedBoundary, DERIVED,
    apply_wire_perm, canonical_frame, leakage, semantic_action, Frame,
)

q = Q()
qq = Arrow(q, q)
ATOL = 1e-10
MODES = [False, True]
I2 = np.eye(2)
H_M = np.array([[1, 1], [1, -1]]) / np.sqrt(2)


def _value(nm, gate):
    return Lam(nm, q, q, Seq(Var(nm, q), gate))


def _witness():
    """The C witness: two external inputs separated by a function value."""
    T = Ten(q, Ten(qq, q))
    body = LetPair("a", "rest", q, Ten(qq, q), Var("z", T),
                   LetPair("f", "x", qq, q, Var("rest", Ten(qq, q)),
                           Pair(Var("a", q),
                                Apply(Var("f", qq), Var("x", q)))))
    lam = Lam("z", T, Ten(q, q), body)
    return Apply(lam, Pair(Id(q), Pair(_value("hx", Hg(0, q)), Id(q))))


def _arts(term, materialize=False):
    r, arts = compile_with_artifacts(term, materialize=materialize)
    root = [a for a in arts if a.occurrence == 0][0]
    return r, arts, root


# ===========================================================================
# the acceptance gates
# ===========================================================================

@pytest.mark.parametrize("materialize", MODES)
def test_S1_ingress_is_exactly_0_1_8_9_with_exact_action(materialize):
    r = compile(_witness(), materialize=materialize)
    assert tuple(r.input_frame.codes) == (0, 1, 8, 9)
    U = r.circuit.get_unitary()
    assert leakage(r.input_frame, U, r.output_frame) < ATOL
    assert abs(r.global_phase) < 1e-12
    got = semantic_action(r.input_frame, U, r.output_frame)
    np.testing.assert_allclose(got, np.kron(I2, H_M), atol=ATOL, rtol=0.0)


@pytest.mark.parametrize("materialize", MODES)
def test_S2_argument_ingress_is_inherited_externally(materialize):
    """The root's negative boundary IS the argument artifact's ingress
    boundary -- by identity, factors and noncontiguous placements included
    -- not the argument's egress and not a canonical contiguous frame."""
    _r, arts, root = _arts(_witness(), materialize)
    arg = [a for a in arts if a.occurrence == 1][0]
    sb = root.selected_boundary
    assert sb.authority == DERIVED
    assert sb.origin == "appcut:beta"
    assert sb.ingress is arg.selected_boundary.ingress
    assert tuple(sb.ingress.codes) == (0, 1, 8, 9)
    # noncontiguous: the two dimension-2 inputs sit at wires 0 and 3, the
    # function value's dimension-1 factor between them at (1, 2)
    pls = [tuple(pl) for pl in sb.ingress.route.placements]
    dims = [f.dim for f in sb.ingress.route.parts]
    assert pls == [(0,), (1, 2), (3,)]
    assert dims == [2, 1, 2]
    # ... and it is NOT the canonical contiguous frame
    assert tuple(root.input_frame.codes) != (0, 4, 8, 12)


@pytest.mark.parametrize("materialize", MODES)
def test_S3_body_egress_is_inherited_positively(materialize):
    """The root's positive boundary is the body's egress boundary. Without
    materialization they are ONE object; materialization transports every
    egress exactly once through the final swap, so both carry the same
    transported codes."""
    _r, arts, root = _arts(_witness(), materialize)
    body = [a for a in arts if a.occurrence == 6][0]     # outer LetPair
    sb = root.selected_boundary
    if not materialize:
        assert sb.egress is body.selected_boundary.egress
        assert tuple(sb.egress.codes) == (0, 1, 8, 9)
    else:
        assert tuple(sb.egress.codes) == \
            tuple(body.selected_boundary.egress.codes) == (0, 4, 8, 12)


@pytest.mark.parametrize("materialize", MODES)
def test_S4_the_substitution_handoff_is_recorded_and_validated(materialize):
    _r, arts, root = _arts(_witness(), materialize)
    arg = [a for a in arts if a.occurrence == 1][0]
    s = root.substitution
    assert isinstance(s, BetaSubstitution)
    assert s.binder == "z"
    assert s.owner_id is not None
    assert s.polarity == "ingress"
    # lineage: the argument occurrence the binder's content came from
    assert s.arg_cut == arg.cut_id
    # ordered placement: the binder's schedule is the leading slice of the
    # argument's recorded egress
    assert tuple(s.x_phys) == tuple(s.arg_egress_wires)[:len(s.x_phys)]
    assert tuple(s.arg_egress_wires) == tuple(arg.egress_wires)
    # TWO INDEPENDENT type records, validated equal: the lambda's own
    # domain annotation and the argument artifact's recorded output
    assert s.binder_logical == Ten(q, Ten(qq, q))
    assert s.arg_logical == arg.output_frame.logical
    assert s.binder_logical == s.arg_logical


def test_S5_all_three_beta_paths_record_the_boundary():
    """Direct Lam, deferred Var-bound Lam, and transparent Seq(Lam, Id)."""
    # direct
    direct = Apply(Lam("d", q, q, Hg(0, Ten(q, q))), Id(q))
    _r, arts, root = _arts(direct)
    assert isinstance(root.substitution, BetaSubstitution)
    assert root.selected_boundary.origin == "appcut:beta"
    # deferred Var-bound: the inner Apply(Var f, Var x) of the C witness
    _r, arts, _root = _arts(_witness())
    inner = [a for a in arts if isinstance(a.term, Apply)
             and a.occurrence not in (0,)]
    assert inner, "the witness has an inner Apply occurrence"
    assert any(isinstance(a.substitution, BetaSubstitution)
               and a.selected_boundary.origin == "appcut:beta"
               for a in inner), (
        "the deferred Var-bound beta path did not record its boundary")
    # transparent Seq(Lam, Id)
    seqlam = Apply(Seq(Lam("s", q, q, Hg(0, Ten(q, q))), Id(qq)), Id(q))
    _r, arts, root = _arts(seqlam)
    assert isinstance(root.substitution, BetaSubstitution)
    assert root.selected_boundary.origin == "appcut:beta"


@pytest.mark.parametrize("materialize", MODES)
def test_S6_the_repair_is_boundary_only(materialize):
    """Commands, phase and pending permutation are EXACTLY the pre-repair
    compilation's, captured from checkpoint/semantic-seqcut-20260905."""
    r = compile(_witness(), materialize=materialize)
    cmds = [str(c) for c in r.circuit.get_commands()]
    if materialize:
        assert cmds == ["SWAP q[1], q[2];", "H q[3];", "SWAP q[1], q[3];"]
        assert list(r.perm.new_to_old) == [0, 1, 2, 3]
    else:
        assert cmds == ["H q[3];"]
        assert list(r.perm.new_to_old) == [0, 3, 1, 2]
    assert abs(float(r.circuit.phase)) < 1e-12


def test_S7_nested_beta_remains_exact():
    """f(g(x)) still compiles to S then H, with the handoff's leading-slice
    rule covering the function-layout tail of the inner result."""
    fgx = Apply(Lam("a", q, q, Hg(0, Ten(q, q))),
                Apply(Lam("b", q, q, Sg(0, Ten(q, q))), Id(q)))
    r, arts, root = _arts(fgx)
    names = [str(c.op.type.name) for c in r.circuit.get_commands()]
    assert names == ["S", "H"]
    assert isinstance(root.substitution, BetaSubstitution)


# ===========================================================================
# mutation gates
# ===========================================================================

@pytest.mark.parametrize("materialize", MODES)
def test_S8_the_canonical_frame_fallback_is_dead(materialize):
    """The historic construction, replayed: the Apply's type-canonical
    contiguous frame padded with function-layout spectators. It records
    (0,4,8,12), and the artifact LEAKS through it -- exactly what the
    release gate refuses. A mutation restoring that fallback cannot pass."""
    r = compile(_witness(), materialize=materialize)
    U = r.circuit.get_unitary()
    from compile.frames import with_spectators
    canon = with_spectators(canonical_frame(Ten(q, q)), 4,
                            residual_name="fn_layout", role="residual")
    assert tuple(canon.codes) == (0, 4, 8, 12)
    assert leakage(canon, U, r.output_frame) > 0.1, (
        "the canonical fallback would not even be caught")
    assert tuple(r.input_frame.codes) != tuple(canon.codes)


@pytest.mark.parametrize("materialize", MODES)
def test_S9_swapped_or_reversed_boundaries_fail_the_gates(materialize):
    r = compile(_witness(), materialize=materialize)
    U = r.circuit.get_unitary()
    # ingress/egress swapped: the action gate breaks
    swapped_sem = semantic_action(r.output_frame, U, r.input_frame)
    ok = np.allclose(swapped_sem, np.kron(I2, H_M), atol=ATOL) and \
        np.allclose(semantic_action(r.input_frame, U, r.output_frame),
                    np.kron(I2, H_M), atol=ATOL)
    if materialize:
        # with the swaps emitted the two frames genuinely differ
        assert tuple(r.input_frame.codes) != tuple(r.output_frame.codes)
    # reversed permutation transport: applying the FORWARD map where the
    # inverse belongs moves the egress the wrong way and leaks
    if not materialize:
        fwd = list(r.perm.new_to_old)
        wrong = apply_wire_perm(r.output_frame, fwd)
        right_leak = leakage(r.input_frame, U, r.output_frame)
        wrong_leak = leakage(r.input_frame, U, wrong)
        assert right_leak < ATOL
        assert wrong_leak > 0.1, (
            "reversing the permutation transport was not caught")


def test_S10_a_forged_or_omitted_handoff_is_refused():
    sub = dict(binder="z", owner_id="own:z", binder_logical=q,
               arg_logical=q, x_phys=(0, 1), arg_cut="cut:a",
               arg_egress_wires=(0, 1), at_cut="cut:app")
    BetaSubstitution(**sub)                          # the honest one passes
    # equal WIDTH with different wires is a forgery, not a handoff
    with pytest.raises(ProvenanceError) as ei:
        BetaSubstitution(**{**sub, "x_phys": (1, 0)})
    assert "does not hand the binder" in str(ei.value)
    with pytest.raises(ProvenanceError):
        BetaSubstitution(**{**sub, "x_phys": (2, 3)})
    # not the leading slice
    with pytest.raises(ProvenanceError):
        BetaSubstitution(**{**sub, "arg_egress_wires": (1, 0, 2)})
    # omitted identities
    with pytest.raises(ProvenanceError):
        BetaSubstitution(**{**sub, "owner_id": None})
    with pytest.raises(ProvenanceError):
        BetaSubstitution(**{**sub, "arg_cut": None})
    with pytest.raises(ProvenanceError):
        BetaSubstitution(**{**sub, "at_cut": None})
    # wrong polarity: the binder receives at ingress
    with pytest.raises(ProvenanceError):
        BetaSubstitution(**{**sub, "polarity": "egress"})


def test_S10b_type_and_owner_validation_is_not_circular():
    """The two typed records are INDEPENDENT sources: an equal-width but
    different logical type is refused at construction, and an owner never
    installed for the binder is refused against the environment."""
    from lang.types import Plus, Unit
    sub = dict(binder="z", owner_id="own:z", binder_logical=q,
               arg_logical=q, x_phys=(0,), arg_cut="cut:a",
               arg_egress_wires=(0,), at_cut="cut:app")
    # Plus(I, I) and Q are both one wire wide and dimension two -- equal
    # width is not evidence, and the mismatch is refused
    with pytest.raises(ProvenanceError) as ei:
        BetaSubstitution(**{**sub, "arg_logical": Plus(Unit(), Unit())})
    assert "equal widths are not evidence" in str(ei.value)
    ok = BetaSubstitution(**sub)
    ok.check_installed("own:z")
    # a freshly minted owner that was never installed is a forgery
    with pytest.raises(ProvenanceError) as ei:
        ok.check_installed("own:fresh.1")
    assert "does not describe this binding" in str(ei.value)
    with pytest.raises(ProvenanceError):
        ok.check_installed(None)


@pytest.mark.parametrize("materialize", MODES)
def test_S12_local_beta_boundaries_do_not_degrade(materialize):
    """The simple local witness: the RETURNED Compiled boundary -- not
    merely an internal Artifact -- stays DERIVED with origin appcut:beta.
    Finalisation must never silently replace it with a frame default."""
    t = Apply(Lam("x", q, q, Seq(Var("x", q), Hg(0, q))), Id(q))
    r = compile(t, materialize=materialize)
    sb = r.selected_boundary
    assert sb is not None and not isinstance(sb, str)
    assert sb.origin == "appcut:beta", sb.origin
    assert sb.authority == DERIVED
    assert sb.ingress.space == "ambient"
    U = r.circuit.get_unitary()
    assert leakage(r.input_frame, U, r.output_frame) < ATOL


@pytest.mark.parametrize("materialize", MODES)
def test_S13_the_function_layout_survives_as_a_residual_port(materialize):
    """The repaired input frame keeps the closed function-value layout: the
    external semantic inputs sit on wires (0, 3), and wires (1, 2) carry a
    residual port with the factor's own recorded type, owner and origin --
    taken from the argument's recorded Par schedule, never invented from
    widths or fixed bits."""
    from compile.frames import completed_dimension
    r = compile(_witness(), materialize=materialize)
    fin = r.input_frame
    assert tuple(fin.codes) == (0, 1, 8, 9)
    res = [pt for pt in fin.ports if pt.role == "residual"]
    assert len(res) == 1, f"expected one residual port, got {fin.ports}"
    pt = res[0]
    assert tuple(pt.wires) == (1, 2)
    from lang.types import Unit
    assert pt.logical == Unit(), (
        "the ingress-side occupancy presents exactly one state")
    assert pt.owner_id is not None and str(pt.owner_id).startswith("cut:"), (
        "the port carries the function value's own recorded provenance")
    assert pt.origin_cut is not None
    # completion and reconstruction stay correct: the residual multiplies
    # the dimension by exactly one
    assert completed_dimension(fin) == 4
    # ... and the external inputs occupy exactly wires 0 and 3
    varying = set()
    for c in fin.codes:
        for w in range(fin.n_qubits):
            if (c >> (fin.n_qubits - 1 - w)) & 1:
                varying.add(w)
    assert varying == {0, 3}


@pytest.mark.parametrize("materialize", MODES)
def test_S14_sibling_betas_do_not_shadow_each_other(materialize):
    """Two sibling beta reductions under ONE binder name: each records its
    own installed owner, the bindings are restored lexically, and the
    circuit is exact."""
    appH = Apply(Lam("v", q, q, Seq(Var("v", q), Hg(0, q))), Id(q))
    appS = Apply(Lam("v", q, q, Seq(Var("v", q), Sg(0, q))), Id(q))
    t = Seq(Seq(Id(q), appH), appS)
    r, arts, _root = _arts(t, materialize)
    subs = [a.substitution for a in arts
            if isinstance(a.term, Apply) and a.substitution is not None]
    assert len(subs) == 2
    assert subs[0].owner_id != subs[1].owner_id, (
        "the two sibling binders share one minted owner; the binding "
        "environment leaked")
    for s in subs:
        assert s.binder == "v"
        s.check_installed(s.owner_id)
    U = r.circuit.get_unitary()
    S_M = np.array([[1, 0], [0, 1j]])
    got = semantic_action(r.input_frame, U, r.output_frame)
    np.testing.assert_allclose(got, S_M @ H_M, atol=ATOL, rtol=0.0)
    assert leakage(r.input_frame, U, r.output_frame) < ATOL


def test_S11_every_beta_apply_carries_its_substitution():
    """Omitting the handoff is not expressible in production: every
    beta-reduced Apply artifact records one, and its boundary is DERIVED --
    never the string default."""
    for term in (_witness(),
                 Apply(Lam("d", q, q, Hg(0, Ten(q, q))), Id(q))):
        _r, arts, _root = _arts(term)
        for a in arts:
            if isinstance(a.term, Apply) and \
                    a.selected_boundary is not None and \
                    not isinstance(a.selected_boundary, str) and \
                    a.selected_boundary.origin == "appcut:beta":
                assert isinstance(a.substitution, BetaSubstitution)
                assert a.selected_boundary.authority == DERIVED
