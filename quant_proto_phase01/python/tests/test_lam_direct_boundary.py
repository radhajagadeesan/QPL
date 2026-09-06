"""Direct-boundary Lam allocation: the public-root register IS the carrier.

The boundary semantics selects each public compilation root's carrier
(`select_frames`, consulted before the register exists).  Only (+) may
introduce representation coordinates — its tag and prescribed
block/padding coordinates, which are already part of the selected
coproduct carrier.  No non-(+) constructor may create surviving root
wires outside that carrier: nested Lam compilation in particular must
not produce a root `fn_layout` residual to legitimize allocator
over-approximation.

History pinned here: `_internal_width(Lam)` used to compute
`ctx_w + body_internal`, counting the captured context twice (a free
variable is typed as the identity on its own wires — typing_/check
`type_of(Var) -> (ty, ty)` — so the context is already inside the
body's judgment and its internal width).  Compounding per nesting
level, the abstract QSwitch allocated 12 wires against its selected
8-wire carrier, with wires 8-11 surviving only as a root
('fn_layout', 'residual') port, untouched by every command and fixed
by the pending permutation [6,7,0,1,2,3,4,5,8,9,10,11].  The v1.0.0
12-wire artifact's recorded facts and framed semantic action are kept
in fixtures/qswitch_abstract_sealed_v100_oracle.npz and used below as
the equivalence oracle (restriction through its recorded |0...0>
spectator embedding IS its framed action, since the spectator
coordinates are fixed at 0 in the recorded codes).
"""

import json
import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..",
                                "ocaml"))
from bridge import parse_term  # noqa: E402

from lang.terms import (Id, Seq, Pair, LetPair, Var, Lam, Apply, PlusMap,
                        NPlusMap, DistL, UndistL, TenTerm, H, EncodeQubit)
from lang.types import Q, Unit, Ten, Plus, Arrow
import compile.to_pytket as TP
from compile.to_pytket import compile, select_frames, TypeCheckError

FIX = os.path.join(os.path.dirname(__file__), "fixtures")
MODES = (False, True)
ATOL = 1e-9


def _fixture(name):
    with open(os.path.join(FIX, name + ".json")) as f:
        return parse_term(json.load(f))


# ---------------------------------------------------------------------------
# Minimal dense statevector applier (pytket's simulator refuses larger
# registers; command unitaries stay tiny).  Big-endian: wire 0 is the MSB.
# ---------------------------------------------------------------------------

def _op_unitary(op):
    try:
        return np.asarray(op.get_unitary())
    except Exception:
        return np.asarray(op.get_box().get_unitary())


def _apply_cmd(state, U, qubits, n):
    k = len(qubits)
    rest = [i for i in range(n) if i not in qubits]
    psi = state.reshape([2] * n)
    psi = np.transpose(psi, list(qubits) + rest).reshape(2 ** k, -1)
    psi = (U @ psi).reshape([2] * k + [2] * (n - k))
    return np.transpose(psi, np.argsort(list(qubits) + rest)).reshape(-1)


def _run(circ, in_code):
    n = circ.n_qubits
    state = np.zeros(2 ** n, complex)
    state[in_code] = 1.0
    for cmd in circ.get_commands():
        state = _apply_cmd(state, _op_unitary(cmd.op),
                           [q.index[0] for q in cmd.qubits], n)
    return state * np.exp(1j * np.pi * float(circ.phase))


def _framed_columns(r):
    cols, leaks = [], []
    for code in r.input_frame.codes:
        sv = _run(r.circuit, code)
        col = np.array([sv[c] for c in r.output_frame.codes], complex)
        inside, total = np.linalg.norm(col), np.linalg.norm(sv)
        leaks.append(np.sqrt(max(total ** 2 - inside ** 2, 0.0)))
        cols.append(col)
    return np.array(cols).T, float(max(leaks) if leaks else 0.0)


def _full_operator(r):
    """The artifact's full register operator with the pending permutation
    applied (new wire j reads old wire perm.new_to_old[j])."""
    n = r.circuit.n_qubits
    W = np.zeros((2 ** n, 2 ** n), complex)
    for c in range(2 ** n):
        W[:, c] = _run(r.circuit, c)
    p = list(r.perm.new_to_old)
    if p != list(range(n)):
        M = np.zeros((2 ** n, 2 ** n))
        for idx in range(2 ** n):
            o = 0
            for j in range(n):
                if (idx >> (n - 1 - p[j])) & 1:
                    o |= 1 << (n - 1 - j)
            M[o, idx] = 1.0
        W = M @ W
    return W


