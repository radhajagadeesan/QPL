# src/compile/frames.py
"""Boundary frames: exact embeddings of a semantic basis into a register.

Central invariant
-----------------
A judgment type determines the semantic boundary *space*, but does **not**
uniquely determine its physical *embedding*. The derivation selects the
boundary frames and port placements.

So one abstract interface may legitimately have several frames. For
``Ten(Z3, Z3)`` — semantic dimension 9, four physical qubits — both of these
are correct and neither is "the" encoding:

    tensor frame   codes = [0, 1, 2, 4, 5, 6, 8, 9, 10]     [D_tag | A payload]
    flat-9 frame   codes = [0, 1, 2, 3, 4, 5, 6, 7, 8]      one 4-bit tag

These are reconciled by ``Align`` at the splice, never by changing the source
type or the example.

What a Frame is
---------------
A ``Frame`` records the exact embedding

    u : semantic space (dim d)  -->  physical register (dim 2^n)

as ``codes``: ``codes[i]`` is the physical basis index of the i-th valid
semantic basis label. ``codes`` is **authoritative**. ``expr`` carries a
symbolic form (identity, wire permutation, tensor, sum, tag-conditioned
permutation, composition) that fast paths may exploit, but it is an
optimisation and never the semantics. ``WirePerm`` likewise becomes an
optimisation rather than the semantic representation.

Semantic testing
----------------
Correctness of a compiled ``G`` is judged on the code space only:

    U_sem  = (u_out)^dagger  G  u_in                     compared exactly
    leak   = ||(I - u_out u_out^dagger) G u_in||         must vanish

Equality on unused padding states is not required. Comparison is exact, with
no phase quotient — ``(iX)(iX) = -I`` must be distinguishable from ``+I``.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field, replace as _dataclass_replace, replace
from typing import Tuple, Optional

import numpy as np

from lang.types import (
    Ty, Q, Unit, Ten, Plus, Arrow, Dual,
    width, flatten_plus, tag_width, payload_width, pretty,
)


# ---------------------------------------------------------------------------
# Type serialization (frames travel across the Bridge, so the logical
# interface must round-trip structurally -- `pretty` is lossy)
# ---------------------------------------------------------------------------

def ty_to_json(ty: Ty) -> dict:
    if isinstance(ty, Unit):
        return {"node": "Unit"}
    if isinstance(ty, Q):
        return {"node": "Q"}
    if isinstance(ty, Ten):
        return {"node": "Ten", "left": ty_to_json(ty.left),
                "right": ty_to_json(ty.right)}
    if isinstance(ty, Plus):
        return {"node": "Plus", "left": ty_to_json(ty.left),
                "right": ty_to_json(ty.right)}
    if isinstance(ty, Arrow):
        return {"node": "Arrow", "dom": ty_to_json(ty.dom),
                "cod": ty_to_json(ty.cod)}
    if isinstance(ty, Dual):
        return {"node": "Dual", "ty": ty_to_json(ty.ty)}
    raise TypeError(f"ty_to_json: unsupported {ty!r}")


def ty_from_json(j: dict) -> Ty:
    node = j["node"]
    if node == "Unit":
        return Unit()
    if node == "Q":
        return Q()
    if node == "Ten":
        return Ten(ty_from_json(j["left"]), ty_from_json(j["right"]))
    if node == "Plus":
        return Plus(ty_from_json(j["left"]), ty_from_json(j["right"]))
    if node == "Arrow":
        return Arrow(ty_from_json(j["dom"]), ty_from_json(j["cod"]))
    if node == "Dual":
        return Dual(ty_from_json(j["ty"]))
    raise ValueError(f"ty_from_json: unknown node {node}")


def semantic_dim(ty: Ty) -> int:
    """Dimension of the semantic boundary space of a type.

    A frame's `codes` must have exactly this length: an embedding maps every
    valid semantic basis label somewhere, and nothing else.
    """
    if isinstance(ty, Unit):
        return 1
    if isinstance(ty, Q):
        return 2
    if isinstance(ty, Ten):
        return semantic_dim(ty.left) * semantic_dim(ty.right)
    if isinstance(ty, Plus):
        return sum(semantic_dim(leaf) for leaf in flatten_plus(ty))
    if isinstance(ty, Arrow):
        return semantic_dim(ty.dom) * semantic_dim(ty.cod)
    if isinstance(ty, Dual):
        return semantic_dim(ty.ty)
    raise TypeError(f"semantic_dim: unsupported {ty!r}")


# ---------------------------------------------------------------------------
# Sectors and ports (derivation-selected placement, recorded not reconstructed)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Sector:
    """A branch region of a sum frame: the codes belonging to one summand.

    `tag_values` is a SET of physical tag words, not a single integer. A
    summand that is itself a sum spans several tag words -- in
    NPlusMap((Z3, Z5), ...) the second summand occupies tag words 3..7 -- and
    recording it as one integer misdescribes the sector.
    """
    index: int
    logical: Ty
    codes: Tuple[int, ...]
    tag_values: Tuple[int, ...]

    def __post_init__(self):
        if isinstance(self.tag_values, int):
            object.__setattr__(self, "tag_values", (self.tag_values,))
        if not self.tag_values:
            raise ValueError(f"Sector {self.index}: no tag values")
        if len(set(self.tag_values)) != len(self.tag_values):
            raise ValueError(f"Sector {self.index}: repeated tag value")

    def to_json(self) -> dict:
        return {"index": self.index, "logical": ty_to_json(self.logical),
                "codes": list(self.codes), "tag_values": list(self.tag_values)}

    @staticmethod
    def from_json(j: dict) -> "Sector":
        tv = j.get("tag_values", [j["tag_value"]] if "tag_value" in j else [])
        return Sector(int(j["index"]), ty_from_json(j["logical"]),
                      tuple(int(c) for c in j["codes"]),
                      tuple(int(t) for t in tv))


PORT_ROLES = ("main", "payload", "tag", "context", "residual")


# --- provenance identity ---------------------------------------------------
#
# Ownership and cut lineage are MINTED, never inferred. Two binders of the same
# type get different owners; two occurrences of one AST object get different
# cuts. Nothing here reads a type, a name, a wire, or a bit pattern -- those
# were exactly the inference routes that produced untruthful artifacts.

class ProvenanceScope:
    """Deterministic, compile-scoped provenance namespace.

    A module-global counter would make identities depend on whatever was
    compiled before, so the same derivation would serialize differently across
    runs and separately compiled branch artifacts could collide when combined.

    Instead each compilation owns a root scope and FORKS a child per
    occurrence. An identity is the scope's path plus a local ordinal:

        own:0.2.1     cut:0.2.1

    Reproducible, because it depends only on the traversal of the derivation.
    Collision-free across siblings, because their paths differ. Distinct for
    two occurrences of one AST object, because each visit forks its own scope.
    No type, name, wire or bit geometry participates -- those were exactly the
    inference routes that produced untruthful artifacts.
    """

    __slots__ = ("path", "_mints", "_forks")

    def __init__(self, path: Tuple[int, ...] = ()):
        self.path = tuple(path)
        self._mints = 0
        self._forks = 0

    def fork(self) -> "ProvenanceScope":
        """A child namespace. Siblings are disjoint by construction."""
        self._forks += 1
        return ProvenanceScope(self.path + (self._forks,))

    def _next(self, kind: str) -> str:
        self._mints += 1
        tail = ".".join(str(x) for x in self.path + (self._mints,))
        return f"{kind}:{tail}"

    def owner(self) -> str:
        """A fresh binder identity within this scope."""
        return self._next("own")

    def cut(self) -> str:
        """A fresh cut identity within this scope."""
        return self._next("cut")

    def __repr__(self):
        return f"ProvenanceScope({'.'.join(str(x) for x in self.path) or '/'})"


class ProvenanceError(Exception):
    """Missing, duplicated or ambiguous ownership / cut lineage."""


def completion_factor(port: "Port") -> int:
    """How much a live port multiplies the completed dimension.

    A true Unit spectator contributes 1. Anything else contributes its own
    semantic dimension -- f : Q-oQ contributes 4, EndoOp contributes 16.
    """
    if isinstance(port.logical, Unit):
        return 1
    return semantic_dim(port.logical)


def check_binding_consistency(bindings, where=""):
    """Two records of ONE owner must agree on everything recorded.

    Equal owner id with a different type, placement, introduction cut or
    encoding is not one resource seen twice; it is a contradiction, and
    completing against either reading would be a guess.
    """
    seen = {}
    for b in bindings:
        key = b.owner_id
        if key is None:
            continue
        prev = seen.get(key)
        if prev is None:
            seen[key] = b
            continue
        for fld in ("logical", "wires", "intro_cut", "codes"):
            if getattr(prev, fld) != getattr(b, fld):
                raise ProvenanceError(
                    f"{where}owner {key} is recorded twice with different "
                    f"{fld}: {getattr(prev, fld)!r} versus "
                    f"{getattr(b, fld)!r}")
    return True


def _completion_factors(ports) -> dict:
    """Distinct live completion factors, keyed on (owner_id, cut_id).

    Shared by Frame.completed_dimension and SidePlacement so the two can never
    disagree about what "counted once" means.
    """
    seen = {}
    for p in ports:
        if p.role not in ("context", "residual"):
            continue
        factor = completion_factor(p)
        if factor == 1:
            continue
        if p.owner_id is None or p.cut_id is None:
            raise ProvenanceError(
                f"live {p.role} port {p.name!r} of type "
                f"{pretty(p.logical)} has no "
                f"{'owner_id' if p.owner_id is None else 'cut_id'}; the "
                f"completed dimension cannot be computed without provenance")
        if p.by_sector:
            raise ProvenanceError(
                f"live {p.role} port {p.name!r} is sector-conditioned "
                f"{p.by_sector}; an outer context must be represented once, "
                f"unconditionally, not copied per sector")
        key = (p.owner_id, p.cut_id)
        if key in seen and seen[key] != factor:
            raise ProvenanceError(
                f"owner {p.owner_id} at cut {p.cut_id} appears with "
                f"conflicting completion factors {seen[key]} and {factor}")
        seen[key] = factor
    return seen


def completed_dimension(frame: "Frame") -> int:
    """frame.dim times each DISTINCT live completion factor, once.

    Distinctness is decided by recorded provenance -- (owner_id, cut_id) --
    and by nothing else. Never by type, name, wires or basis geometry: two
    equal-typed binders are two resources, and one binder mentioned twice is
    one resource.

    Raises rather than guessing on missing provenance, conflicting ownership,
    or a sector-conditioned context (an outer context must be represented once,
    unconditionally, not per sector).
    """
    total = frame.dim
    for factor in _completion_factors(frame.ports).values():
        total *= factor
    return total


@dataclass(frozen=True)
class Port:
    """A placement of a sub-interface within a frame.

    Placement may be SECTOR-CONDITIONED: the same logical port can sit on
    different wires in different sectors -- "wire 2 in sector 0, wire 3 in
    sector 1" -- which is exactly the situation a fixed wire tuple cannot
    express and which the unequal-width distributor creates.

    `wires` gives the unconditioned placement; `by_sector` maps a sector's
    tag_value to that sector's wires and, when present, is authoritative.

    `role="residual"` marks spectator coordinates the logical interface does
    not name -- transported contexts, function-layout wires, padding.
    """
    name: str
    logical: Ty
    wires: Tuple[int, ...] = ()
    role: str = "main"
    by_sector: Tuple[Tuple[int, Tuple[int, ...]], ...] = ()
    owner_id: Optional[str] = None      # which BINDER owns this resource
    cut_id: Optional[str] = None        # the CURRENT boundary cut
    origin_cut: Optional[str] = None    # the IMMUTABLE introduction cut

    def __post_init__(self):
        if self.role not in PORT_ROLES:
            raise ValueError(
                f"Port {self.name}: role {self.role!r} not in {PORT_ROLES}")
        if not self.wires and not self.by_sector:
            raise ValueError(f"Port {self.name}: no placement given")
        for group in (self.wires,) + tuple(w for _, w in self.by_sector):
            if len(set(group)) != len(group):
                raise ValueError(f"Port {self.name}: repeated wire in {group}")
            for w in group:
                if not isinstance(w, int) or isinstance(w, bool) or w < 0:
                    raise ValueError(f"Port {self.name}: bad wire {w!r}")
        tags = [t for t, _ in self.by_sector]
        if len(set(tags)) != len(tags):
            raise ValueError(f"Port {self.name}: duplicate sector tag in "
                             f"by_sector")

    @property
    def is_sector_conditioned(self) -> bool:
        return bool(self.by_sector)

    def wires_in_sector(self, tag_value: int) -> Tuple[int, ...]:
        for t, w in self.by_sector:
            if t == tag_value:
                return w
        if self.by_sector:
            raise KeyError(f"Port {self.name}: no placement for sector "
                           f"{tag_value}")
        return self.wires

    def all_wires(self) -> Tuple[int, ...]:
        seen = list(self.wires)
        for _, w in self.by_sector:
            seen.extend(w)
        return tuple(sorted(set(seen)))

    def recut(self, new_cut: str) -> "Port":
        """Move this port to a new BOUNDARY cut. Changes cut_id ONLY.

        `origin_cut` is preserved exactly as-is and is never derived from the
        current cut. Laundering an arbitrary boundary cut into the origin
        would fabricate lineage: it would look like recorded provenance while
        actually recording wherever the port happened to sit.
        """
        return replace(self, cut_id=new_cut)

    @property
    def is_live(self) -> bool:
        """A port standing for a real resource, not padding."""
        return not isinstance(self.logical, Unit)

    def require_origin(self, where: str = "") -> str:
        """The introduction cut, or an explicit failure.

        Only legacy Unit spectators may carry None. A live typed port without
        recorded origin cannot be identified across cuts, and guessing one is
        the inference this model exists to remove.
        """
        if not self.is_live:
            return self.origin_cut
        if self.origin_cut is None:
            raise ProvenanceError(
                f"{where or 'port'} {self.name!r} of type "
                f"{pretty(self.logical)} is live but records no origin_cut; "
                f"it must be set explicitly from its TypedBinding.intro_cut")
        return self.origin_cut

    def to_json(self) -> dict:
        return {"name": self.name, "logical": ty_to_json(self.logical),
                "wires": list(self.wires), "role": self.role,
                "by_sector": [[t, list(w)] for t, w in self.by_sector],
                "owner_id": self.owner_id, "cut_id": self.cut_id,
                "origin_cut": self.origin_cut}

    @staticmethod
    def from_json(j: dict) -> "Port":
        return Port(j["name"], ty_from_json(j["logical"]),
                    tuple(int(w) for w in j.get("wires", [])),
                    j.get("role", "main"),
                    tuple((int(t), tuple(int(x) for x in w))
                          for t, w in j.get("by_sector", [])),
                    owner_id=j.get("owner_id"),
                    cut_id=j.get("cut_id"),
                    origin_cut=j.get("origin_cut"))


# ---------------------------------------------------------------------------
# Symbolic frame expressions (optimisation hints; `codes` stays authoritative)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class FIdentity:
    n: int


@dataclass(frozen=True)
class FWirePerm:
    """A pure wire permutation: new_to_old on n qubits."""
    new_to_old: Tuple[int, ...]


@dataclass(frozen=True)
class FTensor:
    left: "FrameExpr"
    right: "FrameExpr"


@dataclass(frozen=True)
class FSum:
    """Flat sum: tag_bits tag qubits then payload_bits shared payload."""
    parts: Tuple["FrameExpr", ...]
    tag_bits: int
    payload_bits: int


@dataclass(frozen=True)
class FTagCondPerm:
    """A permutation that differs per tag sector."""
    tag_bits: int
    per_tag: Tuple[Tuple[int, ...], ...]


@dataclass(frozen=True)
class FCompose:
    """first then second, chronologically."""
    first: "FrameExpr"
    second: "FrameExpr"


@dataclass(frozen=True)
class FOpaque:
    """A codeword permutation with no cheaper structure."""
    note: str = ""


FrameExpr = object  # tagged union of the above


def expr_to_json(e) -> Optional[dict]:
    if e is None:
        return None
    if isinstance(e, FIdentity):
        return {"k": "identity", "n": e.n}
    if isinstance(e, FWirePerm):
        return {"k": "wireperm", "new_to_old": list(e.new_to_old)}
    if isinstance(e, FTensor):
        return {"k": "tensor", "left": expr_to_json(e.left),
                "right": expr_to_json(e.right)}
    if isinstance(e, FSum):
        return {"k": "sum", "parts": [expr_to_json(p) for p in e.parts],
                "tag_bits": e.tag_bits, "payload_bits": e.payload_bits}
    if isinstance(e, FTagCondPerm):
        return {"k": "tagcond", "tag_bits": e.tag_bits,
                "per_tag": [list(p) for p in e.per_tag]}
    if isinstance(e, FCompose):
        return {"k": "compose", "first": expr_to_json(e.first),
                "second": expr_to_json(e.second)}
    if isinstance(e, FOpaque):
        return {"k": "opaque", "note": e.note}
    raise TypeError(f"expr_to_json: unsupported {e!r}")


def expr_from_json(j: Optional[dict]):
    if j is None:
        return None
    k = j["k"]
    if k == "identity":
        return FIdentity(int(j["n"]))
    if k == "wireperm":
        return FWirePerm(tuple(int(x) for x in j["new_to_old"]))
    if k == "tensor":
        return FTensor(expr_from_json(j["left"]), expr_from_json(j["right"]))
    if k == "sum":
        return FSum(tuple(expr_from_json(p) for p in j["parts"]),
                    int(j["tag_bits"]), int(j["payload_bits"]))
    if k == "tagcond":
        return FTagCondPerm(int(j["tag_bits"]),
                            tuple(tuple(int(x) for x in p) for p in j["per_tag"]))
    if k == "compose":
        return FCompose(expr_from_json(j["first"]), expr_from_json(j["second"]))
    if k == "opaque":
        return FOpaque(j.get("note", ""))
    raise ValueError(f"expr_from_json: unknown kind {k}")


class ExprEvalError(Exception):
    """A non-opaque FrameExpr could not be evaluated exactly."""


def permute_index(idx: int, new_to_old, n: int) -> int:
    """Re-index a basis state under a wire permutation (big-endian, q0 = MSB).

    New wire j carries what old wire new_to_old[j] carried.
    """
    out = 0
    for j in range(n):
        bit = (idx >> (n - 1 - new_to_old[j])) & 1
        out |= bit << (n - 1 - j)
    return out


def expr_eval(e, logical: Ty, n_qubits: int) -> Tuple[int, ...]:
    """Codes denoted by a FrameExpr. Raises ExprEvalError if it cannot be
    evaluated exactly.

    Fail-CLOSED: `FOpaque` is the only form permitted to decline, and it
    declines by being opaque -- callers must not treat "could not evaluate"
    as "valid".
    """
    if e is None:
        raise ExprEvalError("no expression")

    if isinstance(e, FOpaque):
        raise ExprEvalError(f"opaque: {e.note}")

    if isinstance(e, FIdentity):
        # The flat prefix embedding of the semantic space into n qubits --
        # NOT "all 2^n indices". A 9-dimensional space in 4 qubits is codes
        # 0..8, which is exactly what flat_frame builds.
        if e.n != n_qubits:
            raise ExprEvalError(f"FIdentity({e.n}) in a {n_qubits}-qubit frame")
        d = semantic_dim(logical)
        if d > (1 << n_qubits):
            raise ExprEvalError("dimension exceeds register")
        return tuple(range(d))

    if isinstance(e, FWirePerm):
        # Validate BEFORE any shifting: an out-of-range entry would otherwise
        # surface as a raw "negative shift count" ValueError from
        # permute_index rather than as a clean ExprEvalError.
        if (len(e.new_to_old) != n_qubits
                or sorted(e.new_to_old) != list(range(n_qubits))):
            raise ExprEvalError(f"FWirePerm {e.new_to_old} is not a permutation "
                                f"of {n_qubits} wires")
        base = _canonical_codes(logical)[0]
        return tuple(permute_index(c, e.new_to_old, n_qubits) for c in base)

    if isinstance(e, FTensor):
        if not isinstance(logical, (Ten, Arrow)):
            raise ExprEvalError(f"FTensor against non-tensor {pretty(logical)}")
        lt = logical.left if isinstance(logical, Ten) else logical.dom
        rt = logical.right if isinstance(logical, Ten) else logical.cod
        nl, nr = width(lt), width(rt)
        if nl + nr != n_qubits:
            raise ExprEvalError("FTensor child widths do not fill the register")
        # Children are evaluated, not ignored.
        lc = expr_eval(e.left, lt, nl)
        rc = expr_eval(e.right, rt, nr)
        return tuple((a << nr) | b for a in lc for b in rc)

    if isinstance(e, FSum):
        if not isinstance(logical, Plus):
            raise ExprEvalError(f"FSum against non-sum {pretty(logical)}")
        leaves = flatten_plus(logical)
        if len(e.parts) != len(leaves):
            raise ExprEvalError(f"FSum has {len(e.parts)} parts for "
                                f"{len(leaves)} leaves")
        if e.tag_bits + e.payload_bits != n_qubits:
            raise ExprEvalError("FSum tag+payload does not fill the register")
        out = []
        for i, (part, leaf) in enumerate(zip(e.parts, leaves)):
            wl = width(leaf)
            if wl > e.payload_bits:
                raise ExprEvalError(
                    f"FSum: leaf {i} needs {wl} payload wires but the sum "
                    f"declares {e.payload_bits}")
            lc = expr_eval(part, leaf, wl)
            scale = 1 << (e.payload_bits - wl)
            out.extend((i << e.payload_bits) | (c * scale) for c in lc)
        return tuple(out)

    if isinstance(e, FCompose):
        first = expr_eval(e.first, logical, n_qubits)
        # `second` must be a wire permutation applied after `first`.
        if isinstance(e.second, FWirePerm):
            sec = e.second
            if (len(sec.new_to_old) != n_qubits
                    or sorted(sec.new_to_old) != list(range(n_qubits))):
                raise ExprEvalError(
                    f"FCompose: second stage {sec.new_to_old} is not a "
                    f"permutation of {n_qubits} wires")
            return tuple(permute_index(c, sec.new_to_old, n_qubits)
                         for c in first)
        raise ExprEvalError("FCompose second stage must be a wire permutation")

    if isinstance(e, FTagCondPerm):
        raise ExprEvalError("FTagCondPerm requires explicit sector codes")

    raise ExprEvalError(f"unknown expression {e!r}")


# ---------------------------------------------------------------------------
# Frame
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Frame:
    """An exact embedding of a logical interface into a physical register."""

    logical: Ty
    n_qubits: int
    codes: Tuple[int, ...]
    expr: FrameExpr = field(default=None, compare=False)
    label: str = field(default="", compare=False)
    sectors: Tuple[Sector, ...] = field(default=(), compare=False)
    ports: Tuple[Port, ...] = field(default=(), compare=False)

    def __post_init__(self):
        if not isinstance(self.n_qubits, int) or self.n_qubits < 0:
            raise ValueError(f"Frame {self.label}: bad n_qubits "
                             f"{self.n_qubits!r}")
        dim_phys = 1 << self.n_qubits
        for c in self.codes:
            if not isinstance(c, int) or isinstance(c, bool):
                raise ValueError(f"Frame {self.label}: non-integer code {c!r}")
            if not (0 <= c < dim_phys):
                raise ValueError(
                    f"Frame {self.label}: code {c} outside register of "
                    f"{self.n_qubits} qubits")
        if len(set(self.codes)) != len(self.codes):
            raise ValueError(f"Frame {self.label}: codes are not distinct")

        expected = semantic_dim(self.logical)
        if len(self.codes) != expected:
            raise ValueError(
                f"Frame {self.label}: {len(self.codes)} codes but "
                f"{pretty(self.logical)} has semantic dimension {expected}")

        seen_tags, covered = set(), []
        for sec in self.sectors:
            clash = seen_tags & set(sec.tag_values)
            if clash:
                raise ValueError(
                    f"Frame {self.label}: sector tag(s) {sorted(clash)} "
                    f"claimed by more than one sector")
            seen_tags |= set(sec.tag_values)
            if not set(sec.codes) <= set(self.codes):
                raise ValueError(
                    f"Frame {self.label}: sector {sec.index} has codes "
                    f"outside the frame")
            if len(sec.codes) != semantic_dim(sec.logical):
                raise ValueError(
                    f"Frame {self.label}: sector {sec.index} has "
                    f"{len(sec.codes)} codes but dimension "
                    f"{semantic_dim(sec.logical)}")
            covered.extend(sec.codes)

        if self.sectors:
            # Disjoint and exhaustive over the frame's codes.
            if len(covered) != len(set(covered)):
                raise ValueError(
                    f"Frame {self.label}: sectors overlap")
            if set(covered) != set(self.codes):
                missing = sorted(set(self.codes) - set(covered))
                raise ValueError(
                    f"Frame {self.label}: sectors are not exhaustive; "
                    f"codes {missing} belong to no sector")
            # Sectors may GROUP leaves (one sector per declared summand, each
            # spanning several leaves), so their count need not equal the leaf
            # count. Disjointness, exhaustiveness and per-sector dimension are
            # already enforced above, and tag sets record the grouping.
            if isinstance(self.logical, Plus):
                if len(self.sectors) > len(flatten_plus(self.logical)):
                    raise ValueError(
                        f"Frame {self.label}: {len(self.sectors)} sectors "
                        f"exceed {len(flatten_plus(self.logical))} leaves")

        for port in self.ports:
            for tag, _ in port.by_sector:
                if self.sectors and tag not in seen_tags:
                    raise ValueError(
                        f"Frame {self.label}: port {port.name} conditions on "
                        f"sector tag {tag}, which has no sector")
            for w in port.all_wires():
                if w >= self.n_qubits:
                    raise ValueError(
                        f"Frame {self.label}: port {port.name} references "
                        f"wire {w} beyond {self.n_qubits} qubits")

    # -- expression validation ---------------------------------------------

    def validate_expr(self) -> bool:
        """True iff `expr` evaluates EXACTLY to `codes`.

        Fail-closed: an expression that cannot be evaluated is not valid. Only
        `FOpaque` (and a frame with no expression) is exempt, and such a frame
        is simply ineligible for any symbolic fast path.
        """
        if self.expr is None or isinstance(self.expr, FOpaque):
            return False
        try:
            return expr_eval(self.expr, self.logical, self.n_qubits) == self.codes
        except ExprEvalError:
            return False

    def has_fast_path(self) -> bool:
        """Whether a fast path may consume `expr` -- i.e. it validates."""
        return self.validate_expr()

    # -- basic queries ------------------------------------------------------

    @property
    def dim(self) -> int:
        """Semantic dimension (number of valid codewords)."""
        return len(self.codes)

    @property
    def completed_dimension(self) -> int:
        """`dim` completed by each distinct live context/residual factor."""
        return completed_dimension(self)

    def encode(self, label: int) -> int:
        """Physical basis index of semantic basis label `label`."""
        return self.codes[label]

    def decode(self, phys: int) -> Optional[int]:
        """Semantic label for a physical index, or None if outside the code."""
        try:
            return self.codes.index(phys)
        except ValueError:
            return None

    def isometry(self) -> np.ndarray:
        """u : C^dim -> C^(2^n), with u[codes[i], i] = 1."""
        u = np.zeros((1 << self.n_qubits, self.dim), dtype=complex)
        for i, c in enumerate(self.codes):
            u[c, i] = 1.0
        return u

    def unused_codes(self) -> Tuple[int, ...]:
        used = set(self.codes)
        return tuple(i for i in range(1 << self.n_qubits) if i not in used)

    def is_identity_embedding(self) -> bool:
        """True when codes are exactly 0..dim-1 — a *flat prefix*, which says
        nothing about agreement with another frame. Use `frames_agree` for the
        zero-cost splice decision."""
        return self.codes == tuple(range(self.dim))

    # -- serialization ------------------------------------------------------

    def to_json(self) -> dict:
        return {
            "logical": ty_to_json(self.logical),
            "n_qubits": self.n_qubits,
            "codes": list(self.codes),
            "label": self.label,
            "expr": expr_to_json(self.expr),
            "sectors": [sec.to_json() for sec in self.sectors],
            "ports": [prt.to_json() for prt in self.ports],
        }

    @staticmethod
    def from_json(j: dict) -> "Frame":
        return Frame(
            logical=ty_from_json(j["logical"]),
            n_qubits=int(j["n_qubits"]),
            codes=tuple(int(c) for c in j["codes"]),
            expr=expr_from_json(j.get("expr")),
            label=j.get("label", ""),
            sectors=tuple(Sector.from_json(x) for x in j.get("sectors", [])),
            ports=tuple(Port.from_json(x) for x in j.get("ports", [])),
        )

    def __repr__(self) -> str:
        shown = list(self.codes[:8]) + (["..."] if self.dim > 8 else [])
        return (f"Frame({self.label or pretty(self.logical)}, "
                f"n={self.n_qubits}, dim={self.dim}, codes={shown})")


# ---------------------------------------------------------------------------
# Canonical frame construction
# ---------------------------------------------------------------------------

def canonical_frame(ty: Ty, label: str = "") -> Frame:
    """The canonical frame of a type: flat maximal-connected-sum for Plus,
    positional tensor for Ten. This is Invariant L's layout, made explicit as
    an embedding rather than only as a width."""
    codes, expr = _canonical_codes(ty)
    return Frame(logical=ty, n_qubits=width(ty), codes=tuple(codes),
                 expr=expr, label=label or pretty(ty))


def _canonical_codes(ty: Ty):
    if isinstance(ty, Unit):
        return [0], FIdentity(0)

    if isinstance(ty, Q):
        return [0, 1], FIdentity(1)

    if isinstance(ty, Ten):
        lc, le = _canonical_codes(ty.left)
        rc, re_ = _canonical_codes(ty.right)
        nb = width(ty.right)
        codes = [(a << nb) | b for a in lc for b in rc]
        return codes, FTensor(le, re_)

    if isinstance(ty, Plus):
        leaves = flatten_plus(ty)
        pw = payload_width(ty)
        parts, codes = [], []
        for i, leaf in enumerate(leaves):
            lc, le = _canonical_codes(leaf)
            parts.append(le)
            # A leaf's payload occupies the FIRST width(leaf) of the pw shared
            # payload wires, i.e. the high-order bits of the payload field.
            scale = 1 << (pw - width(leaf))
            codes.extend((i << pw) | (c * scale) for c in lc)
        return codes, FSum(tuple(parts), tag_width(ty), pw)

    if isinstance(ty, Arrow):
        # width(A -o B) = width(A) + width(B): the function is its wire bundle.
        lc, le = _canonical_codes(ty.dom)
        rc, re_ = _canonical_codes(ty.cod)
        nb = width(ty.cod)
        return [(a << nb) | b for a in lc for b in rc], FTensor(le, re_)

    if isinstance(ty, Dual):
        return _canonical_codes(ty.ty)

    raise TypeError(f"canonical_frame: unsupported type {ty!r}")


def tensor_frame(left: Frame, right: Frame, label: str = "") -> Frame:
    """The positional tensor frame [left | right].

    This is the frame `DatatypeControl` uses — [D_tag | A payload] — and it is
    deliberately NOT the flat-sum frame of the isomorphic type. Both are valid
    embeddings of the same interface; Align reconciles them.
    """
    nb = right.n_qubits
    codes = tuple((a << nb) | b for a in left.codes for b in right.codes)
    # The right operand's wires sit AFTER the left operand's, so its ports
    # must be shifted; leaving them unshifted makes two operands appear to
    # claim the same physical wires.
    shifted = tuple(
        Port(f"r.{pt.name}", pt.logical,
             tuple(w + left.n_qubits for w in pt.wires), pt.role,
             tuple((tg, tuple(w + left.n_qubits for w in ws))
                   for tg, ws in pt.by_sector),
             owner_id=pt.owner_id, cut_id=pt.cut_id,
             origin_cut=pt.origin_cut)
        for pt in right.ports)
    lports = tuple(Port(f"l.{pt.name}", pt.logical, pt.wires, pt.role,
                        pt.by_sector,
                        owner_id=pt.owner_id, cut_id=pt.cut_id,
                        origin_cut=pt.origin_cut)
                   for pt in left.ports)
    return Frame(
        logical=Ten(left.logical, right.logical),
        n_qubits=left.n_qubits + right.n_qubits,
        codes=codes,
        expr=FTensor(left.expr, right.expr),
        label=label or f"({left.label} (x) {right.label})",
        ports=lports + shifted,
    )


def flat_frame(ty: Ty, n_qubits: int, label: str = "") -> Frame:
    """The flat frame of an interface: codes 0..dim-1 in an n-qubit register.

    Used to express the *other* legitimate encoding of an interface whose
    canonical frame is positional — e.g. Ten(Z3,Z3) has canonical codes
    [0,1,2,4,5,6,8,9,10] but flat codes [0..8] in the same 4 qubits.
    """
    dim = canonical_frame(ty).dim
    if dim > (1 << n_qubits):
        raise ValueError(
            f"flat_frame: dimension {dim} exceeds register of {n_qubits} qubits")
    return Frame(logical=ty, n_qubits=n_qubits, codes=tuple(range(dim)),
                 expr=FIdentity(n_qubits), label=label or f"flat({pretty(ty)})")


def embeddings_agree(a: "Frame", b: "Frame") -> bool:
    """Embedding equality: same register, same physical codes.

    This is the zero-cost splice condition. It deliberately does NOT compare
    logical types: a producer and consumer may present associativity-related
    interfaces -- Ten(Q, Ten(Q,Q)) against Ten(Ten(Q,Q), Q) -- which denote
    the same embedding, and interface compatibility is type_of's job. What
    Align must reconcile is a difference in CODES.
    """
    return a.n_qubits == b.n_qubits and a.codes == b.codes


def frames_agree(a: Frame, b: Frame) -> bool:
    """Embedding equality -- the zero-cost splice condition.

    Two frames agree when they embed the same interface into the same register
    at the same physical indices. `is_identity_embedding` is NOT this test: it
    only says a frame's codes form a flat prefix, which two frames can both do
    while still disagreeing about which wires carry what.
    """
    return (a.logical == b.logical
            and a.n_qubits == b.n_qubits
            and a.codes == b.codes)


# ---------------------------------------------------------------------------
# Semantic action and leakage (the acceptance-test harness)
# ---------------------------------------------------------------------------

def semantic_action(frame_in: Frame, G: np.ndarray, frame_out: Frame) -> np.ndarray:
    """U_sem = (u_out)^dagger G u_in, compared EXACTLY (no phase quotient)."""
    u_in = frame_in.isometry()
    u_out = frame_out.isometry()
    expected = 1 << frame_in.n_qubits
    if G.shape != (expected, expected):
        raise ValueError(
            f"semantic_action: G is {G.shape} but frame_in has "
            f"{frame_in.n_qubits} qubits (expected {(expected, expected)})")
    return u_out.conj().T @ G @ u_in


def leakage(frame_in: Frame, G: np.ndarray, frame_out: Frame) -> float:
    """||(I - u_out u_out^dagger) G u_in|| — must vanish on the code space."""
    u_in = frame_in.isometry()
    u_out = frame_out.isometry()
    proj_out = u_out @ u_out.conj().T
    residual = (np.eye(proj_out.shape[0]) - proj_out) @ G @ u_in
    return float(np.linalg.norm(residual))


def assert_framed_semantics(frame_in: Frame, G: np.ndarray, frame_out: Frame,
                            expected: np.ndarray, *, atol: float = 1e-10):
    """Exact framed-semantics check plus zero leakage."""
    leak = leakage(frame_in, G, frame_out)
    if leak >= atol:
        raise AssertionError(
            f"leakage {leak:.3e} out of the valid code space "
            f"({frame_in.label} -> {frame_out.label})")
    got = semantic_action(frame_in, G, frame_out)
    # rtol=0: exact comparison, no phase quotient and no relative slack.
    if not np.allclose(got, expected, atol=atol, rtol=0.0):
        raise AssertionError(
            f"framed semantics mismatch ({frame_in.label} -> "
            f"{frame_out.label})\n  got:\n{np.round(got, 6)}\n"
            f"  expected:\n{np.round(expected, 6)}")


# ---------------------------------------------------------------------------
# Transported frames: what a zero-gate structural iso actually produces
# ---------------------------------------------------------------------------

def distl_transported_frame(a: Ty, b: Ty, c: Ty, label: str = "") -> Frame:
    """The output frame `dist_l : (A+B)(x)C -> (A(x)C)+(B(x)C)` transports.

    dist_l moves no data, so its output keeps the *input* wire layout
    [tag | shared payload | C]: C stays on the low wire and the narrower
    summand leaves the wider summand's extra payload wires unused. The
    canonical frame of the codomain instead packs each summand contiguously.

    For A = C = QBool, B = QBool (x) QBool:

        transported (this)          (0, 1, 4, 5, 8, 9, 10, 11, 12, 13, 14, 15)
        canonical consumer          (0, 2, 4, 6, 8, 9, 10, 11, 12, 13, 14, 15)

    Same interface, same register, same dimension, different embedding. This
    is the unequal-width distributivity mismatch, made explicit rather than
    silently miscompiled; Align reconciles the two.
    """
    cod = Plus(Ten(a, c), Ten(b, c))
    pw = payload_width(cod)
    wc = width(c)
    codes, sectors = [], []
    for i, summand in enumerate(((a, c), (b, c))):
        s_ty, c_ty = summand
        sect, ws = [], width(s_ty)
        for sv in canonical_frame(s_ty).codes:
            for cv in canonical_frame(c_ty).codes:
                # summand payload keeps the HIGH payload wires; C keeps the
                # LOW wires; wires between them are the wider summand's, and
                # are unused for the narrower one.
                sect.append((i << pw) | (sv << (pw - ws)) | cv)
        sectors.append(Sector(index=i, logical=Ten(s_ty, c_ty),
                              codes=tuple(sect), tag_values=(i,)))
        codes.extend(sect)
    return Frame(logical=cod, n_qubits=width(cod), codes=tuple(codes),
                 expr=FOpaque("dist_l transported layout"),
                 label=label or "dist_l transported",
                 sectors=tuple(sectors))


# ---------------------------------------------------------------------------
# Truthful frames: pending permutations and spectator registers
# ---------------------------------------------------------------------------

def apply_wire_perm(frame: "Frame", new_to_old, label: str = "") -> "Frame":
    """The frame after a wire permutation is applied to the register.

    A compiled artifact may carry a PENDING permutation instead of emitting
    SWAPs. That permutation is semantics, so it must appear in the boundary
    frame: otherwise the frames claim identity while the artifact permutes,
    and framed semantics silently reports the wrong operator. This is how
    WirePerm is actually demoted to an optimisation -- the frame stays
    authoritative whether or not the perm was materialised.
    """
    n = frame.n_qubits
    if sorted(new_to_old) != list(range(n)):
        raise ValueError(f"apply_wire_perm: {new_to_old} is not a permutation "
                         f"of {n} wires")
    codes = tuple(permute_index(c, new_to_old, n) for c in frame.codes)
    sectors = tuple(
        Sector(sec.index, sec.logical,
               tuple(permute_index(c, new_to_old, n) for c in sec.codes),
               sec.tag_values)
        for sec in frame.sectors)
    inv = [0] * n
    for j, o in enumerate(new_to_old):
        inv[o] = j
    ports = tuple(
        Port(prt.name, prt.logical,
             tuple(inv[w] for w in prt.wires), prt.role,
             tuple((t, tuple(inv[w] for w in ws)) for t, ws in prt.by_sector),
             owner_id=prt.owner_id, cut_id=prt.cut_id,
             origin_cut=prt.origin_cut)
        for prt in frame.ports)
    return Frame(logical=frame.logical, n_qubits=n, codes=codes,
                 expr=FCompose(frame.expr, FWirePerm(tuple(new_to_old))),
                 label=label or f"{frame.label}+perm",
                 sectors=sectors, ports=ports)


def with_spectators(frame: "Frame", n_qubits: int, *,
                    residual_name: str = "ancilla",
                    residual_ty: Optional[Ty] = None,
                    role: str = "residual",
                    label: str = "") -> "Frame":
    """Widen a frame to a larger register, recording the extra coordinates as
    a residual port.

    Used where the artifact's register is genuinely wider than the logical
    interface -- e.g. EncodeQubit compiles into two wires while its interface
    names one. Claiming the narrow frame would misdescribe the artifact.
    The logical codes keep their values, i.e. the spectators are the LOW wires
    held at |0>.
    """
    extra = n_qubits - frame.n_qubits
    if extra < 0:
        raise ValueError("with_spectators: target register is narrower")
    if extra == 0:
        return frame
    codes = tuple(c << extra for c in frame.codes)
    sectors = tuple(Sector(s.index, s.logical, tuple(c << extra for c in s.codes),
                           s.tag_values) for s in frame.sectors)
    resid = Port(residual_name, residual_ty if residual_ty is not None else Unit(),
                 tuple(range(frame.n_qubits, n_qubits)), role=role)
    ports = tuple(frame.ports) + (resid,)
    return Frame(logical=frame.logical, n_qubits=n_qubits, codes=codes,
                 expr=FOpaque("widened with spectator register"),
                 label=label or f"{frame.label}+spectators",
                 sectors=sectors, ports=ports)


def _sum_side_frames(a: Ty, b: Ty, c: Ty, *, right: bool):
    """The shared gate-free layout for a distributor, at the SUM side's width.

    A distributor moves no data: it reinterprets one physical layout under two
    different logical types. Both boundaries therefore get the SAME codes, and
    the residual mismatch against a canonical consumer is resolved at the
    SPLICE by Align -- never inside the distributor.

    Two orientations, mirror images of each other:

        right=False   dist_l : (A + B) (x) C -> (A(x)C) + (B(x)C)
                      layout  [ tag | summand payload | C ]
        right=True    dist_r : A (x) (B + C) -> (A(x)B) + (A(x)C)
                      layout  [ tag | A | summand payload ]

    Sizing from the judgment types instead gives a 5-qubit domain against a
    4-qubit codomain and wrongly suggests no gate-free distributor exists; the
    width here comes from the selected layout, which is the sum side's.
    """
    if right:
        fixed, summands = a, (b, c)
        dom = Ten(a, Plus(b, c))
        cod = Plus(Ten(a, b), Ten(a, c))
    else:
        fixed, summands = c, (a, b)
        dom = Ten(Plus(a, b), c)
        cod = Plus(Ten(a, c), Ten(b, c))

    n = width(cod)
    pw = payload_width(cod)
    wf = width(fixed)
    fixed_codes = canonical_frame(fixed).codes

    # ONE physical layout, addressed by (tag, fixed value, summand value).
    def phys(i, fv, sv, ws):
        if right:
            # [ tag | A (high) | summand payload (low) ]
            return (i << pw) | (fv << (pw - wf)) | sv
        # [ tag | summand payload (high) | C (low) ]
        return (i << pw) | (sv << (pw - ws)) | fv

    sum_codes, sectors = [], []
    for i, summand in enumerate(summands):
        ws = width(summand)
        sc = canonical_frame(summand).codes
        if right:
            sect = [phys(i, fv, sv, ws) for fv in fixed_codes for sv in sc]
            logical = Ten(fixed, summand)
        else:
            sect = [phys(i, fv, sv, ws) for sv in sc for fv in fixed_codes]
            logical = Ten(summand, fixed)
        sum_codes.extend(sect)
        sectors.append(Sector(i, logical, tuple(sect), (i,)))
    sum_codes = tuple(sum_codes)

    # The two readings enumerate their semantic labels in DIFFERENT orders,
    # so they do not in general share a code list -- a frame's codes[k] is the
    # physical index of ITS OWN k-th label.
    #
    #   dist_l   dom (A+B)(x)C   : summand outer, C inner
    #            cod (A(x)C)+(B(x)C): summand outer, C inner   -- coincide
    #   dist_r   dom A(x)(B+C)   : A outer, summand inner
    #            cod (A(x)B)+(A(x)C): summand outer, A inner   -- DIFFER
    #
    # Getting this wrong makes dist_r silently the identity on labels instead
    # of the canonical iso; the zero-gate circuit then computes the wrong map
    # while every same-codes assertion still passes.
    if right:
        tensor_codes = tuple(
            phys(i, fv, sv, width(sm))
            for fv in fixed_codes
            for i, sm in enumerate(summands)
            for sv in canonical_frame(sm).codes)
    else:
        tensor_codes = sum_codes

    # `sectors` describe the tag-conditioned decomposition of a SUM frame; the
    # tensor reading has no top-level sum, so it declares none.
    tensor_frame_codes, sum_frame_codes = tensor_codes, sum_codes

    tag_port = Port("tag", Plus(*summands), (0,), role="tag")
    # A zero-width fixed factor (e.g. dist_r with A = I) occupies no wires at
    # all, so it declares no port -- an empty placement is not a placement.
    if right:
        # A is at a fixed placement; the summand payload is not -- its width
        # differs per sector, so its wires are sector-conditioned.
        fixed_ports = ((Port("A", fixed, tuple(range(1, 1 + wf)),
                             role="payload"),) if wf > 0 else ())
        s_port = Port("summand", Plus(*summands), (), role="payload",
                      by_sector=tuple((i, tuple(range(n - width(sm), n)))
                                      for i, sm in enumerate(summands)))
    else:
        fixed_ports = ((Port("C", fixed, tuple(range(n - wf, n)),
                             role="payload"),) if wf > 0 else ())
        s_port = Port("summand", Plus(*summands), (), role="payload",
                      by_sector=tuple((i, tuple(range(1, 1 + width(sm))))
                                      for i, sm in enumerate(summands)))

    label = "dist_r" if right else "dist_l"
    desc = ("dist_r shared layout [tag | A | payload]" if right
            else "dist_l shared layout [tag | payload | C]")
    ports = (tag_port, s_port) + fixed_ports
    fin = Frame(logical=dom, n_qubits=n, codes=tensor_frame_codes,
                expr=FOpaque(desc), label=label + " in", ports=ports)
    fout = Frame(logical=cod, n_qubits=n, codes=sum_frame_codes,
                 expr=FOpaque(desc), label=label + " out",
                 sectors=tuple(sectors), ports=ports)
    return fin, fout


def distl_frames(a: Ty, b: Ty, c: Ty):
    """Shared gate-free frames for `dist_l`. See `_sum_side_frames`."""
    return _sum_side_frames(a, b, c, right=False)


def distr_frames(a: Ty, b: Ty, c: Ty):
    """Shared gate-free frames for `dist_r`. See `_sum_side_frames`."""
    return _sum_side_frames(a, b, c, right=True)


class UnsupportedFrame(Exception):
    """A frame situation the backend cannot represent yet.

    Raised BEFORE emission, so no partial circuit or output is produced.
    """


def encode_qubit_frames():
    """Explicit frames for the legacy one-hot Encode/Decode pair.

    Q -> I+I in two wires: |0> maps to |10> (code 2) and |1> to |01> (code 1).
    The input keeps its qubit on the high wire with the ancilla at |0>, so its
    codes are (0, 2). These must be SELECTED, not inferred by widening a
    one-qubit frame -- widening preserves codes, and the one-hot output does
    not have the input's codes.
    """
    q1 = Port("q", Q(), (0,), role="main")
    anc = Port("ancilla", Unit(), (1,), role="residual")
    fin = Frame(logical=Q(), n_qubits=2, codes=(0, 2),
                expr=FOpaque("Q with ancilla at |0> on the low wire"),
                label="encode in", ports=(q1, anc))
    fout = Frame(logical=Plus(Unit(), Unit()), n_qubits=2, codes=(2, 1),
                 expr=FOpaque("one-hot: |0>->|10>, |1>->|01>"),
                 label="encode out",
                 sectors=(Sector(0, Unit(), (2,), (0,)),
                          Sector(1, Unit(), (1,), (1,))))
    return fin, fout


def distributor_iso(a: Ty, b: Ty, c: Ty, ctor: str) -> Tuple[int, ...]:
    """The canonical distributivity relabelling, as `iso[k] = j`.

    Derived from the shared layout rather than restated: two readings of ONE
    physical layout induce the iso by "same physical code". Domain label k and
    codomain label j denote the same state exactly when their codes agree.
    """
    right = ctor in ("DistR", "UndistR")
    fin, fout = _sum_side_frames(a, b, c, right=right)
    if ctor.startswith("Undist"):
        fin, fout = fout, fin
    pos = {code: j for j, code in enumerate(fout.codes)}
    return tuple(pos[code] for code in fin.codes)


def distributor_frames(a: Ty, b: Ty, c: Ty, ctor: str):
    """Shared gate-free frames for any of the four distributors.

    Undist* are the inverses of Dist*, so they select the SAME physical
    layout with the two logical readings exchanged.
    """
    right = ctor in ("DistR", "UndistR")
    fin, fout = _sum_side_frames(a, b, c, right=right)
    if ctor.startswith("Undist"):
        fin, fout = fout, fin
    return fin, fout


# ---------------------------------------------------------------------------
# Occurrence placement (Stage G1: data model only -- nothing consults it yet)
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class TypedBinding:
    """An ambient resource the occurrence does not own but must carry.

    `name` is a LOOKUP KEY only. Identity is `owner_id`; the type is used to
    validate a recorded binding (its width must match its wires), never to
    invent an owner or a placement.
    """
    name: str
    logical: Ty
    wires: Tuple[int, ...]
    owner_id: str
    intro_cut: str
    # The resource's ORDERED local encoding, recorded here at introduction.
    # A consumer must never manufacture one: range(1 << len(wires)) densifies
    # a sparse resource -- Plus(Q,I) is dimension 3 on two wires, not 4.
    # Supplied explicitly for a derivation-selected binding; for the legacy
    # public `env={name: wires}` boundary it is the type's canonical
    # encoding, fixed here rather than rediscovered later.
    codes: Tuple[int, ...] = ()

    def __post_init__(self):
        from lang.types import width as _w
        if not self.codes:
            object.__setattr__(self, "codes",
                               tuple(canonical_frame(self.logical).codes))
        if len(set(self.codes)) != len(self.codes):
            raise ProvenanceError(
                f"binding {self.name!r} repeats a code in {self.codes}")
        _sd = semantic_dim(self.logical)
        if len(self.codes) != _sd:
            raise ProvenanceError(
                f"binding {self.name!r} of type {pretty(self.logical)} has "
                f"semantic dimension {_sd} but records {len(self.codes)} "
                f"codes")
        for c in self.codes:
            if not (0 <= c < (1 << len(self.wires))):
                raise ProvenanceError(
                    f"binding {self.name!r}: code {c} outside its own "
                    f"{len(self.wires)}-wire space")
        if len(set(self.wires)) != len(self.wires):
            raise ProvenanceError(
                f"binding {self.name!r} claims a wire twice: {self.wires}")
        if _w(self.logical) != len(self.wires):
            raise ProvenanceError(
                f"binding {self.name!r} is {pretty(self.logical)} of width "
                f"{_w(self.logical)} but occupies {len(self.wires)} wires "
                f"{self.wires}")
        if not self.owner_id or not self.intro_cut:
            raise ProvenanceError(
                f"binding {self.name!r} carries no owner/introduction cut")


@dataclass(frozen=True, slots=True)
class ChartFactor:
    """One factor of a boundary chart, with its own identity.

    `codes` are the factor's OWN ordered codes in its OWN premise-local
    address space. Two factors from different artifacts may both start at
    local wire 0; that is not a collision, it is two namespaces.

    `role` and `logical` are the DERIVATION-LEVEL discriminators. A variable
    spine accumulates operand factors and carries exactly one terminal
    residual yank, and the terminal one is identified by its recorded role
    and its logical type -- never by its name, its dimension, its wire count
    or its position being "last but one". Two factors of equal dimension can
    be an operand and a residual of different types, which is exactly the
    ctrl_ho trap: S_h (x) Y_Endo and S_h (x) S_y (x) Y_Q are both dimension
    16 and are different charts.
    """
    name: str
    owner: object                 # the artifact / premise this factor is of
    n_qubits: int
    codes: Tuple[int, ...]
    role: str = "operand"         # "operand" | "residual" | "block"
    logical: object = None        # the factor's derivation-level type
    # For role="block" only: the identity of the already-constructed direct
    # sum this factor aggregates. A block is NEITHER an operand nor a
    # source-typed residual, so typed residual matching must skip it.
    descriptor: object = None
    # THE FACTOR'S OWN IDENTITY, distinct from `owner`.
    #
    # `owner` says which RESOURCE this factor carries; two different factors
    # can carry the same resource, and a frame-default factor carries no
    # resource at all (owner None, logical None) yet still has to be
    # nameable. `factor_id` is minted where the factor is ISSUED, is
    # collision-free among its siblings, and is the same on both polarities
    # when the two present one factor lineage. It is never derived from a
    # type, a width, a code, a wire overlap or a Python object identity --
    # all of which two distinct factors can share.
    factor_id: str = ""
    # THE SOURCE OCCURRENCE this factor descends from.
    #
    # `owner` names a RESOURCE, `factor_id` names THIS factor, and `source`
    # names the derivation occurrence the factor's content came from. It is
    # what makes a factor classifiable: the same emitted factor kind is
    # payload in one branch and carried context in another, and only its
    # ancestry says which. Nothing may classify from a name, a role, a type,
    # a dimension or a placement.
    source: object = None

    @property
    def dim(self) -> int:
        return len(self.codes)

    def __post_init__(self):
        if not self.factor_id:
            raise ProvenanceError(
                f"chart factor {self.name!r} was issued without a factor_id; "
                f"a factor that cannot be named cannot be matched at a cut")
        if self.role not in ("operand", "residual", "block"):
            raise ProvenanceError(
                f"chart factor {self.name!r} has role {self.role!r}; a spine "
                f"factor is an operand or the terminal residual, and an "
                f"aggregate direct sum is a block")
        if self.role == "block":
            d = self.descriptor
            if d is None:
                raise ProvenanceError(
                    f"chart factor {self.name!r} is a block but records no "
                    f"descriptor")
            if self.logical is not None:
                raise ProvenanceError(
                    f"block factor {self.name!r} carries a logical type "
                    f"{self.logical!r}; a direct sum is not a source-typed "
                    f"residual")
            if self.owner != d.cut_id:
                raise ProvenanceError(
                    f"block factor {self.name!r} is owned by {self.owner!r} "
                    f"but its descriptor records {d.cut_id!r}")
            want = sum(d.block_dims)
            if len(self.codes) != want:
                raise ProvenanceError(
                    f"block factor {self.name!r} has dimension "
                    f"{len(self.codes)} but its blocks sum to {want}")
            if self.n_qubits != d.block_width:
                raise ProvenanceError(
                    f"block factor {self.name!r} spans {self.n_qubits} wires "
                    f"but its descriptor records {d.block_width}")


@dataclass(frozen=True, slots=True)
class ChartRoute:
    """The recorded r^+- of a boundary chart: Repart_r( Par(parts...) ).

    `embed` is AUTHORITATIVE and is the whole of the encoding: it is the one
    joint injective map

        (head coordinate, tail coordinate)  ->  ambient code

    lexicographic in the ordered `parts`. It is deliberately not a pair of raw
    wire groups, because after Repart the joint encoding may be correlated and
    need not be expressible as disjoint wire tuples.

    `kind` says which Repart was scheduled, and therefore whether `embed` can
    be RECOMPUTED from the schedule rather than merely compared with itself:

      "scatter"  each factor was laid on its own ambient wires, so
                 `placements` is the schedule and the codes can be rebuilt
                 from it independently of `embed`.
      "opaque"   some other Repart. `embed` is then the only description
                 there is; reconstruction is unavailable and says so.

    `placements` is the scatter schedule and NOTHING MORE. For a correlated
    Repart it is empty, and it must never be read as defining the chart's
    support or its complement in general -- only a scatter licenses that,
    and only because the scatter schedule says so.
    """
    label: str = ""
    parts: Tuple[ChartFactor, ...] = ()     # ordered factor identities
    embed: Tuple[int, ...] = ()             # product index -> ambient code
    kind: str = "opaque"
    placements: Tuple[Tuple[int, ...], ...] = ()
    n_qubits: int = 0

    @property
    def reconstructible(self) -> bool:
        return self.kind == "scatter" and len(self.placements) == len(self.parts)

    def decode(self, product_index):
        """The ordered factor coordinates for a product index.

        Mixed radix over the ordered `parts`, FIRST factor most significant,
        so the spine's application order is what the index means.
        """
        if not self.parts:
            raise ProvenanceError("route carries no factors")
        out = []
        for f in reversed(self.parts):
            product_index, r = divmod(product_index, f.dim)
            out.append(r)
        if product_index:
            raise ProvenanceError(
                f"route {self.label}: product index out of range")
        return tuple(reversed(out))

    @property
    def operands(self):
        """The accumulated operand factors, in application order."""
        return tuple(f for f in self.parts if f.role == "operand")

    @property
    def residual(self):
        """The one terminal residual yank factor, by RECORDED ROLE.

        Not "the last one", not "the one whose dimension matches": a spine
        with the wrong terminal residual has the same length and can have the
        same dimension.
        """
        res = [f for f in self.parts if f.role == "residual"]
        if len(res) != 1:
            raise ProvenanceError(
                f"route {self.label}: {len(res)} residual factors, want "
                f"exactly one terminal yank")
        if self.parts[-1] is not res[0]:
            raise ProvenanceError(
                f"route {self.label}: the residual factor {res[0].name!r} is "
                f"not terminal; a spine ends in its result yank")
        return res[0]

    def is_spine(self) -> bool:
        """A canonical variable spine: operands then one terminal residual."""
        if not self.parts:
            return False
        if any(f.role != "operand" for f in self.parts[:-1]):
            return False
        return self.parts[-1].role == "residual"

    def check_schedule(self):
        """Widths, placement lengths, wire range and disjointness.

        These are properties of the RECORDED SCHEDULE alone. None of them
        consults `embed`, so none of them can be satisfied by a chart merely
        agreeing with itself.
        """
        if not self.parts:
            raise ProvenanceError(f"route {self.label}: no factors recorded")
        if self.n_qubits < 0:
            raise ProvenanceError(
                f"route {self.label}: negative register width "
                f"{self.n_qubits}")
        for f in self.parts:
            if f.dim == 0:
                raise ProvenanceError(f"route {self.label}: factor {f.name} "
                                      f"is empty")
            if len(set(f.codes)) != f.dim:
                raise ProvenanceError(
                    f"route {self.label}: factor {f.name} repeats a code")
            for c in f.codes:
                if not (0 <= c < (1 << f.n_qubits)):
                    raise ProvenanceError(
                        f"route {self.label}: factor {f.name} code {c} "
                        f"outside its own {f.n_qubits}-qubit space")
        if self.kind == "scatter":
            if len(self.placements) != len(self.parts):
                raise ProvenanceError(
                    f"route {self.label}: {len(self.placements)} placements "
                    f"for {len(self.parts)} factors")
            seen = set()
            for f, g in zip(self.parts, self.placements):
                if len(g) != f.n_qubits:
                    raise ProvenanceError(
                        f"route {self.label}: factor {f.name} is "
                        f"{f.n_qubits} qubits wide but its placement names "
                        f"{len(g)} wires {g}")
                for w in g:
                    if not (0 <= w < self.n_qubits):
                        raise ProvenanceError(
                            f"route {self.label}: placement wire {w} outside "
                            f"the {self.n_qubits}-qubit register")
                    if w in seen:
                        raise ProvenanceError(
                            f"route {self.label}: wire {w} is placed twice")
                    seen.add(w)
        elif self.placements:
            raise ProvenanceError(
                f"route {self.label}: a {self.kind!r} repart recorded "
                f"scatter placements; they would not describe it")
        return True

    def reconstruct(self):
        """Recompute the ambient codes FROM THE SCHEDULE.

        This is the independent check: it never reads `embed`, so an `embed`
        that does not come from the recorded schedule is caught instead of
        confirming itself.
        """
        if not self.reconstructible:
            raise ProvenanceError(
                f"route {self.label}: a {self.kind!r} repart cannot be "
                f"reconstructed from its schedule")
        n = self.n_qubits

        def _place(code, f, wires):
            c = 0
            for i, w in enumerate(wires):
                if (code >> (f.n_qubits - 1 - i)) & 1:
                    c |= 1 << (n - 1 - w)
            return c

        out = [0]
        for f, wires in zip(self.parts, self.placements):
            out = [base | _place(cd, f, wires) for base in out for cd in f.codes]
        return tuple(out)

    def decode_ambient(self, code):
        """(head coordinate, tail coordinate) read OUT OF THE AMBIENT CODE.

        Independent of the code's position in `embed`: the factor bits are
        extracted at the scheduled wires and looked up in each factor's own
        ordered codes.
        """
        if not self.reconstructible:
            raise ProvenanceError(
                f"route {self.label}: a {self.kind!r} repart cannot be "
                f"decoded from its schedule")
        n = self.n_qubits
        out = []
        for f, g in zip(self.parts, self.placements):
            v = 0
            for i, w in enumerate(g):
                v |= ((code >> (n - 1 - w)) & 1) << (f.n_qubits - 1 - i)
            if v not in f.codes:
                raise ProvenanceError(
                    f"route {self.label}: ambient code {code} carries {v} on "
                    f"factor {f.name}, which is not one of its codes "
                    f"{f.codes}")
            out.append(f.codes.index(v))
        return tuple(out)


@dataclass(frozen=True, slots=True)
class BoundaryChart:
    """A derivation-selected boundary chart, ALONGSIDE the logical Frame.

    Frame keeps its logical interface and its cardinality invariant: for
    `h y` the result type stays Q (dim 2). The selected chart is a different
    object of dimension 4 = S_y (x) Y_Q, so neither has to lie about the other.

    `codes` is ORDERED, and the order is what encodes the factorisation --
    reading it as an unordered set loses exactly the distinction between
    U_y (x) yank_Q and yank_Q (x) U_y.
    """
    n_qubits: int
    codes: Tuple[int, ...]
    route: Optional[ChartRoute] = None
    label: str = ""
    space: str = "local"     # "local": premise-local addresses; "ambient":
                             # already placed in the compiled register
    # Every ambient coordinate this COMPLETE chart claims: main/tag/payload,
    # carried context, residual factors, and constant tag coordinates that
    # are part of the embedding. Declared spectators are excluded.
    #
    # This is NOT the cut-facing interface -- an open sum's completed chart
    # claims nine coordinates while its typed cut is three of them -- and it
    # is never `range(register)` for want of a better answer, nor inferred
    # from which bits happen to vary.
    support_wires: Optional[Tuple[int, ...]] = None

    @property
    def dim(self) -> int:
        return len(self.codes)

    def support(self, where=""):
        """The recorded support, or the one the route provably determines.

        A scatter route IS a recorded placement schedule, so its union is a
        record, not a guess. Anything else -- an opaque or correlated ambient
        chart -- has to carry its support explicitly, because nothing about
        it says which coordinates it claims.
        """
        if self.support_wires is not None:
            return tuple(self.support_wires)
        if self.route is not None and self.route.reconstructible:
            return tuple(sorted({w for pl in self.route.placements
                                 for w in pl}))
        if self.space == "local":
            return tuple(range(self.n_qubits))
        raise ProvenanceError(
            f"{where}chart {self.label!r} is an opaque ambient chart with no "
            f"recorded support, so which coordinates it claims is unknown; "
            f"the register's width is not an answer")

    def isometry(self):
        """The ordered embedding of the chart into the ambient register.

        Column j is the chart's j-th basis vector, so the ORDER of `codes`
        carries the factorisation -- which is what distinguishes
        U_y (x) yank_Q from yank_Q (x) U_y.
        """
        import numpy as _np
        M = _np.zeros((1 << self.n_qubits, len(self.codes)), dtype=complex)
        for j, c in enumerate(self.codes):
            M[c, j] = 1.0
        return M

    def decode(self, ambient_code):
        """Recover (head coordinate, tail coordinate) from an ambient code.

        Read out of the code's BITS at the scheduled wires when the Repart
        allows it; only an opaque Repart falls back to the code's position.
        """
        if self.route is None or not self.route.parts:
            raise ProvenanceError(f"chart {self.label}: no factor identities")
        if isinstance(self.route, JoinRoute):
            return self.route.decode(ambient_code)[0]
        if self.route.reconstructible:
            return self.route.decode_ambient(ambient_code)
        return self.route.decode(self.codes.index(ambient_code))

    def validate_joint(self):
        """Check the chart AGAINST ITS RECORDED SCHEDULE, not against itself.

        `embed` and `codes` come from the same construction, so comparing
        them proves nothing on its own. The load-bearing steps here are the
        schedule checks (widths, placement lengths, wire range, disjointness)
        and, when the Repart is reconstructible, recomputing the ambient
        codes from the schedule and decoding each code out of its bits.
        """
        r = self.route
        if r is None or not r.parts:
            raise ProvenanceError(f"chart {self.label}: no factored route")
        if isinstance(r, JoinRoute):
            # A RELATION validates row by row: every recorded row rebuilds
            # its ambient code from the recorded placements, and the chart
            # carries exactly the relation's codes. No product-dimension
            # claim applies -- a join is smaller than the product, and
            # saying otherwise is the degradation this type exists to stop.
            if r.n_qubits != self.n_qubits:
                raise ProvenanceError(
                    f"chart {self.label}: the relation is over {r.n_qubits} "
                    f"wires but the chart is over {self.n_qubits}")
            if tuple(r.codes) != tuple(self.codes):
                raise ProvenanceError(
                    f"chart {self.label}: the relation's codes do not "
                    f"reproduce chart.codes")
            for f, pl in zip(r.parts, r.placements):
                if len(pl) != f.n_qubits:
                    raise ProvenanceError(
                        f"chart {self.label}: factor {f.name!r} spans "
                        f"{f.n_qubits} wires but is placed on {len(pl)}")
            for row, c in zip(r.rows, r.codes):
                v = 0
                for coord, pl in zip(row, r.placements):
                    v |= scatter_code(coord, tuple(pl), self.n_qubits)
                if v != c:
                    raise ProvenanceError(
                        f"chart {self.label}: relation row {row} rebuilds to "
                        f"{v}, not the recorded code {c}")
            return True
        r.check_schedule()
        want = 1
        for f in r.parts:
            want *= f.dim
        if self.dim != want:
            raise ProvenanceError(
                f"chart {self.label}: dim {self.dim} != "
                f"{'*'.join(str(f.dim) for f in r.parts)}")
        if len(set(self.codes)) != len(self.codes):
            raise ProvenanceError(f"chart {self.label}: codes not injective")
        if r.n_qubits != self.n_qubits:
            raise ProvenanceError(
                f"chart {self.label}: the route is over {r.n_qubits} wires "
                f"but the chart is over {self.n_qubits}")
        for c in self.codes:
            if not (0 <= c < (1 << self.n_qubits)):
                raise ProvenanceError(
                    f"chart {self.label}: code {c} outside the register")
        if tuple(r.embed) != tuple(self.codes):
            raise ProvenanceError(
                f"chart {self.label}: the recorded route does not reproduce "
                f"chart.codes")
        if r.reconstructible:
            rebuilt = r.reconstruct()
            if rebuilt != tuple(self.codes):
                raise ProvenanceError(
                    f"chart {self.label}: rebuilding the recorded "
                    f"{r.kind} schedule gives {rebuilt}, not the chart's "
                    f"{tuple(self.codes)}")
            for j, c in enumerate(self.codes):
                if r.decode_ambient(c) != r.decode(j):
                    raise ProvenanceError(
                        f"chart {self.label}: code {c} decodes out of its "
                        f"bits as {r.decode_ambient(c)} but sits at product "
                        f"position {r.decode(j)}")
        return True

    def transport(self, new_to_old):
        """Carry an AMBIENT chart through a wire permutation.

        Exactly the frame rule (`apply_wire_perm`): new wire j reads what old
        wire `new_to_old[j]` carried. A premise-local chart has no ambient
        wires to move, so transporting one is refused rather than silently
        treated as a no-op.
        """
        if self.space != "ambient":
            raise ProvenanceError(
                f"chart {self.label}: only an ambient chart can be "
                f"transported, this one is {self.space!r}")
        n = self.n_qubits
        new_to_old = tuple(new_to_old)
        if sorted(new_to_old) != list(range(n)):
            raise ProvenanceError(
                f"chart {self.label}: {tuple(new_to_old)} is not a "
                f"permutation of {n} wires")
        codes = tuple(permute_index(c, new_to_old, n) for c in self.codes)
        route = self.route
        places = tuple(tuple(new_to_old.index(w) for w in g)
                       for g in route.placements) if route is not None else ()
        if isinstance(route, JoinRoute):
            # A relation moves with its register: the rows and their source
            # pairs are unchanged, only where the factors sit and what the
            # ambient codes are.
            route = replace(route, codes=codes, placements=places,
                            support=tuple(sorted(
                                new_to_old.index(w) for w in self.support())))
        elif route is not None:
            route = replace(route, embed=codes, placements=places)
        sup = self.support_wires
        if sup is not None:
            sup = tuple(new_to_old.index(w) for w in sup)
        return replace(self, codes=codes, route=route, support_wires=sup)

    def __post_init__(self):
        if len(set(self.codes)) != len(self.codes):
            raise ProvenanceError(
                f"chart {self.label}: codes are not distinct {self.codes}")
        for c in self.codes:
            if not (0 <= c < (1 << self.n_qubits)):
                raise ProvenanceError(
                    f"chart {self.label}: code {c} outside a "
                    f"{self.n_qubits}-qubit register")
        # ... and the recorded support, in the SAME hook. Two __post_init__
        # definitions in one class silently keep only the last, which is how
        # this validator stopped running at all.
        if self.support_wires is None:
            return
        sw = tuple(self.support_wires)
        if len(set(sw)) != len(sw):
            raise ProvenanceError(
                f"chart {self.label}: its support {sw} repeats a wire")
        for w in sw:
            if not (0 <= w < self.n_qubits):
                raise ProvenanceError(
                    f"chart {self.label}: support wire {w} is outside a "
                    f"{self.n_qubits}-wire space")
        if self.route is not None and self.route.reconstructible:
            sched = {w for pl in self.route.placements for w in pl}
            if set(sw) != sched:
                raise ProvenanceError(
                    f"chart {self.label}: its recorded support {sw} is not "
                    f"the union of its scatter placements "
                    f"{tuple(sorted(sched))}")


def chart_of_frame(frame: "Frame", space: str = "local") -> "BoundaryChart":
    """The default chart: an ordinary boundary IS its own selected chart.

    The codes are the frame's own. `space` says whether those addresses are
    premise-local (the default -- nothing has told us where this premise
    sits) or already the compiled register's, which only a caller holding the
    whole register may assert.
    """
    return BoundaryChart(n_qubits=frame.n_qubits, codes=tuple(frame.codes),
                         label=f"{frame.label}=frame", space=space,
                         support_wires=tuple(range(frame.n_qubits)))


def par_then_repart(factors, repart, n_qubits, route_label="",
                    placements=(), kind="opaque"):
    """Repart_r( Par(factors...) ), with NAMESPACED premise addresses.

    Par builds the product workspace with disjoint premise injections, so a
    local wire 0 in each factor is a different address, not a collision. Each
    factor's ACTUAL ordered codes are tensored; none is expanded into a dense
    2^k space.

    The product is lexicographic with the FIRST factor most significant, so a
    variable spine's application order is what the index means. Repart then
    applies the recorded code-domain pullback to reach the ambient encoding.
    The result may be correlated: the factors need NOT occupy disjoint raw
    wire tuples. It is one joint injective map

        (factor coordinates...) -> ambient code

    with every factor identity, role and type retained, in order.
    """
    factors = tuple(factors)
    if not factors:
        raise ProvenanceError(f"chart {route_label}: Par of no factors")
    combos = [()]
    for f in factors:
        combos = [c + (cd,) for c in combos for cd in f.codes]
    embed = [repart(*c) for c in combos]
    if len(set(embed)) != len(embed):
        raise ProvenanceError(
            f"chart {route_label}: the recorded repart is not injective on "
            f"the product -- {len(embed)} ordered tuples collapse to "
            f"{len(set(embed))} ambient codes")
    route = ChartRoute(label=route_label, parts=factors,
                       embed=tuple(embed), kind=kind, n_qubits=n_qubits,
                       placements=tuple(tuple(g) for g in placements))
    chart = BoundaryChart(n_qubits=n_qubits, codes=tuple(embed), route=route,
                          label=route_label, space="ambient")
    want = 1
    for f in factors:
        want *= f.dim
    if chart.dim != want:
        raise ProvenanceError(
            f"chart {route_label}: dim {chart.dim} != "
            f"{'*'.join(str(f.dim) for f in factors)}")
    return chart


def localize_scatter(chart):
    """Re-read an AMBIENT scatter chart as a premise-local one, plus wires.

    Returns `(n_qubits, codes, wires)`: the chart's own ordered codes packed
    into one contiguous local address space, and the ambient wires that space
    sits on. Everything comes from the RECORDED schedule -- the factor codes
    and their placements -- so no bit-variation is inspected and no support
    is guessed. Scattering the result back onto `wires` reproduces the
    chart's ambient codes exactly, in the same order.

    A chart whose Repart is not a scatter has no recorded support to
    localise, and says so rather than falling back to the whole register.
    """
    r = chart.route
    if chart.space != "ambient":
        raise ProvenanceError(
            f"chart {chart.label}: only an ambient chart is localised, this "
            f"one is {chart.space!r}")
    if r is not None and isinstance(r, JoinRoute):
        # A RELATIONAL chart localises to its own recorded rows -- one local
        # code per surviving state, correlations intact. Nothing is expanded
        # to a product and nothing is dropped.
        wires = tuple(w for g in r.placements for w in g)
        codes = []
        for row in r.rows:
            c = 0
            for f, cd in zip(r.parts, row):
                c = (c << f.n_qubits) | cd
            codes.append(c)
        return len(wires), tuple(codes), wires
    if r is None or not r.reconstructible:
        raise ProvenanceError(
            f"chart {chart.label}: its Repart is "
            f"{'unrecorded' if r is None else repr(r.kind)}, so it records "
            f"no support to place a further factor beside")
    r.check_schedule()
    wires = tuple(w for g in r.placements for w in g)
    codes = []
    for combo in _ordered_product(r.parts):
        c = 0
        shift = 0
        for f, cd in zip(reversed(r.parts), reversed(combo)):
            c |= cd << shift
            shift += f.n_qubits
        codes.append(c)
    return len(wires), tuple(codes), wires


def _ordered_product(parts):
    combos = [()]
    for f in parts:
        combos = [c + (cd,) for c in combos for cd in f.codes]
    return combos


def scatter_repart(placements, n_qubits):
    """The Repart that lays premise-local factors on ambient wires.

    Returns `(repart, placements)`. This is ONE possible repart -- the simple
    scatter -- and `par_then_repart` still checks its injectivity on the
    product rather than trusting it, so a repart that collides two ordered
    tuples is refused instead of silently truncating the chart.
    """
    groups = tuple(tuple(g) for g in placements)

    def repart(*codes):
        if len(codes) != len(groups):
            raise ProvenanceError(
                f"scatter: {len(codes)} factor codes for {len(groups)} "
                f"placements")
        c = 0
        for cd, g in zip(codes, groups):
            for i, w in enumerate(g):
                if (cd >> (len(g) - 1 - i)) & 1:
                    c |= 1 << (n_qubits - 1 - w)
        return c

    return repart, groups


def _bits_on(code, wires, n):
    """The sub-code carried on `wires`, read in THEIR order."""
    v = 0
    for i, w in enumerate(wires):
        v |= ((code >> (n - 1 - w)) & 1) << (len(wires) - 1 - i)
    return v


def tenpack(chart, r_p, theta):
    """p^e |-> p^e theta^e, on ONE polarity. GATE-FREE.

    `r_p` is this polarity's binder schedule (ambient wires, x then y) and
    `theta` is a permutation of range(len(r_p)): ambient wire `r_p[i]` is
    re-addressed to `r_p[theta[i]]`.

    Only the ADDRESSING of the binder coordinate changes. Cardinality, factor
    order, factor identity, ownership, sparse code order and every wire
    outside `r_p` are untouched -- that is what gate-free means here. The
    identity theta is a genuine no-op, so a derivation whose producer already
    hands the port over in binder order is unaffected.
    """
    r = chart.route
    if r is None or (not isinstance(r, JoinRoute) and not r.reconstructible):
        raise ProvenanceError(
            f"chart {chart.label}: TenPack needs a recorded scatter schedule "
            f"to re-address, this one is "
            f"{'unrecorded' if r is None else repr(r.kind)}")
    r_p = tuple(r_p)
    theta = tuple(theta)
    if sorted(theta) != list(range(len(r_p))):
        raise ProvenanceError(
            f"TenPack: theta {theta} is not a permutation of the {len(r_p)} "
            f"binder slots")
    if len(set(r_p)) != len(r_p):
        raise ProvenanceError(
            f"TenPack: the binder schedule {r_p} repeats a wire")
    for w in r_p:
        if not (0 <= w < chart.n_qubits):
            raise ProvenanceError(
                f"TenPack: binder wire {w} outside a {chart.n_qubits}-wire "
                f"register")
    move = {w: w for w in range(chart.n_qubits)}
    for i, w in enumerate(r_p):
        move[w] = r_p[theta[i]]
    if isinstance(r, JoinRoute):
        # A RELATIONAL chart is re-addressed as the relation it is: rows,
        # source pairs and factor identities untouched, coordinates moved.
        moved = r.moved(move, chart.n_qubits)
        packed = BoundaryChart(
            n_qubits=chart.n_qubits, codes=tuple(moved.codes), route=moved,
            label=chart.label, space="ambient",
            support_wires=tuple(moved.support))
        packed.validate_joint()
        return packed
    r.check_schedule()
    places = tuple(tuple(move[w] for w in g) for g in r.placements)
    rep, places = scatter_repart(places, chart.n_qubits)
    packed = par_then_repart(r.parts, rep, chart.n_qubits, r.label,
                             placements=places, kind="scatter")
    packed.validate_joint()
    return packed


def check_spine_residual(route, expected_cod, where=""):
    """The terminal residual must be the head's own codomain.

    A pure, directly testable guard: equal dimension is never evidence, so an
    application refuses to replace a terminal residual the derivation does
    not identify with its head. Returns the residual factor.
    """
    res = route.residual
    if res.logical != expected_cod:
        raise ProvenanceError(
            f"{where or 'spine'}: the terminal residual is typed "
            f"{pretty(res.logical) if res.logical is not None else None}, "
            f"not the head's codomain "
            f"{pretty(expected_cod) if expected_cod is not None else None}; "
            f"refusing to replace a residual the derivation does not "
            f"identify with this application's head")
    return res


def _matched_factor(chart, tensor_ty, where, port_ref=None):
    """The producer factor the tensor cut consumes.

    Identified by RECORDED STRUCTURE -- the unique factor whose role is
    "residual" and whose logical type is the tensor being eliminated, and,
    when the derivation recorded the port's own identity, by that EXACT
    recorded source ref. Never by width, dimension, varying bits, name or
    position: a producer may carry unmatched operand factors of the same
    dimension, and in a neutral application it does. Several candidates
    with no recorded identity to separate them are refused, not ranked.
    """
    r = chart.route
    if r is None or not r.parts:
        raise ProvenanceError(
            f"{where}: the producer records no factored boundary, so the "
            f"tensor port cannot be identified")
    hits = [i for i, f in enumerate(r.parts)
            if f.role == "residual" and f.logical == tensor_ty]
    if port_ref is not None:
        hits = [i for i in hits
                if r.parts[i].source is not None
                and any(x.ref == port_ref for x in r.parts[i].source.refs)]
        if not hits:
            raise ProvenanceError(
                f"{where}: no producer factor carries the recorded port "
                f"identity {port_ref!r}")
    if not hits:
        raise ProvenanceError(
            f"{where}: no producer factor is a residual of type "
            f"{pretty(tensor_ty)}; its factors are "
            f"{[(f.name, f.role, pretty(f.logical) if f.logical is not None else None) for f in r.parts]}")
    if len(hits) > 1:
        raise ProvenanceError(
            f"{where}: {len(hits)} producer factors are classified as the "
            f"residual of type {pretty(tensor_ty)}; the derivation does not "
            f"say which one the cut consumes")
    return hits[0]


def tensor_splice(prod_in, prod_out, body_in, body_out, tensor_ty,
                  port_ref=None):
    """Splice_{A(x)B}( producer , TenPack(body) ).

    The producer's boundary is NOT assumed to be the tensor port. Its matched
    factor is located by recorded role and logical type; every other producer
    factor is an unmatched prefix that must survive the cut. This is the
    ordinary case, not an exotic one: a neutral application `f a` producing
    A(x)B has boundary S_a (x) Y_{A(x)B}, and only Y is consumed.

    The composition is a RELATIONAL JOIN on the matched port:

        producer-prefix x matched-port    join    matched-port x body
        =====================================================
                  producer-prefix x body

    Because each port label occurs once per prefix coordinate, that
    projection is deliberately many-to-one, and a first-match lookup would
    silently keep one prefix coordinate and drop the rest.

    Returns `(ingress, egress)`.
    """
    n = body_in.n_qubits
    if prod_in.dim != prod_out.dim:
        raise ProvenanceError(
            f"Splice: the producer's ingress ({prod_in.dim}) and egress "
            f"({prod_out.dim}) charts have different dimensions, so they "
            f"record no correspondence to pull back along")
    for ch, nm in ((prod_in, "producer ingress"), (prod_out, "producer egress"),
                   (body_out, "body egress")):
        if ch.n_qubits != n:
            raise ProvenanceError(
                f"Splice: {nm} spans {ch.n_qubits} wires but the body spans "
                f"{n}")
    m = _matched_factor(prod_out, tensor_ty, "Splice egress",
                        port_ref=port_ref)
    m_in = _matched_factor(prod_in, tensor_ty, "Splice ingress",
                           port_ref=port_ref)
    if m_in != m:
        raise ProvenanceError(
            f"Splice: the matched tensor factor is at position {m_in} on the "
            f"producer's ingress and {m} on its egress; the two polarities "
            f"do not agree on what the cut consumes")
    ro, ri = prod_out.route, prod_in.route
    port = tuple(ro.placements[m])
    if tuple(ri.placements[m]) != port:
        raise ProvenanceError(
            f"Splice: the matched factor sits on {ri.placements[m]} at "
            f"ingress and {port} at egress; a cut consumes one resource")

    mask = 0
    for w in port:
        mask |= 1 << (n - 1 - w)
    # Group the producer's positions by the port label they carry. The groups
    # are the prefix coordinates for that label, IN PRODUCER ORDER.
    by_label = {}
    for k, c in enumerate(prod_out.codes):
        by_label.setdefault(_bits_on(c, port, n), []).append(k)

    codes = []
    pairs = []
    for bi, bc in enumerate(body_in.codes):
        v = _bits_on(bc, port, n)
        ks = by_label.get(v)
        if not ks:
            raise ProvenanceError(
                f"Splice: the packed body selects {v} on the A(x)B port, "
                f"which the producer cannot supply -- its output labels "
                f"there are {sorted(by_label)}")
        pairs.append((bi, bc, ks))
    # producer-prefix MAJOR, body minor: the surviving producer factors lead.
    width = len(next(iter(by_label.values())))
    spl_sources = []
    for j in range(width):
        for bi, bc, ks in pairs:
            if len(ks) != width:
                raise ProvenanceError(
                    f"Splice: the producer's port projection is uneven "
                    f"({len(ks)} against {width} positions); the prefix does "
                    f"not factor through the port")
            rest = bc & ~mask
            pin = prod_in.codes[ks[j]]
            if pin & rest:
                raise ProvenanceError(
                    f"Splice: the producer's ingress code {pin} overlaps the "
                    f"body's non-port selection {rest}; the two premises are "
                    f"not on disjoint resources")
            codes.append(pin | rest)
            spl_sources.append((ks[j], bi))
    if len(set(codes)) != len(codes):
        raise ProvenanceError(
            f"Splice: the composed ingress is not injective -- "
            f"{len(codes)} selections collapse to {len(set(codes))}")

    prefix_in = tuple(f for i, f in enumerate(ri.parts) if i != m)
    prefix_in_pl = tuple(pl for i, pl in enumerate(ri.placements) if i != m)
    prefix_out = tuple(f for i, f in enumerate(ro.parts) if i != m)
    prefix_out_pl = tuple(pl for i, pl in enumerate(ro.placements) if i != m)

    ingress = _joined_chart(codes, prefix_in + tuple(body_in.route.parts),
                            prefix_in_pl + tuple(body_in.route.placements),
                            n, f"{body_in.route.label}|splice",
                            sources=tuple(spl_sources))
    # The egress keeps the producer's surviving factors beside the body's own
    # output; the matched port was consumed by the cut and exports nothing.
    # A RELATIONAL body stays relational: its rows and source pairs survive
    # beside the prefix rather than being expanded to a product.
    if isinstance(body_out.route, JoinRoute):
        br = body_out.route
        combos = [((), 0)]
        for f, pl in zip(prefix_out, prefix_out_pl):
            combos = [(cs + (cd,), amb | scatter_code(cd, tuple(pl), n))
                      for cs, amb in combos for cd in f.codes]
        rows_e, codes_e, srcs_e = [], [], []
        for ci, (cs, amb) in enumerate(combos):
            for bi2 in range(len(br.rows)):
                if amb & br.codes[bi2]:
                    raise ProvenanceError(
                        f"Splice: a prefix factor overlaps the relational "
                        f"body's coordinates")
                rows_e.append(tuple(cs) + tuple(br.rows[bi2]))
                codes_e.append(amb | br.codes[bi2])
                srcs_e.append((ci, bi2))
        jr = JoinRoute(
            label=f"{br.label}|splice", parts=prefix_out + tuple(br.parts),
            placements=prefix_out_pl + tuple(br.placements),
            rows=tuple(rows_e), sources=tuple(srcs_e), codes=tuple(codes_e),
            support=tuple(sorted(set(w for pl in prefix_out_pl for w in pl)
                                 | set(br.support))),
            n_qubits=n, producer_face=br.producer_face,
            consumer_face=br.consumer_face, transport=br.transport,
            substitutions=br.substitutions)
        egress = BoundaryChart(n_qubits=n, codes=tuple(codes_e), route=jr,
                               label=jr.label, space="ambient",
                               support_wires=tuple(jr.support))
        egress.validate_joint()
    else:
        egress = _par_of(prefix_out + tuple(body_out.route.parts),
                         prefix_out_pl + tuple(body_out.route.placements), n,
                         f"{body_out.route.label}|splice", body_out)
    return ingress, egress


def _joined_chart(codes, parts, placements, n, label, sources=None):
    """A chart on `codes`, described by `parts` when the schedule rebuilds it.

    A join need not stay a plain scatter of its factors; when it does not,
    and the caller recorded which premise-state pair each composite state
    came from, the encoding is kept as the RELATION it is -- a JoinRoute
    with every row and source pair -- and never as an opaque embed that
    pretends nothing was correlated.
    """
    route = ChartRoute(label=label, parts=tuple(parts), embed=tuple(codes),
                       kind="scatter", n_qubits=n,
                       placements=tuple(placements))
    try:
        ok = route.reconstruct() == tuple(codes)
    except ProvenanceError:
        ok = False
    if not ok:
        route = None
        if sources is not None:
            # The relation is recorded ONLY when its rows are true: every
            # composite state must decompose over the retained factors'
            # recorded placements into recorded factor states. A splice
            # whose composition leaves foreign bits on a factor's wires is
            # not that relation, and stays an opaque embed of exactly the
            # composed codes rather than a decomposition that lies.
            try:
                route = JoinRoute(
                    label=label, parts=tuple(parts),
                    placements=tuple(tuple(pl) for pl in placements),
                    rows=tuple(tuple(gather_code(c, tuple(pl), n)
                                     for pl in placements) for c in codes),
                    sources=tuple(sources), codes=tuple(codes),
                    support=tuple(sorted({w for pl in placements
                                          for w in pl})),
                    n_qubits=n)
            except ProvenanceError:
                route = None
        if route is None:
            route = ChartRoute(label=label, parts=tuple(parts),
                               embed=tuple(codes), kind="opaque", n_qubits=n)
    ch = BoundaryChart(n_qubits=n, codes=tuple(codes), route=route,
                       label=label, space="ambient")
    ch.validate_joint()
    return ch


def _par_of(parts, placements, n, label, fallback):
    """Par of the surviving producer factors with the body's own factors."""
    if not parts:
        return fallback
    rep, pl = scatter_repart(placements, n)
    ch = par_then_repart(tuple(parts), rep, n, label, placements=pl,
                         kind="scatter")
    ch.validate_joint()
    return ch


