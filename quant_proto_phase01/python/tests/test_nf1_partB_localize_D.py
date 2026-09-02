"""NF-1 Part B: localize D to closed typed witnesses.

TEST-ONLY. Nothing here repairs anything.

D remains red after NF_beta_tensor with NO residual redex, so the failure is
not a beta/tensor-normalization failure. This module drives it down to closed,
beta/tensor-normal witnesses:

    P  = PlusMap(I(x)Q, (I(+)I)(x)Q, Id(I(x)Q), DistL(I,I,Q))
    P0 = PlusMap(I,     (I(+)I)(x)I, Id(I),     DistL(I,I,I))

P0 is the SMALLEST tested witness -- 2 qubits, semantic dimension 3. P is the
larger one, kept because its left sector also moves.

P emits G_P = I_8 -- zero commands -- yet reports an ingress and an egress
that are different embeddings, so the required

    G_P u_P^-  =  u_P^+

cannot hold.

CAUSE (precise). PlusMap uses ONE parent payload placement and never
constructs or realizes independent occurrence-level ingress and egress
inclusions. Dropping the branch frames exposes the deficient API, but merely
returning DistL's identical local frames would NOT repair the parent-sector
transport: the parent still has to map its own j_i^- to its own j_i^+, and
nothing in the branch artifact supplies that.

Correspondingly, a correct repair does NOT make j_i^- equal j_i^+. The
inclusions stay different; what must hold is the transport equation

    G_parent J_i^-  =  J_i^+ G_i

which is what the acceptance oracle below asserts.
"""

import numpy as np
import pytest

from lang.types import Unit, Q, Ten, Plus
from lang.terms import (Id, Seq, PlusMap, NPlusMap, DistL, UndistL,
                        H as Hg, S as Sg, T as Tg)
from compile.to_pytket import compile
from compile.frames import semantic_action, leakage, pretty

I, q = Unit(), Q()
IA = Ten(I, q)                       # I (x) Q
BIA = Ten(Plus(I, I), q)             # (I (+) I) (x) Q
MODES = [False, True]
ATOL = 1e-10

H_M = np.array([[1, 1], [1, -1]], complex) / np.sqrt(2)
S_M = np.array([[1, 0], [0, 1j]], complex)
T_M = np.array([[1, 0], [0, np.exp(1j * np.pi / 4)]], complex)


def P_witness():
    return PlusMap(IA, BIA, Id(IA), DistL(I, I, q))


def Q_witness():
    return PlusMap(IA, Plus(IA, IA), Id(IA), UndistL(I, I, q))


def _framed(t, m):
    r = compile(t, materialize=m)
    U = r.circuit.get_unitary()
    return r, U, semantic_action(r.input_frame, U, r.output_frame), \
        leakage(r.input_frame, U, r.output_frame)


# ---------------------------------------------------------------------------
# PRE-REPAIR observations about P
#
# Zero commands and G = I are records of TODAY's behaviour, not invariants of
# a correct repair: realizing the sector transport will require the parent to
# emit a permutation. These tests are EXPECTED TO CHANGE when the repair
# lands, and they are not acceptance criteria. The canonical codes below ARE
# expected to survive.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("materialize", MODES)
def test_P_emits_its_post_align(materialize):
    """Was: 0 commands, G = I_8, leakage sqrt(2). Those recorded the DEFECT.

    P's branch frames agree, so K^+ = J^- != J^+ and the parent owes exactly
    one post-Align. No pre-Align: J^- == K^-.
    """
    r = compile(P_witness(), materialize=materialize)
    assert r.circuit.n_qubits == 3
    assert len(r.circuit.get_commands()) == 1, [str(c) for c in r.circuit.get_commands()]
    assert "ToffoliBox" in str(r.circuit.get_commands()[0])


@pytest.mark.parametrize("materialize", MODES)
def test_P_canonical_boundary_codes(materialize):
    """The boundary codes themselves. Expected to survive the repair."""
    r = compile(P_witness(), materialize=materialize)
    assert tuple(r.input_frame.codes) == (0, 2, 4, 5, 6, 7)
    assert tuple(r.output_frame.codes) == (0, 1, 2, 3, 4, 5)


def inclusion(codes, ambient_dim):
    """J: C^{|codes|} -> C^{ambient}, J[codes[k], k] = 1."""
    J = np.zeros((ambient_dim, len(codes)), complex)
    for k, c in enumerate(codes):
        J[c, k] = 1.0
    return J


