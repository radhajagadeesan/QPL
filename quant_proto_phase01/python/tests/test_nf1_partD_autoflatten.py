"""NF-1 Part D: the auto-flatten placement gate. TEST-ONLY -- CLASSIFICATION.

Nothing here repairs anything. This module asks one question: when a binary
PlusMap is auto-flattened into an NPlusMap, does the flattened emission still
honour the boundary transport its parent owes?

    (1) A_pre  J_i^- = K_i^-
    (2) B      K_i^- = K_i^+ G_i
    (3) A_post K_i^+ = J_i^+

Auto-flatten dissolves a branch OCCURRENCE into that branch's own branches. If
the dissolved branch needed a plan of its own -- and P provably does, that is
the content of checkpoint/closed-k1-sector-transport-20260902 -- then the plan
is never constructed, because the occurrence it belonged to no longer exists
by the time anything is emitted.

ORACLE. The expected action is built from primitives (H (+) I (+) S; I_7;
an independently compiled twist tensored with I_7). It is deliberately NOT
"whatever an explicitly written NPlusMap produces": both routes reach the same
emitter and would share the same defect, so agreeing with each other would
prove nothing.

SELECTION. Every witness proves it really took the auto-flatten route --
exactly one NPlusMap occurrence, and no PlusMapAlignPlan on the outer PlusMap.
A Strategy A or Strategy B compilation is not accepted as satisfying these
tests; the point is to gate auto-flatten specifically.
"""

import numpy as np
import pytest

from lang.types import Unit, Q, Ten, Plus
from lang.terms import (Id, PlusMap, NPlusMap, TenTerm, TwistTen, DistL,
                        H as Hg, S as Sg)
from compile.to_pytket import (compile, compile_with_artifacts, select_frames,
                               type_of, _sub_wire_to_full)
from compile.frames import semantic_action, leakage, pretty

I, q = Unit(), Q()
IA = Ten(I, q)
BIA = Ten(Plus(I, I), q)
MODES = [False, True]
ATOL = 1e-10

H_M = np.array([[1, 1], [1, -1]], complex) / np.sqrt(2)
S_M = np.diag([1, 1j]).astype(complex)


# --- witnesses -------------------------------------------------------------

def AF0_witness():
    """Simple semantic control: three gate branches, no moving boundary."""
    inner = PlusMap(q, q, Hg(0, q), Id(q))
    return PlusMap(Plus(q, q), q, inner, Sg(0, q))


def P_witness():
    """The closed k=1 witness that provably needs a post-Align of its own."""
    return PlusMap(IA, BIA, Id(IA), DistL(I, I, q))


def AF1_witness():
    """DECISIVE: auto-flatten must not discard P's occurrence transport."""
    return PlusMap(Plus(IA, BIA), I, P_witness(), Id(I))


def AF2_witness():
    """AF1 at a non-zero offset, behind a pending non-trivial permutation."""
    return TenTerm(TwistTen(q, Ten(q, q)), AF1_witness())


# --- selection proof -------------------------------------------------------

def assert_auto_flatten_selected(t, outer, where):
    """Exactly one NPlusMap occurrence, and no plan on the outer PlusMap."""
    _, arts = compile_with_artifacts(t)
    npm = [a for a in arts if isinstance(a.term, NPlusMap)]
    assert len(npm) == 1, (
        f"{where}: expected exactly one NPlusMap occurrence, got {len(npm)} "
        f"(kinds: {[type(a.term).__name__ for a in arts]})")
    outers = [a for a in arts if isinstance(a.term, PlusMap)]
    assert outers, f"{where}: the outer PlusMap never became an occurrence"
    for a in outers:
        assert a.plan is None, (
            f"{where}: a PlusMapAlignPlan exists, so this did NOT take the "
            f"auto-flatten route -- a Strategy A/B compilation does not "
            f"satisfy this gate")
    return arts


def _inclusion(codes, dim):
    J = np.zeros((dim, len(codes)), complex)
    for m, c in enumerate(codes):
        J[c, m] = 1.0
    return J


