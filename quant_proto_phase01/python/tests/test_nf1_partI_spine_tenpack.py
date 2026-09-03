"""NF-1 Part I: accumulated variable spines, Par, TenPack and Tensor Splice.

The four clauses this module pins, and nothing wider:

 1. A variable spine ACCUMULATES every operand boundary and retains exactly
    one final result yank:

        B_j^+-  =  (r_j^+-)^-1 [ S_1^+- (x) ... (x) S_j^+- (x) Y_Tj^+- ]
        action  =  U_R1 (x) ... (x) U_Rj (x) yank_Tj

    so each successive Apply keeps its head's operand factors and replaces
    ONLY the head's terminal residual Y_{A-oB} with its own Y_B.

 2. Emit(Pair(R1,R2)) = Par(Emit(R1), Emit(R2)).

 3. TenPack is gate-free and polarity-specific:
        p^+- |-> p^+- theta^+-,   r_p^+- = r_x^+- followed by r_y^+-.

 4. Emit(LetPair(R,N)) = Splice_{A(x)B}(Emit(R), TenPack_N(Emit(N))).

THE TRAP. In ctrl_ho's right branch the head is the curried spine `f h y`.
Its inner application has boundary S_h (x) Y_Endo, dimension 16. The required
OUTER boundary is S_h (x) S_y (x) Y_Q, also dimension 16. The two are
different charts with different terminal residual types, and the matching
dimension is an accident. Nothing here may select a chart by dimension,
by "outermost" or "largest", by occurrence number, by frame width, by origin
string, by syntax depth or by which bits vary.

This is a SELECTED-BOUNDARY METADATA phase. No emitted command, phase,
allocation or Frame changes; H11 stays red and the open-occurrence
Complete/Block consumption is a later phase.
"""

import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(__file__))

from lang.types import Q, Ten, Arrow, Unit, Plus
from lang.terms import (LetPair, Apply, Var, Id, Seq, Pair, TenTerm,
                        H as Hg, S as Sg)
import compile.to_pytket as TP
from compile.to_pytket import compile, compile_with_artifacts
from compile.frames import (semantic_action, leakage, ProvenanceError,
                            ChartFactor, SelectedBoundary, TenPackSchedule,
                            par_then_repart, scatter_repart)
from typing_.check import TypeCheckError

q = Q()
endo = Arrow(q, q)
MODES = [False, True]
ATOL = 1e-10
H_M = np.array([[1, 1], [1, -1]], complex) / np.sqrt(2)
I2 = np.eye(2, dtype=complex)


# ---------------------------------------------------------------------------
# Witnesses
# ---------------------------------------------------------------------------

F_END = Arrow(endo, endo)
D_CURRIED = Ten(F_END, Ten(endo, q))


def curried_spine():
    """let (f,rest)=Id in let (h,y)=rest in f h y

    The head of the outer application is itself an application, so the outer
    boundary must ACCUMULATE S_h.
    """
    return LetPair("f", "rest", F_END, Ten(endo, q), Id(D_CURRIED),
                   LetPair("h", "y", endo, q, Var("rest", Ten(endo, q)),
                           Apply(Apply(Var("f", F_END), Var("h", endo)),
                                 Var("y", q))))


A2 = Ten(q, q)
F_MULTI = Arrow(A2, Arrow(q, q))
D_MULTI = Ten(F_MULTI, Ten(A2, q))
U_A = np.kron(H_M, I2)          # H on wire 0 of A2 = Q (x) Q
U_B = H_M


def multi_spine():
    """let (f,rest)=Id in let (a,b)=rest in f (a;H) (b;H)

    Two operands of UNEQUAL dimension (4 and 2) with nontrivial actions, so
    S_a (x) S_b (x) Y differs from S_b (x) S_a (x) Y.
    """
    return LetPair("f", "rest", F_MULTI, Ten(A2, q), Id(D_MULTI),
                   LetPair("a", "b", A2, q, Var("rest", Ten(A2, q)),
                           Apply(Apply(Var("f", F_MULTI),
                                       Seq(Var("a", A2), Hg(0, A2))),
                                 Seq(Var("b", q), Hg(0, q)))))


def simple_spine():
    """let (h,y)=Id in h y"""
    return LetPair("h", "y", endo, q, Id(Ten(endo, q)),
                   Apply(Var("h", endo), Var("y", q)))


def pair_yank():
    """let (x,y)=Id in Pair(x,y) -- the whole-port tensor yank."""
    return LetPair("x", "y", q, q, Id(Ten(q, q)),
                   Pair(Var("x", q), Var("y", q)))


def appcuts(arts):
    return [a for a in arts if a.selected_boundary is not None
            and a.selected_boundary.origin == "appcut"]


def outermost_spine(arts):
    """The application whose boundary accumulates the MOST factors.

    A test-side convenience for locating the witness; production never
    searches like this, which is exactly what M11 checks.
    """
    cuts = appcuts(arts)
    return max(cuts, key=lambda a: len(a.selected_boundary.ingress.route.parts))


def framed(term, materialize, pick=None):
    r, arts = compile_with_artifacts(term, materialize=materialize)
    a = (pick or outermost_spine)(arts)
    sb = a.selected_boundary
    U = r.circuit.get_unitary()
    return r, a, sb, U, semantic_action(sb.ingress, U, sb.egress)


