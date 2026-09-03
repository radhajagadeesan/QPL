# src/compile/to_pytket.py
"""Compiler: Source Term ==> pytket Circuit, using permutations as metadata."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Tuple

from pytket.circuit import Circuit, OpType

from lang.terms import (
    Term, Id, Seq, TenTerm,
    TwistTen, AssocTenL, AssocTenR,
    TwistPlus, AssocPlusL, AssocPlusR,
    DistL, DistR, UndistL, UndistR,
    WireIdentity, TagPerm,
    Feedback,
    # Phase 0 gates
    H, S, CX,
    # Phase 4C fixed gates
    X, Y, Z, T, Tdg, Sdg, CZ, CCX, CSWAP,
    # Phase 4C parameterized gates
    Rz, Rx, Ry, Phase, CRz,
    # Controlled single-qubit gates
    CH, CS, CSdg,
    # Compact-closed structure
    Cup, Cap,
    # Higher-order constructs
    FunVar, Lam, Apply,
    # Tensor intro/elim and variables (full source language)
    Pair, LetPair, Var,
    # Case/copairing and bifunctor
    Case,
    CaseExpr,
    PlusMap,
    NPlusMap,
    PhasedPlusMap,
    PhasedControl,
    # Exponentials of structural involutions
    ExpSwap, ExpInvolution,
    # Controlled combinator
    Ctrl,
    # Qubit encoding isomorphism
    EncodeQubit, DecodeQubit,
    GlobalPhase,
    DatatypeControl,
    Sum,
)
from lang.types import width, Arrow, Unit, Plus, Ten, pretty as _pretty_ty
from dataclasses import dataclass as _dc_alias, replace as _dc_replace
from compile.frames import (Frame, Sector, Port, canonical_frame,
                            ProvenanceScope, ProvenanceError, TypedBinding,
                            NeedsBranchPreparation, plan_open_occurrence,
                            BranchInputs, SelectionContext, EMPTY_SELECTION,
                            BoundaryChart, ChartRoute, ChartFactor,
                            chart_of_frame, par_then_repart, scatter_repart,
                            localize_scatter,
                            SelectedBoundary,
                            frames_agree, semantic_dim,
                            apply_wire_perm, with_spectators,
                            distl_frames, encode_qubit_frames,
                            distributor_frames,
                            UnsupportedFrame, embeddings_agree)
from compile.align import (emit_align, align_as_wire_permutation,
                           align_is_identity, align_permutation,
                           build_align, transported_frame, AlignError)

# Type alias for compilation environment
# Maps variable names to (start, width) wire ranges in the logical layout
Env = dict[str, tuple[int, int]]
from typing import NamedTuple
from typing_.check import type_of, assert_well_typed, TypeCheckError
from core.perm import (
    WirePerm, identity, compose, inverse,
    twist_tensor_perm, assoc_tensor_L_perm, assoc_tensor_R_perm,
    twist_plus_perm, assoc_plus_L_perm, assoc_plus_R_perm,
    dist_L_perm, dist_R_perm, undist_L_perm, undist_R_perm,
    TaggedPerm, tagged_from_perm, tagged_compose,
    is_involution, decompose_involution,
)
from backends.materialize import swaps_for_perm, apply_swaps


@dataclass
class Artifact:
    """The effective artifact of ONE occurrence of a subterm.

    Carries what a splice actually needs: the frames selected for this
    occurrence, its physical offset, and the pending permutation at entry and
    exit. Recording frames alone is not enough -- two occurrences of the same
    AST object sit at different offsets, and a consumer must align against
    the producer's effective output, not against a type.
    """
    term: object
    occurrence: int
    offset: int
    input_frame: object
    output_frame: object
    perm_at_entry: tuple = ()
    perm_at_exit: tuple = ()
    plan: object = None          # PlusMapAlignPlan, when this occurrence has one
    cut_id: object = None        # this OCCURRENCE's cut lineage, minted per visit
    placement: object = None     # G2: the shadow OccurrencePlacement, if any
    # The derivation-selected boundary of THIS occurrence, resolved before the
    # artifact is built. Never a deferred description to be interpreted later.
    selected_boundary: object = None
    # The ambient wires this occurrence's INPUT boundary arrives on and its
    # OUTPUT boundary leaves on, in local order. Recorded independently: the
    # two are NOT the same tuple, and a structural relabeller (TwistTen,
    # DistR, Seq, Lam) reorders one relative to the other.
    ingress_wires: tuple = ()
    egress_wires: tuple = ()

    @property
    def n_qubits(self) -> int:
        return max(self.input_frame.n_qubits, self.output_frame.n_qubits)


@dataclass(frozen=True, slots=True)
class Compiled:
    """A compiled artifact.

    `perm` is an OPTIMISATION, not the semantic boundary representation --
    the frames below are authoritative. Frames and ports are recorded by the
    emitter that produced the artifact (the typed term is the derivation);
    downstream compilation only transports or aligns them, and must never
    reconstruct them from `type_of`.

    `global_phase` is tracked explicitly because the backend circuit
    representation may discard it, and the framed semantics is compared
    exactly -- (iX)(iX) = -I must be distinguishable from +I.

    Frames default to None while emitters are being made frame-aware; a None
    frame means "this emitter has not yet recorded its selection", never
    "use the canonical frame of the type".
    """
    circuit: Circuit
    perm: WirePerm
    log: Optional[List[str]] = None
    input_frame: Optional["Frame"] = None
    output_frame: Optional["Frame"] = None
    input_ports: tuple = ()
    output_ports: tuple = ()
    global_phase: float = 0.0
    selected_boundary: object = None


# --- Auto-flatten helpers for nested PlusMap → NPlusMap conversion ---

def _try_flatten_plusmap(t):
    """Try to flatten a nested PlusMap into an NPlusMap.

    Returns an NPlusMap if the PlusMap tree can be recursively decomposed
    into per-leaf branches, or None if any branch is opaque.
    """
    from lang.types import Plus, flatten_plus
    if not isinstance(t, PlusMap):
        return None
    left_leaves = flatten_plus(t.ty_left) if isinstance(t.ty_left, Plus) else [t.ty_left]
    right_leaves = flatten_plus(t.ty_right) if isinstance(t.ty_right, Plus) else [t.ty_right]
    # Base case: genuinely binary, no flattening needed
    if len(left_leaves) == 1 and len(right_leaves) == 1:
        return None
    # Recursive case: decompose branches
    left_branches = _extract_branches(t.left, t.ty_left)
    right_branches = _extract_branches(t.right, t.ty_right)
    if left_branches is None or right_branches is None:
        return None  # Can't decompose — caller raises error
    all_types = tuple(left_leaves + right_leaves)
    all_branches = tuple(left_branches + right_branches)
    return NPlusMap(all_types, all_branches)


def _extract_branches(term, ty):
    """Extract per-leaf branches from a term operating on a Plus type.

    Returns a list of per-leaf branch terms, or None if decomposition fails.
    """
    from lang.types import Plus, flatten_plus
    leaves = flatten_plus(ty) if isinstance(ty, Plus) else [ty]
    if len(leaves) == 1:
        return [term]  # Leaf: term is already the branch
    if isinstance(term, (PlusMap, Case)):
        # PlusMap and Case have identical structure: ty_left, ty_right, left, right
        left_br = _extract_branches(term.left, term.ty_left)
        right_br = _extract_branches(term.right, term.ty_right)
        if left_br is not None and right_br is not None:
            return left_br + right_br
    if isinstance(term, Seq):
        # Seq(Id, g) → extract from g (Id is identity, doesn't change branches)
        if isinstance(term.f, Id):
            return _extract_branches(term.g, ty)
        # Seq(f, Id) → extract from f
        if isinstance(term.g, Id):
            return _extract_branches(term.f, ty)
    if isinstance(term, Id):
        # Id on a Plus type: each leaf gets Id on its own type
        return [Id(leaf) for leaf in leaves]
    return None  # Cannot decompose opaque branch


# Distributivity is now supported with tagged layout model - no longer need to block it


def _contains_dist(t: Term) -> bool:
    """Check if term contains DistL, DistR, UndistL, or UndistR anywhere."""
    if isinstance(t, (DistL, DistR, UndistL, UndistR)):
        return True
    if isinstance(t, Seq):
        return _contains_dist(t.f) or _contains_dist(t.g)
    if isinstance(t, TenTerm):
        return _contains_dist(t.f) or _contains_dist(t.g)
    if isinstance(t, Feedback):
        return _contains_dist(t.body)
    return False


def _shared_width(t: Term) -> int:
    """Compute the physical wire width, accounting for distributivity sharing.

    For terms containing DistL or DistR, the syntactic domain and codomain types
    have different naive widths, but the physical layout is the same under the
    sharing model.

    This function computes the actual physical width by traversing the term
    and using the domain width (which is canonical for distributivity).
    """
    dom, _ = type_of(t)
    return width(dom)


def _contains_feedback(t: Term) -> bool:
    """Check if term contains Feedback anywhere."""
    if isinstance(t, Feedback):
        return True
    if isinstance(t, Seq):
        return _contains_feedback(t.f) or _contains_feedback(t.g)
    if isinstance(t, TenTerm):
        return _contains_feedback(t.f) or _contains_feedback(t.g)
    if isinstance(t, Ctrl):
        return _contains_feedback(t.body)
    return False


def _contains_encode_decode(t: Term) -> bool:
    """Check if term contains EncodeQubit or DecodeQubit anywhere."""
    if isinstance(t, (EncodeQubit, DecodeQubit)):
        return True
    if isinstance(t, Seq):
        return _contains_encode_decode(t.f) or _contains_encode_decode(t.g)
    if isinstance(t, TenTerm):
        return _contains_encode_decode(t.f) or _contains_encode_decode(t.g)
    if isinstance(t, Feedback):
        return _contains_encode_decode(t.body)
    return False



def _reconstruct_value(phys_wires: list[int], ty, deferred_fns: dict) -> Term | None:
    """Reconstruct a term value from physical wire positions and deferred Lam info.

    For Arrow-typed wire ranges that match a deferred Lam, returns that Lam.
    For Ten types, recursively decomposes into Pair of sub-values.
    For unknown/data types, returns Id(ty) as a placeholder.
    Returns None only if the reconstruction fails completely.
    """
    from lang.types import Arrow, Ten, Unit as UnitTy, width as w
    total_w = w(ty)
    if total_w == 0:
        return Id(UnitTy())
    if isinstance(ty, Arrow):
        key = tuple(phys_wires[:total_w])
        if key in deferred_fns:
            return deferred_fns[key]
        return Id(ty)  # No deferred value — identity placeholder
    if isinstance(ty, Ten):
        wL = w(ty.left)
        wR = w(ty.right)
        left_val = _reconstruct_value(phys_wires[:wL], ty.left, deferred_fns)
        right_val = _reconstruct_value(phys_wires[wL:wL + wR], ty.right, deferred_fns)
        if left_val is not None and right_val is not None:
            return Pair(left_val, right_val)
        return None
    # Atomic data type (Q, Plus, Unit, etc.) — identity
    return Id(ty)


def _inject_input_value(branch: Term, input_value: Term) -> Term:
    """Replace the first LetPair(x, y, Id(...), body) with LetPair(x, y, input_value, body).

    This injects a known input value into a branch's LetPair chain so that
    _normalize can propagate values and β-reduce inner Apply(Var, ...) terms.
    """
    if isinstance(branch, LetPair) and isinstance(branch.pair, Id):
        return LetPair(branch.x, branch.y, branch.ty_x, branch.ty_y,
                       input_value, branch.body)
    return branch


def _has_spectator_coordinates(t: Term) -> bool:
    """True if t's physical frame legitimately exceeds width(cod).

    Spectator coordinates are physical wires the logical codomain does not
    name: Lam/Apply function-layout wires, Cup/Cap compact-closed wires,
    free-variable context wires, and the legacy encode/decode ancilla. For
    every other term the frame width IS the logical width, which is what
    Invariant W's corollary asserts.
    """
    from typing_.check import _free_var_width
    if _free_var_width(t) > 0:
        return True
    if _contains_encode_decode(t):
        return True

    stack = [t]
    while stack:
        u = stack.pop()
        if isinstance(u, (Lam, Apply, Cup, Cap, FunVar)):
            return True
        stack.extend(_subterms(u))
    return False


class BranchPlacement(NamedTuple):
    """Where ONE branch physically sits inside its parent, in LOCAL wire
    coordinates (wire 0 is the parent's own first wire).

    This is the single authority for the placement. Both the frame lifting
    and the wire map used for emitted commands read `payload_base` from here,
    so the `max(k,1)` formula exists in exactly one place; when the two were
    computed separately they could drift apart without any test noticing.
    """
    index: int
    tag_value: int
    tag_wires: tuple
    payload_base: int
    width: int                  # the ARTIFACT's frame width, not width(type)
    logical_in: object
    logical_out: object
    K_minus: tuple
    K_plus: tuple
    local_to_block: tuple = ()  # branch-local wire -> parent-local block wire
    ports_in: tuple = ()        # lifted Port objects, parent-local wires
    ports_out: tuple = ()

    def wire(self, local_branch_wire: int) -> int:
        """Branch-local wire -> parent-local wire, at the controlled-block
        stage. THE authority: the K lift, the lifted ports and the emitted
        commands all read this one tuple.

        It is not `payload_base + i` in general. On the Strategy A path a
        sum-typed branch's inner tag sits in the parent's TAG register, so its
        wire 0 lands at k-1, not at k -- for Q's right branch the mapping is
        (1, 2), where `payload_base + i` would say (2, 3)."""
        return self.local_to_block[local_branch_wire]


class PlusMapAlignPlan(NamedTuple):
    """The occurrence-selected plan for one closed binary PlusMap.

    Retains the TYPED sectors and the lifted branch ports. F_pre and F_mid are
    deliberately code-only Align operands -- they name coordinates, not
    ownership -- so the typed metadata lives here rather than being invented
    onto them. In particular a parent residual port is never copied onto them:
    V makes exactly such a coordinate live, and claiming it is still residual
    would be false.
    """
    n_qubits: int
    tag_wires: tuple
    payload_base: int
    placements: tuple
    F_pre: object
    F_mid: object
    parent_in: object
    parent_out: object

    @property
    def K_minus(self):
        return tuple(pl.K_minus for pl in self.placements)

    @property
    def K_plus(self):
        return tuple(pl.K_plus for pl in self.placements)


def _lift_port(pt, local_to_block):
    """A branch Port, carried into parent-local coordinates.

    Name, logical type, role, wires AND by_sector all survive. Every wire goes
    through the placement tuple -- NOT `+ payload_base`, which is wrong
    wherever the branch's inner tag sits in the parent's tag register. The
    by_sector TAG VALUES are left alone: they index the branch's own inner
    sectors, while the outer sector is supplied by the enclosing
    BranchPlacement.tag_value, and rewriting them would conflate two sum
    levels.
    """
    def mv(ws):
        return tuple(local_to_block[w] for w in ws)
    return Port(name=pt.name, logical=pt.logical, role=pt.role,
                wires=mv(pt.wires),
                by_sector=tuple((tv, mv(ws)) for tv, ws in pt.by_sector),
                owner_id=pt.owner_id, cut_id=pt.cut_id,
                origin_cut=pt.origin_cut)


def _lift_via_placement(codes, tag_value, n_qubits, local_to_block,
                        P_inv=None, pw_parent=None, selector_bits=1):
    """Branch code -> parent code, THROUGH the placement tuple.

    The branch's w-bit code is scattered onto the block wires named by
    `local_to_block` (big-endian: branch bit j is the j-th most significant),
    the left/right selector goes to wire 0, and on the Strategy A path the
    resulting block tag is carried back through P^-1 into the parent's own
    coordinates.

    `selector_bits` is how many leading wires the selector owns: 1 for the
    binary paths, where it is the single left/right bit, and k for the
    NPlusMap fast path, where branch i owns the whole k-bit tag word i.

    All three paths share this; only `local_to_block`, `selector_bits` and the
    presence of P differ.
    """
    w = len(local_to_block)
    out = []
    for c in codes:
        block = tag_value << (n_qubits - selector_bits)
        for j in range(w):
            if (c >> (w - 1 - j)) & 1:
                block |= 1 << (n_qubits - 1 - local_to_block[j])
        if P_inv is not None:
            tag = block >> pw_parent
            if tag >= len(P_inv):
                return None
            block = (P_inv[tag] << pw_parent) | (block & ((1 << pw_parent) - 1))
        out.append(block)
    return tuple(out)


def _strategy_a_local_to_block(sub_ty, artifact_n, k):
    """`_sub_wire_to_full` at offset 0 -- the Strategy A placement tuple."""
    from lang.types import tag_width as _tw
    sub_tw = _tw(sub_ty) if isinstance(sub_ty, Plus) else 0
    if sub_tw > k - 1:
        return None
    tup = tuple(_sub_wire_to_full(i, sub_tw, 0, k) for i in range(artifact_n))
    return tup if all(0 <= wr < 64 for wr in tup) else None


class StrategyBDensePlan(NamedTuple):
    """Strategy B's occurrence plan.

    Deliberately NOT a BranchPlacement: Strategy B does not factor through
    wires at all, it synthesizes one full-register unitary. What it owes is an
    ordered CODE MAP per sector, from the branch artifact's own frame codes
    onto the parent's sector codes:

        artifact fin  code[j]  ->  K_i^-[j]
        artifact fout code[j]  ->  K_i^+[j]

    Taking K_i^- = J_i^- and K_i^+ = J_i^+ makes (1) and (3) identity by
    construction, so no intermediate egress frame is ever formed. That matters:
    the old ingress-geometry arithmetic produced (2,4,6,8) for SB_R, a code
    outside the 3-qubit register, so an intermediate egress is not merely
    inconvenient -- it is not representable.
    """
    n_qubits: int
    K_minus: tuple          # per sector, ordered parent codes
    K_plus: tuple
    in_maps: tuple          # per sector: ((artifact_code, parent_code), ...)
    out_maps: tuple
    free_in: tuple          # deterministic complement, ascending
    free_out: tuple
    logicals_in: tuple
    logicals_out: tuple


# --- primitive gates on framed sum boundaries ------------------------------
#
# A raw qubit gate on a TAG wire of a SPARSE sum frame can carry valid codes
# out of the code space, producing an artifact whose recorded frames the
# circuit leaks out of. Diagonal gates move no code and are always safe;
# payload gates never touch the tag; a dense frame has no unused codes to
# leak into. Everything else must be proved code-space preserving.

_GATE_SHAPE = {}          # term class name -> (pytket OpType name, arity)


def _gate_shape(t):
    """(OpType, local wires) for a primitive gate term, or None."""
    from pytket.circuit import OpType
    name = type(t).__name__
    table = {
        "H": (OpType.H, ("i",)), "X": (OpType.X, ("i",)),
        "Y": (OpType.Y, ("i",)), "Z": (OpType.Z, ("i",)),
        "S": (OpType.S, ("i",)), "Sdg": (OpType.Sdg, ("i",)),
        "T": (OpType.T, ("i",)), "Tdg": (OpType.Tdg, ("i",)),
        "CX": (OpType.CX, ("i", "j")), "CZ": (OpType.CZ, ("i", "j")),
        "CCX": (OpType.CCX, ("i", "j", "k")),
        "CSWAP": (OpType.CSWAP, ("c", "i", "j")),
    }
    if name not in table:
        return None
    op, fields = table[name]
    try:
        wires = tuple(int(getattr(t, f)) for f in fields)
    except AttributeError:
        return None
    return op, wires


def _gate_preserves_code_space(op, wires, n_qubits, codes):
    """True iff the gate maps every valid code into the span of valid codes.

    Exact, not conservative: the gate's own unitary is built on |wires| qubits
    and only the transitions it ACTUALLY makes are checked, so a permutation
    gate is not rejected merely because some unrelated bit pattern is unused.
    """
    from pytket.circuit import Circuit
    m = len(wires)
    sub = Circuit(m)
    sub.add_gate(op, list(range(m)))
    U = sub.get_unitary()
    valid = set(codes)
    for c in codes:
        idx = 0
        for slot, w in enumerate(wires):
            if (c >> (n_qubits - 1 - w)) & 1:
                idx |= 1 << (m - 1 - slot)
        col = U[:, idx]
        for row in range(1 << m):
            if abs(col[row]) <= 1e-12:
                continue
            c2 = c
            for slot, w in enumerate(wires):
                mask = 1 << (n_qubits - 1 - w)
                c2 = (c2 | mask) if (row >> (m - 1 - slot)) & 1 else (c2 & ~mask)
            if c2 not in valid:
                return False
    return True


def _check_primitive_frame(t, frame):
    """Raise before emission if a primitive would leave the code space."""
    if frame is None or not frame.codes:
        return
    n = frame.n_qubits
    if len(frame.codes) == (1 << n):
        return                                  # dense: nothing to leak into
    shape = _gate_shape(t)
    if shape is None:
        return
    op, wires = shape
    if any(not (0 <= w < n) for w in wires):
        return
    if _gate_preserves_code_space(op, wires, n, tuple(frame.codes)):
        return
    from compile.frames import pretty as _pretty
    raise UnsupportedFrame(
        f"{type(t).__name__} on wire(s) {list(wires)} does not preserve the "
        f"code space of {_pretty(frame.logical)}: the frame has "
        f"{len(frame.codes)} valid codes {tuple(frame.codes)} in a "
        f"{n}-qubit register, and this gate carries some of them onto unused "
        f"states. Emitting the raw gate would record boundary frames the "
        f"circuit leaks out of. Failing closed before emission.")


def _as_uniformly_controlled_u2(U):
    """Recognize a uniformly controlled U2 in the COMPLETED matrix itself.

    Not inferred from pw == 1 or from any type-level property: the test is on
    the matrix. Every cross-block 2x2 must be exactly zero and every diagonal
    2x2 must be unitary. Returns the 2^(n-1) diagonal blocks in control-state
    order, or None.
    """
    import numpy as np
    dim = U.shape[0]
    if dim < 4 or dim % 2:
        return None
    nb = dim // 2
    blocks = []
    for a in range(nb):
        for b in range(nb):
            blk = U[2 * a:2 * a + 2, 2 * b:2 * b + 2]
            if a == b:
                if not np.allclose(blk.conj().T @ blk, np.eye(2),
                                   atol=1e-10, rtol=0.0):
                    return None
            elif not np.allclose(blk, 0, atol=1e-10, rtol=0.0):
                return None
        blocks.append(U[2 * a:2 * a + 2, 2 * a:2 * a + 2])
    return blocks


# G2 only: lets a test capture the placement of an occurrence whose emission
# still raises. Successful occurrences carry it on their Artifact instead.
_PLANNER_OBSERVED = []
_PLANNER_INCOMPLETE = []


def _plusmap_placement(n_qubits, k):
    """(tag_wires, payload_base) in LOCAL coordinates. The only definition."""
    base = max(k, 1)
    return tuple(range(k)), base


def _sum_sectors(frame, summands):
    """The ONE sector policy for sum frames -- shared by NPlusMap and PlusMap.

    Sectors say which codes belong to which branch: ordered, typed, disjoint
    and exhaustive.

    A summand that is itself a sum spans SEVERAL tag words -- in (Z3, Z5) the
    second spans 3..7 -- so `tag_values` is DERIVED from the codes and the
    payload width, never assumed to be the summand index.

    Callers must pass the UNWIDENED frame: the derivation is
    `code >> payload_width`, and widening shifts every code left, so deriving
    tags after widening records corrupted outer tags. `with_spectators` then
    shifts the sector codes and carries tag_values through unchanged.
    """
    from lang.types import payload_width as _pwf
    from compile.frames import Sector as _Sec
    pw = _pwf(frame.logical) if isinstance(frame.logical, Plus) else 0
    secs, at = [], 0
    for i, sm in enumerate(summands):
        d = semantic_dim(sm)
        codes = frame.codes[at:at + d]
        tags = tuple(sorted({c >> pw for c in codes}))
        secs.append(_Sec(i, sm, codes, tags))
        at += d
    return tuple(secs)


def _with_sum_sectors(frame, summands, label):
    """Re-label `frame` with sectors, preserving its ports.

    ports= is not optional: rebuilding a Frame without it silently drops
    truthful residual/context metadata.

    If the summands do not tile the frame -- which happens when a summand is
    Arrow-typed, so its encoding is a wire bundle rather than a sum region --
    no sectors are recorded. Recording a wrong tiling would be worse than
    recording none.
    """
    if sum(semantic_dim(sm) for sm in summands) != frame.dim:
        return frame
    return Frame(logical=frame.logical, n_qubits=frame.n_qubits,
                 codes=frame.codes, expr=frame.expr, label=label,
                 sectors=_sum_sectors(frame, summands), ports=frame.ports)


def _nplusmap_frames(t):
    """NPlusMap's selection: independent ingress and egress, sectors, then a
    common register.

    Ingress and egress are canonical frames of their own types and may have
    different natural widths -- (IA (+) BIA (+) I) needs 4 qubits while its
    image (IA (+) (IA (+) IA) (+) I) needs 3. Selecting them at those two
    widths and stopping there left the emitter with a 4-qubit register and a
    3-qubit output frame, which Invariant W rejects outright: the artifact
    could not even be built, let alone be truthful.

    Sectors are recorded BEFORE widening -- tag_values derive as
    `code >> payload_width`, and widening shifts every code -- and
    `with_spectators` then carries sectors, tag_values and ports through,
    recording the pad as a typed residual port. The allocator consumes this
    selected width; W is not repaired downstream.
    """
    from lang.types import build_plus_tree
    dom = build_plus_tree(list(t.summand_types))
    cods = [type_of(br)[1] for br in t.branches]
    cod = build_plus_tree(cods)
    fin, fout = canonical_frame(dom), canonical_frame(cod)
    fin = _with_sum_sectors(fin, list(t.summand_types), "NPlusMap in")
    fout = _with_sum_sectors(fout, cods, "NPlusMap out")
    want = max(fin.n_qubits, fout.n_qubits)
    if fin.n_qubits < want:
        fin = with_spectators(fin, want)
    if fout.n_qubits < want:
        fout = with_spectators(fout, want)
    return fin, fout


def _plusmap_frames(t):
    """Binary PlusMap's selection, with exactly TWO sectors on each boundary.

    The two boundaries are selected INDEPENDENTLY: neither is inferred from
    the other, and they are not assumed equal. Their sectors are the parent's
    occurrence-level inclusions J_L^-, J_R^- (ingress) and J_L^+, J_R^+
    (egress).

    Code selection is unchanged from the generic canonical path: this adds
    sectors and nothing else.
    """
    d_, c_ = type_of(t)                  # Plus(ty_left, ty_right) -> Plus(cods)
    fin, fout = canonical_frame(d_), canonical_frame(c_)
    out_summands = [type_of(t.left)[1], type_of(t.right)[1]]
    # Sectors BEFORE widening; with_spectators then shifts codes and adds the
    # residual port itself.
    fin = _with_sum_sectors(fin, [t.ty_left, t.ty_right], "PlusMap in")
    fout = _with_sum_sectors(fout, out_summands, "PlusMap out")
    want = max(fin.n_qubits, fout.n_qubits)
    if fin.n_qubits < want:
        fin = with_spectators(fin, want)
    if fout.n_qubits < want:
        fout = with_spectators(fout, want)
    return fin, fout


def allocation_width(t: Term, env: Env = None) -> int:
    """The register width for `t` -- the SINGLE authority.

    Both the allocator and `select_frames` call this, so the emitter's frames
    and the circuit agree by construction and Invariant W's content becomes
    "nobody allocated something other than this", which is the drift it
    exists to catch.
    """
    # Deliberately NOT max(width(dom), width(cod)): the judgment types fix the
    # semantic space, not the embedding, and folding them in here is what
    # overrode dist_l's 4-qubit selection with a 5-qubit register.
    # Composites allocate structurally from their operands, so that an
    # operand needing a wider register than its judgment type (Encode's
    # ancilla, a distributor's shared layout) is actually given the room --
    # otherwise the emitter's selection and the register disagree.
    if isinstance(t, TenTerm):
        return allocation_width(t.f, env) + allocation_width(t.g, env)
    if isinstance(t, Seq):
        return max(allocation_width(t.f, env), allocation_width(t.g, env))

    n = _internal_width(t)
    if _contains_encode_decode(t):
        n = max(n, 2)          # the legacy one-hot pair works in two wires
    if env:
        for phys_list in env.values():
            for phys in phys_list:
                n = max(n, phys + 1)
    return n


def _distributor_canonical_frames(t):
    """The canonical frames of a distributor, when its own wire permutation
    actually realises the canonical iso -- otherwise None.

    Equal WIDTH is not the right criterion: UndistR(I, I, Bool) has a 2-qubit
    domain and codomain whose canonical embeddings are codes (0,2,3) and
    (0,1,2), which no wire permutation relates. Nor is "the permutation makes
    the two frames identical": the permutation's job is to IMPLEMENT the
    relabelling, so for dist_r both frames are canonical and the wire swap is
    what realises the iso. The truthful check is that the permutation carries
    each domain code to the codomain code of its image under the canonical
    iso; then the framed semantics is exactly that iso, with no leakage, at
    zero gates, and the artifact's public boundary stays canonical.
    """
    from compile.frames import distributor_iso, permute_index
    d_, c_ = type_of(t)
    cd, cc = canonical_frame(d_), canonical_frame(c_)
    if cd.n_qubits != cc.n_qubits or cd.dim != cc.dim:
        return None
    fn = {DistL: dist_L_perm, DistR: dist_R_perm,
          UndistL: undist_L_perm, UndistR: undist_R_perm}[type(t)]
    tagged = fn(t.a, t.b, t.c)
    if tagged.tag_perm is not None or tagged.tag_flips:
        return None                    # tag moves are not plain wire moves
    # The FORWARD map: permute_index already sends a physical index to where
    # this wire permutation puts it. Using the inverse here passes anyway for
    # a symmetric perm -- DistR(Q,I,I) is [1,0] -- and fails for an
    # asymmetric one such as DistR(Q(x)Q,I,I) at [2,0,1], the same trap that
    # hid the pending-permutation direction error behind TwistTen(Q,Q).
    fwd = list(tagged.perm.new_to_old)
    try:
        iso = distributor_iso(t.a, t.b, t.c, type(t).__name__)
    except Exception:
        return None
    for k, code in enumerate(cd.codes):
        if permute_index(code, fwd, cd.n_qubits) != cc.codes[iso[k]]:
            return None
    return cd, cc


def _check_open_placement(*, branch_name, payload_phys, context_phys,
                          tag_phys, cmds, wire_map):
    """Reject an overlapping open-branch placement BEFORE emission.

    A pre-emission safety guard only: it repairs nothing, infers no frame and
    adds no metadata. It uses evidence already computed on this path -- the
    payload/context/tag physical placements and the mapped argument list of
    each command -- and converts what would otherwise surface from inside the
    backend ("Multiple operation arguments reference q[N]") into a
    deterministic UnsupportedFrame naming the wire and the two roles.
    """
    roles = (("tag", list(tag_phys)),
             ("payload", list(payload_phys)),
             ("context", list(context_phys)))
    for role, wires in roles:
        if len(set(wires)) != len(wires):
            dup = next(w for w in wires if wires.count(w) > 1)
            raise UnsupportedFrame(
                f"{branch_name}: the {role} placement {wires} is not "
                f"injective -- physical wire {dup} is claimed twice. "
                f"Failing closed before emission.")
    for i in range(len(roles)):
        for j in range(i + 1, len(roles)):
            (ra, wa), (rb, wb) = roles[i], roles[j]
            shared = sorted(set(wa) & set(wb))
            if shared:
                raise UnsupportedFrame(
                    f"{branch_name}: physical wire {shared[0]} is claimed by "
                    f"both the {ra} placement {wa} and the {rb} placement "
                    f"{wb}. The derivation does not identify that coordinate "
                    f"with itself, so the branch cannot be emitted. Failing "
                    f"closed before emission.")
    for cmd in cmds:
        mapped = [wire_map(qb.index[0]) for qb in cmd.qubits]
        if len(set(mapped)) != len(mapped):
            dup = next(w for w in mapped if mapped.count(w) > 1)
            raise UnsupportedFrame(
                f"{branch_name}: operation {cmd.op.type.name} would receive "
                f"physical wire {dup} twice (mapped arguments {mapped}). "
                f"Failing closed before emission.")


def select_frames(t: Term, ctx=None):
    """Select this term's boundary frames.

    `ctx` is the derivation's SelectionContext. Passing EMPTY_SELECTION
    asserts the occurrence is provably closed and FAILS for an open term --
    otherwise the context-free fallback this model removes would simply return
    under a new name. `ctx=None` is the not-yet-migrated legacy path.
    """
    if ctx is not None:
        ctx.require_closed(
            t, [nm for nm, _ in _ordered_free_vars(t)],
            where=f"select_frames({type(t).__name__})")
    return _select_frames_impl(t)


def _select_frames_impl(t: Term):
    """The boundary frames the emitter for `t` selects.

    Emitter-specific selections come first; everything else selects the
    canonical frame of its own interface. This is consulted BEFORE the
    register is allocated, so that a derivation which chooses a narrower
    layout actually gets it -- sizing from judgment types instead silently
    overrides the selection.
    """
    if isinstance(t, (DistL, DistR, UndistL, UndistR)):
        # The shared narrower layout exists to solve a WIDTH mismatch: sizing
        # from the judgment types gives (for unequal-width dist_l) a 5-qubit
        # domain against a 4-qubit codomain and wrongly suggests no gate-free
        # distributor exists.
        #
        # Where the two canonical widths already agree there is no such
        # mismatch, so the canonical frames are selectable and are preferred:
        # they keep the artifact's public boundary canonical. Choosing the
        # shared layout there instead would hand every external caller a
        # rotated interface -- dist_r's domain reading is A-outer while the
        # shared layout is tag-outer, which made QSwitch[id,id] compare
        # against a canonically framed `id` at fidelity 0.5.
        #
        # In the equal-width case the two canonical layouts differ by a WIRE
        # permutation, which the emitter contributes and which costs no gates.
        _canon = _distributor_canonical_frames(t)
        if _canon is not None:
            return _canon
        return distributor_frames(t.a, t.b, t.c, type(t).__name__)
    if isinstance(t, TenTerm):
        # Compose the operands' SELECTED frames, including any residual
        # wires they hold. Falling back to the canonical frame of the tensor
        # type would ignore an operand's own layout choice and let its
        # residual coordinates collide with the other operand's.
        from compile.frames import tensor_frame as _tf
        lf_in, lf_out = select_frames(t.f)
        rf_in, rf_out = select_frames(t.g)
        return (_tf(lf_in, rf_in, label="ten in"),
                _tf(lf_out, rf_out, label="ten out"))

    if isinstance(t, Seq):
        # A Seq's effective boundary is its producer's input and its
        # consumer's output, taken from their own selections.
        f_in, _ = select_frames(t.f)
        _, g_out = select_frames(t.g)
        n_amb = max(f_in.n_qubits, g_out.n_qubits)
        if f_in.n_qubits < n_amb:
            f_in = with_spectators(f_in, n_amb, residual_name="splice_pad")
        if g_out.n_qubits < n_amb:
            g_out = with_spectators(g_out, n_amb, residual_name="splice_pad")
        return f_in, g_out

    if isinstance(t, NPlusMap):
        return _nplusmap_frames(t)
    if isinstance(t, PlusMap):
        return _plusmap_frames(t)

    if isinstance(t, EncodeQubit):
        return encode_qubit_frames()
    if isinstance(t, DecodeQubit):
        fin, fout = encode_qubit_frames()
        return fout, fin                       # Decode is Encode reversed

    d_, c_ = type_of(t)
    fin, fout = canonical_frame(d_), canonical_frame(c_)

    # A term whose interfaces have different widths, or which needs scratch
    # wires (Lam/Apply function layout), SELECTS both frames in the register
    # it actually uses, recording the extra coordinates as residual ports.
    # This is a declared selection, not boundary widening: it happens here,
    # in the one place selection lives, so the allocator and the emitter agree
    # by construction and Invariant W stays strict.
    # Selection is INDEPENDENT of allocation: it must not consult
    # _internal_width, or the two move together and Invariant W -- which
    # compares the allocation against the independently selected frames --
    # becomes vacuous.
    want = max(fin.n_qubits, fout.n_qubits)
    if fin.n_qubits < want:
        fin = with_spectators(fin, want)
    if fout.n_qubits < want:
        fout = with_spectators(fout, want)
    return fin, fout


def _internal_width(t: Term) -> int:
    """Compute internal wire width needed for a term.

    For most terms, this is max(width(dom), width(cod)).
    For higher-order terms (Lam, Apply), we need extra wires for the function layout.
    """
    from lang.types import width as type_width

    if isinstance(t, Lam):
        # Lam needs width(A) + width(B) for the function layout [A_slot | B_slot]
        # For open lambdas (body has free variables), the body needs
        # ctx_w extra wires during execution for the context.
        wA = type_width(t.dom)
        wB = type_width(t.cod)
        body_internal = _internal_width(t.body)
        from typing_.check import _free_var_width
        ctx_w = _free_var_width(t.body, frozenset({t.name}))
        return max(wA + wB, ctx_w + body_internal)

    if isinstance(t, Apply):
        # Nested Apply chain fully β-reducible: compute width on the reduced form
        # so we don't over-allocate for the abstract layout.
        reduced = _peel_apply_chain(t, {})
        if reduced is not None:
            return _internal_width(reduced)

        # Apply needs f's internal width (which includes [A_slot | B_slot])
        # plus arg's internal width, but they overlap on A_slot
        f_dom, f_cod = type_of(t.f)
        if isinstance(f_cod, Arrow):
            wA = type_width(f_cod.dom)
            wB = type_width(f_cod.cod)
            # Check for closed lambda: f_dom = Unit means no context wires
            # In this case, we can compile as β-reduced (arg;body) with no extra wires
            if isinstance(t.f, Lam) and isinstance(f_dom, Unit):
                # Closed lambda application: internal width is just wA (= wB for endomorphisms)
                arg_internal = _internal_width(t.arg)
                body_internal = _internal_width(t.f.body)
                return max(wA, wB, arg_internal, body_internal)
            else:
                f_internal = _internal_width(t.f)
                arg_internal = _internal_width(t.arg)
                # f and arg overlap on A_slot, so we need max, not sum
                return max(wA + wB, f_internal, arg_internal)
        else:
            # Fallback
            dom, cod = type_of(t)
            return max(type_width(dom), type_width(cod))

    if isinstance(t, Seq):
        return max(_internal_width(t.f), _internal_width(t.g))

    if isinstance(t, TenTerm):
        return _internal_width(t.f) + _internal_width(t.g)

    if isinstance(t, LetPair):
        return max(_internal_width(t.pair), _internal_width(t.body))

    if isinstance(t, Pair):
        return _internal_width(t.fst) + _internal_width(t.snd)

    if isinstance(t, Sum):
        # Frame width, not logical width: the target carries the tag plus the
        # shared payload of the completed branches.
        dom_s, cod_s = type_of(t)
        return max(type_width(dom_s), type_width(cod_s),
                   max((_internal_width(b) for b in (t.left, t.right)), default=0))

    if isinstance(t, (DistL, DistR, UndistL, UndistR)):
        # All four distributors are gate-free in the derivation-selected
        # SHARED layout; sizing from the judgment types instead gives (for
        # dist_l) a 5-qubit domain against a 4-qubit codomain and wrongly
        # suggests no gate-free distributor exists. Allocation must READ the
        # selection here rather than recompute a width of its own -- a second
        # width policy would silently override the selected frame.
        _fi, _fo = select_frames(t)
        return max(_fi.n_qubits, _fo.n_qubits)

    if isinstance(t, DatatypeControl):
        # Tensor frame: [ D_tag | A payload ].  Deliberately NOT the flat sum
        # frame -- see the DatatypeControl docstring.
        from lang.types import tag_width as _tw_dc, Ten as _Ten_dc
        k_dc = _tw_dc(t.dt_rep)
        br_int = max((_internal_width(b) for b in t.branches), default=0)
        return max(type_width(_Ten_dc(t.dt_rep, t.a_ty)), k_dc + br_int)

    if isinstance(t, NPlusMap):
        # Invariant L: size from the CANONICAL layout of the whole domain, not
        # from an independent (branch-count + max-summand) allocation. The old
        # formula diverged from the flat encoding exactly when a summand is
        # itself a sum — e.g. (Z3, Z5): canonical 3 vs old 1 + 3 = 4 — leaving
        # the emitter and the register allocator disagreeing about the frame.
        from lang.types import (build_plus_tree, flatten_plus,
                                tag_width as _tw)
        dom_sum = build_plus_tree(list(t.summand_types))
        canonical = type_width(dom_sum)
        leaf_counts = [len(flatten_plus(st)) for st in t.summand_types]
        if all(m == 1 for m in leaf_counts):
            # Controlled-emission path: branch circuits are emitted into the
            # shared payload region, so the parent must also cover k + branch.
            branch_internal = max(_internal_width(br) for br in t.branches)
            return max(canonical, _tw(dom_sum) + branch_internal)
        # Block-synthesis path: branches are compiled separately and only their
        # unitaries are splatted, so the parent needs exactly the canonical frame.
        return canonical

    # Default: use type widths
    dom, cod = type_of(t)
    return max(type_width(dom), type_width(cod))


# ── Term-level normalization (mirrors OCaml elaboration) ─────────────
#
# The OCaml elaborator β-reduces Apply(Lam(x,A,e), v) and substitutes
# LetTen bindings before sending to Python.  For terms built directly
# via the Python API we do the same transformations here so that Case
# branches never contain free variables.
#
#   LetPair(x, y, Pair(v1, v2), body) → body[v1/x, v2/y]
#   Var(name) with name in subst_env    → subst_env[name]

def _contains_var(term: Term, name: str) -> bool:
    """Check if term contains a free reference to Var(name)."""
    if isinstance(term, Var):
        return term.name == name
    if isinstance(term, Seq):
        return _contains_var(term.f, name) or _contains_var(term.g, name)
    if isinstance(term, TenTerm):
        return _contains_var(term.f, name) or _contains_var(term.g, name)
    if isinstance(term, Pair):
        return _contains_var(term.fst, name) or _contains_var(term.snd, name)
    if isinstance(term, LetPair):
        if _contains_var(term.pair, name):
            return True
        if term.x == name or term.y == name:
            return False  # shadowed
        return _contains_var(term.body, name)
    if isinstance(term, Lam):
        if term.name == name:
            return False  # shadowed
        return _contains_var(term.body, name)
    if isinstance(term, Apply):
        return _contains_var(term.f, name) or _contains_var(term.arg, name)
    if isinstance(term, Case):
        return _contains_var(term.left, name) or _contains_var(term.right, name)
    if isinstance(term, CaseExpr):
        if _contains_var(term.scrut, name):
            return True
        if term.x == name or term.y == name:
            return False
        return _contains_var(term.left, name) or _contains_var(term.right, name)
    if isinstance(term, PlusMap):
        return _contains_var(term.left, name) or _contains_var(term.right, name)
    if isinstance(term, NPlusMap):
        return any(_contains_var(b, name) for b in term.branches)
    return False


def _substitute(term: Term, name: str, replacement: Term) -> Term:
    """Replace every Var(name, _) in *term* with *replacement*."""
    if isinstance(term, Var):
        return replacement if term.name == name else term
    if isinstance(term, Id):
        return term
    if isinstance(term, Seq):
        return Seq(_substitute(term.f, name, replacement),
                   _substitute(term.g, name, replacement))
    if isinstance(term, TenTerm):
        return TenTerm(_substitute(term.f, name, replacement),
                       _substitute(term.g, name, replacement))
    if isinstance(term, Pair):
        return Pair(_substitute(term.fst, name, replacement),
                    _substitute(term.snd, name, replacement))
    if isinstance(term, LetPair):
        new_pair = _substitute(term.pair, name, replacement)
        # Don't substitute into body if x or y shadows name
        if term.x == name or term.y == name:
            return LetPair(term.x, term.y, term.ty_x, term.ty_y,
                           new_pair, term.body)
        new_body = _substitute(term.body, name, replacement)
        return LetPair(term.x, term.y, term.ty_x, term.ty_y,
                       new_pair, new_body)
    if isinstance(term, Lam):
        # Don't substitute into body if the Lam binds the same name
        if term.name == name:
            return term
        new_body = _substitute(term.body, name, replacement)
        return Lam(term.name, term.dom, term.cod, new_body)
    if isinstance(term, Apply):
        return Apply(_substitute(term.f, name, replacement),
                     _substitute(term.arg, name, replacement))
    if isinstance(term, Case):
        return Case(term.ty_left, term.ty_right,
                    _substitute(term.left, name, replacement),
                    _substitute(term.right, name, replacement))
    if isinstance(term, CaseExpr):
        new_scrut = _substitute(term.scrut, name, replacement)
        new_left = term.left if term.x == name else _substitute(term.left, name, replacement)
        new_right = term.right if term.y == name else _substitute(term.right, name, replacement)
        return CaseExpr(new_scrut, term.x, term.y, term.ty_x, term.ty_y,
                        new_left, new_right)
    if isinstance(term, PlusMap):
        return PlusMap(term.ty_left, term.ty_right,
                       _substitute(term.left, name, replacement),
                       _substitute(term.right, name, replacement))
    if isinstance(term, NPlusMap):
        new_branches = tuple(_substitute(b, name, replacement) for b in term.branches)
        return NPlusMap(term.summand_types, new_branches)
    # Structural isos, gates, etc. — no sub-terms containing Var
    return term


def _normalize(term: Term) -> Term:
    """Normalize a term by substituting LetPair bindings.

    Mirrors the OCaml elaborator's Let/LetTen elimination:
      LetPair(x, y, Pair(v1, v2), body) → body[v1/x, v2/y]
    Applied recursively until no more substitutions are possible.
    """
    if isinstance(term, LetPair):
        # First normalize the pair
        pair = _normalize(term.pair)
        if isinstance(pair, Pair):
            # Substitute v1 for x and v2 for y in body, then re-normalize
            body = _substitute(term.body, term.x, pair.fst)
            body = _substitute(body, term.y, pair.snd)
            return _normalize(body)
        # pair is not a Pair literal — keep the LetPair, normalize body
        return LetPair(term.x, term.y, term.ty_x, term.ty_y,
                       pair, _normalize(term.body))
    if isinstance(term, Seq):
        return Seq(_normalize(term.f), _normalize(term.g))
    if isinstance(term, TenTerm):
        return TenTerm(_normalize(term.f), _normalize(term.g))
    if isinstance(term, Pair):
        return Pair(_normalize(term.fst), _normalize(term.snd))
    if isinstance(term, Lam):
        return Lam(term.name, term.dom, term.cod, _normalize(term.body))
    if isinstance(term, Apply):
        return Apply(_normalize(term.f), _normalize(term.arg))
    if isinstance(term, Case):
        return Case(term.ty_left, term.ty_right,
                    _normalize(term.left), _normalize(term.right))
    if isinstance(term, CaseExpr):
        return CaseExpr(_normalize(term.scrut), term.x, term.y,
                        term.ty_x, term.ty_y,
                        _normalize(term.left), _normalize(term.right))
    if isinstance(term, PlusMap):
        return PlusMap(term.ty_left, term.ty_right,
                       _normalize(term.left), _normalize(term.right))
    if isinstance(term, NPlusMap):
        return NPlusMap(term.summand_types,
                        tuple(_normalize(b) for b in term.branches))
    # Structural isos, gates, FunVar, Cup, Cap, etc. — leaves
    return term


def _compile_branch(branch, *, env=None, scope=None):
    """Sole route from a branch TERM to controlled-emission material.

    Returns (cmds, phase_ht). Invariant P: the caller MUST discharge phase_ht
    as an exact-tag relative phase at every tag value the branch covers --
    `_discharge_branch_phase` below does that. Commands are only obtainable
    together with the phase, so a call site cannot silently drop the scalar.

    A scalar z.I is unobservable standing alone and fully observable inside a
    branch. It was dropped independently at six sites, and each round of
    per-site fixes missed the others; that is why extraction is funnelled here
    rather than repeated at each emitter.
    """
    a = _compile_branch_artifact(branch, env=env, scope=scope)
    return a.cmds, a.phase


class BranchArtifact(NamedTuple):
    """One branch, compiled ONCE: its commands, its scalar, BOTH of its own
    frames, and its exact unitary. The frames must travel with the commands -- re-deriving them
    later from `type_of` gives the declared type's width, which is not the
    artifact's frame width (DistL(Z3,I,I) declares 2 -> 3 but its artifact
    frames are 3 and 3), and the branch would then be lifted to the wrong
    coordinates."""
    cmds: list
    phase: float
    fin: Frame
    fout: Frame
    circuit: object = None      # the SAME compilation, for its exact unitary
    # preserved from that one nested compilation, already resolved
    selected_boundary: object = None

    @property
    def unitary(self):
        """The branch's exact unitary, phase included (pytket's get_unitary
        carries circuit.phase). Computed from the ONE compilation above --
        never a second compile."""
        return None if self.circuit is None else self.circuit.get_unitary()

    def framed_action(self):
        """G_i = u(fout)^dagger U u(fin), in the branch's own frames."""
        u = self.unitary
        if u is None:
            raise ValueError("BranchArtifact carries no circuit")
        from compile.frames import semantic_action as _sa
        return _sa(self.fin, u, self.fout)


