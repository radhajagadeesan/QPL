"""NF-1 Part E: Strategy B classification. TEST-ONLY -- no production change.

Strategy B is the asymmetric-split path: when one side of a binary PlusMap
carries more leaves than half the tag space, the emitter abandons controlled
dispatch and synthesizes one full unitary over the whole k+pw register.

The question this module answers is whether that synthesized block honours the
boundary transport its occurrence owes:

    (1) A_pre  J_i^- = K_i^-
    (2) B      K_i^- = K_i^+ G_i
    (3) A_post K_i^+ = J_i^+

with B the ACTUAL synthesized block.

ORACLE. The expected action is `block_diag(H, S, X, T)`, built here from the
four primitive matrices. It is deliberately never "agrees with some other
PlusMap compilation" -- two routes through the same emitter would share a
defect and agreeing would prove nothing.

OPACITY. Each witness wraps its multi-leaf branch in a `Seq`, which
`_try_flatten_plusmap` cannot decompose. That is asserted, not assumed: if
auto-flatten ever swallowed these they would silently stop testing Strategy B.
"""

import numpy as np
import pytest

from lang.types import Q, Plus, Ten, payload_width, flatten_plus
from lang.terms import (Id, Seq, TenTerm, PlusMap, NPlusMap, AssocPlusL,
                        AssocPlusR, H as Hg, S as Sg, X as Xg, T as Tg)
from compile.to_pytket import (compile, compile_with_artifacts, select_frames,
                               type_of, _try_flatten_plusmap)
from compile.frames import (semantic_action, leakage, pretty,
                            UnsupportedFrame)

q = Q()
L3 = Plus(Plus(q, q), q)
R3 = Plus(q, Plus(q, q))
MODES = [False, True]
ATOL = 1e-10

H_M = np.array([[1, 1], [1, -1]], complex) / np.sqrt(2)
S_M = np.diag([1, 1j]).astype(complex)
X_M = np.array([[0, 1], [1, 0]], complex)
T_M = np.diag([1, np.exp(1j * np.pi / 4)]).astype(complex)


def _block_diag(*blocks):
    n = sum(b.shape[0] for b in blocks)
    out = np.zeros((n, n), complex)
    at = 0
    for b in blocks:
        d = b.shape[0]
        out[at:at + d, at:at + d] = b
        at += d
    return out


HSXT = _block_diag(H_M, S_M, X_M, T_M)


# --- witnesses -------------------------------------------------------------

def map3_left():
    return PlusMap(Plus(q, q), q,
                   PlusMap(q, q, Hg(0, q), Sg(0, q)),
                   Xg(0, q))


def opaque_left3():
    return Seq(AssocPlusL(q, q, q),
               PlusMap(q, Plus(q, q),
                       Hg(0, q),
                       PlusMap(q, q, Sg(0, q), Xg(0, q))))


def SB31_witness():
    """Genuine opaque 3/1 split: n_left = 3 > half = 2."""
    return PlusMap(L3, q, opaque_left3(), Tg(0, q))


def opaque_right3():
    return Seq(AssocPlusR(q, q, q),
               PlusMap(Plus(q, q), q,
                       PlusMap(q, q, Sg(0, q), Xg(0, q)),
                       Tg(0, q)))


def SB13_witness():
    """Mirror 1/3 split."""
    return PlusMap(q, R3, Hg(0, q), opaque_right3())


WITNESSES = [("SB31", SB31_witness), ("SB13", SB13_witness)]


# --- path evidence ---------------------------------------------------------

def assert_strategy_b_selected(t, where):
    assert _try_flatten_plusmap(t) is None, (
        f"{where}: the Seq no longer blocks auto-flatten, so this witness "
        f"would stop testing Strategy B")
    r = compile(t, materialize=False, explain=True)
    sb = [l for l in r.log if "Strategy B" in l]
    assert len(sb) == 1, f"{where}: expected one Strategy B block, got {sb}"
    assert not any("Strategy A" in l for l in r.log), f"{where}: Strategy A"
    assert not any("NPlusMap(n=" in l for l in r.log), f"{where}: NPlusMap"
    _, arts = compile_with_artifacts(t)
    assert not [a for a in arts if isinstance(a.term, NPlusMap)], (
        f"{where}: a synthetic NPlusMap occurrence exists")
    return r


@pytest.mark.parametrize("name,mk", WITNESSES)
def test_strategy_b_is_the_selected_path(name, mk):
    assert_strategy_b_selected(mk(), name)


