"""NF-1 Part C: the intermediate-frame distinction. TEST-ONLY -- RED TABLE.

Nothing here implements anything. This module exists to demonstrate, before
any algorithm change, that a PlusMap parent needs TWO alignments against the
branch's OWN frames -- not one whole-boundary alignment between the parent's
ingress and egress.

THE THREE EQUATIONS, SECTOR BY SECTOR
-------------------------------------
Write, for sector i:

    J_i^-   parent ingress inclusion   (from the parent input frame's sector)
    J_i^+   parent egress inclusion    (from the parent output frame's sector)
    K_i^-   the branch's OWN input frame,  lifted to the parent register
    K_i^+   the branch's OWN output frame, lifted to the parent register
    G_i     the branch's semantic action, in the branch's own frames
    B       the emitted branch block, in the parent register

    (1) pre-Align     A_pre  J_i^-  =  K_i^-
    (2) branch block  B      K_i^-  =  K_i^+ G_i
    (3) post-Align    A_post K_i^+  =  J_i^+

Composing, with G_parent = A_post . B . A_pre:

    G_parent J_i^- = A_post B A_pre J_i^- = A_post B K_i^-
                   = A_post K_i^+ G_i     = J_i^+ G_i          (as required)

WHY ONE WHOLE-BOUNDARY ALIGN IS WRONG
-------------------------------------
The abandoned attempt emitted a single Align(parent_in, parent_out) after the
branch block. That silently assumes K_i^- = K_i^+, i.e. that the branch leaves
its sector exactly where it found it. Equivalently it assumes equation (2)
reads B J_i^- = J_i^- G_i.

That assumption holds for DistL in P/P0 and fails for DistR at unequal payload
widths. The two witnesses below sit on opposite sides of it:

    P0, P   K_i^+ != J_i^+   ->  post-Align MUST be non-identity
    W       K_i^+ == J_i^+   ->  post-Align MUST be identity

so no single rule about (J^-, J^+) alone can serve both. A whole-boundary
Align emits a non-identity permutation for W and therefore breaks a circuit
that is correct today: that is the mechanism behind the 248 clean -> leaking
regressions recorded in the sweep.

The lift below uses the EMITTER's placement -- tag at wires [0,k), branch
payload at [max(k,1), max(k,1)+w) -- and is asserted against the parent
sector codes rather than assumed.
"""

import numpy as np
import pytest

from lang.types import Unit, Q, Ten, Plus, width
from lang.terms import Id, PlusMap, DistL, DistR, H as Hg
from compile.to_pytket import compile, select_frames, type_of
from compile.frames import semantic_action, leakage, pretty
from compile.align import align_permutation, align_is_identity

I, q = Unit(), Q()
IA = Ten(I, q)
MODES = [False, True]
ATOL = 1e-10

H_M = np.array([[1, 1], [1, -1]], complex) / np.sqrt(2)


# --- the witnesses ---------------------------------------------------------

def W_witness():
    """Branch already realizes its own ingress -> egress move.

    DistR(Q,I,Q) : Q(x)(I(+)Q) -> (Q(x)I)(+)(Q(x)Q), whose two output summands
    have DIFFERENT payload widths. Correct today.
    """
    return PlusMap(Ten(q, Plus(I, q)), I, DistR(q, I, q), Id(I))


def P0_witness():
    return PlusMap(I, Ten(Plus(I, I), I), Id(I), DistL(I, I, I))


def P_witness():
    return PlusMap(IA, Ten(Plus(I, I), q), Id(IA), DistL(I, I, q))


Z3 = Plus(I, Plus(I, I))
A_TY = Ten(Plus(Z3, I), I)