def _root_fn_ports(r):
    return [p for p in (list(r.input_ports or []) + list(r.output_ports or []))
            if p.name == "fn_layout"]


def _touched(r):
    return {q.index[0] for c in r.circuit.get_commands() for q in c.qubits}


# ===========================================================================
# A. Abstract QSwitch: exactly the selected 8-wire carrier, both modes
# ===========================================================================

class TestQSwitchDirectBoundary:

    @pytest.fixture(scope="class")
    def term(self):
        return _fixture("qswitch_abstract_sealed")

    @pytest.fixture(scope="class")
    def oracle(self):
        return np.load(os.path.join(
            FIX, "qswitch_abstract_sealed_v100_oracle.npz"))

    def test_selected_carrier_is_eight(self, term):
        fi, fo = select_frames(term)
        assert fi.n_qubits == fo.n_qubits == 8

    @pytest.mark.parametrize("materialize", MODES)
    def test_register_is_exactly_the_carrier(self, term, materialize):
        r = compile(term, materialize=materialize)
        assert r.circuit.n_qubits == 8
        assert r.input_frame.n_qubits == r.output_frame.n_qubits == 8

    @pytest.mark.parametrize("materialize", MODES)
    def test_no_root_fn_layout_residual(self, term, materialize):
        r = compile(term, materialize=materialize)
        assert _root_fn_ports(r) == []

    def test_same_six_logical_gates_and_phase(self, term, oracle):
        r = compile(term, materialize=False)
        cmds = r.circuit.get_commands()
        assert len(cmds) == int(oracle["log_gates"][0]) == 6
        assert r.global_phase == 0.0
        # commands act only on the retained carrier — and the v1.0.0
        # artifact's commands never left it either, so the gate list is
        # unchanged wire-for-wire
        assert _touched(r) <= set(range(8))

    def test_pending_permutation_is_the_tight_form(self, term, oracle):
        r = compile(term, materialize=False)
        v100 = list(oracle["log_perm"])           # [6,7,0,1,2,3,4,5,8,9,10,11]
        fn = set(int(w) for w in oracle["log_fn_wires"])  # {8,9,10,11}
        tight = [w for w in v100 if w not in fn]
        assert tight == [6, 7, 0, 1, 2, 3, 4, 5]
        assert list(r.perm.new_to_old) == tight

    def test_materialized_permutation_is_identity(self, term):
        r = compile(term, materialize=True)
        assert list(r.perm.new_to_old) == list(range(8))
        # the required permutation-realising SWAPs are allowed here; no
        # fixed six-command requirement in this mode
        assert _touched(r) <= set(range(8))

    @pytest.mark.parametrize("materialize", MODES)
    def test_exact_semantic_action_vs_v100_artifact(self, term, oracle,
                                                    materialize):
        """The v1.0.0 12-wire artifact, restricted through its recorded
        |0000> spectator embedding, is the equivalence oracle."""
        r = compile(term, materialize=materialize)
        sem, leak = _framed_columns(r)
        key = "mat" if materialize else "log"
        assert leak < ATOL
        assert float(oracle[f"{key}_leak"][0]) < ATOL
        np.testing.assert_allclose(sem, oracle[f"{key}_sem"],
                                   atol=ATOL, rtol=0.0)

    @pytest.mark.parametrize("materialize", MODES)
    def test_full_operator_equals_v100_restricted(self, term, materialize):
        """The STRONG restricted-equivalence oracle: the repaired artifact's
        full 256x256 operator (pending permutation applied) equals the
        v1.0.0 12-wire artifact's operator restricted through its recorded
        |0000> spectator embedding on wires 8-11 -- captured column by
        column from the pristine pre-fix tree, where the 12-wire operator
        was verified never to leave that block (zero leakage, unitary
        restriction). The single-ingress-column check above is necessary
        but weak for a value artifact (its ingress is dim 1); this pins the
        whole carrier action."""
        op = np.load(os.path.join(
            FIX, "qswitch_abstract_sealed_v100_oracle_op.npz"))
        key = "mat" if materialize else "log"
        assert float(op[f"{key}_leak"][0]) < ATOL
        r = compile(term, materialize=materialize)
        W = _full_operator(r)
        np.testing.assert_allclose(W, op[f"{key}_W"], atol=ATOL, rtol=0.0)

    @pytest.mark.parametrize("materialize", MODES)
    def test_value_is_pure_wiring(self, term, materialize):
        """Independent structural property from the spec (§4.4/§5: the
        abstract switch is boundary exposure + coherent routing -- "most
        constructs are wiring"): the artifact's full operator is a 0/1
        permutation matrix with zero global phase. Not derived from any
        compiler output."""
        r = compile(term, materialize=materialize)
        assert r.global_phase == 0.0
        W = _full_operator(r)
        assert np.allclose(np.abs(W) * (1 - np.abs(W)), 0, atol=ATOL)
        assert np.allclose(W, W.real, atol=ATOL)
        assert np.allclose(np.abs(W).sum(axis=0), 1.0, atol=ATOL)
        assert np.allclose(np.abs(W).sum(axis=1), 1.0, atol=ATOL)