# --- semantics -------------------------------------------------------------

@pytest.mark.parametrize("name,mk", WITNESSES)
@pytest.mark.parametrize("materialize", MODES)
def test_exact_H_S_X_T(name, mk, materialize):
    t = mk()
    r = compile(t, materialize=materialize)
    U = r.circuit.get_unitary()
    assert r.circuit.n_qubits == 3
    assert r.input_frame.n_qubits == 3 and r.output_frame.n_qubits == 3
    assert tuple(r.input_frame.codes) == tuple(range(8))
    assert tuple(r.output_frame.codes) == tuple(range(8))
    assert abs(r.global_phase) < 1e-12, f"{name}: phase {r.global_phase}"
    assert leakage(r.input_frame, U, r.output_frame) < ATOL
    sem = semantic_action(r.input_frame, U, r.output_frame)
    np.testing.assert_allclose(sem, HSXT, atol=ATOL, rtol=0.0)


@pytest.mark.parametrize("name,mk", WITNESSES)
@pytest.mark.parametrize("materialize", MODES)
def test_off_sector_blocks_are_exactly_zero(name, mk, materialize):
    """Block-diagonality is a separate claim from equality to HSXT: a wrong
    result could match on the diagonal and still couple the leaves."""
    r = compile(mk(), materialize=materialize)
    sem = semantic_action(r.input_frame, r.circuit.get_unitary(),
                          r.output_frame)
    for a in range(4):
        for b in range(4):
            if a == b:
                continue
            blk = sem[2 * a:2 * a + 2, 2 * b:2 * b + 2]
            assert np.allclose(blk, 0, atol=ATOL), (
                f"{name}: off-sector block ({a},{b}) is nonzero:\n{blk}")


@pytest.mark.parametrize("name,mk", WITNESSES)
def test_both_materialization_modes_agree_exactly(name, mk):
    a = compile(mk(), materialize=False)
    b = compile(mk(), materialize=True)
    sa = semantic_action(a.input_frame, a.circuit.get_unitary(), a.output_frame)
    sb = semantic_action(b.input_frame, b.circuit.get_unitary(), b.output_frame)
    np.testing.assert_allclose(sa, sb, atol=ATOL, rtol=0.0)
    assert a.global_phase == b.global_phase


# --- non-zero offset -------------------------------------------------------

@pytest.mark.parametrize("materialize", MODES)
def test_SB31_at_a_nonzero_offset(materialize):
    """The synthesized 3-qubit block must sit on wires (1,2,3), not (0,1,2)."""
    import re
    t = TenTerm(Id(q), SB31_witness())
    r = compile(t, materialize=materialize)
    U = r.circuit.get_unitary()
    assert r.circuit.n_qubits == 4
    assert leakage(r.input_frame, U, r.output_frame) < ATOL
    assert abs(r.global_phase) < 1e-12
    np.testing.assert_allclose(
        semantic_action(r.input_frame, U, r.output_frame),
        np.kron(np.eye(2), HSXT), atol=ATOL, rtol=0.0)
    wires = sorted({int(w) for c in r.circuit.get_commands()
                    for w in re.findall(r"q\[(\d+)\]", str(c))})
    assert wires == [1, 2, 3], wires


# --- derivation-selected transport table -----------------------------------

def strategy_b_plan(t):
    """The StrategyBDensePlan the emitter actually recorded."""
    _, arts = compile_with_artifacts(t)
    plans = [a.plan for a in arts if a.plan is not None]
    assert len(plans) == 1, f"expected one Strategy B plan, got {len(plans)}"
    owners = [type(a.term).__name__ for a in arts if a.plan is not None]
    assert owners == ["PlusMap"], f"plan owner is {owners}"
    return plans[0]


def sector_table(t, branches):
    """J^-, J^+, K^-, K^+ per sector, read from the RECORDED plan.

    Strategy B takes K_i^- = J_i^- and K_i^+ = J_i^+, so (1) and (3) are
    identity by construction and no intermediate egress frame is formed. The
    old ingress-geometry arithmetic (leaf-tag offset o_i, code c -> o_i*2^pw+c)
    is gone: for SB_R it produced (2,4,6,8), a code outside the register.
    """
    fin, fout = select_frames(t)
    plan = strategy_b_plan(t)
    rows = []
    for i, br in enumerate(branches):
        rows.append({
            "J_minus": tuple(fin.sectors[i].codes),
            "J_plus": tuple(fout.sectors[i].codes),
            "K_minus": plan.K_minus[i],
            "K_plus": plan.K_plus[i],
            "in_map": plan.in_maps[i],
            "out_map": plan.out_maps[i],
            "branch": br,
        })
    return fin, fout, rows


