"""NF-1 Part H: AppCut on a variable spine, read in the SELECTED BOUNDARY.

CORRECTED ORACLE. An earlier round of this work asserted

    8 = 2_result x 4_h

for `let (h,y) = id in h y`, i.e. that the application EXPORTS the function
head as a typed residual h : Q-oQ. That is formally wrong and has been
withdrawn.

For  h : Q-oQ, y : Q  |-  h y : Q  the canonical AppCut CONSUMES the head h.
It does not export it. The authoritative variable-spine equations are

    B_hy^+-  =  (r_1^+-)^-1 [ S_y^+- (x) Y_B^+- ]

    omega_1^+ U_hy (omega_1^-)^-1  =  U_y (x) yank_B

so for B = Q the SELECTED boundary dimension is 2 x 2 = 4, not 8. The retained
factors are the operand-y package and the residual result boundary, and the
reference lowering is

    Repart_r( Par(S_y, Y_B) )

yank_Q = I2 in canonical Q coordinates. This follows from (VG): Q has two
one-dimensional positive monomials and yank swaps each M_i^+ (x) 1 to
1 (x) M_i^+. The raw ambient action is compared only AFTER r_1^- / r_1^+.

THE TRAP THIS MODULE EXISTS TO CLOSE. The register is three qubits, so the
anonymous region on wires (1,2) has physical dimension 4 -- numerically equal
to dim(Q-oQ). That coincidence is why the withdrawn oracle looked convincing.

But BOTH wrong readings must be refused:
  * it is not the head -- AppCut consumes h;
  * it is not all padding -- the canonical chart RETAINS the live operand-y
    factor S_y.
Only degrees outside the four-dimensional selected sector are complement.

Frame's cardinality invariant ties dim to logical, and the AppCut result type
is Q (dim 2) while the selected chart is dim 4. So the chart cannot be a
Frame: the logical interfaces stay (Q-oQ)(x)Q -> Q, and the selected boundary
is a separate structured parameter carried ALONGSIDE the circuit, the Frames
and the permutation, on Artifact / BranchArtifact / Compiled.
"""

import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(__file__))

from lang.types import Q, Ten, Arrow, Unit, Plus
from lang.terms import (LetPair, Apply, Var, Id, Seq, TenTerm, PlusMap,
                        TwistTen, WireIdentity, EncodeQubit,
                        H as Hg)
import compile.to_pytket as TP
from compile.to_pytket import compile, compile_with_artifacts, select_frames
from compile.frames import (Frame, Port, semantic_action, leakage, pretty,
                            ProvenanceError, ChartFactor, BoundaryChart,
                            SelectedBoundary, par_then_repart,
                            scatter_repart, UnsupportedFrame)
from core.perm import is_involution
from typing_.check import TypeCheckError

q = Q()
endo = Arrow(q, q)
DOM = Ten(endo, q)
MODES = [False, True]
ATOL = 1e-10

H_M = np.array([[1, 1], [1, -1]], complex) / np.sqrt(2)
I2 = np.eye(2, dtype=complex)
YANK_Q = np.eye(2, dtype=complex)      # yank_Q : the triangle identity on Q


def spine(operand):
    """let (h,y) = id_{(Q-oQ)(x)Q} in h <operand>"""
    return LetPair("h", "y", endo, q, Id(DOM),
                   Apply(Var("h", endo), operand))


W_ID = lambda: spine(Var("y", q))                       # U_y = I
W_H = lambda: spine(Seq(Var("y", q), Hg(0, q)))         # U_y = H

WITNESSES = [("identity operand", W_ID, I2),
             ("H operand", W_H, H_M)]


def appcuts(arts):
    """Every occurrence whose boundary came from the AppCut rule."""
    return [a for a in arts
            if a.selected_boundary is not None
            and a.selected_boundary.origin == "appcut"]


def one_cut(term, materialize, pick=max):
    """The AppCut occurrence's OWN artifact.

    Part H is about the application, so it reads the application's artifact.
    `Compiled.selected_boundary` is the ROOT's, and the root here is a
    LetPair, which has no selected-boundary rule yet -- see H24.
    """
    r, arts = compile_with_artifacts(term, materialize=materialize)
    cuts = appcuts(arts)
    assert cuts, "no AppCut boundary was recorded"
    return r, pick(cuts, key=lambda a: a.selected_boundary.ingress.dim)


def framed(term, materialize, pick=max):
    r, a = one_cut(term, materialize, pick)
    sb = a.selected_boundary
    U = r.circuit.get_unitary()
    return r, a, sb, U, semantic_action(sb.ingress, U, sb.egress)


def assert_exact(term, materialize, want, where):
    r, a, sb, U, sem = framed(term, materialize)
    lk = leakage(sb.ingress, U, sb.egress)
    assert lk < ATOL, f"{where}: leakage {lk:.3e} in the selected chart"
    assert abs(r.circuit.phase) < 1e-12, f"{where}: phase {r.circuit.phase}"
    assert sem.shape == want.shape, f"{where}: action is {sem.shape}, want {want.shape}"
    np.testing.assert_allclose(sem, want, atol=ATOL, rtol=0.0)
    sb.ingress.validate_joint()
    sb.egress.validate_joint()
    return r, a, sb


# ---------------------------------------------------------------------------
# 1. The head is CONSUMED -- no h residual anywhere
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("name,mk,U_y", WITNESSES)
@pytest.mark.parametrize("materialize", MODES)
def test_H1_no_output_port_is_attributed_to_the_head(name, mk, U_y, materialize):
    """AppCut consumes h. Nothing on the egress may be attributed to it.

    This REPLACES the withdrawn `8 = 2_result x 4_h` gate. It is currently
    satisfied, and it must stay satisfied: a future repair that exports the
    head would be wrong, however neatly the dimensions balanced.
    """
    r, a = one_cut(mk(), materialize)
    for p in r.output_frame.ports:
        assert p.name != "h", f"{name}: an egress port is named for the head"
        assert p.logical != endo, (
            f"{name}: egress port {p.name!r} is typed Q-oQ; the head is "
            f"consumed by AppCut and must not be exported")
    for side in (a.selected_boundary.ingress, a.selected_boundary.egress):
        assert [f.name for f in side.route.parts] == ["S_y", "Y_B"], (
            f"{name}: AppCut retains only the operand package and the "
            f"residual boundary; the head contributes no factor")