def V_witness():
    """The MIRROR of W: a non-identity PRE-Align with an identity post-Align.

    Every other witness has J^- == K^-, so an implementation that omitted
    A_pre entirely would still pass them. V closes that hole: its parent lays
    the left summand out at (0,2,4,6) while the branch artifact's own ingress
    is (0,1,2,4), so the branch must be fed through a real pre-Align.
    """
    return PlusMap(A_TY, I, DistL(Z3, I, I), Id(I))


# --- lifting a branch frame through the emitter's placement ----------------

def lift(codes, tag_value, n_qubits, k, w):
    """Branch code -> parent code, at the placement emission actually uses.

    Big-endian: wire 0 is the MSB. The tag occupies wires [0,k) and the branch
    payload occupies [max(k,1), max(k,1)+w).

    `w` MUST be the compiled branch artifact's own frame width. Deriving it
    from `width(type_of(branch))` is wrong: for V's left branch that gives
    in=2 / out=3 while the artifact's frames are BOTH n=3, so the ingress
    would be lifted to the wrong coordinates.

    This formula is a convenience for the pre-implementation table only. It is
    NOT the oracle: every K below is also pinned against an independently
    measured tuple, and once the planner exposes its own occurrence-selected
    K+/K- the tests compare THOSE against the same pinned tuples.
    """
    base = max(k, 1)
    assert base + w <= n_qubits, (
        f"branch artifact width {w} does not fit the payload field of a "
        f"{n_qubits}-qubit parent with tag width {k}")
    return tuple((tag_value << (n_qubits - k)) | (c << (n_qubits - base - w))
                 for c in codes)


def sector_data(t, k=1):
    """(J^-, J^+, K^-, K^+) per sector, for a binary PlusMap.

    Branch widths come from the compiled ARTIFACT's frames, never from
    width(type_of(...)).
    """
    fin, fout = select_frames(t)
    n = fin.n_qubits
    out = []
    for si, (br, tv) in enumerate(((t.left, 0), (t.right, 1))):
        bi, bo = select_frames(br)
        out.append({
            "name": "LR"[si],
            "J_minus": tuple(fin.sectors[si].codes),
            "J_plus": tuple(fout.sectors[si].codes),
            "K_minus": lift(bi.codes, tv, n, k, bi.n_qubits),
            "K_plus": lift(bo.codes, tv, n, k, bo.n_qubits),
            "branch_in": tuple(bi.codes),
            "branch_out": tuple(bo.codes),
            "branch_in_n": bi.n_qubits,
            "branch_out_n": bo.n_qubits,
        })
    return fin, fout, out


# ---------------------------------------------------------------------------
# W -- pinned facts. These are GREEN today and must STAY green.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("materialize", MODES)
def test_W_pinned_parent_frames(materialize):
    r = compile(W_witness(), materialize=materialize)
    assert r.circuit.n_qubits == 4
    assert tuple(r.input_frame.codes) == (0, 2, 3, 4, 6, 7, 8)
    assert tuple(r.output_frame.codes) == (0, 2, 4, 5, 6, 7, 8)
    assert len(r.input_frame.codes) == 7, "semantic dimension is not 7"
    ins = [(s.index, tuple(s.codes), tuple(s.tag_values))
           for s in r.input_frame.sectors]
    outs = [(s.index, tuple(s.codes), tuple(s.tag_values))
            for s in r.output_frame.sectors]
    assert ins == [(0, (0, 2, 3, 4, 6, 7), (0,)), (1, (8,), (1,))], ins
    assert outs == [(0, (0, 2, 4, 5, 6, 7), (0, 1)), (1, (8,), (2,))], outs


def test_W_pinned_branch_frames():
    """The branch's OWN frames differ -- it moves its own data."""
    bi, bo = select_frames(DistR(q, I, q))
    assert tuple(bi.codes) == (0, 2, 3, 4, 6, 7)
    assert tuple(bo.codes) == (0, 2, 4, 5, 6, 7)
    assert tuple(bi.codes) != tuple(bo.codes), (
        "DistR(Q,I,Q) was expected to move its own data")