def _inclusion(codes, dim):
    J = np.zeros((dim, len(codes)), complex)
    for m, c in enumerate(codes):
        J[c, m] = 1.0
    return J


SB_BRANCHES = {
    "SB31": lambda: (opaque_left3(), Tg(0, q)),
    "SB13": lambda: (Hg(0, q), opaque_right3()),
}


@pytest.mark.parametrize("name,mk", WITNESSES)
def test_transport_equations_hold_per_sector(name, mk):
    """(1) and (3) reduce to identity here, and (2) is checked against the
    ACTUAL synthesized block."""
    t = mk()
    fin, fout, rows = sector_table(t, SB_BRANCHES[name]())
    B = compile(t, materialize=False).circuit.get_unitary()
    for i, row in enumerate(rows):
        assert row["J_minus"] == row["K_minus"], (
            f"{name} sector {i}: eq(1) J^-={row['J_minus']} "
            f"K^-={row['K_minus']}")
        assert row["K_plus"] == row["J_plus"], (
            f"{name} sector {i}: eq(3) K^+={row['K_plus']} "
            f"J^+={row['J_plus']}")
        cb = compile(row["branch"], materialize=True)
        G_i = semantic_action(cb.input_frame, cb.circuit.get_unitary(),
                              cb.output_frame)
        lhs = B @ _inclusion(row["K_minus"], B.shape[0])
        rhs = _inclusion(row["K_plus"], B.shape[0]) @ G_i
        assert np.allclose(lhs, rhs, atol=ATOL, rtol=0.0), (
            f"{name} sector {i}: eq(2) fails, max dev "
            f"{np.abs(lhs - rhs).max():.6e}")


def test_SB31_pinned_sector_cuts():
    fin, fout, rows = sector_table(SB31_witness(), SB_BRANCHES["SB31"]())
    assert rows[0]["J_minus"] == (0, 1, 2, 3, 4, 5)
    assert rows[1]["J_minus"] == (6, 7)
    assert rows[0]["K_minus"] == (0, 1, 2, 3, 4, 5)
    assert rows[1]["K_minus"] == (6, 7)


def test_SB13_pinned_sector_cuts():
    fin, fout, rows = sector_table(SB13_witness(), SB_BRANCHES["SB13"]())
    assert rows[0]["J_minus"] == (0, 1)
    assert rows[1]["J_minus"] == (2, 3, 4, 5, 6, 7)
    assert rows[0]["K_minus"] == (0, 1)
    assert rows[1]["K_minus"] == (2, 3, 4, 5, 6, 7)


# ---------------------------------------------------------------------------
# Dense-width sentinel -- MANDATORY completion item, not out of scope
# ---------------------------------------------------------------------------

def SB51_witness():
    """Opaque 5/1 split over six Q leaves: a FOUR-qubit non-permutation
    Strategy B block."""
    L5 = Plus(Plus(L3, q), q)
    map2 = PlusMap(q, q, Tg(0, q), Id(q))
    opaque_left5 = Seq(AssocPlusL(L3, q, q),
                       PlusMap(L3, Plus(q, q), map3_left(), map2))
    return PlusMap(L5, q, opaque_left5, Id(q))


SB51_EXPECTED = _block_diag(H_M, S_M, X_M, T_M, np.eye(2), np.eye(2))


@pytest.mark.parametrize("materialize", MODES)
def test_SB51_dense_width_acceptance(materialize):
    """MANDATORY dense-backend acceptance gate -- currently RED.

    SB51 needs a 4-qubit non-permutation unitary and the backend offers only
    Unitary1/2/3qBox, so Strategy B raises

        NotImplementedError: PlusMap full non-permutation unitary for
        width 4 > 3 not yet supported

    This is stated as the requirement it is -- exact compilation against
    SB51_EXPECTED -- rather than as a passing `pytest.raises`, so it appears in
    the red set and stays visible until the dense-width backend phase lands.
    A test that passes while the feature is missing is how a limitation gets
    mistaken for support.
    """
    t = SB51_witness()
    assert _try_flatten_plusmap(t) is None
    r = compile(t, materialize=materialize)
    U = r.circuit.get_unitary()
    assert leakage(r.input_frame, U, r.output_frame) < ATOL
    assert abs(r.global_phase) < 1e-12
    np.testing.assert_allclose(
        semantic_action(r.input_frame, U, r.output_frame),
        SB51_EXPECTED, atol=ATOL, rtol=0.0)


