"""NF-1 Part M: a bound variable's boundary, from a certified branch parameter.

A bound `Var` cannot tell from anything local to itself whether the slot it
routes into holds a live resource. As a sum branch it does; as an AppCut head
or a LetPair producer being FETCHED it does not, and there the slot is merely
the naming it is about to overwrite. In those positions the slot and the
binding legitimately share wires:

    Var 'h'     slot (2, 0)        binding (0, 1)        share 0
    Var 'rest'  slot (0, 1, 2)     binding (2, 3, 4)     share 2

so a rule that always builds S (x) Y fails closed on ordinary terms. An
earlier unconditional version did exactly that: 225 failed against a 19-red
baseline. It is preserved, unmerged, on wip/bound-var-selected-boundary.

The difference is a property of the POSITION, so the derivation site that
introduces the payload states it, in a BranchParameter. Without one, a bound
Var's boundary is exactly what it always was.
"""

import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(__file__))

from lang.types import Q, Ten, Arrow, Plus, Unit, width
from lang.terms import Var, Seq, LetPair, Apply, Id, H as Hg
import compile.to_pytket as TP
from compile.to_pytket import compile, compile_with_artifacts
from compile.frames import (BranchParameter, ProvenanceScope, ProvenanceError,
                            UnsupportedFrame, canonical_frame, leakage,
                            semantic_action, DERIVED, FRAME_DEFAULT)

q = Q()
endo = Arrow(q, q)
ATOL = 1e-10
MODES = [False, True]


def param(logical=q, placement=(0,), reg=2, sc=None, **over):
    sc = sc or ProvenanceScope()
    d = dict(logical=logical, owner_id=sc.owner(), intro_cut=sc.cut(),
             cut_id=sc.cut(), codes=tuple(canonical_frame(logical).codes),
             ingress_placement=tuple(placement), register_width=reg)
    d.update(over)
    return BranchParameter(**d)


SWAP4 = np.zeros((4, 4), dtype=complex)
for _p in (0, 1):
    for _z in (0, 1):
        SWAP4[(_z << 1) | _p, (_p << 1) | _z] = 1.0


# ===========================================================================
# 1. The decisive branch
# ===========================================================================

@pytest.mark.parametrize("materialize", MODES)
def test_M1_the_certified_branch_var_is_four_by_four_and_exactly_swap(
        materialize):
    """payload Q at local wire 0, z:Q at local wire 1, Var("z",Q)."""
    prm = param()
    r = compile(Var("z", q), env={"z": [1]}, materialize=materialize,
                _branch_parameter=prm)
    sb = r.selected_boundary
    U = r.circuit.get_unitary()
    assert sb.authority == DERIVED
    assert sb.origin == "var:branch-parameter(z)"
    assert sb.ingress.dim == 4 and sb.egress.dim == 4
    names = [(f.name, f.role, f.dim) for f in sb.ingress.route.parts]
    assert names == [("S", "residual", 2), ("Y_z", "operand", 2)], names
    assert [(f.name, f.role, f.dim) for f in sb.egress.route.parts] == names
    assert sb.ingress.route.placements == ((0,), (1,))
    assert leakage(sb.ingress, U, sb.egress) < ATOL
    assert abs(r.global_phase) < 1e-12
    np.testing.assert_allclose(semantic_action(sb.ingress, U, sb.egress),
                               SWAP4, atol=ATOL, rtol=0.0)


def test_M2_pre_materialisation_egress_placement():
    """((1,), (0,)) pending; the swap network moves it back when
    materialised. The egress is read off the exit schedule, not obtained by
    assuming the routing is an involutive swap."""
    prm = param()
    p0 = compile(Var("z", q), env={"z": [1]}, materialize=False,
                 _branch_parameter=prm).selected_boundary
    p1 = compile(Var("z", q), env={"z": [1]}, materialize=True,
                 _branch_parameter=prm).selected_boundary
    assert p0.ingress.route.placements == ((0,), (1,))
    assert p0.egress.route.placements == ((1,), (0,))
    assert p1.ingress.route.placements == ((0,), (1,))
    assert p1.egress.route.placements == ((0,), (1,))
    assert p0.egress.codes != p1.egress.codes


# ===========================================================================
# 2. Ordinary variables are untouched
# ===========================================================================

ORDINARY = [
    ("appcut head", lambda: LetPair("h", "y", endo, q, Id(Ten(endo, q)),
                                    Apply(Var("h", endo), Var("y", q)))),
    ("letpair producer", lambda: LetPair(
        "f", "rest", endo, Ten(endo, q), Id(Ten(endo, Ten(endo, q))),
        LetPair("h", "y", endo, q, Var("rest", Ten(endo, q)),
                Apply(Var("h", endo), Var("y", q))))),
]