def assert_exact(term, materialize, want, where, pick=None):
    r, a, sb, U, sem = framed(term, materialize, pick)
    lk = leakage(sb.ingress, U, sb.egress)
    assert lk < ATOL, f"{where}: leakage {lk:.3e}"
    assert abs(r.circuit.phase) < 1e-12, f"{where}: phase {r.circuit.phase}"
    assert sem.shape == want.shape, f"{where}: {sem.shape} vs {want.shape}"
    np.testing.assert_allclose(sem, want, atol=ATOL, rtol=0.0)
    sb.ingress.validate_joint()
    sb.egress.validate_joint()
    return r, a, sb


# ===========================================================================
# 1. The spine accumulates
# ===========================================================================

@pytest.mark.parametrize("materialize", MODES)
def test_I1_curried_spine_accumulates_the_preceding_operand(materialize):
    """f h y must select S_h (x) S_y (x) Y_Q, not S_y (x) Y_Q."""
    _, arts = compile_with_artifacts(curried_spine(), materialize=materialize)
    cuts = appcuts(arts)
    assert len(cuts) == 2, f"expected two applications, got {len(cuts)}"
    outer = outermost_spine(arts)
    inner = min(cuts, key=lambda a: len(a.selected_boundary.ingress.route.parts))

    for side in ("ingress", "egress"):
        rt = getattr(outer.selected_boundary, side).route
        assert rt.is_spine(), f"{side}: the outer boundary is not a spine"
        assert len(rt.parts) == 3, (
            f"{side}: {len(rt.parts)} factors "
            f"{[f.name for f in rt.parts]}; the head's operand factor was "
            f"discarded instead of accumulated")
        ops = rt.operands
        assert [f.dim for f in ops] == [4, 2], (
            f"{side}: operand dims {[f.dim for f in ops]}, want [4, 2] "
            f"(S_h then S_y, in application order)")
        assert rt.residual.dim == 2 and rt.residual.logical == q, (
            f"{side}: the terminal residual is "
            f"{rt.residual.logical}, want Q -- the head's Y_Endo must be "
            f"REPLACED, not kept")
    assert outer.selected_boundary.ingress.dim == 16

    # The inner application is a DIFFERENT chart of the SAME dimension.
    irt = inner.selected_boundary.ingress.route
    assert inner.selected_boundary.ingress.dim == 16
    assert len(irt.parts) == 2 and irt.residual.logical == endo, (
        "the inner residual must still be Y_Endo")


def test_I2_inner_and_outer_charts_are_not_interchangeable():
    """Both are dimension 16. Dimension is not identity."""
    _, arts = compile_with_artifacts(curried_spine(), materialize=False)
    cuts = appcuts(arts)
    inner = min(cuts, key=lambda a: len(a.selected_boundary.ingress.route.parts))
    outer = outermost_spine(arts)
    i, o = inner.selected_boundary.ingress, outer.selected_boundary.ingress
    assert i.dim == o.dim == 16, "this test needs the dimensions to collide"
    assert i.codes != o.codes, "the two charts must not coincide"
    assert i.route.residual.logical != o.route.residual.logical, (
        "the terminal residual TYPE is what separates them: Endo vs Q")
    assert len(i.route.parts) != len(o.route.parts)


@pytest.mark.parametrize("materialize", MODES)
def test_I3_multi_argument_spine_is_order_discriminating(materialize):
    """Unequal operand dimensions and nontrivial actions, so
    S_a (x) S_b (x) Y differs from S_b (x) S_a (x) Y."""
    want = np.kron(U_A, np.kron(U_B, I2))
    swapped = np.kron(U_B, np.kron(U_A, I2))
    assert not np.allclose(want, swapped, atol=1e-12), (
        "the witness does not discriminate operand order")
    _, a, sb = assert_exact(multi_spine(), materialize, want, "multi-spine")
    rt = sb.ingress.route
    assert [f.dim for f in rt.operands] == [4, 2]
    assert rt.residual.dim == 2 and rt.residual.role == "residual"


@pytest.mark.parametrize("materialize", MODES)
def test_I4_simple_spine_still_exact(materialize):
    """One operand: S_y (x) Y_Q, unchanged by the accumulation rule."""
    _, a, sb = assert_exact(simple_spine(), materialize,
                            np.kron(I2, I2), "simple spine")
    assert sb.ingress.dim == 4
    assert len(sb.ingress.route.parts) == 2


# ===========================================================================
# 2. Pair is Par
# ===========================================================================

def pair_action_witness():
    """let (x,y)=Id in Pair(x;H, y;S) -- an order-discriminating action."""
    return LetPair("x", "y", q, q, Id(Ten(q, q)),
                   Pair(Seq(Var("x", q), Hg(0, q)),
                        Seq(Var("y", q), Sg(0, q))))


S_M = np.diag([1.0 + 0j, 1j])


@pytest.mark.parametrize("materialize", MODES)
def test_I5_pair_selected_boundary_is_par_of_its_children(materialize):
    r, arts = compile_with_artifacts(pair_action_witness(),
                                     materialize=materialize)
    pairs = [a for a in arts if a.selected_boundary.origin == "par"]
    assert len(pairs) == 1
    sb = pairs[0].selected_boundary
    U = r.circuit.get_unitary()
    want = np.kron(H_M, S_M)
    assert not np.allclose(want, np.kron(S_M, H_M), atol=1e-12), (
        "the witness does not discriminate factor order")
    np.testing.assert_allclose(
        semantic_action(sb.ingress, U, sb.egress), want, atol=ATOL, rtol=0.0)
    assert leakage(sb.ingress, U, sb.egress) < ATOL
    assert abs(r.circuit.phase) < 1e-12
    assert sb.ingress.dim == sb.egress.dim == 4
    assert sb.ingress.validate_joint() and sb.egress.validate_joint()