def test_H2_the_anonymous_region_is_classified_by_the_selected_boundary():
    """Wires (0,2) must be CLASSIFIED, and both wrong readings refused.

      * relabelling the whole region h -- the head is consumed by AppCut;
      * calling the whole region padding -- the canonical chart RETAINS the
        live operand-y factor S_y, so part of it is a real resource.
    Its physical dimension is 4, which equals dim(Q-oQ); that coincidence is
    the trap, not evidence.

    Frame.logical is unchanged, so the output FRAME still records one
    anonymous Unit region -- that is expected and is not what is asserted
    here. The classification lives in the selected boundary's factor
    metadata, and the complement is read off the RECORDED SCATTER schedule,
    never off which bits happen to vary. The guard on `kind` is deliberate:
    only a scatter records a support to complement.
    """
    r, a = one_cut(W_ID(), False)
    anon = [p for p in r.output_frame.ports if isinstance(p.logical, Unit)]
    assert anon, "expected the anonymous region"
    region = set(anon[0].wires)
    assert region == {0, 2} and 2 ** len(region) == 4, (
        f"the anonymous region is {sorted(region)}; its dimension 4 is the "
        f"coincidence with dim(Q-oQ) that this test exists to refuse")
    assert anon[0].logical != endo, "the region must never be typed as the head"

    ch = a.selected_boundary.egress
    route = ch.route
    assert route is not None, "the region is unclassified: no recorded route"
    assert route.kind == "scatter", (
        "only a scatter schedule records a support; a correlated Repart "
        "would make the complement claim below meaningless")
    assert [f.name for f in route.parts] == ["S_y", "Y_B"]
    assert route.placements == ((2,), (1,)), (
        f"the two factors must occupy DIFFERENT wires; got "
        f"{route.placements}. Merging them, or placing both on the whole "
        f"region, is the 'one anonymous block' reading this test refuses")
    assert route.parts[0].dim == 2, "S_y is LIVE, not padding"

    placed = {w for g in route.placements for w in g}
    complement = set(range(ch.n_qubits)) - placed
    assert complement == {0}, (
        f"the true complement is wire 0 alone -- everything the recorded "
        f"scatter does not place; got {sorted(complement)}")
    assert region & placed == {2}, (
        f"wire 2 lies inside the anonymous region {sorted(region)} and "
        f"carries the live operand factor S_y; describing the whole region "
        f"as padding is untruthful")
    assert complement < region, (
        "true complement must be a PROPER subset of the anonymous region")


# ---------------------------------------------------------------------------
# 2. The selected boundary is FOUR dimensional, and exact
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("name,mk,U_y", WITNESSES)
@pytest.mark.parametrize("materialize", MODES)
def test_H3_selected_boundary_dimensions_are_four(name, mk, U_y, materialize):
    """operand-y (2) x residual-Q (2) = 4, on BOTH sides."""
    r, a = one_cut(mk(), materialize)
    # The LOGICAL interface types are preserved and NOT redefined.
    assert r.input_frame.logical == DOM
    assert r.output_frame.logical == q
    sb = a.selected_boundary
    assert sb.ingress.dim == 4, f"{name}: ingress dim {sb.ingress.dim}, want 4"
    assert sb.egress.dim == 4, f"{name}: egress dim {sb.egress.dim}, want 4"


@pytest.mark.parametrize("name,mk,U_y", WITNESSES)
@pytest.mark.parametrize("materialize", MODES)
def test_H4_exact_action_is_U_y_tensor_yank(name, mk, U_y, materialize):
    """omega_1^+ U_hy (omega_1^-)^-1 = U_y (x) yank_Q, in the RECORDED chart."""
    assert_exact(mk(), materialize, np.kron(U_y, YANK_Q), name)


def test_H5_factor_order_is_discriminating():
    """With a non-identity operand, U_y (x) yank differs from yank (x) U_y, so
    a reversed lowering cannot pass H4 by accident."""
    assert not np.allclose(np.kron(H_M, YANK_Q), np.kron(YANK_Q, H_M),
                           atol=1e-12), (
        "the chosen operand does not discriminate factor order")


@pytest.mark.parametrize("name,mk,U_y", WITNESSES)
@pytest.mark.parametrize("materialize", MODES)
def test_H6_zero_phase_and_zero_leakage(name, mk, U_y, materialize):
    r, a = one_cut(mk(), materialize)
    sb = a.selected_boundary
    U = r.circuit.get_unitary()
    assert abs(r.global_phase) < 1e-12, f"{name}: phase {r.global_phase}"
    lk = leakage(sb.ingress, U, sb.egress)
    assert lk < ATOL, f"{name}: leakage {lk:.6f} in the selected chart"


