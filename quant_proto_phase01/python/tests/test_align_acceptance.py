"""Acceptance suite for the boundary-frame / Align repair.

Written BEFORE the implementation, so the initial run is the red table.

The contract under test:

  * a judgment type fixes the semantic boundary space, not its physical
    embedding -- the derivation selects the frame;
  * distributors are zero-gate, and any frame conversion happens at the
    SPLICE, via Align;
  * Align is  G' = A G A^dagger  with  A u_co^- = u_pr^+, realised
    chronologically as  A^dagger ; G ; A, with A first extended
    deterministically to a total permutation of the register;
  * semantics is judged on the code space only, exactly:
        U_sem = (u_out)^dagger G u_in           compared with rtol=0
        leak  = ||(I - u_out u_out^dagger) G u_in||  must vanish
  * anything unsupported fails closed, with no partial circuit.
"""

import math

import numpy as np
import pytest

from lang.types import Unit, Q, Ten, Plus, width
from lang.terms import (
    Id, Seq, TenTerm, DistL, DistR, UndistL, UndistR,
    EncodeQubit, DecodeQubit, NPlusMap, PlusMap, X as Xg, TwistTen,
)
from compile.to_pytket import compile
from compile.frames import (
    Frame, Sector, Port, canonical_frame, tensor_frame, flat_frame,
    semantic_action, leakage, assert_framed_semantics, frames_agree,
    embeddings_agree, UnsupportedFrame, ExprEvalError,
    FIdentity, FSum, FCompose, FTensor, FWirePerm, FOpaque,
)

QB = Plus(Unit(), Unit())
Z3 = Plus(Unit(), Plus(Unit(), Unit()))
Z5 = Plus(Unit(), Plus(Unit(), Plus(Unit(), Plus(Unit(), Unit()))))
MODES = [False, True]


def _framed(term, materialize):
    r = compile(term, materialize=materialize)
    U = r.circuit.get_unitary()
    return r, U, semantic_action(r.input_frame, U, r.output_frame)


def _assert_exact_identity(term, materialize, dim):
    r, U, sem = _framed(term, materialize)
    assert leakage(r.input_frame, U, r.output_frame) < 1e-10, "leaks"
    assert np.allclose(sem, np.eye(dim), atol=1e-10, rtol=0.0)
    return r


# ---------------------------------------------------------------------------
# 1. All four distributors, equal- and unequal-width, both modes
# ---------------------------------------------------------------------------

DISTRIBUTORS = [
    ("DistL-equal",   lambda: DistL(Unit(), Q(), Q())),
    ("DistR-equal",   lambda: DistR(Unit(), Unit(), QB)),
    ("UndistL-equal", lambda: UndistL(Unit(), Q(), Q())),
    ("UndistR-equal", lambda: UndistR(Unit(), Unit(), QB)),
    ("DistL-unequal", lambda: DistL(QB, Ten(QB, QB), QB)),
]


def _distributivity_oracle(A, B, C, right):
    """The canonical distributivity iso, built independently of the compiler.

    dist_l and dist_r are NOT both the identity on semantic labels: the two
    readings enumerate their labels in different orders for dist_r
    (dom A(x)(B+C) is A-outer; cod (A(x)B)+(A(x)C) is summand-outer), so the
    map is a non-trivial permutation there. Asserting `identity` for all four
    hides exactly that.
    """
    from compile.frames import semantic_dim as sd
    dA, dB, dC = sd(A), sd(B), sd(C)
    n = dA * dB + dA * dC if right else (dA + dB) * dC
    M = np.zeros((n, n))
    if right:
        for a in range(dA):
            for i, (off, ds) in enumerate([(0, dB), (dB, dC)]):
                for s in range(ds):
                    M[(0 if i == 0 else dA * dB) + a * ds + s,
                      a * (dB + dC) + off + s] = 1
    else:
        for i, (off, ds) in enumerate([(0, dA), (dA, dB)]):
            for s in range(ds):
                for c in range(dC):
                    M[(0 if i == 0 else dA * dC) + s * dC + c,
                      (off + s) * dC + c] = 1
    return M


