"""NF-1 Part K: emitting an open sum DIRECTLY from its completed-branch Block.

The plan produced in Part J is consumed as it stands. No Align, no A_pre or
A_post: for the recorded charts the block equation already holds, and adding
transport would cover a defect rather than repair one.

    Sem(W ; plan.ingress, plan.egress)  =  blockdiag( G_0 (x) I_16 , G_1 )

This is an EMISSION-FIDELITY oracle: it checks that the emitted circuit acts
as the completed blocks say, where each G_i is read from that branch's own
prepared artifact. It is NOT an independent denotation of the source term --
both sides come from this compiler -- so it catches an emitter that departs
from its plan, not a plan that misreads the source.

    G_i = semantic_action( branch.artifact.selected_boundary.ingress,
                           branch.artifact.unitary,
                           branch.artifact.selected_boundary.egress )

The artifact's unitary already carries its circuit phase. Frames are never
consulted. `local_to_ambient` is ALREADY a physical parent placement and
`tag_wires` are ALREADY physical and big-endian, so neither is passed through
`p`, an offset, or `apply_new_to_old` again. `plan.inclusion(i, side)` gives
positions in the ordered 80-dimensional semantic chart -- not wires and not
basis codes.
"""

import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(__file__))

from pytket.circuit import Circuit

from lang.types import Q, Ten, Arrow, Plus, Unit
import compile.to_pytket as TP
from compile.to_pytket import (compile, compile_with_artifacts,
                               _preflight_open_use_block,
                               _emit_open_use_block)
from compile.frames import (semantic_action, leakage, ProvenanceError,
                            ProvenanceScope, TypedBinding, ChartFactor,
                            UseBlockLayout, complete_branch, plan_use_block,
                            par_then_repart, scatter_repart, UnsupportedFrame,
                            SelectedBoundary)

q = Q()
MODES = [False, True]
ATOL = 1e-10


def ctrl_ho_plan(materialize=False):
    """The authoritative plan, captured from a real compilation."""
    from test_nf1_beta_tensor import _fixture
    TP._USE_BLOCK_OBSERVED.clear()
    try:
        compile(_fixture("ctrl_ho_closed_plus_map"), materialize=materialize)
    except Exception:
        pass
    assert TP._USE_BLOCK_OBSERVED, "no use-block plan was produced"
    return TP._USE_BLOCK_OBSERVED[-1]


def branch_action(b):
    """G_i, read in the branch's OWN selected boundary. Never fin/fout."""
    sb = b.artifact.selected_boundary
    return semantic_action(sb.ingress, b.artifact.unitary, sb.egress)


def expected_blockdiag(plan):
    """blockdiag(Vhat_0, Vhat_1), in RECORDED factor order.

    Built here, in the test, from the branch actions and the recorded
    inactive completions -- not by any production helper.
    """
    blocks = []
    for b in plan.branches:
        G = branch_action(b)
        M = G
        seen = set()
        for x in b.inactive:
            if x.owner_id in seen:
                continue
            seen.add(x.owner_id)
            M = np.kron(M, np.eye(len(x.codes), dtype=complex))
        blocks.append(M)
    n = sum(m.shape[0] for m in blocks)
    out = np.zeros((n, n), dtype=complex)
    o = 0
    for m in blocks:
        out[o:o + m.shape[0], o:o + m.shape[1]] = m
        o += m.shape[0]
    return out, blocks


def inclusion_matrix(plan, i, side):
    """J_i^side as a rectangular isometry, built from the recorded positions."""
    parent = plan.ingress if side == "ingress" else plan.egress
    js = plan.inclusion(i, side)
    M = np.zeros((parent.dim, len(js)), dtype=complex)
    for col, row in enumerate(js):
        M[row, col] = 1.0
    return M


def emit_fresh(plan):
    """Emit the plan into a fresh circuit of the plan's own width."""
    c = Circuit(plan.ambient_width)
    _emit_open_use_block(c, plan)
    return c


# ===========================================================================
# 1. The 80-dimensional operator equation
# ===========================================================================

@pytest.mark.parametrize("materialize", MODES)
def test_K1_emission_realises_the_block_diagonal(materialize):
    plan = ctrl_ho_plan(materialize)
    c = emit_fresh(plan)
    U = c.get_unitary()
    W = semantic_action(plan.ingress, U, plan.egress)
    expected, _ = expected_blockdiag(plan)
    assert W.shape == (80, 80) == expected.shape
    dev = float(np.max(np.abs(W - expected)))
    assert dev < ATOL, f"maximum deviation {dev:.3e} from blockdiag(Vhat)"
    np.testing.assert_allclose(W, expected, atol=ATOL, rtol=0.0)


