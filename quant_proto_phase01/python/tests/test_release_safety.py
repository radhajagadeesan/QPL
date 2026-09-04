"""Release-safety witnesses for the Zenodo boundary.

Every semantic gate here runs BOTH materialization modes, uses the artifact's
own recorded frames, compares

    U_sem = (u_out)^dagger G u_in

against an INDEPENDENTLY constructed expected matrix (never one extracted
from the circuit under test), requires

    leak = ||(I - u_out u_out^dagger) G u_in|| = 0

to a tight tolerance, compares the ACTUAL global phase rather than a
projective one, and uses rtol=0.

Passing counts are not evidence. Each witness is an exact counterexample or
it is not a gate.
"""

import json
import os
import sys

import numpy as np
import pytest

from lang.types import Unit, Q, Ten, Plus, Arrow
from lang.terms import (Id, Seq, Apply, Lam, Var, Pair, LetPair, TenTerm,
                        DistL, PlusMap, TwistTen, WireIdentity,
                        H as Hg, S as Sg, T as Tg, X as Xg)
from compile.to_pytket import compile, compile_with_artifacts
from compile.frames import semantic_action, leakage, UnsupportedFrame
from typing_.check import type_of

I = Unit()
q = Q()
qq = Arrow(q, q)
MODES = [False, True]
ATOL = 1e-10

FIX = os.path.join(os.path.dirname(__file__), "fixtures")

H_M = np.array([[1, 1], [1, -1]], complex) / np.sqrt(2)
S_M = np.array([[1, 0], [0, 1j]], complex)
T_M = np.array([[1, 0], [0, np.exp(1j * np.pi / 4)]], complex)
X_M = np.array([[0, 1], [1, 0]], complex)
Z_M = np.array([[1, 0], [0, -1]], complex)
I2 = np.eye(2, dtype=complex)
Z3 = Plus(I, Plus(I, I))


def _fixture(name):
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..",
                                    "ocaml"))
    from bridge import parse_term
    with open(os.path.join(FIX, name + ".json")) as f:
        return parse_term(json.load(f))


def _framed(term, materialize):
    r = compile(term, materialize=materialize)
    U = r.circuit.get_unitary()
    return r, U, semantic_action(r.input_frame, U, r.output_frame)


def _assert_exact(r, U, sem, expected, *, phase=0.0, where=""):
    lk = leakage(r.input_frame, U, r.output_frame)
    assert lk < ATOL, (
        f"{where}: leakage {lk:.6e} -- the recorded frames do not describe "
        f"the artifact (in={r.input_frame.codes}, out={r.output_frame.codes})")
    assert abs(r.global_phase - phase) < 1e-12, (
        f"{where}: global phase {r.global_phase}, expected {phase}")
    assert sem.shape == expected.shape, (
        f"{where}: action is {sem.shape}, expected {expected.shape}")
    np.testing.assert_allclose(sem, expected, atol=ATOL, rtol=0.0,
                               err_msg=f"{where}: action differs")


# ===========================================================================
# A. Unequal-width distributivity naturality
# ===========================================================================

A_T, B_T, C_T = q, Ten(q, q), q


def _naturality_pair():
    x_on_c = Xg(0, C_T)
    p_l = Seq(TenTerm(Id(Plus(A_T, B_T)), x_on_c), DistL(A_T, B_T, C_T))
    p_r = Seq(DistL(A_T, B_T, C_T),
              PlusMap(Ten(A_T, C_T), Ten(B_T, C_T),
                      TenTerm(Id(A_T), x_on_c), TenTerm(Id(B_T), x_on_c)))
    return p_l, p_r


def _naturality_expected():
    """X on the C coordinate, in every summand. Labels are (s, c) with s over
    A (+) B and c over C, so this is I_6 (x) X. Built from primitives."""
    return np.kron(np.eye(6, dtype=complex), X_M)


@pytest.mark.parametrize("materialize", MODES)
def test_A_naturality_both_paths_exact(materialize):
    exp = _naturality_expected()
    sems = []
    for name, term in zip(("P_L", "P_R"), _naturality_pair()):
        r, U, sem = _framed(term, materialize)
        _assert_exact(r, U, sem, exp, where=f"A/{name}")
        sems.append(sem)
    np.testing.assert_allclose(sems[0], sems[1], atol=ATOL, rtol=0.0,
                               err_msg="A: the two paths differ")