@dataclass(frozen=True, slots=True)
class BlockDescriptor:
    """The stable identity of an ALREADY-CONSTRUCTED Block.

    Enough to audit the aggregate back to the Block it came from, and no
    reference to the plan object itself -- holding the plan would make
    equality circular and would invite a consumer to reach into the sectors.
    A Block is a DIRECT SUM; the aggregate below is one alphabet, never a
    product of these sectors.
    """
    cut_id: str
    branch_cuts: Tuple[object, ...]
    tag_values: Tuple[int, ...]
    uses: Tuple[Tuple[str, ...], ...]
    inactive: Tuple[Tuple[str, ...], ...]
    block_dims: Tuple[int, ...]
    tag_wires: Tuple[int, ...]
    block_to_ambient: Tuple[int, ...]
    block_width: int
    ambient_width: int

    def __post_init__(self):
        n = len(self.branch_cuts)
        for nm, f in (("tag_values", self.tag_values), ("uses", self.uses),
                      ("inactive", self.inactive),
                      ("block_dims", self.block_dims)):
            if len(f) != n:
                raise ProvenanceError(
                    f"block descriptor: {nm} has {len(f)} entries for {n} "
                    f"branches")
        if len(set(self.block_to_ambient)) != len(self.block_to_ambient):
            raise ProvenanceError(
                f"block descriptor: block_to_ambient {self.block_to_ambient} "
                f"is not injective")
        if len(self.block_to_ambient) != self.block_width:
            raise ProvenanceError(
                f"block descriptor: block_to_ambient names "
                f"{len(self.block_to_ambient)} wires for a "
                f"{self.block_width}-wire block")
        for c in self.branch_cuts:
            if not c:
                raise ProvenanceError(
                    "block descriptor: a branch records no cut identity; a "
                    "label is not an identity")
        if len(set(self.branch_cuts)) != len(self.branch_cuts):
            raise ProvenanceError(
                f"block descriptor: branch cut identities {self.branch_cuts} "
                f"are not distinct")

    def check_against(self, plan, where="block descriptor"):
        """Every recorded fact must agree with the plan it describes.

        A forged or stale descriptor is refused BEFORE the aggregate is built
        and therefore before any circuit mutation.
        """
        checks = (
            ("ambient_width", self.ambient_width, plan.ambient_width),
            ("block_width", self.block_width, plan.block_width),
            ("block_to_ambient", tuple(self.block_to_ambient),
             tuple(plan.block_to_ambient)),
            ("tag_wires", tuple(self.tag_wires), tuple(plan.tag_wires)),
            ("tag_values", tuple(self.tag_values),
             tuple(b.tag_value for b in plan.branches)),
            ("branch_cuts", tuple(self.branch_cuts),
             tuple(b.artifact.cut_id for b in plan.branches)),
            ("uses", tuple(self.uses),
             tuple(tuple(b.uses) for b in plan.branches)),
            ("inactive", tuple(self.inactive),
             tuple(tuple(x.owner_id for x in b.inactive)
                   for b in plan.branches)),
            ("block_dims", tuple(self.block_dims),
             tuple(b.dim for b in plan.branches)),
        )
        for name, mine, theirs in checks:
            if mine != theirs:
                raise ProvenanceError(
                    f"{where}: {name} is {mine!r} but the Block records "
                    f"{theirs!r}")
        return True