def test_I6_pair_factor_order_is_fst_then_snd():
    """Reversing the recorded order builds a different chart."""
    _, arts = compile_with_artifacts(pair_action_witness(), materialize=False)
    sb = [a for a in arts if a.selected_boundary.origin == "par"][0]\
        .selected_boundary
    rt = sb.ingress.route
    assert len(rt.parts) == 2
    rep, places = scatter_repart(tuple(reversed(rt.placements)), rt.n_qubits)
    reversed_chart = par_then_repart(tuple(reversed(rt.parts)), rep,
                                     rt.n_qubits, "reversed",
                                     placements=places, kind="scatter")
    assert reversed_chart.codes != sb.ingress.codes, (
        "fst/snd order is not observable in the Par chart")


def test_I7_two_child_local_wire_zero_addresses_stay_distinct():
    """Both children may address their own local wire 0."""
    a = ChartFactor(name="fst", owner="cut:a", n_qubits=1, codes=(0, 1))
    b = ChartFactor(name="snd", owner="cut:b", n_qubits=1, codes=(0, 1),
                    role="residual", logical=q)
    assert a.codes == b.codes and a.n_qubits == b.n_qubits
    rep, places = scatter_repart(((1,), (2,)), 3)
    ch = par_then_repart((a, b), rep, 3, "par", placements=places,
                         kind="scatter")
    assert ch.dim == 4 and len(set(ch.codes)) == 4
    assert [ch.decode(c) for c in ch.codes] == [(0, 0), (0, 1), (1, 0), (1, 1)]


def test_I8_unit_child_is_a_real_dimension_one_factor():
    """Unit must be KEPT. 1 x 4 and 4 are the same number, not the same
    chart: dropping the factor loses its identity and provenance."""
    t = LetPair("x", "y", Unit(), q, Id(Ten(Unit(), q)),
                Pair(Var("x", Unit()), Var("y", q)))
    _, arts = compile_with_artifacts(t, materialize=False)
    sb = [a for a in arts if a.selected_boundary.origin == "par"][0]\
        .selected_boundary
    dims = [f.dim for f in sb.ingress.route.parts]
    assert dims == [1, 2], f"factor dims {dims}; the Unit factor was dropped"
    assert sb.ingress.dim == 2


@pytest.mark.parametrize("materialize", MODES)
def test_I9_pair_children_are_the_exact_artifacts_emission_used(materialize):
    """The Par consumes the two Artifact objects go() returned -- identified
    by their compile-scoped cut ids, not recompiled."""
    _, arts = compile_with_artifacts(pair_action_witness(),
                                     materialize=materialize)
    par = [a for a in arts if a.selected_boundary.origin == "par"][0]
    owners = {f.owner for f in par.selected_boundary.ingress.route.parts}
    cuts = {a.cut_id for a in arts}
    assert owners <= cuts, (
        f"Par factor owners {owners} are not cut ids of artifacts this "
        f"compilation produced; a child was rebuilt rather than consumed")
    assert all(o is not None for o in owners)


# ===========================================================================
# 3. TenPack
# ===========================================================================

def test_I10_tenpack_records_four_schedules_x_before_y():
    r = compile(curried_spine(), materialize=False)
    sched = r.selected_boundary.packing
    assert isinstance(sched, TenPackSchedule), "no TenPack schedule recorded"
    for side in ("ingress", "egress"):
        r_p = sched.check(side, r.circuit.n_qubits)
        rx = sched.r_x_in if side == "ingress" else sched.r_x_out
        assert r_p[:len(rx)] == tuple(rx), f"{side}: x does not precede y"


def test_I11_the_two_polarities_are_recorded_independently():
    """r_p^- and r_p^+ are read at their own moments. On this witness they
    differ, so using one for the other is observable."""
    r = compile(simple_spine(), materialize=False)
    sched = r.selected_boundary.packing
    assert sched.r_p("ingress") != sched.r_p("egress"), (
        f"both polarities gave {sched.r_p('ingress')}; this witness cannot "
        f"then distinguish a reused schedule")


@pytest.mark.parametrize("bad,msg", [
    (dict(r_x_in=(0, 0), r_y_in=(2,)), "not\n            injective"),
    (dict(r_x_in=(0, 1), r_y_in=(1,)), "injective"),
    (dict(r_x_in=(0, 99), r_y_in=(2,)), "outside"),
])
def test_I12_bad_binder_schedules_raise(bad, msg):
    base = dict(r_x_in=(0, 1), r_y_in=(2,), r_x_out=(0, 1), r_y_out=(2,))
    base.update(bad)
    with pytest.raises(ProvenanceError):
        TenPackSchedule(**base).check("ingress", 3)