def assert_sector_transport(r, U, sectors, where):
    """G_parent J_i^- == J_i^+ G_i, for each branch sector.

    NOT `j_i^- == j_i^+`. A correct repair keeps the two inclusions
    DIFFERENT and realizes the transport between them.
    """
    n = U.shape[0]
    cin, cout = tuple(r.input_frame.codes), tuple(r.output_frame.codes)
    off_in = off_out = 0
    for name, dim, G_i in sectors:
        Jin = inclusion(cin[off_in:off_in + dim], n)
        Jout = inclusion(cout[off_out:off_out + dim], n)
        lhs, rhs = U @ Jin, Jout @ G_i
        assert np.allclose(lhs, rhs, atol=ATOL, rtol=0.0), (
            f"{where}: sector {name} transport fails: "
            f"G J^- != J^+ G_{name}\n"
            f"  J^- cols {cin[off_in:off_in + dim]}, "
            f"J^+ cols {cout[off_out:off_out + dim]}\n"
            f"  max |G J^- - J^+ G| = {np.abs(lhs - rhs).max():.6f}")
        off_in += dim
        off_out += dim


def assert_boundary_transport(r, U, where):
    """G_parent u^- == u^+ G_sem at the whole boundary (G_sem = I here)."""
    n = U.shape[0]
    uin = inclusion(tuple(r.input_frame.codes), n)
    uout = inclusion(tuple(r.output_frame.codes), n)
    lhs, rhs = U @ uin, uout @ np.eye(uin.shape[1])
    assert np.allclose(lhs, rhs, atol=ATOL, rtol=0.0), (
        f"{where}: boundary transport fails: G u^- != u^+; "
        f"max dev {np.abs(lhs - rhs).max():.6f}")


# --- diagnostic (factual, not the acceptance oracle) -----------------------

@pytest.mark.parametrize("materialize", MODES)
def test_P_sector_inclusions_are_independent_DIAGNOSTIC(materialize):
    """Factual record of the four inclusions. Deliberately NOT a gate.

    j_L^- = (0,2)      j_L^+ = (0,1)
    j_R^- = (4,5,6,7)  j_R^+ = (2,3,4,5)

    That these differ is not itself the defect -- a correct compiler may well
    choose different ingress and egress embeddings. The defect is that the
    transport between them is not realized; see the oracle below.
    """
    r = compile(P_witness(), materialize=materialize)
    cin, cout = tuple(r.input_frame.codes), tuple(r.output_frame.codes)
    assert (cin[:2], cin[2:]) == ((0, 2), (4, 5, 6, 7))
    assert (cout[:2], cout[2:]) == ((0, 1), (2, 3, 4, 5))
    assert cin[:2] != cout[:2] and cin[2:] != cout[2:]


# --- acceptance oracle -- EXPECTED RED -------------------------------------

@pytest.mark.parametrize("materialize", MODES)
def test_P_sector_transport_equation(materialize):
    """G_P J_i^- = J_i^+ G_i for both branches, with G_i = I.

    This is the first failed equation for D. It makes NO assumption about the
    physical circuit: what the parent emits is exactly what is under test.
    """
    r = compile(P_witness(), materialize=materialize)
    U = r.circuit.get_unitary()
    assert_sector_transport(
        r, U, [("L", 2, np.eye(2)), ("R", 4, np.eye(4))], "P")


@pytest.mark.parametrize("materialize", MODES)
def test_P_boundary_transport_equation(materialize):
    r = compile(P_witness(), materialize=materialize)
    assert_boundary_transport(r, r.circuit.get_unitary(), "P")


# ---------------------------------------------------------------------------
# 12. P0 -- the smallest tested witness (facts confirmed before pinning)
# ---------------------------------------------------------------------------

def P0_witness():
    return PlusMap(I, Ten(Plus(I, I), I), Id(I), DistL(I, I, I))


@pytest.mark.parametrize("materialize", MODES)
def test_P0_emits_its_post_align(materialize):
    """Was: 0 commands, G = I_4, leakage 1. Those recorded the DEFECT."""
    r = compile(P0_witness(), materialize=materialize)
    U = r.circuit.get_unitary()
    assert len(r.circuit.get_commands()) == 1, [str(c) for c in r.circuit.get_commands()]
    assert "ToffoliBox" in str(r.circuit.get_commands()[0])
    assert leakage(r.input_frame, U, r.output_frame) < ATOL


@pytest.mark.parametrize("materialize", MODES)
def test_P0_canonical_boundary_codes(materialize):
    """2 qubits, semantic dimension 3, canonical codes. Survives the repair."""
    r = compile(P0_witness(), materialize=materialize)
    assert r.circuit.n_qubits == 2
    cin, cout = tuple(r.input_frame.codes), tuple(r.output_frame.codes)
    assert cin == (0, 2, 3), f"input codes {cin}"
    assert cout == (0, 1, 2), f"output codes {cout}"
    assert len(cin) == 3, "semantic dimension is not 3"