# ---------------------------------------------------------------------------
# 3. The recorded route is INDEPENDENTLY checkable
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("name,mk,U_y", WITNESSES)
def test_H7_route_is_recorded_and_independently_reconstructible(name, mk, U_y):
    """r_1^- and r_1^+ must be recomputable FROM THE SCHEDULE.

    Comparing `embed` with `codes` proves nothing -- they are built together.
    What is checked here is that rebuilding the recorded Par->Repart schedule
    reproduces the ambient codes, and that each code decodes out of its own
    bits at the scheduled wires rather than by its position in a list.
    """
    _, a = one_cut(mk(), False)
    sb = a.selected_boundary
    for label, ch in (("r_1^-", sb.ingress), ("r_1^+", sb.egress)):
        assert ch.route is not None, f"{label} is not recorded"
        assert ch.route.label == label
        assert ch.route.reconstructible, f"{label} records no usable schedule"
        assert ch.route.check_schedule()
        assert ch.route.reconstruct() == tuple(ch.codes), (
            f"{label}: rebuilding the schedule does not give the chart")
        assert ch.validate_joint()
        for j, c in enumerate(ch.codes):
            assert ch.route.decode_ambient(c) == ch.route.decode(j), (
                f"{label}: code {c} decodes out of its bits differently "
                f"from its product position")
        assert ch.decode(ch.codes[3]) == (1, 1)


# ---------------------------------------------------------------------------
# 4. Envelope vs selected sector
# ---------------------------------------------------------------------------

def test_H8_generic_four_code_frame_constructor_smoke_test():
    """A generic constructor check ONLY -- NOT the expected AppCut chart.

    An earlier version of this test claimed to prove expressibility. It did
    not: it set logical = Q(x)Q, which would change the term's result type
    from Q, and its padding port named wire 2 while codes (0,1,4,5) actually
    vary wires 0 and 2 -- wire 1 is the fixed one. Both are corrected here,
    and the test no longer claims anything about AppCut.
    """
    f = Frame(logical=Ten(q, q), n_qubits=3, codes=(0, 1, 4, 5),
              ports=(Port("pad", Unit(), (1,), role="residual"),))
    assert f.dim == 4 and 2 ** f.n_qubits == 8
    fixed = [w for w in range(3)
             if len({(c >> (2 - w)) & 1 for c in f.codes}) == 1]
    assert fixed == [1], f"fixed wires {fixed}, but padding names wire 1"
    assert f.completed_dimension == 4


def test_H9_egress_separates_the_live_operand_from_true_complement():
    """The egress separates the retained operand-y factor from real surplus.

    S_y and Y_B are DISTINCT ordered factors even though both are Q here, so
    a 'shared factor' implementation that identified them would fail.
    """
    r, a = one_cut(W_ID(), False)
    ch = a.selected_boundary.egress
    S_y, Y_B = ch.route.parts
    assert S_y.name == "S_y" and S_y.dim == 2, (
        "the canonical chart RETAINS the operand-y package as a live factor; "
        "describing the whole anonymous region as Unit padding is untruthful")
    assert Y_B.name == "Y_B" and Y_B.dim == 2
    assert S_y.owner != Y_B.owner, (
        "S_y belongs to the operand premise and Y_B to the application; they "
        "are two factors of two different premises, never one shared factor")
    assert ch.dim == S_y.dim * Y_B.dim == 4
    assert ch.validate_joint()
    assert ch.route.kind == "scatter"
    placed = {w for g in ch.route.placements for w in g}
    assert placed == {1, 2} and set(range(ch.n_qubits)) - placed == {0}
    anon = [p for p in r.output_frame.ports if isinstance(p.logical, Unit)]
    region = set(anon[0].wires)
    assert region == {0, 2}
    assert region & placed == {2} and region - placed == {0}


# ---------------------------------------------------------------------------
# 5. The Par stage: premise-local addresses are NAMESPACED
# ---------------------------------------------------------------------------

def test_H12_two_premise_local_wire_zeros_give_four_distinct_labels():
    """Both factors address their own local wire 0. That is two namespaces,
    not a collision, and the product must carry four distinct labels."""
    head = ChartFactor(name="S_y", owner="cut:operand", n_qubits=1,
                       codes=(0, 1))
    tail = ChartFactor(name="Y_B", owner="cut:application", n_qubits=1,
                       codes=(0, 1), role="residual", logical=q)
    assert head.codes == tail.codes and head.n_qubits == tail.n_qubits
    rep, places = scatter_repart(((2,), (1,)), 3)
    ch = par_then_repart((head, tail), rep, 3, "r", placements=places,
                         kind="scatter")
    assert ch.dim == 4 and len(set(ch.codes)) == 4, (
        "two local wire-0 factors collapsed into fewer than four labels")
    assert [ch.decode(c) for c in ch.codes] == [(0, 0), (0, 1), (1, 0), (1, 1)]
    assert ch.validate_joint()


def test_H12b_a_genuinely_colliding_repart_is_refused():
    """The namespacing is not a licence to ignore a real ambient collision:
    a repart that lands two ordered pairs on one code must be rejected, not
    silently truncated to a smaller chart."""
    head = ChartFactor(name="S_y", owner="cut:a", n_qubits=1, codes=(0, 1))
    tail = ChartFactor(name="Y_B", owner="cut:b", n_qubits=1,
                       codes=(0, 1), role="residual", logical=q)
    rep, places = scatter_repart(((2,), (2,)), 3)     # SAME ambient wire
    with pytest.raises(ProvenanceError) as e:
        par_then_repart((head, tail), rep, 3, "r", placements=places,
                        kind="scatter")
    assert "injective" in str(e.value)


# ---------------------------------------------------------------------------
# 6. Sparse children keep their ORDER
# ---------------------------------------------------------------------------

def test_H13_sparse_child_order_is_preserved():
    """The child is consumed as its ACTUAL ordered codes -- never replaced by
    all 2^k assignments to its wires, and never sorted."""
    sparse = ChartFactor(name="S_y", owner="cut:operand", n_qubits=3,
                         codes=(5, 0, 3))
    tail = ChartFactor(name="Y_B", owner="cut:application", n_qubits=1,
                       codes=(0, 1), role="residual", logical=q)
    rep, places = scatter_repart(((0, 1, 2), (3,)), 4)
    ch = par_then_repart((sparse, tail), rep, 4, "r", placements=places,
                         kind="scatter")
    assert ch.codes == (10, 11, 0, 1, 6, 7), (
        f"the child's order (5,0,3) was not preserved: {ch.codes}")
    reordered = ChartFactor(name="S_y", owner="cut:operand", n_qubits=3,
                            codes=(0, 3, 5))
    other = par_then_repart((reordered, tail), rep, 4, "r",
                            placements=places, kind="scatter")
    assert other.codes != ch.codes