@pytest.mark.parametrize("name,mk", ORDINARY)
@pytest.mark.parametrize("materialize", MODES)
def test_M3_ordinary_bound_vars_get_no_branch_parameter(name, mk, materialize):
    """A spy on every compile: no ordinary Var is handed a parameter, and no
    Var boundary is built by the certified rule."""
    seen = []
    orig = TP.compile

    def spy(term, **kw):
        seen.append(kw.get("_branch_parameter"))
        return orig(term, **kw)

    TP.compile = spy
    try:
        orig(mk(), materialize=materialize)
    finally:
        TP.compile = orig
    assert all(x is None for x in seen), (
        f"{name}: a branch parameter reached an ordinary compilation")
    _, arts = compile_with_artifacts(mk(), materialize=materialize)
    for a in arts:
        if isinstance(a.term, Var):
            sb = a.selected_boundary
            assert not sb.origin.startswith("var:branch-parameter"), (
                f"{name}: an ordinary Var used the certified rule")


def test_M4_ordinary_vars_keep_their_slot_binding_overlap():
    """The very overlaps that made an unconditional rule fail closed are
    still present -- and still harmless, because the rule does not fire."""
    _, arts = compile_with_artifacts(ORDINARY[1][1]())
    overlaps = []
    for a in arts:
        if isinstance(a.term, Var) and a.routing is not None:
            slot = tuple(a.perm_at_entry[a.offset + i]
                         for i in range(width(a.term.ty)))
            bind = tuple(a.routing.wires)
            if set(slot) & set(bind) and set(slot) != set(bind):
                overlaps.append((a.term.name, slot, bind))
    assert overlaps, (
        "this witness must contain a partially overlapping slot/binding, or "
        "it does not exercise the case the certificate exists to separate")


# ===========================================================================
# 3. The certificate is root-scoped
# ===========================================================================

def test_M5_the_parameter_does_not_reach_a_nested_var():
    """Issued for the branch ROOT. A Var deeper in the branch is ordinary."""
    prm = param()
    _, arts = compile_with_artifacts(Seq(Var("z", q), Hg(0, q)),
                                     env={"z": [1]})
    # (no parameter at all: the nested-Var shape still compiles as before)
    base = {a.occurrence: a.selected_boundary.origin for a in arts
            if isinstance(a.term, Var)}
    sink = {}
    compile(Seq(Var("z", q), Hg(0, q)), env={"z": [1]},
            _branch_parameter=prm, _artifact_sink=sink)
    withp = {a.occurrence: a.selected_boundary.origin
             for a in sink["artifacts"] if isinstance(a.term, Var)}
    assert withp == base, (
        f"the parameter leaked to a nested Var: {base} -> {withp}")
    assert all(not o.startswith("var:branch-parameter")
               for o in withp.values())


# ===========================================================================
# 4. Removing or forging the certificate
# ===========================================================================

def test_M6_without_the_certificate_the_decisive_case_is_incomplete():
    """The mutation gate: no parameter, no two-factor boundary -- and the
    single-factor root then demonstrably does not describe the action."""
    r = compile(Var("z", q), env={"z": [1]}, materialize=True)
    sb = r.selected_boundary
    assert not sb.origin.startswith("var:branch-parameter")
    assert sb.ingress.dim != 4
    assert leakage(sb.ingress, r.circuit.get_unitary(), sb.egress) > 0.5, (
        "without the parameter the root must be visibly incomplete, or M1 "
        "proves nothing")


@pytest.mark.parametrize("bad,frag", [
    (dict(logical=Ten(q, q)), "placement names"),
    (dict(ingress_placement=(1,)), "entry slot"),
    (dict(codes=(0, 0)), "repeats a code"),
    (dict(codes=(0, 1, 2)), "semantic dimension"),
    (dict(register_width=5), "wire register"),
    (dict(owner_id=""), "owner or cut"),
    (dict(intro_cut=""), "owner or cut"),
])
def test_M7_a_forged_parameter_fails_closed(bad, frag):
    try:
        prm = param(**bad)
    except ProvenanceError as e:
        assert frag in str(e), f"{bad}: {e}"
        return
    with pytest.raises((ProvenanceError, UnsupportedFrame)) as e:
        compile(Var("z", q), env={"z": [1]}, _branch_parameter=prm)
    assert frag in str(e.value), f"{bad}: {e.value}"


def test_M8_the_parameter_and_the_binding_must_be_distinct_premises():
    """Same owner, or overlapping placements, is not two premises."""
    with pytest.raises(UnsupportedFrame) as e:
        compile(Var("z", q), env={"z": [1]},
                _branch_parameter=param(placement=(1,)))
    assert "entry slot" in str(e.value) or "overlap" in str(e.value)