def _compile_branch_artifact(branch, *, env=None, scope=None):
    """Prepare ONE branch. `scope` parents its provenance to the enclosing
    occurrence; without it the branch would mint its own root."""
    sub = compile(branch, materialize=True, env=env, _prov_scope=scope) \
        if env is not None \
        else compile(branch, materialize=True, _prov_scope=scope)
    return BranchArtifact(_get_sub_cmds(sub.circuit), float(sub.circuit.phase),
                          sub.input_frame, sub.output_frame, sub.circuit,
                          selected_boundary=sub.selected_boundary)


def _discharge_branch_phase(circ, tag_qubits, tag_values, phase_ht):
    """Promote a branch's accumulated scalar to an exact-tag relative phase at
    every tag value the branch covers. Runs even when the branch emitted no
    gates, so a pure-GlobalPhase branch is not lost."""
    if abs(phase_ht) <= 1e-10 or not tag_qubits:
        return
    for tv in tag_values:
        _emit_exact_tag_phase(circ, tag_qubits, tv, phase_ht)


def _emit_exact_tag_phase(circ, tag_qubits, tag_value, theta_ht):
    """Emit an exact-tag phase gate: multiply amplitudes by e^{iπ·θ_ht} on
    the specific basis state |tag_value⟩ of the tag register, identity elsewhere.

    Uses the anti-control pattern: X-flip bits that are 0 in the big-endian
    binary representation of tag_value, apply an all-controls-1 U1(θ_ht),
    then unflip. Big-endian: bit j=0 is the MSB. Matches NPlusMap's
    (branch_idx >> (k - 1 - j)) & 1 convention.

    Sole entry point for exact-tag phase emission; PhasedPlusMap and
    PhasedControl both call this so their tag conventions agree.
    """
    from pytket.circuit import QControlBox, Op
    k = len(tag_qubits)

    flips = [
        j for j in range(k)
        if ((tag_value >> (k - 1 - j)) & 1) == 0
    ]

    for j in flips:
        circ.X(tag_qubits[j])

    if k == 1:
        circ.add_gate(OpType.U1, [theta_ht], [tag_qubits[0]])
    elif k == 2:
        circ.add_gate(OpType.CU1, [theta_ht],
                      [tag_qubits[0], tag_qubits[1]])
    else:
        base = Op.create(OpType.U1, [theta_ht])
        circ.add_qcontrolbox(QControlBox(base, k - 1), tag_qubits)

    for j in reversed(flips):
        circ.X(tag_qubits[j])