def test_W_lifted_K_frames():
    _, _, secs = sector_data(W_witness())
    L, R = secs
    assert L["K_minus"] == (0, 2, 3, 4, 6, 7), L["K_minus"]
    assert L["K_plus"] == (0, 2, 4, 5, 6, 7), L["K_plus"]
    assert R["K_minus"] == (8,) and R["K_plus"] == (8,)


@pytest.mark.parametrize("materialize", MODES)
def test_W_exact_action_phase_leakage(materialize):
    """W is exact today: the permutation 0,2,3,1,4,5,6 on 7 labels."""
    r = compile(W_witness(), materialize=materialize)
    U = r.circuit.get_unitary()
    sem = semantic_action(r.input_frame, U, r.output_frame)
    expected = np.zeros((7, 7), complex)
    for col, row in enumerate((0, 2, 3, 1, 4, 5, 6)):
        expected[row, col] = 1.0
    np.testing.assert_allclose(sem, expected, atol=ATOL, rtol=0.0)
    assert leakage(r.input_frame, U, r.output_frame) < ATOL
    assert abs(r.global_phase) < 1e-12
    assert len(r.circuit.get_commands()) == 3


# --- equations (1) and (3) for W -------------------------------------------

def test_W_pre_align_is_identity():
    for s in sector_data(W_witness())[2]:
        assert s["J_minus"] == s["K_minus"], (
            f"W sector {s['name']}: pre-Align must be identity, but "
            f"J^-={s['J_minus']} K^-={s['K_minus']}")


def test_W_post_align_is_identity():
    """K^+ == J^+, so equation (3) is satisfied by doing NOTHING."""
    for s in sector_data(W_witness())[2]:
        assert s["K_plus"] == s["J_plus"], (
            f"W sector {s['name']}: post-Align must be identity, but "
            f"K^+={s['K_plus']} J^+={s['J_plus']}")


def test_W_whole_boundary_align_would_break_it():
    """The abandoned rule, evaluated on W: it is NOT the identity.

    Emitting align(parent_in, parent_out) here would move a circuit whose
    branch has already arrived, which is exactly how W went from leakage 0 to
    leakage 1. This test records that the discarded rule is wrong on W -- it
    is the discriminator the whole-boundary attempt fails.
    """
    fin, fout, _ = sector_data(W_witness())
    assert not align_is_identity(fin, fout), (
        "premise lost: W's parent embeddings no longer differ")
    assert align_permutation(fin, fout) == (
        0, 1, 2, 4, 5, 3, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15)


# ---------------------------------------------------------------------------
# P0 and P -- the opposite side of the distinction. RED until implemented.
# ---------------------------------------------------------------------------

def test_P0_pre_align_is_identity():
    for s in sector_data(P0_witness())[2]:
        assert s["J_minus"] == s["K_minus"], (
            f"P0 sector {s['name']}: J^-={s['J_minus']} K^-={s['K_minus']}")


def test_P0_post_align_is_NOT_identity():
    """The sector that must move. Opposite conclusion to W, same rule."""
    secs = sector_data(P0_witness())[2]
    R = secs[1]
    assert R["K_plus"] == (2, 3), R["K_plus"]
    assert R["J_plus"] == (1, 2), R["J_plus"]
    assert R["K_plus"] != R["J_plus"], (
        "P0 sector R must require a non-identity post-Align")
    assert secs[0]["K_plus"] == secs[0]["J_plus"], (
        "P0 sector L was expected to need no post-Align")


def test_P_post_align_is_NOT_identity():
    for s in sector_data(P_witness())[2]:
        assert s["K_plus"] != s["J_plus"], (
            f"P sector {s['name']} must require a non-identity post-Align, "
            f"but K^+={s['K_plus']} J^+={s['J_plus']}")