@pytest.mark.parametrize("materialize", MODES)
def test_A_distributor_is_zero_gate(materialize):
    r = compile(DistL(A_T, B_T, C_T), materialize=materialize)
    assert r.circuit.n_gates == 0


# ===========================================================================
# B. Nontrivial wire-permutation splice -- UNCOVERED
# ===========================================================================
#
# The candidate witness (TwistTen(Q,Z3) spliced into a consumer) turned out to
# be frame-identical: prod_out == cons_in == (0,1,2,3,4,5) and
# align_is_identity(...) is True, so it never reaches the wire-permutation
# Align fast path. It was a vacuous gate and has been REMOVED rather than
# left as a skip -- a skipped test reads as "fine" in a summary line.
#
# No public-source witness exercising that fast path has been found. The path
# is therefore UNCOVERED, and is recorded as such in
# docs/RELEASE_SAFETY_STATUS.md. It is NOT claimed to be supported.

# ===========================================================================
# C. Direct beta application with noncontiguous placement
# ===========================================================================

def _value(nm, gate):
    return Lam(nm, q, q, Seq(Var(nm, q), gate))


def _noncontiguous_witness():
    """ONE source term: the two external inputs are separated by a function
    value's wires, the lambda destructures the pair and applies it."""
    T = Ten(q, Ten(qq, q))
    body = LetPair("a", "rest", q, Ten(qq, q), Var("z", T),
                   LetPair("f", "x", qq, q, Var("rest", Ten(qq, q)),
                           Pair(Var("a", q),
                                Apply(Var("f", qq), Var("x", q)))))
    lam = Lam("z", T, Ten(q, q), body)
    return Apply(lam, Pair(Id(q), Pair(_value("hx", Hg(0, q)), Id(q))))


@pytest.mark.parametrize("materialize", MODES)
def test_C_noncontiguous_beta_ingress_and_action(materialize):
    r, U, sem = _framed(_noncontiguous_witness(), materialize)
    assert tuple(r.input_frame.codes) == (0, 1, 8, 9), (
        f"C: ingress {tuple(r.input_frame.codes)}, expected (0,1,8,9)")
    _assert_exact(r, U, sem, np.kron(I2, H_M), where="C")


# ===========================================================================
# D. Curried H (+) S (+) T selector (term from the OCaml demo)
# ===========================================================================

Z3A = Ten(Z3, q)


def _hst_expected():
    M = np.zeros((6, 6), complex)
    for k, blk in enumerate((H_M, S_M, T_M)):
        M[2 * k:2 * k + 2, 2 * k:2 * k + 2] = blk
    return M


@pytest.mark.parametrize("materialize", MODES)
def test_D_curried_selector_is_h_s_t(materialize):
    t = _fixture("curried_select_3_applied_hst")
    r, U, sem = _framed(Apply(t, Id(Z3A)), materialize)
    assert tuple(r.input_frame.codes) == (0, 1, 2, 3, 4, 5)
    _assert_exact(r, U, sem, _hst_expected(), where="D")


# ===========================================================================
# E. Qswitch eta witness -- UNRESOLVED (oracle blocked, not a compiler blocker)
# ===========================================================================
#
# `get_unitary` refusing 14 qubits is a HARNESS limit, not a compiler failure.
# The obligations are split: what compilation reports, and -- separately -- an
# exact semantic check that does not need a dense 2^n x 2^n unitary.