def _emit_tag_perm_unitary(circ, p, tag_perm, k, offset, explain, log):
    """Emit a unitary implementing a summand-index permutation on the tag register.

    For nested sums with n > 2 summands, tag_perm is an arbitrary permutation
    of {0, ..., n-1}. This builds the corresponding permutation matrix on the
    k = ceil(log2(n)) tag qubits and emits it via Unitary2qBox / Unitary3qBox.

    Unused computational basis states (n <= idx < 2^k) map to themselves.
    """
    import math
    import numpy as np
    from pytket.circuit import Unitary2qBox

    n = len(tag_perm)
    dim = 2 ** k

    # Build dim x dim permutation matrix.
    # U|i⟩ = |tag_perm[i]⟩ for i < n, U|i⟩ = |i⟩ for i >= n.
    U = np.zeros((dim, dim), dtype=complex)
    for i in range(n):
        U[tag_perm[i], i] = 1.0
    for i in range(n, dim):
        U[i, i] = 1.0

    # Get physical wire positions for the tag qubits
    tag_phys = [p.apply_new_to_old(offset + j) for j in range(k)]

    if k == 2:
        box = Unitary2qBox(U)
        circ.add_unitary2qbox(box, tag_phys[0], tag_phys[1])
    elif k == 3:
        from pytket.circuit import Unitary3qBox
        box = Unitary3qBox(U)
        circ.add_unitary3qbox(box, tag_phys[0], tag_phys[1], tag_phys[2])
    else:
        # For k > 3: pytket has no built-in Unitary4qBox+, but tag_perm IS
        # always a permutation matrix, so use ToffoliBox (synthesizes any
        # bit-string permutation as a sequence of multiplexed rotations).
        from pytket.circuit import ToffoliBox, ToffoliBoxSynthStrat
        perm_pairs = []
        for i in range(dim):
            j = tag_perm[i] if i < n else i  # identity on unused states
            # Big-endian bit-string: bit 0 is most-significant
            inp = tuple(bool((i >> (k - 1 - b)) & 1) for b in range(k))
            out = tuple(bool((j >> (k - 1 - b)) & 1) for b in range(k))
            perm_pairs.append((inp, out))
        box = ToffoliBox(perm_pairs, ToffoliBoxSynthStrat.Matching)
        circ.add_toffolibox(box, tag_phys)

    if explain:
        log.append(f"TagPerm {tag_perm} on {k} qubits, phys={tag_phys}")


def _get_sub_cmds(circuit):
    """Get commands from a materialized sub-circuit for controlled emission.

    QControlBox(op, n) wraps ANY op — including other QControlBoxes and
    UnitaryNqBoxes — so no decomposition is needed. This avoids the
    exponential gate blowup that DecomposeBoxes caused on iterated Ctrl.
    """
    return list(circuit.get_commands())


def _emit_nway_controlled(circ, tag_qubits, branch_idx, sub_cmds, wire_map_fn):
    """Emit multi-controlled gates for a single branch of NPlusMap.

    For branch index `i` with `k` tag qubits (big-endian):
    1. X-flip: For each tag qubit j where bit (i >> (k-1-j)) & 1 == 0, apply X
    2. Multi-controlled gates: All k tag qubits are now 1 for branch i
    3. X-unflip: Undo the X gates from step 1
    """
    from pytket.circuit import QControlBox
    k = len(tag_qubits)

    # X-flip: make all tag bits 1 for this branch
    for j in range(k):
        if not ((branch_idx >> (k - 1 - j)) & 1):
            circ.X(tag_qubits[j])

    # Multi-controlled gates
    for cmd in sub_cmds:
        phys_qubits = [wire_map_fn(q.index[0]) for q in cmd.qubits]
        ctrl_op = _CTRL_GATE_MAP.get(cmd.op.type)
        if ctrl_op is not None and k == 1:
            circ.add_gate(ctrl_op, cmd.op.params, [tag_qubits[0]] + phys_qubits)
        elif cmd.op.type in (OpType.CnX, OpType.CCX):
            # CnX/CCX: n-ary controlled X; prepend k more controls
            circ.add_gate(OpType.CnX, [], tag_qubits + phys_qubits)
        else:
            qcb = QControlBox(cmd.op, k)
            circ.add_qcontrolbox(qcb, tag_qubits + phys_qubits)

    # X-unflip
    for j in range(k):
        if not ((branch_idx >> (k - 1 - j)) & 1):
            circ.X(tag_qubits[j])


# Module-level map from gate types to their controlled versions
_CTRL_GATE_MAP = {
    OpType.H: OpType.CH,
    OpType.S: OpType.CS,
    OpType.Sdg: OpType.CSdg,
    OpType.X: OpType.CX,
    OpType.Y: OpType.CY,
    OpType.Z: OpType.CZ,
    OpType.Rz: OpType.CRz,
    OpType.Rx: OpType.CRx,
    OpType.Ry: OpType.CRy,
    OpType.CX: OpType.CCX,
}


def _sub_wire_to_full(sub_wire, sub_tw, offset, k):
    """Map sub-circuit wire index to full-circuit logical wire index.

    Sub-circuit layout: [inner_tag₀..inner_tag_{tw-1} | payload₀..]
    Full layout (big-endian): [MSB | (k-1 inner tag bits) | payload₀..]
    MSB is at offset (the control qubit).

    The sub-circuit's tag bits must map to the LAST `sub_tw` inner tag bit
    positions, not the FIRST. The leaves of an n-leaf summand are encoded
    at basis states 0..n-1 in the sub-circuit, which corresponds to the
    LOW-ORDER bits being free. In the full circuit's flat encoding (after
    Strategy A's tag permutation P), the left summand's leaves occupy
    positions 0..n_left-1, which use the LOW-ORDER inner tag bits — i.e.,
    the LAST inner tag bits in big-endian ordering.

    For sub_tw == k-1 (left summand fills the MSB=0 half), both first-bits
    and last-bits orderings coincide, so this used to work for balanced
    binary cases.
    """
    if sub_wire < sub_tw:
        # Last sub_tw inner tag bits: q[offset + k - sub_tw .. offset + k - 1]
        return offset + k - sub_tw + sub_wire
    else:
        return offset + k + (sub_wire - sub_tw)  # payload


def _ordered_free_vars(t: Term, bound: frozenset = frozenset()) -> list:
    """Free variables in left-to-right AST order, deduplicated.

    Returns a list of (name, ty) pairs for each unique free variable.
    """
    if isinstance(t, Var):
        return [(t.name, t.ty)] if t.name not in bound else []
    if isinstance(t, LetPair):
        pv = _ordered_free_vars(t.pair, bound)
        bv = _ordered_free_vars(t.body, bound | {t.x, t.y})
        seen = {name for name, _ in pv}
        return pv + [(n, ty) for n, ty in bv if n not in seen]
    if isinstance(t, Lam):
        return _ordered_free_vars(t.body, bound | {t.name})
    if isinstance(t, Pair):
        lv = _ordered_free_vars(t.fst, bound)
        rv = _ordered_free_vars(t.snd, bound)
        seen = {name for name, _ in lv}
        return lv + [(n, ty) for n, ty in rv if n not in seen]
    if isinstance(t, Apply):
        lv = _ordered_free_vars(t.f, bound)
        rv = _ordered_free_vars(t.arg, bound)
        seen = {name for name, _ in lv}
        return lv + [(n, ty) for n, ty in rv if n not in seen]
    if isinstance(t, Seq):
        lv = _ordered_free_vars(t.f, bound)
        rv = _ordered_free_vars(t.g, bound)
        seen = {name for name, _ in lv}
        return lv + [(n, ty) for n, ty in rv if n not in seen]
    if isinstance(t, (PlusMap, Case)):
        lv = _ordered_free_vars(t.left, bound)
        rv = _ordered_free_vars(t.right, bound)
        seen = {name for name, _ in lv}
        return lv + [(n, ty) for n, ty in rv if n not in seen]
    if isinstance(t, NPlusMap):
        result = []
        seen = set()
        for branch in t.branches:
            for name, ty in _ordered_free_vars(branch, bound):
                if name not in seen:
                    result.append((name, ty))
                    seen.add(name)
        return result
    if isinstance(t, TenTerm):
        lv = _ordered_free_vars(t.f, bound)
        rv = _ordered_free_vars(t.g, bound)
        seen = {name for name, _ in lv}
        return lv + [(n, ty) for n, ty in rv if n not in seen]
    return []  # Structural isos, gates, Id, etc.


def _resolve_term(t: Term, term_env: dict) -> Term:
    """Resolve a term through the term environment.

    If t is a Var whose name is in term_env, return the bound term.
    Otherwise return t as-is.
    """
    if isinstance(t, Var) and t.name in term_env:
        return term_env[t.name]
    return t


def _find_lam(f: Term, term_env: dict) -> 'Lam | None':
    """Extract the underlying Lam from a function term, for β-reduction.

    Handles:
    - Lam directly
    - Var(name) where name maps to a Lam in term_env
    - Seq(lam, Id) wrapping (used to prevent eager β-reduction in demos)
    Returns None if no Lam can be found.
    """
    if isinstance(f, Lam):
        return f
    if isinstance(f, Var) and f.name in term_env:
        inner = term_env[f.name]
        if isinstance(inner, Lam):
            return inner
    if isinstance(f, Seq):
        # Seq(lam, Id) is transparent — peel off Id
        if isinstance(f.g, Id):
            return _find_lam(f.f, term_env)
        if isinstance(f.f, Id):
            return _find_lam(f.g, term_env)
    return None


def _peel_apply_chain(t: Term, term_env: dict) -> 'Term | None':
    """Try to fully β-reduce a chain of nested Applies ending in a Lam-stack.

    Pattern: Apply(Apply(...Apply(Lam(x_1, Lam(x_2, ... Lam(x_n, body))), v_1), v_2), ..., v_n)
    Reduces to: body[v_1/x_1][v_2/x_2]...[v_n/x_n]

    The outermost Lam variable x_1 receives the innermost Apply's argument v_1.
    Returns the reduced body, or None if the chain cannot be fully reduced
    (e.g., not enough Lams, or a Lam doesn't use its bound variable — falling
    back protects deferred-value semantics for select_2/qswitch-style terms).
    """
    apply_chain = []
    current = t
    while isinstance(current, Apply):
        apply_chain.append(current)
        current = current.f

    if len(apply_chain) < 2:
        return None  # Single Apply — let existing single-Apply path handle it

    base = current
    if isinstance(base, Var) and base.name in term_env:
        base = term_env[base.name]
    if isinstance(base, Seq) and isinstance(base.g, Id):
        base = base.f

    if not isinstance(base, Lam):
        return None

    # apply_chain is outer→inner. The OUTERMOST Apply (apply_chain[0]) provides
    # the argument for the INNERMOST Lam. So we iterate args inner→outer to
    # match Lams outer→inner.
    args_inner_to_outer = [ac.arg for ac in reversed(apply_chain)]

    body = base
    for arg in args_inner_to_outer:
        if not isinstance(body, Lam):
            return None
        if not _contains_var(body.body, body.name):
            # Lam doesn't use its binding — protect arg's gates by falling back.
            return None
        body = _substitute(body.body, body.name, arg)

    return body


def _contains_lolli(ty) -> bool:
    """True iff the type has an Arrow (Lolli) anywhere."""
    if isinstance(ty, Arrow):
        return True
    if isinstance(ty, Ten):
        return _contains_lolli(ty.left) or _contains_lolli(ty.right)
    if isinstance(ty, Plus):
        return _contains_lolli(ty.left) or _contains_lolli(ty.right)
    return False


def _first_order(ty) -> bool:
    return not _contains_lolli(ty)


def _assert_first_order_sum_payloads(term: Term) -> None:
    """Defense-in-depth soundness check.

    The OCaml surface's case sugars and datatype `control` combinator
    already enforce that sum-typed payloads are first-order — no Lolli
    (Arrow) may appear inside the target type of ⊕-Map / case / ⊕-I / control.

    This function reasserts that invariant on the compiled term itself,
    catching any term whose sum-producing construct emits a Plus type
    containing an Arrow anywhere. It fires only if a guard is missing
    upstream (i.e., a future OCaml refactor loses a check, or a term is
    authored directly at the Python term IR bypassing the OCaml surface).

    Traverses `type_of` at each sum-producing subterm (PlusMap, NPlusMap,
    Case, PhasedPlusMap, PhasedControl) and rejects if any output summand
    is not first-order.
    """
    def _check_sum_output(t: Term, site: str) -> None:
        _, cod = type_of(t)
        if isinstance(cod, Plus) and _contains_lolli(cod):
            raise TypeCheckError(
                f"{site}: sum payloads must be first-order (contain no Lolli).\n"
                f"Function values may be consumed inside a branch, but not "
                f"returned on a summand.\n"
                f"Offending output type: {_pretty_ty(cod)}\n"
                f"(This is the defense-in-depth check in to_pytket.py — the "
                f"OCaml surface's case sugars and datatype `control` should "
                f"have already caught this. If you're seeing this from OCaml "
                f"source, please report it as a missing guard.)"
            )
        # Also catch Case (whose cod is a Plus of the branch cods) and
        # anything whose cod contains a Plus-of-Lolli anywhere.
        if _plus_with_lolli_anywhere(cod):
            raise TypeCheckError(
                f"{site}: nested sum with Lolli payload detected.\n"
                f"Offending output type: {_pretty_ty(cod)}"
            )

    def _walk(t: Term) -> None:
        # Check this node if it produces a sum.
        if isinstance(t, PlusMap):
            _check_sum_output(t, "PlusMap")
        elif isinstance(t, NPlusMap):
            _check_sum_output(t, "NPlusMap")
        elif isinstance(t, Case):
            _check_sum_output(t, "Case")
        elif isinstance(t, CaseExpr):
            # CaseExpr is desugared to Seq(scrut, Case(...)) at compile time,
            # but the first-order guard runs BEFORE desugaring — check here
            # too so the ordinary OCaml case path cannot bypass the restriction.
            _check_sum_output(t, "CaseExpr")
        elif isinstance(t, PhasedPlusMap):
            _check_sum_output(t, "PhasedPlusMap")
        elif isinstance(t, PhasedControl):
            _check_sum_output(t, "PhasedControl")
        # Recurse into subterms.
        for child in _subterms(t):
            _walk(child)

    _walk(term)


def _plus_with_lolli_anywhere(ty) -> bool:
    """True iff ty contains a Plus whose summands contain an Arrow."""
    if isinstance(ty, Plus):
        if _contains_lolli(ty.left) or _contains_lolli(ty.right):
            return True
        return _plus_with_lolli_anywhere(ty.left) or _plus_with_lolli_anywhere(ty.right)
    if isinstance(ty, Ten):
        return _plus_with_lolli_anywhere(ty.left) or _plus_with_lolli_anywhere(ty.right)
    if isinstance(ty, Arrow):
        return _plus_with_lolli_anywhere(ty.dom) or _plus_with_lolli_anywhere(ty.cod)
    return False


def _subterms(t: Term):
    """Yield the immediate subterms of t."""
    if isinstance(t, Seq):
        yield t.f; yield t.g
    elif isinstance(t, TenTerm):
        yield t.f; yield t.g
    elif isinstance(t, Pair):
        yield t.fst; yield t.snd
    elif isinstance(t, LetPair):
        yield t.pair; yield t.body
    elif isinstance(t, Lam):
        yield t.body
    elif isinstance(t, Apply):
        yield t.f; yield t.arg
    elif isinstance(t, Case):
        yield t.left; yield t.right
    elif isinstance(t, CaseExpr):
        yield t.scrut; yield t.left; yield t.right
    elif isinstance(t, PlusMap):
        yield t.left; yield t.right
    elif isinstance(t, PhasedPlusMap):
        yield t.left; yield t.right
    elif isinstance(t, NPlusMap):
        for b in t.branches:
            yield b
    elif isinstance(t, Ctrl):
        yield t.body
    elif isinstance(t, ExpInvolution):
        yield t.body
    # Otherwise no subterms.


def _is_neutral_spine(t: Term) -> bool:
    """Is this a canonical neutral variable spine?

        neutral ::= Var | Apply(neutral, normal_argument)

    Decided from the DERIVATION SHAPE alone -- never from widths, frames,
    fixtures or observed placements. The whole spine is walked before any
    emission, so a non-neutral head buried under applications is refused
    before its argument or head is compiled.

    The `normal_argument` side is enforced by this same guard: compiling an
    inner application runs it again on that application's own head.
    """
    while isinstance(t, Apply):
        t = t.f
    return isinstance(t, Var)


def _slot_wires(perm, offset, w):
    """The ambient wires a width-`w` slot at `offset` names under `perm`.

    Empty when the slot does not fit the register: a boundary wider than the
    register is not placed by this rule, and saying so is better than
    returning a truncated tuple that reads as a placement.
    """
    if w < 0 or offset < 0 or offset + w > len(perm):
        return ()
    return tuple(perm[offset + i] for i in range(w))


def _has_boundary_rule(t: Term) -> bool:
    """Terms whose selected boundary is NOT simply their frames.

    `Apply` builds the AppCut chart; `LetPair` transports its body's. Every
    other term defaults, and says so. Listing them here is what makes the
    default explicit: an occurrence in this set that records nothing is a
    rule that failed to fire, and is rejected rather than quietly defaulted.
    """
    return isinstance(t, (Apply, LetPair))


def compile_with_artifacts(term: Term, *, materialize: bool = False,
                           explain: bool = False, env: Env = None):
    """`compile`, plus every occurrence artifact produced along the way.

    Two occurrences of the same AST object appear as two artifacts at two
    offsets, which is what a splice needs and what `id()`-keyed recording
    could not express.
    """
    out = {}
    res = compile(term, materialize=materialize, explain=explain, env=env,
                  _artifact_sink=out)
    return res, out.get("artifacts", [])