def test_the_distinction_is_not_derivable_from_parent_frames_alone():
    """W and P0 BOTH have non-identity align(J^-, J^+), yet W must not move.

    This is the whole point: the parent frames alone do not determine the
    transport. Only the branch's own egress K^+ does.
    """
    for name, t in (("W", W_witness()), ("P0", P0_witness())):
        fin, fout, _ = sector_data(t)
        assert not align_is_identity(fin, fout), name
    w_moves = any(s["K_plus"] != s["J_plus"] for s in sector_data(W_witness())[2])
    p_moves = any(s["K_plus"] != s["J_plus"] for s in sector_data(P0_witness())[2])
    assert not w_moves and p_moves, (
        "the two witnesses no longer straddle the distinction")


# --- equation (3) as an acceptance gate -- RED -----------------------------

@pytest.mark.parametrize("materialize", MODES)
def test_P0_is_exact_identity(materialize):
    r = compile(P0_witness(), materialize=materialize)
    U = r.circuit.get_unitary()
    assert leakage(r.input_frame, U, r.output_frame) < ATOL
    assert abs(r.global_phase) < 1e-12, f"P0 phase {r.global_phase}"
    np.testing.assert_allclose(
        semantic_action(r.input_frame, U, r.output_frame),
        np.eye(3), atol=ATOL, rtol=0.0)


@pytest.mark.parametrize("materialize", MODES)
def test_P_is_exact_identity(materialize):
    r = compile(P_witness(), materialize=materialize)
    U = r.circuit.get_unitary()
    assert leakage(r.input_frame, U, r.output_frame) < ATOL
    assert abs(r.global_phase) < 1e-12, f"P phase {r.global_phase}"
    np.testing.assert_allclose(
        semantic_action(r.input_frame, U, r.output_frame),
        np.eye(6), atol=ATOL, rtol=0.0)


# ---------------------------------------------------------------------------
# V -- the pre-Align mirror. Independently pinned tuples.
# ---------------------------------------------------------------------------

def test_V_pinned_branch_artifact_widths():
    """The artifact's frame widths, which are NOT width(type_of(...)).

    The left branch's declared domain has width 2 and its declared codomain
    width 3, but BOTH artifact frames are 3 qubits. Lifting the ingress with
    the type width would place K^- at the wrong coordinates.
    """
    bi, bo = select_frames(DistL(Z3, I, I))
    assert (bi.n_qubits, bo.n_qubits) == (3, 3), (bi.n_qubits, bo.n_qubits)
    assert tuple(bi.codes) == (0, 1, 2, 4)
    assert tuple(bo.codes) == (0, 1, 2, 4)
    assert width(type_of(DistL(Z3, I, I))[0]) == 2, (
        "premise lost: the type width no longer differs from the artifact's")


@pytest.mark.parametrize("materialize", MODES)
def test_V_pinned_parent_frames(materialize):
    r = compile(V_witness(), materialize=materialize)
    assert r.circuit.n_qubits == 4
    assert tuple(r.input_frame.codes) == (0, 2, 4, 6, 8)
    assert tuple(r.output_frame.codes) == (0, 1, 2, 4, 8)
    assert len(r.input_frame.codes) == 5, "semantic dimension is not 5"


def test_V_pinned_sector_inclusions():
    """J^- = (0,2,4,6 | 8)   K^- = K^+ = J^+ = (0,1,2,4 | 8)"""
    _, _, secs = sector_data(V_witness())
    L, R = secs
    assert L["J_minus"] == (0, 2, 4, 6), L["J_minus"]
    assert L["K_minus"] == (0, 1, 2, 4), L["K_minus"]
    assert L["K_plus"] == (0, 1, 2, 4), L["K_plus"]
    assert L["J_plus"] == (0, 1, 2, 4), L["J_plus"]
    assert (R["J_minus"], R["K_minus"], R["K_plus"], R["J_plus"]) == \
        ((8,), (8,), (8,), (8,))