def aggregate_block_chart(plan, side, descriptor, root=None):
    """The Block as ONE factor over its own direct-sum alphabet.

    Repart_{block_to_ambient}( Par( BlockFactor ) )

    Par has exactly ONE factor. This is not, and must never be described as,
    a product of the Block's sectors: a direct sum is not a tensor product,
    and the sectors are not recoverable from tag bits or code geometry here.

    What the aggregate buys is a genuine one-factor SCATTER route, so the
    ordinary TenPack and Splice can compose it without being weakened to
    accept route-less charts.

    `root` is the external semantic root the Block occurrence serves at THIS
    polarity, read by the ADAPTER from its own handed-down record -- the
    occurrence was introduced inside the enclosing compilation, so inside a
    branch it serves that side's issued root, and outside any branch there
    is none and the factor stays unlinked. This rule records what it is
    given; it never selects a root itself.
    """
    parent = plan.ingress if side == "ingress" else plan.egress
    b2a = tuple(descriptor.block_to_ambient)
    n = descriptor.ambient_width
    if parent.n_qubits != n:
        raise ProvenanceError(
            f"block aggregate {side}: the parent chart spans "
            f"{parent.n_qubits} wires but the descriptor records {n}")
    outside = [w for w in range(n) if w not in set(b2a)]
    local = []
    for c in parent.codes:
        for w in outside:
            if (c >> (n - 1 - w)) & 1:
                raise ProvenanceError(
                    f"block aggregate {side}: code {c} occupies wire {w}, "
                    f"which the block placement does not name")
        v = 0
        for i, w in enumerate(b2a):
            v |= ((c >> (n - 1 - w)) & 1) << (len(b2a) - 1 - i)
        local.append(v)
    if len(set(local)) != len(local):
        raise ProvenanceError(
            f"block aggregate {side}: the pullback is not injective")
    f = ChartFactor(name="B", owner=descriptor.cut_id,
                    n_qubits=descriptor.block_width, codes=tuple(local),
                    role="block", logical=None, descriptor=descriptor,
                    factor_id=f"block:{descriptor.cut_id}",
                    source=FactorSource((SourcePortRef(
                        ref=str(descriptor.cut_id),
                        origin_cut=descriptor.cut_id,
                        path=("block", side), root=root),)))
    rep, places = scatter_repart((b2a,), n)
    ch = par_then_repart((f,), rep, n, f"block^{side}", placements=places,
                         kind="scatter")
    if ch.route.placements != (b2a,):
        raise ProvenanceError(
            f"block aggregate {side}: the factor was not placed on the "
            f"descriptor's own block placement")
    ch.validate_joint()
    if tuple(ch.codes) != tuple(parent.codes):
        raise ProvenanceError(
            f"block aggregate {side}: scattering the pullback gives "
            f"{ch.codes[:6]}... not the parent's {tuple(parent.codes)[:6]}...")
    return ch