PS = Plus(q, Unit())
ePS = Arrow(PS, PS)


def sparse_spine():
    """Plus(Q,I) has three codes in a four-dimensional register, so a dense
    2^k reading of the operand would give 4x4=16, not 9."""
    return LetPair("h", "y", ePS, PS, Id(Ten(ePS, PS)),
                   Apply(Var("h", ePS), Var("y", PS)))


@pytest.mark.parametrize("materialize", MODES)
def test_H13b_sparse_operand_spine_is_exactly_I9(materialize):
    _, a, sb = assert_exact(sparse_spine(), materialize, np.eye(9),
                            "sparse Plus(Q,I) spine")
    for ch in (sb.ingress, sb.egress):
        S_y, Y_B = ch.route.parts
        assert S_y.codes == (0, 1, 2) and S_y.n_qubits == 2, (
            f"the operand's sparse codes were not carried through: "
            f"{S_y.codes}")
        assert ch.dim == 9 == S_y.dim * Y_B.dim


# ---------------------------------------------------------------------------
# 7. The operand is never recognised by its syntax
# ---------------------------------------------------------------------------

D3 = Ten(endo, Ten(endo, q))


def nested_spine():
    """let (h1,rest) = id in let (h2,y) = rest in h1 (h2 y)

    The outer application's operand is an Apply -- neither a Var nor a
    Seq(Var, ...) -- so an emitter that recognised operands by syntax would
    have no case for it.
    """
    return LetPair("h1", "rest", endo, Ten(endo, q), Id(D3),
                   LetPair("h2", "y", endo, q, Var("rest", Ten(endo, q)),
                           Apply(Var("h1", endo),
                                 Apply(Var("h2", endo), Var("y", q)))))


@pytest.mark.parametrize("materialize", MODES)
def test_H14_nested_spine_is_exactly_I8(materialize):
    """The outer chart CONSUMES the inner occurrence's whole selected
    boundary as its operand factor: 4 (inner) x 2 (residual Q) = 8, and the
    all-identity spine acts as exactly I8."""
    r, arts = compile_with_artifacts(nested_spine(), materialize=materialize)
    cuts = appcuts(arts)
    assert len(cuts) == 2, f"expected two AppCuts, got {len(cuts)}"
    outer = max(cuts, key=lambda a: a.selected_boundary.ingress.dim)
    inner = min(cuts, key=lambda a: a.selected_boundary.ingress.dim)
    assert isinstance(outer.term.arg, Apply), (
        "this witness is only meaningful if the outer operand is an Apply")
    assert inner.selected_boundary.ingress.dim == 4
    assert outer.selected_boundary.ingress.dim == 8
    _, _, sb = assert_exact(nested_spine(), materialize, np.eye(8), "nested")
    # the operand factor's support is the inner chart's RECORDED support
    inner_support = {w for g in inner.selected_boundary.ingress.route.placements
                     for w in g}
    assert set(sb.ingress.route.placements[0]) == inner_support, (
        "the outer operand factor must sit on the inner occurrence's own "
        "recorded support, not on the whole register")


# ---------------------------------------------------------------------------
# 8. The two polarities, kept apart
# ---------------------------------------------------------------------------

Z3 = Plus(Plus(Unit(), Unit()), Unit())
TW_A = Ten(q, Z3)
TW_B = Ten(Z3, q)
eTW = Arrow(TW_B, TW_B)


def twist_spine():
    """The operand REORDERS its own wires, so its ingress placement is a
    3-cycle away from its egress placement. Reusing one snapshot for both,
    or reversing the direction, changes the answer."""
    return LetPair("h", "y", eTW, TW_A, Id(Ten(eTW, TW_A)),
                   Apply(Var("h", eTW), Seq(Var("y", TW_A),
                                            TwistTen(q, Z3))))


TWIST_M = np.zeros((6, 6), dtype=complex)
for _a in range(2):
    for _b in range(3):
        TWIST_M[_b * 2 + _a, _a * 3 + _b] = 1.0


@pytest.mark.parametrize("materialize", MODES)
def test_H15_operand_placement_differs_between_the_two_polarities(materialize):
    """A non-involutive OPERAND relabelling, exact in both modes.

    This is the witness the Apply rotation alone cannot provide: the argument's
    own placement changes, so ingress and egress cannot share a snapshot.
    """
    _, a, sb = assert_exact(twist_spine(), materialize,
                            np.kron(TWIST_M, np.eye(6)), "twist operand")
    # The two polarities carry DIFFERENT operand codes, from the operand's
    # own two frames -- visible in either mode.
    assert sb.ingress.route.parts[0].codes != sb.egress.route.parts[0].codes, (
        "the operand's ingress and egress charts collapsed to one")
    # And its PLACEMENT differs too. That is visible before materialisation;
    # materialising emits the swap network that physically performs the
    # reorder, after which both polarities legitimately name the same wires
    # in the same order. So the placement claim is made where it is
    # observable, while exactness above is required in both modes.
    _, a0 = one_cut(twist_spine(), False)
    pin = a0.selected_boundary.ingress.route.placements[0]
    pout = a0.selected_boundary.egress.route.placements[0]
    assert pin != pout, (
        f"the operand's placement is identical on both polarities ({pin}); "
        f"this witness cannot then distinguish them")
    assert sorted(pin) == sorted(pout), (
        "the operand occupies the same wires; only their ORDER differs")
    assert tuple(reversed(pin)) != pout, (
        "the reordering must not be its own reverse, or direction would be "
        "untestable")