@pytest.mark.parametrize("materialize", MODES)
@pytest.mark.parametrize("name, F, G", [
    ("qswitch_hs_hom",
     np.array([[1, 1], [1, -1]], complex) / np.sqrt(2),   # H
     np.diag([1.0 + 0j, 1j])),                             # S
    ("qswitch_xz_hom",
     np.array([[0, 1], [1, 0]], complex),                  # X
     np.diag([1.0 + 0j, -1.0 + 0j])),                      # Z
])
def test_qswitch_instantiated_spec_oracle(name, F, G, materialize):
    """Independent QSwitch semantic oracle, derived from the specification
    and never from compiler output:

        b = 0 :  q -> f(g(q))     (apply g then f)  =>  block  F @ G
        b = 1 :  q -> g(f(q))     (apply f then g)  =>  block  G @ F

    (counterparts/surface_programs.ml cp_qswitch: `case b ~zero:(f (g w))
    ~one_:(g (f w))`; spec §5). The instantiated switches are the
    CERTIFIED content route for the case-bodied abstract qswitch value:
    wire-level Apply of op values into it is refused by the canonical-
    normal-form AppCut (recorded Phase-2 finding, run_counterparts.ml),
    and the OCaml counterpart suite proves `qswitch_hs sugar == meta-level
    QSwitch[H,S]` (row 1) plus the row-24 family by circuit equality, and
    compiles the abstract value itself (row 11). Together with the full-
    operator restricted equivalence above, this supplies the two required
    acceptance legs. Two asymmetric pairs (HS: FG != GF; XZ: FG = -GF) so
    an order-insensitive artifact cannot pass."""
    assert not np.allclose(F @ G, G @ F, atol=ATOL)
    expected = np.zeros((4, 4), complex)
    expected[0:2, 0:2] = F @ G
    expected[2:4, 2:4] = G @ F
    r = compile(_fixture(name), materialize=materialize)
    assert r.circuit.n_qubits == 2
    sem, leak = _framed_columns(r)
    assert leak < ATOL
    np.testing.assert_allclose(sem, expected, atol=ATOL, rtol=0.0)


# ===========================================================================
# B. The four excess families from the investigation, as permanent gates
# ===========================================================================

@pytest.mark.parametrize("name, width", [
    ("qswitch_abstract_sealed", 8),      # was 12
    ("compose2_abstract_sealed", 6),     # was 8
    ("qswitch_eta_sealed", 14),          # was 34
    ("curried_select_3_abstract", 12),   # was 16
])
@pytest.mark.parametrize("materialize", MODES)
def test_excess_families_are_tight(name, width, materialize):
    t = _fixture(name)
    fi, fo = select_frames(t)
    assert max(fi.n_qubits, fo.n_qubits) == width
    r = compile(t, materialize=materialize)
    assert r.circuit.n_qubits == width
    assert _root_fn_ports(r) == []
    assert _touched(r) <= set(range(width))


# ===========================================================================
# C. Adversarial coverage for the corrected recurrence
# ===========================================================================

def _iq():
    return Ten(Unit(), Q())


def _qq():
    return Arrow(Q(), Q())


def _h_value():
    return Lam("hx", Q(), Q(), Seq(Var("hx", Q()), H(0, Q())))