@pytest.mark.parametrize("materialize", MODES)
def test_K2_zero_leakage_and_zero_phase(materialize):
    plan = ctrl_ho_plan(materialize)
    c = emit_fresh(plan)
    U = c.get_unitary()
    assert leakage(plan.ingress, U, plan.egress) < ATOL
    assert abs(float(c.phase)) < 1e-12, f"global phase {c.phase}"


@pytest.mark.parametrize("materialize", MODES)
def test_K3_the_block_equation_holds_sector_by_sector(materialize):
    """W J_i^- = J_i^+ Vhat_i, with the inclusions built independently."""
    plan = ctrl_ho_plan(materialize)
    c = emit_fresh(plan)
    W = semantic_action(plan.ingress, c.get_unitary(), plan.egress)
    _, vhats = expected_blockdiag(plan)
    for i, b in enumerate(plan.branches):
        Jm = inclusion_matrix(plan, b.index, "ingress")
        Jp = inclusion_matrix(plan, b.index, "egress")
        lhs, rhs = W @ Jm, Jp @ vhats[i]
        dev = float(np.max(np.abs(lhs - rhs)))
        assert dev < ATOL, (
            f"block {b.index}: W J^- != J^+ Vhat, max deviation {dev:.3e}")


@pytest.mark.parametrize("materialize", MODES)
def test_K4_cross_blocks_are_zero(materialize):
    plan = ctrl_ho_plan(materialize)
    W = semantic_action(plan.ingress, emit_fresh(plan).get_unitary(),
                        plan.egress)
    for i in (0, 1):
        for j in (0, 1):
            if i == j:
                continue
            Jm = inclusion_matrix(plan, j, "ingress")
            Jp = inclusion_matrix(plan, i, "egress")
            cross = Jp.conj().T @ W @ Jm
            dev = float(np.max(np.abs(cross)))
            assert dev < ATOL, (
                f"cross block ({i},{j}) is nonzero, max {dev:.3e}")


@pytest.mark.parametrize("materialize", MODES)
def test_K5_placement_facts(materialize):
    plan = ctrl_ho_plan(materialize)
    assert plan.tag_wires == (4,)
    blocks = {b.index: b for b in plan.branches}
    assert blocks[0].local_to_ambient == (5, 6, 7)
    assert blocks[1].local_to_ambient == (5, 6, 7, 0, 1, 2, 3)
    assert plan.spectators == (8, 9)
    c = emit_fresh(plan)
    touched = {qb.index[0] for cmd in c.get_commands() for qb in cmd.qubits}
    assert not (touched & {8, 9}), (
        f"emission touched spectator wires {sorted(touched & {8, 9})}")
    assert touched <= set(range(8))


# ===========================================================================
# 2. Discriminating witnesses
# ===========================================================================

def _root(codes, n_local):
    """A selected chart over the BRANCH's own n_local-wire register.

    Exactly the shape a prepared BranchArtifact carries: its own register,
    not the parent's. complete_branch lifts it through local_to_ambient.
    """
    f = ChartFactor(factor_id="tssion0", name="V", owner="cut:v", n_qubits=n_local, codes=codes)
    rep, pl = scatter_repart((tuple(range(n_local)),), n_local)
    return par_then_repart((f,), rep, n_local, "v", placements=pl,
                           kind="scatter")


class _Art:
    """A prepared branch artifact, built for the test."""
    def __init__(self, circ, chart, phase=0.0):
        self.circuit = circ
        self.cmds = circ.get_commands()
        self.phase = phase
        self.selected_boundary = SelectedBoundary(ingress=chart,
                                                  egress=chart, origin="test")

    @property
    def unitary(self):
        return self.circuit.get_unitary()


def _mk_plan(specs, ambient, tag_wires, owned=()):
    """specs: [(tag_value, n_local, local_to_ambient, circ, phase, codes)]"""
    lay = UseBlockLayout(ambient_width=ambient, owned_wires=tuple(owned),
                         tag_wires=tuple(tag_wires),
                         workspace_wires=tuple(
                             w for w in range(ambient)
                             if w not in set(tag_wires) | set(owned)))
    blocks = []
    for tag, n_local, l2a, circ, ph, codes in specs:
        # branch-LOCAL: placements are 0..n_local-1; complete_branch lifts
        # them through local_to_ambient.
        ch = _root(codes, n_local)
        blocks.append(complete_branch(
            index=len(blocks), artifact=_Art(circ, ch, ph), uses=(),
            inactive=(), local_to_ambient=tuple(l2a), tag_value=tag,
            ambient_width=ambient))
    return plan_use_block(blocks, lay)