def test_I13_the_binder_schedule_is_matched_against_the_producer_port():
    """x-before-y is enforced where it is OBSERVABLE.

    Inside TenPackSchedule the order cannot be checked: r_p is built as
    r_x ++ r_y, so comparing it with r_x is a tautology. What makes the
    order real is the Splice: r_p^- must equal the producer's own recorded
    A(x)B port placement, which a reversed schedule fails (mutation M8).
    """
    for mk in (simple_spine, pair_yank, curried_spine):
        _, arts = compile_with_artifacts(mk(), materialize=False)
        roots = [a for a in arts
                 if a.selected_boundary.origin == "letpair:splice"]
        assert roots
        for lp in roots:
            producer = next(a for a in arts if a.term is lp.term.pair)
            assert lp.selected_boundary.packing.r_p("ingress") == \
                tuple(producer.egress_wires), (
                f"{mk.__name__}: the binder schedule and the producer's "
                f"handed-over port are not the same resource in the same "
                f"order")


def test_I14_complementary_ranges_are_inherited():
    """Every wire is either in the binder schedule or in its complement."""
    r = compile(curried_spine(), materialize=False)
    sched = r.selected_boundary.packing
    n = r.circuit.n_qubits
    for side in ("ingress", "egress"):
        cover = set(sched.r_p(side)) | set(sched.complement(side))
        assert cover == set(range(n)), (
            f"{side}: {sorted(cover)} does not cover the {n}-wire register; "
            f"a complementary range was dropped")


# ===========================================================================
# 4. LetPair is a Splice, not a copy
# ===========================================================================

@pytest.mark.parametrize("materialize", MODES)
def test_I15_letpair_root_is_a_splice(materialize):
    for mk in (simple_spine, pair_yank, curried_spine):
        r = compile(mk(), materialize=materialize)
        sb = r.selected_boundary
        assert sb.origin == "letpair:splice", (
            f"{mk.__name__}: root origin {sb.origin!r}; the root must come "
            f"from Splice(pair, TenPack(body)), not from copying the body")
        assert sb.packing is not None, (
            f"{mk.__name__}: the root records no TenPack schedule, so the "
            f"producer was never matched")


@pytest.mark.parametrize("materialize", MODES)
def test_I16_tensor_yank_producers_are_exact(materialize):
    """let (x,y)=Id in Pair(x,y) and let (h,y)=Id in h y."""
    for mk, dim in ((pair_yank, 4), (simple_spine, 4)):
        r = compile(mk(), materialize=materialize)
        sb = r.selected_boundary
        U = r.circuit.get_unitary()
        assert sb.ingress.dim == sb.egress.dim == dim
        assert leakage(sb.ingress, U, sb.egress) < ATOL
        assert abs(r.global_phase) < 1e-12
        np.testing.assert_allclose(
            semantic_action(sb.ingress, U, sb.egress), np.eye(dim),
            atol=ATOL, rtol=0.0)


def test_I17_a_routed_var_producer_is_not_ignored():
    """The nested LetPair's producer is a Var that ROUTES its wires. The
    Splice matches against the producer's own recorded egress placement, so
    the routing is honoured rather than assumed to be the slot."""
    _, arts = compile_with_artifacts(curried_spine(), materialize=False)
    lps = [a for a in arts if a.selected_boundary.origin == "letpair:splice"]
    assert len(lps) == 2
    inner = min(lps, key=lambda a: a.occurrence
                if a.occurrence != 0 else 10 ** 9)
    prod = [a for a in arts if isinstance(a.term, Var)
            and a.cut_id is not None]
    assert prod, "expected a Var producer"
    # the recorded schedule IS the producer's recorded egress placement
    sched = inner.selected_boundary.packing
    assert sched is not None
    assert len(sched.r_p("ingress")) == len(set(sched.r_p("ingress")))


# ===========================================================================
# 5. ctrl_ho branch roots -- the authoritative pins for the next phase
# ===========================================================================

CTRL_HO_ING_CODES = (0, 1, 16, 17, 32, 33, 48, 49,
                     64, 65, 80, 81, 96, 97, 112, 113)
CTRL_HO_EGR_CODES = (0, 64, 1, 65, 2, 66, 3, 67,
                     4, 68, 5, 69, 6, 70, 7, 71)


def _ctrl_ho_branch_roots(materialize):
    """Every prepared branch's ROOT selected boundary, in preparation order.

    Read by intercepting branch preparation, which is where the next phase
    will consume them -- not by searching a global artifact list.
    """
    from test_nf1_beta_tensor import _fixture
    seen = []
    orig = TP._compile_branch_artifact

    def spy(branch, *, env=None, scope=None):
        a = orig(branch, env=env, scope=scope)
        seen.append((a, env is not None))
        return a

    TP._compile_branch_artifact = spy
    try:
        try:
            compile(_fixture("ctrl_ho_closed_plus_map"),
                    materialize=materialize)
        except Exception:
            pass          # the open placement is the NEXT phase; H11 stays red
    finally:
        TP._compile_branch_artifact = orig
    return seen