def _open_plusmap_ctrl_lam():
    """λf:(Q⊸Q). λba:(Bool⊗Q). (dist ; [id | id_I⊗f] ; undist)(ba) —
    the ctrl combinator with an OPEN PlusMap branch capturing f."""
    iq = _iq()
    right_open = LetPair(
        "i", "a", Unit(), Q(), Id(iq),
        Pair(Var("i", Unit()), Apply(Var("f", _qq()), Var("a", Q()))))
    pipeline = Seq(DistL(Unit(), Unit(), Q()),
                   Seq(PlusMap(iq, iq, Id(iq), right_open),
                       UndistL(Unit(), Unit(), Q())))
    bq = Ten(Plus(Unit(), Unit()), Q())
    return Lam("f", _qq(), Arrow(bq, bq),
               Lam("ba", bq, bq, Seq(Var("ba", bq), pipeline)))


def _closed_ctrl_h():
    iq = _iq()
    return Seq(DistL(Unit(), Unit(), Q()),
               Seq(PlusMap(iq, iq, Id(iq), TenTerm(Id(Unit()), H(0, Q()))),
                   UndistL(Unit(), Unit(), Q())))


class TestAdversarial:

    @pytest.mark.parametrize("materialize", MODES)
    def test_open_plusmap_under_lam(self, materialize):
        t = _open_plusmap_ctrl_lam()
        fi, fo = select_frames(t)
        want = max(fi.n_qubits, fo.n_qubits)
        r = compile(t, materialize=materialize)
        assert r.circuit.n_qubits == want == 6
        assert _root_fn_ports(r) == []

    @pytest.mark.parametrize("materialize", MODES)
    def test_open_plusmap_under_lam_applied_is_exact(self, materialize):
        """Captured context is retained exactly once: applying the open-
        branch ctrl to H must equal the closed ctrl(H) — a duplicated or
        dropped context would change the action.  Both sides β-reduce to a
        function VALUE of type (Bool⊗Q)⊸(Bool⊗Q), so the comparison is
        between the two value artifacts (dim-1 ingress; the prepared
        function state determines the function exactly)."""
        bq = Ten(Plus(Unit(), Unit()), Q())
        applied = Apply(_open_plusmap_ctrl_lam(), _h_value())
        closed_value = Lam("cb", bq, bq, Seq(Var("cb", bq), _closed_ctrl_h()))
        ra = compile(applied, materialize=materialize)
        rc = compile(closed_value, materialize=materialize)
        assert ra.circuit.n_qubits == rc.circuit.n_qubits == 4
        sa, la = _framed_columns(ra)
        sc, lc = _framed_columns(rc)
        assert la < ATOL and lc < ATOL
        np.testing.assert_allclose(sa, sc, atol=ATOL, rtol=0.0)

    @pytest.mark.parametrize("materialize", MODES)
    def test_open_nplusmap_under_lam(self, materialize):
        """λinput. let f0,f1,f2,s = input in NPlusMap(open branches)(s) —
        the tupled three-branch selector with per-branch captured fns."""
        qq, iq = _qq(), _iq()

        def branch(fn):
            return LetPair("i", "a", Unit(), Q(), Id(iq),
                           Pair(Var("i", Unit()),
                                Apply(Var(fn, qq), Var("a", Q()))))

        sum3 = Plus(iq, Plus(iq, iq))
        pm = NPlusMap((iq, iq, iq), (branch("f0"), branch("f1"),
                                     branch("f2")))
        input_ty = Ten(qq, Ten(qq, Ten(qq, sum3)))
        body = LetPair(
            "f0", "r1", qq, Ten(qq, Ten(qq, sum3)),
            Var("input", input_ty),
            LetPair("f1", "r2", qq, Ten(qq, sum3),
                    Var("r1", Ten(qq, Ten(qq, sum3))),
                    LetPair("f2", "s", qq, sum3,
                            Var("r2", Ten(qq, sum3)),
                            Seq(Var("s", sum3), pm))))
        t = Lam("input", input_ty, sum3, body)
        fi, fo = select_frames(t)
        want = max(fi.n_qubits, fo.n_qubits)
        r = compile(t, materialize=materialize)
        assert r.circuit.n_qubits == want
        assert _root_fn_ports(r) == []
        # the (+) tag coordinates of the summand frames survive: the output
        # frame still describes the 3-summand coproduct carrier
        assert r.output_frame.n_qubits == want

    @pytest.mark.parametrize("materialize", MODES)
    def test_lam_with_captured_context(self, materialize):
        t = Lam("x", Q(), Arrow(Q(), Ten(Q(), Q())),
                Lam("y", Q(), Ten(Q(), Q()),
                    Pair(Var("y", Q()), Var("x", Q()))))
        fi, fo = select_frames(t)
        r = compile(t, materialize=materialize)
        assert r.circuit.n_qubits == max(fi.n_qubits, fo.n_qubits) == 4
        assert _root_fn_ports(r) == []
        sem, leak = _framed_columns(r)
        assert leak < ATOL and abs(np.linalg.norm(sem) - 1.0) < ATOL

    @pytest.mark.parametrize("materialize", MODES)
    def test_context_free_nested_lam(self, materialize):
        """A closed Lam nested under an outer Lam (empty inner context):
        the corrected recurrence must not shrink below the carrier either.
        (Pair(fn_value, data) would be another witness, but that shape hits
        a pre-existing, fix-independent par-route limitation.)"""
        t = Lam("x", Q(), Q(), Apply(_h_value(), Var("x", Q())))
        fi, fo = select_frames(t)
        r = compile(t, materialize=materialize)
        assert r.circuit.n_qubits == max(fi.n_qubits, fo.n_qubits) == 2
        assert _root_fn_ports(r) == []
        # Both roots are values of Q⊸Q; the nested context-free Lam must
        # prepare exactly the state its β-normal closed value prepares.
        sem, leak = _framed_columns(r)
        ref, leak_ref = _framed_columns(compile(_h_value(),
                                                materialize=materialize))
        assert leak < ATOL and leak_ref < ATOL
        np.testing.assert_allclose(sem, ref, atol=ATOL, rtol=0.0)

    @pytest.mark.parametrize("materialize", MODES)
    def test_sparse_datatype_selection_under_lam(self, materialize):
        """Arity-5 selector under Lam: sparse non-power-of-two codes stay
        sparse and ordered; (+) coordinates are carrier structure."""
        t = _fixture("select5_sealed")
        fi, fo = select_frames(t)
        r = compile(t, materialize=materialize)
        assert r.circuit.n_qubits == max(fi.n_qubits, fo.n_qubits) == 8
        assert _root_fn_ports(r) == []
        # This is a function-VALUE artifact: its egress frame is the sparse
        # function-layout carrier, strictly smaller than the full register
        # space (sparsity preserved; ordering of the code list is the
        # recorded embedding, not numeric order).
        codes = list(r.output_frame.codes)
        assert len(codes) == len(set(codes)) < 2 ** 8

    def test_modes_agree_on_sparse_selector(self):
        t = _fixture("select5_sealed")
        s0, l0 = _framed_columns(compile(t, materialize=False))
        s1, l1 = _framed_columns(compile(t, materialize=True))
        assert l0 < ATOL and l1 < ATOL
        np.testing.assert_allclose(s0, s1, atol=ATOL, rtol=0.0)