def test_K6_tag_value_is_used_not_the_branch_index():
    """Two blocks whose tag values are the REVERSE of their indices."""
    a, b = Circuit(1), Circuit(1)
    a.X(0)
    b.H(0)
    plan = _mk_plan([(1, 1, (1,), a, 0.0, (0, 1)),
                     (0, 1, (1,), b, 0.0, (0, 1))], 2, (0,))
    assert [x.tag_value for x in plan.branches] == [1, 0], (
        "this witness needs tag values that differ from the indices")
    c = emit_fresh(plan)
    W = semantic_action(plan.ingress, c.get_unitary(), plan.egress)
    expected, _ = expected_blockdiag(plan)
    np.testing.assert_allclose(W, expected, atol=ATOL, rtol=0.0)
    # Reading the INDEX where the tag value belongs builds a different
    # circuit. Compared on the raw unitary: each plan's own chart-relative
    # action is blockdiag in list order either way, so that would not
    # discriminate.
    swapped = _mk_plan([(0, 1, (1,), a, 0.0, (0, 1)),
                        (1, 1, (1,), b, 0.0, (0, 1))], 2, (0,))
    assert not np.allclose(c.get_unitary(),
                           emit_fresh(swapped).get_unitary(), atol=1e-12), (
        "the tag value is indistinguishable from the index on this witness")


def test_K7_nonzero_offset_and_non_monotone_placement():
    """local_to_ambient need not start at 0 or ascend."""
    a = Circuit(2)
    a.CX(0, 1)
    b = Circuit(2)
    b.H(0)
    plan = _mk_plan([(0, 2, (3, 1), a, 0.0, (0, 1, 2, 3)),
                     (1, 2, (3, 1), b, 0.0, (0, 1, 2, 3))], 4, (0,))
    assert plan.branches[0].local_to_ambient == (3, 1)
    c = emit_fresh(plan)
    W = semantic_action(plan.ingress, c.get_unitary(), plan.egress)
    expected, _ = expected_blockdiag(plan)
    np.testing.assert_allclose(W, expected, atol=ATOL, rtol=0.0)
    touched = {qb.index[0] for cmd in c.get_commands() for qb in cmd.qubits}
    assert 2 not in touched, "wire 2 is a spectator here"


def test_K8_a_phase_only_branch_keeps_its_relative_sector_phase():
    """Including the tag-0 arm: a branch that emits no gate but carries a
    global phase must still contribute that phase on its own sector."""
    for tag in (0, 1):
        a = Circuit(1)
        a.add_phase(0.25)                       # e^{i pi/4}
        b = Circuit(1)
        specs = [(tag, 1, (1,), a, 0.25, (0, 1)),
                 (1 - tag, 1, (1,), b, 0.0, (0, 1))]
        plan = _mk_plan(specs, 2, (0,))
        assert not plan.branches[0].artifact.cmds, "the arm must emit no gate"
        c = emit_fresh(plan)
        W = semantic_action(plan.ingress, c.get_unitary(), plan.egress)
        expected, _ = expected_blockdiag(plan)
        np.testing.assert_allclose(W, expected, atol=ATOL, rtol=0.0)
        ph = np.exp(1j * np.pi * 0.25)
        # The parent chart lists the blocks in plan order, so the phase arm
        # is the FIRST block whichever tag value it carries -- which is
        # exactly why the emitter must use tag_value and not the index.
        np.testing.assert_allclose(W[:2, :2], ph * np.eye(2),
                                   atol=ATOL, rtol=0.0)
        np.testing.assert_allclose(W[2:, 2:], np.eye(2), atol=ATOL, rtol=0.0)
        assert plan.branches[0].tag_value == tag


def test_K9_a_sparse_selected_root_branch():
    """A branch whose selected root is a proper subset of its register."""
    # anti-controlled X: swaps |00> and |01>, fixes |10> and |11>, so it
    # preserves the sparse code set {0,1,2} exactly.
    a = Circuit(2)
    a.X(0)
    a.CX(0, 1)
    a.X(0)
    b = Circuit(2)
    plan = _mk_plan([(0, 2, (1, 2), a, 0.0, (0, 1, 2)),
                     (1, 2, (1, 2), b, 0.0, (0, 1, 2))], 3, (0,))
    assert plan.branches[0].dim == 3, "the root must stay sparse"
    assert plan.ingress.dim == 6
    c = emit_fresh(plan)
    assert leakage(plan.ingress, c.get_unitary(), plan.egress) < ATOL