@dataclass(frozen=True, slots=True)
class BranchParameter:
    """The live summand premise a sum branch is given.

    THE EXTRA DERIVATION PARAMETER. A bound variable cannot tell, from
    anything local to itself, whether the slot it routes into currently holds
    a live resource. When it is a sum branch it does; when it is an AppCut
    head or a LetPair producer being fetched as a value it does not, and
    there the slot is merely the naming about to be overwritten.

    That difference is a property of the POSITION, so the derivation site
    that introduces the payload states it. Everything here is recorded at
    issue: nothing is read back from the branch term, a variable name, a
    dimension, a bit pattern, or whether placements happen to overlap.
    """
    logical: Ty
    owner_id: str
    intro_cut: str
    cut_id: str
    codes: Tuple[int, ...]
    ingress_placement: Tuple[int, ...]
    register_width: int

    def __post_init__(self):
        from lang.types import width as _w
        if not self.owner_id or not self.intro_cut or not self.cut_id:
            raise ProvenanceError(
                "branch parameter carries no owner or cut lineage")
        w = _w(self.logical)
        if len(self.ingress_placement) != w:
            raise ProvenanceError(
                f"branch parameter of type {pretty(self.logical)} is width "
                f"{w} but its placement names "
                f"{len(self.ingress_placement)} wires "
                f"{self.ingress_placement}")
        if len(set(self.ingress_placement)) != len(self.ingress_placement):
            raise ProvenanceError(
                f"branch parameter placement {self.ingress_placement} is not "
                f"injective")
        for x in self.ingress_placement:
            if not (0 <= x < self.register_width):
                raise ProvenanceError(
                    f"branch parameter placement wire {x} is outside the "
                    f"{self.register_width}-wire branch register")
        if len(set(self.codes)) != len(self.codes):
            raise ProvenanceError("branch parameter repeats a code")
        if len(self.codes) != semantic_dim(self.logical):
            raise ProvenanceError(
                f"branch parameter of type {pretty(self.logical)} has "
                f"semantic dimension {semantic_dim(self.logical)} but "
                f"records {len(self.codes)} codes")
        for c in self.codes:
            if not (0 <= c < (1 << w)):
                raise ProvenanceError(
                    f"branch parameter code {c} outside its own {w}-wire "
                    f"space")

    def check_against(self, cert, register_width, where=""):
        """The parameter and the binding must be two DISTINCT resources."""
        if self.owner_id == cert.owner_id:
            raise ProvenanceError(
                f"{where}the branch parameter and the binding {cert.name!r} "
                f"claim the same owner {self.owner_id}; they are two "
                f"premises")
        if self.register_width != register_width:
            raise ProvenanceError(
                f"{where}the branch parameter records a "
                f"{self.register_width}-wire register but the occurrence is "
                f"in {register_width}")
        a, b = set(self.ingress_placement), set(cert.wires)
        if a & b:
            raise ProvenanceError(
                f"{where}the branch parameter sits on "
                f"{self.ingress_placement} and the binding {cert.name!r} on "
                f"{tuple(cert.wires)}; they overlap on {sorted(a & b)}, so "
                f"the routing cut is not two disjoint premises")
        if len(self.ingress_placement) != len(cert.wires):
            raise ProvenanceError(
                f"{where}the branch parameter is "
                f"{len(self.ingress_placement)} wires but the binding is "
                f"{len(cert.wires)}")
        return True


@dataclass(frozen=True, slots=True)
class RoutingOnly:
    """A certificate that an occurrence ONLY ROUTED a recorded binding.

    ISSUED BY THE EMITTER THAT KNOWS, at the moment it does the routing: the
    bound-variable emitter, which brings one recorded binding into the
    consumer's slot without touching the register. It is never inferred by a
    consumer from zero commands, from a differing permutation, or from
    recognising a term's syntax -- an arbitrary gate-free structural
    permutation is NOT this.
    """
    name: str
    wires: Tuple[int, ...]
    owner_id: Optional[str]
    ingress_wires: Tuple[int, ...]
    egress_wires: Tuple[int, ...]
    perm_at_entry: Tuple[int, ...] = ()
    perm_at_exit: Tuple[int, ...] = ()
    n_cmds: int = 0
    phase_delta: float = 0.0

    def validate(self, where="", artifact=None):
        """Everything the certificate claims, checked.

        With `artifact`, the certificate is also required to AGREE with the
        occurrence that issued it -- a forged or stale certificate whose
        permutations, handoffs, command count or phase differ from what the
        artifact actually recorded is refused.
        """
        if self.n_cmds != 0:
            raise ProvenanceError(
                f"{where}routing certificate for {self.name!r} claims to be "
                f"gate-free but {self.n_cmds} command(s) were emitted")
        if abs(self.phase_delta) > 1e-12:
            raise ProvenanceError(
                f"{where}routing certificate for {self.name!r} carries phase "
                f"{self.phase_delta}")
        if not self.owner_id:
            raise ProvenanceError(
                f"{where}routing certificate for {self.name!r} carries no "
                f"binder identity; it must come from the binder that "
                f"introduced the name")
        for nm, ws in (("ingress", self.ingress_wires),
                       ("egress", self.egress_wires)):
            if tuple(ws) != tuple(self.wires):
                raise ProvenanceError(
                    f"{where}routing certificate for {self.name!r}: its "
                    f"{nm} handoff is {tuple(ws)} but its binding sits on "
                    f"{tuple(self.wires)}")
        if len(set(self.wires)) != len(self.wires):
            raise ProvenanceError(
                f"{where}routing certificate for {self.name!r} claims wire "
                f"{self.wires} twice")
        if len(self.perm_at_entry) != len(self.perm_at_exit):
            raise ProvenanceError(
                f"{where}routing certificate for {self.name!r}: entry and "
                f"exit permutations describe {len(self.perm_at_entry)} and "
                f"{len(self.perm_at_exit)} wires")
        n = len(self.perm_at_entry)
        for nm, ws in (("entry", self.perm_at_entry),
                       ("exit", self.perm_at_exit)):
            if ws and sorted(ws) != list(range(len(ws))):
                raise ProvenanceError(
                    f"{where}routing certificate {nm} permutation {ws} is "
                    f"not a permutation")
        for w in self.wires:
            if n and not (0 <= w < n):
                raise ProvenanceError(
                    f"{where}routing certificate for {self.name!r}: wire {w} "
                    f"is outside the {n}-wire register it records")
        if artifact is not None:
            for fld, mine in (("perm_at_entry", self.perm_at_entry),
                              ("perm_at_exit", self.perm_at_exit)):
                if tuple(getattr(artifact, fld)) != tuple(mine):
                    raise ProvenanceError(
                        f"{where}routing certificate for {self.name!r} "
                        f"records {fld} {tuple(mine)} but the occurrence "
                        f"recorded {tuple(getattr(artifact, fld))}")
            if artifact.n_cmds != self.n_cmds or \
                    abs(artifact.phase_delta - self.phase_delta) > 1e-12:
                raise ProvenanceError(
                    f"{where}routing certificate for {self.name!r} disagrees "
                    f"with its occurrence on commands/phase")
            if tuple(artifact.egress_wires) != tuple(self.egress_wires):
                raise ProvenanceError(
                    f"{where}routing certificate for {self.name!r} hands over "
                    f"{tuple(self.egress_wires)} but the occurrence recorded "
                    f"{tuple(artifact.egress_wires)}")
        return True


FRAME_DEFAULT = "frame-default"
DERIVED = "derived"


@dataclass(frozen=True, slots=True)
class TenPackSchedule:
    """The binder schedules a canonical LetPair derivation records.

    Four tuples, TWO PER POLARITY, recorded at their own moments: the x and y
    binder placements as the body receives them, and again as the body leaves
    them. They are never derived from one another -- reusing the negative
    schedule on the positive side is the mistake this record exists to make
    visible.

        r_p^e = r_x^e followed by r_y^e          (x PRECEDES y)
    """
    r_x_in: Tuple[int, ...]
    r_y_in: Tuple[int, ...]
    r_x_out: Tuple[int, ...]
    r_y_out: Tuple[int, ...]
    complement_in: Tuple[int, ...] = ()
    complement_out: Tuple[int, ...] = ()

    def r_p(self, side: str) -> Tuple[int, ...]:
        if side == "ingress":
            return tuple(self.r_x_in) + tuple(self.r_y_in)
        if side == "egress":
            return tuple(self.r_x_out) + tuple(self.r_y_out)
        raise ProvenanceError(f"unknown polarity {side!r}")

    def complement(self, side: str) -> Tuple[int, ...]:
        return tuple(self.complement_in if side == "ingress"
                     else self.complement_out)

    def check(self, side: str, ambient: int):
        """Injectivity, range, and x-before-y, on ONE polarity."""
        rx = tuple(self.r_x_in if side == "ingress" else self.r_x_out)
        ry = tuple(self.r_y_in if side == "ingress" else self.r_y_out)
        r_p = rx + ry
        comp = self.complement(side)
        # An EMPTY schedule is a genuine zero-wire pair (Unit (x) Unit), not
        # a missing one; what is refused is a malformed one.
        if len(set(r_p)) != len(r_p):
            raise ProvenanceError(
                f"TenPack {side}: the binder schedule {r_p} is not "
                f"injective -- x and y would share a coordinate")
        if len(set(comp)) != len(comp):
            raise ProvenanceError(
                f"TenPack {side}: the complement {comp} repeats a wire")
        both = set(r_p) & set(comp)
        if both:
            raise ProvenanceError(
                f"TenPack {side}: wire(s) {sorted(both)} are in both the "
                f"binder schedule and its complement")
        for label, ws in (("binder", r_p), ("complement", comp)):
            for w in ws:
                if not (0 <= w < ambient):
                    raise ProvenanceError(
                        f"TenPack {side}: {label} wire {w} outside an "
                        f"ambient register of {ambient}")
        # NOTE: "x precedes y" is not checkable here -- r_p is BUILT as
        # rx + ry, so any test of it against itself is a tautology. The
        # order is enforced where it is observable: the Splice matches r_p
        # against the producer's own recorded A(x)B port placement, which a
        # reversed schedule fails.
        return r_p


@dataclass(frozen=True, slots=True)
class SelectedBoundary:
    """The derivation-selected boundary of ONE occurrence.

    Independent ingress and egress ordered charts, each carrying its own joint
    injective embedding into the compiled register. The two sides are never
    identified: `S_y^-` and `S_y^+` are different charts on different
    coordinates even when they have the same type.

    `origin` says WHICH rule produced this boundary, and is required. An
    ordinary occurrence says so explicitly (`"frame-default"`); a missing
    special rule can therefore never masquerade as the default, because the
    occurrences that have a rule are checked for having recorded one.
    """
    ingress: BoundaryChart
    egress: BoundaryChart
    origin: str
    # EXPLICIT authority. `origin` stays diagnostic prose; nothing may infer
    # authority by parsing it, comparing widths, inspecting codes, scanning
    # free variables or looking at syntax.
    authority: str = "frame-default"
    # The TenPack binder schedules, when this boundary came through one.
    # Carried so a consumer can see WHICH schedule packed it, rather than
    # having to trust that the two polarities were kept apart.
    packing: object = None
    # THE PAYLOAD/FIBRE PARTITION, per polarity, as ordered factor_ids.
    #
    # The rule that CONSTRUCTS a boundary knows which of its factors present
    # the payload it was handed and which carry context beside it -- it made
    # them, from different inputs. Recovering that split afterwards by asking
    # which placements fall inside the payload wires is geometry choosing,
    # and two factors of equal width can sit either side of that line.
    # Recorded placement may VALIDATE this partition; it may not make it.
    #
    # Each entry is (presenter_ids, fibre_ids) and must partition every
    # factor of its polarity exactly once, dimension-one factors included.
    ingress_partition: object = None
    egress_partition: object = None

    def partition(self, side):
        return (self.ingress_partition if side == "ingress"
                else self.egress_partition)

    def check_partition(self, side, where=""):
        """The recorded split covers this polarity's factors exactly once."""
        part = self.partition(side)
        chart = self.ingress if side == "ingress" else self.egress
        if part is None:
            raise ProvenanceError(
                f"{where}the {side} boundary records no payload/fibre "
                f"partition, so which factors present its payload would have "
                f"to be inferred from where they sit")
        pres, fib = tuple(part[0]), tuple(part[1])
        if chart.route is None:
            if fib or len(pres) != 1:
                raise ProvenanceError(
                    f"{where}a route-less {side} boundary is one presenter "
                    f"and no fibre, but {len(pres)}/{len(fib)} are recorded")
            return True
        have = [f.factor_id for f in chart.route.parts]
        both = list(pres) + list(fib)
        if len(set(both)) != len(both):
            raise ProvenanceError(
                f"{where}the {side} partition classifies a factor twice: "
                f"{both}")
        if set(both) != set(have):
            missing = sorted(set(have) - set(both))
            foreign = sorted(set(both) - set(have))
            raise ProvenanceError(
                f"{where}the {side} partition does not cover this boundary "
                f"exactly once: missing {missing}, foreign {foreign}")
        return True

    @staticmethod
    def from_frames(frame_in, frame_out, origin="frame-default",
                    space="local"):
        """The explicit default: this occurrence's boundary IS its frames.

        It claims NOTHING about payload or fibre. A defaulted boundary may be
        a branch root presenting a semantic main occurrence, or an ordinary
        intermediate carrying only context, and only the rule that placed it
        knows which. An exhaustive projection is supplied by that rule, not
        assumed here.
        """
        return SelectedBoundary(ingress=chart_of_frame(frame_in, space),
                                egress=chart_of_frame(frame_out, space),
                                origin=origin, authority=FRAME_DEFAULT)

    @property
    def is_derived(self) -> bool:
        return self.authority == DERIVED

    def __post_init__(self):
        if self.authority not in (FRAME_DEFAULT, DERIVED):
            raise ProvenanceError(
                f"selected boundary {self.origin!r} records authority "
                f"{self.authority!r}; it is exactly {FRAME_DEFAULT!r} or "
                f"{DERIVED!r}")

    def transport_egress(self, new_to_old):
        """Carry only the egress through a permutation applied after it."""
        return replace(self, egress=self.egress.transport(new_to_old))


@dataclass(frozen=True, slots=True)
class SelectionContext:
    """The derivation context a boundary is selected IN.

    An open term's boundary cannot be selected from syntax alone: it needs the
    typed bindings the derivation introduced, the scope that owns them, and the
    cuts the two sides belong to. A closed term passes EMPTY_SELECTION
    explicitly -- an open term must never silently fall back to context-free
    canonical selection.
    """
    bindings: Tuple["TypedBinding", ...] = ()
    scope: object = None
    ingress_cut: Optional[str] = None
    egress_cut: Optional[str] = None
    local_to_ambient: Tuple[int, ...] = ()
    pending_perm: Tuple[int, ...] = ()

    def binding(self, name):
        """The recorded binding for `name`, or None. A lookup, not a search."""
        for b in self.bindings:
            if b.name == name:
                return b
        return None

    def with_bindings(self, more):
        return replace(self, bindings=self.bindings + tuple(more))

    @property
    def is_empty(self) -> bool:
        return not self.bindings

    def require_closed(self, term, free_names, where=""):
        """EMPTY_SELECTION asserts the occurrence is PROVABLY CLOSED.

        Passing it for a term with free variables would make the old
        context-free fallback legal again under a new name, so it fails
        explicitly instead.
        """
        if self.is_empty and free_names:
            raise ProvenanceError(
                f"{where or type(term).__name__}: EMPTY_SELECTION was used "
                f"for an OPEN term with free variables "
                f"{sorted(free_names)}. An empty selection context asserts "
                f"the occurrence is closed; an open boundary must be selected "
                f"in the derivation's typed binding context.")


EMPTY_SELECTION = SelectionContext()


@dataclass(frozen=True, slots=True)
class BranchInputs:
    """One prepared branch, as the planner sees it.

    Holds a DIRECT REFERENCE to the authoritative BranchArtifact rather than
    copying its frames, ports, commands and phase into a parallel record --
    two stores of the same facts drift, and the planner and the emitter must
    be provably looking at one object.

    Frames stay LOCAL: ambient context belongs to the occurrence placement.
    """
    index: int
    artifact: object                 # THE BranchArtifact, by identity
    uses: Tuple[str, ...] = ()       # OWNER IDS this branch actually binds
    # Recorded during the ONE preparation pass, so no consumer re-scans the
    # branch's syntax or re-derives its layout:
    bindings: Tuple[object, ...] = ()          # the TypedBindings it uses
    local_to_ambient: Tuple[int, ...] = ()     # branch-local -> register
    # The recorded handoffs of those bindings into this branch's preparation.
    transport: Tuple["BindingTransport", ...] = ()
    # The branch's per-polarity BranchMainProjections, issued at preparation
    # ({"ingress": ..., "egress": ...}), which Complete consumes unchanged.
    projections: object = None

    @property
    def fin(self):
        return self.artifact.fin

    @property
    def fout(self):
        return self.artifact.fout


@dataclass(frozen=True, slots=True)
class SidePlacement:
    """ONE boundary side of an occurrence: ingress or egress.

    The two sides are represented independently -- separate cut ids, separate
    local-to-ambient injections, separate reservations, separate ports. Every
    transport phase so far turned on the fact that inferring one side from the
    other is wrong, and a single shared `local_to_ambient` would rebuild
    exactly that mistake.

    The reservations are what let the main placement be selected AROUND an
    owned context: a context port on wire 0 is representable simply by putting
    tag/main/payload elsewhere.
    """
    cut_id: str
    ambient_width: int
    local_to_ambient: Tuple[int, ...] = ()
    tag_wires: Tuple[int, ...] = ()
    main_wires: Tuple[int, ...] = ()
    payload_wires: Tuple[int, ...] = ()
    ports: Tuple[Port, ...] = ()

    def __post_init__(self):
        n = self.ambient_width
        if not isinstance(n, int) or n < 0:
            raise ProvenanceError(f"bad ambient width {n!r}")
        if not self.cut_id:
            raise ProvenanceError("a side placement carries no cut_id")

        def _check(name, ws):
            if len(set(ws)) != len(ws):
                raise ProvenanceError(f"{name} is not injective: {ws}")
            for w in ws:
                if not (0 <= w < n):
                    raise ProvenanceError(
                        f"{name} claims wire {w} outside an ambient register "
                        f"of {n}")

        _check("local_to_ambient", self.local_to_ambient)
        reserved = {}
        for name, ws in (("tag", self.tag_wires), ("main", self.main_wires),
                         ("payload", self.payload_wires)):
            _check(name, ws)
            for w in ws:
                if w in reserved:
                    raise ProvenanceError(
                        f"wire {w} is reserved by both {reserved[w]} and "
                        f"{name}")
                reserved[w] = name

        claimed = {}
        for p in self.ports:
            live = not isinstance(p.logical, Unit)
            if live and (p.owner_id is None or p.cut_id is None):
                raise ProvenanceError(
                    f"live port {p.name!r} carries no owner_id/cut_id")
            if p.cut_id is not None and p.cut_id != self.cut_id:
                raise ProvenanceError(
                    f"port {p.name!r} belongs to cut {p.cut_id} but sits on "
                    f"the side whose cut is {self.cut_id}")
            key = (p.owner_id, p.cut_id)
            for w in p.all_wires():
                if not (0 <= w < n):
                    raise ProvenanceError(
                        f"port {p.name!r} claims wire {w} outside the ambient "
                        f"register")
                if live and w in reserved:
                    raise ProvenanceError(
                        f"live completion port {p.name!r} collides with this "
                        f"side's {reserved[w]} coordinate at wire {w}")
                prev = claimed.get(w)
                if prev is not None and prev != key:
                    raise ProvenanceError(
                        f"wire {w} is claimed by two distinct owner/cut pairs "
                        f"{prev} and {key}")
                claimed[w] = key

    def ambient(self, local_wire: int) -> int:
        """Local wire -> ambient wire. A lookup, never a recomputation."""
        return self.local_to_ambient[local_wire]

    def completed_dimension(self, main_dim: int) -> int:
        """`main_dim` completed by this side's distinct live factors."""
        total = main_dim
        for factor in _completion_factors(self.ports).values():
            total *= factor
        return total


@dataclass(frozen=True, slots=True)
class OccurrencePlacement:
    """Where one occurrence's LOCAL frames sit inside an ambient register.

    The branch artifact's own frames stay local; ambient context lives here,
    never in the branch-local `Frame.codes`.
    """
    ingress: SidePlacement
    egress: SidePlacement
    pending_perm: Tuple[int, ...] = ()

    def __post_init__(self):
        if self.ingress.ambient_width != self.egress.ambient_width:
            raise ProvenanceError(
                f"ingress and egress disagree on the ambient register "
                f"({self.ingress.ambient_width} vs "
                f"{self.egress.ambient_width})")

    @property
    def ambient_width(self) -> int:
        return self.ingress.ambient_width


# ---------------------------------------------------------------------------
# The occurrence planner (pure)
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class BindingTransport:
    """One owned resource handed INTO a branch preparation, recorded AT the
    handoff.

    Identity is not re-established afterwards by matching a name, a type, a
    dimension, an encoding or a wire. The parent's TypedBinding is handed
    down and the nested derivation adopts its owner and its introduction
    lineage, so the resource inside the branch IS the resource outside it.
    What is recorded here is that handoff: the same owner, the same origin,
    the same type and ordered codes, the branch-local wires it was given, and
    the parent wires those transport back onto.

    This is what a resource a branch CONSUMES has instead of a factor. An
    Apply spine splices its function argument into the result, so the
    resource is gone from the branch's own chart -- but it did not stop being
    that resource, and `used_bindings` alone is only the parent's intention.
    """
    owner_id: str
    intro_cut: str
    logical: Ty
    codes: Tuple[int, ...]
    local_wires: Tuple[int, ...]
    ambient_wires: Tuple[int, ...]
    name: str = ""

    def __post_init__(self):
        from lang.types import width as _w
        if self.owner_id is None or self.intro_cut is None:
            raise ProvenanceError(
                f"binding transport {self.name!r}: a handoff without an owner "
                f"or an introduction cut proves nothing")
        if len(self.local_wires) != len(self.ambient_wires):
            raise ProvenanceError(
                f"binding transport {self.name!r}: {len(self.local_wires)} "
                f"branch-local wires against {len(self.ambient_wires)} parent "
                f"wires")
        for tag, ws in (("branch-local", self.local_wires),
                        ("parent", self.ambient_wires)):
            if len(set(ws)) != len(ws):
                raise ProvenanceError(
                    f"binding transport {self.name!r}: the {tag} placement "
                    f"{ws} claims a wire twice")
        if _w(self.logical) != len(self.local_wires):
            raise ProvenanceError(
                f"binding transport {self.name!r}: {pretty(self.logical)} is "
                f"width {_w(self.logical)} but occupies "
                f"{len(self.local_wires)} wires")
        if len(self.codes) != semantic_dim(self.logical):
            raise ProvenanceError(
                f"binding transport {self.name!r}: {pretty(self.logical)} has "
                f"semantic dimension {semantic_dim(self.logical)} but "
                f"{len(self.codes)} codes are recorded")

    def check_transport(self, local_to_ambient, where=""):
        """The branch-local wires land exactly on the parent's."""
        l2a = tuple(local_to_ambient)
        for w in self.local_wires:
            if not (0 <= w < len(l2a)):
                raise ProvenanceError(
                    f"{where}binding {self.name!r} was given branch-local "
                    f"wire {w}, which local_to_ambient does not record")
        got = tuple(l2a[w] for w in self.local_wires)
        if got != tuple(self.ambient_wires):
            raise ProvenanceError(
                f"{where}binding {self.name!r} transports from "
                f"{self.local_wires} to {got}, but the parent holds it on "
                f"{self.ambient_wires}")
        return True


def issue_binding_transport(parent, local_view, local_to_ambient, where=""):
    """Record ONE handoff, at the site that performs it.

    Refuses anything that is not literally the same resource: a fresh owner,
    a rewritten introduction cut, a changed type or a re-encoded resource are
    all a DIFFERENT resource wearing the same name.
    """
    for fld in ("owner_id", "intro_cut", "logical", "codes"):
        if getattr(parent, fld) != getattr(local_view, fld):
            raise ProvenanceError(
                f"{where}the branch-local view of {parent.name!r} disagrees "
                f"with the parent binding on {fld}: "
                f"{getattr(local_view, fld)!r} against "
                f"{getattr(parent, fld)!r}; a handed-down resource keeps its "
                f"identity")
    t = BindingTransport(
        owner_id=parent.owner_id, intro_cut=parent.intro_cut,
        logical=parent.logical, codes=tuple(parent.codes),
        local_wires=tuple(local_view.wires),
        ambient_wires=tuple(parent.wires), name=parent.name)
    t.check_transport(local_to_ambient, where)
    return t


def gather_code(code, wires, ambient_width):
    """The sub-code `code` carries on `wires`. Inverse of `scatter_code`."""
    v = 0
    k = len(wires)
    for i, w in enumerate(wires):
        if not (0 <= w < ambient_width):
            raise ProvenanceError(
                f"wire {w} is outside a register of {ambient_width}")
        if (code >> (ambient_width - 1 - w)) & 1:
            v |= 1 << (k - 1 - i)
    return v


def replace_code(code, wires, sub, ambient_width):
    """`code` with the bits at `wires` replaced by the sub-code `sub`."""
    out = code
    k = len(wires)
    for i, w in enumerate(wires):
        bit = 1 << (ambient_width - 1 - w)
        out &= ~bit
        if (sub >> (k - 1 - i)) & 1:
            out |= bit
    return out