# ===========================================================================
# TRANSPORT-ACTIVE witnesses
#
# SB31/SB13 above are GREEN CONTROLS: every sector there has J^- == K^- and
# K^+ == J^+, so they exercise Strategy B's full-block arithmetic and offset
# handling but NOT boundary transport. All-Q leaves give ingress and egress the
# same sum geometry and the dense (0..7) identity embedding, which cannot
# distinguish a transport-correct emitter from one that ignores transport.
#
# The witnesses below keep width 3 and semantic dimension 5 but give ingress
# and egress DIFFERENT sum geometry, so at least one inclusion genuinely moves.
# ===========================================================================

from lang.types import Unit, Ten, tag_width                       # noqa: E402
from lang.terms import DistL                                      # noqa: E402

I = Unit()
T0 = Ten(Plus(I, I), I)
SH = S_M @ H_M


def D_term():
    """T0 -> Tout, semantic action S.H on the two labels."""
    return Seq(Seq(Hg(0, T0), Sg(0, T0)), DistL(I, I, I))


L3_T = Plus(Plus(I, T0), I)
R3_T = Plus(I, Plus(T0, I))


def F3_term():
    return Seq(AssocPlusL(I, T0, I),
               PlusMap(I, Plus(T0, I),
                       Id(I),
                       PlusMap(T0, I, D_term(), Id(I))))


def G3_term():
    return Seq(AssocPlusR(I, T0, I),
               PlusMap(Plus(I, T0), I,
                       PlusMap(I, T0, Id(I), D_term()),
                       Id(I)))


def SB_L_witness():
    """Genuine opaque 3/1, transport-active."""
    return PlusMap(L3_T, I, F3_term(), Id(I))


def SB_R_witness():
    """Genuine opaque 1/3, transport-active."""
    return PlusMap(I, R3_T, Id(I), G3_term())


E_L = np.eye(5, dtype=complex)
E_L[1:3, 1:3] = SH
E_R = np.eye(5, dtype=complex)
E_R[2:4, 2:4] = SH

TRANSPORT_WITNESSES = [
    ("SB_L", SB_L_witness, E_L, lambda: (F3_term(), Id(I))),
    ("SB_R", SB_R_witness, E_R, lambda: (Id(I), G3_term())),
]


@pytest.mark.parametrize("name,mk,E,brs", TRANSPORT_WITNESSES)
def test_transport_witness_is_well_typed_and_selects_strategy_b(name, mk, E, brs):
    t = mk()
    d, c = type_of(t)
    fin, fout = select_frames(t)
    assert fin.n_qubits == 3 and fout.n_qubits == 3
    assert len(fin.codes) == 5 and len(fout.codes) == 5
    assert_strategy_b_selected(t, name)


@pytest.mark.parametrize("name,mk,E,brs", TRANSPORT_WITNESSES)
def test_transport_witness_is_TRANSPORT_ACTIVE(name, mk, E, brs):
    """Guard against this suite quietly degenerating into the all-Q controls.

    At least one inclusion must genuinely differ, and ingress/egress must have
    different sum geometry -- otherwise the witness proves nothing about
    transport that SB31/SB13 did not already.
    """
    t = mk()
    d, c = type_of(t)
    assert (tag_width(d), payload_width(d)) != (tag_width(c), payload_width(c)), (
        f"{name}: ingress and egress share a geometry, so this is not "
        f"transport-active")
    # After the repair K_i^- = J_i^- and K_i^+ = J_i^+ BY CONSTRUCTION, so
    # comparing them can no longer detect activity. What must move is the
    # recorded CODE MAP: the branch artifact's own frame codes onto the
    # parent's sector codes. On the all-Q controls those maps are the identity.
    plan = strategy_b_plan(t)
    moved = [(i, m) for i, m in enumerate(plan.out_maps)
             if any(a != b for a, b in m)]
    assert moved, (
        f"{name}: every recorded code map is the identity; this witness is "
        f"no more transport-active than the all-Q controls")


