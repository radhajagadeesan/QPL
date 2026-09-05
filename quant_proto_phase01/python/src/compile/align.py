# src/compile/align.py
"""Align: reconciling two boundary frames at a splice.

A judgment type fixes the semantic boundary space, not its physical
embedding, so a producer and a consumer of the same interface may sit in
different frames. Align is the partial isometry that carries one to the
other, extended deterministically over the unused code space:

    A u_co^-  =  u_pr^+          i.e.  A maps the consumer's embedding onto
                                       the producer's

and the consumer artifact is retargeted by

    G  |-->  A G A^dagger,        L^± |--> A L^±

**Chronology.** With the usual execute-left-to-right circuit convention, the
matrix equation ``G' = A G A^dagger`` is realised by the gate sequence

    A^dagger ;  G ;  A

not ``A ; G ; A^dagger``. The tests assert the matrix equation rather than
the gate order, so this orientation cannot silently invert.

**Total extension.** The valid-code mapping is partial. It is completed over
the unused states in a fixed, deterministic way (ascending order on both
sides). This is not tidiness: pytket's ``ToffoliBox`` rejects a partial
permutation outright ("some states aren't mapped"), so the extension is what
makes the alignment representable at all.

**Fast paths.**
  * frames agree            -> identity, zero gates
  * a pure wire permutation -> folds into the running ``WirePerm``
  * otherwise               -> one exact permutation box
"""

from __future__ import annotations

from typing import Optional, Tuple

import numpy as np

from compile.frames import (Frame, embeddings_agree, permute_index,
                            FOpaque)


class AlignError(Exception):
    """Two frames cannot be aligned (different dimensions or registers)."""


# ---------------------------------------------------------------------------
# The alignment permutation
# ---------------------------------------------------------------------------

def align_permutation(src: Frame, dst: Frame) -> Tuple[int, ...]:
    """Total permutation `p` with `p[src_code] = dst_code`.

    At a splice this is called as `align_permutation(consumer_in, producer_out)`
    so that A maps CONSUMER codes onto PRODUCER codes:  A u_C^- = u_P^+ ,
    i.e. A|c_i> = |p_i>.

    The valid codes are mapped label-by-label; the unused codes of each side
    are then paired in ascending order, which is deterministic and total.
    """
    # Align never widens silently. Unequal registers or dimensions require an
    # explicitly selected common ambient frame with typed residual ports; if
    # the caller has not supplied one, this fails closed.
    if src.n_qubits != dst.n_qubits:
        raise AlignError(
            f"cannot align frames of different registers "
            f"({src.n_qubits} vs {dst.n_qubits} qubits): select a common "
            f"ambient frame with typed residual ports first")
    if src.dim != dst.dim:
        raise AlignError(
            f"cannot align frames of different semantic dimensions "
            f"({src.dim} vs {dst.dim})")

    size = 1 << src.n_qubits
    perm = [None] * size
    for s, d in zip(src.codes, dst.codes):
        perm[s] = d

    free_src = [i for i in range(size) if perm[i] is None]
    used_dst = set(dst.codes)
    free_dst = [i for i in range(size) if i not in used_dst]
    for s, d in zip(free_src, free_dst):
        perm[s] = d
    return tuple(perm)


def build_align(src: Frame, dst: Frame) -> np.ndarray:
    """The alignment matrix A with  A u_src = u_dst  (exactly)."""
    perm = align_permutation(src, dst)
    size = 1 << src.n_qubits
    A = np.zeros((size, size), dtype=complex)
    for s, d in enumerate(perm):
        A[d, s] = 1.0
    return A


# ---------------------------------------------------------------------------
# Fast-path classification
# ---------------------------------------------------------------------------

def align_is_identity(src: Frame, dst: Frame) -> bool:
    return embeddings_agree(src, dst)


def align_gate_count(src: Frame, dst: Frame) -> int:
    """Gates an align would add: zero when the frames already agree."""
    if align_is_identity(src, dst):
        return 0
    if align_as_wire_permutation(src, dst) is not None:
        return 0                       # folds into WirePerm
    return 1                           # one exact permutation box