@pytest.mark.parametrize("materialize", MODES)
def test_I18_ctrl_ho_branch_roots_are_four_and_sixteen(materialize):
    seen = _ctrl_ho_branch_roots(materialize)
    assert len(seen) == 2, f"expected two prepared branches, got {len(seen)}"
    closed = [a for a, has_ctx in seen if not has_ctx]
    open_ = [a for a, has_ctx in seen if has_ctx]
    assert len(closed) == 1 and len(open_) == 1
    u0, u1 = closed[0], open_[0]

    for a, dim in ((u0, 4), (u1, 16)):
        sb = a.selected_boundary
        assert sb.origin == "letpair:splice"
        assert sb.ingress.dim == dim and sb.egress.dim == dim, (
            f"branch root {sb.ingress.dim}/{sb.egress.dim}, want {dim}")
        U = a.circuit.get_unitary()
        assert leakage(sb.ingress, U, sb.egress) < ATOL
        assert abs(a.phase) < 1e-12
        np.testing.assert_allclose(
            semantic_action(sb.ingress, U, sb.egress), np.eye(dim),
            atol=ATOL, rtol=0.0)
        assert sb.ingress.validate_joint() and sb.egress.validate_joint()


@pytest.mark.parametrize("materialize", MODES)
def test_I19_ctrl_ho_right_root_is_the_complete_outer_spine(materialize):
    """S_h (x) S_y (x) Y_Q -- NOT the inner S_h (x) Y_Endo chart of the same
    dimension. This is the anti-heuristic guard: the right branch contains
    two applications and only the accumulated one is correct."""
    seen = _ctrl_ho_branch_roots(materialize)
    u1 = [a for a, has_ctx in seen if has_ctx][0]
    sb = u1.selected_boundary
    for side, ch, want_pl in (
            ("ingress", sb.ingress, ((), (0, 1), (2,), (6,))),
            ("egress", sb.egress, ((), (4, 5), (6,), (0,)))):
        rt = ch.route
        assert rt.is_spine(), f"{side}: not a canonical spine"
        assert [f.dim for f in rt.parts] == [1, 4, 2, 2], (
            f"{side}: factor dims {[f.dim for f in rt.parts]}, want "
            f"[1, 4, 2, 2] = Unit (x) S_h (x) S_y (x) Y_Q")
        assert rt.residual.logical == q, (
            f"{side}: terminal residual is {rt.residual.logical}; the inner "
            f"chart's Y_Endo must have been replaced")
        assert rt.placements == want_pl, (
            f"{side}: placements {rt.placements}, want {want_pl}")
    assert sb.ingress.codes == CTRL_HO_ING_CODES
    assert sb.egress.codes == CTRL_HO_EGR_CODES


@pytest.mark.parametrize("materialize", MODES)
def test_I20_ctrl_ho_left_root_is_S_y_times_Y_Q(materialize):
    seen = _ctrl_ho_branch_roots(materialize)
    u0 = [a for a, has_ctx in seen if not has_ctx][0]
    rt = u0.selected_boundary.ingress.route
    assert [f.dim for f in rt.parts] == [1, 2, 2]
    assert rt.residual.logical == q
    assert u0.selected_boundary.ingress.codes == (0, 2, 1, 3)
    assert u0.selected_boundary.egress.codes == (0, 4, 1, 5)


def test_I21_branch_preparation_does_not_change_the_circuit():
    """This phase is metadata only: the branch circuits are what they were."""
    for materialize in MODES:
        seen = _ctrl_ho_branch_roots(materialize)
        gates = sorted(len(a.cmds) for a, _ in seen)
        assert gates == [1, 5], (
            f"branch gate counts {gates}, want [1, 5]; a selected-boundary "
            f"phase must not add or remove a command")


PS = Plus(q, Unit())


@pytest.mark.parametrize("materialize", MODES)
def test_I22_a_sparse_pair_child_stays_sparse(materialize):
    """Plus(Q,I) has THREE codes in a two-qubit space.

    Par must consume the child's actual ordered codes, so the product is
    3 x 2 = 6. Replacing the child by all 2^k assignments to its wires would
    give 4 x 2 = 8 -- a bigger chart that no longer describes the branch.
    """
    t = LetPair("x", "y", PS, q, Id(Ten(PS, q)),
                Pair(Var("x", PS), Var("y", q)))
    r, arts = compile_with_artifacts(t, materialize=materialize)
    sb = [a for a in arts if a.selected_boundary.origin == "par"][0]\
        .selected_boundary
    for side, ch in (("ingress", sb.ingress), ("egress", sb.egress)):
        rt = ch.route
        assert [f.dim for f in rt.parts] == [3, 2], (
            f"{side}: factor dims {[f.dim for f in rt.parts]}, want [3, 2]; "
            f"the sparse child was densified")
        assert rt.parts[0].codes == (0, 1, 2), (
            f"{side}: sparse codes {rt.parts[0].codes} were not carried "
            f"through in order")
        assert rt.parts[0].n_qubits == 2 and rt.parts[0].dim < 4, (
            f"{side}: the child must stay a proper subset of its 2-qubit "
            f"space")
        assert ch.dim == 6, f"{side}: chart dim {ch.dim}, want 6 (not 8)"
    U = r.circuit.get_unitary()
    assert leakage(sb.ingress, U, sb.egress) < ATOL
    np.testing.assert_allclose(
        semantic_action(sb.ingress, U, sb.egress), np.eye(6),
        atol=ATOL, rtol=0.0)


# ===========================================================================
# 6. Clause 4 for real: TenPack ACTS, and Splice CONSUMES the producer
# ===========================================================================
#
# An earlier revision of this module accepted an implementation that returned
# the body's charts unchanged with origin="letpair:splice" and packing=sched
# attached. That is the body-copy implementation M10 was meant to forbid; it
# survived only because the tests checked the label rather than the chart.
# These tests check the chart.

from compile.frames import (BoundaryChart, ChartRoute, tenpack,
                            tensor_splice, chart_of_frame)