def compile(term: Term, *, materialize: bool = False, explain: bool = False,
            env: Env = None, _artifact_sink=None,
            _prov_scope: "ProvenanceScope" = None) -> Compiled:
    """`_prov_scope` is INTERNAL. A public compile mints exactly one
    ProvenanceScope root; nested branch preparation passes a child of the
    enclosing occurrence's scope so its identities are transitive descendants
    rather than a second, unrelated universe."""
    # Check for Feedback - not currently supported
    if _contains_feedback(term):
        raise NotImplementedError(
            "Feedback terms are not currently supported. "
            "The Feedback constructor exists for future use but has no compilation path."
        )

    # Normalize: substitute LetPair bindings, mirroring OCaml elaboration.
    # This ensures Case branches contain no free variables before type-checking.
    term = _normalize(term)

    assert_well_typed(term)

    _assert_first_order_sum_payloads(term)

    dom, cod = type_of(term)

    # For terms with encode/decode, we always need 2 wires (Q=1, I+I=2).
    # Even if roundtrip Q→Q has width 1, internally we need 2 wires.
    if False:   # superseded: allocation_width handles encode/decode structurally
        n = 2
    else:
        # Compute internal width needed for higher-order terms
        # One authority for the register width, shared with select_frames.
        # No fail-open fallback: if the emitter cannot select frames we stop.
        try:
            _sel_in, _sel_out = select_frames(term)
        except UnsupportedFrame:
            raise                      # dedicated error, surfaced verbatim
        except Exception as _e:
            raise TypeCheckError(
                f"cannot select boundary frames for {type(term).__name__}: "
                f"{_e}")
        n = max(allocation_width(term, env),
                _sel_in.n_qubits, _sel_out.n_qubits)
        # When env is supplied (sub-compile of open PlusMap branches), it may
        # reference physical wire positions beyond the term's declared width.
        # Make sure the circuit is large enough.
        if env:
            for phys_list in env.values():
                for phys in phys_list:
                    if phys + 1 > n:
                        n = phys + 1

    # --- derivation-selected frame recording -------------------------------
    # The typed term IS the derivation: the emitter handling each constructor
    # selects and RECORDS its boundary frames, sectors and ports here.
    # Downstream compilation transports or aligns what was recorded; it must
    # never reconstruct embeddings, sectors, ports or payload locations from
    # type_of. Keyed by id(subterm) so producer and consumer frames at a
    # splice stay independently addressable (checkpoint 2 consumes these).
    # Keyed by OCCURRENCE, not by id(subterm): the same AST object may appear
    # twice at different offsets, and id() would collapse the two derivations
    # into one entry. Each entry into `go` takes the next sequence number, so
    # producer and consumer at a splice stay independently addressable.
    frame_registry = {}
    _occurrence = [0]

    def _record_frames(occ, t_, fin, fout, in_ports=(), out_ports=()):
        frame_registry[occ] = (type(t_).__name__, fin, fout,
                               tuple(in_ports), tuple(out_ports))
        return fin, fout

    def _select_default_frames(t_):
        """Delegates to the single module-level `select_frames`.

        There is deliberately no second copy of the selection policy here:
        the allocator and the emitter must agree by construction, and a
        duplicated policy is how they drift apart.
        """
        return select_frames(t_)

    def go(t: Term, offset: int = 0, env: Env = None, *, is_value: bool = False):
        """Emit `t` and return its EFFECTIVE artifact for this occurrence."""
        occ = _occurrence[0]
        _occurrence[0] += 1
        # Minted per VISIT, so two occurrences of one AST object never share a
        # cut lineage. Identity of the term object is deliberately not used.
        # Forked per VISIT from the compile-scoped namespace, so two
        # occurrences of one AST object never share a cut lineage and two
        # sibling subcompiles cannot collide.
        _cut_ids[occ] = _prov.fork().cut()
        try:
            fin, fout = select_frames(t)
        except UnsupportedFrame:
            raise
        except Exception as _e:
            raise TypeCheckError(
                f"cannot select boundary frames for {type(t).__name__}: {_e}")
        entry = tuple(p.new_to_old)
        prev_occ = _cur_occ[0]
        _cur_occ[0] = occ
        try:
            _go_body(t, offset, env, is_value=is_value,
                     parent_in=fin, parent_out=fout)
        finally:
            _cur_occ[0] = prev_occ
        # An emitter may report a TRANSPORTED output frame (Seq after Align);
        # that effective frame, not the selected one, is what propagates.
        fout = _frame_override.pop(occ, fout)
        # The selected boundary is resolved HERE, per occurrence, before the
        # artifact exists -- never left as a description for the root to
        # interpret. An occurrence whose term has a selected-boundary rule
        # must have recorded one; otherwise a rule that silently failed to
        # fire would be indistinguishable from the ordinary default.
        _sb = _boundary_sink.pop(occ, None)
        if _sb is None:
            if _has_boundary_rule(t):
                raise TypeCheckError(
                    f"{type(t).__name__} has a selected-boundary rule but "
                    f"recorded no boundary for occurrence {occ}; a missing "
                    f"rule must not fall through to the frame default "
                    f"(docs/COMPILER_INVARIANTS.md)")
            _sb = SelectedBoundary.from_frames(fin, fout)
        elif isinstance(_sb, str):
            # An explicit request for the default, with the reason recorded.
            _sb = SelectedBoundary.from_frames(fin, fout, origin=_sb)
        # The two placements, derived SEPARATELY. The egress is the slot this
        # occurrence leaves its result on; the ingress is where its input
        # arrived, which for a term that CLAIMS a slot (Var binding a context
        # resource, Seq inheriting its producer's) is not the entry naming of
        # that slot -- those emitters record their own and the default is
        # used otherwise.
        _exit = tuple(p.new_to_old)
        _egr_w = _slot_wires(_exit, offset, fout.n_qubits)
        _ing_w = _placement_sink.pop(occ, None)
        if _ing_w is None:
            _ing_w = _slot_wires(entry, offset, fin.n_qubits)
        art = Artifact(term=t, occurrence=occ, offset=offset,
                       input_frame=fin, output_frame=fout,
                       perm_at_entry=entry, perm_at_exit=tuple(p.new_to_old),
                       plan=_plan_sink.pop(occ, None),
                       cut_id=_cut_ids[occ],
                       placement=_shadow_plans.pop(occ, None),
                       selected_boundary=_sb,
                       ingress_wires=_ing_w, egress_wires=_egr_w)
        frame_registry[occ] = art
        artifacts.append(art)
        return art

    artifacts = []
    _frame_override = {}
    _plan_sink = {}
    _cut_ids = {}
    _prov = _prov_scope if _prov_scope is not None else ProvenanceScope()
    _binding_cache = {}
    _shadow_plans = {}
    _boundary_sink = {}
    _placement_sink = {}
    _planner_observed = _PLANNER_OBSERVED
    _cur_occ = [0]
    circ = Circuit(n)
    p = identity(n)
    # Track pending tag flips (X gates to emit after permutation tracking)
    pending_tag_flips: List[int] = []
    log: List[str] = []
    # Track variable → original Term bindings for deferred Apply β-reduction.
    # When a Lam is compiled as a function value (inside a Pair/arg), its body
    # is deferred. At Apply(Var(f), arg) time, the Lam body is retrieved and
    # compiled on-the-fly with the argument in place.
    term_env: dict[str, Term] = {}
    # Track deferred function values by physical wire positions.
    # When a Lam is compiled as a value (is_value=True), we record its
    # physical wire range so PlusMap branch sub-compilations can reconstruct
    # the input value and β-reduce Apply(Var("f"), ...) terms.
    deferred_fns: dict[tuple[int, ...], Term] = {}

    def emit_H(i: int, offset: int = 0) -> None:
        global_idx = i + offset
        phys = p.apply_new_to_old(global_idx)
        circ.H(phys)
        if explain:
            log.append(f"H local {i} + offset {offset} = global {global_idx} -> physical {phys}")

    def emit_S(i: int, offset: int = 0) -> None:
        global_idx = i + offset
        phys = p.apply_new_to_old(global_idx)
        circ.S(phys)
        if explain:
            log.append(f"S local {i} + offset {offset} = global {global_idx} -> physical {phys}")

    def emit_CX(i: int, j: int, offset: int = 0) -> None:
        global_i = i + offset
        global_j = j + offset
        phys_i = p.apply_new_to_old(global_i)
        phys_j = p.apply_new_to_old(global_j)
        circ.CX(phys_i, phys_j)
        if explain:
            log.append(f"CX local ({i},{j}) + offset {offset} = global ({global_i},{global_j}) -> physical ({phys_i},{phys_j})")

    # Phase 4C: Additional fixed gate emitters
    def emit_X(i: int, offset: int = 0) -> None:
        phys = p.apply_new_to_old(i + offset)
        circ.X(phys)

    def emit_Y(i: int, offset: int = 0) -> None:
        phys = p.apply_new_to_old(i + offset)
        circ.Y(phys)

    def emit_Z(i: int, offset: int = 0) -> None:
        phys = p.apply_new_to_old(i + offset)
        circ.Z(phys)

    def emit_T(i: int, offset: int = 0) -> None:
        phys = p.apply_new_to_old(i + offset)
        circ.T(phys)

    def emit_Tdg(i: int, offset: int = 0) -> None:
        phys = p.apply_new_to_old(i + offset)
        circ.Tdg(phys)

    def emit_Sdg(i: int, offset: int = 0) -> None:
        phys = p.apply_new_to_old(i + offset)
        circ.Sdg(phys)

    def emit_CZ(i: int, j: int, offset: int = 0) -> None:
        phys_i = p.apply_new_to_old(i + offset)
        phys_j = p.apply_new_to_old(j + offset)
        circ.CZ(phys_i, phys_j)

    def emit_CCX(i: int, j: int, k: int, offset: int = 0) -> None:
        phys_i = p.apply_new_to_old(i + offset)
        phys_j = p.apply_new_to_old(j + offset)
        phys_k = p.apply_new_to_old(k + offset)
        circ.CCX(phys_i, phys_j, phys_k)

    def emit_CSWAP(c: int, i: int, j: int, offset: int = 0) -> None:
        """Emit CSWAP (Fredkin) gate: swap i,j when c is |1⟩."""
        phys_c = p.apply_new_to_old(c + offset)
        phys_i = p.apply_new_to_old(i + offset)
        phys_j = p.apply_new_to_old(j + offset)
        circ.CSWAP(phys_c, phys_i, phys_j)

    # Phase 4C: Parameterized gate emitters
    def emit_Rz(theta: float, i: int, offset: int = 0) -> None:
        phys = p.apply_new_to_old(i + offset)
        circ.Rz(theta, phys)

    def emit_Rx(theta: float, i: int, offset: int = 0) -> None:
        phys = p.apply_new_to_old(i + offset)
        circ.Rx(theta, phys)

    def emit_Ry(theta: float, i: int, offset: int = 0) -> None:
        phys = p.apply_new_to_old(i + offset)
        circ.Ry(theta, phys)

    def emit_Phase(phi: float, i: int, offset: int = 0) -> None:
        phys = p.apply_new_to_old(i + offset)
        # pytket uses U1 for phase gate: U1(phi) = diag(1, e^{i*phi})
        circ.U1(phi, phys)

    def emit_CRz(theta: float, i: int, j: int, offset: int = 0) -> None:
        phys_i = p.apply_new_to_old(i + offset)
        phys_j = p.apply_new_to_old(j + offset)
        circ.CRz(theta, phys_i, phys_j)

    # Controlled single-qubit gate emitters (for quantum case expressions)
    def emit_CH(i: int, j: int, offset: int = 0) -> None:
        phys_i = p.apply_new_to_old(i + offset)
        phys_j = p.apply_new_to_old(j + offset)
        circ.CH(phys_i, phys_j)

    def emit_CS(i: int, j: int, offset: int = 0) -> None:
        phys_i = p.apply_new_to_old(i + offset)
        phys_j = p.apply_new_to_old(j + offset)
        circ.CS(phys_i, phys_j)

    def emit_CSdg(i: int, j: int, offset: int = 0) -> None:
        phys_i = p.apply_new_to_old(i + offset)
        phys_j = p.apply_new_to_old(j + offset)
        circ.CSdg(phys_i, phys_j)

    def emit_ExpSwap(theta: float, i: int, j: int, offset: int = 0) -> None:
        """Emit exp(iθ · SWAP) on wires i and j.

        exp(iθ · SWAP) = cos(θ)I + i·sin(θ)·SWAP

        Decomposition uses XXPhase, YYPhase, ZZPhase:
        SWAP = (I + XX + YY + ZZ) / 2
        exp(iθ · SWAP) = e^{iθ/2} · exp(iθ·XX/2) · exp(iθ·YY/2) · exp(iθ·ZZ/2)

        In pytket: XXPhase(α) = exp(-iαπ·XX/2)
        So we use α = -θ/π to get exp(iθ·XX/2), etc.
        """
        import math
        phys_i = p.apply_new_to_old(i + offset)
        phys_j = p.apply_new_to_old(j + offset)

        # Parameter for pytket's XXPhase/YYPhase/ZZPhase
        # pytket uses α where XXPhase(α) = exp(-iαπ·XX/2)
        # We want exp(iθ·XX/2), so α = -θ/π
        alpha = -theta / math.pi

        # Global phase e^{iθ/2} - pytket doesn't have global phase directly
        # but we can add it via GPhase if needed, or just accept it as implicit
        # For now, emit the 3 rotation gates
        circ.XXPhase(alpha, phys_i, phys_j)
        circ.YYPhase(alpha, phys_i, phys_j)
        circ.ZZPhase(alpha, phys_i, phys_j)

        if explain:
            log.append(f"ExpSwap theta={theta} local ({i},{j}) + offset {offset} -> physical ({phys_i},{phys_j})")

    def embed_local_perm(local_perm: WirePerm, offset: int) -> WirePerm:
        """Embed a local permutation into the global n-wire space.

        For a local permutation acting on wires [0..local_width-1],
        create a global permutation where:
        - Wires [0..offset-1] are identity
        - Wires [offset..offset+local_width-1] get the local perm (shifted)
        - Wires [offset+local_width..n-1] are identity
        """
        local_width = local_perm.n
        global_perm = list(range(n))  # Start with identity
        for i in range(local_width):
            # Map global wire (offset + i) to global wire (offset + local_perm[i])
            global_perm[offset + i] = offset + local_perm.new_to_old[i]
        return WirePerm(n, global_perm)

    def _var_route_perm(curr_positions: list, offset: int) -> WirePerm:
        """Permutation that moves wires from curr_positions to [offset..offset+w).

        curr_positions[i] is the current logical position of the variable's i-th wire.
        After applying this perm, logical position offset+i holds wire curr_positions[i].
        Remaining positions are filled in order (preserving relative order of other wires).

        Used by Var to route a variable's wires to the expected offset.
        """
        w = len(curr_positions)
        perm_list = [None] * n
        used_src = set(curr_positions)
        used_dst = set(range(offset, offset + w))

        # Place variable wires
        for i in range(w):
            perm_list[offset + i] = curr_positions[i]

        # Fill remaining: free dst positions get free src positions in order
        free_src = [j for j in range(n) if j not in used_src]
        free_dst = [j for j in range(n) if j not in used_dst]
        for d, s in zip(free_dst, free_src):
            perm_list[d] = s

        return WirePerm(n, perm_list)

    def apply_tagged_perm(tagged: TaggedPerm, offset: int) -> None:
        """Apply a TaggedPerm: update global perm and emit X gates for tag flips.

        Also handles general tag_perm (summand index permutation) for nested
        sums where a simple X flip is insufficient.
        """
        nonlocal p
        # Embed the wire permutation
        step = embed_local_perm(tagged.perm, offset)
        p = compose(step, p)

        # For each tag flip position, emit an X gate
        # The flip positions are in local coordinates, need to add offset
        for local_pos in tagged.tag_flips:
            global_pos = local_pos + offset
            # Map through current permutation to get physical wire
            phys = p.apply_new_to_old(global_pos)
            circ.X(phys)
            if explain:
                log.append(f"Tag flip at local {local_pos} + offset {offset} = global {global_pos} -> physical {phys}")

        # Handle general tag_perm for nested sums (n > 2 summands).
        # tag_flips handles the binary case (n=2); for n>2, tag_perm encodes
        # a general permutation on summand indices that must be synthesized
        # as a unitary on the log-encoded tag register.
        if tagged.tag_perm is not None and not tagged.tag_flips:
            import math
            tp = tagged.tag_perm
            n_summands = len(tp)
            k = math.ceil(math.log2(n_summands)) if n_summands > 1 else 0
            # Only emit if non-identity
            if k > 0 and tp != tuple(range(n_summands)):
                _emit_tag_perm_unitary(circ, p, tp, k, offset, explain, log)

    def _branch_scope():
        """A child of THIS compilation's scope for one branch preparation.

        Without it, `compile()` would mint a second ProvenanceScope root and
        the branch's identities would live in an unrelated universe.
        """
        return _prov.fork()

    def _typed_bindings(names, scope, env_):
        """Wrap external env entries ONCE, at this occurrence's boundary.

        `compile(..., env={"z": [wire]})` stays supported; it is validated and
        given provenance here rather than being rediscovered independently
        inside every branch. The name is a lookup key, not identity.
        """
        out = []
        for nm, ty_fv in names:
            if not env_ or nm not in env_:
                continue
            wires = tuple(env_[nm])
            key = (nm, wires)
            if key not in _binding_cache:
                _binding_cache[key] = TypedBinding(
                    name=nm, logical=ty_fv, wires=wires,
                    owner_id=scope.owner(), intro_cut=scope.cut())
            out.append(_binding_cache[key])
        return tuple(out)

    def _plan_open_occurrence_for(t, parent_in, parent_out, free_names,
                                  k_in, k_out, env_, branches=()):
        """Thin adapter: collect THIS construct's inputs, defer every
        placement decision to the one shared planner."""
        scope = _prov.fork()
        bindings = _typed_bindings(free_names, scope, env_)
        if not bindings:
            return None
        # The ambient register is the occurrence's own boundary PLUS the
        # coordinates its owned context occupies. Passing the current register
        # instead would reproduce the very collision this stage exists to
        # remove: the context and the tag would be forced to share a wire.
        ctx_w = sum(len(b.wires) for b in bindings)
        ambient = max(parent_in.n_qubits, parent_out.n_qubits) + ctx_w
        return plan_open_occurrence(
            parent_in=parent_in, parent_out=parent_out, branches=branches,
            bindings=bindings, ambient_width=ambient, scope=scope,
            tag_width_in=k_in, tag_width_out=k_out, perm=tuple(p.new_to_old))

    def _plusmap_align_plan(t, arts, k, parent_in, parent_out,
                            placement_fn=None, P_inv=None,
                            payload_base_override=None,
                            summ_in=None, summ_out=None, selector_bits=1):
        """Build the occurrence's plan, or FAIL CLOSED.

        Called for an in-scope CLOSED boundary -- equal registers, both sides
        sector-described, first-order -- on either the k<=1 or the Strategy A
        path. For such a boundary a plan is owed: if one cannot be built the
        parent cannot honour A_pre J^- = K^- / A_post K^+ = J^+, and returning
        None would silently emit the pre-repair circuit under a boundary that
        claims otherwise. So this raises instead.

        `placement_fn(sector, artifact_n)` returns that branch's
        `local_to_block` tuple, which is the single authority consumed by the
        lift, by the lifted ports and by the emitted commands.
        """
        n = parent_in.n_qubits
        tag_wires, payload_base = _plusmap_placement(n, k)
        if payload_base_override is not None:
            payload_base = payload_base_override
        pw_parent = n - k
        if placement_fn is None:
            def placement_fn(_sector, artifact_n, _pb=payload_base):
                return tuple(_pb + i for i in range(artifact_n))

        def _fail(why):
            raise UnsupportedFrame(
                f"PlusMap: cannot construct the occurrence align plan "
                f"({why}). The boundary is closed and sector-described, so a "
                f"plan is required; refusing to emit an unaligned circuit "
                f"under it. Failing closed before emission.")

        pls, pre, mid = [], [], []
        if summ_in is None:
            summ_in = [t.ty_left, t.ty_right]
        if summ_out is None:
            summ_out = [type_of(t.left)[1], type_of(t.right)[1]]
        if len(summ_in) != len(arts) or len(summ_out) != len(arts):
            _fail(f"{len(arts)} branch artifacts but {len(summ_in)} ingress / "
                  f"{len(summ_out)} egress summands")
        for tv, a in enumerate(arts):
            wi, wo = a.fin.n_qubits, a.fout.n_qubits
            l2b = placement_fn(tv, max(wi, wo))
            if l2b is None or any(wr >= n for wr in l2b):
                _fail(f"branch {tv} artifact width {max(wi, wo)} does not fit "
                      f"a {n}-qubit parent")
            Km = _lift_via_placement(a.fin.codes, tv, n, l2b[:wi],
                                     P_inv, pw_parent, selector_bits)
            Kp = _lift_via_placement(a.fout.codes, tv, n, l2b[:wo],
                                     P_inv, pw_parent, selector_bits)
            if Km is None or Kp is None:
                _fail(f"branch {tv} does not lift into the parent register")
            pls.append(BranchPlacement(
                index=tv, tag_value=tv, tag_wires=tag_wires,
                payload_base=payload_base, width=max(wi, wo),
                logical_in=summ_in[tv], logical_out=summ_out[tv],
                K_minus=Km, K_plus=Kp, local_to_block=l2b,
                ports_in=tuple(_lift_port(pt, l2b) for pt in a.fin.ports),
                ports_out=tuple(_lift_port(pt, l2b) for pt in a.fout.ports)))
            pre.extend(Km)
            mid.extend(Kp)

        if len(set(pre)) != len(pre):
            _fail("lifted ingress codes are not injective")
        if len(set(mid)) != len(mid):
            _fail("lifted egress codes are not injective")
        if len(pre) != len(parent_in.codes):
            _fail(f"lifted ingress has {len(pre)} codes but the parent "
                  f"boundary has {len(parent_in.codes)}")
        if len(mid) != len(parent_out.codes):
            _fail(f"lifted egress has {len(mid)} codes but the parent "
                  f"boundary has {len(parent_out.codes)}")
        try:
            # Code-only Align operands. No ports: a parent residual port must
            # not be copied onto a coordinate a branch has made live.
            F_pre = Frame(logical=parent_in.logical, n_qubits=n,
                          codes=tuple(pre), label="PlusMap F_pre")
            F_mid = Frame(logical=parent_out.logical, n_qubits=n,
                          codes=tuple(mid), label="PlusMap F_mid")
        except ValueError as e:
            _fail(str(e))
        return PlusMapAlignPlan(
            n_qubits=n, tag_wires=tag_wires, payload_base=payload_base,
            placements=tuple(pls), F_pre=F_pre, F_mid=F_mid,
            parent_in=parent_in, parent_out=parent_out)

    def _emit_frame_align(src, dst, offset, n, *, where):
        """One coherent whole-register Align. Identity and wire-permutation
        stay free; anything else is one exact permutation box."""
        nonlocal p
        if align_is_identity(src, dst):
            return 0
        wp = align_as_wire_permutation(src, dst)
        if wp is not None:
            step = embed_local_perm(WirePerm(len(wp), list(wp)), offset)
            p = compose(step, p)
            if explain:
                log.append(f"PlusMap {where}: wire permutation {wp}")
            return 0
        phys = [p.apply_new_to_old(offset + i) for i in range(n)]
        emit_align(circ, phys, src, dst)
        if explain:
            log.append(f"PlusMap {where}: {align_permutation(src, dst)} "
                       f"on wires {phys}")
        return 1

    def _emit_controlled_branch(ctrl_q, sub_cmds, wire_map_fn, anti=False,
                                extra_anti_qubits=None):
        """Emit each gate controlled on ctrl_q, with wires mapped by wire_map_fn.

        Args:
            ctrl_q: Physical qubit for primary control
            sub_cmds: Commands from the sub-circuit
            wire_map_fn: Function mapping sub-circuit wire index to physical qubit
            anti: If True, wrap with X gates for anti-control on ctrl_q
            extra_anti_qubits: Additional physical qubits to anti-control (for
                Strategy A asymmetric splits where the sub-circuit doesn't use
                all k-1 inner tag bits — the unused bits must be anti-controlled
                to restrict the wrapped operation to valid leaf positions only).
        """
        from pytket.circuit import QControlBox
        extras = extra_anti_qubits or []
        # X-flip all anti-controls (primary + extras) so the underlying multi-
        # control sees them as positive.
        if anti:
            circ.X(ctrl_q)
        for q in extras:
            circ.X(q)
        all_ctrls = [ctrl_q] + list(extras)
        n_ctrls = len(all_ctrls)
        for cmd in sub_cmds:
            phys_qubits = [wire_map_fn(q.index[0]) for q in cmd.qubits]
            ctrl_op = _CTRL_GATE_MAP.get(cmd.op.type)
            if ctrl_op is not None and n_ctrls == 1:
                circ.add_gate(ctrl_op, cmd.op.params, all_ctrls + phys_qubits)
            elif cmd.op.type in (OpType.CnX, OpType.CCX):
                # CnX/CCX: n-ary controlled X; prepend ALL extra controls.
                circ.add_gate(OpType.CnX, [], all_ctrls + phys_qubits)
            else:
                qcb = QControlBox(cmd.op, n_ctrls)
                circ.add_qcontrolbox(qcb, all_ctrls + phys_qubits)
        # X-unflip
        for q in extras:
            circ.X(q)
        if anti:
            circ.X(ctrl_q)

    def _go_body(t: Term, offset: int = 0, env: Env = None, *,
                 is_value: bool = False, parent_in=None, parent_out=None) -> None:
        """Compile term t at given wire offset with variable environment.

        Args:
            t: The term to compile
            offset: Wire offset for this term within the circuit
            env: Environment mapping variable names to (start, width) wire ranges
            is_value: If True, this term is being compiled as a function value
                (e.g. inside a Pair argument). Lam terms defer body compilation
                when is_value=True, and the body is compiled later at Apply time.
        """
        if env is None:
            env = {}
        nonlocal p
        if isinstance(t, Id):
            if explain:
                log.append(f"Id (offset={offset})")
            return
        if isinstance(t, GlobalPhase):
            # Scalar z·I on ty: track via pytket's circuit.phase (in half-turns).
            # pytket's get_unitary() respects add_phase, so the scalar factor
            # appears correctly in the compiled unitary. When this term appears
            # inside a controlled context (as a branch of PlusMap / Case /
            # PhasedPlusMap), the enclosing branch-compile site is responsible
            # for reading the accumulated sub-circuit .phase and promoting it
            # to an exact-tag relative phase on the tag qubits.
            import math as _math
            circ.add_phase(t.theta / _math.pi)
            if explain:
                log.append(f"GlobalPhase(θ={t.theta:.4f}) at offset {offset}")
            return
        if isinstance(t, WireIdentity):
            # Wire-level identity between two types of equal width: emit no gates.
            if explain:
                log.append(f"WireIdentity (no gates, dom→cod type coercion)")
            return
        if isinstance(t, TagPerm):
            # Basis-state permutation: emit ToffoliBox at the term's width.
            from lang.types import width as type_width
            k = type_width(t.ty)
            if k == 0:
                return  # nothing to do for unit type
            tag_phys = [p.apply_new_to_old(offset + i) for i in range(k)]
            n = len(t.perm)
            dim = 2 ** k
            from pytket.circuit import ToffoliBox, ToffoliBoxSynthStrat
            perm_pairs = []
            for i in range(dim):
                j = t.perm[i] if i < n else i
                inp = tuple(bool((i >> (k - 1 - b)) & 1) for b in range(k))
                out = tuple(bool((j >> (k - 1 - b)) & 1) for b in range(k))
                perm_pairs.append((inp, out))
            box = ToffoliBox(perm_pairs, ToffoliBoxSynthStrat.Matching)
            circ.add_toffolibox(box, tag_phys)
            if explain:
                log.append(f"TagPerm: k={k}, perm={t.perm}")
            return
        if isinstance(t, Seq):
            a_f = go(t.f, offset, env)
            # A composite's input boundary is its PRODUCER's, wherever that
            # arrived; the slot naming at Seq's own entry describes the stage
            # before the producer claimed anything.
            _placement_sink[_cur_occ[0]] = a_f.ingress_wires
            try:
                g_in, g_out = select_frames(t.g)
            except UnsupportedFrame:
                raise

            # Align at the splice, against the producer's EFFECTIVE output
            # frame from its returned artifact -- never a frame recomputed
            # from type_of.  A u_C^- = u_P^+ , so A carries CONSUMER codes
            # onto PRODUCER codes.
            prod_out, cons_in = a_f.output_frame, g_in
            # Unequal registers need an explicitly selected common ambient
            # frame with typed residual ports -- Align never widens silently.
            if prod_out.n_qubits != cons_in.n_qubits:
                _amb = max(prod_out.n_qubits, cons_in.n_qubits)
                if prod_out.n_qubits < _amb:
                    prod_out = with_spectators(prod_out, _amb,
                                               residual_name="splice_pad")
                if cons_in.n_qubits < _amb:
                    cons_in = with_spectators(cons_in, _amb,
                                              residual_name="splice_pad")
                    g_out = with_spectators(g_out, _amb,
                                            residual_name="splice_pad")
            if not align_is_identity(cons_in, prod_out):
                wp = align_as_wire_permutation(cons_in, prod_out)
                if wp is not None:
                    # Fast path: a pure wire permutation folds into WirePerm.
                    _frame_override[_cur_occ[0]] = transported_frame(
                        build_align(cons_in, prod_out), g_out)
                    go(t.g, offset, env)
                    return
                wires = [p.apply_new_to_old(offset + i)
                         for i in range(prod_out.n_qubits)]
                A = build_align(cons_in, prod_out)
                # G_C' = A G_C A^dagger, emitted chronologically as
                # A^dagger ; G_C ; A.
                emit_align(circ, wires, prod_out, cons_in)     # A^dagger
                go(t.g, offset, env)                            # G_C
                emit_align(circ, wires, cons_in, prod_out)      # A
                # The effective output is A u_C^+ ; propagate it onward.
                _frame_override[_cur_occ[0]] = transported_frame(A, g_out)
                return
            go(t.g, offset, env)
            return

        # TenTerm: parallel composition with offset semantics (Phase 2)
        if isinstance(t, TenTerm):
            # Get the type of the left branch to compute right branch offset
            # Offset the right operand by the left operand's SELECTED
            # physical width -- including any residual wires it holds --
            # never by its judgment width, which would let one operand's
            # residual coordinates collide with the other's.
            _lf_in, _lf_out = select_frames(t.f)
            left_width = max(_lf_in.n_qubits, _lf_out.n_qubits)
            go(t.f, offset, env)
            go(t.g, offset + left_width, env)
            if explain:
                log.append(f"TenTerm left_width={left_width}")
            return

        if isinstance(t, TwistTen):
            local_step = twist_tensor_perm(t.a, t.b)
            step = embed_local_perm(local_step, offset)
            p = compose(step, p)
            if explain:
                log.append(f"TwistTen local={local_step.new_to_old} offset={offset} global={step.new_to_old}")
            return
        if isinstance(t, AssocTenL):
            local_step = assoc_tensor_L_perm(t.a, t.b, t.c)
            step = embed_local_perm(local_step, offset)
            p = compose(step, p)
            if explain:
                log.append(f"AssocTenL perm={step.new_to_old}")
            return
        if isinstance(t, AssocTenR):
            local_step = assoc_tensor_R_perm(t.a, t.b, t.c)
            step = embed_local_perm(local_step, offset)
            p = compose(step, p)
            if explain:
                log.append(f"AssocTenR perm={step.new_to_old}")
            return

        if isinstance(t, TwistPlus):
            tagged = twist_plus_perm(t.a, t.b)
            apply_tagged_perm(tagged, offset)
            if explain:
                log.append(f"TwistPlus perm={tagged.perm.new_to_old} flips={tagged.tag_flips}")
            return
        if isinstance(t, AssocPlusL):
            tagged = assoc_plus_L_perm(t.a, t.b, t.c)
            apply_tagged_perm(tagged, offset)
            if explain:
                log.append(f"AssocPlusL perm={tagged.perm.new_to_old} flips={tagged.tag_flips}")
            return
        if isinstance(t, AssocPlusR):
            tagged = assoc_plus_R_perm(t.a, t.b, t.c)
            apply_tagged_perm(tagged, offset)
            if explain:
                log.append(f"AssocPlusR perm={tagged.perm.new_to_old} flips={tagged.tag_flips}")
            return

        # Distributivity: now supported with tagged layout
        if isinstance(t, DistL):
            # Gate-free either way. At equal widths the canonical frames were
            # selected and the two layouts differ by a wire permutation, which
            # is contributed here and costs no gates. At unequal widths the
            # shared layout was selected: both readings are the same physical
            # layout, so nothing moves and any conversion a consumer needs
            # happens at the splice, via Align.
            if _distributor_canonical_frames(t) is not None:
                tagged = dist_L_perm(t.a, t.b, t.c)
                apply_tagged_perm(tagged, offset)
                if explain:
                    log.append(
                        f"DistL perm={tagged.perm.new_to_old} (identity)")
            elif explain:
                log.append("DistL: gate-free in the shared layout")
            return

        if isinstance(t, DistR):
            # Gate-free either way. At equal widths the canonical frames were
            # selected and the two layouts differ by a wire permutation, which
            # is contributed here and costs no gates. At unequal widths the
            # shared layout was selected: both readings are the same physical
            # layout, so nothing moves and any conversion a consumer needs
            # happens at the splice, via Align.
            if _distributor_canonical_frames(t) is not None:
                tagged = dist_R_perm(t.a, t.b, t.c)
                apply_tagged_perm(tagged, offset)
                if explain:
                    log.append(
                        f"DistR perm={tagged.perm.new_to_old} (tag moves to front)")
            elif explain:
                log.append("DistR: gate-free in the shared layout")
            return

        # Inverse distributivity: now supported with tagged layout
        if isinstance(t, UndistL):
            # Gate-free either way. At equal widths the canonical frames were
            # selected and the two layouts differ by a wire permutation, which
            # is contributed here and costs no gates. At unequal widths the
            # shared layout was selected: both readings are the same physical
            # layout, so nothing moves and any conversion a consumer needs
            # happens at the splice, via Align.
            if _distributor_canonical_frames(t) is not None:
                tagged = undist_L_perm(t.a, t.b, t.c)
                apply_tagged_perm(tagged, offset)
                if explain:
                    log.append(
                        f"UndistL perm={tagged.perm.new_to_old} (identity)")
            elif explain:
                log.append("UndistL: gate-free in the shared layout")
            return
        if isinstance(t, UndistR):
            # Gate-free either way. At equal widths the canonical frames were
            # selected and the two layouts differ by a wire permutation, which
            # is contributed here and costs no gates. At unequal widths the
            # shared layout was selected: both readings are the same physical
            # layout, so nothing moves and any conversion a consumer needs
            # happens at the splice, via Align.
            if _distributor_canonical_frames(t) is not None:
                tagged = undist_R_perm(t.a, t.b, t.c)
                apply_tagged_perm(tagged, offset)
                if explain:
                    log.append(
                        f"UndistR perm={tagged.perm.new_to_old} (identity)")
            elif explain:
                log.append("UndistR: gate-free in the shared layout")
            return

        # Frame-awareness for primitive gates: checked BEFORE any emission.
        _check_primitive_frame(t, parent_in)

        if isinstance(t, H):
            emit_H(t.i, offset); return
        if isinstance(t, S):
            emit_S(t.i, offset); return
        if isinstance(t, CX):
            emit_CX(t.i, t.j, offset); return

        # Phase 4C: Additional fixed gates
        if isinstance(t, X):
            emit_X(t.i, offset); return
        if isinstance(t, Y):
            emit_Y(t.i, offset); return
        if isinstance(t, Z):
            emit_Z(t.i, offset); return
        if isinstance(t, T):
            emit_T(t.i, offset); return
        if isinstance(t, Tdg):
            emit_Tdg(t.i, offset); return
        if isinstance(t, Sdg):
            emit_Sdg(t.i, offset); return
        if isinstance(t, CZ):
            emit_CZ(t.i, t.j, offset); return
        if isinstance(t, CCX):
            emit_CCX(t.i, t.j, t.k, offset); return

        if isinstance(t, CSWAP):
            emit_CSWAP(t.c, t.i, t.j, offset); return

        # Ctrl: inductive controlled combinator
        # Compiles Ctrl(f) : Bool ⊗ A → Bool ⊗ A
        # Uses built-in controlled gates when available, recurses otherwise
        if isinstance(t, Ctrl):
            # Control qubit is at offset, payload starts at offset+1
            ctrl_wire = offset
            payload_offset = offset + 1

            def compile_multi_ctrl(body: Term, ctrls: list, pay_off: int) -> None:
                """Recursively compile controlled body with multiple control wires.

                Args:
                    body: The term to control
                    ctrls: List of control wire positions (in order)
                    pay_off: Offset where payload wires start
                """
                n_ctrls = len(ctrls)

                # Single-controlled gates (built-in)
                if n_ctrls == 1:
                    ctrl = ctrls[0]
                    if isinstance(body, H):
                        emit_CH(ctrl, body.i + pay_off)
                        return
                    if isinstance(body, S):
                        emit_CS(ctrl, body.i + pay_off)
                        return
                    if isinstance(body, Sdg):
                        emit_CSdg(ctrl, body.i + pay_off)
                        return
                    if isinstance(body, X):
                        emit_CX(ctrl, body.i + pay_off)
                        return
                    if isinstance(body, Z):
                        emit_CZ(ctrl, body.i + pay_off)
                        return
                    if isinstance(body, Rz):
                        emit_CRz(body.theta, ctrl, body.i + pay_off)
                        return
                    if isinstance(body, CX):
                        emit_CCX(ctrl, body.i + pay_off, body.j + pay_off)
                        return
                    # Ctrl(TwistTen) on Q ⊗ Q = CSWAP
                    if isinstance(body, TwistTen):
                        from lang.types import Q as QTy
                        if isinstance(body.a, QTy) and isinstance(body.b, QTy):
                            emit_CSWAP(ctrl, pay_off, pay_off + 1)
                            return
                        else:
                            w_a = width(body.a)
                            w_b = width(body.b)
                            for i in range(min(w_a, w_b)):
                                emit_CSWAP(ctrl, pay_off + i, pay_off + w_a + i)
                            return

                # Doubly-controlled gates (built-in)
                if n_ctrls == 2:
                    c0, c1 = ctrls[0], ctrls[1]
                    if isinstance(body, X):
                        # CCX = Toffoli
                        emit_CCX(c0, c1, body.i + pay_off)
                        return

                # Structural: identity (any number of controls)
                if isinstance(body, Id):
                    return

                # Inductive: Ctrl(Seq(f, g)) = Ctrl(f); Ctrl(g)
                if isinstance(body, Seq):
                    compile_multi_ctrl(body.f, ctrls, pay_off)
                    compile_multi_ctrl(body.g, ctrls, pay_off)
                    return

                # Inductive: Ctrl(TenTerm(f, g)) = Ctrl(f) ⊗ Ctrl(g) with shared controls
                if isinstance(body, TenTerm):
                    left_dom, _ = type_of(body.f)
                    left_width = width(left_dom)
                    compile_multi_ctrl(body.f, ctrls, pay_off)
                    compile_multi_ctrl(body.g, ctrls, pay_off + left_width)
                    return

                # Inductive: Ctrl(Ctrl(f)) adds another control
                # Layout: [c_outer | c_inner | A]
                # When body is Ctrl(inner), we add its control to our list
                if isinstance(body, Ctrl):
                    inner_ctrl = pay_off  # Inner control is first wire of payload
                    inner_pay_off = pay_off + 1  # Inner payload starts after inner control
                    compile_multi_ctrl(body.body, ctrls + [inner_ctrl], inner_pay_off)
                    return

                # Fallback: primitive gates with n >= 2 controls via QControlBox
                def _prim_to_qcontrolbox(body, n_ctrls, ctrls, pay_off):
                    """Try to emit a primitive gate with n controls using QControlBox.
                    Returns True if handled, False otherwise."""
                    from pytket.circuit import QControlBox, Op
                    # Map term types to (OpType, params, target_wires)
                    if isinstance(body, H):
                        base_op = Op.create(OpType.H)
                        targets = [body.i]
                    elif isinstance(body, S):
                        base_op = Op.create(OpType.S)
                        targets = [body.i]
                    elif isinstance(body, Sdg):
                        base_op = Op.create(OpType.Sdg)
                        targets = [body.i]
                    elif isinstance(body, X):
                        base_op = Op.create(OpType.X)
                        targets = [body.i]
                    elif isinstance(body, Y):
                        base_op = Op.create(OpType.Y)
                        targets = [body.i]
                    elif isinstance(body, Z):
                        base_op = Op.create(OpType.Z)
                        targets = [body.i]
                    elif isinstance(body, T):
                        base_op = Op.create(OpType.T)
                        targets = [body.i]
                    elif isinstance(body, Tdg):
                        base_op = Op.create(OpType.Tdg)
                        targets = [body.i]
                    elif isinstance(body, Rz):
                        base_op = Op.create(OpType.Rz, [body.theta])
                        targets = [body.i]
                    elif isinstance(body, Rx):
                        base_op = Op.create(OpType.Rx, [body.theta])
                        targets = [body.i]
                    elif isinstance(body, Ry):
                        base_op = Op.create(OpType.Ry, [body.theta])
                        targets = [body.i]
                    elif isinstance(body, CX):
                        base_op = Op.create(OpType.CX)
                        targets = [body.i, body.j]
                    else:
                        return False
                    qcb = QControlBox(base_op, n_ctrls)
                    phys_targets = [p.apply_new_to_old(t + pay_off) for t in targets]
                    ctrl_phys = [p.apply_new_to_old(c) for c in ctrls]
                    circ.add_qcontrolbox(qcb, ctrl_phys + phys_targets)
                    return True

                if _prim_to_qcontrolbox(body, n_ctrls, ctrls, pay_off):
                    return

                # General fallback: compile any body to a sub-circuit
                # and control each gate (no decomposition needed).
                from pytket.circuit import QControlBox
                sub_cmds, _ctrl_phase_ht = _compile_branch(
                    body, scope=_branch_scope())
                # The body's scalar becomes a phase conditional on all
                # controls firing (tag value all-ones).
                _discharge_branch_phase(
                    circ, [p.apply_new_to_old(c) for c in ctrls],
                    [(1 << n_ctrls) - 1], _ctrl_phase_ht)
                for cmd in sub_cmds:
                    phys_qubits = [p.apply_new_to_old(q.index[0] + pay_off)
                                   for q in cmd.qubits]
                    ctrl_phys = [p.apply_new_to_old(c) for c in ctrls]
                    ctrl_op = _CTRL_GATE_MAP.get(cmd.op.type) if n_ctrls == 1 else None
                    if ctrl_op is not None:
                        circ.add_gate(ctrl_op, cmd.op.params,
                                      ctrl_phys + phys_qubits)
                    elif cmd.op.type in (OpType.CnX, OpType.CCX):
                        # CnX/CCX: n-ary controlled X; prepend more controls
                        circ.add_gate(OpType.CnX, [],
                                      ctrl_phys + phys_qubits)
                    else:
                        qcb = QControlBox(cmd.op, n_ctrls)
                        circ.add_qcontrolbox(qcb, ctrl_phys + phys_qubits)
                return

            compile_multi_ctrl(t.body, [ctrl_wire], payload_offset)
            if explain:
                log.append(f"Ctrl: compiled with control at {ctrl_wire}, payload at {payload_offset}")
            return

        # Phase 4C: Parameterized gates
        if isinstance(t, Rz):
            emit_Rz(t.theta, t.i, offset); return
        if isinstance(t, Rx):
            emit_Rx(t.theta, t.i, offset); return
        if isinstance(t, Ry):
            emit_Ry(t.theta, t.i, offset); return
        if isinstance(t, Phase):
            emit_Phase(t.phi, t.i, offset); return
        if isinstance(t, CRz):
            emit_CRz(t.theta, t.i, t.j, offset); return

        # Controlled single-qubit gates
        if isinstance(t, CH):
            emit_CH(t.i, t.j, offset); return
        if isinstance(t, CS):
            emit_CS(t.i, t.j, offset); return
        if isinstance(t, CSdg):
            emit_CSdg(t.i, t.j, offset); return

        # Exponentials of structural involutions
        if isinstance(t, ExpSwap):
            emit_ExpSwap(t.theta, t.i, t.j, offset); return

        if isinstance(t, ExpInvolution):
            # Direct unitary synthesis: compile body to get U, verify U²≈I,
            # then emit cos(θ)·I + i·sin(θ)·U as a unitary box.
            # This correctly handles tag flips, tag perms, and multi-transpositions.
            import numpy as np
            import math as _math

            body_result = compile(t.body, materialize=True)
            U = body_result.circuit.get_unitary()
            body_n = U.shape[0]
            body_w = int(_math.log2(body_n))

            # Verify involution: U² ≈ I
            UU = U @ U
            if not np.allclose(UU, np.eye(body_n), atol=1e-9):
                raise TypeCheckError(
                    f"ExpInvolution body must be an involution (U²=I), "
                    f"but U² deviates from I by {np.max(np.abs(UU - np.eye(body_n))):.2e}"
                )

            # If U ≈ I then exp(iθ·I) = e^{iθ}·I, a SCALAR z·I. Invariant P:
            # scalars are unobservable standing alone but fully observable
            # inside a branch, so this must be recorded, not discarded. The
            # enclosing controlled-emission site promotes it to an exact-tag
            # conditional phase.
            if np.allclose(U, np.eye(body_n), atol=1e-9):
                circ.add_phase(t.theta / _math.pi)
                if explain:
                    log.append(f"ExpInvolution theta={t.theta} body=I "
                               f"-> scalar recorded as global phase")
                return

            # M = cos(θ)·I + i·sin(θ)·U
            M = _math.cos(t.theta) * np.eye(body_n) + 1j * _math.sin(t.theta) * U

            # Emit as UnitaryNqBox
            phys_wires = [p.apply_new_to_old(i + offset) for i in range(body_w)]

            if body_w == 1:
                from pytket.circuit import Unitary1qBox
                box = Unitary1qBox(M)
                circ.add_unitary1qbox(box, phys_wires[0])
            elif body_w == 2:
                from pytket.circuit import Unitary2qBox
                box = Unitary2qBox(M)
                circ.add_unitary2qbox(box, phys_wires[0], phys_wires[1])
            elif body_w == 3:
                from pytket.circuit import Unitary3qBox
                box = Unitary3qBox(M)
                circ.add_unitary3qbox(box, phys_wires[0], phys_wires[1], phys_wires[2])
            else:
                raise NotImplementedError(
                    f"ExpInvolution on {body_w} qubits (> 3) not yet supported")

            if explain:
                log.append(f"ExpInvolution theta={t.theta} body_w={body_w} via direct unitary synthesis")
            return

        # Qubit encoding isomorphism: Q ↔ I + I
        if isinstance(t, EncodeQubit):
            # encode : Q → I + I
            # Circuit: CX[0,1]; X[0]
            # Wire 0 is input Q, wire 1 is ancilla (assumed |0⟩)
            # Output: wire 0 = t₀, wire 1 = t₁ of I+I
            emit_CX(0, 1, offset)
            emit_X(0, offset)
            if explain:
                log.append(f"EncodeQubit: CX(0,1); X(0) at offset {offset}")
            return

        if isinstance(t, DecodeQubit):
            # decode : I + I → Q
            # Circuit: X[0]; CX[0,1]
            # Input: wires 0,1 are I+I (t₀, t₁)
            # Output: wire 0 is Q, wire 1 is ancilla (returned to |0⟩)
            emit_X(0, offset)
            emit_CX(0, 1, offset)
            if explain:
                log.append(f"DecodeQubit: X(0); CX(0,1) at offset {offset}")
            return

        # Case/copairing: redirect to PlusMap (identical semantics and fields)
        if isinstance(t, Case):
            go(PlusMap(t.ty_left, t.ty_right, t.left, t.right), offset, env)
            return

        # CaseExpr: pure syntactic sugar — desugar to Seq(scrut, Case(...))
        if isinstance(t, CaseExpr):
            desugared = Seq(t.scrut, Case(t.ty_x, t.ty_y, t.left, t.right))
            go(desugared, offset, env)
            if explain:
                log.append(f"CaseExpr: desugared to Seq(scrut, Case({t.ty_x}, {t.ty_y}, ...))")
            return

        # PlusMap (⊕-Map): f ⊕ g : (A + B) → (C + D)
        # Bifunctorial action on sums. Same anti-control pattern as Case.
        #
        # For nested sums, auto-flatten to NPlusMap (preferred n-ary path).
        # Falls back to Strategy A (tag perm sandwich) for opaque branches
        # that can't be decomposed (e.g., from the elaborate pipeline).
        #
        # Wire layout: [tag₀ | tag₁ | ... | tag_{k-1} | payload]
        if isinstance(t, PlusMap):
            from lang.types import Plus, flatten_plus, tag_width as tw_fn, payload_width
            import math

            # Compute structure of the sum type
            n_left = len(flatten_plus(t.ty_left)) if isinstance(t.ty_left, Plus) else 1
            n_right = len(flatten_plus(t.ty_right)) if isinstance(t.ty_right, Plus) else 1
            n_sum = n_left + n_right
            k = math.ceil(math.log2(n_sum)) if n_sum > 1 else 0

            # Compute branch widths
            left_dom, _ = type_of(t.left)
            left_w = width(left_dom)
            right_dom, _ = type_of(t.right)
            right_w = width(right_dom)

            # Check for open branches (free variables widen domain beyond declared type).
            # For value-style branches (apply_f_branch pattern), the type_of'd dom
            # already includes the free var context, so left_w - payload_w gives ctx.
            # For morphism-style branches (Seq, etc.), the dom is the morphism's
            # declared input only — free vars don't appear there. Use the explicit
            # free-var width sum (filtered by env membership, to avoid counting
            # CaseExpr/PlusMap payload-bound vars that aren't in env) so both cases work.
            payload_left_w = width(t.ty_left)
            payload_right_w = width(t.ty_right)
            fv_left_w = sum(width(ty_fv) for n, ty_fv in _ordered_free_vars(t.left) if n in env)
            fv_right_w = sum(width(ty_fv) for n, ty_fv in _ordered_free_vars(t.right) if n in env)
            ctx_left_w = max(left_w - payload_left_w, fv_left_w)
            ctx_right_w = max(right_w - payload_right_w, fv_right_w)


            # FAIL CLOSED FIRST. When the parent's ingress and egress
            # embeddings differ, the branch result has to be carried between
            # them. On the open path the register also carries context wires
            # the parent frame does not describe, so that carry cannot be
            # placed. Decide it HERE -- before any branch is compiled, any
            # controlled command or phase is emitted, and before delegating to
            # the flattened NPlusMap. Raising later would leave a partial
            # circuit behind.
            if ctx_left_w > 0 or ctx_right_w > 0:
                _pf_in, _pf_out = select_frames(t)
                # Only judge a boundary that is genuinely a SUM boundary.
                # Sectors are recorded exactly when the summands tile the
                # frame; when they do not -- an Arrow summand encodes as a
                # wire bundle, so its "dimension" is the whole register -- the
                # two sides are not comparable as ingress/egress and the
                # pre-existing path is left alone. The specific wire-conflict
                # guard downstream still applies there.
                # TEMPORARY CONTAINMENT -- not a statement about the source.
                # This does NOT claim the source language has higher-order
                # sums. It says only that WITHOUT context provenance this
                # emitter cannot tell a genuine sum-boundary width mismatch
                # from the artifact of an Arrow-carrying context, and the
                # downstream wire-conflict guard gives the more specific
                # diagnostic for the cases that matter today. Remove this
                # scoping once context provenance exists (the F2 seam); it is
                # a containment, not an invariant.
                _d_par, _c_par = type_of(t)
                _is_sum_boundary = (bool(_pf_in.sectors) and bool(_pf_out.sectors)
                                    and _first_order(_d_par)
                                    and _first_order(_c_par))
                if _is_sum_boundary and (_pf_in.n_qubits != _pf_out.n_qubits
                                         or _pf_in.dim != _pf_out.dim):
                    raise UnsupportedFrame(
                        f"PlusMap (open branches): the parent ingress and "
                        f"egress are not even comparable "
                        f"({_pf_in.n_qubits} qubits / dim {_pf_in.dim} versus "
                        f"{_pf_out.n_qubits} qubits / dim {_pf_out.dim}), so "
                        f"no carry between them exists and the branches are "
                        f"open. Failing closed before emission.")
                if _is_sum_boundary and not align_is_identity(_pf_in, _pf_out):
                    raise UnsupportedFrame(
                        f"PlusMap (open branches): the parent ingress "
                        f"{tuple(_pf_in.codes)} and egress "
                        f"{tuple(_pf_out.codes)} embeddings differ, so the "
                        f"branch result must be carried between them, but the "
                        f"branches are open and the carry cannot be placed "
                        f"against context wires the parent frame does not "
                        f"describe. Failing closed before emission.")

            # Auto-flatten nested PlusMap to NPlusMap when possible
            if isinstance(t.ty_left, Plus) or isinstance(t.ty_right, Plus):
                flat = _try_flatten_plusmap(t)
                if flat is not None:
                    # Delegate to NPlusMap compilation
                    go(flat, offset, env)
                    return
                # Fall through to Strategy A for opaque branches

            if ctx_left_w > 0 or ctx_right_w > 0:
                # Prepared-artifact planning happens below, after every
                # alternative has been prepared exactly once. The frames and
                # free-variable list are gathered here.
                _fv_all = [(nm, ty_) for nm, ty_ in
                           (_ordered_free_vars(t.left)
                            + _ordered_free_vars(t.right))]
                _seen_nm = set()
                _fv_uniq = [x for x in _fv_all
                            if not (x[0] in _seen_nm or _seen_nm.add(x[0]))]
                _pi, _po = select_frames(t)
                # Open branches: compile with parent env for free variable routing
                tag_phys = p.apply_new_to_old(offset)
                payload_base = offset + max(k, 1)

                # PREPARE every alternative exactly once, BEFORE planning
                # or emitting. All of them are prepared even if legacy
                # emission later fails on an earlier branch, because the
                # planner needs the complete occurrence.
                _prepared = []
                for branch, pw, ctx_w, anti in [
                    (t.left, payload_left_w, ctx_left_w, True),
                    (t.right, payload_right_w, ctx_right_w, False),
                ]:
                    if pw + ctx_w == 0:
                        _prepared.append(None)
                        continue
                    if ctx_w > 0:
                        fv = _ordered_free_vars(branch)
                        sub_env = {}
                        ctx_pos = pw
                        for name, ty_fv in fv:
                            w_fv = width(ty_fv)
                            sub_env[name] = list(range(ctx_pos, ctx_pos + w_fv))
                            ctx_pos += w_fv
                        branch_to_compile = branch
                        if deferred_fns:
                            for name, ty_fv in fv:
                                if name in env:
                                    key = tuple(env[name])
                                    if key in deferred_fns:
                                        branch_to_compile = _substitute(
                                            branch_to_compile, name,
                                            deferred_fns[key])
                            branch_to_compile = _normalize(branch_to_compile)
                        _art = _compile_branch_artifact(
                            branch_to_compile, env=sub_env,
                            scope=_branch_scope())
                        ctx_parent_phys = []
                        for name, ty_fv in fv:
                            if name in env:
                                ctx_parent_phys.extend(env[name])
                    else:
                        _art = _compile_branch_artifact(
                            branch, scope=_branch_scope())
                        ctx_parent_phys = []
                    _prepared.append((_art, pw, ctx_w, anti,
                                      list(ctx_parent_phys)))

                # PLAN from those exact artifact objects.
                try:
                    _bins = tuple(
                        BranchInputs(index=_i, artifact=_pr[0])
                        for _i, _pr in enumerate(_prepared) if _pr is not None)
                    _sp2 = _plan_open_occurrence_for(
                        t, _pi, _po, _fv_uniq, max(k, 1), max(k, 1), env,
                        branches=_bins)
                    if _sp2 is not None:
                        _shadow_plans[_cur_occ[0]] = _sp2
                        _PLANNER_OBSERVED.append(_sp2)
                except NeedsBranchPreparation as _nb2:
                    _PLANNER_INCOMPLETE.append(_nb2)
                except ProvenanceError:
                    pass

                # EMIT from the SAME artifacts. No branch is compiled again.
                for _pr in _prepared:
                    if _pr is None:
                        continue
                    _art, pw, ctx_w, anti, ctx_parent_phys = _pr
                    cmds, _open_phase_ht = _art.cmds, _art.phase
                    if ctx_w > 0:
                        def make_open_wire_map(_pw=pw, _pb=payload_base,
                                               _cpp=list(ctx_parent_phys)):
                            def wm(w):
                                if w < _pw:
                                    return p.apply_new_to_old(w + _pb)
                                else:
                                    return _cpp[w - _pw]
                            return wm

                        if cmds:
                            _wm_open = make_open_wire_map()
                            _check_open_placement(
                                branch_name=("PlusMap left" if anti
                                             else "PlusMap right"),
                                payload_phys=[p.apply_new_to_old(_w + payload_base)
                                              for _w in range(pw)],
                                context_phys=list(ctx_parent_phys),
                                tag_phys=[tag_phys],
                                cmds=cmds, wire_map=_wm_open)
                            _emit_controlled_branch(tag_phys, cmds,
                                                    _wm_open, anti=anti)
                    else:
                        if pw == 0:
                            cmds = []
                        if cmds:
                            def make_closed_wire_map(_pb=payload_base):
                                def wm(w):
                                    return p.apply_new_to_old(w + _pb)
                                return wm
                            _emit_controlled_branch(tag_phys, cmds,
                                                    make_closed_wire_map(),
                                                    anti=anti)

                    _discharge_branch_phase(circ, [tag_phys],
                                            [0 if anti else 1], _open_phase_ht)

                if explain:
                    log.append(f"PlusMap(k={k}, open branches): "
                               f"ctx_left={ctx_left_w}, ctx_right={ctx_right_w} "
                               f"at offset {offset}")
                return

            # Closed branches: compile as standalone sub-circuits.
            # If deferred function values exist (from outer Apply β-reduction),
            # reconstruct the branch input value and inject it so _normalize
            # can β-reduce Apply(Var("f"), ...) terms inside the branch.
            def _compile_branch_with_deferred(branch, branch_w, payload_base_off):
                """Returns (cmds, phase_ht). phase_ht is the branch's accumulated
                global phase in half-turns (from any GlobalPhase inside the
                branch), which the caller must promote to an exact-tag relative
                phase on the tag qubits — otherwise the scalar becomes an
                observable relative branch operation that is silently dropped."""
                if branch_w == 0:
                    # Still compile so we can extract any accumulated global
                    # phase from a GlobalPhase term inside the branch.
                    _a = _compile_branch_artifact(branch, scope=_branch_scope())
                    return BranchArtifact([], _a.phase, _a.fin, _a.fout,
                                          _a.circuit)
                if deferred_fns:
                    parent_phys = [p.apply_new_to_old(payload_base_off + i)
                                   for i in range(branch_w)]
                    br_dom, _ = type_of(branch)
                    input_val = _reconstruct_value(parent_phys, br_dom, deferred_fns)
                    if input_val is not None and not isinstance(input_val, Id):
                        modified = _inject_input_value(branch, input_val)
                        modified = _normalize(modified)
                        return _compile_branch_artifact(
                            modified, scope=_branch_scope())
                return _compile_branch_artifact(branch, scope=_branch_scope())

            payload_base_for_branches = offset + max(k, 1)
            _left_art = _compile_branch_with_deferred(t.left, left_w, payload_base_for_branches)
            _right_art = _compile_branch_with_deferred(t.right, right_w, payload_base_for_branches)
            left_cmds, left_phase = _left_art.cmds, _left_art.phase
            right_cmds, right_phase = _right_art.cmds, _right_art.phase

            if k <= 1:
                # Simple binary case: 1 outer tag bit.
                # The boundary is the one THIS occurrence selected in `go`;
                # emission never reselects it.
                _pf_in, _pf_out = parent_in, parent_out
                _plan = None
                # IN SCOPE is decided HERE, by an explicit predicate -- never
                # by a plan failing to build. Once in scope a plan is owed and
                # `_plusmap_align_plan` raises rather than returning None, so
                # there is no path on which a missing plan quietly degrades to
                # the pre-repair circuit.
                #
                # `bool(sectors)` alone is not enough: an Arrow-carrying
                # summand has full-space semantic dimension, so it TILES the
                # frame and gets sectors, while its frame is a wire bundle
                # rather than a sum embedding (the abstract-QSwitch boundary
                # is 64 codes wide for 4 codes of branch). First-order-ness
                # excludes those. TEMPORARY CONTAINMENT, same as the
                # open-branch guard: it is what we can decide without context
                # provenance, not a claim about the source language.
                _dp, _cp = type_of(t)
                if (_pf_in is not None and _pf_out is not None
                        and _pf_in.n_qubits == _pf_out.n_qubits
                        and bool(_pf_in.sectors) and bool(_pf_out.sectors)
                        and _first_order(_dp) and _first_order(_cp)):
                    _plan = _plusmap_align_plan(
                        t, (_left_art, _right_art), max(k, 1), _pf_in, _pf_out)
                    _plan_sink[_cur_occ[0]] = _plan

                # ONE placement object feeds both the lifting (inside the
                # plan) and the wire map below.
                _pb_local = (_plan.payload_base if _plan is not None
                             else _plusmap_placement(
                                 _pf_in.n_qubits if _pf_in is not None
                                 else offset + 1, k)[1])
                payload_base = offset + _pb_local

                # (1) A_pre : parent ingress -> where the block expects input
                if _plan is not None:
                    _emit_frame_align(_pf_in, _plan.F_pre, offset,
                                      _plan.n_qubits, where="A_pre")

                tag_phys = p.apply_new_to_old(offset)
                wire_map = lambda w: p.apply_new_to_old(w + payload_base)
                if left_cmds:
                    _emit_controlled_branch(tag_phys, left_cmds, wire_map, anti=True)
                if right_cmds:
                    _emit_controlled_branch(tag_phys, right_cmds, wire_map)

                # Promote each branch's accumulated global phase to an exact-tag
                # relative phase on the tag qubit. Left branch fires at tag=0,
                # right at tag=1. Without this, a GlobalPhase inside a branch
                # (e.g., `phase (-1) A` as the left branch of `omap0 A B _ _`)
                # would be silently dropped from the compiled circuit despite
                # being an OBSERVABLE relative branch operation.
                if abs(left_phase) > 1e-10:
                    _emit_exact_tag_phase(circ, [tag_phys], 0, left_phase)
                if abs(right_phase) > 1e-10:
                    _emit_exact_tag_phase(circ, [tag_phys], 1, right_phase)

                # (3) A_post : where the block left its result -> parent egress
                if _plan is not None:
                    _emit_frame_align(_plan.F_mid, _pf_out, offset,
                                      _plan.n_qubits, where="A_post")

                if explain:
                    log.append(f"PlusMap(k=1): {len(left_cmds)} left gates (anti-ctrl), "
                               f"{len(right_cmds)} right gates (ctrl); "
                               f"left_phase_ht={left_phase:.4f}, "
                               f"right_phase_ht={right_phase:.4f} at offset {offset}")
                return

            # k >= 2: Strategy A — tag permutation sandwich
            # (fallback for opaque branches that can't be auto-flattened)
            half = 2 ** (k - 1)

            if n_left > half or n_right > half:
                # Strategy B: one full-register unitary, built DIRECTLY in the
                # occurrence-selected parent code frames.
                #
                # The previous construction sized each branch's tag blocks from
                # its INGRESS leaf count and reused that for the egress
                # (_splat, additive tag offsets, n_left/n_right). That is the
                # defect: a branch may change leaf count (3 in, 4 out), and
                # then the egress does not fit -- SB_L had its egress block
                # zeroed to make room for the other branch, and SB_R's fourth
                # egress block would have landed at parent code 8, outside the
                # register. None of that arithmetic is used here.
                import numpy as np
                pw = payload_width(Plus(t.ty_left, t.ty_right))
                w = k + pw
                dim = 2 ** w

                _sb_in, _sb_out = parent_in, parent_out

                def _sb_fail(why):
                    raise UnsupportedFrame(
                        f"PlusMap: cannot construct the Strategy B dense "
                        f"placement plan ({why}). Failing closed before "
                        f"emission.")

                if _sb_in is None or _sb_out is None:
                    _sb_fail("the occurrence selected no parent frames")
                if _sb_in.n_qubits != _sb_out.n_qubits:
                    _sb_fail(f"parent registers differ "
                             f"({_sb_in.n_qubits} vs {_sb_out.n_qubits} qubits)")
                if _sb_in.n_qubits != w:
                    _sb_fail(f"parent register {_sb_in.n_qubits} qubits but "
                             f"Strategy B synthesises {w}")
                if len(_sb_in.codes) != len(_sb_out.codes):
                    _sb_fail(f"parent dimensions differ "
                             f"({len(_sb_in.codes)} vs {len(_sb_out.codes)})")
                if len(_sb_in.sectors) != 2 or len(_sb_out.sectors) != 2:
                    _sb_fail(f"expected exactly two parent sectors, got "
                             f"{len(_sb_in.sectors)} / {len(_sb_out.sectors)}")

                _sb_arts = (_left_art, _right_art)
                if len(_sb_arts) != 2:
                    _sb_fail("expected exactly two branch artifacts")

                _K_minus, _K_plus = [], []
                _in_maps, _out_maps = [], []
                _lg_in, _lg_out = [], []
                _G = []
                for _i, _a in enumerate(_sb_arts):
                    _Jm = tuple(_sb_in.sectors[_i].codes)
                    _Jp = tuple(_sb_out.sectors[_i].codes)
                    if _sb_in.sectors[_i].logical != type_of(
                            (t.left, t.right)[_i])[0]:
                        _sb_fail(f"sector {_i} ingress type disagrees with the "
                                 f"branch artifact interface")
                    if _sb_out.sectors[_i].logical != type_of(
                            (t.left, t.right)[_i])[1]:
                        _sb_fail(f"sector {_i} egress type disagrees with the "
                                 f"branch artifact interface")
                    if len(_a.fin.codes) != len(_Jm):
                        _sb_fail(f"sector {_i} ingress code map is "
                                 f"{len(_a.fin.codes)} -> {len(_Jm)}")
                    if len(_a.fout.codes) != len(_Jp):
                        _sb_fail(f"sector {_i} egress code map is "
                                 f"{len(_a.fout.codes)} -> {len(_Jp)}")
                    if len(set(_Jm)) != len(_Jm) or len(set(_Jp)) != len(_Jp):
                        _sb_fail(f"sector {_i} parent codes are not injective")
                    if any(not (0 <= c < dim) for c in _Jm + _Jp):
                        _sb_fail(f"sector {_i} parent codes leave the register")
                    _Ua = _a.unitary
                    if _Ua is None:
                        _sb_fail(f"sector {_i} artifact carries no unitary")

                    from compile.frames import (semantic_action as _sa2,
                                                leakage as _lk_fn)
                    _Gi = _sa2(_a.fin, _Ua, _a.fout)
                    _lk = _lk_fn(_a.fin, _Ua, _a.fout)
                    if _lk > 1e-9:
                        _sb_fail(f"branch {_i} leaks ({_lk:.6e}); projecting it "
                                 f"would mask the leak")
                    if _Gi.shape[0] != _Gi.shape[1] or _Gi.shape[0] != len(_Jm):
                        _sb_fail(f"branch {_i} action is {_Gi.shape}, expected "
                                 f"({len(_Jm)},{len(_Jm)})")
                    if not np.allclose(_Gi.conj().T @ _Gi,
                                       np.eye(_Gi.shape[0]), atol=1e-9,
                                       rtol=0.0):
                        _sb_fail(f"branch {_i} action is not unitary")

                    _K_minus.append(_Jm)
                    _K_plus.append(_Jp)
                    _in_maps.append(tuple(zip(tuple(_a.fin.codes), _Jm)))
                    _out_maps.append(tuple(zip(tuple(_a.fout.codes), _Jp)))
                    _lg_in.append(_sb_in.sectors[_i].logical)
                    _lg_out.append(_sb_out.sectors[_i].logical)
                    _G.append(_Gi)

                _used_in = [c for s_ in _K_minus for c in s_]
                _used_out = [c for s_ in _K_plus for c in s_]
                if len(set(_used_in)) != len(_used_in):
                    _sb_fail("parent ingress sectors overlap")
                if len(set(_used_out)) != len(_used_out):
                    _sb_fail("parent egress sectors overlap")
                if sorted(_used_in) != sorted(_sb_in.codes):
                    _sb_fail("ingress sectors are not exhaustive of the "
                             "parent codes")
                if sorted(_used_out) != sorted(_sb_out.codes):
                    _sb_fail("egress sectors are not exhaustive of the "
                             "parent codes")

                _free_in = tuple(sorted(set(range(dim)) - set(_used_in)))
                _free_out = tuple(sorted(set(range(dim)) - set(_used_out)))
                if len(_free_in) != len(_free_out):
                    _sb_fail(f"complement sizes differ "
                             f"({len(_free_in)} vs {len(_free_out)})")

                _sb_plan = StrategyBDensePlan(
                    n_qubits=w, K_minus=tuple(_K_minus), K_plus=tuple(_K_plus),
                    in_maps=tuple(_in_maps), out_maps=tuple(_out_maps),
                    free_in=_free_in, free_out=_free_out,
                    logicals_in=tuple(_lg_in), logicals_out=tuple(_lg_out))

                # B_valid = sum_i E(K_i^+) G_i E(K_i^-)^dagger, then the
                # deterministic ascending complement completion.
                def _E(codes):
                    M = np.zeros((dim, len(codes)), complex)
                    for _m, _c in enumerate(codes):
                        M[_c, _m] = 1.0
                    return M

                U_full = np.zeros((dim, dim), complex)
                for _Jm, _Jp, _Gi in zip(_sb_plan.K_minus, _sb_plan.K_plus, _G):
                    U_full += _E(_Jp) @ _Gi @ _E(_Jm).conj().T
                for _src, _dst in zip(_sb_plan.free_in, _sb_plan.free_out):
                    U_full[_dst, _src] = 1.0     # rows are outputs

                if not np.allclose(U_full.conj().T @ U_full, np.eye(dim),
                                   atol=1e-9, rtol=0.0):
                    _sb_fail("the completed block is not unitary")

                _plan_sink[_cur_occ[0]] = _sb_plan
                phys = [p.apply_new_to_old(offset + _j) for _j in range(w)]

                def _is_perm_matrix(U):
                    n_ = U.shape[0]
                    for r_ in range(n_):
                        mags = np.abs(U[r_])
                        if not (np.sum(mags > 0.5) == 1
                                and np.allclose(mags[mags <= 0.5], 0)):
                            return False
                    for c_ in range(n_):
                        mags = np.abs(U[:, c_])
                        if not (np.sum(mags > 0.5) == 1
                                and np.allclose(mags[mags <= 0.5], 0)):
                            return False
                    for r_ in range(n_):
                        for c_ in range(n_):
                            if np.abs(U[r_, c_]) > 0.5 and not np.allclose(
                                    U[r_, c_], 1.0, atol=1e-10):
                                return False
                    return True

                if w == 2:
                    from pytket.circuit import Unitary2qBox
                    box = Unitary2qBox(U_full)
                    circ.add_unitary2qbox(box, phys[0], phys[1])
                elif w == 3:
                    from pytket.circuit import Unitary3qBox
                    box = Unitary3qBox(U_full)
                    circ.add_unitary3qbox(box, phys[0], phys[1], phys[2])
                elif _is_perm_matrix(U_full):
                    # ToffoliBox for arbitrary permutation matrices on w qubits.
                    from pytket.circuit import ToffoliBox, ToffoliBoxSynthStrat
                    perm_pairs = []
                    full_dim = 2 ** w
                    for i in range(full_dim):
                        # Find j such that U[j, i] = 1.
                        col = U_full[:, i]
                        j = int(np.argmax(np.abs(col)))
                        inp = tuple(bool((i >> (w - 1 - b)) & 1) for b in range(w))
                        out = tuple(bool((j >> (w - 1 - b)) & 1) for b in range(w))
                        perm_pairs.append((inp, out))
                    box = ToffoliBox(perm_pairs, ToffoliBoxSynthStrat.Matching)
                    circ.add_toffolibox(box, phys)
                else:
                    # Width > 3 and not a permutation. pytket 2.11 has no
                    # general n-qubit unitary box (the ceiling is
                    # Unitary3qBox) and no matrix-accepting synthesis pass, so
                    # the only exact realisations are structured ones. A
                    # uniformly controlled U2 is recognised from the COMPLETED
                    # matrix -- cross-blocks zero, diagonal blocks unitary --
                    # never from pw or the type.
                    _blocks = _as_uniformly_controlled_u2(U_full)
                    if _blocks is None:
                        _sb_fail(
                            f"width {w} > 3 and the completed block is neither "
                            f"a permutation nor a uniformly controlled U2; "
                            f"pytket offers no general {w}-qubit unitary box, "
                            f"so there is no exact realisation")
                    from pytket.circuit import (MultiplexedU2Box,
                                                Unitary1qBox)
                    _nctrl = w - 1
                    _map = {}
                    for _bi, _blk in enumerate(_blocks):
                        # Control state is big-endian over the leading wires,
                        # matching phys order: phys[0..w-2] control,
                        # phys[w-1] target.
                        _bits = tuple(bool((_bi >> (_nctrl - 1 - _j)) & 1)
                                      for _j in range(_nctrl))
                        _map[_bits] = Unitary1qBox(_blk)
                    circ.add_gate(MultiplexedU2Box(_map), phys)

                if explain:
                    log.append(f"PlusMap(k={k}, Strategy B full unitary): "
                               f"n_left={n_left}, n_right={n_right}, w={w}")
                return

            dim = 2 ** k

            # Build permutation P: left indices → MSB=0 half, right → MSB=1 half
            P_list = [None] * dim
            for i in range(n_left):
                P_list[i] = i
            for i in range(n_right):
                P_list[n_left + i] = half + i
            used_targets = set(v for v in P_list if v is not None)
            free_targets = sorted(set(range(dim)) - used_targets)
            j = 0
            for i in range(dim):
                if P_list[i] is None:
                    P_list[i] = free_targets[j]
                    j += 1
            P_tup = tuple(P_list)
            is_identity_P = (P_tup == tuple(range(dim)))

            tw_left = tw_fn(t.ty_left) if isinstance(t.ty_left, Plus) else 0
            tw_right = tw_fn(t.ty_right) if isinstance(t.ty_right, Plus) else 0

            # --- Strategy A boundary transport -------------------------
            # Same three equations as the closed k<=1 path; only the lift
            # differs, because a branch that is itself a sum puts its inner
            # tag in the PARENT's tag register rather than in the payload
            # field. Scope is decided by the same explicit predicate, and once
            # in scope the plan is owed (it raises rather than degrading).
            _sa_in, _sa_out = parent_in, parent_out
            _sa_plan = None
            _sa_dp, _sa_cp = type_of(t)
            if (_sa_in is not None and _sa_out is not None
                    and _sa_in.n_qubits == _sa_out.n_qubits
                    and bool(_sa_in.sectors) and bool(_sa_out.sectors)
                    and _first_order(_sa_dp) and _first_order(_sa_cp)):
                _P_inv = [0] * dim
                for _a, _b in enumerate(P_tup):
                    _P_inv[_b] = _a
                _sub_tys = (t.ty_left, t.ty_right)

                def _sa_placement(sector, artifact_n, _st=_sub_tys, _k=k):
                    return _strategy_a_local_to_block(_st[sector], artifact_n, _k)

                _sa_plan = _plusmap_align_plan(
                    t, (_left_art, _right_art), k, _sa_in, _sa_out,
                    placement_fn=_sa_placement, P_inv=tuple(_P_inv),
                    payload_base_override=k)
                _plan_sink[_cur_occ[0]] = _sa_plan
                # (1) A_pre, before the P sandwich
                _emit_frame_align(_sa_in, _sa_plan.F_pre, offset,
                                  _sa_plan.n_qubits, where="A_pre (Strategy A)")

            # Step 1: Emit P (tag permutation) if non-identity
            if not is_identity_P:
                _emit_tag_perm_unitary(circ, p, P_tup, k, offset, explain, log)

            # Step 2: PlusMap_bit controlled on MSB.
            # When the sub-branch's tag width is less than k-1, the inner tag
            # bits NOT used by the sub-branch must be anti-controlled to
            # restrict the wrapped operation to valid leaf positions only
            # (the "extra" filler positions of the MSB half would otherwise
            # be incorrectly modified).
            msb_phys = p.apply_new_to_old(offset)

            if left_cmds:
                # When a plan exists its placement is THE authority; only the
                # unplanned path falls back to the formula.
                if _sa_plan is not None:
                    _pl0 = _sa_plan.placements[0]
                    left_wm = lambda w, _q=_pl0: p.apply_new_to_old(
                        offset + _q.wire(w))
                else:
                    left_wm = lambda w, stw=tw_left: p.apply_new_to_old(
                        _sub_wire_to_full(w, stw, offset, k))
                # Extra anti-control qubits: q[1..k-1-tw_left] (the inner tag
                # bits before the sub-circuit's bits, which are at the end).
                n_extra_left = k - 1 - tw_left
                extras_left = [p.apply_new_to_old(offset + 1 + i)
                               for i in range(n_extra_left)] if n_extra_left > 0 else None
                _emit_controlled_branch(msb_phys, left_cmds, left_wm,
                                        anti=True, extra_anti_qubits=extras_left)
            if right_cmds:
                if _sa_plan is not None:
                    _pl1 = _sa_plan.placements[1]
                    right_wm = lambda w, _q=_pl1: p.apply_new_to_old(
                        offset + _q.wire(w))
                else:
                    right_wm = lambda w, stw=tw_right: p.apply_new_to_old(
                        _sub_wire_to_full(w, stw, offset, k))
                n_extra_right = k - 1 - tw_right
                extras_right = [p.apply_new_to_old(offset + 1 + i)
                                for i in range(n_extra_right)] if n_extra_right > 0 else None
                _emit_controlled_branch(msb_phys, right_cmds, right_wm,
                                        extra_anti_qubits=extras_right)

            # Promote branch-accumulated global phases to exact-tag phases.
            # After the P permutation, left summands occupy NEW tag values
            # 0..n_left-1, and right summands occupy n_left..n_left+n_right-1.
            # A GlobalPhase inside a branch must fire once per tag value the
            # branch covers.
            tag_qubits_all = [p.apply_new_to_old(offset + i) for i in range(k)]
            if abs(left_phase) > 1e-10:
                for tag_value in range(n_left):
                    _emit_exact_tag_phase(circ, tag_qubits_all, tag_value, left_phase)
            if abs(right_phase) > 1e-10:
                for tag_value in range(n_right):
                    # P sends right summand i to tag (half + i), NOT (n_left + i);
                    # these coincide only when n_left == half. With n_left=3,
                    # n_right=2, k=3, half=4 the old base phased tag 3 (unused
                    # filler) and 4, missing tag 5 -> diag(1,1,1,-1,1) instead
                    # of diag(1,1,1,-1,-1).
                    _emit_exact_tag_phase(circ, tag_qubits_all, half + tag_value, right_phase)

            # Step 3: Emit P⁻¹ if non-identity
            if not is_identity_P:
                P_inv = [0] * dim
                for i in range(dim):
                    P_inv[P_tup[i]] = i
                _emit_tag_perm_unitary(circ, p, tuple(P_inv), k, offset, explain, log)

            # (3) A_post, after P^-1: the sandwich as a whole is the block B
            if _sa_plan is not None:
                _emit_frame_align(_sa_plan.F_mid, _sa_out, offset,
                                  _sa_plan.n_qubits, where="A_post (Strategy A)")

            if explain:
                log.append(f"PlusMap(k={k}, Strategy A): n_left={n_left}, n_right={n_right}, "
                           f"P={P_tup}, {len(left_cmds)} left gates, {len(right_cmds)} right gates "
                           f"at offset {offset}")
            return

        # NPlusMap: n-ary coherent sum eliminator
        # Uses per-branch X-flip + multi-controlled gates + X-unflip.
        # Open branches (with free vars referencing the outer env) get the
        # same deferred-Lam propagation + wire-mapped emission as binary
        # PlusMap. This is the single primitive that handles all n-ary
        # dispatch — binary PlusMap, control, anticontrol, etc. all desugar
        # to this path.
        if isinstance(t, Sum):
            # Block^sum_{alpha,beta}: the unitary block map  a.W1 (+) b.W2,
            # |alpha| = |beta| = 1.  NOT state preparation -- no Hadamard and
            # no amplitude preparation is emitted; the tag is the physical
            # coordinate of a boundary that is already a direct sum.
            import numpy as np
            from lang.types import (Plus as _Plus_s, flatten_plus as _fp_s,
                                    tag_width as _tw_s, payload_width as _pw_s)
            from typing_.check import _free_var_width as _fvw_s

            g1, a_ty = type_of(t.left)
            g2, b_ty = type_of(t.right)

            # Open premises need (Sum-complete)'s identity transport of the
            # inactive context, which requires the frame inclusions j_i^eps.
            # Those are deferred, so reject rather than approximate.
            if _fvw_s(t.left) > 0 or _fvw_s(t.right) > 0 or \
               width(g1) > 0 or width(g2) > 0:
                raise NotImplementedError(
                    "Sum with open premises requires inactive-context "
                    "completion (Sum-complete) via the frame inclusions "
                    "j_i^eps, which are deferred to the frame-aware repair "
                    "round. Closed premises are supported. See "
                    "docs/SUM_INTRODUCTION_DESIGN.md."
                )

            target = _Plus_s(a_ty, b_ty)
            k_s = _tw_s(target)
            pw_s = _pw_s(target)
            m_a = len(_fp_s(a_ty))
            w_tot = k_s + pw_s
            if w_tot > 3:
                raise NotImplementedError(
                    f"Sum needs a {w_tot}-qubit unitary box; pytket provides "
                    f"only Unitary1/2/3qBox (docs/LIMITATIONS.md sec 1).")

            sub1 = compile(t.left, materialize=True)
            sub2 = compile(t.right, materialize=True)
            U1 = sub1.circuit.get_unitary()
            U2 = sub2.circuit.get_unitary()
            # Branch coefficients only. Each premise's own global phase is
            # ALREADY carried by its get_unitary() (pytket's get_unitary
            # respects add_phase), so folding it into gamma as well would
            # square it -- e.g. a GlobalPhase(pi) premise gave (-1)*(-1) = +1.
            # Splatting U_i therefore promotes the premise scalar to an
            # exact-tag conditional phase automatically; gamma adds only
            # alpha / beta on top.
            gamma1 = np.exp(1j * t.alpha_theta)
            gamma2 = np.exp(1j * t.beta_theta)

            dim = 2 ** w_tot
            U_full = np.eye(dim, dtype=complex)

            for (U_i, gamma, off_i, ty_i) in (
                    (U1, gamma1, 0, a_ty), (U2, gamma2, m_a, b_ty)):
                m_i = len(_fp_s(ty_i))
                pw_i = _pw_s(ty_i) if isinstance(ty_i, _Plus_s) else width(ty_i)
                scale = 2 ** (pw_s - pw_i)

                def _g(u, y, _o=off_i, _s=scale):
                    return (_o + u) * (2 ** pw_s) + y * _s

                for u in range(m_i):
                    for y in range(2 ** pw_i):
                        gi = _g(u, y)
                        U_full[gi, :] = 0
                        U_full[:, gi] = 0
                for u1 in range(m_i):
                    for y1 in range(2 ** pw_i):
                        for u2 in range(m_i):
                            for y2 in range(2 ** pw_i):
                                L1 = u1 * (2 ** pw_i) + y1
                                L2 = u2 * (2 ** pw_i) + y2
                                # alpha / beta scale the ENTIRE valid block.
                                U_full[_g(u1, y1), _g(u2, y2)] = \
                                    gamma * U_i[L1, L2]

            phys = [p.apply_new_to_old(offset + j) for j in range(w_tot)]
            if w_tot == 1:
                from pytket.circuit import Unitary1qBox
                circ.add_unitary1qbox(Unitary1qBox(U_full), phys[0])
            elif w_tot == 2:
                from pytket.circuit import Unitary2qBox
                circ.add_unitary2qbox(Unitary2qBox(U_full), phys[0], phys[1])
            else:
                from pytket.circuit import Unitary3qBox
                circ.add_unitary3qbox(Unitary3qBox(U_full),
                                      phys[0], phys[1], phys[2])

            if explain:
                log.append(f"Sum(alpha={t.alpha_theta:.4f}, "
                           f"beta={t.beta_theta:.4f}, k={k_s}, pw={pw_s}) "
                           f"at offset {offset}")
            return

        if isinstance(t, DatatypeControl):
            # Coherent control over an n-ary datatype, TENSOR frame:
            #     [ D_tag (tag_width(D)) | A payload (width(A)) ]
            # Branch i fires under exact-tag control on tag value i; invalid
            # datatype tags act as identity. This is the emitter that `control`
            # used before its lowering was separated from NPlusMap -- moved
            # here verbatim so Z_n behaviour is unchanged.
            from lang.types import tag_width as tw_dc
            k = tw_dc(t.dt_rep)
            tag_phys = [p.apply_new_to_old(offset + j) for j in range(k)]
            payload_base = offset + k
            branch_pw = width(t.a_ty)

            for i, br in enumerate(t.branches):
                fv = _ordered_free_vars(br)
                fv_in_env = [(nm, ty_fv) for nm, ty_fv in fv if nm in env]

                if fv_in_env:
                    sub_env = {}
                    ctx_pos = branch_pw
                    for name, ty_fv in fv_in_env:
                        w_fv = width(ty_fv)
                        sub_env[name] = list(range(ctx_pos, ctx_pos + w_fv))
                        ctx_pos += w_fv

                    branch_to_compile = br
                    if deferred_fns:
                        for name, ty_fv in fv_in_env:
                            key = tuple(env[name])
                            if key in deferred_fns:
                                branch_to_compile = _substitute(
                                    branch_to_compile, name, deferred_fns[key])
                        branch_to_compile = _normalize(branch_to_compile)

                    sub_cmds, branch_phase_ht = _compile_branch(
                        branch_to_compile, env=sub_env,
                        scope=_branch_scope())

                    if sub_cmds:
                        ctx_parent_phys = []
                        for name, ty_fv in fv_in_env:
                            ctx_parent_phys.extend(env[name])

                        def _wm_open(_pw=branch_pw, _pb=payload_base,
                                     _cpp=list(ctx_parent_phys)):
                            def wire_map(w):
                                if w < _pw:
                                    return p.apply_new_to_old(_pb + w)
                                return _cpp[w - _pw]
                            return wire_map

                        _emit_nway_controlled(circ, tag_phys, i, sub_cmds,
                                              _wm_open())
                else:
                    sub_cmds, branch_phase_ht = _compile_branch(
                        br, scope=_branch_scope())

                    if sub_cmds:
                        def _wm_closed(pb=payload_base):
                            def wire_map(w):
                                return p.apply_new_to_old(pb + w)
                            return wire_map

                        _emit_nway_controlled(circ, tag_phys, i, sub_cmds,
                                              _wm_closed())

                _discharge_branch_phase(circ, tag_phys, [i], branch_phase_ht)

            if explain:
                log.append(f"DatatypeControl({t.name}, arity={t.arity}, "
                           f"k={k}, payload={branch_pw}) at offset {offset}")
            return

        if isinstance(t, NPlusMap):
            from lang.types import (Plus, flatten_plus, tag_width as tw_fn,
                                    payload_width, build_plus_tree)
            import math

            n_branches = len(t.summand_types)
            assert n_branches >= 2

            # Invariant L (docs/COMPILER_INVARIANTS.md): the emitter must use the
            # canonical layout of the complete domain, not an independent
            # allocation. Previously this computed k from the BRANCH COUNT and
            # pw from max(width(summand)), which for sum-headed summands yields a
            # frame no isometry connects to the declared type — e.g. (Z3, Z5) has
            # 3+5=8 leaves so canonical width is 3, while the old formula gave
            # ceil(log2 2) + max(2,3) = 4.
            dom_sum = build_plus_tree(list(t.summand_types))
            k = tw_fn(dom_sum)
            pw = payload_width(dom_sum)

            # Per-branch leaf counts and global tag offsets:
            #   m_i = |leaves(A_i)|,  o_i = sum_{j<i} m_j
            # Local leaf tag u of branch i embeds as global tag o_i + u.
            leaf_counts = [len(flatten_plus(st)) for st in t.summand_types]
            offsets_i = []
            _acc = 0
            for _m in leaf_counts:
                offsets_i.append(_acc)
                _acc += _m

            # Fast path: when every summand is a single leaf, o_i = i and each
            # branch owns exactly tag value i, so the canonical frame coincides
            # with per-branch exact-tag dispatch and controlled emission applies
            # directly. (This is every NPlusMap in the current corpus.)
            # ---- capability dispatch, BEFORE any circuit mutation ----
            #
            #   if has_open_branches:  require fast path (env-aware), else reject
            #   elif fast_path_supports: fast path
            #   elif source_frame == target_frame: dense synthesis
            #   else: reject (asymmetric Block synthesis)
            #
            # Dense synthesis is never invoked with env=None on an open block:
            # standalone-compiling an open branch yields a unitary carrying its
            # own context wires, whose top-left corner is unrelated to the
            # branch's action, and splatting it would silently miscompile.
            from typing_.check import _free_var_width as _fvw

            # fast_path_supports: exact-tag dispatch needs branch i to own
            # exactly tag value i, i.e. every summand is a single leaf.
            fast_path_supports = all(m == 1 for m in leaf_counts)
            open_branches = [i for i, br in enumerate(t.branches)
                             if _fvw(br) > 0]

            if open_branches and not fast_path_supports:
                raise NotImplementedError(
                    f"NPlusMap has open branches {open_branches} (free-variable "
                    f"contexts) but leaf counts {leaf_counts} require dense "
                    f"synthesis, which compiles branches standalone and cannot "
                    f"resolve free variables. Rejected before emission. "
                    f"See docs/LIMITATIONS.md."
                )

            all_single_leaf = fast_path_supports
            if not all_single_leaf:
                # Block synthesis at the canonical frame. Branch i owns the tag
                # RANGE [o_i, o_i+m_i), which is not power-of-2 aligned in
                # general, so exact-tag controlled emission cannot express it.
                # Build the block-diagonal unitary directly.
                #
                # Index mapping (big-endian, q[0] = MSB; a branch's payload
                # occupies the first pw_i of the pw global payload wires):
                #   local   L = u * 2^pw_i + y            (u < m_i, y < 2^pw_i)
                #   global  G = (o_i + u) * 2^pw + y * 2^(pw - pw_i)
                # The tag relation is additive, not a bit projection — which is
                # exactly why controlled emission does not apply.
                import numpy as np

                cod_sum = build_plus_tree(
                    [type_of(br)[1] for br in t.branches])
                if (tw_fn(cod_sum), payload_width(cod_sum)) != (k, pw):
                    raise NotImplementedError(
                        f"NPlusMap block synthesis currently requires the domain "
                        f"and codomain to share a canonical frame; got "
                        f"dom (k={k}, pw={pw}) vs cod "
                        f"(k={tw_fn(cod_sum)}, pw={payload_width(cod_sum)})."
                    )

                w_total = k + pw
                if w_total > 3:
                    raise NotImplementedError(
                        f"NPlusMap block synthesis needs a {w_total}-qubit unitary "
                        f"box; pytket provides only Unitary1/2/3qBox "
                        f"(docs/LIMITATIONS.md §1)."
                    )

                dim = 2 ** w_total
                U_full = np.eye(dim, dtype=complex)

                for i, (st, br) in enumerate(zip(t.summand_types, t.branches)):
                    m_i = leaf_counts[i]
                    o_i = offsets_i[i]
                    pw_i = payload_width(st) if isinstance(st, Plus) else width(st)
                    scale = 2 ** (pw - pw_i)

                    # An OPEN branch carries context wires for its free
                    # variables, so its unitary is larger than the block we
                    # splat into and its top-left corner is unrelated to the
                    # branch's action. Reading it would silently miscompile
                    # (indices stay in range), so reject explicitly.
                    from typing_.check import _free_var_width as _fvw
                    fv_open = [nm for nm, _ in _ordered_free_vars(br)
                               if env and nm in env]
                    if fv_open or _fvw(br) > 0:
                        raise NotImplementedError(
                            f"NPlusMap block synthesis does not support open "
                            f"branches: branch {i} has free variables "
                            f"{[nm for nm, _ in _ordered_free_vars(br)]} "
                            f"(context width {_fvw(br)}). The "
                            f"controlled-emission path resolves these against "
                            f"the outer env; synthesis compiles branches "
                            f"standalone and cannot."
                        )

                    U_i = compile(br, materialize=True).circuit.get_unitary()

                    def g_index(u, y, _o=o_i, _s=scale):
                        return (_o + u) * (2 ** pw) + y * _s

                    # Clear this branch's global block (rows and columns) before
                    # splatting, so the initial identity does not leak in.
                    for u in range(m_i):
                        for y in range(2 ** pw_i):
                            gi = g_index(u, y)
                            U_full[gi, :] = 0
                            U_full[:, gi] = 0

                    for u1 in range(m_i):
                        for y1 in range(2 ** pw_i):
                            for u2 in range(m_i):
                                for y2 in range(2 ** pw_i):
                                    L1 = u1 * (2 ** pw_i) + y1
                                    L2 = u2 * (2 ** pw_i) + y2
                                    U_full[g_index(u1, y1), g_index(u2, y2)] = \
                                        U_i[L1, L2]

                phys = [p.apply_new_to_old(offset + j) for j in range(w_total)]
                if w_total == 1:
                    from pytket.circuit import Unitary1qBox
                    circ.add_unitary1qbox(Unitary1qBox(U_full), phys[0])
                elif w_total == 2:
                    from pytket.circuit import Unitary2qBox
                    circ.add_unitary2qbox(Unitary2qBox(U_full), phys[0], phys[1])
                else:
                    from pytket.circuit import Unitary3qBox
                    circ.add_unitary3qbox(Unitary3qBox(U_full),
                                          phys[0], phys[1], phys[2])

                if explain:
                    log.append(
                        f"NPlusMap(block synthesis): leaf_counts={leaf_counts}, "
                        f"offsets={offsets_i}, k={k}, pw={pw} at offset {offset}")
                return

            tag_phys = [p.apply_new_to_old(offset + j) for j in range(k)]
            payload_base = offset + k

            # --- closed fast-path sector transport ---------------------------
            # The synthetic NPlusMap is its own occurrence and owns its own
            # plan; it does not inherit anything from a PlusMap that
            # auto-flatten dissolved. Its cut has one sector per leaf, which is
            # a different (and equally legitimate) classification of the same
            # embedding the outer PlusMap occurrence records with fewer
            # sectors.
            # "Closed" must mean SYNTACTICALLY closed -- free variables are
            # computed independently of `env`. Keying on env membership let a
            # branch with a free variable that simply is not in scope be
            # classified as closed and compiled standalone, which is not a
            # closed branch, it is an unresolved one.
            _np_fv = [[nm for nm, _ in _ordered_free_vars(br)]
                      for br in t.branches]
            _np_unresolved = [(i, [nm for nm in fv if not (env and nm in env)])
                              for i, fv in enumerate(_np_fv)]
            _np_unresolved = [(i, nms) for i, nms in _np_unresolved if nms]
            if _np_unresolved:
                # Before branch compilation, Align emission or any parent
                # mutation. The open/context path is a later phase; until it
                # exists this fails closed rather than compiling a branch
                # whose context nothing supplies.
                raise UnsupportedFrame(
                    f"NPlusMap: branch(es) "
                    f"{[i for i, _ in _np_unresolved]} have free variables "
                    f"{[nms for _, nms in _np_unresolved]} that are not bound "
                    f"in the enclosing environment, so their context is "
                    f"unresolved. Failing closed before emission.")
            if any(_np_fv):
                # G2 SHADOW: same planner, same policy, different adapter.
                try:
                    _fv_all = []
                    _seen_nm = set()
                    for _br in t.branches:
                        for nm, ty_ in _ordered_free_vars(_br):
                            if nm not in _seen_nm:
                                _seen_nm.add(nm)
                                _fv_all.append((nm, ty_))
                    _pi, _po = select_frames(t)
                    _sp = _plan_open_occurrence_for(
                        t, _pi, _po, _fv_all, k, k, env)
                    if _sp is not None:
                        _shadow_plans[_cur_occ[0]] = _sp
                        _planner_observed.append(_sp)
                except ProvenanceError:
                    pass
            _np_arts = None
            _np_plan = None
            if not any(_np_fv):
                # Compile every branch EXACTLY once, carrying commands, phase
                # and both frames together.
                _np_arts = [_compile_branch_artifact(br, scope=_branch_scope())
                            for br in t.branches]
                _npf_in, _npf_out = parent_in, parent_out
                _np_dp, _np_cp = type_of(t)
                if (_npf_in is not None and _npf_out is not None
                        and _npf_in.n_qubits == _npf_out.n_qubits
                        and bool(_npf_in.sectors) and bool(_npf_out.sectors)
                        and len(_npf_in.sectors) == len(t.branches)
                        and len(_npf_out.sectors) == len(t.branches)
                        and _first_order(_np_dp) and _first_order(_np_cp)):
                    _np_plan = _plusmap_align_plan(
                        t, _np_arts, k, _npf_in, _npf_out,
                        payload_base_override=k, selector_bits=k,
                        summ_in=list(t.summand_types),
                        summ_out=[type_of(br)[1] for br in t.branches])
                    # Validate against the derivation-selected parent sectors.
                    for _i, _pl in enumerate(_np_plan.placements):
                        if _pl.logical_in != _npf_in.sectors[_i].logical or \
                                _pl.logical_out != _npf_out.sectors[_i].logical:
                            raise UnsupportedFrame(
                                f"NPlusMap: branch {_i} interface disagrees "
                                f"with the selected parent sector. Failing "
                                f"closed before emission.")
                    _plan_sink[_cur_occ[0]] = _np_plan
                    _emit_frame_align(_npf_in, _np_plan.F_pre, offset,
                                      _np_plan.n_qubits, where="A_pre (NPlusMap)")

            for i, (st, br) in enumerate(zip(t.summand_types, t.branches)):
                branch_pw = width(st)
                # Check if branch is open: any free var present in outer env.
                fv = _ordered_free_vars(br)
                fv_in_env = [(name, ty_fv) for name, ty_fv in fv if name in env]

                if fv_in_env:
                    # Open branch: build sub_env, substitute deferred Lams, compile.
                    sub_env = {}
                    ctx_pos = branch_pw
                    for name, ty_fv in fv_in_env:
                        w_fv = width(ty_fv)
                        sub_env[name] = list(range(ctx_pos, ctx_pos + w_fv))
                        ctx_pos += w_fv

                    branch_to_compile = br
                    if deferred_fns:
                        for name, ty_fv in fv_in_env:
                            key = tuple(env[name])
                            if key in deferred_fns:
                                branch_to_compile = _substitute(
                                    branch_to_compile, name, deferred_fns[key])
                        branch_to_compile = _normalize(branch_to_compile)

                    sub_cmds, branch_phase_ht = _compile_branch(
                        branch_to_compile, env=sub_env,
                        scope=_branch_scope())

                    if sub_cmds:
                        ctx_parent_phys = []
                        for name, ty_fv in fv_in_env:
                            ctx_parent_phys.extend(env[name])

                        def make_wire_map_open(_pw=branch_pw, _pb=payload_base,
                                               _cpp=list(ctx_parent_phys)):
                            def wire_map(w):
                                if w < _pw:
                                    return p.apply_new_to_old(_pb + w)
                                else:
                                    return _cpp[w - _pw]
                            return wire_map

                        _emit_nway_controlled(circ, tag_phys, i, sub_cmds,
                                              make_wire_map_open())
                else:
                    # Closed branch: reuse the single compile from above.
                    if _np_arts is not None:
                        sub_cmds = _np_arts[i].cmds
                        branch_phase_ht = _np_arts[i].phase
                    else:
                        sub_cmds, branch_phase_ht = _compile_branch(
                        br, scope=_branch_scope())

                    if sub_cmds:
                        if _np_plan is not None:
                            # THE authority. `payload_base + w` happens to give
                            # the same answer here, and keeping both would
                            # recreate exactly the drift removed for Strategy A.
                            def make_wire_map(_pl=_np_plan.placements[i],
                                              _off=offset):
                                def wire_map(w):
                                    return p.apply_new_to_old(_off + _pl.wire(w))
                                return wire_map
                        else:
                            # Unplanned legacy path only.
                            def make_wire_map(pb=payload_base):
                                def wire_map(w):
                                    return p.apply_new_to_old(pb + w)
                                return wire_map

                        _emit_nway_controlled(circ, tag_phys, i, sub_cmds,
                                              make_wire_map())

                _discharge_branch_phase(circ, tag_phys, [i], branch_phase_ht)

            if _np_plan is not None:
                _emit_frame_align(_np_plan.F_mid, _npf_out, offset,
                                  _np_plan.n_qubits, where="A_post (NPlusMap)")

            if explain:
                log.append(f"NPlusMap(n={n_branches}, k={k}): "
                           f"{n_branches} branches at offset {offset}")
            return

        # PhasedPlusMap: like PlusMap but with phase z = e^{iθ} on left branch
        if isinstance(t, PhasedPlusMap):
            from lang.types import Plus, flatten_plus, tag_width as tw_fn, payload_width
            import math

            theta = t.theta

            n_left = len(flatten_plus(t.ty_left)) if isinstance(t.ty_left, Plus) else 1
            n_right = len(flatten_plus(t.ty_right)) if isinstance(t.ty_right, Plus) else 1
            n_sum = n_left + n_right
            k = math.ceil(math.log2(n_sum)) if n_sum > 1 else 0

            # Compile branches to sub-circuits. Extract accumulated global
            # phase so any GlobalPhase inside a branch (as opposed to the
            # PhasedPlusMap's own phase parameter) is not silently dropped
            # during the commands-only extraction.
            left_dom, _ = type_of(t.left)
            left_w = width(left_dom)
            left_cmds, left_branch_phase_ht = _compile_branch(
                t.left, scope=_branch_scope())
            if left_w == 0:
                left_cmds = []

            right_dom, _ = type_of(t.right)
            right_w = width(right_dom)
            right_cmds, right_branch_phase_ht = _compile_branch(
                t.right, scope=_branch_scope())
            if right_w == 0:
                right_cmds = []

            if k <= 1:
                tag_phys = p.apply_new_to_old(offset)
                payload_base = offset + max(k, 1)

                wire_map = lambda w: p.apply_new_to_old(w + payload_base)
                if left_cmds:
                    _emit_controlled_branch(tag_phys, left_cmds, wire_map, anti=True)
                if right_cmds:
                    _emit_controlled_branch(tag_phys, right_cmds, wire_map)

                # Phase application: X; U1(θ/π); X for left branch (tag=0)
                half_turns = theta / math.pi
                circ.X(tag_phys)
                circ.add_gate(OpType.U1, [half_turns], [tag_phys])
                circ.X(tag_phys)

                # Promote branch-accumulated global phases to exact-tag
                # relative phases on the tag qubit, in addition to the
                # PhasedPlusMap's own phase parameter above. Without this,
                # a GlobalPhase inside a branch would be silently dropped.
                if abs(left_branch_phase_ht) > 1e-10:
                    _emit_exact_tag_phase(circ, [tag_phys], 0, left_branch_phase_ht)
                if abs(right_branch_phase_ht) > 1e-10:
                    _emit_exact_tag_phase(circ, [tag_phys], 1, right_branch_phase_ht)

                if explain:
                    log.append(f"PhasedPlusMap(k=1, θ={theta:.4f}): {len(left_cmds)} left, "
                               f"{len(right_cmds)} right; "
                               f"left_branch_phase_ht={left_branch_phase_ht:.4f}, "
                               f"right_branch_phase_ht={right_branch_phase_ht:.4f} "
                               f"at offset {offset}")
                return

            # k >= 2: Strategy A — tag permutation sandwich
            half = 2 ** (k - 1)

            if n_left > half or n_right > half:
                # Strategy B: full unitary synthesis (same as PlusMap, plus phase)
                import numpy as np
                pw = payload_width(Plus(t.ty_left, t.ty_right))
                w = k + pw
                dim_pw = 2 ** pw

                _sb_f = compile(t.left, materialize=True)
                _sb_g = compile(t.right, materialize=True)
                U_f = _sb_f.circuit.get_unitary()
                U_g = _sb_g.circuit.get_unitary()
                # Invariant P: a width-0 branch contributes ONLY a scalar; the
                # identity fill below would discard it.
                _zf = np.exp(1j * np.pi * float(_sb_f.circuit.phase))
                _zg = np.exp(1j * np.pi * float(_sb_g.circuit.phase))
                dim = 2 ** w

                def _splat_phased(U_dst, U_src, n_blocks, off, dim_pw):
                    for b1 in range(n_blocks):
                        for b2 in range(n_blocks):
                            d_rs1, d_re1 = (off + b1) * dim_pw, (off + b1 + 1) * dim_pw
                            d_rs2, d_re2 = (off + b2) * dim_pw, (off + b2 + 1) * dim_pw
                            s_rs1, s_re1 = b1 * dim_pw, (b1 + 1) * dim_pw
                            s_rs2, s_re2 = b2 * dim_pw, (b2 + 1) * dim_pw
                            U_dst[d_rs1:d_re1, d_rs2:d_re2] = U_src[s_rs1:s_re1, s_rs2:s_re2]

                if n_left > half:
                    U_full = U_f.copy()
                    w_g = width(type_of(t.right)[0])
                    for tr in range(n_right):
                        tf = n_left + tr
                        rs, re = tf * dim_pw, (tf + 1) * dim_pw
                        U_full[rs:re, :] = 0
                        U_full[:, rs:re] = 0
                    if w_g == 0:
                        for tr in range(n_right):
                            tf = n_left + tr
                            rs, re = tf * dim_pw, (tf + 1) * dim_pw
                            U_full[rs:re, rs:re] = _zg * np.eye(dim_pw)
                    else:
                        _splat_phased(U_full, U_g, n_right, n_left, dim_pw)
                else:
                    U_full = np.eye(dim, dtype=complex)
                    w_f = width(type_of(t.left)[0])
                    if w_f == 0:
                        for tl in range(n_left):
                            rs, re = tl * dim_pw, (tl + 1) * dim_pw
                            U_full[rs:re, rs:re] = _zf * np.eye(dim_pw)
                    else:
                        _splat_phased(U_full, U_f, n_left, 0, dim_pw)
                    _splat_phased(U_full, U_g, n_right, n_left, dim_pw)

                # Apply phase e^{iθ} to all left tag blocks
                phase = np.exp(1j * theta)
                for tl in range(n_left):
                    rs, re = tl * dim_pw, (tl + 1) * dim_pw
                    U_full[rs:re, :] *= phase

                phys = [p.apply_new_to_old(offset + i) for i in range(w)]
                if w == 2:
                    from pytket.circuit import Unitary2qBox
                    box = Unitary2qBox(U_full)
                    circ.add_unitary2qbox(box, phys[0], phys[1])
                elif w == 3:
                    from pytket.circuit import Unitary3qBox
                    box = Unitary3qBox(U_full)
                    circ.add_unitary3qbox(box, phys[0], phys[1], phys[2])
                else:
                    raise NotImplementedError(
                        f"PhasedPlusMap full unitary for width {w} > 3 not yet supported")

                if explain:
                    log.append(f"PhasedPlusMap(k={k}, θ={theta:.4f}, Strategy B): "
                               f"n_left={n_left}, n_right={n_right}, w={w}")
                return

            dim = 2 ** k
            P_list = [None] * dim
            for i in range(n_left):
                P_list[i] = i
            for i in range(n_right):
                P_list[n_left + i] = half + i
            used_targets = set(v for v in P_list if v is not None)
            free_targets = sorted(set(range(dim)) - used_targets)
            j = 0
            for i in range(dim):
                if P_list[i] is None:
                    P_list[i] = free_targets[j]
                    j += 1
            P_tup = tuple(P_list)
            is_identity_P = (P_tup == tuple(range(dim)))

            tw_left = tw_fn(t.ty_left) if isinstance(t.ty_left, Plus) else 0
            tw_right = tw_fn(t.ty_right) if isinstance(t.ty_right, Plus) else 0

            # Step 1: Emit P
            if not is_identity_P:
                _emit_tag_perm_unitary(circ, p, P_tup, k, offset, explain, log)

            # Step 2: PlusMap_bit on MSB
            msb_phys = p.apply_new_to_old(offset)

            if left_cmds:
                # When a plan exists its placement is THE authority; only the
                # unplanned path falls back to the formula.
                if _sa_plan is not None:
                    _pl0 = _sa_plan.placements[0]
                    left_wm = lambda w, _q=_pl0: p.apply_new_to_old(
                        offset + _q.wire(w))
                else:
                    left_wm = lambda w, stw=tw_left: p.apply_new_to_old(
                        _sub_wire_to_full(w, stw, offset, k))
                _emit_controlled_branch(msb_phys, left_cmds, left_wm, anti=True)
            if right_cmds:
                if _sa_plan is not None:
                    _pl1 = _sa_plan.placements[1]
                    right_wm = lambda w, _q=_pl1: p.apply_new_to_old(
                        offset + _q.wire(w))
                else:
                    right_wm = lambda w, stw=tw_right: p.apply_new_to_old(
                        _sub_wire_to_full(w, stw, offset, k))
                _emit_controlled_branch(msb_phys, right_cmds, right_wm)

            # Promote branch-accumulated global phases to exact-tag relative
            # phases at each tag value the branch covers. After the P
            # permutation, left summands live at NEW tag values 0..n_left-1
            # and right at n_left..n_left+n_right-1. Emits ONLY when a
            # branch's `.phase` is non-trivial; the PhasedPlusMap's own
            # phase parameter has already been applied below.
            tag_qubits_all_pp = [p.apply_new_to_old(offset + i) for i in range(k)]
            if abs(left_branch_phase_ht) > 1e-10:
                for tag_value in range(n_left):
                    _emit_exact_tag_phase(circ, tag_qubits_all_pp, tag_value, left_branch_phase_ht)
            if abs(right_branch_phase_ht) > 1e-10:
                for tag_value in range(n_right):
                    # Same tag-base correction as PlusMap Strategy A above.
                    _emit_exact_tag_phase(circ, tag_qubits_all_pp, half + tag_value, right_branch_phase_ht)

            # Step 3: Emit P⁻¹
            if not is_identity_P:
                P_inv = [0] * dim
                for i in range(dim):
                    P_inv[P_tup[i]] = i
                _emit_tag_perm_unitary(circ, p, tuple(P_inv), k, offset, explain, log)

            # Phase application on left branch (tag ∈ left_set).
            # After Strategy A's tag permutation P, left summands occupy
            # NEW tag values 0..n_left-1. Phase EACH of them; a single
            # anti-control on the MSB is insufficient when n_left is not
            # a full 2^(k-1) block (e.g., asymmetric n_left=3, n_right=1).
            sum_ty = Plus(t.ty_left, t.ty_right)
            total_tag_bits = tw_fn(sum_ty)
            half_turns = theta / math.pi
            tag_qubits = [p.apply_new_to_old(offset + i) for i in range(total_tag_bits)]

            for tag_value in range(n_left):
                _emit_exact_tag_phase(circ, tag_qubits, tag_value, half_turns)

            if explain:
                log.append(f"PhasedPlusMap(k={k}, θ={theta:.4f}, Strategy A): "
                           f"n_left={n_left}, n_right={n_right} at offset {offset}")
            return

        # PhasedControl: phase-weighted n-ary control
        if isinstance(t, PhasedControl):
            from lang.types import tag_width
            import math

            arity = t.arity
            phases = t.phases  # List of angles in radians
            n_tag_bits = tag_width(t.dt_rep)

            # Convert radians to half-turns for pytket
            half_turns = [theta / math.pi for theta in phases]

            # Get the tag qubits once (same for every branch)
            tag_qubits = [p.apply_new_to_old(offset + i) for i in range(n_tag_bits)]

            # For each branch i, apply phase e^{iθᵢ} at tag basis state i,
            # using the big-endian helper (matching NPlusMap's convention).
            # This replaces the earlier little-endian expression and unifies
            # the tag-indexing convention across NPlusMap/PhasedPlusMap/PhasedControl.
            for branch_idx in range(arity):
                theta_ht = half_turns[branch_idx]
                # Skip if phase is effectively 1 (theta ≈ 0 mod 2π)
                if abs(theta_ht) < 1e-10 or abs(abs(theta_ht) - 2.0) < 1e-10:
                    continue
                _emit_exact_tag_phase(circ, tag_qubits, branch_idx, theta_ht)

            if explain:
                non_trivial = sum(1 for ht in half_turns if abs(ht) >= 1e-10 and abs(abs(ht) - 2.0) >= 1e-10)
                log.append(f"PhasedControl({t.name}, arity={arity}): {non_trivial} non-trivial phases on {n_tag_bits} tag bits at offset {offset}")
            return

        # Compact-closed: Cup and Cap (pure wiring, zero gates)
        if isinstance(t, Cup):
            # η_A : I → A ⊗ A* — allocates 2·width(A) wires, no gates
            if explain:
                log.append(f"Cup({t.ty}): pure wiring, 0 gates at offset {offset}")
            return

        if isinstance(t, Cap):
            # ε_A : A* ⊗ A → I — wire identification, no gates
            if explain:
                log.append(f"Cap({t.ty}): pure wiring, 0 gates at offset {offset}")
            return

        # Higher-order constructs (compiled via cup/cap wiring)
        if isinstance(t, FunVar):
            # Identity on function wires (A ⊗ B)
            if explain:
                log.append(f"FunVar '{t.name}': identity on {width(t.dom) + width(t.cod)} wires at offset {offset}")
            return

        if isinstance(t, Lam):
            # Lambda: λx:A. body : Γ → (A ⊸ B)
            # Per spec §4.4: Boundary exposure
            #
            # body : (Γ ⊗ A) → B is compiled with x:A bound to extra input wires.
            # Lambda repackages: C_{λx.body} : ⟦Γ⟧ → ⟦A⟧||⟦B⟧
            #
            # Output layout: [A_slot | B_slot] where:
            #   - A_slot (wires [offset..offset+wA)) = x (argument input)
            #   - B_slot (wires [offset+wA..offset+wA+wB)) = body output
            wA = width(t.dom)
            wB = width(t.cod)

            # Deferred mode: when compiled as a function VALUE (is_value=True),
            # don't compile the body — just reserve the wire layout [A_slot|B_slot].
            # The body will be compiled at Apply time via β-reduction.
            # This is essential for the trace model: body gates must fire AFTER
            # the argument data is in place, not on |0⟩.
            if is_value:
                # Record deferred Lam by its physical wire positions
                phys_wires = tuple(p.new_to_old[offset + i] for i in range(wA + wB))
                deferred_fns[phys_wires] = t
                if explain:
                    log.append(f"Lam '{t.name}' (deferred): wA={wA}, wB={wB} at offset {offset}, phys={phys_wires}")
                return

            # Check for open lambda: body has free variables from enclosing scope.
            # If so, we must bind x AFTER the context wires to avoid overlap.
            fv = _ordered_free_vars(t.body, frozenset({t.name}))
            ctx_w = sum(width(ty) for _, ty in fv)

            if ctx_w > 0:
                # Open lambda: context wires Γ occupy [offset..offset+ctx_w)
                # in the env. Bind x at [offset+ctx_w..offset+ctx_w+wA) to avoid
                # overlapping with Γ wires.
                x_phys = [p.new_to_old[offset + ctx_w + i] for i in range(wA)]
                new_env = {**env, t.name: x_phys}

                # Compile body: it accesses both Γ (via env) and x
                go(t.body, offset, new_env)

                # Route to [A_slot | B_slot] output layout.
                # After body: result at logical [offset..offset+wB).
                # Same rotation as closed case: shift body output to B_slot.
                total_width = wA + wB
                if total_width > 0 and wB > 0:
                    local_perm = list(range(wB, total_width)) + list(range(wB))
                    step = embed_local_perm(WirePerm(total_width, local_perm), offset)
                    p = compose(step, p)
                    if explain:
                        log.append(f"Lam '{t.name}' (open): route to [A|B], wA={wA}, wB={wB}")

                if explain:
                    log.append(f"Lam '{t.name}' (open): x phys={x_phys}, ctx_w={ctx_w}, "
                               f"B_slot at [{offset+wA}, {offset+wA+wB})")
                return

            # Closed lambda: x bound at [offset..offset+wA), no context overlap.
            x_phys = [p.new_to_old[offset + i] for i in range(wA)]
            new_env = {**env, t.name: x_phys}

            # Compile body with x bound
            go(t.body, offset, new_env)

            # Route body output to B_slot:
            # After body: result at [offset..offset+wB). Rotate to [A_slot | B_slot].
            total_width = wA + wB
            if total_width > 0 and wB > 0:
                local_perm = list(range(wB, total_width)) + list(range(wB))
                step = embed_local_perm(WirePerm(total_width, local_perm), offset)
                p = compose(step, p)
                if explain:
                    log.append(f"Lam '{t.name}': route body output to B_slot, wA={wA}, wB={wB}")

            if explain:
                log.append(f"Lam '{t.name}': x phys={x_phys} at offset {offset}, B_slot at [{offset+wA}, {offset+wA+wB})")
            return

        if isinstance(t, Apply):
            # Apply: f arg : B
            # Per spec §4.5: Boundary splicing / β-reduction
            #
            # f : ... → Arrow(A, B) produces [A_slot | B_slot] on output
            # arg : ... → A produces [A] on output
            # Apply connects (identifies) arg's A output with f's A_slot
            # Result is B_slot

            # Multi-level β-reduction for nested Apply chains. Apply(Apply(Lam(x,
            # Lam(y, body)), v1), v2) → body[v1/x, v2/y] without mixing β-reduce
            # and boundary-splicing at different levels (which causes wire
            # misalignment). Skipped when any inner Lam doesn't reference its
            # variable, to preserve deferred semantics (qswitch / select_2).
            reduced = _peel_apply_chain(t, term_env)
            if reduced is not None:
                # The cut is peeled away before emission, so this occurrence
                # has no AppCut boundary. Said explicitly, with the reason, so
                # it is not mistaken for a rule that failed to fire.
                _boundary_sink[_cur_occ[0]] = "appcut:peeled"
                go(_normalize(reduced), offset, env)
                return

            f_dom, f_cod = type_of(t.f)
            if not isinstance(f_cod, Arrow):
                raise TypeCheckError(f"Apply expects function type, got {f_cod}")

            A = f_cod.dom
            B = f_cod.cod
            wA = width(A)
            wB = width(B)

            # Try to find the underlying Lam for β-reduction.
            # This handles: Apply(Lam, arg), Apply(Var(f), arg) where f is a known Lam,
            # and Apply(Seq(Lam, Id), arg).
            lam = _find_lam(t.f, term_env)

            if lam is not None:
                # β-reduction: compile arg (with deferred Lam bodies), then body
                # Arg compiled as value: Lam bodies within the arg are deferred
                # and registered in term_env for inner Apply β-reduction.
                go(t.arg, offset, env, is_value=True)
                # Register arg term in term_env for LetPair propagation
                term_env[lam.name] = t.arg
                # Bind x to the argument wires (physical positions for perm stability)
                x_phys = [p.new_to_old[offset + i] for i in range(wA)]
                new_env = {**env, lam.name: x_phys}
                go(lam.body, offset, new_env)
                # β-reduction ELIMINATES the cut, so there is no AppCut
                # boundary to build here. Recorded explicitly.
                _boundary_sink[_cur_occ[0]] = "appcut:beta-reduced"
                if explain:
                    log.append(f"Apply (β-reduce '{lam.name}'): arg;body, x phys={x_phys}")
                return

            # ---- Canonical-form precondition, BEFORE any emission ---------
            #
            # The reference emitter is defined on canonical normal
            # derivations, in which an application's head is a neutral
            # variable spine. A head like
            #
            #     Seq(Var h, WireIdentity, TwistTen, WireIdentity)
            #
            # typechecks and reaches here, but it relabels the head's own
            # bundle, so its residual boundary is not the resource it was at
            # the cut -- Y_B^- and Y_B^+ genuinely part company and the
            # selected boundary leaks. Part H does not widen to cover such a
            # head; it refuses it, and the source/NF layer is what guarantees
            # one never arrives.
            #
            # Checked here -- after the beta/Lam cases are ruled out, and
            # before the argument, the head, or the circuit is touched -- so
            # the refusal costs no emission and leaves nothing half-built.
            if not _is_neutral_spine(t.f):
                raise UnsupportedFrame(
                    f"AppCut requires a canonical neutral variable spine as "
                    f"its head (neutral ::= Var | Apply(neutral, "
                    f"normal_argument)), but this head is "
                    f"{type(t.f).__name__}. The reference emitter is defined "
                    f"on canonical normal derivations; normalize the term "
                    f"before compiling it.")

            # General case: full boundary splicing with function layout
            # 1. Compile arg at offset - fills A_slot wires
            # 2. Compile f at offset - f's body operates on A_slot, B_slot is result
            # 3. Result is on B_slot: [offset+wA..offset+wA+wB)

            # Compile arg first - produces A on wires [offset..offset+wA)
            # This fills the A_slot that f will read from
            _a_arg = go(t.arg, offset, env)

            # Compile f - operates on wires [offset..offset+wA+wB)
            # f's A_slot is [offset..offset+wA), B_slot is [offset+wA..offset+wA+wB)
            # For Lam, the body+swap makes B_slot contain the result
            _a_fun = go(t.f, offset, env)

            # After f: result is on B_slot [offset+wA..offset+wA+wB)
            # But Apply's output type is B (width wB), so we need to
            # route B_slot to [offset..offset+wB)
            #
            # This is the inverse of Lam's routing.
            # Lam did: rotate left by wB (body output [0..wB) → [wA..wA+wB))
            # Apply undoes: rotate right by wB (B_slot [wA..wA+wB) → [0..wB))
            # ---- AppCut selected boundary --------------------------------
            #
            #     B_hy^+-  =  (r_1^+-)^-1 [ S_y^+- (x) Y_B^+- ]
            #
            # The head is CONSUMED: it contributes no factor and no residual
            # port. What is retained is the operand package S_y and the
            # residual result boundary Y_B, operand first.
            #
            # THE TWO POLARITIES ARE BUILT SEPARATELY, from the two premises'
            # OWN recorded schedules -- never one snapshot reused:
            #
            #   S_y^-  the argument's ingress chart on its ingress placement
            #   S_y^+  the argument's egress  chart on its egress  placement
            #   Y_B^-  the head bundle's ingress placement, B half
            #   Y_B^+  the head bundle's egress  placement, B half
            #
            # A structural relabeller (TwistTen, DistR, Seq, Lam) reorders a
            # premise's ingress placement relative to its egress placement,
            # so these are four distinct tuples in general.
            #
            # Y_B's CODES are the canonical boundary of the residual type B,
            # read off the head's own Arrow type; the same codes on both
            # polarities is what yank_B says, while the two PLACEMENTS stay
            # independent. Nothing is read from `env` here, nothing is
            # inferred from widths, varying bits or a matrix fit, and the
            # operand's syntax is never inspected.
            _reg = len(p.new_to_old)   # `n` is shadowed inside this emitter
            _sb_arg = _a_arg.selected_boundary
            if _sb_arg is None:
                raise TypeCheckError(
                    "Apply: the AppCut boundary needs the argument's "
                    "selected boundary, which was not recorded")
            _yank_B = canonical_frame(B, label="Y_B")
            if _yank_B.n_qubits != wB:
                raise TypeCheckError(
                    f"Apply: the canonical boundary of B is "
                    f"{_yank_B.n_qubits} qubits but the B interface is {wB} "
                    f"wide")
            def _head_bundle_wires(side, rec):
                """The ambient wires carrying the head's A-oB bundle.

                Two recorded sources for the SAME thing, in canonical bundle
                order, so `[wA:]` is the residual boundary either way:

                  * the head artifact's own placement, when it records one
                    shaped like the bundle (a variable head does);
                  * when the head is itself an application, the Y factor of
                    its recorded AppCut route -- which IS the residual
                    boundary of its result type, i.e. this bundle.

                Nothing else is consulted. A head that records neither is an
                unreached case and says so.
                """
                if len(rec) == wA + wB:
                    return tuple(rec)
                _sb_f = _a_fun.selected_boundary
                _ch = (None if _sb_f is None else
                       (_sb_f.ingress if side == "ingress" else _sb_f.egress))
                if (_ch is not None and _ch.space == "ambient"
                        and _ch.route is not None and _ch.route.reconstructible
                        and len(_ch.route.placements) == 2
                        and len(_ch.route.placements[1]) == wA + wB):
                    return tuple(_ch.route.placements[1])
                raise TypeCheckError(
                    f"Apply: the head's {side} bundle placement is not "
                    f"recorded -- its own placement names {len(rec)} wires "
                    f"for a {wA}+{wB} bundle, and it carries no AppCut route "
                    f"whose residual factor is that bundle. The residual "
                    f"boundary Y_B cannot be split off it")

            _head_in = _head_bundle_wires("ingress", _a_fun.ingress_wires)
            _head_out = _head_bundle_wires("egress", _a_fun.egress_wires)

            def _operand_factor(chart, wires, side):
                """The operand premise as ONE factor, on ONE polarity.

                A premise-local chart is placed at the argument artifact's
                own recorded placement for THIS polarity. A nested AppCut's
                chart is already AMBIENT, and is localised from its own
                recorded scatter schedule -- its support is the wires that
                schedule names, never "the whole register" and never the
                wires whose bits happen to vary.
                """
                if chart.space == "ambient":
                    nq, codes, w = localize_scatter(chart)
                    return nq, codes, w
                if len(wires) != chart.n_qubits:
                    raise TypeCheckError(
                        f"Apply: the operand's {side} chart is "
                        f"{chart.n_qubits} qubits but its recorded {side} "
                        f"placement names {len(wires)} wires {wires}")
                return chart.n_qubits, tuple(chart.codes), tuple(wires)

            def _appcut_side(label, arg_chart, arg_wires, head_wires, side):
                # Two NAMESPACED premises. S_y's addresses belong to the
                # argument artifact and Y_B's to the head; a local wire 0 in
                # each is two addresses, not a collision. Only the ambient
                # pullback can collide, and par_then_repart refuses it when
                # it does.
                _nq, _codes, _wires = _operand_factor(arg_chart, arg_wires,
                                                      side)
                head = ChartFactor(name="S_y", owner=_a_arg.cut_id,
                                   n_qubits=_nq, codes=_codes)
                tail = ChartFactor(name="Y_B", owner=_cut_ids[_cur_occ[0]],
                                   n_qubits=_yank_B.n_qubits,
                                   codes=tuple(_yank_B.codes))
                rep, places = scatter_repart(_wires, head_wires[wA:], _reg)
                ch = par_then_repart(head, tail, rep, _reg, label,
                                     placements=places, kind="scatter")
                ch.validate_joint()
                return ch

            _boundary_sink[_cur_occ[0]] = SelectedBoundary(
                ingress=_appcut_side("r_1^-", _sb_arg.ingress,
                                     _a_arg.ingress_wires,
                                     _head_in, "ingress"),
                egress=_appcut_side("r_1^+", _sb_arg.egress,
                                    _a_arg.egress_wires,
                                    _head_out, "egress"),
                origin="appcut")

            total_width = wA + wB
            if total_width > 0 and wB > 0:
                # Inverse rotation: [wA, wA+1, ..., wA+wB-1, 0, 1, ..., wA-1]
                # This puts B_slot (was at [wA..wA+wB)) back to [0..wB)
                local_perm = list(range(wA, total_width)) + list(range(wA))
                step = embed_local_perm(WirePerm(total_width, local_perm), offset)
                p = compose(step, p)
                if explain:
                    log.append(f"Apply: route B_slot to output, wA={wA}, wB={wB}")

            if explain:
                log.append(f"Apply: arg at offset {offset}, f at offset {offset}, result at [{offset}, {offset+wB})")
            return

        # Full source language: Var, Pair, LetPair
        if isinstance(t, Var):
            # Var: §4.1 — identity on ⟦A⟧, no gates.
            #
            # env stores lists of PHYSICAL wire positions (stable across perm changes).
            # Use inverse(p) to find each wire's CURRENT logical position,
            # then route to [offset..offset+w) if needed.
            if t.name in env:
                phys_list = env[t.name]
                var_width = len(phys_list)
                # A Var does not CONSUME the slot at `offset`; it BINDS a
                # context resource and routes it there. So its input boundary
                # arrives on the binder's wires, not on whatever the slot was
                # naming at entry. The emitter that knows this records it.
                _placement_sink[_cur_occ[0]] = tuple(phys_list)
                if var_width > 0:
                    inv_p = inverse(p)
                    curr_positions = [inv_p.new_to_old[ph] for ph in phys_list]
                    target = list(range(offset, offset + var_width))
                    if curr_positions != target:
                        step = _var_route_perm(curr_positions, offset)
                        p = compose(step, p)
                        if explain:
                            log.append(f"Var '{t.name}': route {curr_positions} -> [{offset},{offset+var_width})")
                    else:
                        if explain:
                            log.append(f"Var '{t.name}': identity at [{offset},{offset+var_width})")
                else:
                    if explain:
                        log.append(f"Var '{t.name}': zero-width, identity")
            else:
                if explain:
                    log.append(f"Var '{t.name}' (unbound): identity on {width(t.ty)} wires at offset {offset}")
            return

        if isinstance(t, Pair):
            # Tensor introduction: (fst, snd) : A ⊗ B
            # Compile fst and snd in parallel.
            # Use CODOMAIN width for offset: fst's output occupies
            # [offset..offset+w_cod_fst), snd starts after.
            # This is critical for Lam/Apply terms where cod_w != dom_w.
            #
            # Propagate is_value: if this Pair is a value (e.g. function argument),
            # its children are also values. This defers Lam body compilation.
            _, fst_cod = type_of(t.fst)
            fst_w = width(fst_cod)
            go(t.fst, offset, env, is_value=is_value)
            go(t.snd, offset + fst_w, env, is_value=is_value)
            if explain:
                log.append(f"Pair: fst at offset {offset}, snd at offset {offset + fst_w}")
            return

        if isinstance(t, LetPair):
            # LetPair: §4.3 — compile pair, bind x/y to output subranges, compile body.
            #
            # Always compile the pair (even if it's a Var — Var handles its own routing).
            # Bind x and y using PHYSICAL wire positions so env entries remain stable
            # across subsequent perm compositions.
            go(t.pair, offset, env)

            # After pair: output is at logical [offset..offset+wX+wY).
            # Store physical positions (full list) for perm-stable bindings.
            x_width = width(t.ty_x)
            y_width = width(t.ty_y)
            x_phys = [p.new_to_old[offset + i] for i in range(x_width)]
            y_phys = [p.new_to_old[offset + x_width + i] for i in range(y_width)]
            new_env = {**env, t.x: x_phys, t.y: y_phys}

            # Propagate term_env: if the pair's term is a known Pair,
            # bind x and y to its components for later β-reduction.
            pair_term = _resolve_term(t.pair, term_env)
            if isinstance(pair_term, Pair):
                term_env[t.x] = pair_term.fst
                term_env[t.y] = pair_term.snd

            go(t.body, offset, new_env)
            # LetPair has NO selected-boundary rule yet. Copying the body's
            # boundary up whenever it happened to be ambient would be an
            # unearned general claim about tensor elimination: LetPair's own
            # ingress is the PAIR, not the body's input, and the rule that
            # relates them is TenPack, which is a later phase. So this stays
            # on the explicit frame default and says why. Part H reads the
            # AppCut occurrence's own artifact instead.
            _boundary_sink[_cur_occ[0]] = "letpair:frame-default(TenPack pending)"
            if explain:
                log.append(f"LetPair: {t.x} phys={x_phys}, "
                          f"{t.y} phys={y_phys}, body at offset {offset}")
            return

        raise TypeError(f"Unknown term node: {t!r}")

    go(term, env=env if env else {})

    _pre_swap = tuple(p.new_to_old)
    if materialize:
        swaps = swaps_for_perm(p)
        apply_swaps(circ, swaps)
        if explain:
            log.append(f"Materialize swaps={swaps}")
        p = identity(n)

    # Materialising appends a swap network AFTER every occurrence has been
    # emitted, so it moves the egress of every boundary already placed in the
    # register -- and nothing else, since the ingress is read before the
    # circuit runs. Every artifact is re-expressed in the FINAL circuit's
    # coordinates here, so no consumer has to know the transport existed.
    if materialize and list(_pre_swap) != list(range(n)):
        _moved = []
        for _a in artifacts:
            _sb_a = _a.selected_boundary
            if _sb_a is not None and _sb_a.egress.space == "ambient":
                _a = _dc_replace(
                    _a, selected_boundary=_sb_a.transport_egress(_pre_swap))
            _moved.append(_a)
        artifacts = _moved
        frame_registry = {a.occurrence: a for a in artifacts}

    if _artifact_sink is not None:
        _artifact_sink["artifacts"] = artifacts
    _root = frame_registry.get(0)
    if _root is None:
        raise TypeCheckError(
            f"no boundary frames recorded for {type(term).__name__}: every "
            f"emitter must record the frames it selected (frames are "
            f"required, never reconstructed downstream)")
    _fin, _fout = _root.input_frame, _root.output_frame

    # Higher-order terms carry function-layout wires (Lam/Apply boundary
    # slots, Cup/Cap) whose exact count emission determines rather than
    # _internal_width predicting it. The CATEGORY is declared here -- these
    # coordinates are function layout, recorded as such -- so a first-order
    # term whose register drifts still trips W below.
    if _has_spectator_coordinates(term):
        if _fin.n_qubits < n:
            _fin = with_spectators(_fin, n, residual_name="fn_layout",
                                   role="residual")
        if _fout.n_qubits < n:
            _fout = with_spectators(_fout, n, residual_name="fn_layout",
                                    role="residual")

    # A sub-compile given an `env` works inside a larger PARENT register; the
    # extra coordinates are the outer context, which is explainable and so is
    # recorded as a context port. This is not the unconditional boundary
    # widening that made W tautological: it fires only when an env was
    # actually supplied, so an unexplained allocation at top level still trips.
    if env and (_fin.n_qubits < n or _fout.n_qubits < n):
        if _fin.n_qubits < n:
            _fin = with_spectators(_fin, n, residual_name="context",
                                   role="context")
        if _fout.n_qubits < n:
            _fout = with_spectators(_fout, n, residual_name="context",
                                    role="context")
    # Frame.ports is the single authoritative location; Compiled's fields
    # mirror it rather than being a second, independently-filled copy.
    _pin, _pout = _fin.ports, _fout.ports

    # A PENDING permutation is semantics, not bookkeeping: without it the
    # frames claim identity while the artifact permutes. Under
    # materialize=True the swaps were emitted and p is the identity, so both
    # modes end up truthful.
    _pl = list(p.new_to_old)
    if _pl != list(range(len(_pl))) and len(_pl) == _fout.n_qubits:
        # The INVERSE: new_to_old says which old wire each new wire reads, so
        # transporting a frame forward through the pending permutation uses
        # the inverse map. A symmetric perm (SWAP) hides the difference, which
        # is why TwistTen(Q,Q) passed while TwistTen(Q,Z3) did not.
        _inv = [0] * len(_pl)
        for _j, _o in enumerate(_pl):
            _inv[_o] = _j
        _fout = apply_wire_perm(_fout, _inv)
    # ---- Invariant W (docs/COMPILER_INVARIANTS.md) --------------------------
    # Strictly  q = F_in.n = F_out.n, checked against the FINAL frames (after
    # any declared spectator/context selection), not against the values
    # recorded before emission -- otherwise the check never sees them.
    if not (n == _fin.n_qubits == _fout.n_qubits):
        raise TypeCheckError(
            f"Invariant W violated: register is {n} qubits but the selected "
            f"frames are {_fin.n_qubits} (in) and {_fout.n_qubits} (out) for "
            f"{type(term).__name__}. Either the allocator drifted or the "
            f"emitter's selection is wrong; spectators must be selected "
            f"explicitly (docs/COMPILER_INVARIANTS.md).")

    # The compilation's selected boundary is the ROOT occurrence's, already
    # resolved. A boundary placed in the register survives as it is, except
    # that materialising appends a swap network AFTER the emission, which
    # moves the egress and nothing else. A boundary that defaulted is rebuilt
    # from the FINAL root frames, so it agrees with input_frame/output_frame
    # after the spectator, context and pending-permutation steps above.
    _sel = _root.selected_boundary
    if _sel is not None and _sel.egress.space == "ambient":
        pass          # already in the final circuit's coordinates above
    else:
        _sel = SelectedBoundary.from_frames(
            _fin, _fout,
            origin=(_sel.origin if _sel is not None else "frame-default"),
            space="ambient")
    return Compiled(circuit=circ, perm=p, log=(log if explain else None),
                    input_frame=_fin, output_frame=_fout,
                    input_ports=_pin, output_ports=_pout,
                    global_phase=float(circ.phase),
                    selected_boundary=_sel)