@dataclass(frozen=True, slots=True)
class CutCompletion:
    """WHY a cut is wider than one of its premises.

    Two recorded interfaces do not establish a common cut merely because one
    wire set happens to contain the other. When their widths differ, the
    splice's own typed frame-reconciliation is what decides that the extra
    coordinate exists and what it is for, and it issues this. Without one,
    a containment is a coincidence and the cut fails closed.

    `ordered_wires` is the common placement, IN ORDER. Both premise
    placements must appear inside it in their own recorded order -- turning
    them into sets would lose exactly the ordering the codes are written in.

    `reason` is DIAGNOSTIC. Nothing branches on its content; it is required to
    be present so a completion cannot be issued without saying anything, and
    it is never parsed.
    """
    ordered_wires: Tuple[int, ...]
    ambient_width: int
    producer_wires: Tuple[int, ...]
    consumer_wires: Tuple[int, ...]
    widened: str                       # "producer" | "consumer"
    from_width: int
    to_width: int
    reason: str
    cut_id: object = None
    producer_logical: object = None
    consumer_logical: object = None
    residual_name: str = ""

    def __post_init__(self):
        w = self.ordered_wires
        if len(set(w)) != len(w):
            raise ProvenanceError(
                f"cut completion: the common placement {w} repeats a wire")
        for x in w:
            if not (0 <= x < self.ambient_width):
                raise ProvenanceError(
                    f"cut completion: wire {x} is outside a "
                    f"{self.ambient_width}-wire register")
        if self.widened not in ("producer", "consumer"):
            raise ProvenanceError(
                f"cut completion: {self.widened!r} is neither premise")
        if self.to_width != len(w):
            raise ProvenanceError(
                f"cut completion: it completes to {self.to_width} but records "
                f"{len(w)} coordinates")
        if self.from_width >= self.to_width:
            raise ProvenanceError(
                f"cut completion: {self.from_width} -> {self.to_width} does "
                f"not widen anything")
        if not self.reason:
            raise ProvenanceError(
                "cut completion: no reason recorded for the extra coordinate")
        for nm, ws in (("producer", self.producer_wires),
                       ("consumer", self.consumer_wires)):
            it = iter(w)
            if not all(x in it for x in ws):
                raise ProvenanceError(
                    f"cut completion: the {nm}'s placement {tuple(ws)} is not "
                    f"inside the common placement {w} in its own order")
        narrow = (self.producer_wires if self.widened == "producer"
                  else self.consumer_wires)
        wide = (self.consumer_wires if self.widened == "producer"
                else self.producer_wires)
        if len(narrow) != self.from_width:
            raise ProvenanceError(
                f"cut completion: it says the {self.widened} was "
                f"{self.from_width} wide but its placement has {len(narrow)} "
                f"coordinates")
        if len(wide) >= len(narrow) and len(wide) != self.to_width:
            raise ProvenanceError(
                f"cut completion: it completes to {self.to_width} but the "
                f"unwidened premise occupies {len(wide)} coordinates")

    def check_against(self, producer_interface, consumer_interface,
                      cut_id, widened_frame, where=""):
        """This certificate is THIS occurrence's, for THESE two interfaces.

        Placement, ordering, logical type, lineage and polarity all have to
        agree, and the widened premise has to actually carry the typed
        residual ports the completion claims. Equal geometry from another
        occurrence is a different completion, not this one.
        """
        if self.cut_id != cut_id:
            raise ProvenanceError(
                f"{where}the completion was issued at cut {self.cut_id!r} but "
                f"this occurrence's cut is {cut_id!r}; equal geometry from "
                f"another occurrence is not this completion")
        if tuple(self.producer_wires) != tuple(
                producer_interface.ordered_wires):
            raise ProvenanceError(
                f"{where}the completion records the producer on "
                f"{self.producer_wires} but its interface is on "
                f"{tuple(producer_interface.ordered_wires)}")
        if tuple(self.consumer_wires) != tuple(
                consumer_interface.ordered_wires):
            raise ProvenanceError(
                f"{where}the completion records the consumer on "
                f"{self.consumer_wires} but its interface is on "
                f"{tuple(consumer_interface.ordered_wires)}")
        for nm, want, rec in (
                ("producer", producer_interface.logical, self.producer_logical),
                ("consumer", consumer_interface.logical, self.consumer_logical)):
            if rec is not None and rec != want:
                raise ProvenanceError(
                    f"{where}the completion types the {nm} "
                    f"{pretty(rec)} but its interface is "
                    f"{pretty(want) if want is not None else None}")
        if producer_interface.polarity != "egress":
            raise ProvenanceError(
                f"{where}the producer's interface is recorded at polarity "
                f"{producer_interface.polarity!r}, not egress")
        if consumer_interface.polarity != "ingress":
            raise ProvenanceError(
                f"{where}the consumer's interface is recorded at polarity "
                f"{consumer_interface.polarity!r}, not ingress")
        if self.residual_name:
            got = [pt.name for pt in getattr(widened_frame, "ports", ())]
            if self.residual_name not in got:
                raise ProvenanceError(
                    f"{where}the completion claims the {self.widened} was "
                    f"padded with typed {self.residual_name!r} ports, but the "
                    f"widened frame carries {got}; the evidence is absent")
        return True


@dataclass(frozen=True, slots=True)
class CutTransport:
    """THE transport at one Seq cut, recorded once and used twice.

    A Seq splices a producer's output onto a consumer's input, and when the
    two embeddings disagree it emits a real Align. That Align is a fact about
    the compiled circuit; the composed selected boundary has to describe the
    SAME fact. Rebuilding an "equivalent" one later from types, fresh frames
    or code geometry is how the metadata and the gates come to disagree
    without anything detecting it, so both the emission and the composition
    consume this object.

    `forward` is total on the cut's own address space and carries CONSUMER
    codes onto PRODUCER codes -- the direction of A u_C^- = u_P^+ .
    """
    wires: Tuple[int, ...]
    ambient_width: int
    consumer_codes: Tuple[int, ...]
    producer_codes: Tuple[int, ...]
    forward: Tuple[int, ...]
    inverse: Tuple[int, ...]
    kind: str                       # identity | wire-permutation | code-permutation
    wire_permutation: Optional[Tuple[int, ...]] = None
    label: str = ""
    # The two premise placements this transport binds, each in its OWN
    # recorded order. They are kept apart: a producer that leaves its result
    # on (2,0,1) and a consumer that receives on (0,1,2) meet at one cut, and
    # collapsing them into a single tuple would silently reorder the codes.
    producer_wires: Tuple[int, ...] = ()
    consumer_wires: Tuple[int, ...] = ()
    # Present exactly when the two premises did not already describe the same
    # typed cut and the splice's own reconciliation completed them onto one.
    completion: Optional["CutCompletion"] = None

    def __post_init__(self):
        k = len(self.wires)
        size = 1 << k
        if len(set(self.wires)) != k:
            raise ProvenanceError(
                f"cut transport {self.label}: wires {self.wires} repeat")
        for w in self.wires:
            if not (0 <= w < self.ambient_width):
                raise ProvenanceError(
                    f"cut transport {self.label}: wire {w} is outside a "
                    f"{self.ambient_width}-wire register")
        if len(self.forward) != size or len(self.inverse) != size:
            raise ProvenanceError(
                f"cut transport {self.label}: the map is not total on a "
                f"{k}-wire cut")
        if sorted(self.forward) != list(range(size)):
            raise ProvenanceError(
                f"cut transport {self.label}: the forward map is not a "
                f"permutation, so the cut correspondence is not injective")
        for i, j in enumerate(self.forward):
            if self.inverse[j] != i:
                raise ProvenanceError(
                    f"cut transport {self.label}: the inverse disagrees with "
                    f"the forward map at {i}")
        if len(self.consumer_codes) != len(self.producer_codes):
            raise ProvenanceError(
                f"cut transport {self.label}: {len(self.consumer_codes)} "
                f"consumer codes against {len(self.producer_codes)} producer "
                f"codes")
        for c, pcode in zip(self.consumer_codes, self.producer_codes):
            if self.forward[c] != pcode:
                raise ProvenanceError(
                    f"cut transport {self.label}: it carries consumer code "
                    f"{c} to {self.forward[c]}, but the selected cut records "
                    f"{pcode}; this is not the transport that was selected")
        if self.kind not in ("identity", "wire-permutation",
                             "code-permutation"):
            raise ProvenanceError(
                f"cut transport {self.label}: unknown kind {self.kind!r}")
        if (self.kind == "identity") != (
                tuple(self.forward) == tuple(range(size))):
            raise ProvenanceError(
                f"cut transport {self.label}: kind {self.kind!r} disagrees "
                f"with the recorded map")
        if (self.wire_permutation is not None) != (
                self.kind == "wire-permutation"):
            raise ProvenanceError(
                f"cut transport {self.label}: a wire permutation is recorded "
                f"iff the kind says so")
        if self.wire_permutation is not None:
            wp = tuple(self.wire_permutation)
            if sorted(wp) != list(range(k)):
                raise ProvenanceError(
                    f"cut transport {self.label}: {wp} is not a permutation "
                    f"of the cut's {k} wires")
            for i in range(size):
                if permute_index(i, wp, k) != self.forward[i]:
                    raise ProvenanceError(
                        f"cut transport {self.label}: the recorded wire "
                        f"permutation {wp} does not induce the forward map "
                        f"at code {i}; the two describe different Aligns")
        for nm, ws in (("producer", self.producer_wires),
                       ("consumer", self.consumer_wires)):
            if not ws:
                continue
            if len(set(ws)) != len(ws):
                raise ProvenanceError(
                    f"cut transport {self.label}: the {nm}'s placement {ws} "
                    f"repeats a wire")
            if set(ws) - set(self.wires):
                raise ProvenanceError(
                    f"cut transport {self.label}: the {nm} is placed on "
                    f"{ws}, which the cut {self.wires} does not cover")
        if self.completion is not None:
            c = self.completion
            if tuple(c.ordered_wires) != tuple(self.wires):
                raise ProvenanceError(
                    f"cut transport {self.label}: its completion records the "
                    f"common placement {c.ordered_wires} but the cut is "
                    f"{self.wires}")
            if c.ambient_width != self.ambient_width:
                raise ProvenanceError(
                    f"cut transport {self.label}: its completion is over "
                    f"{c.ambient_width} wires, not {self.ambient_width}")
        elif self.producer_wires and self.consumer_wires and \
                set(self.producer_wires) != set(self.consumer_wires):
            raise ProvenanceError(
                f"cut transport {self.label}: the producer is placed on "
                f"{self.producer_wires} and the consumer on "
                f"{self.consumer_wires}; different placements need a recorded "
                f"completion saying why, not a containment")

    def apply(self, ambient_code):
        """Transport one AMBIENT code through the cut."""
        return replace_code(
            ambient_code, self.wires,
            self.forward[gather_code(ambient_code, self.wires,
                                     self.ambient_width)],
            self.ambient_width)

    def check_selected(self, consumer_codes, producer_codes, where=""):
        """This IS the transport the Seq selected -- not one like it."""
        if (tuple(consumer_codes) != tuple(self.consumer_codes)
                or tuple(producer_codes) != tuple(self.producer_codes)):
            raise ProvenanceError(
                f"{where}the recorded cut transport was built for "
                f"{self.consumer_codes} -> {self.producer_codes}, but the cut "
                f"actually selected {tuple(consumer_codes)} -> "
                f"{tuple(producer_codes)}")
        return True


@dataclass(frozen=True, slots=True)
class CutFace:
    """WHICH factor presents the cut, at one polarity, and how its states
    project onto the cut's semantic labels.

    The projection is MANY-TO-ONE and that is the point: a completed Block of
    192 states meets a six-state cut, so every cut label has a fibre of 32
    states behind it and all of them survive the join. A map from cut label
    to composite state cannot exist, and nothing here pretends otherwise.

    Two forms, and only two:

      * ROUTED -- the premise has a chart route, and the face names the one
        factor inside it that presents the cut, by `factor_id`.
      * ATOMIC -- the premise has no route. Then the face must be an
        EXHAUSTIVE presentation of the whole chart (`whole_chart`), because a
        route-less premise cannot say what else it carries; a proper subface
        would leave prefix or context factors unrecorded, and a join must
        never assume those are absent.

    The factor identity is MINTED from the derivation's provenance scope. It
    is never synthesized from codes or placement: those are used to VALIDATE
    the recorded presentation, never to discover it.
    """
    factor_ids: Tuple[str, ...]
    polarity: str
    cut_id: object
    origin_cut: object
    codes: Tuple[int, ...]            # the factor's own ordered coordinates
    placement: Tuple[int, ...]        # in the CHART's own address space
    labels: Tuple[int, ...]           # state index -> index into `alphabet`
    n_labels: int
    interface_wires: Tuple[int, ...]  # the cut's ambient placement
    # THE ORDERED SEMANTIC CUT ALPHABET: the cut sub-codes this premise
    # actually presents, in order. It is NOT the number of parent states --
    # a two-state face and a two-hundred-state face can present the same
    # two-label alphabet -- and it is what two premises must agree on,
    # through the transport, to be at the same cut.
    alphabet: Tuple[int, ...] = ()
    fibre_sizes: Tuple[int, ...] = ()
    role: str = ""
    logical: object = None
    descriptor: object = None
    whole_chart: bool = False

    def __post_init__(self):
        if self.polarity not in ("ingress", "egress"):
            raise ProvenanceError(
                f"cut face: polarity {self.polarity!r} is neither ingress nor "
                f"egress")
        if not self.factor_ids:
            raise ProvenanceError("cut face: it names no factor")
        if len(set(self.factor_ids)) != len(self.factor_ids):
            raise ProvenanceError(
                f"cut face: it names {self.factor_ids} with a repeat")
        if self.cut_id is None or self.origin_cut is None:
            raise ProvenanceError(
                "cut face: it carries no cut identity or origin lineage")
        if len(self.labels) != len(self.codes):
            raise ProvenanceError(
                f"cut face: {len(self.labels)} labels for {len(self.codes)} "
                f"factor states")
        if len(set(self.codes)) != len(self.codes):
            raise ProvenanceError("cut face: a factor state repeats a code")
        if len(set(self.placement)) != len(self.placement):
            raise ProvenanceError(
                f"cut face: its placement {self.placement} repeats a wire")
        if self.n_labels <= 0:
            raise ProvenanceError("cut face: it projects onto no labels")
        if self.alphabet:
            if len(self.alphabet) != self.n_labels:
                raise ProvenanceError(
                    f"cut face: it records {len(self.alphabet)} alphabet "
                    f"symbols for {self.n_labels} labels")
            if len(set(self.alphabet)) != len(self.alphabet):
                raise ProvenanceError(
                    f"cut face: its alphabet {self.alphabet} repeats a symbol")
            span = 1 << len(self.interface_wires)
            for a in self.alphabet:
                if not (0 <= a < span):
                    raise ProvenanceError(
                        f"cut face: alphabet symbol {a} is outside the cut's "
                        f"own {len(self.interface_wires)}-wire space")
        for L in self.labels:
            if not (0 <= L < self.n_labels):
                raise ProvenanceError(
                    f"cut face: label {L} is outside the recorded "
                    f"{self.n_labels}")
        got = [0] * self.n_labels
        for L in self.labels:
            got[L] += 1
        if any(x == 0 for x in got):
            raise ProvenanceError(
                f"cut face: labels {[i for i, x in enumerate(got) if not x]} "
                f"have no states, so the cut is not covered")
        if self.fibre_sizes and tuple(self.fibre_sizes) != tuple(got):
            raise ProvenanceError(
                f"cut face: it records fibre sizes {tuple(self.fibre_sizes)} "
                f"but its projection gives {tuple(got)}")
        if len(self.interface_wires) != len(set(self.interface_wires)):
            raise ProvenanceError(
                "cut face: its interface placement repeats a wire")

    def recut(self, cut_id, polarity=None):
        """The SAME face, read at a new occurrence's cut.

        A relay carries its child's face onward; the origin is preserved so
        the factor is still traceable to where it was actually presented.
        """
        return _dataclass_replace(
            self, cut_id=cut_id,
            origin_cut=(self.origin_cut if self.origin_cut is not None
                        else self.cut_id),
            polarity=polarity or self.polarity)

    @property
    def fibres(self):
        """label -> the ordered factor-state indices behind it."""
        out = [[] for _ in range(self.n_labels)]
        for i, L in enumerate(self.labels):
            out[L].append(i)
        return tuple(tuple(x) for x in out)

    def check_against(self, chart, cut_id, where=""):
        """This face IS this chart's, at this occurrence's cut."""
        if self.cut_id != cut_id:
            raise ProvenanceError(
                f"{where}the face was issued at cut {self.cut_id!r} but this "
                f"occurrence's cut is {cut_id!r}; it is a stale face")
        if chart.route is None:
            if not self.whole_chart:
                raise ProvenanceError(
                    f"{where}the premise records no route, so only an "
                    f"EXHAUSTIVE atomic face is acceptable: a proper subface "
                    f"would leave its prefix and context factors unrecorded, "
                    f"and a join must not assume they are absent")
            if len(self.codes) != chart.dim:
                raise ProvenanceError(
                    f"{where}the atomic face presents {len(self.codes)} "
                    f"states but the chart has {chart.dim}; it does not "
                    f"exhaust the premise")
            rebuilt = tuple(
                scatter_code(c, self.placement, chart.n_qubits)
                for c in self.codes)
            if rebuilt != tuple(chart.codes):
                raise ProvenanceError(
                    f"{where}the atomic face reassembles to {rebuilt[:6]}... "
                    f"but the chart's codes are {tuple(chart.codes)[:6]}...")
            sup = tuple(chart.support(where))
            if tuple(self.placement) != sup:
                raise ProvenanceError(
                    f"{where}the atomic face is placed on {self.placement} "
                    f"but the chart's recorded support is {sup}, in that "
                    f"order")
            return True
        hits = [f for f in chart.route.parts
                if f.factor_id in set(self.factor_ids)]
        if len(hits) != len(self.factor_ids):
            raise ProvenanceError(
                f"{where}the face names {self.factor_ids} but the route "
                f"resolves {[f.factor_id for f in hits]}; a face must resolve "
                f"each of its factors exactly once")
        if len(self.factor_ids) > 1:
            # A MULTI-FACTOR presentation: the face's codes are the joint
            # presenter states, first named factor most significant, and its
            # placement is the presenters' concatenated placement in the
            # face's own order. The presenters need not be contiguous.
            by_id = {f.factor_id: f for f in hits}
            ordered = [by_id[fid] for fid in self.factor_ids]
            joint = [()]
            for g in ordered:
                joint = [c + (cd,) for c in joint for cd in g.codes]
            want = []
            for combo in joint:
                v = 0
                for g, cd in zip(ordered, combo):
                    v = (v << g.n_qubits) | cd
                want.append(v)
            if tuple(self.codes) != tuple(want):
                raise ProvenanceError(
                    f"{where}the face records {len(self.codes)} joint states "
                    f"but its presenters' ordered product is {len(want)}"
                    + ("" if len(self.codes) != len(want) else
                       " with different codes"))
            place = []
            for fid in self.factor_ids:
                idx = chart.route.parts.index(by_id[fid])
                place.extend(chart.route.placements[idx]
                             if chart.route.placements else ())
            if chart.route.placements and \
                    tuple(self.placement) != tuple(place):
                raise ProvenanceError(
                    f"{where}the face is placed on {self.placement} but its "
                    f"presenters' concatenated placement is {tuple(place)}")
            return True
        f = hits[0]
        if self.role and f.role != self.role:
            raise ProvenanceError(
                f"{where}the face records role {self.role!r} but the factor "
                f"is {f.role!r}")
        if self.logical is not None and f.logical != self.logical:
            raise ProvenanceError(
                f"{where}the face records type {pretty(self.logical)} but the "
                f"factor is "
                f"{pretty(f.logical) if f.logical is not None else None}")
        if self.descriptor is not None and f.descriptor is not self.descriptor:
            raise ProvenanceError(
                f"{where}the face records a different descriptor than the "
                f"factor it names")
        if tuple(self.codes) != tuple(f.codes):
            raise ProvenanceError(
                f"{where}the face records {len(self.codes)} factor states but "
                f"the factor has {len(f.codes)}")
        idx = chart.route.parts.index(f)
        place = tuple(chart.route.placements[idx]) \
            if chart.route.placements else ()
        if place and tuple(self.placement) != place:
            raise ProvenanceError(
                f"{where}the face is placed on {self.placement} but the route "
                f"schedules that factor on {place}")
        return True


def branch_cut_symbols(proj, tag_bit, main_wires, ambient_width, where=""):
    """ONE completed branch's cut alphabet ON THE MAIN COORDINATES.

    Each symbol of the branch's completed projection, in the projection's
    OWN recorded order, expressed through the projection's own recorded
    schedule -- the symbol scattered on its label coordinates, the recorded
    on-cut padding bits fixed, the branch's sector tag applied -- and read
    off the cut. Fixed padding is PRESERVED as the fixed bits it is, never
    promoted to semantic states, and fibre coordinates contribute nothing:
    a fibre that leaks onto the cut is caught by row validation, not
    absorbed here.

    Nothing row-shaped participates. This is the DEFINITION the Block's
    rows are later validated against.
    """
    W = tuple(main_wires)
    n = ambient_width
    mask = 0
    for w in W:
        mask |= 1 << (n - 1 - w)
    if tag_bit & ~mask:
        raise ProvenanceError(
            f"{where}the sector tag lies outside the main coordinates {W}")
    fixed = 0
    on_cut = set(W)
    for w, b in proj.padding:
        if b and w in on_cut:
            fixed |= 1 << (n - 1 - w)
    out = []
    for sym in proj.alphabet:
        amb = scatter_code(sym, proj.label_wires, n)
        if amb & ~mask:
            raise ProvenanceError(
                f"{where}projected symbol {sym} lies outside the main "
                f"coordinates {W}")
        out.append(gather_code(amb | fixed | tag_bit, W, n))
    if len(set(out)) != len(out):
        raise ProvenanceError(
            f"{where}two projected symbols land on one cut symbol: {out}")
    return tuple(out)


def antecedent_main_alphabet(plan, main_wires, polarity, where=""):
    """The ordered cut alphabet the completed sum's parent presents.

    Built ANTECEDENTLY from each branch's own completed per-polarity
    projection -- its recorded alphabet, in its recorded order, expressed on
    the cut coordinates and tagged into the branch's sector -- concatenated
    in summand order. The Block's rows may CONFIRM this alphabet; they never
    define, shrink or reorder it. (Replaces `parent_main_alphabet`, which
    read whole selected-boundary row images and could not tell the payload
    from the fibre.)
    """
    out = []
    for blk in plan.branches:
        proj = (blk.ingress_projection if polarity == "ingress"
                else blk.egress_projection)
        if proj is None:
            raise ProvenanceError(
                f"{where}branch {blk.index} carries no completed {polarity} "
                f"projection; the antecedent branch projections define the "
                f"alphabet and are required")
        out.extend(branch_cut_symbols(
            proj, plan.tag_bit(blk.index), main_wires, plan.ambient_width,
            f"{where}branch {blk.index} {polarity}: "))
    if len(set(out)) != len(out):
        raise ProvenanceError(
            f"{where}two summand states land on one cut symbol: {out}")
    return tuple(out)


@dataclass(frozen=True, slots=True)
class SourcePortRef:
    """A displayed semantic port occurrence, by MINTED identity.

    `ref` comes from the derivation's provenance scope; `origin_cut` is where
    that occurrence was introduced; `path` is the structural route to it
    inside its premise. None of the three is a type, a width or a placement,
    because two ports can agree on all of those and still be different ports.
    """
    ref: str
    origin_cut: object
    path: Tuple[str, ...] = ()
    # THE RECORDED GRAPH-LINK to the external semantic root this port serves.
    #
    # An occurrence minted INSIDE a branch -- an Apply result, a spine
    # residual -- is meaningless to the enclosing sum on its own: the adapter
    # knows only "the branch's payload root" and "the binding f", and would
    # have to guess how an internal Apply identity relates to either. So the
    # link is recorded when the port is minted, by the rule that knows, and
    # read afterwards. Classification is then a lookup, never a
    # reconstruction.
    root: object = None

    def __post_init__(self):
        if not self.ref:
            raise ProvenanceError("source port: no minted identity")
        if self.origin_cut is None:
            raise ProvenanceError(
                f"source port {self.ref!r}: no origin cut, so where it was "
                f"introduced cannot be recovered")

    def linked_to(self, root):
        """The same port, with its link to an external root recorded ONCE.

        A link is permanent. A later cut that grafts one premise onto another
        records a SourceSubstitution beside the ports rather than rewriting
        them: destructively relinking would erase where the occurrence
        actually came from, which is the only thing that makes it traceable.
        """
        if self.root is not None and self.root != root:
            raise ProvenanceError(
                f"source port {self.ref!r} is already linked to {self.root!r}; "
                f"a link is permanent, and a graft records a substitution "
                f"instead of relinking to {root!r}")
        return _dataclass_replace(self, root=root)

    def reaches(self, where=""):
        """The external root this port serves, or a refusal."""
        if self.root is None:
            raise ProvenanceError(
                f"{where}source port {self.ref!r} records no link to an "
                f"external semantic root, so which side of this branch it "
                f"serves cannot be read -- only invented")
        return self.root


@dataclass(frozen=True, slots=True)
class SourceSubstitution:
    """A recorded graft: which port a cut replaced with which other port.

    SeqCut removes a matched formal port and puts the producer's in its
    place. That is a fact ABOUT the composition, not a correction to either
    premise, so it lives here and both original references survive intact.
    """
    replaced: str
    by: str
    at_cut: object
    polarity: str

    def __post_init__(self):
        if self.polarity not in ("ingress", "egress"):
            raise ProvenanceError(
                f"source substitution: polarity {self.polarity!r} is neither "
                f"ingress nor egress")
        if self.replaced == self.by:
            raise ProvenanceError(
                f"source substitution: {self.replaced!r} replaces itself")
        if self.at_cut is None:
            raise ProvenanceError(
                "source substitution: no cut recorded for the graft")


@dataclass(frozen=True, slots=True)
class FactorSource:
    """The ordered semantic ports a factor's content descends from.

    Usually one. More than one means a constructor combined ports, and then
    the constructor owes an explicit row projection: a merged factor cannot
    be classified after the fact without guessing which port it speaks for.
    """
    refs: Tuple[SourcePortRef, ...]

    def __post_init__(self):
        if not self.refs:
            raise ProvenanceError("factor source: no source ports recorded")
        ids = [r.ref for r in self.refs]
        if len(set(ids)) != len(ids):
            raise ProvenanceError(
                f"factor source: it names {ids} with a repeat")

    @property
    def mixed(self) -> bool:
        return len(self.refs) > 1

    @property
    def sole(self) -> "SourcePortRef":
        if self.mixed:
            raise ProvenanceError(
                f"factor source {[r.ref for r in self.refs]} combines several "
                f"ports; it has no single one")
        return self.refs[0]


@dataclass(frozen=True, slots=True)
class RowProjection:
    """THE authority: how one polarity's selected rows meet a semantic port.

    One label and one fibre key per selected row. The label projection is
    MANY-TO-ONE -- 192 rows over six labels, 32 to a fibre -- so a label
    alone never identifies a row; `(label, fibre_key)` does, bijectively, and
    that is checked rather than assumed.

    Ingress and egress are separate objects. A premise may present a
    different alphabet on each side, and collapsing the two is the mistake
    this type exists to make impossible.

    Ancestry and any payload/fibre partition SUMMARISE this record. They
    never produce it: nothing here is decided by a factor's role, type,
    width or placement.
    """
    port: SourcePortRef
    polarity: str
    alphabet: Tuple[int, ...]
    labels: Tuple[int, ...]
    fibre_keys: Tuple[int, ...]
    presenters: Tuple[str, ...]
    support: Tuple[int, ...]
    rows: Tuple[int, ...] = ()
    padding: Tuple[Tuple[int, int], ...] = ()
    # THE ASSEMBLY SCHEDULE, recorded by the constructor: which coordinates
    # carry the semantic symbol and which carry the fibre key, in the chart's
    # own address space, plus the width they live in. Reconstruction runs
    # from THIS, so `check_rows` re-derives each row from an independently
    # recorded placement instead of looking its own triples back up -- a
    # dictionary keyed on the very rows it is meant to prove would agree with
    # itself no matter what.
    label_wires: Tuple[int, ...] = ()
    fibre_wires: Tuple[int, ...] = ()
    row_width: int = 0

    def __post_init__(self):
        if self.polarity not in ("ingress", "egress"):
            raise ProvenanceError(
                f"row projection: polarity {self.polarity!r} is neither "
                f"ingress nor egress")
        if not self.presenters:
            raise ProvenanceError(
                "row projection: it names no presenting factor")
        if len(set(self.presenters)) != len(self.presenters):
            raise ProvenanceError(
                f"row projection: presenters {self.presenters} repeat")
        if not self.alphabet:
            raise ProvenanceError(
                "row projection: the semantic alphabet is empty")
        if len(set(self.alphabet)) != len(self.alphabet):
            raise ProvenanceError(
                f"row projection: alphabet {self.alphabet} repeats a symbol")
        n = len(self.labels)
        if len(self.fibre_keys) != n:
            raise ProvenanceError(
                f"row projection: {n} labels against {len(self.fibre_keys)} "
                f"fibre keys")
        if self.rows and len(self.rows) != n:
            raise ProvenanceError(
                f"row projection: {n} labels against {len(self.rows)} rows")
        if not n:
            raise ProvenanceError("row projection: it selects no rows")
        for L in self.labels:
            if not (0 <= L < len(self.alphabet)):
                raise ProvenanceError(
                    f"row projection: label {L} is outside its own "
                    f"{len(self.alphabet)}-symbol alphabet")
        pairs = list(zip(self.labels, self.fibre_keys))
        if len(set(pairs)) != n:
            raise ProvenanceError(
                "row projection: two rows share a (label, fibre_key) pair, so "
                "the pair does not identify a row")
        covered = set(self.labels)
        gaps = [i for i in range(len(self.alphabet)) if i not in covered]
        if gaps:
            raise ProvenanceError(
                f"row projection: symbols {[self.alphabet[i] for i in gaps]} "
                f"have no rows, so the alphabet is not covered")
        if len(set(self.support)) != len(self.support):
            raise ProvenanceError(
                f"row projection: support {self.support} repeats a wire")
        if self.row_width:
            lw, fw = tuple(self.label_wires), tuple(self.fibre_wires)
            if set(lw) & set(fw):
                raise ProvenanceError(
                    f"row projection: {sorted(set(lw) & set(fw))} carries both "
                    f"the semantic symbol and the fibre key")
            for w in lw + fw + tuple(w for w, _ in self.padding):
                if not (0 <= w < self.row_width):
                    raise ProvenanceError(
                        f"row projection: coordinate {w} is outside a "
                        f"{self.row_width}-wire row")
            for a in self.alphabet:
                if a >= (1 << len(lw)):
                    raise ProvenanceError(
                        f"row projection: symbol {a} does not fit its "
                        f"{len(lw)} label coordinates")
            for k in self.fibre_keys:
                if k >= (1 << len(fw)):
                    raise ProvenanceError(
                        f"row projection: fibre key {k} does not fit its "
                        f"{len(fw)} fibre coordinates")

    @property
    def fibre_sizes(self):
        out = [0] * len(self.alphabet)
        for L in self.labels:
            out[L] += 1
        return tuple(out)

    def row_of(self, label, fibre_key):
        """(label, fibre_key) -> the row it identifies. The projection has no
        inverse from the label alone, and does not pretend to."""
        for i, (L, k) in enumerate(zip(self.labels, self.fibre_keys)):
            if L == label and k == fibre_key:
                return i
        raise ProvenanceError(
            f"row projection: no row carries ({label}, {fibre_key})")

    def assemble(self, label, fibre_key):
        """Rebuild a row from the RECORDED schedule -- symbol on the label
        coordinates, fibre key on the fibre coordinates, padding fixed."""
        if not self.row_width:
            raise ProvenanceError(
                "row projection: no assembly schedule was recorded, so a row "
                "cannot be rebuilt independently of the rows themselves")
        out = 0
        for w, b in self.padding:
            if b:
                out |= 1 << (self.row_width - 1 - w)
        out |= scatter_code(self.alphabet[label], self.label_wires,
                            self.row_width)
        out |= scatter_code(fibre_key, self.fibre_wires, self.row_width)
        return out

    def check_rows(self, chart, where=""):
        """It projects THIS chart, and its schedule REBUILDS every row.

        The reconstruction is independent: it runs from the recorded label
        and fibre coordinates, not from the (label, fibre_key, row) triples
        being checked.
        """
        if not self.rows:
            raise ProvenanceError(
                f"{where}the projection records no rows to check")
        if tuple(self.rows) != tuple(chart.codes):
            raise ProvenanceError(
                f"{where}the projection is over rows {tuple(self.rows)[:6]}... "
                f"but the chart's are {tuple(chart.codes)[:6]}...")
        if self.row_width and self.row_width != chart.n_qubits:
            raise ProvenanceError(
                f"{where}the projection assembles {self.row_width}-wire rows "
                f"but the chart is over {chart.n_qubits}")
        for i, row in enumerate(self.rows):
            got = self.assemble(self.labels[i], self.fibre_keys[i])
            if got != row:
                raise ProvenanceError(
                    f"{where}row {i} is {row} but its recorded schedule "
                    f"assembles ({self.labels[i]}, {self.fibre_keys[i]}) to "
                    f"{got}")
        return True