@pytest.mark.parametrize("materialize", MODES)
def test_H16_appcut_at_a_nonzero_offset_is_exact(materialize):
    """The rule works off each premise's own recorded placement, so an
    application that is not at wire 0 gets a correct boundary too."""
    t = TenTerm(Id(q), W_ID())
    _, a, sb = assert_exact(t, materialize, np.kron(I2, YANK_Q), "offset")
    assert a.offset > 0, f"this witness needs a nonzero offset, got {a.offset}"
    assert sb.ingress.n_qubits == 4
    placed = {w for g in sb.ingress.route.placements for w in g}
    assert 0 not in placed, (
        "the spectator Id(q) on wire 0 must not be swept into the chart")


E2 = Arrow(q, Ten(q, q))
D2 = Ten(E2, q)
YANK_QQ = np.eye(4, dtype=complex)


def wide_spine(operand):
    """h : Q -o (Q (x) Q). The Apply rotation is a 3-cycle, not a swap."""
    return LetPair("h", "y", E2, q, Id(D2), Apply(Var("h", E2), operand))


WIDE = [("identity operand", lambda: wide_spine(Var("y", q)), I2),
        ("H operand", lambda: wide_spine(Seq(Var("y", q), Hg(0, q))), H_M)]


@pytest.mark.parametrize("name,mk,U_y", WIDE)
def test_H17_non_involutive_pending_permutation_direction_is_pinned(name, mk, U_y):
    """A symmetric permutation hides transport direction. This one does not."""
    r0, _, sb0 = assert_exact(mk(), False, np.kron(U_y, YANK_QQ), name)
    assert not is_involution(r0.perm), (
        f"{name}: this witness needs a non-involutive pending permutation, "
        f"got {list(r0.perm.new_to_old)}")
    r1, _, sb1 = assert_exact(mk(), True, np.kron(U_y, YANK_QQ), name)
    assert sb1.egress.codes != sb0.egress.codes, (
        f"{name}: materialising appends a swap network that moves the egress; "
        f"an unmoved chart would mean the transport never ran")
    inv = [0] * r0.perm.n
    for j, o in enumerate(r0.perm.new_to_old):
        inv[o] = j
    assert sb1.egress.transport(tuple(inv)).codes != sb1.egress.codes, (
        "the wrong direction must be observably different")


# ---------------------------------------------------------------------------
# 9. Every artifact carries a REAL resolved boundary
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("materialize", MODES)
def test_H18_every_artifact_carries_a_resolved_boundary(materialize):
    """No occurrence may carry a deferred description for the root to
    interpret later, and every recorded origin must name a real rule."""
    r, arts = compile_with_artifacts(nested_spine(), materialize=materialize)
    assert arts
    for a in arts:
        sb = a.selected_boundary
        assert isinstance(sb, SelectedBoundary), (
            f"occurrence {a.occurrence} ({type(a.term).__name__}) carries "
            f"{sb!r}, not a resolved selected boundary")
        for ch in (sb.ingress, sb.egress):
            assert isinstance(ch, BoundaryChart) and ch.dim > 0
            assert len(set(ch.codes)) == ch.dim
        assert sb.origin, f"occurrence {a.occurrence} records no origin"
    assert appcuts(arts), "the nested spine must contain AppCut boundaries"


def test_H18b_branch_preparation_preserves_resolved_boundaries():
    """A prepared branch carries resolved boundaries from the one nested
    compilation it performed -- not fresh defaults."""
    sink = {}
    compile(nested_spine(), materialize=True, _artifact_sink=sink)
    cuts = appcuts(sink["artifacts"])
    assert len(cuts) == 2
    for c in cuts:
        assert c.selected_boundary.ingress.space == "ambient"
        assert c.selected_boundary.ingress.validate_joint()
    ba = TP._compile_branch_artifact(nested_spine())
    assert isinstance(ba.selected_boundary, SelectedBoundary)
    assert ba.selected_boundary.origin


def test_H18c_sibling_preparations_do_not_share_factor_identities():
    """Factor owners are compilation-scoped cut identities. Two sibling
    branch preparations of the SAME term must not reuse them -- a per-compile
    occurrence integer would collide immediately."""
    from compile.frames import ProvenanceScope
    root = ProvenanceScope()
    per_sibling = []
    for _ in range(2):
        sink = {}
        compile(nested_spine(), materialize=True, _prov_scope=root.fork(),
                _artifact_sink=sink)
        cuts = appcuts(sink["artifacts"])
        assert len(cuts) == 2
        owners = set()
        for c in cuts:
            for f in c.selected_boundary.ingress.route.parts:
                assert isinstance(f.owner, str) and ":" in f.owner, (
                    f"factor owner {f.owner!r} is not a scoped provenance id")
                owners.add(f.owner)
        # Within one compile an id may legitimately repeat: the inner
        # application is both the outer's operand premise and its own
        # residual owner, and naming the same premise twice is correct.
        per_sibling.append(owners)
    a, b = per_sibling
    assert a and b
    assert not (a & b), (
        f"sibling preparations reused factor identities: {sorted(a & b)}. A "
        f"per-compile occurrence integer would collide on every one of them")


# ---------------------------------------------------------------------------
# 10. A perturbed route is not a description of the chart
# ---------------------------------------------------------------------------