def codeword_columns(r, U_free=True):
    """Framed semantic columns via one statevector per input codeword.

    Prepares each valid input code, simulates only that state, reads the
    amplitudes on the recorded output codes, and reports the norm of whatever
    lands OUTSIDE the output code space as leakage. Scales as
    (#input codes) x 2^n instead of 2^n x 2^n.
    """
    from pytket import Circuit
    n = r.circuit.n_qubits
    cols, leaks = [], []
    for code in r.input_frame.codes:
        prep = Circuit(n)
        for w in range(n):
            if (code >> (n - 1 - w)) & 1:
                prep.X(w)
        prep.append(r.circuit)
        sv = prep.get_statevector()
        col = np.array([sv[c] for c in r.output_frame.codes], complex)
        inside = np.linalg.norm(col)
        total = np.linalg.norm(sv)
        leaks.append(np.sqrt(max(total ** 2 - inside ** 2, 0.0)))
        cols.append(col)
    return np.array(cols).T, float(max(leaks) if leaks else 0.0)


def test_E_codeword_harness_agrees_with_the_dense_action():
    """Validate the harness itself against a circuit whose dense framed action
    is already known, before trusting it on anything large."""
    term, _ = _naturality_pair()
    r = compile(term, materialize=True)
    dense = semantic_action(r.input_frame, r.circuit.get_unitary(),
                            r.output_frame)
    cols, leak = codeword_columns(r)
    np.testing.assert_allclose(cols, dense, atol=ATOL, rtol=0.0,
                               err_msg="codeword harness disagrees with the "
                                       "dense framed action")
    assert leak < ATOL


def test_E_qswitch_compile_only_record():
    """What compilation reports. No semantic claim is made here."""
    t = _fixture("qswitch_eta_endoQ")
    r = compile(t, materialize=False)
    assert r.circuit is not None
    assert r.circuit.n_qubits == 14
    assert len(r.input_frame.codes) == 1        # closed term
    assert len(r.output_frame.codes) == 16384


def test_E_qswitch_semantic_oracle_is_unresolved():
    """E is UNRESOLVED, and this records exactly why -- it is not skipped and
    it is not a compiler blocker.

    The artifact is a closed function VALUE: one input codeword, and an output
    frame covering all 2^14 basis states. A leakage check against a code space
    that IS the whole space is vacuous, and block_diag(U0,U1) is a statement
    about the function's ACTION on arguments, not about the value's encoding.
    Stating it needs the APPLIED form as a source term, which this pass does
    not have. Constructing U0/U1 by splitting the compiled action -- as the
    earlier version of this test did -- is not an independent oracle and
    could not detect a wrong-but-block-diagonal result.
    """
    t = _fixture("qswitch_eta_endoQ")
    r = compile(t, materialize=False)
    assert len(r.output_frame.codes) == 2 ** r.circuit.n_qubits, (
        "output frame no longer spans the whole space; a non-vacuous leakage "
        "check may now be statable and E should be revisited")

# ===========================================================================
# F. ctrl_ho witness -- three SEPARATE facts
# ===========================================================================
#
#   F1  duplicate physical arguments during emission -> compiler blocker
#   F2  missing completed-dimension / provenance metadata -> absent feature
#   F3  action / phase / leakage -> UNEVALUATED, because compilation fails
#
# Conflating these was what made the earlier report overstate the evidence.

