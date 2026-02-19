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
    WirePerm, identity, compose,
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


def _compile_structural_to_perm(t: Term) -> WirePerm:
    """Compile a purely structural term to its wire permutation.

    This is used by ExpInvolution to extract the permutation from its body.
    The body must be purely structural (no gates).

    Returns:
        The wire permutation induced by the structural term.

    Raises:
        TypeCheckError: If the term contains non-structural elements (gates).
    """
    from lang.types import width as type_width, Plus, flatten_plus
    dom, _ = type_of(t)
    n = type_width(dom)
    p = identity(n)

    def embed_local_perm(local_perm: WirePerm, offset: int) -> WirePerm:
        local_width = local_perm.n
        global_perm = list(range(n))
        for i in range(local_width):
            global_perm[offset + i] = offset + local_perm.new_to_old[i]
        return WirePerm(n, global_perm)

    def go(term: Term, offset: int = 0) -> None:
        nonlocal p
        if isinstance(term, Id):
            return

        if isinstance(term, Seq):
            go(term.f, offset)
            go(term.g, offset)
            return

        if isinstance(term, TenTerm):
            left_dom, _ = type_of(term.f)
            left_width = type_width(left_dom)
            go(term.f, offset)
            go(term.g, offset + left_width)
            return

        if isinstance(term, TwistTen):
            local_step = twist_tensor_perm(term.a, term.b)
            step = embed_local_perm(local_step, offset)
            p = compose(step, p)
            return

        if isinstance(term, AssocTenL):
            local_step = assoc_tensor_L_perm(term.a, term.b, term.c)
            step = embed_local_perm(local_step, offset)
            p = compose(step, p)
            return

        if isinstance(term, AssocTenR):
            local_step = assoc_tensor_R_perm(term.a, term.b, term.c)
            step = embed_local_perm(local_step, offset)
            p = compose(step, p)
            return

        if isinstance(term, TwistPlus):
            tagged = twist_plus_perm(term.a, term.b)
            # With one-hot encoding, tag_flips should be empty
            step = embed_local_perm(tagged.perm, offset)
            p = compose(step, p)
            return

        if isinstance(term, AssocPlusL):
            tagged = assoc_plus_L_perm(term.a, term.b, term.c)
            step = embed_local_perm(tagged.perm, offset)
            p = compose(step, p)
            return

        if isinstance(term, AssocPlusR):
            tagged = assoc_plus_R_perm(term.a, term.b, term.c)
            step = embed_local_perm(tagged.perm, offset)
            p = compose(step, p)
            return

        if isinstance(term, DistL):
            tagged = dist_L_perm(term.a, term.b, term.c)
            step = embed_local_perm(tagged.perm, offset)
            p = compose(step, p)
            return

        if isinstance(term, DistR):
            tagged = dist_R_perm(term.a, term.b, term.c)
            step = embed_local_perm(tagged.perm, offset)
            p = compose(step, p)
            return

        if isinstance(term, UndistL):
            tagged = undist_L_perm(term.a, term.b, term.c)
            step = embed_local_perm(tagged.perm, offset)
            p = compose(step, p)
            return

        if isinstance(term, UndistR):
            tagged = undist_R_perm(term.a, term.b, term.c)
            step = embed_local_perm(tagged.perm, offset)
            p = compose(step, p)
            return

        # ExpInvolution body should not contain gates
        raise TypeCheckError(
            f"ExpInvolution body must be purely structural, "
            f"but contains non-structural term: {type(term).__name__}"
        )

    go(t)
    return p


def _internal_width(t: Term) -> int:
    """Compute internal wire width needed for a term.

    For most terms, this is max(width(dom), width(cod)).
    For higher-order terms (Lam, Apply), we need extra wires for the function layout.
    """
    from lang.types import width as type_width

    if isinstance(t, Lam):
        # Lam needs width(A) + width(B) for the function layout [A_slot | B_slot]
        wA = type_width(t.dom)
        wB = type_width(t.cod)
        body_internal = _internal_width(t.body)
        return max(wA + wB, body_internal)

    if isinstance(t, Apply):
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

    # Default: use type widths
    dom, cod = type_of(t)
    return max(type_width(dom), type_width(cod))


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
        raise NotImplementedError(
            f"tag_perm on {k} tag qubits (> 3) not yet supported")

    if explain:
        log.append(f"TagPerm {tag_perm} on {k} qubits, phys={tag_phys}")