def test_H19_route_perturbation_changes_the_chart_or_fails_validation():
    from dataclasses import replace as _replace
    _, a = one_cut(W_ID(), False)
    ch = a.selected_boundary.egress
    assert ch.validate_joint()

    # (a) perturbing the recorded embedding: the schedule no longer rebuilds
    #     the chart, and validation must say so.
    bad_embed = (ch.route.embed[1], ch.route.embed[0]) + ch.route.embed[2:]
    with pytest.raises(ProvenanceError) as e:
        _replace(ch, route=_replace(ch.route, embed=bad_embed)).validate_joint()
    assert "does not reproduce" in str(e.value)

    # (b) perturbing the PLACEMENT while keeping embed: reconstruction from
    #     the schedule now disagrees with the codes. This is the check that
    #     `embed == codes` alone could never make.
    swapped = _replace(ch.route, placements=(ch.route.placements[1],
                                             ch.route.placements[0]))
    with pytest.raises(ProvenanceError) as e:
        _replace(ch, route=swapped).validate_joint()
    assert "rebuilding the recorded" in str(e.value)

    # (c) a placement whose length disagrees with its factor's width
    with pytest.raises(ProvenanceError) as e:
        _replace(ch.route, placements=((1, 2), ch.route.placements[1])
                 ).check_schedule()
    assert "wires" in str(e.value)

    # (d) a placement outside the register
    with pytest.raises(ProvenanceError) as e:
        _replace(ch.route, placements=((9,), ch.route.placements[1])
                 ).check_schedule()
    assert "outside the" in str(e.value)

    # (e) two factors on one wire
    with pytest.raises(ProvenanceError) as e:
        _replace(ch.route, placements=((1,), (1,))).check_schedule()
    assert "placed twice" in str(e.value)

    # (f) scatter placements attached to a repart that is not a scatter
    with pytest.raises(ProvenanceError) as e:
        _replace(ch.route, kind="opaque").check_schedule()
    assert "would not describe it" in str(e.value)


# ---------------------------------------------------------------------------
# 11. The default is EXPLICIT, and a missing rule cannot masquerade as it
# ---------------------------------------------------------------------------

def test_H20_ordinary_occurrences_default_explicitly_from_their_frames():
    r = compile(Id(q), materialize=False)
    sb = r.selected_boundary
    assert sb.origin == "frame-default", (
        f"an ordinary occurrence must SAY it defaulted, got {sb.origin!r}")
    assert sb.ingress.codes == tuple(r.input_frame.codes)
    assert sb.egress.codes == tuple(r.output_frame.codes)


def test_H20b_a_rule_that_fails_to_fire_is_rejected_not_defaulted():
    """Declare that `Id` has a boundary rule; since no emitter records one,
    the compilation must fail rather than quietly produce the default."""
    orig = TP._has_boundary_rule
    TP._has_boundary_rule = lambda t: isinstance(t, (Apply, LetPair, Id))
    try:
        with pytest.raises(TypeCheckError) as e:
            compile(Id(q), materialize=False)
        assert "must not fall through to the frame default" in str(e.value)
    finally:
        TP._has_boundary_rule = orig
    assert compile(Id(q)).selected_boundary.origin == "frame-default"


# ---------------------------------------------------------------------------
# 12. Scope limits, stated rather than assumed
# ---------------------------------------------------------------------------

from test_release_safety import _use                     # noqa: E402

GUARDS = [("valid open branch", lambda: PlusMap(q, q, _use("f"), Id(q))),
          ("coherent sharing", lambda: PlusMap(q, q, _use("f"), _use("f")))]


@pytest.mark.parametrize("name,mk", GUARDS)
@pytest.mark.parametrize("materialize", MODES)
def test_H21_release_safety_guards_now_consume_the_use_block(
        name, mk, materialize):
    """SUPERSEDES the frame-default expectation.

    These four witnesses used to compile with a root frame default, because
    the open sum had no plan. They now emit from their completed-branch
    Block, so the root boundary IS that Block. The blockwise arithmetic is
    asserted rather than accepting any successful compilation:

        valid open branch   u0(4) + u1(2) x T_f(4) = 12
        coherent sharing    both branches use f    =  8
    """
    from compile.frames import OpenUseBlockPlan
    r, arts = compile_with_artifacts(mk(), env={"f": [2, 3]},
                                     materialize=materialize)
    assert r.circuit is not None and r.circuit.n_qubits == 4
    sb = r.selected_boundary
    assert isinstance(sb, SelectedBoundary)
    assert sb.origin == "plusmap:use-block", (
        f"{name}: the root kept {sb.origin!r} instead of its Block")
    planned = [a for a in arts if isinstance(a.placement, OpenUseBlockPlan)]
    assert planned, f"{name}: no use-block plan"
    pl = planned[0].placement
    want = 12 if "valid" in name else 8
    assert pl.ingress.dim == pl.egress.dim == want, (
        f"{name}: parent {pl.ingress.dim}/{pl.egress.dim}, want {want}")
    assert sum(b.dim for b in pl.branches) == want, (
        f"{name}: the parent is the DIRECT SUM of its blocks")
    for ch in (sb.ingress, sb.egress):
        assert ch.n_qubits == r.circuit.n_qubits
        assert len(set(ch.codes)) == ch.dim
    assert not hasattr(r, "chart_error")


def test_H22_an_unequal_width_operand_fails_closed_with_a_named_reason():
    """RECORDED RED, kept as a fail-closed gate rather than a guess.

    `Seq(Var y, EncodeQubit)` selects a 2-qubit ingress frame (EncodeQubit's
    one-hot boundary) while inheriting its producer's 1-wire ingress
    placement. The artifact model therefore records a placement that does not
    span the boundary it is supposed to place, and the AppCut rule must say
    so instead of padding, truncating, or silently reusing the egress
    placement. Closing this needs the placement to be selected by the
    derivation, which is the TenPack/Distributor phase, not this one.
    """
    PU = Plus(Unit(), Unit())
    ePU = Arrow(PU, PU)
    op = Seq(Var("y", q), EncodeQubit())
    fi, fo = select_frames(op)
    assert fi.n_qubits == 2 and fo.n_qubits == 2
    t = LetPair("h", "y", ePU, q, Id(Ten(ePU, q)), Apply(Var("h", ePU), op))
    with pytest.raises(TypeCheckError) as e:
        compile(t, materialize=False)
    msg = str(e.value)
    assert "recorded ingress placement" in msg and "chart is 2 qubits" in msg


