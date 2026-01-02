# developer.md — Logical vs Physical Wires in GateAtom (Phase 4A Decision Record)

**Status:** Adopted  
**Applies to:** Phase 4A and all subsequent phases  
**Last updated:** 2025‑12‑31

---

## Purpose of this Document

This document records and justifies a **design decision** made during Phase 4A
implementation:  
**Gate atoms must be logically addressed; physicalization is a backend concern.**

This decision is critical for:
- enabling Phase 4A extraction completeness,
- preserving Phase 0–3 invariants,
- and avoiding architectural debt that would block Phase 4B (ZX) and Phase 4C (Lie / exponentials).

This is a **forward‑looking record** and should be treated as normative guidance
for future contributors.

---

## The Problem Observed

### Current Phase 3 behavior (prior to Phase 4A)

Gate atoms were defined as:

```python
@dataclass(frozen=True, slots=True)
class GateAtom:
    gate_name: str
    wires: Tuple[int, ...]  # physical wire indices
```

And emitted as:

```python
phys_wires = tuple(p.apply_new_to_old(g) for g in global_wires)
atoms.append(GateAtom(gate_name, phys_wires))
```

This **bakes in the current permutation** at emission time.

### Why this blocks Phase 4A

Phase 4A requires reasoning of the form:

> “This gate does not touch loop wires **modulo routing**.”

That reasoning requires:
- reindexing gate support under permutations,
- commuting routing past gates,
- certifying disjointness in *some* routing frame.

Once physical indices are baked into atoms:
- the logical frame is lost,
- gate support cannot be safely reindexed,
- cached physical wires become stale under rewrites,
- and extraction completeness is artificially capped.

---

## Decision (Recorded)

### ✅ GateAtom wires are **logical**, not physical

Effective immediately:

```python
@dataclass(frozen=True, slots=True)
class GateAtom:
    """Opaque gate atom with logical wire indices."""
    gate_name: str
    wires: Tuple[int, ...]  # logical (pre‑routing) indices

    def support(self) -> Set[int]:
        return set(self.wires)
```

The field name `wires` is retained to minimize disruption, but its **meaning is now logical**.

---

## Consequences of This Decision

### 1. emit_atom no longer applies permutations

Old behavior (removed):

```python
phys_wires = tuple(p.apply_new_to_old(g) for g in global_wires)
atoms.append(GateAtom(gate_name, phys_wires))
```

New behavior:

```python
atoms.append(GateAtom(gate_name, tuple(global_wires)))
```

### 2. Physicalization is deferred to the backend

A single, explicit physicalization step occurs **only** when lowering to pytket:

```python
def physicalize(atom: GateAtom, p: WirePerm) -> Tuple[int, ...]:
    return tuple(p.apply_new_to_old(w) for w in atom.wires)
```

No other phase should use physical wires.

---

## Invariants Preserved

This change **does not weaken** any locked invariant:

- Phase 0–3 observable behavior remains identical.
- `materialize=False` still emits zero SWAPs.
- Residual GOI artifacts are preserved verbatim (now in logical form).
- Determinism improves: residual equality now compares logical structure, not incidental physical layout.

---

## Why We Explicitly Rejected “Store Both Logical and Physical”

An alternative considered was:

```python
GateAtom(
    logical_wires=...,
    physical_wires=...
)
```

This was rejected because:

- Phase 4A rewrites **reindex logical support**.
- Cached physical wires become stale unless updated everywhere.
- Cache invalidation couples extraction logic to backend concerns.
- This would make later Option‑3 cleanup *harder*, not easier.

If a frame is carried, physical wires should be **derived**, not cached.

---

## Impact on Phase 4A Extraction

With this decision:

- Gate support is always in a logical frame.
- Loop‑wire disjointness checks become trivial and sound.
- Routing commutation updates only logical indices.
- Externalization witnesses remain purely structural.
- The Phase 3 firewall (“do not inspect gate internals”) remains intact.

---

## Impact on Future Phases

### Phase 4B (ZX post‑pass)
- ZX translation expects logical connectivity.
- Late physicalization aligns perfectly with diagrammatic rewriting.

### Phase 4C (Lie / exponentials)
- Analytic atoms remain opaque.
- Logical support + routing separation preserves soundness.

### Eventual Option 3 (Full backend physicalization)
- This decision *is* Option‑3‑shaped.
- Migrating later becomes a cleanup, not a redesign.

---

## Rules for Contributors (Normative)

1. **GateAtom.wires are logical.**
2. **No phase except the backend may compute physical wires.**
3. **Extraction, normalization, and GOI reasoning must use logical indices only.**
4. **Do not introduce cached physical wires in atoms.**
5. **Routing/permutation objects define the physical frame.**

Violating these rules will break extraction completeness or future extensibility.

---

## Summary

This decision is the minimal change that:
- unlocks Phase 4A,
- preserves all Phase 0–3 guarantees,
- and prevents long‑term architectural debt.

It should be treated as a **stable design commitment** going forward.