def test_V_requires_a_nonidentity_PRE_align():
    """The gap every other witness leaves open."""
    L = sector_data(V_witness())[2][0]
    assert L["J_minus"] != L["K_minus"], (
        "V must require a real pre-Align; without it A_pre could be omitted "
        "entirely and every other witness would still pass")


def test_V_post_align_is_identity():
    for s in sector_data(V_witness())[2]:
        assert s["K_plus"] == s["J_plus"], (
            f"V sector {s['name']}: post-Align must be identity, "
            f"K^+={s['K_plus']} J^+={s['J_plus']}")


def test_V_and_W_straddle_pre_and_post():
    """W needs neither Align; V needs only the pre; P/P0 need only the post.

    No single-sided implementation satisfies all three.
    """
    def needs(t):
        secs = sector_data(t)[2]
        return (any(s["J_minus"] != s["K_minus"] for s in secs),
                any(s["K_plus"] != s["J_plus"] for s in secs))
    assert needs(W_witness()) == (False, False), needs(W_witness())
    assert needs(V_witness()) == (True, False), needs(V_witness())
    assert needs(P0_witness()) == (False, True), needs(P0_witness())
    assert needs(P_witness()) == (False, True), needs(P_witness())


@pytest.mark.parametrize("materialize", MODES)
def test_V_is_exact_identity(materialize):
    r = compile(V_witness(), materialize=materialize)
    U = r.circuit.get_unitary()
    assert leakage(r.input_frame, U, r.output_frame) < ATOL
    assert abs(r.global_phase) < 1e-12
    np.testing.assert_allclose(
        semantic_action(r.input_frame, U, r.output_frame),
        np.eye(5), atol=ATOL, rtol=0.0)


# ---------------------------------------------------------------------------
# Equation (2) as a matrix statement:  B K_i^- = K_i^+ G_i
# ---------------------------------------------------------------------------

def _inclusion(codes, dim):
    J = np.zeros((dim, len(codes)), complex)
    for m, c in enumerate(codes):
        J[c, m] = 1.0
    return J


@pytest.mark.parametrize("materialize", MODES)
def test_W_equation_2_branch_block_matrix(materialize):
    """B K_i^- = K_i^+ G_i, as matrices, for both sectors of W.

    W is the witness where both Aligns are identity, so its emitted circuit
    IS the branch block B. That makes equation (2) directly checkable today,
    independently of any transport.
    """
    r = compile(W_witness(), materialize=materialize)
    B = r.circuit.get_unitary()
    dim = B.shape[0]
    _, _, secs = sector_data(W_witness())
    for s, br in zip(secs, (W_witness().left, W_witness().right)):
        bi, bo = select_frames(br)
        cb = compile(br, materialize=materialize)
        G_i = semantic_action(cb.input_frame, cb.circuit.get_unitary(),
                              cb.output_frame)
        Km = _inclusion(s["K_minus"], dim)
        Kp = _inclusion(s["K_plus"], dim)
        lhs, rhs = B @ Km, Kp @ G_i
        assert np.allclose(lhs, rhs, atol=ATOL, rtol=0.0), (
            f"W sector {s['name']}: B K^- != K^+ G_i; "
            f"max dev {np.abs(lhs - rhs).max():.6e}")


# ---------------------------------------------------------------------------
# Chronology, with a COMMAND-BEARING branch -- RED
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("materialize", MODES)
def test_command_bearing_chronology_H_plus_I4(materialize):
    """A non-identity branch block on top of a moving parent.

    An identity-branch witness cannot distinguish Transport.Branch from
    Branch.Transport. This one can: H acts on the LEFT sector only, so the
    two orders give different matrices.
    """
    t = PlusMap(IA, Ten(Plus(I, I), q), Hg(0, IA), DistL(I, I, q))
    expected = np.eye(6, dtype=complex)
    expected[0:2, 0:2] = H_M
    r = compile(t, materialize=materialize)
    U = r.circuit.get_unitary()
    assert leakage(r.input_frame, U, r.output_frame) < ATOL
    assert abs(r.global_phase) < 1e-12
    np.testing.assert_allclose(
        semantic_action(r.input_frame, U, r.output_frame),
        expected, atol=ATOL, rtol=0.0)