def _decompose_and_get_cmds(circuit):
    """Decompose box types (Unitary2qBox etc.) to primitives, return commands.

    Inner PlusMap compilations with Strategy A emit Unitary2qBox for tag
    permutations. When these sub-circuits are used as branches of an outer
    Case/PlusMap, the outer needs to control each gate. Op.create() fails
    on box types, so we decompose first.
    """
    from pytket.passes import DecomposeBoxes
    DecomposeBoxes().apply(circuit)
    return list(circuit.get_commands())


def _emit_nway_controlled(circ, tag_qubits, branch_idx, sub_cmds, wire_map_fn):
    """Emit multi-controlled gates for a single branch of NPlusMap.

    For branch index `i` with `k` tag qubits (big-endian):
    1. X-flip: For each tag qubit j where bit (i >> (k-1-j)) & 1 == 0, apply X
    2. Multi-controlled gates: All k tag qubits are now 1 for branch i
    3. X-unflip: Undo the X gates from step 1
    """
    from pytket.circuit import QControlBox, Op
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
        else:
            base_op = Op.create(cmd.op.type, cmd.op.params)
            qcb = QControlBox(base_op, k)
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
    Full layout (big-endian): [MSB | inner_tag₀..inner_tag_{k-2} | payload₀..]
    MSB is at offset (the control qubit).
    Inner tag bits are at offset+1..offset+k-1.
    Payload starts at offset+k.
    """
    if sub_wire < sub_tw:
        return offset + 1 + sub_wire  # inner tag bits (after MSB)
    else:
        return offset + k + (sub_wire - sub_tw)  # payload


def compile(term: Term, *, materialize: bool = False, explain: bool = False, env: Env = None) -> Compiled:
    # Check for Feedback - not currently supported
    if _contains_feedback(term):
        raise NotImplementedError(
            "Feedback terms are not currently supported. "
            "The Feedback constructor exists for future use but has no compilation path."
        )

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

    circ = Circuit(n)
    p = identity(n)
    # Track pending tag flips (X gates to emit after permutation tracking)
    pending_tag_flips: List[int] = []
    log: List[str] = []

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

    def _emit_controlled_branch(ctrl_q, sub_cmds, wire_map_fn, anti=False):
        """Emit each gate controlled on ctrl_q, with wires mapped by wire_map_fn.

        Args:
            ctrl_q: Physical qubit for control
            sub_cmds: Commands from the sub-circuit
            wire_map_fn: Function mapping sub-circuit wire index to physical qubit
            anti: If True, wrap with X gates for anti-control
        """
        from pytket.circuit import QControlBox, Op
        if anti:
            circ.X(ctrl_q)
        for cmd in sub_cmds:
            phys_qubits = [wire_map_fn(q.index[0]) for q in cmd.qubits]
            ctrl_op = _CTRL_GATE_MAP.get(cmd.op.type)
            if ctrl_op is not None:
                circ.add_gate(ctrl_op, cmd.op.params, [ctrl_q] + phys_qubits)
            else:
                base_op = Op.create(cmd.op.type, cmd.op.params)
                qcb = QControlBox(base_op, 1)
                circ.add_qcontrolbox(qcb, [ctrl_q] + phys_qubits)
        if anti:
            circ.X(ctrl_q)

    def go(t: Term, offset: int = 0, env: Env = None) -> None:
        """Compile term t at given wire offset with variable environment.

        Args:
            t: The term to compile
            offset: Wire offset for this term within the circuit
            env: Environment mapping variable names to (start, width) wire ranges
        """
        if env is None:
            env = {}
        nonlocal p
        if isinstance(t, Id):
            if explain:
                log.append(f"Id (offset={offset})")
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

                # Inductive: Ctrl(PlusMap/Case/...) — compile body, decompose, control each gate
                if isinstance(body, (PlusMap, Case, CaseExpr, NPlusMap, PhasedPlusMap, PhasedControl)):
                    from pytket.circuit import QControlBox, Op
                    sub = compile(body, materialize=True)
                    sub_cmds = _decompose_and_get_cmds(sub.circuit)
                    for cmd in sub_cmds:
                        phys_qubits = [p.apply_new_to_old(q.index[0] + pay_off)
                                       for q in cmd.qubits]
                        ctrl_phys = [p.apply_new_to_old(c) for c in ctrls]
                        ctrl_op = _CTRL_GATE_MAP.get(cmd.op.type) if n_ctrls == 1 else None
                        if ctrl_op is not None:
                            circ.add_gate(ctrl_op, cmd.op.params,
                                          ctrl_phys + phys_qubits)
                        else:
                            base_op = Op.create(cmd.op.type, cmd.op.params)
                            qcb = QControlBox(base_op, n_ctrls)
                            circ.add_qcontrolbox(qcb, ctrl_phys + phys_qubits)
                    return

                # Fallback: unsupported multi-controlled gate
                raise NotImplementedError(
                    f"Multi-controlled ({n_ctrls} controls) not implemented for: {type(body).__name__}. "
                    f"Only X (CCX/Toffoli) is supported for 2 controls. "
                    f"Use structural decomposition or primitive gates."
                )

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
            # Compile the body as a structural term to get its permutation
            # We need to compile only the structural part, not gates
            body_perm = _compile_structural_to_perm(t.body)

            # Verify it's an involution
            if not is_involution(body_perm):
                raise TypeCheckError(
                    f"ExpInvolution body must compile to an involutive permutation, "
                    f"but got perm with π² ≠ id"
                )

            # Decompose into disjoint transpositions
            swaps = decompose_involution(body_perm)

            # Emit ExpSwap for each transposition
            for (a, b) in swaps:
                emit_ExpSwap(t.theta, a, b, offset)

            if explain:
                log.append(f"ExpInvolution theta={t.theta} body_perm={body_perm.new_to_old} swaps={swaps}")
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

        # CaseExpr: pattern-matching case with variable binding
        # Compile scrutinee, then dispatch branches using _emit_controlled_branch.
        if isinstance(t, CaseExpr):
            go(t.scrut, offset, env)

            tag_phys = p.apply_new_to_old(offset)
            payload_base = offset + 1

            left_env = {**env, t.x: (0, width(t.ty_x))}
            left_w = width(type_of(t.left)[0])
            left_cmds = _decompose_and_get_cmds(compile(t.left, materialize=True, env=left_env).circuit) if left_w > 0 else []

            right_env = {**env, t.y: (0, width(t.ty_y))}
            right_w = width(type_of(t.right)[0])
            right_cmds = _decompose_and_get_cmds(compile(t.right, materialize=True, env=right_env).circuit) if right_w > 0 else []

            wire_map = lambda w: p.apply_new_to_old(w + payload_base)
            if left_cmds:
                _emit_controlled_branch(tag_phys, left_cmds, wire_map, anti=True)
            if right_cmds:
                _emit_controlled_branch(tag_phys, right_cmds, wire_map)

            if explain:
                log.append(f"CaseExpr: scrut compiled, {t.x} bound at [{payload_base},{payload_base+width(t.ty_x)}), "
                           f"{t.y} bound at [{payload_base},{payload_base+width(t.ty_y)}), "
                           f"{len(left_cmds)} left gates (anti-ctrl), "
                           f"{len(right_cmds)} right gates (ctrl)")
            return

        # PlusMap (⊕-Map): f ⊕ g : (A + B) → (C + D)
        # Bifunctorial action on sums. Same anti-control pattern as Case.
        #
        # For nested sums (k > 1 tag bits), uses Strategy A from COH-PLUSMAP-02:
        # Tag permutation sandwich — synthesize permutation P mapping left-set
        # to MSB=0 half, emit P; PlusMap_bit on MSB; P⁻¹.
        #
        # Wire layout: [tag₀ | tag₁ | ... | tag_{k-1} | payload]
        # In pytket ILO convention: tag₀ is LSB, tag_{k-1} is MSB.
        # After P: MSB=0 → left summands, MSB=1 → right summands.
        if isinstance(t, PlusMap):
            from lang.types import Plus, flatten_plus, tag_width as tw_fn, payload_width
            import math

            # Compute structure of the sum type
            n_left = len(flatten_plus(t.ty_left)) if isinstance(t.ty_left, Plus) else 1
            n_right = len(flatten_plus(t.ty_right)) if isinstance(t.ty_right, Plus) else 1
            n_sum = n_left + n_right
            k = math.ceil(math.log2(n_sum)) if n_sum > 1 else 0

            # Compile branches to sub-circuits
            left_dom, _ = type_of(t.left)
            left_w = width(left_dom)
            left_cmds = _decompose_and_get_cmds(compile(t.left, materialize=True).circuit) if left_w > 0 else []

            right_dom, _ = type_of(t.right)
            right_w = width(right_dom)
            right_cmds = _decompose_and_get_cmds(compile(t.right, materialize=True).circuit) if right_w > 0 else []

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
            half = 2 ** (k - 1)

            if n_left > half or n_right > half:
                # Strategy B: full unitary synthesis for asymmetric splits.
                import numpy as np
                pw = payload_width(Plus(t.ty_left, t.ty_right))
                w = k + pw
                dim_pw = 2 ** pw

                U_f = compile(t.left, materialize=True).circuit.get_unitary()
                U_g = compile(t.right, materialize=True).circuit.get_unitary()
                dim = 2 ** w

                if n_left > half:
                    U_full = U_f.copy()
                    w_g = width(type_of(t.right)[0])
                    for tr in range(n_right):
                        tf = n_left + tr
                        rs, re = tf * dim_pw, (tf + 1) * dim_pw
                        U_full[rs:re, :] = 0
                        U_full[:, rs:re] = 0
                        if w_g == 0:
                            U_full[rs:re, rs:re] = np.eye(dim_pw)
                        else:
                            g_rs = tr * dim_pw
                            U_full[rs:re, rs:re] = U_g[g_rs:g_rs+dim_pw, g_rs:g_rs+dim_pw]
                else:
                    U_full = np.eye(dim, dtype=complex)
                    w_f = width(type_of(t.left)[0])
                    for tl in range(n_left):
                        rs, re = tl * dim_pw, (tl + 1) * dim_pw
                        if w_f == 0:
                            U_full[rs:re, rs:re] = np.eye(dim_pw)
                        else:
                            f_rs = tl * dim_pw
                            U_full[rs:re, rs:re] = U_f[f_rs:f_rs+dim_pw, f_rs:f_rs+dim_pw]
                    for tr in range(n_right):
                        tf = n_left + tr
                        rs, re = tf * dim_pw, (tf + 1) * dim_pw
                        g_rs = tr * dim_pw
                        U_full[rs:re, rs:re] = U_g[g_rs:g_rs+dim_pw, g_rs:g_rs+dim_pw]

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
                        f"PlusMap full unitary for width {w} > 3 not yet supported")

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

            # Step 2: PlusMap_bit controlled on MSB
            msb_phys = p.apply_new_to_old(offset)

            if left_cmds:
                left_wm = lambda w, stw=tw_left: p.apply_new_to_old(
                    _sub_wire_to_full(w, stw, offset, k))
                _emit_controlled_branch(msb_phys, left_cmds, left_wm, anti=True)
            if right_cmds:
                right_wm = lambda w, stw=tw_right: p.apply_new_to_old(
                    _sub_wire_to_full(w, stw, offset, k))
                _emit_controlled_branch(msb_phys, right_cmds, right_wm)

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
        # Uses per-branch X-flip + multi-controlled gates + X-unflip
        if isinstance(t, NPlusMap):
            from lang.types import (Plus, flatten_plus, tag_width as tw_fn,
                                    payload_width, build_plus_tree)
            import math

            n_branches = len(t.summand_types)
            assert n_branches >= 2
            sum_ty = build_plus_tree(list(t.summand_types))
            k = tw_fn(sum_ty)
            pw = payload_width(sum_ty)

            tag_phys = [p.apply_new_to_old(offset + j) for j in range(k)]
            payload_base = offset + k

            for i, (st, br) in enumerate(zip(t.summand_types, t.branches)):
                sub = compile(br, materialize=True)
                sub_cmds = _decompose_and_get_cmds(sub.circuit)

                if not sub_cmds:
                    continue  # Id branch, nothing to emit

                def make_wire_map(pb=payload_base):
                    def wire_map(w):
                        return p.apply_new_to_old(pb + w)
                    return wire_map

                _emit_nway_controlled(circ, tag_phys, i, sub_cmds, make_wire_map())

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
            left_cmds = _decompose_and_get_cmds(compile(t.left, materialize=True).circuit) if left_w > 0 else []

            right_dom, _ = type_of(t.right)
            right_w = width(right_dom)
            right_cmds = _decompose_and_get_cmds(compile(t.right, materialize=True).circuit) if right_w > 0 else []

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

                if n_left > half:
                    U_full = U_f.copy()
                    w_g = width(type_of(t.right)[0])
                    for tr in range(n_right):
                        tf = n_left + tr
                        rs, re = tf * dim_pw, (tf + 1) * dim_pw
                        U_full[rs:re, :] = 0
                        U_full[:, rs:re] = 0
                        if w_g == 0:
                            U_full[rs:re, rs:re] = np.eye(dim_pw)
                        else:
                            g_rs = tr * dim_pw
                            U_full[rs:re, rs:re] = U_g[g_rs:g_rs+dim_pw, g_rs:g_rs+dim_pw]
                else:
                    U_full = np.eye(dim, dtype=complex)
                    w_f = width(type_of(t.left)[0])
                    for tl in range(n_left):
                        rs, re = tl * dim_pw, (tl + 1) * dim_pw
                        if w_f == 0:
                            U_full[rs:re, rs:re] = np.eye(dim_pw)
                        else:
                            f_rs = tl * dim_pw
                            U_full[rs:re, rs:re] = U_f[f_rs:f_rs+dim_pw, f_rs:f_rs+dim_pw]
                    for tr in range(n_right):
                        tf = n_left + tr
                        rs, re = tf * dim_pw, (tf + 1) * dim_pw
                        g_rs = tr * dim_pw
                        U_full[rs:re, rs:re] = U_g[g_rs:g_rs+dim_pw, g_rs:g_rs+dim_pw]

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
                raise NotImplementedError(
                    f"PhasedPlusMap with {total_tag_bits} tag bits not yet fully implemented.")
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
                    # For 3+ tag qubits, need multi-controlled U1 decomposition
                    # This is complex; for now raise NotImplementedError
                    raise NotImplementedError(
                        f"PhasedControl with {n_tag_bits} tag bits not yet fully implemented. "
                        "Only 1-2 tag bits (arity ≤ 4) supported.")

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
            # Per spec section 4.6: Boundary exposure
            #
            # body : (Γ ⊗ A) → B is compiled with x:A bound to extra input wires.
            # Lambda repackages: C_{λx.body} : ⟦Γ⟧ → ⟦A⟧||⟦B⟧
            #
            # Output layout: [A_slot | B_slot] where:
            #   - A_slot (wires [offset..offset+wA)) = x (argument input)
            #   - B_slot (wires [offset+wA..offset+wA+wB)) = body output
            #
            # For body : A → B operating on the x wires:
            #   - body transforms wires [offset..offset+wA) (the A_slot)
            #   - After body, result is on [offset..offset+wB)
            #   - We route result to B_slot via permutation swap
            wA = width(t.dom)
            wB = width(t.cod)

            # Bind x to the A_slot wires
            x_start = offset
            new_env = {**env, t.name: (x_start, wA)}

            # Compile body with x bound
            go(t.body, offset, new_env)

            # Route body output to B_slot:
            # Body output is on [offset..offset+wB), need it on [offset+wA..offset+wA+wB)
            #
            # The lambda output layout is [A_slot | B_slot]:
            #   - A_slot [0..wA): exposed argument input interface
            #   - B_slot [wA..wA+wB): body result
            #
            # After body compiles, result is on [0..wB). We need to shift it right by wA.
            total_width = wA + wB
            if total_width > 0 and wB > 0:
                # Build permutation: shift B wires right by wA positions
                # new_to_old[i] = where wire i's content comes from
                #
                # For wires [0..wA): these become A_slot (identity, keep as-is)
                # For wires [wA..wA+wB): these get content from [0..wB)
                #   new wire (wA + j) gets old wire j, for j in 0..wB-1
                #
                # In new_to_old format:
                #   perm[wA + j] = j  (B_slot gets body output)
                #   perm[i] = wA + i for i in 0..wA-1 (A_slot gets what was after body output)
                #
                # But wait - after body, wires [0..wB) have result, [wB..wA+wB) are unchanged.
                # We want: [0..wA) = A_slot (input interface), [wA..wA+wB) = body result
                #
                # For wA == wB: swap [0..wA) and [wA..2wA) -> works
                # For wA != wB: need proper routing
                #
                # Correct routing:
                #   - Body output [0..wB) → B_slot [wA..wA+wB)
                #   - Original input interface was [0..wA), but body consumed it
                #   - After routing, A_slot [0..wA) should be the "exposed" interface
                #
                # The permutation rotates: [0..wA+wB) → [wB, wB+1, ..., wA+wB-1, 0, 1, ..., wB-1]
                # This puts body output (was at [0..wB)) at [wA..wA+wB)
                local_perm = list(range(wB, total_width)) + list(range(wB))
                step = embed_local_perm(WirePerm(total_width, local_perm), offset)
                p = compose(step, p)
                if explain:
                    log.append(f"Lam '{t.name}': route body output to B_slot, wA={wA}, wB={wB}")

            if explain:
                log.append(f"Lam '{t.name}': x at [{x_start}, {x_start+wA}), B_slot at [{offset+wA}, {offset+wA+wB})")
            return

        if isinstance(t, Apply):
            # Apply: f arg : B
            # Per spec section 4.7: Boundary splicing
            #
            # f : ... → Arrow(A, B) produces [A_slot | B_slot] on output
            # arg : ... → A produces [A] on output
            # Apply connects (identifies) arg's A output with f's A_slot
            # Result is B_slot
            f_dom, f_cod = type_of(t.f)
            if not isinstance(f_cod, Arrow):
                raise TypeCheckError(f"Apply expects function type, got {f_cod}")

            A = f_cod.dom
            B = f_cod.cod
            wA = width(A)
            wB = width(B)

            # Special case: closed lambda application (β-reduction at compile time)
            # When f is Lam with f_dom = Unit, we can compile directly as arg;body
            # without the function-layout swaps
            if isinstance(t.f, Lam) and isinstance(f_dom, Unit):
                # Closed lambda: compile as β-reduced (arg then body)
                # arg fills wires [offset..offset+wA), body operates on them
                go(t.arg, offset, env)
                # Bind x to the argument wires and compile body
                x_start = offset
                new_env = {**env, t.f.name: (x_start, wA)}
                go(t.f.body, offset, new_env)
                if explain:
                    log.append(f"Apply (closed lambda): β-reduced as arg;body, x at [{x_start}, {x_start+wA})")
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
            # Variable reference: identity on the variable's wire range.
            # Look up variable in env to get its wire range.
            if t.name in env:
                var_start, var_width = env[t.name]
                if explain:
                    log.append(f"Var '{t.name}': identity on wires [{var_start}, {var_start + var_width}) at offset {offset}")
            else:
                # Variable not in env - this is an error in a proper implementation,
                # but for now we just treat it as identity on ty wires at offset.
                if explain:
                    log.append(f"Var '{t.name}' (unbound): identity on {width(t.ty)} wires at offset {offset}")
            return

        if isinstance(t, Pair):
            # Tensor introduction: (fst, snd) : A ⊗ B
            # Compile fst and snd in parallel.
            # fst at offset, snd at offset + width(fst).
            fst_dom, _ = type_of(t.fst)
            fst_w = width(fst_dom)
            go(t.fst, offset, env)
            go(t.snd, offset + fst_w, env)
            if explain:
                log.append(f"Pair: fst at offset {offset}, snd at offset {offset + fst_w}")
            return

        if isinstance(t, LetPair):
            # Tensor elimination: let (x, y) = pair in body
            # 1. Compile pair to get output wires ⟦A⟧||⟦B⟧
            # 2. Extend env: x ↦ prefix (A wires), y ↦ suffix (B wires)
            # 3. Compile body with extended env
            #
            # The pair's output becomes input to the body where x and y are bound.
            go(t.pair, offset, env)

            # Extend environment for body
            x_start = offset
            x_width = width(t.ty_x)
            y_start = offset + x_width
            y_width = width(t.ty_y)
            new_env = {**env, t.x: (x_start, x_width), t.y: (y_start, y_width)}

            go(t.body, offset, new_env)
            if explain:
                log.append(f"LetPair: {t.x} at [{x_start},{x_start+x_width}), "
                          f"{t.y} at [{y_start},{y_start+y_width}), body at offset {offset}")
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