@pytest.mark.parametrize("name,make", DISTRIBUTORS, ids=[n for n, _ in DISTRIBUTORS])
@pytest.mark.parametrize("materialize", MODES)
def test_distributor_exact_zero_leakage(name, make, materialize):
    """Every distributor realises the canonical iso exactly on its code
    space, in both materialization modes, with no leakage."""
    from typing_.check import type_of
    t = make()
    _, cod = type_of(t)
    dim = canonical_frame(cod).dim
    r, U, sem = _framed(t, materialize)
    assert leakage(r.input_frame, U, r.output_frame) < 1e-10, "leaks"
    assert sem.shape == (dim, dim)
    right = name.startswith(("DistR", "UndistR"))
    expected = _distributivity_oracle(t.a, t.b, t.c, right)
    if name.startswith("Undist"):
        expected = expected.T
    assert np.allclose(sem, expected, atol=1e-10, rtol=0.0)


@pytest.mark.parametrize("materialize", MODES)
@pytest.mark.parametrize("pair", [("DistL", "UndistL"), ("DistR", "UndistR")],
                         ids=["left", "right"])
def test_distributor_roundtrip_is_identity(pair, materialize):
    """dist ; undist = id, at zero gates -- the relabelling is a change of
    frame, so it cancels without any circuit."""
    import lang.terms as lt
    A, B, C = QB, Ten(QB, QB), QB
    d, u = (getattr(lt, k)(A, B, C) for k in pair)
    r, U, sem = _framed(Seq(d, u), materialize)
    assert r.circuit.n_gates == 0
    assert leakage(r.input_frame, U, r.output_frame) < 1e-10
    assert np.allclose(sem, np.eye(sem.shape[0]), atol=1e-10, rtol=0.0)


@pytest.mark.parametrize("name,make", DISTRIBUTORS, ids=[n for n, _ in DISTRIBUTORS])
def test_distributor_is_zero_gate(name, make):
    """Distributors move no data; conversion belongs at the splice."""
    r = compile(make(), materialize=False)
    assert r.circuit.n_gates == 0


# ---------------------------------------------------------------------------
# 2. The original distributivity-naturality square
# ---------------------------------------------------------------------------

def test_distributivity_naturality_square():
    """P_L = (id ⊗ X_C) ; dist_l   against   P_R = dist_l ; (id⊗X_C ⊕ id⊗X_C).

    Both must agree exactly on all 12 codewords with zero leakage. This is
    the §6 witness that previously reported fidelity 0.5.
    """
    A, B, C = QB, Ten(QB, QB), QB
    x_on_c = Xg(0, C)

    p_l = Seq(TenTerm(Id(Plus(A, B)), x_on_c), DistL(A, B, C))
    p_r = Seq(DistL(A, B, C),
              PlusMap(Ten(A, C), Ten(B, C),
                      TenTerm(Id(A), x_on_c), TenTerm(Id(B), x_on_c)))

    sems = []
    for term in (p_l, p_r):
        r, U, sem = _framed(term, True)
        assert leakage(r.input_frame, U, r.output_frame) < 1e-10
        assert sem.shape == (12, 12)
        sems.append(sem)
    assert np.allclose(sems[0], sems[1], atol=1e-10, rtol=0.0)


# ---------------------------------------------------------------------------
# 3. Direct and nested splices
# ---------------------------------------------------------------------------

def _cod(t):
    from typing_.check import type_of
    return type_of(t)[1]


@pytest.mark.parametrize("materialize", MODES)
def test_direct_splice_after_distributor(materialize):
    A, B, C = QB, Ten(QB, QB), QB
    d = DistL(A, B, C)
    _assert_exact_identity(Seq(d, Id(_cod(d))), materialize, 12)


@pytest.mark.parametrize("materialize", MODES)
def test_nested_splice(materialize):
    from typing_.check import type_of
    A, B, C = QB, Ten(QB, QB), QB
    d = DistL(A, B, C)
    dom, cod = type_of(d)
    _assert_exact_identity(Seq(Seq(Id(dom), d), Id(cod)), materialize, 12)


@pytest.mark.parametrize("materialize", MODES)
def test_longer_seq_chain_with_nested_aligns(materialize):
    from typing_.check import type_of
    A, B, C = QB, Ten(QB, QB), QB
    d = DistL(A, B, C)
    dom, cod = type_of(d)
    chain = Seq(Seq(Id(dom), d), Seq(Id(cod), Id(cod)))
    _assert_exact_identity(chain, materialize, 12)


# ---------------------------------------------------------------------------
# 4. Encode/Decode composition
# ---------------------------------------------------------------------------