@pytest.mark.parametrize("name,mk,E,brs", TRANSPORT_WITNESSES)
@pytest.mark.parametrize("materialize", MODES)
def test_transport_witness_exact_action(name, mk, E, brs, materialize):
    r = compile(mk(), materialize=materialize)
    U = r.circuit.get_unitary()
    assert abs(r.global_phase) < 1e-12, f"{name}: phase {r.global_phase}"
    assert leakage(r.input_frame, U, r.output_frame) < ATOL, (
        f"{name}: leakage {leakage(r.input_frame, U, r.output_frame):.6f}")
    sem = semantic_action(r.input_frame, U, r.output_frame)
    np.testing.assert_allclose(sem, E, atol=ATOL, rtol=0.0)
    for a in range(5):
        for b in range(5):
            if abs(E[a, b]) < 1e-15:
                assert abs(sem[a, b]) < ATOL, (
                    f"{name}: off-sector amplitude at ({a},{b}) = {sem[a, b]}")


@pytest.mark.parametrize("name,mk,E,brs", TRANSPORT_WITNESSES)
def test_transport_witness_modes_agree_exactly(name, mk, E, brs):
    a = compile(mk(), materialize=False)
    b = compile(mk(), materialize=True)
    sa = semantic_action(a.input_frame, a.circuit.get_unitary(), a.output_frame)
    sb = semantic_action(b.input_frame, b.circuit.get_unitary(), b.output_frame)
    np.testing.assert_allclose(sa, sb, atol=ATOL, rtol=0.0)
    assert a.global_phase == b.global_phase


@pytest.mark.parametrize("name,mk,E,brs", TRANSPORT_WITNESSES)
def test_transport_witness_equations(name, mk, E, brs):
    """(1) holds; (2) is the earliest failure on both witnesses.

    The multi-leaf branch CHANGES LEAF COUNT (3 in, 4 out), while Strategy B
    sizes a branch's tag blocks from its INGRESS leaf count and reuses that for
    the egress:

      SB_L  U_full = U_f.copy(), then the right summand's block (tag 3, codes
            6-7) is zeroed to make room -- but F3's own egress USES code 6, so
            the branch's egress block is destroyed. eq(2) dev = 1.0.
      SB_R  _splat copies only n_right = 3 of G3's 4 egress blocks; the 4th
            would land at parent code 8, outside the 3-qubit register, so K^+
            is not even representable.
    """
    t = mk()
    _, _, rows = sector_table(t, brs())
    B = compile(t, materialize=False).circuit.get_unitary()
    dim = B.shape[0]
    for i, row in enumerate(rows):
        assert row["J_minus"] == row["K_minus"], (
            f"{name} sector {i}: eq(1) J^-={row['J_minus']} "
            f"K^-={row['K_minus']}")
        assert max(row["K_plus"]) < dim, (
            f"{name} sector {i}: eq(2) K^+={row['K_plus']} leaves the "
            f"{B.shape[0].bit_length() - 1}-qubit register entirely")
        cb = compile(row["branch"], materialize=True)
        G_i = semantic_action(cb.input_frame, cb.circuit.get_unitary(),
                              cb.output_frame)
        lhs = B @ _inclusion(row["K_minus"], dim)
        rhs = _inclusion(row["K_plus"], dim) @ G_i
        assert np.allclose(lhs, rhs, atol=ATOL, rtol=0.0), (
            f"{name} sector {i}: eq(2) fails, max dev "
            f"{np.abs(lhs - rhs).max():.6e}")
        assert row["K_plus"] == row["J_plus"], (
            f"{name} sector {i}: eq(3) K^+={row['K_plus']} "
            f"J^+={row['J_plus']}")


@pytest.mark.parametrize("materialize", MODES)
def test_SB_L_at_a_nonzero_offset(materialize):
    import re
    t = TenTerm(Id(q), SB_L_witness())
    r = compile(t, materialize=materialize)
    U = r.circuit.get_unitary()
    assert leakage(r.input_frame, U, r.output_frame) < ATOL
    assert abs(r.global_phase) < 1e-12
    np.testing.assert_allclose(
        semantic_action(r.input_frame, U, r.output_frame),
        np.kron(np.eye(2), E_L), atol=ATOL, rtol=0.0)
    wires = sorted({int(w) for c in r.circuit.get_commands()
                    for w in re.findall(r"q\[(\d+)\]", str(c))})
    assert wires == [1, 2, 3], wires


# ---------------------------------------------------------------------------
# The recorded dense plan: pinned code maps and complement
# ---------------------------------------------------------------------------