def _chart(codes, placements, parts, n=3):
    rep, pl = scatter_repart(placements, n)
    return par_then_repart(parts, rep, n, "t", placements=pl, kind="scatter")


def test_I23_tenpack_with_a_nontrivial_theta_moves_the_codes():
    """p |-> p theta is a REAL re-addressing of the binder coordinate.

    Merely storing the schedule leaves the chart alone, which this pins
    against: with r_p = (0,1) and theta swapping the two binder slots, the
    packed codes must be the transposed ones.
    """
    a = ChartFactor(name="A", owner="cut:a", n_qubits=1, codes=(0, 1))
    b = ChartFactor(name="B", owner="cut:b", n_qubits=1, codes=(0, 1),
                    role="residual", logical=q)
    ch = _chart(None, ((0,), (1,)), (a, b))
    assert ch.codes == (0, 2, 4, 6)          # wire 0 weight 4, wire 1 weight 2

    same = tenpack(ch, r_p=(0, 1), theta=(0, 1))
    assert same.codes == ch.codes, "the identity theta must change nothing"

    swapped = tenpack(ch, r_p=(0, 1), theta=(1, 0))
    assert swapped.codes == (0, 4, 2, 6), (
        f"packed codes {swapped.codes}; a non-identity theta must move the "
        f"binder bits")
    assert swapped.route.placements == ((1,), (0,))
    assert [f.name for f in swapped.route.parts] == ["A", "B"], (
        "packing must not reorder or rename the factors")
    assert swapped.dim == ch.dim
    swapped.validate_joint()


def test_I24_tenpack_leaves_non_binder_wires_alone():
    a = ChartFactor(name="A", owner="cut:a", n_qubits=1, codes=(0, 1))
    b = ChartFactor(name="B", owner="cut:b", n_qubits=1, codes=(0, 1),
                    role="residual", logical=q)
    ch = _chart(None, ((0,), (2,)), (a, b))
    packed = tenpack(ch, r_p=(0, 1), theta=(1, 0))
    assert packed.route.placements == ((1,), (2,)), (
        "wire 2 is outside the binder schedule and must not move")


def test_I25_tenpack_polarities_are_independent():
    """theta^- must touch only the negative chart, theta^+ only the positive."""
    a = ChartFactor(name="A", owner="cut:a", n_qubits=1, codes=(0, 1))
    b = ChartFactor(name="B", owner="cut:b", n_qubits=1, codes=(0, 1),
                    role="residual", logical=q)
    ing = _chart(None, ((0,), (1,)), (a, b))
    egr = _chart(None, ((0,), (1,)), (a, b))
    p_in = tenpack(ing, (0, 1), (1, 0))
    p_out = tenpack(egr, (0, 1), (0, 1))
    assert p_in.codes != ing.codes, "theta^- did not act"
    assert p_out.codes == egr.codes, "theta^+ was the identity and acted anyway"


def test_I26_splice_uses_the_producers_selected_ingress():
    """The external negative boundary is the PRODUCER's ingress, pulled back
    along the producer's own recorded chart correspondence.

    The producer here is NOT the identity: its ingress and egress charts pair
    up in a different order, so returning the body's ingress unchanged gives
    the wrong answer.
    """
    port = (0, 1)
    a = ChartFactor(name="A", owner="cut:a", n_qubits=2, codes=(0, 1, 2, 3))
    # producer: output code i corresponds to input code REVERSED
    prod_out = _chart(None, (port,), (a,))
    a_rev = ChartFactor(name="A", owner="cut:a", n_qubits=2,
                        codes=(3, 2, 1, 0))
    prod_in = _chart(None, (port,), (a_rev,))
    assert prod_in.codes != prod_out.codes

    body_f = ChartFactor(name="S", owner="cut:b", n_qubits=2, codes=(0, 2))
    body_in = _chart(None, (port,), (body_f,))
    body_out = _chart(None, (port,), (body_f,))

    ing, egr = tensor_splice(prod_in, prod_out, body_in, body_out, port)
    # body selects producer-output positions 0 and 2, whose producer INPUTS
    # are codes 3 and 1, i.e. ambient 3<<1 = 6 and 1<<1 = 2.
    assert ing.codes == (6, 2), (
        f"spliced ingress {ing.codes}; the producer's selected ingress was "
        f"not consumed (returning the body's ingress would give "
        f"{body_in.codes})")
    assert ing.codes != body_in.codes
    assert egr.codes == body_out.codes, "the egress is the body's own"


def test_I27_splice_refuses_a_body_code_the_producer_cannot_supply():
    port = (0, 1)
    a = ChartFactor(name="A", owner="cut:a", n_qubits=2, codes=(0, 1))
    prod_in = _chart(None, (port,), (a,))
    prod_out = _chart(None, (port,), (a,))
    unreachable = ChartFactor(name="S", owner="cut:b", n_qubits=2,
                              codes=(0, 3))
    body = _chart(None, (port,), (unreachable,))
    with pytest.raises(ProvenanceError) as e:
        tensor_splice(prod_in, prod_out, body, body, port)
    assert "cannot supply" in str(e.value) or "not produced" in str(e.value)