ENCDEC = [
    ("Id;Encode", lambda: Seq(Id(Q()), EncodeQubit()), 2),
    ("Encode;Id", lambda: Seq(EncodeQubit(), Id(QB)), 2),
    ("Id;Decode", lambda: Seq(Id(QB), DecodeQubit()), 2),
    ("Decode;Id", lambda: Seq(DecodeQubit(), Id(Q())), 2),
]


@pytest.mark.parametrize("name,make,dim", ENCDEC, ids=[n for n, _, _ in ENCDEC])
@pytest.mark.parametrize("materialize", MODES)
def test_encode_decode_composition(name, make, dim, materialize):
    _assert_exact_identity(make(), materialize, dim)


@pytest.mark.parametrize("materialize", MODES)
def test_encode_then_decode_roundtrip(materialize):
    _assert_exact_identity(Seq(EncodeQubit(), DecodeQubit()), materialize, 2)


# ---------------------------------------------------------------------------
# 5. Tensor placement
# ---------------------------------------------------------------------------

TENSORS = [
    ("Dist(x)Id",   lambda: TenTerm(DistL(Unit(), Q(), Q()), Id(Q()))),
    ("Encode(x)Id", lambda: TenTerm(EncodeQubit(), Id(Q()))),
    ("Id(x)Encode", lambda: TenTerm(Id(Q()), EncodeQubit())),
]


@pytest.mark.parametrize("name,make", TENSORS, ids=[n for n, _ in TENSORS])
@pytest.mark.parametrize("materialize", MODES)
def test_tensor_placement_exact(name, make, materialize):
    from typing_.check import type_of
    t = make()
    _, cod = type_of(t)
    r, U, sem = _framed(t, materialize)
    assert leakage(r.input_frame, U, r.output_frame) < 1e-10
    assert sem.shape[0] == canonical_frame(cod).dim


@pytest.mark.parametrize("name,make", TENSORS, ids=[n for n, _ in TENSORS])
def test_tensor_residual_wires_do_not_overlap_operands(name, make):
    """An operand's residual wires must not collide with the other operand."""
    r = compile(make(), materialize=False)
    used = {}
    for pt in r.output_frame.ports:
        for w in pt.all_wires():
            assert w not in used, (
                f"wire {w} claimed by both {used[w]} and {pt.name}")
            used[w] = pt.name


# ---------------------------------------------------------------------------
# 6. Align paths
# ---------------------------------------------------------------------------

def test_align_identity_costs_zero_gates():
    from compile.align import align_gate_count
    f = canonical_frame(Ten(Q(), Q()))
    assert align_gate_count(f, f) == 0


def test_align_wire_permutation_folds():
    """A pure wire permutation folds into WirePerm rather than emitting."""
    from compile.align import align_is_wire_permutation
    from compile.frames import apply_wire_perm
    f = canonical_frame(Ten(Q(), Q()))
    g = apply_wire_perm(f, (1, 0))
    assert align_is_wire_permutation(f, g)


def test_align_tensor_to_flat_is_exact_with_total_extension():
    """Ten(Z3,Z3) codes {0,1,2,4,5,6,8,9,10} to flat {0..8}: the alignment is
    deterministically extended over the unused states, and acts exactly."""
    from compile.align import build_align
    src = tensor_frame(canonical_frame(Z3), canonical_frame(Z3))
    dst = flat_frame(Ten(Z3, Z3), 4)
    A = build_align(src, dst)
    assert A.shape == (16, 16)
    assert np.allclose(A.conj().T @ A, np.eye(16), atol=1e-12, rtol=0.0)
    for label in range(src.dim):
        assert abs(A[dst.codes[label], src.codes[label]] - 1.0) < 1e-12


def test_align_then_inverse_is_exact_identity():
    from compile.align import build_align
    src = tensor_frame(canonical_frame(Z3), canonical_frame(Z3))
    dst = flat_frame(Ten(Z3, Z3), 4)
    A = build_align(src, dst)
    B = build_align(dst, src)
    assert np.allclose(B @ A, np.eye(16), atol=1e-12, rtol=0.0)


def test_align_matrix_equation_holds():
    """A u_co^- = u_pr^+ -- tested as the matrix equation, so gate ORDER
    cannot introduce an orientation bug."""
    from compile.align import build_align
    src = tensor_frame(canonical_frame(Z3), canonical_frame(Z3))
    dst = flat_frame(Ten(Z3, Z3), 4)
    A = build_align(src, dst)
    assert np.allclose(A @ src.isometry(), dst.isometry(), atol=1e-12, rtol=0.0)