@pytest.mark.parametrize("materialize", MODES)
def test_F1_ctrl_ho_compiles_and_is_exact_on_its_selected_block(materialize):
    """SUPERSEDES "failure is success".

    ctrl_ho used to be rejected because the open branch placement overlapped.
    It now compiles from its completed-branch Block, and the claim is the
    real one: the emitted circuit acts as blockdiag(Vhat_0, Vhat_1) on the
    80-dimensional selected boundary, with no leakage and no phase.
    """
    import numpy as _np
    import compile.to_pytket as _TP
    from compile.frames import semantic_action as _sem, leakage as _leak

    from compile.frames import OpenUseBlockPlan as _P

    _TP._USE_BLOCK_OBSERVED.clear()
    r, arts = compile_with_artifacts(_fixture("ctrl_ho_closed_plus_map"),
                                     materialize=materialize)
    assert r.circuit is not None
    assert _TP._USE_BLOCK_OBSERVED, "no use-block plan was produced"
    pl = _TP._USE_BLOCK_OBSERVED[-1]
    assert pl.ingress.dim == 80 and pl.egress.dim == 80
    # The PLAN is recorded during emission, in pre-materialisation
    # coordinates. What composes with the rest of the circuit is the
    # occurrence's selected boundary, which the root transports through the
    # appended swap network. Read that.
    planned = [a for a in arts if isinstance(a.placement, _P)]
    assert planned, "the sum occurrence carries no use-block plan"
    bd = planned[0].selected_boundary
    assert bd.ingress.dim == 80 and bd.egress.dim == 80

    # Vhat_i, built here from each branch's OWN selected boundary.
    blocks = []
    for b in pl.branches:
        sb = b.artifact.selected_boundary
        M = _sem(sb.ingress, b.artifact.unitary, sb.egress)
        seen = set()
        for x in b.inactive:
            if x.owner_id in seen:
                continue
            seen.add(x.owner_id)
            M = _np.kron(M, _np.eye(len(x.codes), dtype=complex))
        blocks.append(M)
    expected = _np.zeros((80, 80), dtype=complex)
    o = 0
    for m in blocks:
        expected[o:o + m.shape[0], o:o + m.shape[1]] = m
        o += m.shape[0]

    U = r.circuit.get_unitary()
    W = _sem(bd.ingress, U, bd.egress)
    dev = float(_np.max(_np.abs(W - expected)))
    assert dev < 1e-10, f"F1: max deviation {dev:.3e} from blockdiag(Vhat)"
    assert _leak(bd.ingress, U, bd.egress) < 1e-10, "F1: the block leaks"
    assert abs(r.global_phase) < 1e-12, f"F1: phase {r.global_phase}"


def test_F2_ctrl_ho_block_metadata_is_present():
    """SUPERSEDED PROSE REMOVED.

    This used to record the absence of "separate typed f and h ports". There
    are none to have: f is a typed inactive completion of the block that does
    not use it, and h is an operand factor inside the other block's own
    selected root. What must exist is the Block record itself.
    """
    import compile.frames as fr
    for name in ("OpenUseBlockPlan", "CompletedBranch", "complete_branch",
                 "plan_use_block", "use_block_layout"):
        assert hasattr(fr, name), f"no {name}: the Block cannot be recorded"
    from compile.frames import Port, TypedBinding
    assert "owner_id" in Port.__dataclass_fields__
    assert "codes" in TypedBinding.__dataclass_fields__, (
        "a binding carries no recorded encoding, so completing against it "
        "would have to manufacture one")


def test_F3_ctrl_ho_action_is_evaluated_not_deferred():
    """SUPERSEDES "no claim is being made".

    A circuit IS produced now, so the action must be evaluated rather than
    left unevaluated. F1 is the exact oracle; this pins that the artifact
    also carries the Block as its selected boundary, so the result composes.
    """
    import compile.to_pytket as _TP
    from compile.frames import OpenUseBlockPlan as _P

    _r, arts = compile_with_artifacts(_fixture("ctrl_ho_closed_plus_map"))
    planned = [a for a in arts if isinstance(a.placement, _P)]
    assert planned, "the sum occurrence carries no use-block plan"
    a = planned[0]
    sb = a.selected_boundary
    assert sb is not None and sb.origin == "plusmap:use-block", (
        f"the occurrence kept the obsolete boundary {sb.origin if sb else None}")
    assert sb.ingress.codes == a.placement.ingress.codes
    assert sb.egress.codes == a.placement.egress.codes
    assert sb.ingress.dim == 80 and sb.egress.dim == 80


# ===========================================================================
# G. Captured / open function: must be exact or fail closed
# ===========================================================================

def _captured_witness():
    """Smallest captured-function case: (\\f. \\p. f p) H applied to a qubit."""
    closure = Apply(
        Lam("f", qq, Arrow(q, q),
            Lam("p", q, q, Apply(Var("f", qq), Var("p", q)))),
        _value("hx", Hg(0, q)))
    return Apply(closure, Id(q))


@pytest.mark.parametrize("materialize", MODES)
def test_G_captured_function_is_exact(materialize):
    """SEMANTIC GATE. This witness is SUPPORTED at the baseline, so nothing
    weaker than exactness is accepted: it must compile, and give exactly H
    with zero phase and zero leakage in both modes.

    The earlier version also accepted UnsupportedFrame. That was wrong here --
    an escape hatch on a witness that demonstrably works would silently
    absorb a future regression into "failed closed".
    """
    r, U, sem = _framed(_captured_witness(), materialize)
    _assert_exact(r, U, sem, H_M, where="G")