def _lift(codes, msb, n, k, sub_tw, w):
    """Branch code -> parent code through the flattened placement."""
    l2b = tuple(_sub_wire_to_full(i, sub_tw, 0, k) for i in range(w))
    out = []
    for c in codes:
        b = msb << (n - 1)
        for j in range(w):
            if (c >> (w - 1 - j)) & 1:
                b |= 1 << (n - 1 - l2b[j])
        out.append(b)
    return tuple(out)


# ---------------------------------------------------------------------------
# AF0 -- expected GREEN
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("materialize", MODES)
def test_AF0_is_exactly_H_plus_I_plus_S(materialize):
    t = AF0_witness()
    assert_auto_flatten_selected(t, t, "AF0")
    r = compile(t, materialize=materialize)
    U = r.circuit.get_unitary()
    expected = np.zeros((6, 6), complex)
    expected[0:2, 0:2] = H_M
    expected[2:4, 2:4] = np.eye(2)
    expected[4:6, 4:6] = S_M
    assert leakage(r.input_frame, U, r.output_frame) < ATOL
    assert abs(r.global_phase) < 1e-12
    np.testing.assert_allclose(
        semantic_action(r.input_frame, U, r.output_frame),
        expected, atol=ATOL, rtol=0.0)


# ---------------------------------------------------------------------------
# AF1 -- the decisive witness
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("materialize", MODES)
def test_AF1_is_exactly_identity_7(materialize):
    t = AF1_witness()
    assert_auto_flatten_selected(t, t, "AF1")
    r = compile(t, materialize=materialize)
    U = r.circuit.get_unitary()
    assert leakage(r.input_frame, U, r.output_frame) < ATOL, (
        f"AF1: leakage {leakage(r.input_frame, U, r.output_frame):.6f}")
    assert abs(r.global_phase) < 1e-12
    np.testing.assert_allclose(
        semantic_action(r.input_frame, U, r.output_frame),
        np.eye(7), atol=ATOL, rtol=0.0)


AF1_BRANCHES = (Id(IA), DistL(I, I, q), Id(I))
AF1_SUMMANDS = (IA, BIA, I)


def af1_sector_data():
    """The ACTUAL three-sector NPlusMap cut that auto-flatten selects.

    P is NOT part of the selected derivation after flattening, so P's
    two-sector grouping cannot define equation (2). The cut has three leaves.
    Placement is the closed single-leaf fast path: selector tag i in the k tag
    wires, artifact wires at (k, k+1, ...).
    """
    from compile.frames import semantic_dim
    fin, fout = select_frames(AF1_witness())
    n, k = fin.n_qubits, 2

    def regroup(frame, summands):
        out, at = [], 0
        for sm in summands:
            d = semantic_dim(sm)
            out.append(tuple(frame.codes[at:at + d]))
            at += d
        return tuple(out)

    # The parent ARTIFACT records only its two PlusMap sectors; the derivation
    # actually emitted has three. The J tuples below are the three-leaf
    # regrouping of the same code lists, which is the cut auto-flatten
    # selected.
    Jm = regroup(fin, AF1_SUMMANDS)
    Jp = regroup(fout, [type_of(b)[1] for b in AF1_BRANCHES])
    Km, Kp = [], []
    for i, br in enumerate(AF1_BRANCHES):
        bi, bo = select_frames(br)
        Km.append(_lift_leaf(bi.codes, i, n, k, bi.n_qubits))
        Kp.append(_lift_leaf(bo.codes, i, n, k, bo.n_qubits))
    return fin, fout, Jm, Jp, tuple(Km), tuple(Kp)


def _lift_leaf(codes, sector, n, k, w):
    l2b = tuple(k + j for j in range(w))
    out = []
    for c in codes:
        b = sector << (n - k)
        for j in range(w):
            if (c >> (w - 1 - j)) & 1:
                b |= 1 << (n - 1 - l2b[j])
        out.append(b)
    return tuple(out)