def test_H23_letpair_root_is_a_splice_of_producer_and_tenpacked_body():
    """SUPERSEDED the frame-default LetPair.

    LetPair no longer defaults: its root is Splice(pair, TenPack(body)), so
    the producer is matched rather than ignored and the binder schedules are
    recorded per polarity. Part H still reads the APPLICATION's own artifact
    for AppCut claims -- see Part I for the LetPair rule itself.
    """
    r = compile(W_ID(), materialize=False)
    sb = r.selected_boundary
    assert sb.origin == "letpair:splice", (
        f"the root must come from a Splice, got {sb.origin!r}")
    assert sb.packing is not None, "no TenPack binder schedule recorded"
    assert sb.ingress.dim == 4 and sb.egress.dim == 4, (
        "the root now carries the application's accumulated spine boundary")


# ---------------------------------------------------------------------------
# ctrl_ho: the corrected parent boundary is 80, as 64 (+) 16
# ---------------------------------------------------------------------------
#
# Use-block opposite-context completion gives, per branch:
#
#     u0 : S_y (x) Y_Q                 dim 2*2      =  4
#     u1 : S_h (x) S_y (x) Y_Q         dim 4*2*2    = 16
#
#     Gamma_left  = empty                  dim T = 1
#     Gamma_right = { f : EndoOp }         dim T = 16
#
#     left  = B_u0 (x) T_f             dim 4*16     = 64
#     right = T_empty (x) B_u1         dim 1*16     = 16
#
#     parent = left (+) right          dim 64+16    = 80   on BOTH polarities
#
# Part I now pins u0 = 4 and u1 = 16 as the ctrl_ho BRANCH ROOTS; consuming
# them is the next phase, so H11 below stays red.

CTRL_HO_U0 = 4
CTRL_HO_U1 = 16
CTRL_HO_T_F = 16
CTRL_HO_LEFT = CTRL_HO_U0 * CTRL_HO_T_F      # 64
CTRL_HO_RIGHT = 1 * CTRL_HO_U1               # 16
CTRL_HO_PARENT = CTRL_HO_LEFT + CTRL_HO_RIGHT


def test_H10_ctrl_ho_use_block_arithmetic():
    """The completed blocks, kept as a SUM and never flattened.

    80 must arise as 64 (+) 16 from two differently completed blocks. Forcing
    it through one uniform main-dimension x context-factor product would be a
    different claim that happens to hit the same number.
    """
    assert CTRL_HO_LEFT == 64 and CTRL_HO_RIGHT == 16
    assert CTRL_HO_PARENT == 80
    assert CTRL_HO_LEFT != CTRL_HO_RIGHT, (
        "the two blocks are completed against opposite contexts and must not "
        "be collapsed into one multiplier")
    total_main = CTRL_HO_U0 + CTRL_HO_U1                 # 20
    assert total_main * CTRL_HO_T_F != CTRL_HO_PARENT, (
        "a uniform (sum of mains) x T_f product gives 320, not 80; the "
        "completion is per block, against opposite contexts")


@pytest.mark.parametrize("materialize", MODES)
def test_H11_ctrl_ho_selected_boundary_is_80_on_both_sides(materialize):
    """80 = 64 (+) 16, on BOTH polarities, as a tagged direct sum.

    Replaces the withdrawn 256 gate. The blocks are completed against
    OPPOSITE contexts -- u0 against f, u1 against nothing -- so the parent is
    a Block of two differently completed charts, never one uniform
    main-dimension x context-factor product.
    """
    from test_nf1_beta_tensor import _fixture

    TP._USE_BLOCK_OBSERVED.clear()
    compile(_fixture("ctrl_ho_closed_plus_map"), materialize=materialize)
    assert TP._USE_BLOCK_OBSERVED, (
        "no use-block plan for ctrl_ho; the selected boundary cannot be "
        "checked")
    pl = TP._USE_BLOCK_OBSERVED[-1]
    blocks = {b.index: b for b in pl.branches}
    assert blocks[0].dim == CTRL_HO_LEFT, (
        f"left block {blocks[0].dim}, want {CTRL_HO_LEFT} = 4_main x 16_f")
    assert blocks[1].dim == CTRL_HO_RIGHT, (
        f"right block {blocks[1].dim}, want {CTRL_HO_RIGHT} = 16_main")
    assert blocks[0].uses == () and blocks[1].uses != (), (
        "the recorded branch-use sets are the wrong way round")
    assert [b.name for b in blocks[0].inactive] == ["f"], (
        "u0 must be completed against the f it does not use")
    assert blocks[1].inactive == (), (
        "u1 uses f, so it must not be completed against it again")
    assert pl.ingress.dim == CTRL_HO_PARENT, f"ingress {pl.ingress.dim}, want 80"
    assert pl.egress.dim == CTRL_HO_PARENT, f"egress {pl.egress.dim}, want 80"
    for side in ("ingress", "egress"):
        assert len(pl.inclusion(0, side)) == CTRL_HO_LEFT
        assert len(pl.inclusion(1, side)) == CTRL_HO_RIGHT
    assert pl.validate()


# ---------------------------------------------------------------------------
# 13. The canonical-form precondition on the head
# ---------------------------------------------------------------------------
#
# An earlier version of this module asserted, from a 34/34 corpus survey,
# that a head's bundle placement always coincides on both polarities. That
# was a finite-corpus generalisation promoted to a theorem, and it is FALSE
# for the IR as accepted. The counterexample below typechecks, reaches the
# general AppCut path in both modes, and leaks sqrt(2).
#
# The response is not to widen Part H to arbitrary non-normal heads. The
# reference emitter is defined on canonical normal derivations, so a head
# that is not a neutral variable spine is refused before any emission, and
# the source/NF layer is what guarantees one never arrives.

QQ = Ten(q, q)