def align_as_wire_permutation(src: Frame, dst: Frame) -> Optional[Tuple[int, ...]]:
    """`new_to_old` if the alignment is a pure wire permutation, else None.

    A wire permutation is far cheaper than a codeword permutation, and is
    absorbed into the running WirePerm rather than emitted.
    """
    if src.n_qubits != dst.n_qubits or src.dim != dst.dim:
        return None
    n = src.n_qubits
    perm = align_permutation(src, dst)
    # Try every wire permutation? No -- derive it from where the single-bit
    # basis states go, then verify on the whole register.
    images = []
    for j in range(n):
        img = perm[1 << (n - 1 - j)]
        if img == 0 or (img & (img - 1)) != 0:
            return None                # not a basis-vector image
        images.append(n - 1 - img.bit_length() + 1)
    if sorted(images) != list(range(n)):
        return None
    new_to_old = [0] * n
    for old_wire, new_wire in enumerate(images):
        new_to_old[new_wire] = old_wire
    if any(permute_index(i, new_to_old, n) != perm[i] for i in range(1 << n)):
        return None
    return tuple(new_to_old)


def align_is_wire_permutation(src: Frame, dst: Frame) -> bool:
    return align_as_wire_permutation(src, dst) is not None


# ---------------------------------------------------------------------------
# Emission
# ---------------------------------------------------------------------------

def emit_align(circ, wires, src: Frame, dst: Frame, *, inverse: bool = False):
    """Emit the alignment carrying `src` to `dst` onto `wires`.

    Returns True if gates were emitted. Identity and wire-permutation cases
    emit nothing -- the caller folds those into the WirePerm.
    """
    if align_is_identity(src, dst):
        return False
    if align_as_wire_permutation(src, dst) is not None:
        return False

    from pytket.circuit import ToffoliBox
    perm = align_permutation(dst, src) if inverse else align_permutation(src, dst)
    n = src.n_qubits

    def bits(v):
        return tuple(bool((v >> (n - 1 - b)) & 1) for b in range(n))

    circ.add_toffolibox(ToffoliBox({bits(s): bits(d)
                                    for s, d in enumerate(perm)}),
                        list(wires))
    return True


def make_cut_transport(consumer_in: Frame, producer_out: Frame, wires,
                       ambient_width: int, label: str = "",
                       producer_wires=(), consumer_wires=(), completion=None):
    """Select the cut transport ONCE, from the frames the splice actually has.

    Everything downstream -- the two physical Aligns and the composed
    selected boundary -- consumes the returned object, so there is no second
    map to drift from this one.
    """
    from compile.frames import CutTransport
    fwd = align_permutation(consumer_in, producer_out)
    inv = [0] * len(fwd)
    for i, j in enumerate(fwd):
        inv[j] = i
    wp = align_as_wire_permutation(consumer_in, producer_out)
    if align_is_identity(consumer_in, producer_out):
        kind, wp = "identity", None
    elif wp is not None:
        kind = "wire-permutation"
    else:
        kind, wp = "code-permutation", None
    return CutTransport(
        wires=tuple(wires), ambient_width=ambient_width,
        consumer_codes=tuple(consumer_in.codes),
        producer_codes=tuple(producer_out.codes),
        forward=tuple(fwd), inverse=tuple(inv), kind=kind,
        wire_permutation=wp, label=label,
        producer_wires=tuple(producer_wires),
        consumer_wires=tuple(consumer_wires), completion=completion)


def emit_align_transport(circ, transport, *, inverse: bool = False):
    """Emit the physical Align from THE recorded transport.

    Same object as the metadata composition consumes, so the gates and the
    boundary cannot describe different permutations.
    """
    if transport.kind != "code-permutation":
        return False                   # identity and wire perms emit nothing
    from pytket.circuit import ToffoliBox
    perm = transport.inverse if inverse else transport.forward
    n = len(transport.wires)

    def bits(v):
        return tuple(bool((v >> (n - 1 - b)) & 1) for b in range(n))

    circ.add_toffolibox(ToffoliBox({bits(s): bits(d)
                                    for s, d in enumerate(perm)}),
                        list(transport.wires))
    return True


def transported_frame(A: np.ndarray, frame: Frame, label: str = "") -> Frame:
    """The frame `A u` -- the consumer's output carried into the producer's
    frame. This is the effective output of the spliced pair and must be
    propagated to the NEXT splice, not recomputed from a type.
    """
    codes = []
    for c in frame.codes:
        col = A[:, c]
        hits = np.flatnonzero(np.abs(col) > 0.5)
        if len(hits) != 1:
            raise AlignError("alignment is not a basis permutation")
        codes.append(int(hits[0]))
    return Frame(logical=frame.logical, n_qubits=frame.n_qubits,
                 codes=tuple(codes),
                 expr=FOpaque("transported through Align"),
                 label=label or f"{frame.label}@aligned",
                 sectors=(), ports=frame.ports)