@pytest.mark.parametrize("materialize", MODES)
def test_I28_letpair_root_is_the_splice_of_its_two_immediate_premises(
        materialize):
    """WIRING gate: production must pass the producer's OWN charts.

    I26 proves the composition itself is producer-sensitive on synthetic
    inputs. This pins that the compiler actually feeds it the pair
    artifact's recorded ingress and egress charts and the packed body,
    rather than short-circuiting to the body. Recomputing the composition
    here from the artifacts and requiring equality would still pass for a
    body-copy implementation ONLY if the producer were the identity -- which
    is why the synthetic producer-sensitive case is the real gate and this
    one checks the plumbing.
    """
    for mk in (simple_spine, pair_yank, curried_spine):
        _, arts = compile_with_artifacts(mk(), materialize=materialize)
        roots = [a for a in arts
                 if a.selected_boundary.origin == "letpair:splice"]
        assert roots
        for lp in roots:
            producer = next(a for a in arts if a.term is lp.term.pair)
            body = next(a for a in arts if a.term is lp.term.body)
            sched = lp.selected_boundary.packing
            n = lp.selected_boundary.ingress.n_qubits
            port = tuple(producer.egress_wires)
            r_p = sched.r_p("ingress")
            theta_in = tuple(r_p.index(w) for w in port)
            packed_in = tenpack(body.selected_boundary.ingress, r_p, theta_in)
            packed_out = tenpack(body.selected_boundary.egress,
                                 sched.r_p("egress"),
                                 tuple(range(len(sched.r_p("egress")))))
            ing, egr = tensor_splice(
                _lift(producer.selected_boundary.ingress,
                      producer.ingress_wires, n),
                _lift(producer.selected_boundary.egress,
                      producer.egress_wires, n),
                packed_in, packed_out, port)
            assert lp.selected_boundary.ingress.codes == ing.codes, (
                f"{mk.__name__}: the root ingress is not the Splice of this "
                f"LetPair's two immediate premises")
            assert lp.selected_boundary.egress.codes == egr.codes


def _lift(chart, wires, n):
    from compile.to_pytket import _ambient_chart
    return _ambient_chart(chart, wires, n)


def _bits(code, wires, n):
    v = 0
    for i, w in enumerate(wires):
        v |= ((code >> (n - 1 - w)) & 1) << (len(wires) - 1 - i)
    return v


def _ambient(chart, wires, n):
    """A premise-local chart lifted onto its recorded ambient wires."""
    if chart.space == "ambient":
        return list(chart.codes)
    out = []
    for c in chart.codes:
        a = 0
        for i, w in enumerate(wires):
            if (c >> (chart.n_qubits - 1 - i)) & 1:
                a |= 1 << (n - 1 - w)
        out.append(a)
    return out


def test_I29_schedule_wires_must_not_duplicate_or_escape():
    """Set-union coverage is not enough: a duplicated or out-of-range wire in
    the schedule OR its complement must be refused."""
    ok = dict(r_x_in=(0,), r_y_in=(1,), r_x_out=(0,), r_y_out=(1,),
              complement_in=(2,), complement_out=(2,))
    TenPackSchedule(**ok).check("ingress", 3)
    for bad in (dict(complement_in=(2, 2)),
                dict(complement_in=(2, 9)),
                dict(complement_in=(1, 2)),      # overlaps the schedule
                dict(r_x_in=(0,), r_y_in=(0,))):
        d = dict(ok)
        d.update(bad)
        with pytest.raises(ProvenanceError):
            TenPackSchedule(**d).check("ingress", 3)


def test_I30_zero_wire_unit_pair_is_legal():
    """let (x,y) = Id_{I(x)I} in ... has an EMPTY binder schedule, which is a
    genuine zero-wire pair, not a missing one."""
    t = LetPair("x", "y", Unit(), Unit(), Id(Ten(Unit(), Unit())),
                Pair(Var("x", Unit()), Var("y", Unit())))
    r = compile(t, materialize=False)
    sb = r.selected_boundary
    assert sb.origin == "letpair:splice"
    assert sb.ingress.dim == 1 and sb.egress.dim == 1
    assert sb.packing.r_p("ingress") == ()


def test_I31_spine_residual_type_must_match_the_head_codomain():
    """The terminal residual is replaced only when its RECORDED type is the
    head's own arrow type. Equal dimension is not evidence."""
    _, arts = compile_with_artifacts(curried_spine(), materialize=False)
    for a in appcuts(arts):
        rt = a.selected_boundary.ingress.route
        _, f_cod = TP.type_of(a.term.f)
        assert rt.residual.logical == f_cod.cod, (
            f"residual type {rt.residual.logical} is not the head's "
            f"codomain {f_cod.cod}")


@pytest.mark.parametrize("materialize", MODES)
def test_I32_pair_owners_are_exactly_the_two_child_cuts(materialize):
    """Not merely a subset of every cut in the compilation."""
    _, arts = compile_with_artifacts(pair_action_witness(),
                                     materialize=materialize)
    par = [a for a in arts if a.selected_boundary.origin == "par"][0]
    kids = {next(x for x in arts if x.term is par.term.fst).cut_id,
            next(x for x in arts if x.term is par.term.snd).cut_id}
    owners = {f.owner for f in par.selected_boundary.ingress.route.parts}
    assert owners == kids, (
        f"Par factor owners {owners} are not exactly the two immediate "
        f"child cuts {kids}")