def seq_head():
    """A head that RELABELS its own bundle. Not a neutral variable spine."""
    return Seq(Var("h", endo), WireIdentity(endo, QQ), TwistTen(q, q),
               WireIdentity(QQ, endo))


def seq_head_spine(operand=None):
    return LetPair("h", "y", endo, q, Id(DOM),
                   Apply(seq_head(),
                         Var("y", q) if operand is None else operand))


@pytest.mark.parametrize("materialize", MODES)
def test_H25_a_non_neutral_head_fails_closed(materialize):
    """The refuted witness, refused rather than mis-compiled.

    Before the guard this compiled and produced ingress (0,2,1,3), egress
    (0,4,1,5) and leakage sqrt(2) -- an untruthful selected boundary, not an
    error. It must now fail closed, in BOTH modes, naming the requirement.
    """
    with pytest.raises(UnsupportedFrame) as e:
        compile(seq_head_spine(), materialize=materialize)
    msg = str(e.value)
    assert "canonical neutral variable spine" in msg
    assert "normalize" in msg


def test_H25b_the_refusal_precedes_child_compilation_and_emission():
    """Nothing is compiled and nothing is emitted before the refusal.

    The operand here WOULD emit an H. If the guard ran late, that gate would
    already be in the circuit and the argument's frames already selected.
    """
    seen, made = [], []
    orig_sf, orig_circ = TP.select_frames, TP.Circuit

    def spy_sf(t, ctx=None):
        seen.append(type(t).__name__)
        return orig_sf(t, ctx)

    def spy_circ(*a, **k):
        c = orig_circ(*a, **k)
        made.append(c)
        return c

    TP.select_frames, TP.Circuit = spy_sf, spy_circ
    try:
        with pytest.raises(UnsupportedFrame):
            compile(seq_head_spine(Seq(Var("y", q), Hg(0, q))),
                    materialize=False)
    finally:
        TP.select_frames, TP.Circuit = orig_sf, orig_circ

    assert "Apply" in seen, "the guard must be reached at the application"
    for late in ("TwistTen", "WireIdentity", "H", "Var"):
        assert late not in seen, (
            f"{late} was compiled before the head was checked; the guard "
            f"must precede the argument and the head")
    assert made, "no circuit was constructed"
    assert len(made[0].get_commands()) == 0, (
        f"{len(made[0].get_commands())} commands were emitted before the "
        f"refusal; the guard must leave nothing half-built")


def test_H26_neutral_spines_are_accepted_and_stay_exact():
    """Var and curried-Apply heads are canonical and must keep working."""
    assert TP._is_neutral_spine(Var("h", endo))
    assert TP._is_neutral_spine(Apply(Var("h", endo), Var("y", q)))
    assert TP._is_neutral_spine(
        Apply(Apply(Var("h", endo), Var("y", q)), Var("y", q)))
    assert not TP._is_neutral_spine(seq_head())
    assert not TP._is_neutral_spine(Id(endo))
    assert not TP._is_neutral_spine(Apply(seq_head(), Var("y", q))), (
        "a non-neutral head buried under an application must be refused too, "
        "and refused at the OUTER application, before it emits anything")
    for materialize in MODES:
        assert_exact(W_ID(), materialize, np.kron(I2, YANK_Q), "Var head")
        assert_exact(nested_spine(), materialize, np.eye(8), "curried head")


def test_H24_head_neutrality_is_an_enforced_invariant_not_a_corpus_fact():
    """REPLACES the withdrawn 34/34 survey.

    The invariant is not "no witness in our corpus has a reordering head" --
    that claim was false. It is "a head that is not a neutral variable spine
    never reaches emission", and it holds because it is CHECKED, not because
    the fixtures happen to comply.
    """
    for mk in (W_ID, W_H, nested_spine, sparse_spine, twist_spine,
               lambda: wide_spine(Var("y", q)),
               lambda: TenTerm(Id(q), W_ID())):
        for materialize in MODES:
            _, arts = compile_with_artifacts(mk(), materialize=materialize)
            cuts = appcuts(arts)
            assert cuts
            for a in cuts:
                assert TP._is_neutral_spine(a.term.f), (
                    f"an AppCut was emitted for a non-neutral head "
                    f"{type(a.term.f).__name__}; the guard did not hold")
    # and the guard is what makes it true: remove it and the refuted witness
    # walks straight back in.
    orig = TP._is_neutral_spine
    TP._is_neutral_spine = lambda t: True
    try:
        r, a = one_cut(seq_head_spine(), False)
        U = r.circuit.get_unitary()
        sb = a.selected_boundary
        assert leakage(sb.ingress, U, sb.egress) > 1.0, (
            "with the guard bypassed the refuted witness must still leak; if "
            "it does not, this test no longer demonstrates why the guard is "
            "needed")
    finally:
        TP._is_neutral_spine = orig


def test_H24b_production_derives_the_two_residual_placements_separately():
    """Y_B^- and Y_B^+ are computed from two sources, not one read twice.

    The enforced neutral-spine invariant makes them provably equal, so no
    ACCEPTED term can distinguish the two implementations. This test bypasses
    only the guard -- not the boundary rule -- so the refuted head reaches
    AppCut and the difference becomes observable. Collapsing either onto the
    other changes both numbers below.
    """
    orig = TP._is_neutral_spine
    TP._is_neutral_spine = lambda t: True
    try:
        _, a = one_cut(seq_head_spine(), False)
        sb = a.selected_boundary
        y_neg = sb.ingress.route.placements[1]
        y_pos = sb.egress.route.placements[1]
    finally:
        TP._is_neutral_spine = orig
    assert y_neg == (1,), f"Y_B^- placement is {y_neg}, want (1,)"
    assert y_pos == (0,), f"Y_B^+ placement is {y_pos}, want (0,)"
    assert y_neg != y_pos, (
        "the two residual placements were read from one snapshot; on this "
        "head they are genuinely different resources")