def test_AF1_three_sector_cut_is_pinned():
    """J^- = (0,2)|(4,5,6,7)|(8)
       K^- = K^+ = (0,2)|(4,5,6,7)|(8)
       J^+ = (0,2)|(4,6,8,10)|(12)"""
    fin, fout, Jm, Jp, Km, Kp = af1_sector_data()
    assert Jm == ((0, 2), (4, 5, 6, 7), (8,)), Jm
    assert Jp == ((0, 2), (4, 6, 8, 10), (12,)), Jp
    assert Km == ((0, 2), (4, 5, 6, 7), (8,)), Km
    assert Kp == ((0, 2), (4, 5, 6, 7), (8,)), Kp
    # the artifact still records only the TWO PlusMap sectors
    assert len(fin.sectors) == 2 and len(fout.sectors) == 2


def test_AF1_equation_1_holds_and_pre_align_is_identity():
    """A_pre J_i^- = K_i^- with A_pre = I: every branch already lands where the
    parent's ingress sector expects it."""
    _, _, Jm, _, Km, _ = af1_sector_data()
    for i in range(3):
        assert Jm[i] == Km[i], f"eq(1) sector {i}: J^-={Jm[i]} K^-={Km[i]}"


def test_AF1_composite_transport_holds_per_sector():
    """The parent equation the three combine into:

        G_parent J_i^- = J_i^+ G_i

    stated against the WHOLE emitted circuit, which now contains A_post.
    (An earlier version compared the whole circuit to K^+ G_i; that was only
    valid while no Align was emitted.)
    """
    _, _, Jm, Jp, _, _ = af1_sector_data()
    r = compile(AF1_witness(), materialize=False)
    U = r.circuit.get_unitary()
    for i, br in enumerate(AF1_BRANCHES):
        cb = compile(br, materialize=True)
        G_i = semantic_action(cb.input_frame, cb.circuit.get_unitary(),
                              cb.output_frame)
        lhs = U @ _inclusion(Jm[i], U.shape[0])
        rhs = _inclusion(Jp[i], U.shape[0]) @ G_i
        assert np.allclose(lhs, rhs, atol=ATOL, rtol=0.0), (
            f"sector {i}: G J^- != J^+ G_i, max dev "
            f"{np.abs(lhs - rhs).max():.6f}")


def test_AF1_equation_3_needs_a_real_post_align():
    """K_i^+ != J_i^+ in sectors 1 and 2, so A_post must be non-identity.

    This is the operation that was missing. It belongs to the synthetic
    NPlusMap occurrence -- not to the PlusMap that auto-flatten dissolved.
    """
    _, _, _, J, _, Kp = af1_sector_data()
    assert Kp[0] == J[0], "sector 0 was expected to already agree"
    assert Kp[1] != J[1] and Kp[2] != J[2], (
        "sectors 1 and 2 were expected to need a post-Align")
    r = compile(AF1_witness(), materialize=False, explain=True)
    assert any("A_post" in l for l in r.log), (
        "no post-Align was emitted at the NPlusMap occurrence")
    assert not any("A_pre" in l for l in r.log), (
        "a pre-Align was emitted, but equation (1) already holds")