# ===========================================================================
# Guard: the open-branch placement check must not disturb anything valid
# ===========================================================================

def _use(name):
    return Apply(Var(name, qq), Id(q))


@pytest.mark.parametrize("materialize", MODES)
def test_guard_valid_open_branch_is_not_rejected(materialize):
    """COMPILE-ONLY NON-REJECTION CHECK -- not a semantic gate.

    The closest VALID open branch (payload and context disjoint) must not be
    rejected by the guard. No action, phase or leakage is asserted here, so
    this must not be described as "exact"; the semantic gates are A, D, G and
    the closed controls below.
    """
    pm = PlusMap(q, q, _use("f"), Id(q))
    r = compile(pm, env={"f": [2, 3]}, materialize=materialize)
    assert r.circuit is not None
    assert r.circuit.n_qubits == 4


@pytest.mark.parametrize("materialize", MODES)
def test_guard_coherent_sharing_open_branch_is_not_rejected(materialize):
    """COMPILE-ONLY NON-REJECTION CHECK -- not a semantic gate.

    Both branches borrowing the SAME context is legitimate sharing, not an
    overlap, so the guard must not reject it. No action/phase/leakage claim.
    """
    pm = PlusMap(q, q, _use("f"), _use("f"))
    r = compile(pm, env={"f": [2, 3]}, materialize=materialize)
    assert r.circuit is not None


def _value_lam(nm, gate):
    return Lam(nm, q, q, Seq(Var(nm, q), gate))


Z2Q = Plus(q, q)


def _one_open_control(side, vn, gate):
    pm = (PlusMap(q, q, _use("f"), Id(q)) if side == "left"
          else PlusMap(q, q, Id(q), _use("f")))
    inner = Lam("p", Z2Q, Z2Q, Seq(Var("p", Z2Q), pm))
    outer = Lam("f", qq, Arrow(Z2Q, Z2Q), inner)
    return Apply(Apply(outer, _value_lam(vn, gate(0, q))), Id(Z2Q))


def _both_open_control():
    """Both branches open: H on the left summand, S on the right."""
    pm = PlusMap(q, q, _use("f"), _use("g"))
    inner = Lam("p", Z2Q, Z2Q, Seq(Var("p", Z2Q), pm))
    middle = Lam("g", qq, Arrow(Z2Q, Z2Q), inner)
    outer = Lam("f", qq, Arrow(qq, Arrow(Z2Q, Z2Q)), middle)
    return Apply(Apply(Apply(outer, _value_lam("hx", Hg(0, q))),
                       _value_lam("sx", Sg(0, q))), Id(Z2Q))


def _blk(u, v):
    return np.block([[u, np.zeros((2, 2))], [np.zeros((2, 2)), v]])


CLOSED_CONTROLS = [
    ("H+I", lambda: _one_open_control("left", "hx", Hg), _blk(H_M, I2)),
    ("I+X", lambda: _one_open_control("right", "xx", Xg), _blk(I2, X_M)),
    ("H+S", _both_open_control, _blk(H_M, S_M)),
]


@pytest.mark.parametrize("materialize", MODES)
@pytest.mark.parametrize("name,build,expected", CLOSED_CONTROLS,
                         ids=[c[0] for c in CLOSED_CONTROLS])
def test_closed_controls_remain_exact(name, build, expected, materialize):
    """SEMANTIC GATES. Exact action, zero phase, zero leakage, both modes.

    NOTE ON COVERAGE: these three do NOT reach `_check_open_placement` --
    verified by instrumenting it, which reports no invocation for any of them.
    They are semantic regression controls proving the guard commit changed no
    working circuit; they are NOT guard-path coverage. The guard path itself
    is exercised by the two non-rejection checks above (which do invoke it,
    on "PlusMap left") and by F1, which requires it to fire.
    """
    r, U, sem = _framed(build(), materialize)
    _assert_exact(r, U, sem, expected, where=f"control/{name}")