# --- item 6: what G must DO on the valid codes -----------------------------

@pytest.mark.parametrize("materialize", MODES)
def test_P0_valid_code_direction(materialize):
    """G must carry each VALID input code to its paired output code:

        0 -> 0        2 -> 1        3 -> 2

    Physical code 1 is not in the input frame; its image is deliberately
    left unconstrained here.
    """
    r = compile(P0_witness(), materialize=materialize)
    U = r.circuit.get_unitary()
    for src, dst in ((0, 0), (2, 1), (3, 2)):
        want = np.zeros(4, complex)
        want[dst] = 1.0
        got = U[:, src]
        assert np.allclose(got, want, atol=ATOL, rtol=0.0), (
            f"P0: valid code {src} must map to {dst}; "
            f"column {src} is {np.round(got, 6)}")


@pytest.mark.parametrize("materialize", MODES)
def test_P0_sector_inclusions_DIAGNOSTIC(materialize):
    """j_L^- = (0,)  j_L^+ = (0,)   j_R^- = (2,3)  j_R^+ = (1,2)

    Note the left sector already AGREES. The failure is confined to the right
    sector, which is the one the structural DistL branch contributes.
    """
    r = compile(P0_witness(), materialize=materialize)
    cin, cout = tuple(r.input_frame.codes), tuple(r.output_frame.codes)
    assert (cin[:1], cin[1:]) == ((0,), (2, 3))
    assert (cout[:1], cout[1:]) == ((0,), (1, 2))
    assert cin[:1] == cout[:1], "left sector was expected to agree"
    assert cin[1:] != cout[1:], "right sector was expected to differ"


@pytest.mark.parametrize("materialize", MODES)
def test_P0_sector_transport_equation(materialize):
    r = compile(P0_witness(), materialize=materialize)
    assert_sector_transport(
        r, r.circuit.get_unitary(),
        [("L", 1, np.eye(1)), ("R", 2, np.eye(2))], "P0")


@pytest.mark.parametrize("materialize", MODES)
def test_P0_boundary_transport_equation(materialize):
    r = compile(P0_witness(), materialize=materialize)
    assert_boundary_transport(r, r.circuit.get_unitary(), "P0")


# ---------------------------------------------------------------------------
# 7. Sector METADATA gates -- EXPECTED RED
#
# The transport equation says what the circuit must DO. These say what the
# artifact must SAY: a repaired PlusMap has to expose its two branch regions
# as first-class typed sectors, because that is the only place a consumer can
# read j_i^- and j_i^+ from. Today both frames carry zero sectors, so the
# parent's own branch structure is not recorded anywhere.
# ---------------------------------------------------------------------------

def assert_two_sectors(frame, expected, where):
    """Exactly two sectors: typed, ordered, disjoint, exhaustive, pinned.

    `expected` entries are (logical, codes, tag_values). tag_values is a SET
    of physical tag words: a summand that is itself a sum spans several, and
    recording it as one integer would misdescribe the sector.
    """
    secs = tuple(frame.sectors)
    assert len(secs) == 2, (
        f"{where}: expected exactly 2 sectors, found {len(secs)}")

    assert [s.index for s in secs] == [0, 1], (
        f"{where}: sectors are not ordered 0,1: {[s.index for s in secs]}")

    for s, (ty, codes, tags) in zip(secs, expected):
        assert s.logical == ty, (
            f"{where}: sector {s.index} is typed {pretty(s.logical)}, "
            f"expected {pretty(ty)}")
        assert tuple(s.codes) == codes, (
            f"{where}: sector {s.index} codes {tuple(s.codes)} != "
            f"pinned {codes}")
        assert tuple(s.tag_values) == tags, (
            f"{where}: sector {s.index} tag_values {tuple(s.tag_values)} "
            f"!= pinned {tags}")

    a, b = (set(s.codes) for s in secs)
    assert not (a & b), f"{where}: sectors overlap on {sorted(a & b)}"

    concat = tuple(c for s in secs for c in s.codes)
    assert concat == tuple(frame.codes), (
        f"{where}: sectors are not exhaustive/in order: {concat} != "
        f"{tuple(frame.codes)}")


@pytest.mark.parametrize("materialize", MODES)
def test_P0_exposes_two_typed_sectors(materialize):
    r = compile(P0_witness(), materialize=materialize)
    assert_two_sectors(
        r.input_frame,
        [(I, (0,), (0,)), (Ten(Plus(I, I), I), (2, 3), (1,))],
        "P0 input frame")
    assert_two_sectors(
        r.output_frame,
        [(I, (0,), (0,)), (Plus(Ten(I, I), Ten(I, I)), (1, 2), (1, 2))],
        "P0 output frame")