def test_both_occurrence_cuts_are_preserved_with_the_plan_on_the_NPlusMap():
    """The outer PlusMap keeps its TWO sectors and owns no plan. The synthetic
    NPlusMap is its own occurrence, keeps THREE sectors, and owns the plan."""
    _, arts = compile_with_artifacts(AF1_witness())
    outer = [a for a in arts if isinstance(a.term, PlusMap)]
    synth = [a for a in arts if isinstance(a.term, NPlusMap)]
    assert len(outer) == 1 and len(synth) == 1
    assert outer[0].plan is None, "the outer PlusMap must not own the plan"
    assert len(outer[0].input_frame.sectors) == 2
    assert len(outer[0].output_frame.sectors) == 2
    plan = synth[0].plan
    assert plan is not None, "the synthetic NPlusMap must own the plan"
    assert len(synth[0].input_frame.sectors) == 3
    assert len(synth[0].output_frame.sectors) == 3
    assert plan.K_minus == ((0, 2), (4, 5, 6, 7), (8,)), plan.K_minus
    assert plan.K_plus == ((0, 2), (4, 5, 6, 7), (8,)), plan.K_plus
    assert [pl.local_to_block for pl in plan.placements] == [(2,), (2, 3), ()]
    # same embedding, different classification
    assert tuple(outer[0].input_frame.codes) == tuple(synth[0].input_frame.codes)
    assert tuple(outer[0].output_frame.codes) == tuple(synth[0].output_frame.codes)


# ---------------------------------------------------------------------------
# The EXPLICIT flattened term: same transport seam, now exact
# ---------------------------------------------------------------------------

def EXPLICIT_NF():
    return NPlusMap(AF1_SUMMANDS, AF1_BRANCHES)


def test_explicit_flattened_NPlusMap_frames_are_pinned():
    """Independent ingress and egress, then a common register.

    The natural widths differ -- 4 in, 3 out -- so the egress is widened and
    the pad is recorded as a truthful residual port. Selecting at the two
    natural widths and stopping there made the artifact unbuildable: Invariant
    W rejected a 4-qubit register against a 3-qubit output frame.
    """
    fi, fo = select_frames(EXPLICIT_NF())
    assert (fi.n_qubits, fo.n_qubits) == (4, 4), (fi.n_qubits, fo.n_qubits)
    assert tuple(fi.codes) == (0, 2, 4, 5, 6, 7, 8)
    assert tuple(fo.codes) == (0, 2, 4, 6, 8, 10, 12)
    assert [(p.name, p.role, p.wires) for p in fo.ports] == \
        [("ancilla", "residual", (3,))]
    # sectors survive widening, tag_values intact
    assert tuple(tuple(x.codes) for x in fo.sectors) == \
        ((0, 2), (4, 6, 8, 10), (12,))


def test_the_two_occurrence_cuts_share_one_embedding():
    """The outer PlusMap legitimately has TWO sectors; the synthetic NPlusMap
    legitimately has THREE. Different classifications of the SAME embedding --
    so the code lists must agree exactly even though the sectors do not."""
    pi, po = select_frames(AF1_witness())
    ni, no = select_frames(EXPLICIT_NF())
    assert tuple(pi.codes) == tuple(ni.codes), (tuple(pi.codes), tuple(ni.codes))
    assert tuple(po.codes) == tuple(no.codes), (tuple(po.codes), tuple(no.codes))
    assert (pi.n_qubits, po.n_qubits) == (ni.n_qubits, no.n_qubits)
    assert len(pi.sectors) == 2 and len(ni.sectors) == 3
    assert len(po.sectors) == 2 and len(no.sectors) == 3


@pytest.mark.parametrize("materialize", MODES)
def test_explicit_flattened_NPlusMap_is_exactly_identity_7(materialize):
    """Required exactly, independently of AF1.

    This term reaches the SAME transport seam as AF1. It was previously
    unbuildable for a second reason -- `_nplusmap_frames` selected ingress and
    egress at their own natural widths, so Invariant W rejected a 4-qubit
    register against a 3-qubit output frame. With width selection and the
    occurrence transport both repaired it is exact.
    """
    r = compile(EXPLICIT_NF(), materialize=materialize)
    U = r.circuit.get_unitary()
    assert leakage(r.input_frame, U, r.output_frame) < ATOL
    assert abs(r.global_phase) < 1e-12
    np.testing.assert_allclose(
        semantic_action(r.input_frame, U, r.output_frame),
        np.eye(7), atol=ATOL, rtol=0.0)