@pytest.mark.parametrize("materialize", MODES)
def test_I33_pair_and_splice_at_a_nonzero_offset(materialize):
    """A Pair that is not at wire 0, beside a spectator."""
    inner = LetPair("x", "y", q, q, Id(Ten(q, q)),
                    Pair(Seq(Var("x", q), Hg(0, q)), Var("y", q)))
    t = TenTerm(Id(q), inner)
    r, arts = compile_with_artifacts(t, materialize=materialize)
    par = [a for a in arts if a.selected_boundary.origin == "par"][0]
    assert par.offset > 0, f"expected a nonzero offset, got {par.offset}"
    sb = par.selected_boundary
    U = r.circuit.get_unitary()
    assert leakage(sb.ingress, U, sb.egress) < ATOL
    np.testing.assert_allclose(
        semantic_action(sb.ingress, U, sb.egress), np.kron(H_M, I2),
        atol=ATOL, rtol=0.0)
    placed = {w for g in sb.ingress.route.placements for w in g}
    assert 0 not in placed, "the spectator Id(q) must stay outside the chart"


@pytest.mark.parametrize("materialize", MODES)
def test_I34b_splice_under_a_non_involutive_pending_permutation(materialize):
    """The curried spine's pending permutation is a product of a 3-cycle, not
    a swap, so a transport that ran in the wrong direction would show."""
    from core.perm import is_involution
    r0 = compile(curried_spine(), materialize=False)
    assert not is_involution(r0.perm), (
        f"this witness needs a non-involutive pending permutation, got "
        f"{list(r0.perm.new_to_old)}")
    r = compile(curried_spine(), materialize=materialize)
    sb = r.selected_boundary
    U = r.circuit.get_unitary()
    assert sb.ingress.dim == 16 and sb.egress.dim == 16
    assert leakage(sb.ingress, U, sb.egress) < ATOL
    assert abs(r.global_phase) < 1e-12
    np.testing.assert_allclose(
        semantic_action(sb.ingress, U, sb.egress), np.eye(16),
        atol=ATOL, rtol=0.0)
    if materialize:
        assert sb.egress.codes != compile(
            curried_spine(), materialize=False).selected_boundary.egress.codes, (
            "materialising must move the egress; an unmoved chart would mean "
            "the transport never ran")


def test_I36_compilation_actually_invokes_the_splice_with_the_producer():
    """A body-copy is observationally equal END TO END here.

    Every tensor producer this compiler can reach is a whole-port yank whose
    ingress/egress correspondence is the identity, so Splice(producer, packed
    body) and the packed body have the same codes. That is a fact about the
    reachable derivations, not a licence to skip the composition -- so the
    call itself is pinned, with the producer's own charts as its arguments.
    I26 is what proves the composition is producer-sensitive.
    """
    calls = []
    orig = TP.tensor_splice

    def spy(prod_in, prod_out, body_in, body_out, port):
        calls.append((prod_in, prod_out, port))
        return orig(prod_in, prod_out, body_in, body_out, port)

    TP.tensor_splice = spy
    try:
        _, arts = compile_with_artifacts(curried_spine(), materialize=False)
    finally:
        TP.tensor_splice = orig

    roots = [a for a in arts if a.selected_boundary.origin == "letpair:splice"]
    assert len(roots) == 2
    assert len(calls) == len(roots), (
        f"{len(calls)} splice calls for {len(roots)} LetPair roots; the "
        f"composition was skipped")
    for lp in roots:
        producer = next(a for a in arts if a.term is lp.term.pair)
        port = tuple(producer.egress_wires)
        assert any(c[2] == port for c in calls), (
            f"no Splice was performed on the port {port} this producer "
            f"actually hands over")
    for prod_in, prod_out, _ in calls:
        assert prod_in.dim == prod_out.dim and prod_in.dim > 0, (
            "the producer's own charts must be the arguments")


def test_I37_tenpack_is_invoked_per_polarity():
    """theta^- and theta^+ are applied separately, once each per LetPair."""
    calls = []
    orig = TP.tenpack

    def spy(chart, r_p, theta):
        calls.append((tuple(r_p), tuple(theta)))
        return orig(chart, r_p, theta)

    TP.tenpack = spy
    try:
        compile(curried_spine(), materialize=False)
    finally:
        TP.tenpack = orig
    assert len(calls) == 4, (
        f"{len(calls)} TenPack calls for two LetPairs; each needs one per "
        f"polarity")


def test_I38_a_mistyped_terminal_residual_is_not_replaced():
    """Equal dimension is not evidence of identity.

    The spine replaces its head's terminal residual only when the recorded
    logical type is the head's codomain, so S_h (x) Y_Endo can never be
    mistaken for S_h (x) S_y (x) Y_Q.
    """
    _, arts = compile_with_artifacts(curried_spine(), materialize=False)
    cuts = appcuts(arts)
    inner = min(cuts, key=lambda a: len(a.selected_boundary.ingress.route.parts))
    outer = outermost_spine(arts)
    assert inner.selected_boundary.ingress.dim == \
        outer.selected_boundary.ingress.dim == 16
    _, inner_cod = TP.type_of(inner.term.f)
    _, outer_cod = TP.type_of(outer.term.f)
    assert inner.selected_boundary.ingress.route.residual.logical == inner_cod.cod
    assert outer.selected_boundary.ingress.route.residual.logical == outer_cod.cod
    assert inner_cod.cod != outer_cod.cod, (
        "the two residual types must differ, or the guard is untestable")