@pytest.mark.parametrize("materialize", MODES)
def test_P_exposes_two_typed_sectors(materialize):
    r = compile(P_witness(), materialize=materialize)
    assert_two_sectors(
        r.input_frame,
        [(IA, (0, 2), (0,)), (BIA, (4, 5, 6, 7), (1,))],
        "P input frame")
    assert_two_sectors(
        r.output_frame,
        [(IA, (0, 1), (0,)), (Plus(IA, IA), (2, 3, 4, 5), (1, 2))],
        "P output frame")


# ---------------------------------------------------------------------------
# 1-2. P and Q must be exact -- EXPECTED RED
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("materialize", MODES)
def test_P_is_exact_identity(materialize):
    r, U, sem, lk = _framed(P_witness(), materialize)
    assert lk < ATOL, f"P: leakage {lk:.6f}"
    np.testing.assert_allclose(sem, np.eye(6), atol=ATOL, rtol=0.0)


@pytest.mark.parametrize("materialize", MODES)
def test_Q_is_exact_identity(materialize):
    r, U, sem, lk = _framed(Q_witness(), materialize)
    assert lk < ATOL, f"Q: leakage {lk:.6f}"
    np.testing.assert_allclose(sem, np.eye(6), atol=ATOL, rtol=0.0)


# ---------------------------------------------------------------------------
# 4. Green control: both branches structurally trivial
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("materialize", MODES)
def test_control_identity_plusmap_is_exact(materialize):
    r, U, sem, lk = _framed(PlusMap(IA, IA, Id(IA), Id(IA)), materialize)
    assert lk < ATOL
    np.testing.assert_allclose(sem, np.eye(4), atol=ATOL, rtol=0.0)


# ---------------------------------------------------------------------------
# 5. Standalone NPlusMap(H,S,T) -- the branch map alone
# ---------------------------------------------------------------------------

def _hst():
    M = np.zeros((6, 6), complex)
    for k, blk in enumerate((H_M, S_M, T_M)):
        M[2 * k:2 * k + 2, 2 * k:2 * k + 2] = blk
    return M


@pytest.mark.parametrize("materialize", MODES)
def test_standalone_nplusmap_hst_is_exact(materialize):
    pm = NPlusMap((IA, IA, IA), (Hg(0, IA), Sg(0, IA), Tg(0, IA)))
    r, U, sem, lk = _framed(pm, materialize)
    assert lk < ATOL, f"NPlusMap: leakage {lk:.6f}"
    assert abs(r.global_phase) < 1e-12
    np.testing.assert_allclose(sem, _hst(), atol=ATOL, rtol=0.0)


# ---------------------------------------------------------------------------
# 6. Seq(P, Q): the two false placements CANCEL
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("materialize", MODES)
def test_seq_P_Q_is_exact_because_the_errors_cancel(materialize):
    """Seq(P,Q) is green, and that is precisely why it CANNOT validate P or Q.

    The bare inverse round trip Seq(P,Q) cancels and therefore cannot validate
    either factor: P maps j^- to a wrong j^+ and Q maps it back. This is
    evidence about the pair only. It is NOT a claim that every composed use of
    P cancels -- test 7 below is a composed use that does not.
    """
    r, U, sem, lk = _framed(Seq(P_witness(), Q_witness()), materialize)
    assert lk < ATOL, f"Seq(P,Q): leakage {lk:.6f}"
    np.testing.assert_allclose(sem, np.eye(6), atol=ATOL, rtol=0.0)


# ---------------------------------------------------------------------------
# 7. P ; NPlusMap(H,Id,Id) ; Q -- a real consumer between them
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("materialize", MODES)
def test_P_then_branchmap_then_Q_requires_H_plus_I_plus_I(materialize):
    """With a genuine branch map between them the errors no longer cancel."""
    mid = NPlusMap((IA, IA, IA), (Hg(0, IA), Id(IA), Id(IA)))
    term = Seq(Seq(P_witness(), mid), Q_witness())
    expected = np.zeros((6, 6), complex)
    expected[0:2, 0:2] = H_M
    expected[2:4, 2:4] = np.eye(2)
    expected[4:6, 4:6] = np.eye(2)
    r, U, sem, lk = _framed(term, materialize)
    assert lk < ATOL, f"P;map;Q: leakage {lk:.6f} (expected 1/sqrt(2) today)"
    np.testing.assert_allclose(sem, expected, atol=ATOL, rtol=0.0)