PAYLOAD = "payload"
FIBRE = "fibre"


@dataclass(frozen=True, slots=True)
class BranchRoleContext:
    """Which source occurrences are this branch's payload, at ONE polarity.

    Ingress and egress are separate objects, always. A branch may present its
    semantic main occurrence on one side and a different one on the other --
    ctrl_ho's egress alphabet is not its ingress alphabet -- and a single
    mapping serving both is exactly how a polarity gets collapsed.

    The payload root is issued explicitly, including for a branch that
    captures nothing: "no context" is not "no payload".
    """
    polarity: str
    payload: Tuple[str, ...]        # source refs that ARE this branch's main
    fibre: Tuple[str, ...]          # captured bindings and inactive resources
    branch_index: int = -1
    cut_id: object = None

    def __post_init__(self):
        if self.polarity not in ("ingress", "egress"):
            raise ProvenanceError(
                f"branch role context: polarity {self.polarity!r} is neither "
                f"ingress nor egress")
        if not self.payload:
            raise ProvenanceError(
                f"branch role context ({self.polarity}): no payload root was "
                f"issued; a branch with no captured context still presents a "
                f"main occurrence")
        clash = set(self.payload) & set(self.fibre)
        if clash:
            raise ProvenanceError(
                f"branch role context ({self.polarity}): {sorted(clash)} is "
                f"recorded as both payload and fibre")

    def role_of(self, ref, where=""):
        if ref in set(self.payload):
            return PAYLOAD
        if ref in set(self.fibre):
            return FIBRE
        raise ProvenanceError(
            f"{where}source port {ref!r} has no recorded role at "
            f"{self.polarity}; this branch's role context names "
            f"{sorted(set(self.payload) | set(self.fibre))}")


@dataclass(frozen=True, slots=True)
class BranchMainProjection:
    """One prepared branch root's row projection, at ONE polarity.

    A thin typed use of the kernel: the branch's selected rows, the semantic
    main alphabet it presents, and the fibre key carrying everything it holds
    beside that. Completion later extends the fibre; it never touches the
    alphabet.
    """
    branch_index: int
    polarity: str
    projection: RowProjection
    roles: BranchRoleContext
    source_boundary: object = None

    def __post_init__(self):
        if self.polarity != self.projection.polarity:
            raise ProvenanceError(
                f"branch {self.branch_index}: the projection is "
                f"{self.projection.polarity} but the record says "
                f"{self.polarity}")
        if self.polarity != self.roles.polarity:
            raise ProvenanceError(
                f"branch {self.branch_index}: the role context is "
                f"{self.roles.polarity} but the record says {self.polarity}")

    @property
    def alphabet(self):
        return self.projection.alphabet

    @property
    def fibre_sizes(self):
        return self.projection.fibre_sizes


def project_branch_root(chart, roles, *, branch_index, polarity, port,
                        where=""):
    """Issue a branch root's row projection from its RECORDED ancestry.

    Every factor is classified by the role its source occurrence has in this
    branch, at this polarity. The label coordinates are the payload factors'
    own recorded placements and the fibre coordinates are the rest -- read
    off the schedule the chart already carries, not chosen here.
    """
    if chart.route is None or not chart.route.parts:
        raise ProvenanceError(
            f"{where}the branch root records no factors to project")
    lab_w, fib_w, pres = [], [], []
    for f, pl in zip(chart.route.parts, chart.route.placements):
        if f.source is None:
            raise ProvenanceError(
                f"{where}factor {f.name!r} carries no ancestry")
        if f.source.mixed:
            raise ProvenanceError(
                f"{where}factor {f.name!r} combines source ports "
                f"{[r.ref for r in f.source.refs]}; its constructor must "
                f"issue a row projection for it rather than leave it to be "
                f"classified")
        role = roles.role_of(f.source.sole.reaches(where), where)
        if role == PAYLOAD:
            pres.append(f.factor_id)
            lab_w.extend(pl)
        else:
            fib_w.extend(pl)
    if not pres:
        raise ProvenanceError(
            f"{where}no factor descends from this branch's payload root")
    lab_w, fib_w = tuple(lab_w), tuple(fib_w)
    n = chart.n_qubits
    alpha, pos = [], {}
    labels, keys = [], []
    for c in chart.codes:
        a = gather_code(c, lab_w, n)
        if a not in pos:
            pos[a] = len(alpha)
            alpha.append(a)
        labels.append(pos[a])
        keys.append(gather_code(c, fib_w, n))
    fixed = tuple((w, (chart.codes[0] >> (n - 1 - w)) & 1)
                  for w in range(n)
                  if w not in set(lab_w) and w not in set(fib_w))
    proj = RowProjection(
        port=port, polarity=polarity, alphabet=tuple(alpha),
        labels=tuple(labels), fibre_keys=tuple(keys), presenters=tuple(pres),
        support=tuple(sorted(set(lab_w) | set(fib_w))),
        rows=tuple(chart.codes), padding=fixed,
        label_wires=lab_w, fibre_wires=fib_w, row_width=n)
    proj.check_rows(chart, where)
    return BranchMainProjection(branch_index=branch_index, polarity=polarity,
                                projection=proj, roles=roles)


def derive_partition(chart, roles, where=""):
    """A DIAGNOSTIC SUMMARY of a chart's factor ancestry -- not an authority.

    The authority is the polarity's RowProjection. This only groups factors
    by the role their recorded source occurrence has in this branch, so a
    reader can see the split at a glance and a test can check it agrees with
    the projection. Nothing in the compiler may take a composition decision
    from it.

    Historically this read: "the payload/fibre split, from ancestry".

    `roles` maps a source occurrence to PAYLOAD or FIBRE -- the
    occurrence-relative role context the branch's preparation supplied: the
    payload/source occurrence is payload, every captured binding and every
    inactive completion resource is fibre. The split is then a lookup, not a
    decision: `Y_B` descending from the payload source is a presenter, and
    `Y_B` descending from a captured context is fibre, with nothing about the
    two factors themselves distinguishing them.

    The result is a validated CACHE of that ancestry, never an authority in
    its own right.
    """
    if chart.route is None:
        raise ProvenanceError(
            f"{where}a route-less chart has no factor ancestry to read")
    pres, fib = [], []
    for f in chart.route.parts:
        if f.source is None:
            raise ProvenanceError(
                f"{where}factor {f.name!r} records no source occurrence, so "
                f"whether it presents the payload cannot be read from its "
                f"ancestry")
        if isinstance(f.source, (tuple, list)):
            got = {roles.get(x) for x in f.source}
            if len(got) != 1 or None in got:
                raise ProvenanceError(
                    f"{where}factor {f.name!r} combines payload and carried "
                    f"ancestry {tuple(f.source)}; a constructor that merges "
                    f"them must supply an explicit semantic projection "
                    f"witness")
            role = got.pop()
        else:
            role = roles.get(f.source)
        if role is None:
            raise ProvenanceError(
                f"{where}factor {f.name!r} descends from {f.source!r}, which "
                f"this occurrence's role context does not name")
        (pres if role == PAYLOAD else fib).append(f.factor_id)
    if not pres:
        raise ProvenanceError(
            f"{where}no factor descends from the payload source, so this "
            f"boundary presents nothing")
    return tuple(pres), tuple(fib)


def restrict_to_cut(frame_or_chart, wires, ambient_width, where=""):
    """The codes a boundary carries ON the cut coordinates alone.

    A VALIDATOR of an already-recorded placement, never a way to discover
    one. What a premise says away from the cut must be CONSTANT across its
    own codes -- otherwise the interface is not cut-local and projecting it
    would invent an agreement that is not there.

    Returns `(cut_codes, off_cut)` where `off_cut` is the constant the
    premise carries away from the cut.
    """
    codes = tuple(frame_or_chart.codes)
    n = frame_or_chart.n_qubits
    W = tuple(wires)
    if n == len(W):
        return codes, 0
    if n != ambient_width:
        raise ProvenanceError(
            f"{where}the boundary spans {n} wires, which is neither the cut's "
            f"{len(W)} nor the register's {ambient_width}")
    outside = tuple(w for w in range(ambient_width) if w not in set(W))
    ref, out = None, []
    for c in codes:
        rest = gather_code(c, outside, ambient_width)
        if ref is None:
            ref = rest
        elif rest != ref:
            raise ProvenanceError(
                f"{where}the boundary varies off the cut {W} (code {c} "
                f"carries {rest} where an earlier one carried {ref}), so it "
                f"is not a cut-local interface")
        out.append(gather_code(c, W, ambient_width))
    if len(set(out)) != len(out):
        raise ProvenanceError(
            f"{where}restricting to the cut {W} collapses two states onto one "
            f"code, so the cut does not separate them")
    return tuple(out), (ref or 0)


@dataclass(frozen=True, slots=True)
class InterfaceEmbedding:
    """WHERE one polarity's effective interface lives, as the derivation says.

    This is the cut-facing interface, recorded independently per polarity: the
    ordered placement needed to reproduce that occurrence's EFFECTIVE Frame in
    the ambient register. It is not the completed Block's support, not the set
    of varying bits, not `Frame.n_qubits`, not a slot width, and not something
    recovered by trying candidate restrictions until one holds.

    The distinction it exists for: an open sum's effective output Frame spans
    the whole register while its RESULT lives on three coordinates, and a
    nested splice's five-wire output genuinely needs all five. Those two are
    indistinguishable from widths and bit patterns, and telling them apart by
    experiment is what this record replaces.

    `ordered_wires` selects the support. Codes may VALIDATE the record; they
    never choose it.

    WHAT RECONSTRUCTION PROVES: the exact typed ordered-code embedding, and
    only that. It does not reproduce a Frame's ports, sectors, label or
    expression metadata, and a completion port is never copied into a cut
    interface -- the cut is the typed interface, not the completed boundary.
    """
    ambient_width: int
    ordered_wires: Tuple[int, ...]
    local_codes: Tuple[int, ...]
    frame_width: int
    complement: int = 0
    logical: object = None
    cut_id: object = None            # the CURRENT occurrence's cut
    origin_cut: object = None        # where this interface was first selected
    polarity: str = "ingress"

    def __post_init__(self):
        if self.polarity not in ("ingress", "egress"):
            raise ProvenanceError(
                f"interface embedding: polarity {self.polarity!r} is neither "
                f"ingress nor egress")
        w = self.ordered_wires
        if len(set(w)) != len(w):
            raise ProvenanceError(
                f"interface embedding: wires {w} repeat a coordinate")
        for x in w:
            if not (0 <= x < self.ambient_width):
                raise ProvenanceError(
                    f"interface embedding: wire {x} is outside a "
                    f"{self.ambient_width}-wire register")
        if len(set(self.local_codes)) != len(self.local_codes):
            raise ProvenanceError(
                "interface embedding: its ordered codes repeat")
        for c in self.local_codes:
            if not (0 <= c < (1 << len(w))):
                raise ProvenanceError(
                    f"interface embedding: code {c} is outside its own "
                    f"{len(w)}-wire space")
        if self.frame_width not in (len(w), self.ambient_width):
            raise ProvenanceError(
                f"interface embedding: it reconstructs a {self.frame_width}-"
                f"wire frame, which is neither its own {len(w)} coordinates "
                f"nor the register's {self.ambient_width}")
        if self.frame_width == len(w) and self.complement:
            raise ProvenanceError(
                "interface embedding: a frame at interface width carries no "
                "complement, but one is recorded")
        for x in w:
            if (self.complement >> (self.ambient_width - 1 - x)) & 1:
                raise ProvenanceError(
                    f"interface embedding: the complement claims wire {x}, "
                    f"which the interface itself occupies; the fixed part and "
                    f"the interface are disjoint by construction")

    def require_provenance(self, where=""):
        """A record a production cut consumes carries its own identity.

        A missing cut is not a benign default: it is an interface nobody can
        say they selected, and composing across one would attribute it to
        whichever occurrence happened to read it.
        """
        if self.cut_id is None or self.cut_id == "":
            raise ProvenanceError(
                f"{where}the interface record carries no cut identity")
        if self.origin_cut is None or self.origin_cut == "":
            raise ProvenanceError(
                f"{where}the interface record carries no origin lineage, so "
                f"where it was first selected cannot be recovered")
        return True

    def recut(self, cut_id, polarity=None):
        """The SAME interface, read at a new occurrence's cut.

        The origin is preserved: an interface inherited across a Seq was
        selected by the child, and presenting it as freshly selected here
        would lose exactly the lineage a consumer needs.
        """
        return _dataclass_replace(
            self, cut_id=cut_id,
            origin_cut=(self.origin_cut if self.origin_cut is not None
                        else self.cut_id),
            polarity=polarity or self.polarity)

    @property
    def width(self) -> int:
        return len(self.ordered_wires)

    def reconstruct(self) -> "Frame":
        """The effective Frame this record describes -- byte for byte."""
        if self.frame_width == len(self.ordered_wires):
            codes = tuple(self.local_codes)
        else:
            codes = tuple(
                scatter_code(c, self.ordered_wires, self.ambient_width)
                | self.complement for c in self.local_codes)
        return Frame(logical=self.logical, n_qubits=self.frame_width,
                     codes=codes, label="interface")

    def check_reconstructs(self, frame, where=""):
        """It IS this frame -- same TYPE, same codes, same order, same width.

        Equal width and equal codes are not enough: Q(x)Q and Q-oQ are both
        four states on two wires, and an interface that validated against
        either would let a cut splice a pair onto a function.
        """
        got = self.reconstruct()
        if self.logical != frame.logical:
            raise ProvenanceError(
                f"{where}the interface record is typed "
                f"{pretty(self.logical) if self.logical is not None else None}"
                f" but the occurrence's frame is "
                f"{pretty(frame.logical) if frame.logical is not None else None}")
        if got.n_qubits != frame.n_qubits:
            raise ProvenanceError(
                f"{where}the interface record reconstructs a "
                f"{got.n_qubits}-wire frame but the occurrence's is "
                f"{frame.n_qubits}")
        if tuple(got.codes) != tuple(frame.codes):
            raise ProvenanceError(
                f"{where}the interface record reconstructs {tuple(got.codes)} "
                f"but the occurrence's frame is {tuple(frame.codes)}; the "
                f"recorded placement does not describe it")
        return True

    def transported(self, transport, cut_id=None, polarity=None):
        """This interface carried through THE recorded cut transport.

        A transported interface keeps its origin: it was selected where it
        was selected, and the transport moved it, it did not re-select it.
        """
        if tuple(transport.wires) != tuple(self.ordered_wires):
            raise ProvenanceError(
                f"the transport acts on {tuple(transport.wires)} but this "
                f"interface lives on {tuple(self.ordered_wires)}; they are "
                f"not the same placement")
        if transport.ambient_width != self.ambient_width:
            raise ProvenanceError(
                f"the transport is over {transport.ambient_width} wires but "
                f"this interface is over {self.ambient_width}")
        moved = _dataclass_replace(
            self, local_codes=tuple(transport.forward[c]
                                    for c in self.local_codes),
            polarity=polarity or self.polarity)
        return moved.recut(cut_id, polarity) if cut_id is not None else moved


def interface_from_frame(frame, wires, ambient_width, *, logical=None,
                         cut_id=None, origin_cut=None, polarity="ingress",
                         where=""):
    """Record an interface at an ALREADY-CHOSEN placement.

    The caller supplies the wires because the caller is the rule that placed
    the interface. This only restricts the frame onto them and checks that
    what is left over is genuinely fixed. Selecting here IS the origin, so
    `origin_cut` defaults to this occurrence's own cut.
    """
    codes, comp = restrict_to_cut(frame, wires, ambient_width, where)
    outside = tuple(x for x in range(ambient_width) if x not in set(wires))
    rec = InterfaceEmbedding(
        ambient_width=ambient_width, ordered_wires=tuple(wires),
        local_codes=tuple(codes), frame_width=frame.n_qubits,
        complement=(scatter_code(comp, outside, ambient_width)
                    if frame.n_qubits == ambient_width else 0),
        logical=(logical if logical is not None else frame.logical),
        cut_id=cut_id,
        origin_cut=(origin_cut if origin_cut is not None else cut_id),
        polarity=polarity)
    rec.check_reconstructs(frame, where)
    return rec


@dataclass(frozen=True, slots=True)
class JoinRoute:
    """A CORRELATED relational result, kept as what it is.

    `ChartRoute` means a reconstructible Cartesian Repart(Par(...)) and keeps
    that meaning. A cut join is not that in general: 192 Block states meet a
    six-state cut, so the result is a relation with one row per surviving
    state, not a product that can be rebuilt from per-factor codes.

    Every row records the pair it came from, so nothing is lost and nothing
    is invented: the producer label, the consumer label, and the ordered
    factor coordinates the composite state carries.
    """
    label: str
    parts: Tuple[ChartFactor, ...]          # ordered surviving factors
    placements: Tuple[Tuple[int, ...], ...]
    rows: Tuple[Tuple[int, ...], ...]       # per state: factor coordinates
    sources: Tuple[Tuple[int, int], ...]    # per state: (producer, consumer)
    codes: Tuple[int, ...]                  # per state: the ambient code
    support: Tuple[int, ...]
    n_qubits: int
    producer_face: object = None
    consumer_face: object = None
    transport: object = None
    kind: str = "join"
    # The recorded GRAFTS this join performed: which formal port each
    # polarity's cut replaced with which actual one. Both original
    # SourcePortRefs survive on the retained factors; nothing is relinked.
    substitutions: Tuple["SourceSubstitution", ...] = ()

    @property
    def reconstructible(self) -> bool:
        return False                        # a relation is not a schedule

    def decode(self, ambient_code):
        """One relation row, EXACTLY: the ordered factor coordinates and the
        (producer, consumer) source pair behind this ambient code -- or a
        refusal. Nothing is interpolated: a code the relation does not
        record has no row."""
        for i, c in enumerate(self.codes):
            if c == ambient_code:
                return self.rows[i], self.sources[i]
        raise ProvenanceError(
            f"join route {self.label}: ambient code {ambient_code} is not a "
            f"state of this relation")

    def moved(self, wire_map, ambient_width, label=None):
        """The SAME relation, re-addressed wire-by-wire. Rows, source pairs
        and factor identities are untouched; only where the coordinates sit
        changes. `wire_map` maps every current support wire."""
        places = tuple(tuple(wire_map[w] for w in pl)
                       for pl in self.placements)
        codes = []
        for row in self.rows:
            c = 0
            for coord, pl in zip(row, places):
                c |= scatter_code(coord, pl, ambient_width)
            codes.append(c)
        if len(set(codes)) != len(codes):
            raise ProvenanceError(
                f"join route {self.label}: the re-addressing collapses two "
                f"states")
        return _dataclass_replace(
            self, label=(label or self.label), placements=places,
            codes=tuple(codes),
            support=tuple(sorted(wire_map[w] for w in self.support)),
            n_qubits=ambient_width)

    def __post_init__(self):
        n = len(self.rows)
        if len(self.sources) != n or len(self.codes) != n:
            raise ProvenanceError(
                f"join route {self.label}: {n} rows against "
                f"{len(self.sources)} sources and {len(self.codes)} codes")
        if not n:
            raise ProvenanceError(
                f"join route {self.label}: the relation is empty")
        if len(set(self.codes)) != n:
            raise ProvenanceError(
                f"join route {self.label}: two states share an ambient code, "
                f"so the join is not injective")
        if len(set(self.sources)) != n:
            raise ProvenanceError(
                f"join route {self.label}: two states claim the same "
                f"(producer, consumer) pair")
        if len(self.parts) != len(self.placements):
            raise ProvenanceError(
                f"join route {self.label}: {len(self.parts)} factors against "
                f"{len(self.placements)} placements")
        ids = [f.factor_id for f in self.parts]
        if len(set(ids)) != len(ids):
            raise ProvenanceError(
                f"join route {self.label}: it retains one factor twice {ids}")
        for r in self.rows:
            if len(r) != len(self.parts):
                raise ProvenanceError(
                    f"join route {self.label}: a row has {len(r)} "
                    f"coordinates for {len(self.parts)} factors")
            for j, c in enumerate(r):
                if c not in self.parts[j].codes:
                    raise ProvenanceError(
                        f"join route {self.label}: row coordinate {c} is not "
                        f"a state of factor {self.parts[j].name!r}")

    def as_chart_route(self):
        """A ChartRoute ONLY when the rows independently prove a complete
        Cartesian product and a recorded scatter schedule rebuilds the codes
        exactly. Otherwise the result stays correlated, and says so."""
        want = 1
        for f in self.parts:
            want *= len(f.codes)
        if want != len(self.rows) or len(set(self.rows)) != len(self.rows):
            return None
        rep, pl = scatter_repart(self.placements, self.n_qubits)
        try:
            ch = par_then_repart(self.parts, rep, self.n_qubits, self.label,
                                 placements=pl, kind="scatter")
        except ProvenanceError:
            return None
        if tuple(ch.codes) != tuple(self.codes):
            return None
        return ch.route


@dataclass(frozen=True, slots=True)
class FaceSplit:
    """ONE premise split at its recorded cut face, at one polarity.

    `presenters` are the EXACT ordered factors the face names, resolved by
    recorded factor id -- several are allowed, and they need not be
    contiguous in the route. `rest` is every unmatched factor, in the
    route's original order, with its placement. `row_labels` is the full
    parent-state-to-face-label projection, and `joint_place` the
    concatenated presenter placement the face's codes are written on.
    Ancestry travels on the factors themselves; nothing here is selected by
    role, type, dimension, wire containment or varying bits.
    """
    presenters: Tuple[ChartFactor, ...]
    presenter_places: Tuple[Tuple[int, ...], ...]
    rest: Tuple[ChartFactor, ...]
    rest_places: Tuple[Tuple[int, ...], ...]
    row_labels: Tuple[int, ...]
    joint_place: Tuple[int, ...]


def split_at_face(chart, face, n, where=""):
    """Split one premise chart at its recorded CutFace.

    Every presenter is resolved by its recorded factor id, in the FACE's
    order; the face's codes are the joint presenter states (first named
    factor most significant); and each parent state's face label is read by
    following its joint presenter coordinate into the face's own record.
    """
    if chart.route is None:
        if not face.whole_chart:
            raise ProvenanceError(
                f"{where}a route-less premise needs an exhaustive atomic "
                f"face")
        if len(face.labels) != len(chart.codes):
            raise ProvenanceError(
                f"{where}the atomic face records {len(face.labels)} labels "
                f"for {len(chart.codes)} premise states")
        one = ChartFactor(factor_id=face.factor_ids[0],
                          name=chart.label or "u", owner=None,
                          n_qubits=len(face.placement),
                          codes=tuple(face.codes),
                          role=face.role or "residual", logical=face.logical)
        return FaceSplit(presenters=(one,),
                         presenter_places=(tuple(face.placement),),
                         rest=(), rest_places=(),
                         row_labels=tuple(face.labels),
                         joint_place=tuple(face.placement))
    if face.whole_chart and len(chart.route.parts) == 1:
        # An EXHAUSTIVE face says the whole premise is one factor, and it was
        # validated against the premise before it was placed. A lift gives
        # that same single factor its ambient placement and mints its own id
        # for it; the face still names the one factor there is, so it is
        # matched by the recorded exhaustiveness rather than by an id the
        # lift chose after the face was issued.
        pres = (chart.route.parts[0],)
        pres_pl = (tuple(chart.route.placements[0]),)
    else:
        by_id = {}
        for f, pl in zip(chart.route.parts, chart.route.placements):
            if f.factor_id in by_id:
                raise ProvenanceError(
                    f"{where}the route resolves factor id "
                    f"{f.factor_id!r} twice")
            by_id[f.factor_id] = (f, tuple(pl))
        missing = [fid for fid in face.factor_ids if fid not in by_id]
        if missing:
            raise ProvenanceError(
                f"{where}the face names {tuple(face.factor_ids)}, but "
                f"{missing} is not in this premise's route")
        pres = tuple(by_id[fid][0] for fid in face.factor_ids)
        pres_pl = tuple(by_id[fid][1] for fid in face.factor_ids)
    named = set(face.factor_ids) | {f.factor_id for f in pres}
    rest, rest_pl = [], []
    for f, pl in zip(chart.route.parts, chart.route.placements):
        if f.factor_id not in named:
            rest.append(f)
            rest_pl.append(tuple(pl))
    joint_place = tuple(w for pl in pres_pl for w in pl)
    # PARENT state -> face label, through the presenters' own recorded
    # placements and the face's own recorded joint codes. A face records
    # one label per JOINT presenter state; a parent chart may carry many
    # parent states per joint state, and every one of them follows its
    # recorded coordinate -- no scan for which bits vary.
    at = {c: i for i, c in enumerate(face.codes)}
    labels = []
    for c in chart.codes:
        sub = 0
        for f, pl in zip(pres, pres_pl):
            sub = (sub << f.n_qubits) | gather_code(c, pl, n)
        if sub not in at:
            raise ProvenanceError(
                f"{where}a premise state carries {sub} on the face's "
                f"presenters, which the face does not record as a state")
        j = at[sub]
        if j >= len(face.labels):
            raise ProvenanceError(
                f"{where}the face records no label for its state {j}")
        labels.append(face.labels[j])
    return FaceSplit(presenters=pres, presenter_places=pres_pl,
                     rest=tuple(rest), rest_places=tuple(rest_pl),
                     row_labels=tuple(labels), joint_place=joint_place)