# ===========================================================================
# D. Refusals: allocator drift is an error, not a residual
# ===========================================================================

class TestRefusals:

    def test_inflated_closed_root_allocation_is_refused(self, monkeypatch):
        """A mutation reintroducing over-allocation (e.g. restoring
        ctx_w + body_internal, or any non-(+) request for extra root
        wires) must fail BEFORE circuit mutation — not survive as a
        root fn_layout residual."""
        t = _fixture("qswitch_abstract_sealed")
        real = TP.allocation_width
        monkeypatch.setattr(TP, "allocation_width",
                            lambda term, env=None: real(term, env) + 4)
        with pytest.raises(TypeCheckError) as e:
            compile(t)
        assert "carrier" in str(e.value)

    def test_plus_coordinates_do_not_trigger_refusal(self):
        """(+) tags and prescribed padding are selected carrier structure:
        sparse selectors and open sum dispatch compile without tripping the
        drift refusal."""
        compile(_fixture("select5_sealed"))
        compile(_fixture("ctrl_ho_closed_plus_map"))

    def test_legacy_encode_decode_policy_unchanged(self):
        """The excluded legacy EncodeQubit path keeps its documented
        widening; the refusal is scoped to unexplained drift."""
        r = compile(EncodeQubit())
        assert r.circuit.n_qubits == 2
