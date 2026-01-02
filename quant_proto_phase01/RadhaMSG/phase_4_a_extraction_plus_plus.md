# Phase 4A — Extraction++ Design Document

## Status Context
Phases 0–3 are complete and test-locked. Their observable behavior is the specification. Phase 4A strictly **increases extraction completeness** without weakening soundness or modifying any Phase 0–3 outcomes.

This document specifies **Extraction++ (Phase 4A)** in the same architectural style as Phase 3: explicit invariants, algorithmic checks, and determinism-first design.

---

## Mission Statement
Implement:

```
try_extract_v2(goi: GOIArtifact) -> ExtractResult
```

such that:

- It succeeds on a **strict superset** of Phase 3 extractable cases.
- It never extracts incorrectly.
- It preserves residual GOI artifacts when extraction is not provably safe.
- All Phase 0–3 golden outputs remain **bit-for-bit identical**.

---

## Non‑Goals

- No new syntax or semantics.
- No ZX or diagrammatic reasoning (reserved for Phase 4B).
- No weakening of Phase 3 normalization or firewall rules.
- No internal Lie / exponential atoms (Phase 4C).

---

## Locked Invariants (Carried Forward Verbatim)

1. **Structure vs computation**
   - Structural terms compile only to `WirePerm`.
   - Structural compilation emits no gates and no SWAPs.
   - Gates emit unitary pytket operations only.

2. **SWAP policy**
   - `compile(..., materialize=False)` → zero SWAPs.
   - SWAPs appear only via explicit materialization.
   - Residual GOI artifacts never materialize.

3. **Determinism**
   - Same AST ⇒ identical command stream + final permutation (or identical residual GOI).

4. **Distributivity**
   - `DistL` / `DistR` may typecheck but must fail loudly at compile time.

5. **GOI checkpoint invariant**
   - Whenever extraction succeeds, GOI evaluation collapses to a boundary permutation.
   - GOI routes; it does not compute.

6. **Soundness framing**
   - Extraction is sound but incomplete.
   - Failure to extract returns a residual GOI artifact, not an error.

---

## Conceptual Shift from Phase 3

Phase 3 extraction succeeds iff **no gate touches loop wires** syntactically.

Phase 4A strengthens this by allowing extraction whenever it can be **provably shown** that loop wires are untouched *modulo routing*, using only:

- wire permutation algebra,
- gate–routing conjugation,
- routing-only cut elimination,
- and strictly outer (non-atomic) rewrites.

No inspection or rewriting of gate atoms is ever permitted.

---

## New Internal Concepts

### 1. GateFootprint

For each gate atom `G`:

- `support(G)`: the set of wire indices it acts on.
- `kind(G)`: opaque gate identity (never inspected).

Used only to reason about **disjointness** from loop wires under routing.

### 2. RoutingNormalForm++

A strictly additive, outer-only normalization pass that:

- rewrites only routing structure (`WirePerm`, associativity, identity),
- never rewrites inside gate atoms,
- never introduces SWAPs,
- is deterministic and confluent on Phase 3-normal forms.

Applied **only after Phase 3 extraction fails**.

### 3. ExternalizeWitness

A structured witness showing that a feedback body factors as:

```
body ≡ P_out ; body' ; P_in
```

where:

- `P_out`, `P_in` are `WirePerm`s,
- `body'` has loop wires provably gate-free.

This witness justifies applying Phase 3 yanking after safe restructuring.

---

## Phase 4A Extraction Algorithm

### Entry Point
`try_extract_v2(goi)`

### Pipeline

1. **Phase 3 delegation**
   - Attempt `try_extract_v1(goi)`.
   - If successful, return result unchanged.

2. **Outer routing normalization**
   - Apply `RoutingNormalForm++` to residual artifact.

3. **Feedback analysis**
   - For each `Feedback(k, body)`:
     - Attempt Phase 3 yankability.
     - If that fails, run loop interaction analysis.
     - If an `ExternalizeWitness` is produced:
       - Rewrite using routing-only conjugation.
       - Reapply Phase 3 extraction locally.
     - Otherwise, preserve residual.

4. **Global extraction check**
   - If all feedback eliminated → return `(Circuit, WirePerm)`.
   - Else → return residual GOIArtifact.

---

## Soundness Argument (Sketch)

- Phase 3 behavior remains the specification.
- Phase 4A only applies routing algebra and gate-support reindexing.
- No transformation inspects or rewrites inside gate atoms.
- Extraction only occurs when loop wires are certified gate-free modulo routing.
- Therefore, successful extraction still implies:
  - GOI evaluation collapses to a boundary permutation.
  - No computation is performed by GOI routing.

---

## Determinism Requirements

- Canonical traversal order (stable node IDs).
- Fixed rule priority.
- Canonical routing normal form.
- Witness construction must be deterministic.

---

## Deliverables

- `extract_v2.py`
- `routing_nf2.py`
- `loop_analysis.py`
- New Phase 4A tests and goldens (see test plan doc).

---

## Summary

Phase 4A is a **purely additive completeness pass**:

- It extracts strictly more programs than Phase 3.
- It preserves all Phase 0–3 guarantees.
- It is rollback-safe and test-driven.

This phase should be implemented before any ZX-based or semantic extensions.