# ---------------------------------------------------------------------------
# The plan is the authority: compare the PLANNER's own K+/K- with the pins
# ---------------------------------------------------------------------------

def _plan_for(t):
    from compile.to_pytket import compile_with_artifacts
    # `compile` normalizes first, so the top-level PlusMap reaching `go` need
    # not be the same object; select by constructor, not identity.
    _, arts = compile_with_artifacts(t)
    plans = [a.plan for a in arts
             if a.plan is not None and isinstance(a.term, PlusMap)]
    assert len(plans) == 1, (
        f"expected exactly one plan for the PlusMap, got {len(plans)} "
        f"(artifacts: {[type(a.term).__name__ for a in arts]})")
    return plans[0]


@pytest.mark.parametrize("name,t,pinned", [
    ("W", W_witness(),
     (((0, 2, 3, 4, 6, 7), (0, 2, 4, 5, 6, 7)), ((8,), (8,)))),
    ("V", V_witness(),
     (((0, 1, 2, 4), (0, 1, 2, 4)), ((8,), (8,)))),
    ("P0", P0_witness(), (((0,), (0,)), ((2, 3), (2, 3)))),
    ("P", P_witness(), (((0, 2), (0, 2)), ((4, 5, 6, 7), (4, 5, 6, 7)))),
])
def test_planner_K_frames_match_the_pinned_tuples(name, t, pinned):
    """The PLANNER's own occurrence-selected K^-/K^+, not the test's formula.

    The lift helper at the top of this module is a convenience; this is the
    gate. If the planner and the helper ever disagree, this fails.
    """
    plan = _plan_for(t)
    got = tuple((pl.K_minus, pl.K_plus) for pl in plan.placements)
    assert got == pinned, f"{name}: planner K frames {got} != pinned {pinned}"


def test_plan_retains_typed_sectors_and_lifted_ports():
    """Typed occurrence metadata survives on the plan, and is examined.

    F_pre/F_mid stay code-only Align operands with NO ports: a parent residual
    port must never be copied onto a coordinate a branch has made live, which
    is exactly what V does.
    """
    from compile.frames import semantic_dim
    plan = _plan_for(V_witness())
    assert len(plan.placements) == 2
    assert plan.F_pre.ports == () and plan.F_mid.ports == (), (
        "Align operands must not claim ports")
    # one placement object: the wire map is derived from it, not recomputed
    assert plan.payload_base == 1
    assert plan.placements[0].wire(0) == plan.payload_base

    # --- the lifted ports themselves ---
    L = plan.placements[0]
    summ = [pt for pt in L.ports_in if pt.name == "summand"]
    assert len(summ) == 1, [pt.name for pt in L.ports_in]
    pt = summ[0]
    assert pt.logical == Plus(Z3, I), pretty(pt.logical)
    assert pt.role == "payload", pt.role
    # wires shifted by payload_base; INNER sector tag values untouched, since
    # the outer sector is supplied by BranchPlacement.tag_value.
    assert pt.by_sector == ((0, (2, 3)), (1, ())), pt.by_sector
    assert L.tag_value == 0
    tag = [q_ for q_ in L.ports_in if q_.name == "tag"]
    assert tag and tag[0].wires == (1,), tag[0].wires if tag else None

    # --- K sizes agree with the typed sectors they describe ---
    fin, fout = select_frames(V_witness())
    for i, pl in enumerate(plan.placements):
        assert len(pl.K_minus) == semantic_dim(pl.logical_in), (
            f"sector {i}: |K^-|={len(pl.K_minus)} but "
            f"dim({pretty(pl.logical_in)})={semantic_dim(pl.logical_in)}")
        assert len(pl.K_plus) == semantic_dim(pl.logical_out), (
            f"sector {i}: |K^+|={len(pl.K_plus)} but "
            f"dim({pretty(pl.logical_out)})={semantic_dim(pl.logical_out)}")
        assert pl.logical_in == fin.sectors[i].logical, (
            f"sector {i} ingress type disagrees with the parent sector")
        assert pl.logical_out == fout.sectors[i].logical, (
            f"sector {i} egress type disagrees with the parent sector")
    assert plan.placements[0].logical_in == A_TY