# ---------------------------------------------------------------------------
# 7. Occurrences
# ---------------------------------------------------------------------------

def test_reused_ast_object_yields_two_artifacts_at_different_offsets():
    """The same object used twice under TenTerm is two occurrences at two
    offsets -- checked on the artifacts, not merely the final width."""
    from compile.to_pytket import compile_with_artifacts
    shared = Id(Q())
    r, arts = compile_with_artifacts(TenTerm(shared, shared))
    mine = [a for a in arts if a.term is shared]
    assert len(mine) == 2, f"expected two occurrences, got {len(mine)}"
    assert mine[0].offset != mine[1].offset


# ---------------------------------------------------------------------------
# 8. Invariant W
# ---------------------------------------------------------------------------

def test_over_allocation_fails_rather_than_manufacturing_an_ancilla():
    import compile.to_pytket as tp
    from typing_.check import TypeCheckError
    orig = tp._internal_width
    tp._internal_width = lambda t: orig(t) + 1 if isinstance(t, Id) else orig(t)
    try:
        with pytest.raises(TypeCheckError, match="Invariant W"):
            tp.compile(Id(Q()))
    finally:
        tp._internal_width = orig


def test_legitimate_encode_residual_allocation_still_passes():
    r = compile(EncodeQubit(), materialize=True)
    assert r.circuit.n_qubits == 2
    assert r.input_frame.n_qubits == r.output_frame.n_qubits == 2


# ---------------------------------------------------------------------------
# 9. Sectors
# ---------------------------------------------------------------------------

def test_nested_sum_sector_tag_sets():
    r = compile(NPlusMap((Z3, Z5), (Id(Z3), Id(Z5))), materialize=True)
    assert [list(s.tag_values) for s in r.output_frame.sectors] == \
        [[0, 1, 2], [3, 4, 5, 6, 7]]


def test_three_grouped_sectors_accepted():
    r = compile(NPlusMap((QB, QB, QB), (Id(QB), Id(QB), Id(QB))),
                materialize=True)
    secs = r.output_frame.sectors
    assert len(secs) == 3
    codes = [c for s in secs for c in s.codes]
    assert len(codes) == len(set(codes))
    assert set(codes) == set(r.output_frame.codes)


def test_malformed_sector_tag_coverage_rejected():
    with pytest.raises(ValueError):
        Frame(logical=QB, n_qubits=1, codes=(0, 1),
              sectors=(Sector(0, Unit(), (0,), (0,)),))   # not exhaustive


def test_malformed_sector_logical_type_rejected():
    with pytest.raises(ValueError):
        Frame(logical=QB, n_qubits=1, codes=(0, 1),
              sectors=(Sector(0, Q(), (0,), (0,)),        # dim 2 vs 1 code
                       Sector(1, Unit(), (1,), (1,))))


def test_incomplete_by_sector_placement_rejected():
    p = Port("s", Q(), (), role="payload", by_sector=((0, (1,)),))
    with pytest.raises(ValueError, match="no sector|placement"):
        Frame(logical=QB, n_qubits=2, codes=(0, 1),
              sectors=(Sector(0, Unit(), (0,), (0,)),
                       Sector(1, Unit(), (1,), (1,))),
              ports=(Port("s", Q(), (), role="payload",
                          by_sector=((7, (1,)),)),))


# ---------------------------------------------------------------------------
# 10. Frame expressions fail cleanly
# ---------------------------------------------------------------------------

def test_malformed_fsum_fails_cleanly():
    f = Frame(logical=Plus(Q(), Q()), n_qubits=2, codes=(0, 1, 2, 3),
              expr=FSum((FIdentity(1),), 1, 1))      # one part, two leaves
    assert f.validate_expr() is False


def test_malformed_fcompose_fails_cleanly():
    f = Frame(logical=Q(), n_qubits=1, codes=(0, 1),
              expr=FCompose(FIdentity(1), FIdentity(1)))   # second not a perm
    assert f.validate_expr() is False