# ===========================================================================
# 3. Preflight precedes every mutation
# ===========================================================================

def test_K10_a_malformed_later_branch_leaves_the_parent_untouched():
    """Validation covers ALL blocks before the first gate is emitted."""
    good = Circuit(1)
    good.X(0)
    bad = Circuit(1)
    bad.H(0)
    plan = _mk_plan([(0, 1, (1,), good, 0.0, (0, 1)),
                     (1, 1, (1,), bad, 0.0, (0, 1))], 2, (0,))
    # break the SECOND block only
    import dataclasses
    broken = dataclasses.replace(
        plan, branches=(plan.branches[0],
                        dataclasses.replace(plan.branches[1],
                                            local_to_ambient=(0,))))
    target = Circuit(2)
    with pytest.raises(UnsupportedFrame) as e:
        _emit_open_use_block(target, broken)
    assert "branch 1" in str(e.value)
    assert len(target.get_commands()) == 0, (
        f"the parent gained {len(target.get_commands())} command(s) before "
        f"the malformed block was rejected")
    assert abs(float(target.phase)) < 1e-12


def test_K11_a_leaking_prepared_branch_is_rejected_before_emission():
    circ = Circuit(2)
    circ.H(0)                       # takes |0> out of a 1-code selected root
    ch = _root((0,), 2)
    art = _Art(circ, ch)
    lay = UseBlockLayout(ambient_width=2, owned_wires=(), tag_wires=(),
                         workspace_wires=(0, 1))
    blk = complete_branch(index=0, artifact=art, uses=(), inactive=(),
                          local_to_ambient=(0, 1), tag_value=0,
                          ambient_width=2)
    plan = plan_use_block([blk], lay)
    target = Circuit(2)
    with pytest.raises(UnsupportedFrame) as e:
        _emit_open_use_block(target, plan)
    assert "leaks" in str(e.value)
    assert len(target.get_commands()) == 0


def test_K12_a_command_on_an_unrecorded_wire_is_rejected():
    circ = Circuit(2)
    circ.CX(0, 1)
    ch = _root((0, 1), 1)
    art = _Art(circ, ch)
    blk = complete_branch(index=0, artifact=art, uses=(), inactive=(),
                          local_to_ambient=(1,), tag_value=0,
                          ambient_width=3)
    lay = UseBlockLayout(ambient_width=3, owned_wires=(), tag_wires=(0,),
                         workspace_wires=(1, 2))
    plan = plan_use_block([blk], lay)
    target = Circuit(3)
    with pytest.raises(UnsupportedFrame) as e:
        _emit_open_use_block(target, plan)
    msg = str(e.value)
    assert "local_to_ambient" in msg or "does not record" in msg
    assert len(target.get_commands()) == 0


# ===========================================================================
# 4. One preparation, one object, no legacy fallback
# ===========================================================================

def test_K13_the_same_artifacts_are_planned_and_emitted_once():
    from test_nf1_beta_tensor import _fixture
    made = []
    orig = TP._compile_branch_artifact

    def spy(branch, *, env=None, scope=None, **kw):
        a = orig(branch, env=env, scope=scope, **kw)
        made.append(a)
        return a

    TP._compile_branch_artifact = spy
    TP._USE_BLOCK_OBSERVED.clear()
    try:
        compile(_fixture("ctrl_ho_closed_plus_map"), materialize=False)
    finally:
        TP._compile_branch_artifact = orig
    plan = TP._USE_BLOCK_OBSERVED[-1]
    assert len(made) == 2, f"{len(made)} branch preparations, want exactly 2"
    # The EXACT ORDERED identity tuple, not "each appears somewhere".
    planned = tuple(id(b.artifact) for b in plan.branches)
    prepared = tuple(id(m) for m in made)
    assert planned == prepared, (
        f"the plan holds {planned} but preparation produced {prepared}; the "
        f"objects or their order differ")


def test_K14_the_planned_path_does_not_use_the_legacy_branch_compiler():
    """Patch the legacy compiler to raise; a valid plan must still emit."""
    from test_nf1_beta_tensor import _fixture
    orig = TP._compile_branch
    calls = []

    def boom(*a, **k):
        calls.append(a)
        raise AssertionError("the legacy open mapper was used")

    TP._compile_branch = boom
    try:
        r = compile(_fixture("ctrl_ho_closed_plus_map"), materialize=False)
    finally:
        TP._compile_branch = orig
    assert r.circuit is not None
    assert not calls, "the planned path fell back to the legacy mapper"