def seq_cut(producer, consumer, transport, *, producer_support,
            consumer_support, producer_face, consumer_face,
            producer_ingress_face=None, consumer_egress_face=None,
            producer_interface=None, consumer_interface=None,
            widened_frame=None, where="", label="seq:cut"):
    """Compose two occurrence boundaries across the cut Seq actually selected.

        physical:   A G A^dagger F          (F, then A^dagger, then G, then A)

    and this describes THAT circuit. It emits nothing.

    THE JOIN IS RELATIONAL, through the two recorded CutFaces. A composite
    state is a pair of premise states whose recorded cut LABELS the transport
    relates -- not a pair whose cut bits happen to agree, and not a lookup
    keyed on a cut label, which cannot work at all: 192 Block states project
    onto six labels with 32 in every fibre, and all 192 survive.

    Both premises keep everything they brought. The producer's prefix
    factors, the one shared cut, and the consumer's context factors all
    appear, in that order, with their identities, owners, roles, types,
    descriptors and sparse orders intact.

    THE PRODUCER'S ACTION IS NOT COMPOSED INTO THE LAYOUT. A cut composes
    LAYOUTS: the matched producer-output state at recorded label m contributes
    the producer-INPUT state at that same label m. Inverting the producer's
    physical action into the ingress would gauge it away -- an X before a
    completed identity would compose to a reported identity.
    """
    n = transport.ambient_width
    W = tuple(transport.wires)
    P_in, P_out = producer.ingress, producer.egress
    C_in, C_out = consumer.ingress, consumer.egress
    for nm, ch in (("producer ingress", P_in), ("producer egress", P_out),
                   ("consumer ingress", C_in), ("consumer egress", C_out)):
        if ch.space != "ambient":
            raise ProvenanceError(
                f"{where}the {nm} chart is {ch.space!r}, not ambient")
        if ch.n_qubits != n:
            raise ProvenanceError(
                f"{where}the {nm} chart spans {ch.n_qubits} wires but the cut "
                f"is over {n}")
    if P_in.dim != P_out.dim:
        raise ProvenanceError(
            f"{where}the producer's boundary is {P_in.dim} in and "
            f"{P_out.dim} out; the two polarities do not balance")
    if C_in.dim != C_out.dim:
        raise ProvenanceError(
            f"{where}the consumer's boundary is {C_in.dim} in and "
            f"{C_out.dim} out")
    if producer_face is None or consumer_face is None:
        raise ProvenanceError(
            f"{where}a cut needs a recorded face on each side; without one "
            f"the factor presenting the cut would have to be guessed")
    if producer_face.polarity != "egress":
        raise ProvenanceError(
            f"{where}the producer's face is {producer_face.polarity}, not "
            f"egress")
    if consumer_face.polarity != "ingress":
        raise ProvenanceError(
            f"{where}the consumer's face is {consumer_face.polarity}, not "
            f"ingress")
    # NOTE on cut identities: a premise that is itself a composite carries
    # an ingress face descending from ITS producer and an egress face from
    # ITS consumer, with different origin cuts -- so the two faces of one
    # premise are not required to share a cut id. Staleness is caught
    # structurally instead: every face must present exactly its chart's
    # recorded factors, codes and placements below.
    if producer_ingress_face is not None and \
            producer_ingress_face.polarity != "ingress":
        raise ProvenanceError(
            f"{where}the producer's ingress face is recorded at polarity "
            f"{producer_ingress_face.polarity!r}")
    if consumer_egress_face is not None and \
            consumer_egress_face.polarity != "egress":
        raise ProvenanceError(
            f"{where}the consumer's egress face is recorded at polarity "
            f"{consumer_egress_face.polarity!r}")
    # EXPLICIT, NONEMPTY ORDERED ALPHABETS. An absent alphabet would make
    # label ordinals the only currency, and matching ordinals is exactly the
    # positional trap this join exists to close.
    for nm, f in (("producer", producer_face), ("consumer", consumer_face)):
        if not f.alphabet:
            raise ProvenanceError(
                f"{where}the {nm}'s face records no ordered cut alphabet; "
                f"the cut cannot be matched by label position")
    if producer_face.n_labels != consumer_face.n_labels:
        raise ProvenanceError(
            f"{where}the producer presents {producer_face.n_labels} cut "
            f"symbols and the consumer {consumer_face.n_labels}; they are not "
            f"the same cut")
    # THE FACES ARE THIS CUT'S. Each validates against the chart it claims
    # to present -- recorded factor ids, codes and placements, never a guess
    # -- and against the cut placement the transport actually binds. An
    # EXHAUSTIVE face over a single-factor route follows the recorded
    # exhaustiveness convention: a lift mints its own id for the one factor
    # there is, and the face still names that factor by presenting exactly
    # its codes on exactly its placement.
    _p_if0 = producer_ingress_face or producer_face
    _c_ef0 = consumer_egress_face or consumer_face

    def _check_face(f, ch, nm):
        if ch.route is not None and f.whole_chart \
                and len(ch.route.parts) == 1:
            # The face may have been issued on the premise's own local
            # coordinates before the lift placed it; the codes are the
            # identity, and the lift's own recorded placement is where the
            # one factor now sits.
            g = ch.route.parts[0]
            if tuple(f.codes) != tuple(g.codes):
                raise ProvenanceError(
                    f"{where}{nm} face: the exhaustive face records "
                    f"{len(f.codes)} states but the premise's one factor has "
                    f"{len(g.codes)}, or different codes")
            return
        f.check_against(ch, f.cut_id, f"{where}{nm} face: ")

    for nm, f, ch in (("producer egress", producer_face, P_out),
                      ("producer ingress", _p_if0, P_in),
                      ("consumer ingress", consumer_face, C_in),
                      ("consumer egress", _c_ef0, C_out)):
        _check_face(f, ch, nm)
    # A premise's face presents the cut either on the completed COMMON
    # placement or on the premise's OWN recorded placement inside it (the
    # completion certificate is what relates the two). Anything else is a
    # face of a different cut. When a face sits on the premise's own
    # narrower placement, its symbols are EMBEDDED into the common cut
    # space through that recorded placement -- never through a guess.
    def _embedding(f, prem_wires, nm):
        if set(f.interface_wires) == set(W):
            return None
        pw = tuple(prem_wires)
        if pw and tuple(f.interface_wires) == pw:
            if transport.completion is None:
                raise ProvenanceError(
                    f"{where}the {nm}'s face presents the cut on "
                    f"{tuple(f.interface_wires)}, inside the cut "
                    f"{tuple(W)}, but no completion records why the two "
                    f"placements meet at one cut")
            return pw
        raise ProvenanceError(
            f"{where}the {nm}'s face presents the cut on "
            f"{tuple(f.interface_wires)} but the transport binds "
            f"{tuple(W)} (premise placement {pw or tuple(W)}); it is a "
            f"face of a different cut")

    p_emb = _embedding(producer_face, transport.producer_wires, "producer")
    c_emb = _embedding(consumer_face, transport.consumer_wires, "consumer")
    _w_mask = 0
    for w in W:
        _w_mask |= 1 << (n - 1 - w)

    def _embed_sym(sym, emb, nm):
        if emb is None:
            return sym
        amb = scatter_code(sym, emb, n)
        if amb & ~_w_mask:
            raise ProvenanceError(
                f"{where}the {nm}'s cut symbol {sym} lies outside the "
                f"completed cut {tuple(W)}")
        return gather_code(amb, W, n)

    p_alpha = tuple(_embed_sym(a, p_emb, "producer")
                    for a in producer_face.alphabet)
    c_alpha = tuple(_embed_sym(a, c_emb, "consumer")
                    for a in consumer_face.alphabet)
    for nm, alpha in (("producer", p_alpha), ("consumer", c_alpha)):
        if len(set(alpha)) != len(alpha):
            raise ProvenanceError(
                f"{where}two of the {nm}'s cut symbols embed onto one code")
        for a in alpha:
            if not (0 <= a < len(transport.forward)):
                raise ProvenanceError(
                    f"{where}the {nm}'s cut symbol {a} is outside the "
                    f"transport's own {len(transport.forward)}-code space")
    # THE TRANSPORT IS THE SELECTED ONE: built for exactly the cut codes the
    # consumer's face presents, in their recorded order, and its producer
    # side must present exactly the codes the transport was selected onto.
    transport.check_selected(
        c_alpha, tuple(transport.forward[a] for a in c_alpha), where)
    if set(p_alpha) != set(transport.producer_codes):
        raise ProvenanceError(
            f"{where}the producer's face presents {p_alpha} but the "
            f"selected transport records {tuple(transport.producer_codes)}; "
            f"they are not the same cut")
    # A COMPLETION travels with its transport, and is re-validated HERE
    # against the two recorded interfaces and the widened frame -- a caller
    # may prevalidate, but this join must be independently safe.
    if transport.completion is not None:
        if producer_interface is None or consumer_interface is None or \
                widened_frame is None:
            raise ProvenanceError(
                f"{where}the transport carries a cut completion, but the two "
                f"interface embeddings and the widened frame were not "
                f"supplied, so it cannot be validated here")
        transport.completion.check_against(
            producer_interface, consumer_interface,
            transport.completion.cut_id, widened_frame, where)

    def _pair(x, nm):
        if isinstance(x, tuple) and len(x) == 2 and \
                all(isinstance(y, tuple) for y in x):
            return tuple(x[0]), tuple(x[1])
        raise ProvenanceError(
            f"{where}the {nm} support must be recorded per polarity as "
            f"(ingress, egress); got {x!r}")
    p_in_sup, p_out_sup = _pair(producer_support, "producer")
    c_in_sup, c_out_sup = _pair(consumer_support, "consumer")
    for nm, sup, ch in (("producer ingress", p_in_sup, P_in),
                        ("producer egress", p_out_sup, P_out),
                        ("consumer ingress", c_in_sup, C_in),
                        ("consumer egress", c_out_sup, C_out)):
        own = ch.support(f"{where}{nm}: ")
        if set(sup) != set(own):
            raise ProvenanceError(
                f"{where}the supplied {nm} support {tuple(sorted(sup))} is "
                f"not the chart's own recorded {tuple(sorted(own))}")

    # THE CORRESPONDENCE, SYMBOL BY SYMBOL through the transport. A consumer
    # label presenting symbol c meets the producer label presenting
    # forward[c] -- wherever in the producer's recorded order that symbol
    # sits. Label ordinal i is NEVER equated with label ordinal i: sparse
    # and reordered alphabets are the ordinary case, not an exception.
    # Symbols compare in the CUT's own space, each side embedded through its
    # recorded placement when a completion widened the cut.
    p_at = {a: i for i, a in enumerate(p_alpha)}
    lab_of_consumer = {}
    for i, c in enumerate(c_alpha):
        moved = transport.forward[c]
        if moved not in p_at:
            raise ProvenanceError(
                f"{where}the transport carries the consumer's cut symbol {c} "
                f"to {moved}, which the producer's alphabet "
                f"{p_alpha} does not present")
        lab_of_consumer[i] = p_at[moved]

    # Each polarity is split by ITS OWN recorded face. The two share one
    # factor lineage but their codes and placements are recorded
    # independently, so using the egress face on the ingress chart would ask
    # one polarity to answer for the other.
    p_if = producer_ingress_face or producer_face
    c_ef = consumer_egress_face or consumer_face
    p_in_sp = split_at_face(P_in, p_if, n, f"{where}producer ingress: ")
    p_out_sp = split_at_face(P_out, producer_face, n,
                             f"{where}producer egress: ")
    c_in_sp = split_at_face(C_in, consumer_face, n,
                            f"{where}consumer ingress: ")
    c_out_sp = split_at_face(C_out, c_ef, n, f"{where}consumer egress: ")

    p_proj = p_out_sp.row_labels
    c_proj = c_in_sp.row_labels

    def _lineage(f):
        if f.source is None:
            return None
        return tuple((r.ref, r.origin_cut, r.root) for r in f.source.refs)

    def _coequalize(p_parts, p_places, c_rest, c_rest_pl, pol_nm):
        """A GENUINELY shared non-cut resource appears exactly once.

        Named by recorded owner on both premises, and kept only under EXACT
        agreement -- owner, logical type, ordered codes, placement, and the
        full recorded source lineage. Anything less is two different
        resources wearing one owner, and the overlap is refused rather than
        silently overwritten.
        """
        p_by_owner = {}
        for f, pl in zip(p_parts, p_places):
            if f.owner is not None:
                p_by_owner.setdefault(f.owner, []).append((f, tuple(pl)))
        keep, keep_pl, coeq = [], [], set()
        for f, pl in zip(c_rest, c_rest_pl):
            hits = p_by_owner.get(f.owner) if f.owner is not None else None
            if not hits:
                keep.append(f)
                keep_pl.append(tuple(pl))
                continue
            if len(hits) > 1:
                raise ProvenanceError(
                    f"{where}the producer carries owner {f.owner!r} twice at "
                    f"{pol_nm}; which copy the consumer's shares is not "
                    f"derivable")
            pf, ppl = hits[0]
            if not (pf.logical == f.logical
                    and tuple(pf.codes) == tuple(f.codes)
                    and ppl == tuple(pl)
                    and _lineage(pf) == _lineage(f)):
                raise ProvenanceError(
                    f"{where}both premises carry owner {f.owner!r} at "
                    f"{pol_nm} but the two records disagree on type, codes, "
                    f"placement or source lineage; a shared resource is one "
                    f"resource, and this overlap is refused rather than "
                    f"overwritten")
            coeq |= set(pl)
        return tuple(keep), tuple(keep_pl), coeq

    _p_retained_in = tuple(p_in_sp.rest) + tuple(p_in_sp.presenters)
    _p_retained_in_pl = tuple(p_in_sp.rest_places) \
        + tuple(p_in_sp.presenter_places)
    c_ctx_in, c_ctx_in_pl, coeq_in = _coequalize(
        _p_retained_in, _p_retained_in_pl,
        c_in_sp.rest, c_in_sp.rest_places, "ingress")
    _p_rest_out = tuple(p_out_sp.rest)
    _p_rest_out_pl = tuple(p_out_sp.rest_places)
    c_ctx_out, c_ctx_out_pl, coeq_out = _coequalize(
        _p_rest_out, _p_rest_out_pl,
        c_out_sp.rest, c_out_sp.rest_places, "egress")

    # SUPPORT OVERLAP IS NEVER OVERWRITTEN SILENTLY. The premises may share
    # coordinates only where the cut substitutes the formal port, or where a
    # coequalized shared resource sits -- anywhere else, two premises are
    # claiming one wire for two different resources.
    _over_in = set(p_in_sup) & set(c_in_sup)
    _ok_in = set(c_in_sp.joint_place) | coeq_in
    if not _over_in <= _ok_in:
        raise ProvenanceError(
            f"{where}the two premises' ingress supports overlap on "
            f"{sorted(_over_in - _ok_in)}, which is neither the cut nor a "
            f"recorded shared resource; refusing to overwrite it silently")
    _over_out = set(p_out_sup) & set(c_out_sup)
    _ok_out = set(p_out_sp.joint_place) | coeq_out
    if not _over_out <= _ok_out:
        raise ProvenanceError(
            f"{where}the two premises' egress supports overlap on "
            f"{sorted(_over_out - _ok_out)}, which is neither the cut nor a "
            f"recorded shared resource; refusing to overwrite it silently")

    ing, egr, sources = [], [], []
    for p_lab in range(len(P_out.codes)):
        p_face_lab = p_proj[p_lab]
        for c_lab in range(len(C_in.codes)):
            if lab_of_consumer[c_proj[c_lab]] != p_face_lab:
                continue
            pc_in, cc_in = P_in.codes[p_lab], C_in.codes[c_lab]
            pc_out = P_out.codes[p_lab]
            cc_out = transport.apply(C_out.codes[c_lab])
            # A coequalized resource is ONE resource, so it is a further
            # JOIN CONDITION: a premise pair holding it in two different
            # states is not a state of the composition and is excluded --
            # the relation keeps exactly the rows where the one resource is
            # in one state.
            if any(gather_code(pc_in, (w,), n) != gather_code(cc_in, (w,), n)
                   for w in coeq_in):
                continue
            if any(gather_code(pc_out, (w,), n) !=
                   gather_code(cc_out, (w,), n) for w in coeq_out):
                continue
            k_in = cc_in
            for w in p_in_sup:
                k_in = replace_code(k_in, (w,), gather_code(pc_in, (w,), n), n)
            k_out = pc_out
            for w in c_out_sup:
                k_out = replace_code(k_out, (w,),
                                     gather_code(cc_out, (w,), n), n)
            ing.append(k_in)
            egr.append(k_out)
            sources.append((p_lab, c_lab))
    if not sources:
        raise ProvenanceError(
            f"{where}no producer state meets any consumer state at the cut")
    for nm, codes in (("ingress", ing), ("egress", egr)):
        if len(set(codes)) != len(codes):
            raise ProvenanceError(
                f"{where}the composed {nm} repeats a code, so the recorded "
                f"cut correspondence is ambiguous")

    comp_in_sup = tuple(sorted(set(p_in_sup) | set(c_in_sup)))
    comp_out_sup = tuple(sorted(set(p_out_sup) | set(c_out_sup)))

    _identity_tr = tuple(transport.forward) == \
        tuple(range(len(transport.forward)))

    def _moved(f, place):
        """A retained factor carried through the cut transport.

        The egress side keeps the CONSUMER's presenter, and the physical
        Align moved it, so the factor's own codes move with it. Its identity
        does not: the same factor_id, the same owner, role, type and
        descriptor -- one lineage, re-expressed. A factor holding only a
        SLICE of a non-identity cut cannot be moved factor-by-factor, and
        says so rather than staying silently unmoved.
        """
        if f is None or not place or _identity_tr:
            return f
        inner = tuple(place.index(w) for w in W if w in place)
        if not inner:
            return f                     # entirely off the cut
        if len(inner) != len(W):
            raise ProvenanceError(
                f"{where}factor {f.name!r} holds only part of a "
                f"non-identity cut; its states cannot be transported "
                f"factor-by-factor")
        moved = []
        for c in f.codes:
            sub = gather_code(c, inner, f.n_qubits)
            moved.append(replace_code(c, inner, transport.forward[sub],
                                      f.n_qubits))
        if len(set(moved)) != len(moved):
            raise ProvenanceError(
                f"{where}transporting {f.name!r} through the cut collapses "
                f"two of its states")
        return _dataclass_replace(f, codes=tuple(moved))

    # RETAINED, per polarity: producer prefix, the shared cut presenters,
    # consumer context. The ingress reads its cut from the producer
    # (upstream side), the egress from the transported consumer (downstream
    # side). Only the matched formal occurrence is removed.
    parts_in = tuple(p_in_sp.rest) + tuple(p_in_sp.presenters) + c_ctx_in
    places_in = tuple(p_in_sp.rest_places) \
        + tuple(p_in_sp.presenter_places) + c_ctx_in_pl
    _c_pres_o_moved = tuple(_moved(f, pl) for f, pl in
                            zip(c_out_sp.presenters,
                                c_out_sp.presenter_places))
    parts_out = _p_rest_out + _c_pres_o_moved + c_ctx_out
    places_out = _p_rest_out_pl + tuple(c_out_sp.presenter_places) \
        + c_ctx_out_pl
    for nm, parts in (("ingress", parts_in), ("egress", parts_out)):
        ids = [f.factor_id for f in parts]
        if len(set(ids)) != len(ids):
            raise ProvenanceError(
                f"{where}the {nm} join retains one factor twice: {ids}")

    # THE GRAFTS, RECORDED: each polarity's cut replaced a formal port with
    # an actual one. Both original SourcePortRefs stay on their factors,
    # untouched -- a substitution is a fact about the composition, never a
    # relink of either premise.
    def _refs_of(f):
        return tuple(f.source.refs) if f is not None and f.source is not None \
            else ()
    substitutions = []
    for pol_nm, replaced_fs, by_fs in (
            ("ingress", c_in_sp.presenters, p_in_sp.presenters),
            ("egress", p_out_sp.presenters, c_out_sp.presenters)):
        for rf, bf in zip(replaced_fs, by_fs):
            rr, br = _refs_of(rf), _refs_of(bf)
            if rr and br and rr[0].ref != br[0].ref:
                substitutions.append(SourceSubstitution(
                    replaced=rr[0].ref, by=br[0].ref,
                    at_cut=consumer_face.cut_id, polarity=pol_nm))
    substitutions = tuple(substitutions)

    def _rows(codes, parts, places):
        out = []
        for c in codes:
            out.append(tuple(gather_code(c, pl, n) for pl in places))
        return tuple(out)

    def _build(codes, parts, places, side, sup):
        # A joined chart ALWAYS carries its relation. An empty factor list or
        # a relation that will not validate is an error here, not a reason to
        # hand back a route-less chart: falling back would erase exactly the
        # rows and source pairs a downstream cut needs.
        if not parts:
            raise ProvenanceError(
                f"{where}the composed {side} retains no factor, so the join "
                f"has nothing to present at a further cut")
        jr = JoinRoute(
            label=f"{label}^{side}", parts=tuple(parts),
            placements=tuple(places), rows=_rows(codes, parts, places),
            sources=tuple(sources), codes=tuple(codes),
            support=tuple(sup), n_qubits=n,
            producer_face=producer_face, consumer_face=consumer_face,
            transport=transport, substitutions=substitutions)
        # A Cartesian result may return to a ChartRoute -- but only when its
        # own rows prove it and a recorded schedule rebuilds the codes. A
        # correlated one STAYS a JoinRoute, rows and sources intact.
        return BoundaryChart(
            n_qubits=n, codes=tuple(codes),
            route=(jr.as_chart_route() or jr),
            label=f"{label}^{side}", space="ambient",
            support_wires=tuple(sup))

    authority = DERIVED if DERIVED in (producer.authority,
                                       consumer.authority) else FRAME_DEFAULT
    _ci = _build(ing, parts_in, places_in, "ingress", comp_in_sup)
    _ce = _build(egr, parts_out, places_out, "egress", comp_out_sup)

    # THE COMPOSITE'S OWN FACES, so a second Seq can consume this result.
    # Each DESCENDS from the surviving premise's external authority: the
    # ingress is the producer's own ingress face, the egress the consumer's
    # own egress face carried through the same transport the gates used.
    # Their recorded row projections, alphabets and source lineage are
    # TRANSPORTED, never rebuilt from a row image or a first-appearance
    # gather, and each is validated against the chart it is attached to.
    def _out_face(src_face, split, chart, pol, transported):
        if src_face is None or not split.presenters:
            return None
        face = src_face
        if transported and not _identity_tr:
            iface = tuple(src_face.interface_wires)
            if tuple(iface) != tuple(W):
                return None    # not expressible on this cut's own order
            if len(split.presenters) != 1:
                return None    # a sliced non-identity move was refused above
            moved_f = _moved(split.presenters[0],
                             split.presenter_places[0])
            face = _dataclass_replace(
                src_face, codes=tuple(moved_f.codes),
                alphabet=tuple(transport.forward[a]
                               for a in src_face.alphabet))
        # RE-EXPRESSED against the factors the join actually retained: the
        # same row projection, alphabet and source lineage, now naming the
        # retained presenters by THEIR recorded identities and placements --
        # a lift or an atomic mint gave the one factor its own id after the
        # face was issued, and the face follows the factor, never a bit
        # image of the composite's rows.
        retained = (tuple(_moved(f, pl) for f, pl in
                          zip(split.presenters, split.presenter_places))
                    if transported else tuple(split.presenters))
        face = _dataclass_replace(
            face,
            factor_ids=tuple(f.factor_id for f in retained),
            placement=tuple(w for pl in split.presenter_places for w in pl),
            role=(retained[0].role if len(retained) == 1 else ""),
            logical=(retained[0].logical if len(retained) == 1 else None),
            descriptor=(retained[0].descriptor if len(retained) == 1
                        else None),
            whole_chart=False)
        if chart.route is None:
            return None
        face.check_against(chart, face.cut_id, f"{where}composite {pol}: ")
        return face

    return (SelectedBoundary(ingress=_ci, egress=_ce, origin=label,
                             authority=authority),
            _out_face(p_if, p_in_sp, _ci, "ingress", False),
            _out_face(c_ef, c_out_sp, _ce, "egress", True))


def localize_bindings(parent_bindings, local_wires, local_to_ambient,
                      where=""):
    """Relocate owned resources into ONE branch's coordinates, and record it.

    THE single formulation, shared by every open-sum adapter. Only the WIRES
    change: the owner, the logical type, the introduction cut and the ordered
    codes stay the parent's, because the resource inside the branch is the
    resource outside it.

    Two adapters spelling this out separately is exactly how they drift, and
    the drift is invisible from the outside -- both produce a well-formed
    chart over the right basis, and only the identities differ.

    Returns `(views, transports)`: the typed views to hand to the nested
    compilation, and the handoff certificates, each already checked to land
    on the parent's own placement under `local_to_ambient`.
    """
    views, transports = {}, []
    for b in parent_bindings:
        if b.name not in local_wires:
            raise ProvenanceError(
                f"{where}resource {b.name!r} is used by this branch but was "
                f"assigned no branch-local wires")
        view = TypedBinding(name=b.name, logical=b.logical,
                            wires=tuple(local_wires[b.name]),
                            owner_id=b.owner_id, intro_cut=b.intro_cut,
                            codes=tuple(b.codes))
        views[b.name] = view
        transports.append(
            issue_binding_transport(b, view, local_to_ambient, where))
    return views, tuple(transports)


@dataclass(frozen=True, slots=True)
class CompletedBranch:
    """One alternative of an open sum, completed against its INACTIVE context.

    `uses` is the set of owner ids this branch's own derivation actually
    binds -- recorded provenance, never inferred from a type, a dimension, a
    name or which bits vary. `inactive` is every other owned resource at this
    occurrence: the branch does not touch it, so it is carried through
    unchanged and multiplies the completed dimension exactly once.

        Complete(u_i | Gamma_inactive) = V_{u_i} (x) Y_{Gamma_inactive}

    The branch's OWN selected root is the authority; its Frame is never read
    when a selected boundary exists, and it is never recompiled.
    """
    index: int
    artifact: object                       # the exact BranchArtifact, by identity
    uses: Tuple[str, ...]
    inactive: Tuple["TypedBinding", ...]
    tag_value: int
    ingress: BoundaryChart
    egress: BoundaryChart
    # The map emission will need. Recorded, so nothing downstream has to
    # reconstruct it from chart geometry.
    local_to_ambient: Tuple[int, ...] = ()
    # The resources this branch USES, as their full typed bindings and not
    # only as the owner ids in `uses`. A resource consumed inside a branch's
    # own derivation is spliced into that branch's chart rather than carried
    # beside it, so without this record its type, placement and lineage would
    # survive only where some OTHER branch happens to list it as inactive.
    # Provenance must not depend on that accident -- nor on whether the
    # parent Frame turned out able to factorize it.
    used_bindings: Tuple["TypedBinding", ...] = ()
    # The recorded HANDOFFS: one per resource this branch was given. These
    # are what prove the nested derivation used the parent's resource, which
    # `used_bindings` -- the parent's intention -- cannot say on its own.
    binding_transport: Tuple["BindingTransport", ...] = ()
    # The COMPLETED per-polarity row projections: the branch's own
    # projections transported through the lift with the inactive resources
    # appended to the fibre. Main alphabet and labels are the branch's own,
    # unchanged. These are what the Block's cut face consumes.
    ingress_projection: object = None
    egress_projection: object = None

    @property
    def dim(self) -> int:
        return self.ingress.dim

    def __post_init__(self):
        if self.ingress.dim != self.egress.dim:
            raise ProvenanceError(
                f"branch {self.index}: completed ingress {self.ingress.dim} "
                f"and egress {self.egress.dim} disagree; the two polarities "
                f"are completed independently but must balance")
        for b in self.inactive:
            if b.owner_id in self.uses:
                raise ProvenanceError(
                    f"branch {self.index}: owner {b.owner_id} is recorded as "
                    f"both used and inactive")
        _used_ids = {b.owner_id for b in self.used_bindings}
        if self.used_bindings and _used_ids != set(self.uses):
            raise ProvenanceError(
                f"branch {self.index}: the typed used-bindings name "
                f"{sorted(_used_ids)} but `uses` records "
                f"{sorted(set(self.uses))}")
        _tr_ids = {t.owner_id for t in self.binding_transport}
        if len(_tr_ids) != len(self.binding_transport):
            raise ProvenanceError(
                f"branch {self.index}: one owner is transported twice")
        if self.binding_transport and _tr_ids != set(self.uses):
            raise ProvenanceError(
                f"branch {self.index}: handoffs were recorded for "
                f"{sorted(_tr_ids)} but `uses` records "
                f"{sorted(set(self.uses))}")


@dataclass(frozen=True, slots=True)
class OpenUseBlockPlan:
    """The tagged direct sum of the completed alternatives.

        parent = Block(Complete(u_0 | G_0), ..., Complete(u_n | G_n))

    a DIRECT SUM of independently completed blocks -- never the sum of the
    branch dimensions times one uniform context factor, which is a different
    claim that can hit the same number.
    """
    branches: Tuple[CompletedBranch, ...]
    ambient_width: int              # the CONTAINING register, len(p.new_to_old)
    block_width: int                # the wires the Block actually spans
    tag_wires: Tuple[int, ...]
    workspace_wires: Tuple[int, ...]
    block_to_ambient: Tuple[int, ...]   # block-local wire -> register wire
    ingress: BoundaryChart
    egress: BoundaryChart
    support: Tuple[int, ...]
    spectators: Tuple[int, ...]

    def tag_bit(self, index: int) -> int:
        """The ambient bit pattern selecting this block's sector."""
        blk = self.branches[index]
        bit = 0
        for i, w in enumerate(self.tag_wires):
            if (blk.tag_value >> (len(self.tag_wires) - 1 - i)) & 1:
                bit |= 1 << (self.ambient_width - 1 - w)
        return bit

    def tagged_codes(self, index: int, side: str) -> Tuple[int, ...]:
        """The block's completed codes, moved into its own sector."""
        blk = self.branches[index]
        chart = blk.ingress if side == "ingress" else blk.egress
        bit = self.tag_bit(index)
        for c in chart.codes:
            if c & bit:
                raise ProvenanceError(
                    f"block {index}: its completed chart already occupies the "
                    f"tag wire; the tag placement is not free")
        return tuple(c | bit for c in chart.codes)

    def inclusion(self, index: int, side: str) -> Tuple[int, ...]:
        """J_i^side: the parent positions this block occupies, in order."""
        parent = self.ingress if side == "ingress" else self.egress
        pos = {c: j for j, c in enumerate(parent.codes)}
        try:
            return tuple(pos[c] for c in self.tagged_codes(index, side))
        except KeyError as e:
            raise ProvenanceError(
                f"block {index} {side}: code {e.args[0]} is not in the parent "
                f"chart, so the inclusion is not defined")

    def validate(self):
        """Orthogonality, ordered exhaustion, and the block PREREQUISITES.

        This does not evaluate W_block J^- = J^+ Vhat: no circuit is consulted
        here. What is checked is everything that equation presupposes --
        disjoint blocks, ordered exhaustion of the parent, blockwise sparse
        order, equal inclusion sizes, and one ordered factorisation shared by
        both polarities.
        """
        for side in ("ingress", "egress"):
            parent = self.ingress if side == "ingress" else self.egress
            seen, expect = set(), []
            for blk in self.branches:
                codes = self.tagged_codes(blk.index, side)
                if len(set(codes)) != len(codes):
                    raise ProvenanceError(
                        f"block {blk.index} {side}: repeats a code")
                clash = seen & set(codes)
                if clash:
                    raise ProvenanceError(
                        f"block {blk.index} {side}: overlaps an earlier block "
                        f"on {sorted(clash)[:4]}; the blocks are a DIRECT sum "
                        f"and must be orthogonal")
                seen |= set(codes)
                expect.extend(codes)
            if tuple(parent.codes) != tuple(expect):
                raise ProvenanceError(
                    f"{side}: the parent chart is not the ordered exhaustion "
                    f"of its blocks")
            # sparse order is preserved blockwise
            for blk in self.branches:
                js = self.inclusion(blk.index, side)
                if list(js) != sorted(js):
                    raise ProvenanceError(
                        f"block {blk.index} {side}: its codes do not appear "
                        f"in the parent in their own order")
        # STRUCTURAL PREREQUISITES for W_block J_i^- = J_i^+ Vhat_i, not that
        # equation: each block must include with the same dimension on both
        # polarities and carry the same ordered factor list. The operator
        # equation itself compares a circuit against Vhat and is an EMISSION
        # gate; nothing here evaluates a unitary.
        for blk in self.branches:
            if len(self.inclusion(blk.index, "ingress")) != \
                    len(self.inclusion(blk.index, "egress")):
                raise ProvenanceError(
                    f"block {blk.index}: the two inclusions have different "
                    f"sizes, so W_block J^- = J^+ Vhat cannot hold")
            fi = blk.ingress.route.parts if blk.ingress.route else ()
            fe = blk.egress.route.parts if blk.egress.route else ()
            # ROLE, TYPE, OWNER and dimension, in order. Codes and placements
            # legitimately differ between the two polarities -- that is what
            # keeping them independent means -- so they are NOT compared.
            def _sig(fs):
                return [(f.role, f.logical, f.owner, f.dim) for f in fs]
            if _sig(fi) != _sig(fe):
                raise ProvenanceError(
                    f"block {blk.index}: Vhat's ordered factors differ "
                    f"between polarities:\n  ingress {_sig(fi)}\n  egress "
                    f"{_sig(fe)}")
        if self.ingress.dim != self.egress.dim:
            raise ProvenanceError(
                f"parent ingress {self.ingress.dim} != egress "
                f"{self.egress.dim}")
        if set(self.support) & set(self.spectators):
            raise ProvenanceError("a wire is both support and spectator")
        return True