# ---------------------------------------------------------------------------
# Guard 1 -- each branch is compiled EXACTLY once
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("materialize", MODES)
def test_each_branch_is_compiled_exactly_once(materialize, monkeypatch):
    import compile.to_pytket as TP
    calls = []
    orig = TP._compile_branch_artifact

    def spy(branch, *, env=None):
        calls.append(branch)
        return orig(branch, env=env)

    monkeypatch.setattr(TP, "_compile_branch_artifact", spy)
    TP.compile(V_witness(), materialize=materialize)
    assert len(calls) == 2, (
        f"expected one compile per branch, got {len(calls)}: "
        f"{[type(c).__name__ for c in calls]}")
    assert {id(c) for c in calls} == {id(V_witness().left), id(V_witness().right)} or \
        [type(c).__name__ for c in calls] == ["DistL", "Id"]


# ---------------------------------------------------------------------------
# Guard 2 -- a plan that cannot be built FAILS CLOSED, before emission
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("materialize", MODES)
def test_plan_failure_raises_before_mutating_the_parent(materialize, monkeypatch):
    """Force _lift_codes to fail and prove nothing reached the parent circuit.

    The witness has a command-bearing branch, so if the parent were emitted at
    all a 3-qubit circuit would receive operations. None may.
    """
    import compile.to_pytket as TP
    from compile.frames import UnsupportedFrame
    from pytket.circuit import Circuit

    t = PlusMap(IA, Ten(Plus(I, I), q), Hg(0, IA), DistL(I, I, q))
    assert compile(t, materialize=materialize).circuit.n_qubits == 3

    # Patch the symbol the plan ACTUALLY calls. (It was `_lift_codes` before
    # the placement tuple became the single authority; patching a symbol the
    # planner no longer consults would make this test vacuous.)
    monkeypatch.setattr(TP, "_lift_via_placement", lambda *a, **k: None)

    touched = []
    for meth in ("add_gate", "add_toffolibox", "X"):
        orig = getattr(Circuit, meth)

        def wrap(self, *a, _o=orig, _m=meth, **kw):
            if self.n_qubits == 3:
                touched.append(_m)
            return _o(self, *a, **kw)

        monkeypatch.setattr(Circuit, meth, wrap)

    with pytest.raises(UnsupportedFrame) as ei:
        compile(t, materialize=materialize)
    assert "align plan" in str(ei.value).lower(), str(ei.value)
    assert touched == [], (
        f"parent circuit was mutated before failing closed: {touched}")


# ---------------------------------------------------------------------------
# Guards 3 and 4 -- V at a nonzero offset, and after a pending wire perm
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("materialize", MODES)
def test_V_at_a_nonzero_tensor_offset(materialize):
    from lang.terms import TenTerm
    t = TenTerm(Id(q), V_witness())
    r = compile(t, materialize=materialize)
    U = r.circuit.get_unitary()
    assert leakage(r.input_frame, U, r.output_frame) < ATOL
    assert abs(r.global_phase) < 1e-12
    np.testing.assert_allclose(
        semantic_action(r.input_frame, U, r.output_frame),
        np.eye(10), atol=ATOL, rtol=0.0)