def test_SB_L_plan_code_maps_are_pinned():
    plan = strategy_b_plan(SB_L_witness())
    assert plan.n_qubits == 3
    assert plan.K_minus == ((0, 2, 3, 4), (6,)), plan.K_minus
    assert plan.K_plus == ((0, 1, 2, 3), (4,)), plan.K_plus
    assert plan.out_maps[0] == ((0, 0), (2, 1), (4, 2), (6, 3)), plan.out_maps[0]
    assert tuple(zip(plan.free_in, plan.free_out)) == ((1, 5), (5, 6), (7, 7))
    for m in plan.out_maps:
        assert 8 not in [c for _, c in m], "(2,4,6,8) was constructed"


def test_SB_R_plan_code_maps_are_pinned():
    plan = strategy_b_plan(SB_R_witness())
    assert plan.n_qubits == 3
    assert plan.K_minus == ((0,), (2, 4, 5, 6)), plan.K_minus
    assert plan.K_plus == ((0,), (1, 2, 3, 4)), plan.K_plus
    assert plan.out_maps[1] == ((0, 1), (2, 2), (4, 3), (6, 4)), plan.out_maps[1]
    assert tuple(zip(plan.free_in, plan.free_out)) == ((1, 5), (3, 6), (7, 7))
    for m in plan.out_maps:
        assert 8 not in [c for _, c in m], "(2,4,6,8) was constructed"


@pytest.mark.parametrize("name,mk,E,brs", TRANSPORT_WITNESSES)
def test_plan_maps_are_injective_and_complement_sizes_match(name, mk, E, brs):
    plan = strategy_b_plan(mk())
    dim = 2 ** plan.n_qubits
    for maps in (plan.in_maps, plan.out_maps):
        tgt = [c for m in maps for _, c in m]
        assert len(set(tgt)) == len(tgt), f"{name}: code map is not injective"
        assert all(0 <= c < dim for c in tgt), f"{name}: code leaves register"
    assert len(plan.free_in) == len(plan.free_out)
    assert plan.free_in == tuple(sorted(plan.free_in))
    assert plan.free_out == tuple(sorted(plan.free_out))


@pytest.mark.parametrize("name,mk,E,brs", TRANSPORT_WITNESSES)
@pytest.mark.parametrize("materialize", MODES)
def test_exactly_one_strategy_b_box(name, mk, E, brs, materialize):
    r = compile(mk(), materialize=materialize, explain=True)
    assert len([l for l in r.log if "Strategy B" in l]) == 1
    assert len(r.circuit.get_commands()) == 1, [str(c) for c in r.circuit.get_commands()]


@pytest.mark.parametrize("name,mk,E,brs", TRANSPORT_WITNESSES)
@pytest.mark.parametrize("materialize", MODES)
def test_strategy_b_does_not_recompile_its_branches(name, mk, E, brs,
                                                    materialize, monkeypatch):
    """Duplicate-compile regression guard, pinned on the TOTAL compile count.

    Strategy B used to call `compile(t.left)` and `compile(t.right)` again
    after `_left_art` / `_right_art` already existed. That second pair went
    through the module-level `compile`, not `_compile_branch_artifact`, so
    spying on the artifact helper could never have caught it -- and identity or
    repr matching on the branches does not survive normalization, which
    rewrites the objects before they reach the emitter.

    So the guard is the total number of `compile` invocations for the whole
    term. Six today; reintroducing the second pair would make it eight.
    """
    import compile.to_pytket as TP
    calls = [0]
    orig = TP.compile

    def spy(term, **kw):
        calls[0] += 1
        return orig(term, **kw)

    monkeypatch.setattr(TP, "compile", spy)
    spy(mk(), materialize=materialize)
    assert calls[0] == 6, (
        f"{name}: {calls[0]} compile calls, expected 6 -- a branch is being "
        f"compiled more than once")


