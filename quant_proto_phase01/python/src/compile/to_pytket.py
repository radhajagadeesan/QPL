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
)
from lang.types import width, Arrow, Unit

# Type alias for compilation environment
# Maps variable names to (start, width) wire ranges in the logical layout
Env = dict[str, tuple[int, int]]
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


@dataclass(frozen=True, slots=True)
class Compiled:
    circuit: Circuit
    perm: WirePerm
    log: Optional[List[str]] = None


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

    if isinstance(t, NPlusMap):
        # n-ary outer dispatch: parent encoding is k_outer + max(payload).
        # When summands are sums themselves, this differs from the flat
        # encoding's width (which would use ceil(log_2(flat_leaves))).
        import math
        n_branches = len(t.summand_types)
        k_outer = math.ceil(math.log2(n_branches)) if n_branches > 1 else 0
        max_payload = max(type_width(st) for st in t.summand_types)
        branch_internal = max(_internal_width(br) for br in t.branches)
        return max(k_outer + max_payload, k_outer + branch_internal)

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


def compile(term: Term, *, materialize: bool = False, explain: bool = False, env: Env = None) -> Compiled:
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

    dom, cod = type_of(term)

    # For terms with encode/decode, we always need 2 wires (Q=1, I+I=2).
    # Even if roundtrip Q→Q has width 1, internally we need 2 wires.
    if _contains_encode_decode(term):
        n = 2  # encode/decode always operate on 2 wires
    else:
        # Compute internal width needed for higher-order terms
        n = _internal_width(term)
        n_dom = width(dom)
        n_cod = width(cod)
        # Ensure we have at least max(dom, cod) wires
        n = max(n, n_dom, n_cod)
        # When env is supplied (sub-compile of open PlusMap branches), it may
        # reference physical wire positions beyond the term's declared width.
        # Make sure the circuit is large enough.
        if env:
            for phys_list in env.values():
                for phys in phys_list:
                    if phys + 1 > n:
                        n = phys + 1

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

    def go(t: Term, offset: int = 0, env: Env = None, *, is_value: bool = False) -> None:
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
            go(t.f, offset, env)
            go(t.g, offset, env)
            return

        # TenTerm: parallel composition with offset semantics (Phase 2)
        if isinstance(t, TenTerm):
            # Get the type of the left branch to compute right branch offset
            left_dom, _ = type_of(t.f)
            left_width = width(left_dom)
            # Compile left branch first (spec: left-then-right order)
            go(t.f, offset, env)
            # Compile right branch with additional offset
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
            tagged = dist_L_perm(t.a, t.b, t.c)
            apply_tagged_perm(tagged, offset)
            if explain:
                log.append(f"DistL perm={tagged.perm.new_to_old} (identity)")
            return
        if isinstance(t, DistR):
            tagged = dist_R_perm(t.a, t.b, t.c)
            apply_tagged_perm(tagged, offset)
            if explain:
                log.append(f"DistR perm={tagged.perm.new_to_old} (tag moves to front)")
            return

        # Inverse distributivity: now supported with tagged layout
        if isinstance(t, UndistL):
            tagged = undist_L_perm(t.a, t.b, t.c)
            apply_tagged_perm(tagged, offset)
            if explain:
                log.append(f"UndistL perm={tagged.perm.new_to_old} (identity)")
            return
        if isinstance(t, UndistR):
            tagged = undist_R_perm(t.a, t.b, t.c)
            apply_tagged_perm(tagged, offset)
            if explain:
                log.append(f"UndistR perm={tagged.perm.new_to_old} (tag moves back)")
            return

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
                sub = compile(body, materialize=True)
                sub_cmds = _get_sub_cmds(sub.circuit)
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

            # If U ≈ I, then exp(iθ·I) = e^{iθ}·I (global phase) — skip
            if np.allclose(U, np.eye(body_n), atol=1e-9):
                if explain:
                    log.append(f"ExpInvolution theta={t.theta} body=I (global phase, skipped)")
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

            # Auto-flatten nested PlusMap to NPlusMap when possible
            if isinstance(t.ty_left, Plus) or isinstance(t.ty_right, Plus):
                flat = _try_flatten_plusmap(t)
                if flat is not None:
                    # Delegate to NPlusMap compilation
                    go(flat, offset, env)
                    return
                # Fall through to Strategy A for opaque branches

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

            if ctx_left_w > 0 or ctx_right_w > 0:
                # Open branches: compile with parent env for free variable routing
                tag_phys = p.apply_new_to_old(offset)
                payload_base = offset + max(k, 1)

                for branch, pw, ctx_w, anti in [
                    (t.left, payload_left_w, ctx_left_w, True),
                    (t.right, payload_right_w, ctx_right_w, False),
                ]:
                    if pw + ctx_w == 0:
                        continue

                    if ctx_w > 0:
                        # Open branch: compile with env for free variables
                        fv = _ordered_free_vars(branch)
                        sub_env = {}
                        ctx_pos = pw
                        for name, ty_fv in fv:
                            w_fv = width(ty_fv)
                            sub_env[name] = list(range(ctx_pos, ctx_pos + w_fv))
                            ctx_pos += w_fv

                        # Substitute deferred Lam values for free vars (deferred Apply).
                        # If a free var's parent physical wires are registered in
                        # deferred_fns, replace Var(name) with the deferred Lam term so
                        # the sub-compile β-reduces Apply(Var, ...) into concrete gates.
                        branch_to_compile = branch
                        if deferred_fns:
                            for name, ty_fv in fv:
                                if name in env:
                                    key = tuple(env[name])
                                    if key in deferred_fns:
                                        branch_to_compile = _substitute(
                                            branch_to_compile, name, deferred_fns[key])
                            branch_to_compile = _normalize(branch_to_compile)

                        branch_result = compile(branch_to_compile, materialize=True, env=sub_env)
                        cmds = _get_sub_cmds(branch_result.circuit)

                        if not cmds:
                            continue

                        # Map free vars to parent physical positions
                        ctx_parent_phys = []
                        for name, ty_fv in fv:
                            if name in env:
                                ctx_parent_phys.extend(env[name])

                        def make_open_wire_map(_pw=pw, _pb=payload_base,
                                               _cpp=list(ctx_parent_phys)):
                            def wm(w):
                                if w < _pw:
                                    return p.apply_new_to_old(w + _pb)
                                else:
                                    return _cpp[w - _pw]
                            return wm

                        _emit_controlled_branch(tag_phys, cmds,
                                                make_open_wire_map(), anti=anti)
                    else:
                        # Closed branch: compile without env
                        cmds = (_get_sub_cmds(
                            compile(branch, materialize=True).circuit)
                            if pw > 0 else [])
                        if not cmds:
                            continue
                        def make_closed_wire_map(_pb=payload_base):
                            def wm(w):
                                return p.apply_new_to_old(w + _pb)
                            return wm
                        _emit_controlled_branch(tag_phys, cmds,
                                                make_closed_wire_map(), anti=anti)

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
                if branch_w == 0:
                    return []
                if deferred_fns:
                    # Get parent physical wires for this branch's payload
                    parent_phys = [p.apply_new_to_old(payload_base_off + i)
                                   for i in range(branch_w)]
                    # Get the branch's domain type for reconstruction
                    br_dom, _ = type_of(branch)
                    input_val = _reconstruct_value(parent_phys, br_dom, deferred_fns)
                    if input_val is not None and not isinstance(input_val, Id):
                        modified = _inject_input_value(branch, input_val)
                        modified = _normalize(modified)
                        return _get_sub_cmds(compile(modified, materialize=True).circuit)
                return _get_sub_cmds(compile(branch, materialize=True).circuit)

            payload_base_for_branches = offset + max(k, 1)
            left_cmds = _compile_branch_with_deferred(t.left, left_w, payload_base_for_branches)
            right_cmds = _compile_branch_with_deferred(t.right, right_w, payload_base_for_branches)

            if k <= 1:
                # Simple binary case: 1 outer tag bit
                tag_phys = p.apply_new_to_old(offset)
                payload_base = offset + max(k, 1)

                wire_map = lambda w: p.apply_new_to_old(w + payload_base)
                if left_cmds:
                    _emit_controlled_branch(tag_phys, left_cmds, wire_map, anti=True)
                if right_cmds:
                    _emit_controlled_branch(tag_phys, right_cmds, wire_map)

                if explain:
                    log.append(f"PlusMap(k=1): {len(left_cmds)} left gates (anti-ctrl), "
                               f"{len(right_cmds)} right gates (ctrl) at offset {offset}")
                return

            # k >= 2: Strategy A — tag permutation sandwich
            # (fallback for opaque branches that can't be auto-flattened)
            half = 2 ** (k - 1)

            if n_left > half or n_right > half:
                # Strategy B: full unitary synthesis for asymmetric splits
                import numpy as np
                pw = payload_width(Plus(t.ty_left, t.ty_right))
                w = k + pw
                dim_pw = 2 ** pw

                U_f = compile(t.left, materialize=True).circuit.get_unitary()
                U_g = compile(t.right, materialize=True).circuit.get_unitary()
                dim = 2 ** w

                # Helper: copy n_blocks × n_blocks of size dim_pw blocks from U_src
                # starting at block (0, 0) into U_dst starting at block (off, off).
                # This copies the FULL used-states sub-block (including off-diagonal
                # entries that carry cross-summand permutations).
                def _splat(U_dst, U_src, n_blocks, off, dim_pw):
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
                    # Zero out right-summand rows/cols, then splat U_g block.
                    for tr in range(n_right):
                        tf = n_left + tr
                        rs, re = tf * dim_pw, (tf + 1) * dim_pw
                        U_full[rs:re, :] = 0
                        U_full[:, rs:re] = 0
                    if w_g == 0:
                        for tr in range(n_right):
                            tf = n_left + tr
                            rs, re = tf * dim_pw, (tf + 1) * dim_pw
                            U_full[rs:re, rs:re] = np.eye(dim_pw)
                    else:
                        _splat(U_full, U_g, n_right, n_left, dim_pw)
                else:
                    U_full = np.eye(dim, dtype=complex)
                    w_f = width(type_of(t.left)[0])
                    if w_f == 0:
                        for tl in range(n_left):
                            rs, re = tl * dim_pw, (tl + 1) * dim_pw
                            U_full[rs:re, rs:re] = np.eye(dim_pw)
                    else:
                        _splat(U_full, U_f, n_left, 0, dim_pw)
                    _splat(U_full, U_g, n_right, n_left, dim_pw)

                phys = [p.apply_new_to_old(offset + i) for i in range(w)]
                # Check if U_full is a permutation matrix (each row & col has
                # exactly one 1, all others 0). Common when summand payloads
                # are width 0 (e.g., Z_n shifts).
                def _is_perm_matrix(U):
                    if U.shape[0] != U.shape[1]:
                        return False
                    n = U.shape[0]
                    if not np.allclose(np.abs(U), np.eye(n)[np.argmax(np.abs(U), axis=0)].T,
                                       atol=1e-10):
                        # Fallback: check each row has one entry of magnitude 1 and rest 0
                        for r in range(n):
                            row = U[r]
                            mags = np.abs(row)
                            if not (np.sum(mags > 0.5) == 1 and np.allclose(mags[mags <= 0.5], 0)):
                                return False
                        for c in range(n):
                            col = U[:, c]
                            mags = np.abs(col)
                            if not (np.sum(mags > 0.5) == 1 and np.allclose(mags[mags <= 0.5], 0)):
                                return False
                    # Also require all non-zero entries to be 1 (real, no phase).
                    for r in range(n):
                        for c in range(n):
                            if np.abs(U[r, c]) > 0.5:
                                if not np.allclose(U[r, c], 1.0, atol=1e-10):
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
                    raise NotImplementedError(
                        f"PlusMap full non-permutation unitary for width "
                        f"{w} > 3 not yet supported")

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
                right_wm = lambda w, stw=tw_right: p.apply_new_to_old(
                    _sub_wire_to_full(w, stw, offset, k))
                n_extra_right = k - 1 - tw_right
                extras_right = [p.apply_new_to_old(offset + 1 + i)
                                for i in range(n_extra_right)] if n_extra_right > 0 else None
                _emit_controlled_branch(msb_phys, right_cmds, right_wm,
                                        extra_anti_qubits=extras_right)

            # Step 3: Emit P⁻¹ if non-identity
            if not is_identity_P:
                P_inv = [0] * dim
                for i in range(dim):
                    P_inv[P_tup[i]] = i
                _emit_tag_perm_unitary(circ, p, tuple(P_inv), k, offset, explain, log)

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
        if isinstance(t, NPlusMap):
            from lang.types import (Plus, flatten_plus, tag_width as tw_fn,
                                    payload_width, build_plus_tree)
            import math

            n_branches = len(t.summand_types)
            assert n_branches >= 2
            # Tag width is computed from number of branches (outer n-ary dispatch),
            # NOT from a flattened sum_ty. Each summand type may itself be a sum,
            # in which case its tag bits live inside the per-summand payload.
            k = math.ceil(math.log2(n_branches)) if n_branches > 1 else 0
            pw = max(width(st) for st in t.summand_types)

            tag_phys = [p.apply_new_to_old(offset + j) for j in range(k)]
            payload_base = offset + k

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

                    sub = compile(branch_to_compile, materialize=True, env=sub_env)
                    sub_cmds = _get_sub_cmds(sub.circuit)

                    if not sub_cmds:
                        continue

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
                    # Closed branch (or no relevant free vars in scope).
                    sub = compile(br, materialize=True)
                    sub_cmds = _get_sub_cmds(sub.circuit)

                    if not sub_cmds:
                        continue

                    def make_wire_map(pb=payload_base):
                        def wire_map(w):
                            return p.apply_new_to_old(pb + w)
                        return wire_map

                    _emit_nway_controlled(circ, tag_phys, i, sub_cmds,
                                          make_wire_map())

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

            # Compile branches to sub-circuits
            left_dom, _ = type_of(t.left)
            left_w = width(left_dom)
            left_cmds = _get_sub_cmds(compile(t.left, materialize=True).circuit) if left_w > 0 else []

            right_dom, _ = type_of(t.right)
            right_w = width(right_dom)
            right_cmds = _get_sub_cmds(compile(t.right, materialize=True).circuit) if right_w > 0 else []

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

                if explain:
                    log.append(f"PhasedPlusMap(k=1, θ={theta:.4f}): {len(left_cmds)} left, "
                               f"{len(right_cmds)} right at offset {offset}")
                return

            # k >= 2: Strategy A — tag permutation sandwich
            half = 2 ** (k - 1)

            if n_left > half or n_right > half:
                # Strategy B: full unitary synthesis (same as PlusMap, plus phase)
                import numpy as np
                pw = payload_width(Plus(t.ty_left, t.ty_right))
                w = k + pw
                dim_pw = 2 ** pw

                U_f = compile(t.left, materialize=True).circuit.get_unitary()
                U_g = compile(t.right, materialize=True).circuit.get_unitary()
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
                            U_full[rs:re, rs:re] = np.eye(dim_pw)
                    else:
                        _splat_phased(U_full, U_g, n_right, n_left, dim_pw)
                else:
                    U_full = np.eye(dim, dtype=complex)
                    w_f = width(type_of(t.left)[0])
                    if w_f == 0:
                        for tl in range(n_left):
                            rs, re = tl * dim_pw, (tl + 1) * dim_pw
                            U_full[rs:re, rs:re] = np.eye(dim_pw)
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
                left_wm = lambda w, stw=tw_left: p.apply_new_to_old(
                    _sub_wire_to_full(w, stw, offset, k))
                _emit_controlled_branch(msb_phys, left_cmds, left_wm, anti=True)
            if right_cmds:
                right_wm = lambda w, stw=tw_right: p.apply_new_to_old(
                    _sub_wire_to_full(w, stw, offset, k))
                _emit_controlled_branch(msb_phys, right_cmds, right_wm)

            # Step 3: Emit P⁻¹
            if not is_identity_P:
                P_inv = [0] * dim
                for i in range(dim):
                    P_inv[P_tup[i]] = i
                _emit_tag_perm_unitary(circ, p, tuple(P_inv), k, offset, explain, log)

            # Phase application on left branch (tag ∈ left_set)
            sum_ty = Plus(t.ty_left, t.ty_right)
            total_tag_bits = tw_fn(sum_ty)
            half_turns = theta / math.pi
            tag_qubits = [p.apply_new_to_old(offset + i) for i in range(total_tag_bits)]

            for tq in tag_qubits:
                circ.X(tq)
            if total_tag_bits == 1:
                circ.add_gate(OpType.U1, [half_turns], [tag_qubits[0]])
            elif total_tag_bits == 2:
                circ.add_gate(OpType.CU1, [half_turns], [tag_qubits[0], tag_qubits[1]])
            else:
                # k >= 3: multi-controlled U1 via QControlBox
                from pytket.circuit import QControlBox, Op
                base_op = Op.create(OpType.U1, [half_turns])
                qcb = QControlBox(base_op, total_tag_bits - 1)
                circ.add_qcontrolbox(qcb, tag_qubits)
            for tq in reversed(tag_qubits):
                circ.X(tq)

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

            # For each branch i, apply phase e^{iθᵢ} when tag = i
            # Tag i has binary representation, we apply X to bits that are 0,
            # then multi-controlled U1, then X to restore.
            for branch_idx in range(arity):
                theta_ht = half_turns[branch_idx]

                # Skip if phase is effectively 1 (theta ≈ 0 mod 2π)
                if abs(theta_ht) < 1e-10 or abs(abs(theta_ht) - 2.0) < 1e-10:
                    continue

                # Get the tag qubits
                tag_qubits = [p.apply_new_to_old(offset + i) for i in range(n_tag_bits)]

                # Determine which bits need X gates (bits that are 0 in branch_idx)
                bits_to_flip = []
                for bit_pos in range(n_tag_bits):
                    if (branch_idx >> bit_pos) & 1 == 0:
                        bits_to_flip.append(bit_pos)

                # Apply X to flip the 0-bits to 1
                for bit_pos in bits_to_flip:
                    circ.X(tag_qubits[bit_pos])

                # Apply multi-controlled U1 (all tag bits should now be 1)
                if n_tag_bits == 1:
                    circ.add_gate(OpType.U1, [theta_ht], [tag_qubits[0]])
                elif n_tag_bits == 2:
                    circ.add_gate(OpType.CU1, [theta_ht], [tag_qubits[0], tag_qubits[1]])
                else:
                    # k >= 3: multi-controlled U1 via QControlBox
                    from pytket.circuit import QControlBox, Op
                    base_op = Op.create(OpType.U1, [theta_ht])
                    qcb = QControlBox(base_op, n_tag_bits - 1)
                    circ.add_qcontrolbox(qcb, tag_qubits)

                # Apply X to restore the 0-bits
                for bit_pos in reversed(bits_to_flip):
                    circ.X(tag_qubits[bit_pos])

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
                if explain:
                    log.append(f"Apply (β-reduce '{lam.name}'): arg;body, x phys={x_phys}")
                return

            # General case: full boundary splicing with function layout
            # 1. Compile arg at offset - fills A_slot wires
            # 2. Compile f at offset - f's body operates on A_slot, B_slot is result
            # 3. Result is on B_slot: [offset+wA..offset+wA+wB)

            # Compile arg first - produces A on wires [offset..offset+wA)
            # This fills the A_slot that f will read from
            go(t.arg, offset, env)

            # Compile f - operates on wires [offset..offset+wA+wB)
            # f's A_slot is [offset..offset+wA), B_slot is [offset+wA..offset+wA+wB)
            # For Lam, the body+swap makes B_slot contain the result
            go(t.f, offset, env)

            # After f: result is on B_slot [offset+wA..offset+wA+wB)
            # But Apply's output type is B (width wB), so we need to
            # route B_slot to [offset..offset+wB)
            #
            # This is the inverse of Lam's routing.
            # Lam did: rotate left by wB (body output [0..wB) → [wA..wA+wB))
            # Apply undoes: rotate right by wB (B_slot [wA..wA+wB) → [0..wB))
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
            if explain:
                log.append(f"LetPair: {t.x} phys={x_phys}, "
                          f"{t.y} phys={y_phys}, body at offset {offset}")
            return

        raise TypeError(f"Unknown term node: {t!r}")

    go(term, env=env if env else {})

    if materialize:
        swaps = swaps_for_perm(p)
        apply_swaps(circ, swaps)
        if explain:
            log.append(f"Materialize swaps={swaps}")
        p = identity(n)

    return Compiled(circuit=circ, perm=p, log=(log if explain else None))