# ---------------------------------------------------------------------------
# AF2 -- non-zero offset, behind a pending non-trivial permutation
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("materialize", MODES)
def test_AF2_is_twist_tensor_identity_7(materialize):
    t = AF2_witness()
    assert_auto_flatten_selected(t, t, "AF2")
    tw = TwistTen(q, Ten(q, q))
    rt = compile(tw, materialize=True)
    A = semantic_action(rt.input_frame, rt.circuit.get_unitary(),
                        rt.output_frame)
    assert not np.allclose(A, np.eye(8), atol=1e-10), (
        "premise lost: the twist is trivial, so no perm would be pending")
    r = compile(t, materialize=materialize)
    U = r.circuit.get_unitary()
    assert leakage(r.input_frame, U, r.output_frame) < ATOL, (
        f"AF2: leakage {leakage(r.input_frame, U, r.output_frame):.6f}")
    assert abs(r.global_phase) < 1e-12
    np.testing.assert_allclose(
        semantic_action(r.input_frame, U, r.output_frame),
        np.kron(A, np.eye(7)), atol=ATOL, rtol=0.0)


# ---------------------------------------------------------------------------
# Command-bearing chronology, and a genuinely CROSSING pending permutation
# ---------------------------------------------------------------------------

def AF1c_witness():
    """AF1 with a gate on branch 0: a command-bearing block under a
    non-identity A_post, so block-then-Align is distinguishable from
    Align-then-block."""
    inner = PlusMap(IA, BIA, Hg(0, IA), DistL(I, I, q))
    return PlusMap(Plus(IA, BIA), I, inner, Id(I))


def _af1c_expected():
    e = np.eye(7, dtype=complex)
    e[0:2, 0:2] = H_M
    return e


@pytest.mark.parametrize("materialize", MODES)
def test_AF1c_command_bearing_chronology(materialize):
    t = AF1c_witness()
    assert_auto_flatten_selected(t, t, "AF1c")
    r = compile(t, materialize=materialize, explain=True)
    U = r.circuit.get_unitary()
    assert any("A_post" in l for l in r.log)
    assert len(r.circuit.get_commands()) == 6
    assert leakage(r.input_frame, U, r.output_frame) < ATOL
    assert abs(r.global_phase) < 1e-12
    np.testing.assert_allclose(
        semantic_action(r.input_frame, U, r.output_frame),
        _af1c_expected(), atol=ATOL, rtol=0.0)


@pytest.mark.parametrize("materialize", MODES)
def test_AF1c_behind_a_CROSSING_pending_permutation(materialize):
    """The twist moves the very wires the NPlusMap then occupies.

    AF2 only covers a non-zero offset with a DISJOINT pending permutation;
    this one actually crosses, so the placement has to be read through the
    running WirePerm rather than assumed.
    """
    from lang.terms import Seq
    inner_t = AF1c_witness()
    dom, _ = type_of(inner_t)
    tw = TwistTen(q, dom)
    t = Seq(tw, TenTerm(inner_t, Id(q)))

    rt = compile(tw, materialize=True)
    A = semantic_action(rt.input_frame, rt.circuit.get_unitary(),
                        rt.output_frame)
    assert not np.allclose(A, np.eye(A.shape[0]), atol=1e-10), (
        "premise lost: the twist is trivial")

    r = compile(t, materialize=materialize)
    U = r.circuit.get_unitary()
    assert leakage(r.input_frame, U, r.output_frame) < ATOL
    assert abs(r.global_phase) < 1e-12
    np.testing.assert_allclose(
        semantic_action(r.input_frame, U, r.output_frame),
        np.kron(_af1c_expected(), np.eye(2)) @ A, atol=ATOL, rtol=0.0)


# ---------------------------------------------------------------------------
# AF0 shape, single compile, forced planner failure
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("materialize", MODES)
def test_AF0_circuit_commands_are_unchanged(materialize):
    """AF0 needs no Align at all: its boundary does not move. Byte-identical
    command list, and no A_pre/A_post emitted."""
    r = compile(AF0_witness(), materialize=materialize, explain=True)
    names = [str(c).split(" ")[0] for c in r.circuit.get_commands()]
    assert names == ["X", "X", "qif", "X", "X", "X", "qif", "X"], names
    assert not any("A_pre" in l or "A_post" in l for l in r.log)