@pytest.mark.parametrize("materialize", MODES)
def test_V_after_a_pending_nontrivial_wire_permutation(materialize):
    """A twist on the left leaves a non-identity WirePerm pending when V is
    emitted, so V's placement must be read through it."""
    from lang.terms import TenTerm, TwistTen
    tw = TwistTen(q, Ten(q, q))
    t = TenTerm(tw, V_witness())

    r_tw = compile(tw, materialize=True)
    A = semantic_action(r_tw.input_frame, r_tw.circuit.get_unitary(),
                        r_tw.output_frame)
    assert not np.allclose(A, np.eye(8), atol=1e-10), (
        "premise lost: the twist is trivial, so no perm would be pending")

    r = compile(t, materialize=materialize)
    U = r.circuit.get_unitary()
    assert leakage(r.input_frame, U, r.output_frame) < ATOL
    np.testing.assert_allclose(
        semantic_action(r.input_frame, U, r.output_frame),
        np.kron(A, np.eye(5)), atol=ATOL, rtol=0.0)


# ---------------------------------------------------------------------------
# Strategy A: local_to_block is the placement authority
# ---------------------------------------------------------------------------

def Q_witness():
    """Strategy A (k=2). Its right branch is itself a sum, so that branch's
    inner tag lives in the PARENT's tag register."""
    from lang.terms import UndistL
    return PlusMap(IA, Plus(IA, IA), Id(IA), UndistL(I, I, q))


def test_strategy_A_right_placement_is_1_2_not_2_3():
    """Q's right branch maps branch wires 0,1 to parent-local wires 1,2.

    `payload_base + i` would say (2, 3): wrong, because wire 0 of that branch
    is its inner TAG bit, which sits at k-1 inside the parent's tag register,
    not at k. This is exactly the case where a second copy of the placement
    formula could drift from the first without any circuit changing shape.
    """
    plan = _plan_for(Q_witness())
    right = plan.placements[1]
    assert right.local_to_block == (1, 2), right.local_to_block
    assert (right.wire(0), right.wire(1)) == (1, 2)
    assert right.local_to_block != (2, 3), "the payload_base+i answer is wrong here"
    assert plan.placements[0].local_to_block == (2,), plan.placements[0].local_to_block


def test_strategy_A_wire_reads_local_to_block():
    """BranchPlacement.wire is a lookup, not a recomputation."""
    for t in (Q_witness(), V_witness(), P0_witness(), W_witness()):
        plan = _plan_for(t)
        for pl in plan.placements:
            assert tuple(pl.wire(i) for i in range(len(pl.local_to_block))) \
                == pl.local_to_block


def test_strategy_A_K_frames_and_exactness():
    """Q: pre-Align identity, post-Align non-identity -- P's mirror."""
    from compile.frames import semantic_dim
    plan = _plan_for(Q_witness())
    fin, fout = select_frames(Q_witness())
    assert plan.K_minus == ((0, 1), (2, 3, 4, 5)), plan.K_minus
    assert plan.K_plus == ((0, 1), (2, 3, 4, 5)), plan.K_plus
    assert tuple(tuple(s.codes) for s in fin.sectors) == ((0, 1), (2, 3, 4, 5))
    assert tuple(tuple(s.codes) for s in fout.sectors) == ((0, 2), (4, 5, 6, 7))
    for i, pl in enumerate(plan.placements):
        assert len(pl.K_minus) == semantic_dim(pl.logical_in)
        assert len(pl.K_plus) == semantic_dim(pl.logical_out)


@pytest.mark.parametrize("materialize", MODES)
def test_Q_is_exact_identity(materialize):
    r = compile(Q_witness(), materialize=materialize)
    U = r.circuit.get_unitary()
    assert leakage(r.input_frame, U, r.output_frame) < ATOL
    assert abs(r.global_phase) < 1e-12
    np.testing.assert_allclose(
        semantic_action(r.input_frame, U, r.output_frame),
        np.eye(6), atol=ATOL, rtol=0.0)