@pytest.mark.parametrize("materialize", MODES)
def test_forced_bad_branch_action_leaves_the_parent_untouched(materialize, monkeypatch):
    """A non-unitary branch action must be refused before any emission."""
    import compile.to_pytket as TP
    from compile.frames import UnsupportedFrame
    from pytket.circuit import Circuit

    t = SB_L_witness()
    assert compile(t, materialize=materialize).circuit.n_qubits == 3

    import compile.frames as FR
    orig_sa = FR.semantic_action
    monkeypatch.setattr(
        FR, "semantic_action",
        lambda fi, U, fo: 2.0 * orig_sa(fi, U, fo))

    # Branch sub-compiles legitimately run BEFORE the plan is built -- the plan
    # needs their artifacts -- so their circuits are mutated either way. The
    # PARENT's only mutation on this path is the Strategy B box itself, and
    # `add_unitary3qbox` is emitted by nothing else here (F3 alone compiles to
    # X/qif/ToffoliBox). So counting that call is exactly "the parent was
    # never mutated".
    boxes = []
    o = Circuit.add_unitary3qbox

    def wrap(self, *a, _o=o, **kw):
        boxes.append(self.n_qubits)
        return _o(self, *a, **kw)

    monkeypatch.setattr(Circuit, "add_unitary3qbox", wrap)

    with pytest.raises(UnsupportedFrame) as ei:
        compile(t, materialize=materialize)
    assert "Strategy B dense placement plan" in str(ei.value), str(ei.value)
    assert boxes == [], f"parent box emitted before failing closed: {boxes}"


# ===========================================================================
# SB51 dense width: structured exact realisation
#
# pytket 2.11 has no general n-qubit unitary box (ceiling Unitary3qBox) and no
# matrix-accepting synthesis pass. A uniformly controlled U2 is an EXACT
# realisation -- not an approximation, not a workaround.
#
# THE SUPPORTED CLASS is stated on the MATRIX, because that is what the
# recogniser inspects: completed width>3 matrices recognised as uniformly
# controlled one-qubit U(2) blocks IN THE SELECTED WIRE ORDER. SB51 belongs to
# that class. Membership is decided by `_as_uniformly_controlled_u2` alone --
# never by pw, the type, or the plan -- so no statement here should be read as
# "pw >= 2 is forbidden". The negative witness below proves that ONE
# nonconforming matrix is rejected by recognition; it says nothing categorical
# about its payload width.
# ===========================================================================

@pytest.mark.parametrize("materialize", MODES)
def test_SB51_emits_a_multiplexed_u2_on_tag_wires(materialize):
    """Controls are the three tag wires, target is the payload wire."""
    import re
    r = compile(SB51_witness(), materialize=materialize)
    assert r.circuit.n_qubits == 4
    cmds = r.circuit.get_commands()
    assert len(cmds) == 1, [str(c) for c in cmds]
    assert "Multiplexed" in str(cmds[0]), str(cmds[0])
    wires = [int(x) for x in re.findall(r"q\[(\d+)\]", str(cmds[0]))]
    assert wires == [0, 1, 2, 3], wires


@pytest.mark.parametrize("materialize", MODES)
def test_SB51_emitted_unitary_equals_the_completed_plan_matrix(materialize):
    """The circuit realises the plan's own matrix, not something equivalent
    only on the code space -- the complement must agree too."""
    plan = strategy_b_plan(SB51_witness())
    dim = 2 ** plan.n_qubits
    branches = (SB51_witness().left, SB51_witness().right)
    expected = np.zeros((dim, dim), complex)
    for i, br in enumerate(branches):
        cb = compile(br, materialize=True)
        G_i = semantic_action(cb.input_frame, cb.circuit.get_unitary(),
                              cb.output_frame)
        expected += (_inclusion(plan.K_plus[i], dim) @ G_i
                     @ _inclusion(plan.K_minus[i], dim).conj().T)
    for src, dst in zip(plan.free_in, plan.free_out):
        expected[dst, src] = 1.0
    r = compile(SB51_witness(), materialize=materialize)
    np.testing.assert_allclose(r.circuit.get_unitary(), expected,
                               atol=ATOL, rtol=0.0)


def test_SB51_complement_is_identity_on_12_to_15():
    plan = strategy_b_plan(SB51_witness())
    assert plan.free_in == (12, 13, 14, 15), plan.free_in
    assert plan.free_out == (12, 13, 14, 15), plan.free_out
    U = compile(SB51_witness(), materialize=False).circuit.get_unitary()
    for c in (12, 13, 14, 15):
        col = np.zeros(16, complex)
        col[c] = 1.0
        np.testing.assert_allclose(U[:, c], col, atol=ATOL, rtol=0.0)