@pytest.mark.parametrize("materialize", MODES)
def test_each_NPlusMap_branch_is_compiled_exactly_once(materialize, monkeypatch):
    import compile.to_pytket as TP
    calls = []
    orig = TP._compile_branch_artifact

    def spy(branch, *, env=None, **kw):
        calls.append(type(branch).__name__)
        return orig(branch, env=env, **kw)

    monkeypatch.setattr(TP, "_compile_branch_artifact", spy)
    TP.compile(EXPLICIT_NF(), materialize=materialize)
    assert len(calls) == 3, f"expected one compile per branch, got {calls}"


@pytest.mark.parametrize("materialize", MODES)
def test_NPlusMap_plan_failure_leaves_the_parent_untouched(materialize, monkeypatch):
    import compile.to_pytket as TP
    from compile.frames import UnsupportedFrame
    from pytket.circuit import Circuit

    t = AF1c_witness()
    assert compile(t, materialize=materialize).circuit.n_qubits == 4

    monkeypatch.setattr(TP, "_lift_via_placement", lambda *a, **k: None)
    touched = []
    for meth in ("add_gate", "add_toffolibox", "X"):
        orig = getattr(Circuit, meth)

        def wrap(self, *a, _o=orig, _m=meth, **kw):
            if self.n_qubits == 4:
                touched.append(_m)
            return _o(self, *a, **kw)

        monkeypatch.setattr(Circuit, meth, wrap)

    with pytest.raises(UnsupportedFrame) as ei:
        compile(t, materialize=materialize)
    assert "align plan" in str(ei.value).lower(), str(ei.value)
    assert touched == [], f"parent circuit mutated before failing closed: {touched}"


# ---------------------------------------------------------------------------
# BranchPlacement is the EMISSION authority, not only the lift's
# ---------------------------------------------------------------------------

def test_NPlusMap_command_emission_consults_BranchPlacement_wire(monkeypatch):
    """Perturb `BranchPlacement.wire` and the emitted gate must MOVE.

    Non-vacuous by construction: `wire()` is consulted only by emission -- the
    K lift reads `local_to_block` through `_lift_via_placement`, and
    `_lift_port` indexes the tuple directly -- so if the branch command still
    landed on the old wire, emission would be using its own copy of
    `payload_base + w` instead of the plan's placement.
    """
    import compile.to_pytket as TP
    t = AF1c_witness()

    base = ";".join(str(c) for c in compile(t, materialize=False)
                    .circuit.get_commands())
    assert "H q[2]" in base, base          # local_to_block[0] == 2

    orig = TP.BranchPlacement.wire

    def shifted(self, i):
        return orig(self, i) + 1

    monkeypatch.setattr(TP.BranchPlacement, "wire", shifted)
    moved = ";".join(str(c) for c in compile(t, materialize=False)
                     .circuit.get_commands())
    assert "H q[3]" in moved, moved
    assert "H q[2]" not in moved, (
        "the branch command ignored BranchPlacement.wire")


def test_planned_NPlusMap_placements_match_the_emitted_wires():
    """The gate sits exactly where the plan says, for every branch that emits."""
    t = AF1c_witness()
    plan = _plan_for_nplusmap(t)
    r = compile(t, materialize=False)
    txt = ";".join(str(c) for c in r.circuit.get_commands())
    assert plan.placements[0].local_to_block == (2,)
    assert f"H q[{plan.placements[0].wire(0)}]" in txt, txt


def _plan_for_nplusmap(t):
    _, arts = compile_with_artifacts(t)
    plans = [a.plan for a in arts
             if a.plan is not None and isinstance(a.term, NPlusMap)]
    assert len(plans) == 1, f"expected one NPlusMap plan, got {len(plans)}"
    return plans[0]