def test_M9_partial_overlap_of_the_two_premises_fails_closed():
    """A two-wire parameter and a two-wire binding sharing one wire."""
    from compile.frames import RoutingOnly
    prm = param(logical=Ten(q, q), placement=(0, 1), reg=3)
    cert = RoutingOnly(name="z", wires=(1, 2), owner_id="own:other",
                       ingress_wires=(1, 2), egress_wires=(1, 2),
                       perm_at_entry=(0, 1, 2), perm_at_exit=(0, 1, 2))
    with pytest.raises(ProvenanceError) as e:
        prm.check_against(cert, 3, "test: ")
    assert "overlap" in str(e.value)


def test_M10_the_binder_owner_comes_from_the_routing_certificate():
    """Not from the name, the type or the occurrence cut; two equal-typed
    binders stay distinct."""
    prm = param()
    _, arts = compile_with_artifacts(Var("z", q), env={"z": [1]})
    sink = {}
    compile(Var("z", q), env={"z": [1]}, _branch_parameter=prm,
            _artifact_sink=sink)
    root = [a for a in sink["artifacts"] if a.occurrence == 0][0]
    Y = [f for f in root.selected_boundary.ingress.route.parts
         if f.name == "Y_z"][0]
    S = [f for f in root.selected_boundary.ingress.route.parts
         if f.name == "S"][0]
    assert Y.owner == root.routing.owner_id, (
        "the carrier factor is not owned by the binder the certificate names")
    assert S.owner == root.cut_id
    assert Y.owner != S.owner
    assert Y.owner != prm.owner_id, (
        "the binding and the branch parameter must be distinct premises")


# ===========================================================================
# 5. Non-involutive and sparse witnesses
# ===========================================================================

def test_M11_a_var_routed_across_a_wider_register():
    """One-wire Var, three-wire register, binding away from the slot."""
    prm = param(reg=3)
    r = compile(Var("z", q), env={"z": [2]}, materialize=False,
                _branch_parameter=prm)
    sb = r.selected_boundary
    assert sb.ingress.dim == 4 and sb.egress.dim == 4
    assert sb.ingress.route.placements == ((0,), (2,))
    assert sb.egress.route.placements == ((2,), (0,))
    assert sb.ingress.n_qubits == 3
    placed = {w for g in sb.ingress.route.placements for w in g}
    assert 1 not in placed, "wire 1 is a spectator of this cut"
    U = r.circuit.get_unitary()
    assert leakage(sb.ingress, U, sb.egress) < ATOL


PS = Plus(q, Unit())


def test_M12_a_sparse_parameter_stays_sparse():
    """Plus(Q,I) is dimension 3 on two wires: 3 x 3 = 9, never 4 x 4 = 16."""
    prm = param(logical=PS, placement=(0, 1), reg=4)
    r = compile(Var("z", PS), env={"z": [2, 3]}, materialize=False,
                _branch_parameter=prm)
    sb = r.selected_boundary
    parts = sb.ingress.route.parts
    assert [f.dim for f in parts] == [3, 3], [f.dim for f in parts]
    assert parts[0].codes == (0, 1, 2), parts[0].codes
    assert parts[1].codes == (0, 1, 2)
    assert sb.ingress.dim == 9 and sb.egress.dim == 9
    assert sb.ingress.dim != 16
    assert sb.ingress.route.placements == ((0, 1), (2, 3))
    assert sb.egress.route.placements == ((2, 3), (0, 1))
    assert leakage(sb.ingress, r.circuit.get_unitary(), sb.egress) < ATOL


def test_M13_a_multiwire_parameter():
    prm = param(logical=Ten(q, q), placement=(0, 1), reg=4)
    r = compile(Var("z", Ten(q, q)), env={"z": [2, 3]}, materialize=False,
                _branch_parameter=prm)
    sb = r.selected_boundary
    assert sb.ingress.dim == 16 and sb.egress.dim == 16
    assert sb.ingress.route.placements == ((0, 1), (2, 3))
    assert sb.egress.route.placements == ((2, 3), (0, 1))
    assert leakage(sb.ingress, r.circuit.get_unitary(), sb.egress) < ATOL


def test_M14_reversing_the_transport_direction_is_observable():
    """The pending and materialised egress differ, and reading one for the
    other is a different chart."""
    prm = param()
    p0 = compile(Var("z", q), env={"z": [1]}, materialize=False,
                 _branch_parameter=prm).selected_boundary
    p1 = compile(Var("z", q), env={"z": [1]}, materialize=True,
                 _branch_parameter=prm).selected_boundary
    assert p0.egress.codes != p1.egress.codes
    assert p0.ingress.codes == p1.ingress.codes
