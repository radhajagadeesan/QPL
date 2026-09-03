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
from dataclasses import dataclass, field, replace
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


class NeedsBranchPreparation(ProvenanceError):
    """The occurrence cannot be planned until its branches are prepared.

    Raised when the completed cuts do not balance because the branch egress
    cuts are not available yet -- a resource contained inside an ingress
    summand has to be reclassified as a typed residual at egress, and only the
    prepared branch artifact can say which one.

    This is NOT a placement. An unbalanced plan must never be attachable or
    consumable, so this is an exception rather than a partially filled
    OccurrencePlacement.

    `missing_factor` is the numeric gap ONLY. The resource behind it must come
    from the derivation-selected branch egress cut, never be synthesized from
    the factor.
    """

    def __init__(self, ingress: int, egress: int):
        self.ingress = ingress
        self.egress = egress
        self.missing_factor = (ingress // egress if egress and
                               ingress % egress == 0 else None)
        super().__init__(
            f"completed cuts do not balance: ingress {ingress} versus egress "
            f"{egress}"
            + (f" (missing egress factor {self.missing_factor})"
               if self.missing_factor else "")
            + "; the branch egress cuts are not prepared, so no placement "
              "can be produced")


def completion_factor(port: "Port") -> int:
    """How much a live port multiplies the completed dimension.

    A true Unit spectator contributes 1. Anything else contributes its own
    semantic dimension -- f : Q-oQ contributes 4, EndoOp contributes 16.
    """
    if isinstance(port.logical, Unit):
        return 1
    return semantic_dim(port.logical)


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

    def __post_init__(self):
        from lang.types import width as _w
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
    uses: Tuple[str, ...] = ()       # binding names this branch actually uses

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

def _lift_branch_residuals(branches, chosen, parent_cut):
    """Live typed residual ports recorded by the prepared branch artifacts.

    Lifted through the recorded local-to-occurrence injection and RE-CUT onto
    the parent egress side: a branch-local cut_id is not automatically the
    parent egress cut. Ownership is carried over unchanged -- transport must
    not mint a new owner.

    Two branches' residuals are merged only when their recorded owner_id
    agrees. Equal name, type, dimension or wire is NOT proof of sameness.
    """
    out = {}
    for bi in branches or ():
        for pt in bi.fout.ports:
            if isinstance(pt.logical, Unit):
                continue                     # a true spectator, not a resource
            if pt.owner_id is None:
                raise ProvenanceError(
                    f"branch {bi.index} egress port {pt.name!r} of type "
                    f"{pretty(pt.logical)} carries no owner_id; a live "
                    f"residual cannot be placed without recorded ownership")
            lifted = tuple(chosen[w] if w < len(chosen) else w
                           for w in pt.wires)
            origin = pt.require_origin(f"branch {bi.index} egress port")
            key = (pt.owner_id, origin)
            if key in out:
                prev = out[key]
                # Owner AND origin already agree. Type, role and placement
                # must too -- equal dimension, name or wires are never proof.
                if (prev.logical != pt.logical or prev.role != "residual"
                        or prev.wires != lifted):
                    raise ProvenanceError(
                        f"owner {pt.owner_id} at origin {origin} appears as "
                        f"two different residuals "
                        f"({pretty(prev.logical)}@{prev.wires} versus "
                        f"{pretty(pt.logical)}@{lifted}); the derivation does "
                        f"not identify them")
                continue
            out[key] = Port(pt.name, pt.logical, lifted, role="residual",
                            by_sector=(), owner_id=pt.owner_id,
                            cut_id=parent_cut, origin_cut=origin)
    return tuple(out.values())


def plan_open_occurrence(*, parent_in, parent_out, branches, bindings,
                         ambient_width, scope, tag_width_in, tag_width_out,
                         perm=None):
    """Select an occurrence placement around externally owned context.

    PURE: no circuit, no emitter state, no mutation. One algorithm and one
    policy for open PlusMap and open NPlusMap alike -- the two differ only in
    how their caller collects sectors and branch artifacts, which is why B and
    D are one bug rather than two.

    Policy, in order:
      * externally owned context coordinates are PRESERVED exactly as the
        binding records them -- the occurrence moves, the resource does not;
      * tag then payload take the remaining coordinates in ascending order,
        deterministically;
      * each binding becomes ONE unconditional context port per side -- carried
        through inactive sectors, never copied per sector and never counted as
        a summand label.

    Ownership and occupancy come from the recorded bindings. Nothing consults
    `type_of`, a free-variable width scan, a name, or basis-bit geometry;
    `width(binding.logical)` is used only to VALIDATE a recorded binding, which
    TypedBinding already did.
    """
    owned = []
    for b in bindings:
        for w in b.wires:
            if not (0 <= w < ambient_width):
                raise ProvenanceError(
                    f"binding {b.name!r} sits on wire {w}, outside an ambient "
                    f"register of {ambient_width}")
            if w in owned:
                raise ProvenanceError(
                    f"wire {w} is owned by two bindings")
            owned.append(w)
    owned_set = set(owned)
    free = [w for w in range(ambient_width) if w not in owned_set]

    def _side(parent, k, is_in):
        cut = scope.cut()
        need = parent.n_qubits
        if len(free) < need:
            raise ProvenanceError(
                f"{'ingress' if is_in else 'egress'}: {need} coordinates are "
                f"needed for tag+payload but only {len(free)} are unowned in "
                f"an ambient register of {ambient_width}")
        chosen = tuple(free[:need])
        tag = chosen[:k]
        payload = chosen[k:]
        ports = tuple(
            Port(b.name, b.logical, tuple(b.wires), role="context",
                 owner_id=b.owner_id, cut_id=cut)
            for b in bindings)
        if not is_in:
            # Egress additionally carries whatever the PREPARED branches
            # actually classified as live residual result ports. Nothing is
            # synthesized here: if a branch recorded none, none appears, and
            # the completed cuts will refuse to balance.
            ports = ports + tuple(_lift_branch_residuals(branches, chosen, cut))
        return SidePlacement(
            cut_id=cut, ambient_width=ambient_width,
            local_to_ambient=chosen, tag_wires=tag, payload_wires=payload,
            ports=ports)

    ingress = _side(parent_in, tag_width_in, True)
    egress = _side(parent_out, tag_width_out, False)
    place = OccurrencePlacement(ingress=ingress, egress=egress,
                                pending_perm=tuple(perm or ()))

    ci = ingress.completed_dimension(parent_in.dim)
    co = egress.completed_dimension(parent_out.dim)
    if ci != co:
        # Explicitly incomplete, not a degraded plan.
        raise NeedsBranchPreparation(ci, co)
    return place
