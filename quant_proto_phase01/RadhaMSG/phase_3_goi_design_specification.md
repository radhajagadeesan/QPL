# Phase 3 Design Specification: Explicit GOI Feedback

**Role:** Senior Architecture Specification  
**Audience:** Compiler / semantics developer  
**Status:** Design-locked (subject only to additive refinement, not weakening)

---

## 0. Purpose and Scope

Phase 3 introduces *explicit Geometry-of-Interaction (GOI) semantics* into the compiler for the first time.

The purpose of this phase is **not** to add general recursion, runtime looping, or implicit cyclic execution. Instead, Phase 3:

- Adds *one explicit, fenced feedback operator* to the term language.
- Introduces an explicit GOI intermediate representation (IR).
- Provides a **sound but incomplete** extraction mechanism that either:
  - collapses GOI routing to a boundary permutation (success), or
  - preserves a residual GOI artifact (failure).

Phases 0–2 are frozen and must remain behaviorally unchanged.

---

## 1. Non-Negotiable Invariants (Carried Forward)

The following invariants are **architectural axioms**. No Phase 3 code may weaken them.

### 1.1 Structure vs Computation

- Structural terms compile *only* to `WirePerm` metadata.
- Structural compilation emits **no gates and no SWAPs**.
- All computation is expressed *only* as gate atoms.

### 1.2 Flat Execution Artifact

- Successful extraction always yields:
  - a flat, first-order circuit, and
  - a final boundary `WirePerm`.
- No runtime trace, loop, or feedback exists in extracted artifacts.

### 1.3 GOI Checkpoint Invariant

> Whenever extraction succeeds, GOI evaluation collapses to a boundary permutation.

Equivalently:
- GOI evaluation *routes*, it does not compute.
- Gates already emitted account for all computation.

---

## 2. Phase 3 Entry Points

Phase 3 must not disturb the Phase 0–2 compiler API.

### 2.1 Existing API (Unchanged)

```python
compile(term, materialize=False) -> (Circuit, WirePerm)
```

### 2.2 New API (Phase 3)

```python
compile_goi(term, materialize=False)
    -> Extracted | ResidualGOI
```

Where:

- `Extracted = (Circuit, WirePerm)`
- `ResidualGOI = GOIArtifact`

Materialization (`SWAP` insertion) applies **only** in the `Extracted` case.

---

## 3. New Language Construct: `Feedback`

### 3.1 Syntax

Phase 3 introduces exactly **one** new syntactic construct:

```text
Feedback_k(body)
```

Where `k` is a *wire count* (or equivalently, a type width).

### 3.2 Intended Typing (Informal)

If:

```
body : (A ⊗ X) → (B ⊗ X)
width(X) = k
```

then:

```
Feedback_k(body) : A → B
```

### 3.3 Architectural Meaning

- `Feedback` is the *only* construct allowed to create cycles.
- All cycles are **syntactic, explicit, and fenced**.
- No implicit feedback is permitted anywhere in the compiler.

---

## 4. GOI Intermediate Representation (IR)

Phase 3 introduces an explicit representation of GOI structure.

### 4.1 GOIArtifact Structure

A `GOIArtifact` minimally contains:

```python
GOIArtifact = {
  n_in: int,
  n_out: int,
  perm: WirePerm,
  atoms: List[GateAtom],
  loops: List[LoopSpec]
}
```

### 4.2 Components

- **Boundary**
  - `n_in`, `n_out` describe external arity.

- **Routing (`WirePerm`)**
  - Encodes all structural effects and GOI routing.

- **Gate atoms**
  - Exactly the same atomic unitary operations used in Phases 1–2.
  - Each atom carries explicit wire indices.

- **LoopSpec**
  - Describes explicit feedback wiring.
  - Phase 3 canonical form: loop the *last `k` output wires* back to the *last `k` input wires*.

---

## 5. GOI Compilation Semantics

### 5.1 Structural Compilation

- Identical to Phases 0–2.
- Produces only permutations.

### 5.2 Gate Compilation

- Identical to Phases 0–2.
- Produces `GateAtom`s with deterministic ordering.

### 5.3 Composition

- Atom lists concatenate deterministically (left first).
- Permutations compose.
- Wire indices are rewritten via:

```text
physical = perm.apply_new_to_old(logical)
```

### 5.4 Feedback Handling

When compiling `Feedback_k(body)`:

1. Compile `body` to a `GOIArtifact`.
2. Attach a `LoopSpec(k)` to the artifact.
3. No elimination occurs at this stage.

This phase performs **no execution**, only construction.

---

## 6. Normalization Pass

### 6.1 Purpose

Normalize GOI artifacts by pushing all structure into permutations while leaving gate atoms untouched.

### 6.2 Firewall Rule (Critical)

> Structural rewrites may move gates around, but never rewrite *inside* a gate atom.

Consequences:
- Analytic operators (e.g. exponentials) are atomic.
- Normalization is index-rewriting only.

---

## 7. Feedback Elimination (Extraction)

### 7.1 Extraction Pass

```python
try_extract(goi: GOIArtifact)
    -> Extracted | ResidualGOI
```

### 7.2 Soundness Policy

- Extraction is **permissive only when provably correct**.
- Failure is *not an error*.

### 7.3 Yankability Criterion (Phase 3)

A feedback loop is **eliminable** iff:

> No gate atom touches any loop wire after normalization.

Formally:
- Let `L` be the set of loop wire indices.
- For every `GateAtom g`, `support(g) ∩ L = ∅`.

### 7.4 Elimination Algorithm

If the criterion holds:

1. Compute the induced boundary permutation by composing:
   - internal routing permutation, and
   - loop identifications.
2. Discard the loop specification.
3. Return:
   - unchanged gate atom list,
   - updated boundary `WirePerm`.

If the criterion fails:

- Return the unchanged `GOIArtifact` as `ResidualGOI`.

---

## 8. Architectural Interpretation

### 8.1 Relation to Yanking

- Phase 3 implements **restricted yanking**:
  - only for pure wiring loops.
- This is *derived by normalization*, not assumed axiomatically.

### 8.2 Soundness vs Completeness

- Phase 3 guarantees **soundness only**.
- Completeness is explicitly deferred.

Residual GOI artifacts preserve information needed for later refinement.

---

## 9. Forward Compatibility

### 9.1 ZX Integration

ZX may later:
- operate on residual GOI artifacts,
- prove additional cases eliminable,
- never alter extracted results.

### 9.2 Analytic Exponentials

- Treated as gate atoms.
- May block elimination if they touch loop wires.
- Require no Phase 3 redesign.

---

## 10. Developer Guidance

- **Do not modify** Phase 0–2 behavior.
- All Phase 3 code must be additive.
- Prefer explicit data structures over implicit behavior.
- Failure to extract is a valid, expected outcome.

---

## 11. Summary

Phase 3 introduces explicit GOI feedback with fenced semantics. Compilation constructs routing-plus-gates artifacts. Extraction soundly collapses feedback to boundary permutations when possible, and otherwise preserves residual GOI structure. This design ensures rollback safety, deterministic behavior, and compatibility with future completeness-improving passes.