# ---------------------------------------------------------------------------
# "Closed" means SYNTACTICALLY closed
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("materialize", MODES)
def test_unresolved_free_variable_fails_closed(materialize, monkeypatch):
    """A branch free variable that is not bound anywhere is NOT a closed
    branch. It must raise before compilation, Align emission or any parent
    mutation -- previously it was silently classified closed (because the name
    was absent from env) and compiled standalone.

    This is a fail-closed containment, not the open/context repair, which
    remains a required later phase.
    """
    from lang.terms import Var
    from compile.frames import UnsupportedFrame
    from pytket.circuit import Circuit
    import compile.to_pytket as TP

    t = NPlusMap((q, q), (Var("z", q), Hg(0, q)))

    compiled_branches = []
    orig_art = TP._compile_branch_artifact
    monkeypatch.setattr(
        TP, "_compile_branch_artifact",
        lambda br, *, env=None, **kw: (compiled_branches.append(br),
                                       orig_art(br, env=env, **kw))[1])
    touched = []
    for meth in ("add_gate", "add_toffolibox", "X"):
        o = getattr(Circuit, meth)

        def wrap(self, *a, _o=o, _m=meth, **kw):
            touched.append(_m)
            return _o(self, *a, **kw)

        monkeypatch.setattr(Circuit, meth, wrap)

    with pytest.raises(UnsupportedFrame) as ei:
        compile(t, materialize=materialize)
    msg = str(ei.value)
    assert "free variables" in msg and "unresolved" in msg, msg
    assert compiled_branches == [], "a branch was compiled before failing closed"
    assert touched == [], f"a circuit was mutated before failing closed: {touched}"


def test_a_branch_with_free_vars_in_env_is_not_rejected_as_unresolved():
    """A free variable that IS bound in env is legitimately open, not
    unresolved: the new guard must let it through to the existing open route.

    This asserts ONLY the classification, which is what changed here. It makes
    no claim that the open path is correct -- see the KNOWN-RED witness below.
    """
    from lang.terms import Var
    from compile.frames import UnsupportedFrame
    t = NPlusMap((q, q), (Var("z", q), Hg(0, q)))
    try:
        compile(t, env={"z": [2]})
    except UnsupportedFrame as e:
        assert "unresolved" not in str(e), (
            f"a branch bound in env was rejected as unresolved: {e}")

    # and with no env binding it IS unresolved
    with pytest.raises(UnsupportedFrame) as ei:
        compile(t)
    assert "unresolved" in str(ei.value)


def test_bound_open_NPlusMap_end_to_end_is_KNOWN_RED():
    """MANDATORY WITNESS for the open/context-provenance + F2 repair.

    The classification above is correct, but end-to-end compilation of a
    BOUND-open NPlusMap is still red. This pins the observed failure so it
    cannot quietly disappear or be mistaken for support:

        env {"z": [0]}  ->  RuntimeError: Multiple operation arguments
                            reference q[0]
        env {"z": [1]}  ->  the same, naming q[1]

    The context wire collides with the register the NPlusMap occupies -- the
    same overlapping-argument class as release-safety F1, which is why F1 and
    this witness belong to one repair.

    A non-overlapping binding (z at wire 2) does compile, but this phase
    established NO semantic gate for it; that it compiles is not a claim that
    it is correct.

    When the open/context path is repaired this test MUST be replaced by an
    exactness gate, not deleted.
    """
    from lang.terms import Var
    t = NPlusMap((q, q), (Var("z", q), Hg(0, q)))
    for wire in (0, 1):
        with pytest.raises(RuntimeError) as ei:
            compile(t, env={"z": [wire]})
        assert f"q[{wire}]" in str(ei.value), str(ei.value)
        assert "Multiple operation arguments" in str(ei.value), str(ei.value)
    # non-overlapping binding compiles; deliberately NOT asserted correct
    r = compile(t, env={"z": [2]})
    assert len(r.circuit.get_commands()) == 4