def _lift_chart(chart, local_to_ambient, ambient_width, label, port=None):
    """A branch-local scatter chart placed into the occurrence's register.

    `port` is the branch projection's own recorded port, when the caller
    holds one: a ROUTE-LESS lift then TRANSPORTS that existing occurrence
    instead of minting a fresh unlinked one -- a lift re-presents what the
    branch already displays, and must never infer or mint a replacement
    root for it.
    """
    r = chart.route
    if r is None:
        # A branch whose root defaulted to its Frame is ONE factor on its own
        # local wires, in order. That is a recorded description, not a guess:
        # the chart's codes and width are the factor, and the occurrence's
        # local-to-ambient map is where it sits.
        if chart.n_qubits > len(local_to_ambient):
            raise ProvenanceError(
                f"{label}: the branch root spans {chart.n_qubits} wires but "
                f"the occurrence records a {len(local_to_ambient)}-wire "
                f"local-to-ambient map")
        src = (FactorSource((port,)) if port is not None
               else FactorSource((SourcePortRef(
                   ref=f"lift:{label}", origin_cut=label,
                   path=("lift",)),)))
        one = ChartFactor(factor_id=f"lift:{label}", source=src,
                          name=chart.label or "u", owner=None,
                          n_qubits=chart.n_qubits, codes=tuple(chart.codes))
        rep, places = scatter_repart(
            (tuple(local_to_ambient[:chart.n_qubits]),), ambient_width)
        out = par_then_repart((one,), rep, ambient_width, label,
                              placements=places, kind="scatter")
        out.validate_joint()
        return out
    if isinstance(r, JoinRoute):
        # A RELATIONAL branch root lifts as the relation it is: every row
        # and source pair kept, coordinates mapped through the occurrence's
        # own recorded local-to-ambient map.
        for pl in r.placements:
            for w in pl:
                if w >= len(local_to_ambient):
                    raise ProvenanceError(
                        f"{label}: branch wire {w} is outside the recorded "
                        f"local-to-ambient map of {len(local_to_ambient)} "
                        f"wires")
        wm = {w: local_to_ambient[w] for pl in r.placements for w in pl}
        for w in r.support:
            if w >= len(local_to_ambient):
                raise ProvenanceError(
                    f"{label}: support wire {w} is outside the recorded "
                    f"local-to-ambient map")
            wm.setdefault(w, local_to_ambient[w])
        moved = r.moved(wm, ambient_width, label=label)
        out = BoundaryChart(n_qubits=ambient_width,
                            codes=tuple(moved.codes), route=moved,
                            label=label, space="ambient",
                            support_wires=tuple(moved.support))
        out.validate_joint()
        return out
    if not r.reconstructible:
        raise ProvenanceError(
            f"{label}: the branch root records a {r.kind!r} Repart, so it "
            f"cannot be placed in the occurrence register")
    r.check_schedule()
    places = []
    for g in r.placements:
        out = []
        for w in g:
            if w >= len(local_to_ambient):
                raise ProvenanceError(
                    f"{label}: branch wire {w} is outside the recorded "
                    f"local-to-ambient map of {len(local_to_ambient)} wires")
            out.append(local_to_ambient[w])
        places.append(tuple(out))
    rep, places = scatter_repart(places, ambient_width)
    out = par_then_repart(r.parts, rep, ambient_width, label,
                          placements=places, kind="scatter")
    out.validate_joint()
    return out


@dataclass(frozen=True, slots=True)
class UseBlockLayout:
    """Where an open occurrence's Block sits inside the CONTAINING register.

    `ambient_width` is the occurrence's real register -- what the compiler
    actually allocated -- and `block_width` is only how much of it the Block
    spans. Deriving the register as "max parent frame width + owned width"
    gives the second number and calls it the first, which then makes every
    chart code wrong by the difference.
    """
    ambient_width: int
    owned_wires: Tuple[int, ...]
    tag_wires: Tuple[int, ...]
    workspace_wires: Tuple[int, ...]

    @property
    def block_to_ambient(self) -> Tuple[int, ...]:
        return tuple(self.tag_wires) + tuple(self.workspace_wires) \
            + tuple(self.owned_wires)

    @property
    def block_width(self) -> int:
        return len(self.block_to_ambient)

    @property
    def support(self) -> Tuple[int, ...]:
        return tuple(sorted(self.block_to_ambient))

    @property
    def spectators(self) -> Tuple[int, ...]:
        used = set(self.block_to_ambient)
        return tuple(w for w in range(self.ambient_width) if w not in used)


def use_block_layout(bindings, main_width, tag_width, ambient_width):
    """Select the Block's coordinates AROUND the owned context.

    Owned wires are preserved exactly as the bindings record them; the tag
    then the workspace take the remaining coordinates in ascending order.
    Everything left over is a true spectator of this occurrence.
    """
    owned = []
    for b in bindings:
        for w in b.wires:
            if not (0 <= w < ambient_width):
                raise ProvenanceError(
                    f"binding {b.name!r} sits on wire {w}, outside a register "
                    f"of {ambient_width}")
            if w in owned:
                raise ProvenanceError(f"wire {w} is owned by two bindings")
            owned.append(w)
    free = [w for w in range(ambient_width) if w not in set(owned)]
    if len(free) < main_width:
        raise ProvenanceError(
            f"use-block: {main_width} coordinates are needed for tag and "
            f"workspace but only {len(free)} are unowned in {ambient_width}")
    chosen = tuple(free[:main_width])
    return UseBlockLayout(ambient_width=ambient_width,
                          owned_wires=tuple(owned),
                          tag_wires=chosen[:tag_width],
                          workspace_wires=chosen[tag_width:])


def complete_projection(bp, *, local_to_ambient, ambient_width, inactive,
                        completed_chart, where=""):
    """The completed branch's row projection, at ONE polarity.

    The branch's own BranchMainProjection is consumed UNCHANGED: the main
    alphabet, its order and every row's label are the branch's own. The
    schedule is TRANSPORTED through the recorded local-to-ambient map, and
    each inactive resource is appended exactly once -- to the FIBRE only.
    Labels extend by the recorded product schedule (branch rows major, the
    inactive codes minor, in appended order); nothing here reads a row image
    to decide anything, and `check_rows` then re-derives every completed row
    from the transported schedule independently.
    """
    p = bp.projection
    l2a = tuple(local_to_ambient)

    def _amb(w):
        if w >= len(l2a):
            raise ProvenanceError(
                f"{where}projection coordinate {w} is outside the recorded "
                f"{len(l2a)}-wire local-to-ambient map")
        return l2a[w]

    lab_w = tuple(_amb(w) for w in p.label_wires)
    fib_w = tuple(_amb(w) for w in p.fibre_wires)
    pad = tuple((_amb(w), b) for w, b in p.padding)
    m = 1
    for b in inactive:
        fib_w = fib_w + tuple(b.wires)
        m *= len(b.codes)
    rows = tuple(completed_chart.codes)
    nb = len(p.labels)
    if len(rows) != nb * m:
        raise ProvenanceError(
            f"{where}the completed chart has {len(rows)} rows, not the "
            f"{nb} branch rows times the {m} inactive assignments; an "
            f"inactive resource was dropped or duplicated")
    labels = tuple(p.labels[k] for k in range(nb) for _ in range(m))
    keys = tuple(gather_code(r, fib_w, completed_chart.n_qubits)
                 for r in rows)
    out = RowProjection(
        port=p.port, polarity=p.polarity, alphabet=tuple(p.alphabet),
        labels=labels, fibre_keys=keys, presenters=tuple(p.presenters),
        support=tuple(sorted(set(lab_w) | set(fib_w))),
        rows=rows, padding=pad, label_wires=lab_w, fibre_wires=fib_w,
        row_width=completed_chart.n_qubits)
    out.check_rows(completed_chart, where)
    return out


def complete_branch(*, index, artifact, uses, inactive, local_to_ambient,
                    tag_value, ambient_width, label="", used_bindings=(),
                    binding_transport=(), projections=None):
    """Complete ONE alternative against the resources it does not use.

    Both polarities are built independently from the branch's own selected
    root -- never from its Frame, and never by recompiling it. When the
    preparation issued per-polarity BranchMainProjections, they are consumed
    unchanged: the completed projection keeps the branch's main alphabet and
    labels and appends each inactive resource exactly once to the fibre.
    """
    sb = artifact.selected_boundary
    if sb is None:
        raise ProvenanceError(
            f"branch {index}: no selected boundary was prepared, so it "
            f"cannot be completed")
    uses = tuple(uses)
    inactive = tuple(inactive)
    # One owner contributes exactly once however often it is named; two
    # distinct owners of the same type are two resources. Deduplicated ONCE,
    # so the chart and the completed projection see the same list.
    _uniq, _seen_owners = [], set()
    for b in inactive:
        if b.owner_id in _seen_owners:
            continue
        _seen_owners.add(b.owner_id)
        _uniq.append(b)

    def side(which):
        chart = sb.ingress if which == "ingress" else sb.egress
        bp = projections.get(which) if projections else None
        if bp is not None and bp.polarity != which:
            raise ProvenanceError(
                f"branch {index}: the {which} completion was handed the "
                f"{bp.polarity} projection; the two polarities are completed "
                f"independently and must not be swapped")
        base = _lift_chart(chart, local_to_ambient, ambient_width,
                           f"{label or 'branch'}{index}^{which}",
                           port=(bp.projection.port if bp is not None
                                 else None))
        parts = list(base.route.parts)
        places = list(base.route.placements)
        for b in _uniq:
            # The inactive resource is carried as the binding RECORDED it --
            # its own ordered codes, never all 2^k assignments to its wires.
            parts.append(ChartFactor(
                factor_id=f"inactive:{b.owner_id}",
                # The inactive resource IS the captured binding's occurrence,
                # so its link is that binding's own owner -- the identity the
                # adapter's role context records as fibre. Same rule as a
                # routed binding's carrier factor.
                source=FactorSource((SourcePortRef(
                    ref=b.owner_id, origin_cut=b.intro_cut,
                    path=("inactive", b.name), root=b.owner_id),)),
                name=f"Y_{b.name}", owner=b.owner_id, n_qubits=len(b.wires),
                codes=tuple(b.codes),
                role="residual", logical=b.logical))
            places.append(tuple(b.wires))
        rep, pl = scatter_repart(places, ambient_width)
        ch = par_then_repart(tuple(parts), rep, ambient_width,
                             f"{label or 'branch'}{index}^{which}",
                             placements=pl, kind="scatter")
        ch.validate_joint()
        proj = None
        if bp is not None:
            proj = complete_projection(
                bp, local_to_ambient=local_to_ambient,
                ambient_width=ambient_width, inactive=tuple(_uniq),
                completed_chart=ch,
                where=f"branch {index} {which} completion: ")
        return ch, proj

    ch_in, proj_in = side("ingress")
    ch_out, proj_out = side("egress")
    return CompletedBranch(index=index, artifact=artifact, uses=uses,
                           inactive=inactive, tag_value=tag_value,
                           ingress=ch_in, egress=ch_out,
                           local_to_ambient=tuple(local_to_ambient),
                           used_bindings=tuple(used_bindings),
                           binding_transport=tuple(binding_transport),
                           ingress_projection=proj_in,
                           egress_projection=proj_out)


def plan_use_block(completed, layout, label="block"):
    """Block: the TAGGED direct sum of the completed alternatives.

    Each block is tagged into its own sector, so the parent dimension is the
    SUM of the completed block dimensions -- 64 (+) 16 = 80 -- and never the
    sum of the raw branch dimensions times a uniform context factor.
    """
    completed = tuple(completed)
    if not completed:
        raise ProvenanceError(f"{label}: no completed branches")
    ambient_width = layout.ambient_width
    tag_wires = tuple(layout.tag_wires)

    idx = {blk.index: blk for blk in completed}
    if sorted(idx) != [blk.index for blk in completed]:
        raise ProvenanceError(f"{label}: block indices are not ordered")

    def _bit(blk):
        bit = 0
        for i, w in enumerate(tag_wires):
            if (blk.tag_value >> (len(tag_wires) - 1 - i)) & 1:
                bit |= 1 << (ambient_width - 1 - w)
        return bit

    def tagged(which):
        codes = []
        for blk in completed:
            chart = blk.ingress if which == "ingress" else blk.egress
            bit = _bit(blk)
            for c in chart.codes:
                if c & bit:
                    raise ProvenanceError(
                        f"{label}: block {blk.index} already occupies its "
                        f"tag wire; the tag placement is not free")
                codes.append(c | bit)
        if len(set(codes)) != len(codes):
            raise ProvenanceError(
                f"{label} {which}: the tagged blocks are not disjoint")
        # The Block's support is the layout's, not the register's: the
        # spectators it declares are genuinely outside the chart.
        return BoundaryChart(n_qubits=ambient_width, codes=tuple(codes),
                             route=None, label=f"{label}^{which}",
                             space="ambient",
                             support_wires=tuple(layout.support))

    ing, egr = tagged("ingress"), tagged("egress")
    plan = OpenUseBlockPlan(branches=tuple(completed),
                            ambient_width=ambient_width,
                            block_width=layout.block_width,
                            tag_wires=tag_wires,
                            workspace_wires=tuple(layout.workspace_wires),
                            block_to_ambient=layout.block_to_ambient,
                            ingress=ing, egress=egr,
                            support=layout.support,
                            spectators=layout.spectators)
    plan.validate()
    return plan


def scatter_code(code, wires, ambient_width):
    """One local code placed on `wires` of an `ambient_width` register.

    Big-endian in both spaces: bit i of the local code (counting from the
    most significant of `len(wires)`) lands on `wires[i]`.
    """
    v = 0
    k = len(wires)
    for i, w in enumerate(wires):
        if not (0 <= w < ambient_width):
            raise ProvenanceError(
                f"wire {w} is outside a register of {ambient_width}")
        if (code >> (k - 1 - i)) & 1:
            v |= 1 << (ambient_width - 1 - w)
    return v


def completed_embedding(frame, bindings):
    """The frame's MAIN codes completed by each distinct binding, IN ORDER.

    Main outermost, then one factor per distinct owner in `bindings` order --
    the same nesting `complete_branch` uses when it appends the resources a
    branch does not touch after that branch's own factors. Each binding
    contributes its own RECORDED ordered codes on its own recorded wires;
    nothing here densifies a sparse resource to 2^len(wires).

    This is the ORDERED counterpart of `completed_dimension`: that one answers
    "how many states", this one answers "which states, in which order", which
    is what a Block chart has to be compared against. A frame claiming
    dimension 8 and a boundary describing a different eight states is exactly
    the disagreement `classify_factorization` exists to name.
    """
    n = frame.n_qubits
    out = list(frame.codes)
    seen = set()
    for b in bindings:
        if b.owner_id in seen:
            continue
        seen.add(b.owner_id)
        factor = tuple(scatter_code(c, b.wires, n) for c in b.codes)
        out = [m | c for m in out for c in factor]
    if len(set(out)) != len(out):
        raise ProvenanceError(
            "the completed embedding repeats a code: the main placement and "
            "an owned resource are claiming the same coordinate")
    return tuple(out)


# How a parent Frame stands to the Block that is its occurrence's complete cut.
#
# The Block is ALWAYS the authority. These say whether a Frame is additionally
# able to present that same cut as a product of a main interface and
# unconditional context ports -- which is a strictly weaker vocabulary, and one
# that simply cannot express a branch that CONSUMES a resource rather than
# carrying it alongside.
FACTORIZED = "FACTORIZED"
BLOCK_ONLY = "BLOCK_ONLY"


@dataclass(frozen=True, slots=True)
class FactorizationCertificate:
    """One polarity's recorded verdict, issued where both structures are built.

    BLOCK_ONLY is a POSITIVE finding, not a missing result: it records that
    both the Frame and the Block were built and individually validated, and
    that no uniform product factorization of the Block exists. Every resource
    the Frame therefore cannot present is named here and stays fully typed and
    provenance-bearing in the CompletedBranch/OpenUseBlockPlan records.
    Malformed provenance is a different thing entirely and raises before any
    verdict is reached.
    """
    side: str
    status: str
    ambient_width: int
    frame_dim: int                             # the MAIN interface alone
    block_dim: int                             # the complete cut
    main_codes: Tuple[int, ...]
    main_wires: Tuple[int, ...]
    # (owner_id, name) of every owned resource, split by whether the Frame is
    # able to present it as an unconditional context port.
    factors: Tuple[Tuple[str, str], ...] = ()
    omitted: Tuple[Tuple[str, str], ...] = ()
    reason: str = ""

    def __post_init__(self):
        if self.side not in ("ingress", "egress"):
            raise ProvenanceError(
                f"factorization certificate: side {self.side!r} is neither "
                f"ingress nor egress")
        if self.status not in (FACTORIZED, BLOCK_ONLY):
            raise ProvenanceError(
                f"factorization certificate: unknown status {self.status!r}")
        if self.status == FACTORIZED:
            if self.omitted:
                raise ProvenanceError(
                    f"{self.side}: a FACTORIZED frame presents every owned "
                    f"resource, but {self.omitted} are recorded as omitted")
            if not self.factors:
                raise ProvenanceError(
                    f"{self.side}: FACTORIZED records no factors, so it "
                    f"claims a factorization of nothing")
        else:
            if self.factors:
                raise ProvenanceError(
                    f"{self.side}: a BLOCK_ONLY frame presents no context "
                    f"port, but {self.factors} are recorded as presented")
            if not self.omitted:
                raise ProvenanceError(
                    f"{self.side}: BLOCK_ONLY names no omitted resource, so "
                    f"nothing explains why the Frame is not the complete cut")
            if not self.reason:
                raise ProvenanceError(
                    f"{self.side}: BLOCK_ONLY records no reason")

    @property
    def factorized(self) -> bool:
        return self.status == FACTORIZED


def check_context_ports(ports, bindings, cut_id, main_wires, ambient_width,
                        where=""):
    """Every candidate context port, against the binding it claims to present.

    Runs BEFORE any factorization verdict. What it refuses -- a port that
    misreports its type, its placement, its owner or its lineage, a port that
    collides with the main interface or with another resource, a sector-
    conditioned context -- is malformed provenance, and malformed provenance
    must never be laundered into "well, then it is BLOCK_ONLY".
    """
    check_binding_consistency(bindings, where)
    by_owner = {b.owner_id: b for b in bindings}
    if len(ports) != len(by_owner):
        raise ProvenanceError(
            f"{where}{len(ports)} candidate context port(s) for "
            f"{len(by_owner)} distinct owned resource(s)")
    seen_owner, seen_wire = set(), set(main_wires)
    if len(set(main_wires)) != len(main_wires):
        raise ProvenanceError(
            f"{where}the main placement {main_wires} is not injective")
    for w in main_wires:
        if not (0 <= w < ambient_width):
            raise ProvenanceError(
                f"{where}the main placement names wire {w}, outside a "
                f"{ambient_width}-wire register")
    for p in ports:
        b = by_owner.get(p.owner_id)
        if b is None:
            raise ProvenanceError(
                f"{where}context port {p.name!r} claims owner "
                f"{p.owner_id!r}, which no recorded binding holds")
        if p.owner_id in seen_owner:
            raise ProvenanceError(
                f"{where}owner {p.owner_id} is presented by two ports")
        seen_owner.add(p.owner_id)
        if p.role != "context":
            raise ProvenanceError(
                f"{where}port {p.name!r} presents an owned resource with "
                f"role {p.role!r}, not 'context'")
        if p.by_sector:
            raise ProvenanceError(
                f"{where}context port {p.name!r} is sector-conditioned "
                f"{p.by_sector}; an outer context is carried once, "
                f"unconditionally")
        if p.logical != b.logical:
            raise ProvenanceError(
                f"{where}context port {p.name!r} is typed "
                f"{pretty(p.logical)} but its binding records "
                f"{pretty(b.logical)}")
        if tuple(p.wires) != tuple(b.wires):
            raise ProvenanceError(
                f"{where}context port {p.name!r} sits on {tuple(p.wires)} but "
                f"its binding records {tuple(b.wires)}")
        if p.cut_id != cut_id:
            raise ProvenanceError(
                f"{where}context port {p.name!r} is cut at {p.cut_id!r}, not "
                f"at this occurrence's cut {cut_id!r}")
        if p.origin_cut != b.intro_cut:
            raise ProvenanceError(
                f"{where}context port {p.name!r} records origin "
                f"{p.origin_cut!r} but the resource was introduced at "
                f"{b.intro_cut!r}; lineage cannot be reconstructed")
        for w in p.wires:
            if not (0 <= w < ambient_width):
                raise ProvenanceError(
                    f"{where}context port {p.name!r} names wire {w}, outside "
                    f"a {ambient_width}-wire register")
            if w in seen_wire:
                raise ProvenanceError(
                    f"{where}context port {p.name!r} claims wire {w}, which "
                    f"the main placement or another resource already holds")
            seen_wire.add(w)
    return True


def check_block_resource_identity(plan, bindings, parameter_owners=(),
                                  where=""):
    """The Block's resources ARE the parent's resources -- by identity.

    The ordered-code agreement `classify_factorization` decides is about the
    BASIS. It is satisfied by any chart with the right shape, including one
    whose factors belong to freshly minted owners, because a flattened chart
    carries no identities. This is the companion gate: it looks inside the
    blocks and requires every owned resource to be the parent's own.

    For a resource a branch CARRIES, the proof is the factor: same owner,
    same type, same ordered codes, on the parent's own wires after the
    branch-local placement transports. For a resource a branch CONSUMES there
    is no factor to point at, and the proof is the recorded handoff, which was
    issued where the resource was handed down. Neither is a name match, a
    dimension match or a wire match.

    The live summand parameter is a DIFFERENT resource from any of them and
    must not share an owner with one.
    """
    by_owner = {b.owner_id: b for b in bindings}
    params = set(parameter_owners)
    clash = params & set(by_owner)
    if clash:
        raise ProvenanceError(
            f"{where}the live summand parameter and an owned resource share "
            f"owner {sorted(clash)}; the payload a branch is GIVEN is not the "
            f"context it uses")
    for blk in plan.branches:
        at = f"{where}block {blk.index}: "
        tr = {t.owner_id: t for t in blk.binding_transport}
        if set(tr) != set(blk.uses):
            raise ProvenanceError(
                f"{at}handoffs recorded for {sorted(tr)} but the branch uses "
                f"{sorted(set(blk.uses))}; a used resource with no recorded "
                f"handoff is not proved to be the parent's")
        for oid, t in tr.items():
            b = by_owner.get(oid)
            if b is None:
                raise ProvenanceError(
                    f"{at}handoff names owner {oid}, which this occurrence "
                    f"does not own")
            if (t.intro_cut != b.intro_cut or t.logical != b.logical
                    or tuple(t.codes) != tuple(b.codes)
                    or tuple(t.ambient_wires) != tuple(b.wires)):
                raise ProvenanceError(
                    f"{at}the handoff of {b.name!r} disagrees with the parent "
                    f"binding on its lineage, type, encoding or placement")
            t.check_transport(blk.local_to_ambient, at)
        for side in ("ingress", "egress"):
            chart = blk.ingress if side == "ingress" else blk.egress
            if chart.route is None:
                raise ProvenanceError(
                    f"{at}{side} carries no route, so its factors cannot be "
                    f"identified")
            seen = {}
            for f, place in zip(chart.route.parts, chart.route.placements):
                b = by_owner.get(f.owner)
                if b is None:
                    continue                 # not an owned resource
                if f.owner in seen:
                    raise ProvenanceError(
                        f"{at}{side}: owner {f.owner} appears as two factors; "
                        f"one resource is one factor")
                seen[f.owner] = f
                if f.logical != b.logical:
                    raise ProvenanceError(
                        f"{at}{side}: factor {f.name!r} is typed "
                        f"{pretty(f.logical)} but {b.name!r} is "
                        f"{pretty(b.logical)}")
                if tuple(f.codes) != tuple(b.codes):
                    raise ProvenanceError(
                        f"{at}{side}: factor {f.name!r} encodes {f.codes} but "
                        f"{b.name!r} is recorded as {tuple(b.codes)}")
                if f.n_qubits != len(b.wires):
                    raise ProvenanceError(
                        f"{at}{side}: factor {f.name!r} spans {f.n_qubits} "
                        f"wires but {b.name!r} occupies {len(b.wires)}")
                if tuple(place) != tuple(b.wires):
                    raise ProvenanceError(
                        f"{at}{side}: {b.name!r} sits on {tuple(place)} but "
                        f"the parent holds it on {tuple(b.wires)}; the "
                        f"branch-local placement does not transport onto the "
                        f"parent's")
            for x in blk.inactive:
                if x.owner_id not in seen:
                    raise ProvenanceError(
                        f"{at}{side}: {x.name!r} is carried through untouched "
                        f"but no factor of that owner appears, so it was not "
                        f"carried at all")
            # A resource a branch USES may be absent -- consumed into the
            # branch's own derivation, which is what the handoff covers. But
            # if a factor stands on exactly the coordinates this occurrence
            # RECORDED for that resource, then that factor is that resource,
            # and it had better be the parent's. This is the placement the
            # derivation wrote down, not a guess from a type, a width or a
            # name; and an overlapping factor is deliberately not enough,
            # because an Apply spine's residual legitimately covers part of
            # the argument it consumed.
            for oid, t in tr.items():
                if not t.ambient_wires:
                    continue
                for f, place in zip(chart.route.parts,
                                    chart.route.placements):
                    if tuple(place) == tuple(t.ambient_wires) \
                            and f.owner != oid:
                        raise ProvenanceError(
                            f"{at}{side}: the factor {f.name!r} stands on "
                            f"{tuple(place)}, the coordinates recorded for "
                            f"{t.name!r}, but is owned by {f.owner} rather "
                            f"than the resource handed down ({oid}); a "
                            f"branch that carries the parent's resource must "
                            f"carry the PARENT'S resource")
    return True


def classify_factorization(*, side, main_frame, ports, bindings, chart, cut_id,
                           main_wires, where=""):
    """Decide, POSITIVELY, how this polarity's Frame stands to its Block.

    Both structures are built and validated first and independently; the
    verdict is then a comparison of two exact embeddings, never the result of
    catching an error. Equal dimension decides nothing here: the ambient
    width, the exact ordered codes and every port's type, role, placement,
    owner and lineage all have to agree, because a Frame that completes to the
    right NUMBER of states in the wrong ORDER would have every consumer
    composing against the wrong basis.

    Returns `(certificate, ports_to_attach)`. A BLOCK_ONLY frame attaches
    none, and its Block keeps every resource, typed and identified.
    """
    check_context_ports(ports, bindings, cut_id, main_wires,
                        chart.n_qubits, where)
    if main_frame.n_qubits != chart.n_qubits:
        raise ProvenanceError(
            f"{where}the main frame is over {main_frame.n_qubits} wires but "
            f"the Block chart is over {chart.n_qubits}")
    if tuple(main_frame.codes) != tuple(
            scatter_code(c, main_wires, chart.n_qubits)
            for c in canonical_frame(main_frame.logical).codes):
        raise ProvenanceError(
            f"{where}the main frame's codes are not its logical interface "
            f"placed on the recorded main coordinates {main_wires}")
    named = tuple((b.owner_id, b.name) for b in bindings)
    got = completed_embedding(main_frame, bindings)
    want = tuple(chart.codes)
    common = dict(side=side, ambient_width=chart.n_qubits,
                  frame_dim=main_frame.dim, block_dim=len(want),
                  main_codes=tuple(main_frame.codes),
                  main_wires=tuple(main_wires))
    if got == want:
        return (FactorizationCertificate(status=FACTORIZED, factors=named,
                                         **common),
                tuple(ports))
    if len(got) == len(want):
        reason = (f"the Frame completes to the same {len(want)} states in a "
                  f"different order: {got[:6]}... against {want[:6]}...")
    else:
        reason = (f"the Frame completes to {len(got)} states and the Block "
                  f"has {len(want)}: a branch that CONSUMES an owned resource "
                  f"does not carry it as a uniform product factor")
    return (FactorizationCertificate(status=BLOCK_ONLY, omitted=named,
                                     reason=reason, **common),
            ())