def test_control_state_ordering_is_pinned_against_endian_reversal():
    """A deliberately ASYMMETRIC block set.

    SB51's own blocks are H,S,X,T,I,I,I,I -- reversing the control bit order
    permutes them, so the emitted unitary would differ. This checks the
    recogniser and the emitter agree on big-endian control states by
    reconstructing the expected matrix under BOTH orders and requiring only
    the big-endian one to match.
    """
    from compile.to_pytket import _as_uniformly_controlled_u2
    U = compile(SB51_witness(), materialize=False).circuit.get_unitary()
    blocks = _as_uniformly_controlled_u2(U)
    assert blocks is not None and len(blocks) == 8

    # the block set must not be symmetric under bit reversal, or the test
    # could not detect an endian error at all
    rev = [blocks[int(format(i, "03b")[::-1], 2)] for i in range(8)]
    assert any(not np.allclose(a, b, atol=1e-12)
               for a, b in zip(blocks, rev)), (
        "block set is bit-reversal symmetric; endian errors would be invisible")

    def assemble(bs):
        M = np.zeros((16, 16), complex)
        for i, b in enumerate(bs):
            M[2 * i:2 * i + 2, 2 * i:2 * i + 2] = b
        return M

    np.testing.assert_allclose(U, assemble(blocks), atol=ATOL, rtol=0.0)
    assert not np.allclose(U, assemble(rev), atol=1e-10), (
        "reversed control order also matches; ordering is not pinned")


def test_recogniser_rejects_a_non_block_diagonal_matrix():
    from compile.to_pytket import _as_uniformly_controlled_u2
    U = np.eye(16, dtype=complex)
    U[[0, 3]] = U[[3, 0]]          # couples two different 2x2 blocks
    assert _as_uniformly_controlled_u2(U) is None
    bad = np.eye(16, dtype=complex)
    bad[0, 0] = 2.0                # diagonal block no longer unitary
    assert _as_uniformly_controlled_u2(bad) is None


def SB51_nonconforming_witness():
    """A width-4 term whose completed matrix is NOT a uniformly controlled U2.

    It happens to have payload width 2, but that is incidental: recognition
    inspects the matrix, so this witness demonstrates rejection of one
    nonconforming structure, not a rule about pw.
    """
    qq = Ten(q, q)
    L3w = Plus(Plus(qq, qq), qq)
    inner = Seq(AssocPlusL(qq, qq, qq),
                PlusMap(qq, Plus(qq, qq),
                        Hg(0, qq),
                        PlusMap(qq, qq, Sg(0, qq), Xg(0, qq))))
    return PlusMap(L3w, qq, inner, Tg(0, qq))


@pytest.mark.parametrize("materialize", MODES)
def test_nonconforming_width4_matrix_fails_closed(materialize):
    """Rejected BY MATRIX RECOGNITION, with the parent circuit untouched.

    The supported class is stated on the matrix, so this pins the mechanism --
    that `_as_uniformly_controlled_u2` returns None for this block -- rather
    than asserting anything categorical about payload width.
    """
    from pytket.circuit import Circuit
    import compile.to_pytket as TP

    t = SB51_nonconforming_witness()
    seen = []
    orig_rec = TP._as_uniformly_controlled_u2

    def spy(U):
        r = orig_rec(U)
        seen.append((U.shape[0], r is None))
        return r

    boxes = []
    orig_box = Circuit.add_gate

    def wrap(self, *a, **kw):
        if self.n_qubits >= 4:
            boxes.append(str(a[0]) if a else None)
        return orig_box(self, *a, **kw)

    TP._as_uniformly_controlled_u2 = spy
    Circuit.add_gate = wrap
    try:
        with pytest.raises((UnsupportedFrame, NotImplementedError)) as ei:
            compile(t, materialize=materialize)
    finally:
        TP._as_uniformly_controlled_u2 = orig_rec
        Circuit.add_gate = orig_box

    assert seen, "recognition was never consulted"
    assert any(rejected for _, rejected in seen), (
        f"recognition accepted this matrix: {seen}")
    assert boxes == [], f"parent circuit mutated before failing closed: {boxes}"


def test_the_supported_class_is_decided_by_the_matrix_not_by_pw():
    """Recognition takes only a matrix. Two blocks of identical payload width
    are classified differently purely by their structure."""
    from compile.to_pytket import _as_uniformly_controlled_u2
    ok = np.zeros((16, 16), complex)
    for i in range(8):
        ok[2 * i:2 * i + 2, 2 * i:2 * i + 2] = H_M if i % 3 else X_M
    assert _as_uniformly_controlled_u2(ok) is not None
    bad = ok.copy()
    bad[[0, 3]] = bad[[3, 0]]
    assert _as_uniformly_controlled_u2(bad) is None