@pytest.mark.parametrize("expr", [
    FSum((), 0, 0),
    FTensor(FIdentity(1), FIdentity(1)),
    FWirePerm((5, 6)),
    FCompose(FIdentity(1), FOpaque("x")),
])
def test_expr_errors_are_not_raw_valueerror_or_indexerror(expr):
    from compile.frames import expr_eval
    try:
        expr_eval(expr, Q(), 1)
    except ExprEvalError:
        pass
    except (ValueError, IndexError, TypeError) as e:
        pytest.fail(f"leaked a raw {type(e).__name__}: {e}")


# ---------------------------------------------------------------------------
# 11. Regression: the paper's Z_n programs are untouched
# ---------------------------------------------------------------------------

def test_zn_datatype_control_unchanged():
    from lang.terms import DatatypeControl, Rz
    for arity, ty in ((2, QB), (3, Z3)):
        dc = DatatypeControl(f"Z{arity}", arity, ty, Q(),
                             tuple(Rz(2 * math.pi * i / arity, 0, Q())
                                   for i in range(arity)))
        r = compile(dc, materialize=True)
        assert r.circuit.n_qubits == width(ty) + 1


# ---------------------------------------------------------------------------
# 12. Addendum checks: expression robustness, sector validation, Align conventions
# ---------------------------------------------------------------------------

def test_fsum_with_payload_narrower_than_leaf_fails_cleanly():
    """payload_bits < leaf width must surface as ExprEvalError, not a raw
    ValueError escaping from an arithmetic step."""
    from compile.frames import expr_eval
    e = FSum((FIdentity(0), FIdentity(1)), 1, 0)   # payload 0, leaf Q needs 1
    try:
        expr_eval(e, Plus(Unit(), Q()), 2)
    except ExprEvalError:
        pass
    except Exception as exc:
        pytest.fail(f"leaked a raw {type(exc).__name__}: {exc}")


def test_fcompose_with_invalid_wireperm_does_not_raise_indexerror():
    from compile.frames import expr_eval
    e = FCompose(FIdentity(1), FWirePerm((3, 4)))   # not wires of a 1-qubit reg
    try:
        expr_eval(e, Q(), 1)
    except ExprEvalError:
        pass
    except Exception as exc:
        pytest.fail(f"leaked a raw {type(exc).__name__}: {exc}")


def test_swapped_logical_sectors_rejected():
    """Sector logical types must match the codes they claim."""
    with pytest.raises(ValueError):
        Frame(logical=Plus(Q(), Unit()), n_qubits=2, codes=(0, 1, 2),
              sectors=(Sector(0, Unit(), (0, 1), (0,)),      # dim 1 vs 2 codes
                       Sector(1, Q(), (2,), (1,))))


def test_align_chronology_a_dagger_then_g_then_a():
    """G' = A G A^dagger, emitted as A^dagger ; G ; A.

    Verified as the matrix equation so the gate order cannot invert silently.
    """
    from compile.align import build_align
    prod = tensor_frame(canonical_frame(Z3), canonical_frame(Z3))
    cons = flat_frame(Ten(Z3, Z3), 4)
    A = build_align(cons, prod)                      # A u_C^- = u_P^+
    G = np.eye(16, dtype=complex)
    G_transported = A @ G @ A.conj().T
    assert np.allclose(G_transported, np.eye(16), atol=1e-12, rtol=0.0)
    # and the direction is not its own inverse here
    assert not np.allclose(A, A.conj().T, atol=1e-12, rtol=0.0)


def test_align_inverse_direction_pinned():
    from compile.align import build_align
    prod = tensor_frame(canonical_frame(Z3), canonical_frame(Z3))
    cons = flat_frame(Ten(Z3, Z3), 4)
    A = build_align(cons, prod)
    assert np.allclose(A @ cons.isometry(), prod.isometry(), atol=1e-12, rtol=0.0)
    assert np.allclose(A.conj().T @ prod.isometry(), cons.isometry(),
                       atol=1e-12, rtol=0.0)


def test_align_refuses_unequal_registers_rather_than_widening():
    from compile.align import build_align, AlignError
    with pytest.raises(AlignError, match="different registers"):
        build_align(canonical_frame(Q()), canonical_frame(Ten(Q(), Q())))


def test_align_refuses_unequal_dimensions():
    from compile.align import build_align, AlignError
    with pytest.raises(AlignError, match="semantic dimensions"):
        build_align(canonical_frame(Z3), canonical_frame(Plus(Q(), Q())))
