# Phase 4A Extraction Note — Extraction++ (Developer Reference)

**Status:** Active (Phase 4A)  
**Scope:** GOI extraction pipeline  
**Depends on:** `developer_phase4a_gateatom_decision.md`  
**Audience:** Compiler / extraction developers

---

## Purpose of This Note

This note explains **how Phase 4A extraction works in practice**, how it differs from Phase 3, and what invariants extraction developers must respect when modifying or extending the extractor.

It is intentionally **operational**, not architectural: this is the document you read when implementing or debugging `try_extract_v2`.

---

## Context Recap (One Paragraph)

Phase 3 extraction is **sound but incomplete**: it extracts exactly when feedback loops are syntactically gate-free.  
Phase 4A increases completeness **without weakening soundness** by recognizing additional cases where loops are gate-free **modulo routing**, using only structural reasoning (permutations, reassociation, cut elimination) and **never rewriting inside gate atoms**.

---

## Non‑Negotiable Invariants (Restated)

Phase 4A extraction **must preserve all Phase 3 invariants**:

1. Extraction is **sound but incomplete**.
2. If extraction succeeds, GOI evaluation collapses to a **boundary permutation**.
3. If extraction fails, return a **residual GOIArtifact**, not an error.
4. Structural compilation emits **no gates and no SWAPs**.
5. `materialize=False` ⇒ **zero SWAPs**.
6. Gates are **opaque atoms**; never inspect or rewrite their internals.
7. Determinism: same input ⇒ identical output (or identical residual).

If any of these are violated, the extractor is incorrect.

---

## Critical Prerequisite: Logical Gate Wires

Phase 4A **assumes** the decision recorded in:

```
developer_phase4a_gateatom_decision.md
```

Namely:

- `GateAtom.wires` are **logical indices**.
- Routing/permutation defines the physical frame.
- Physicalization occurs only at backend lowering.

Phase 4A reasoning is undefined if atoms carry physical wires.

---

## Phase 4A Extraction Pipeline

### Entry Point

```python
try_extract_v2(goi: GOIArtifact) -> ExtractResult
```

### High‑Level Control Flow

```
1. Attempt Phase 3 extraction (v1)
2. If v1 succeeds → return immediately
3. Otherwise:
   a. Normalize routing (outer-only)
   b. Analyze feedback loops
   c. Externalize routing when provably safe
   d. Retry Phase 3 yanking locally
4. If all feedback eliminated → flatten
5. Else → return residual GOIArtifact
```

**Rule:** Phase 4A may only run on residuals produced by Phase 3.

---

## What Phase 4A Is Allowed to Do

Phase 4A may apply **only structural transformations**:

- reassociate routing composition,
- cancel inverse permutations,
- commute permutations past gates by **reindexing logical support**,
- eliminate routing-only cut pairs,
- factor routing out of feedback bodies.

All of these operate **outside gate atoms**.

---

## What Phase 4A Is Forbidden to Do

Phase 4A must **never**:

- rewrite inside a `GateAtom`,
- inspect gate semantics,
- introduce new gates,
- introduce SWAPs,
- change Phase 3 success cases,
- throw errors on extractable-but-unsupported programs.

When in doubt: **return residual**.

---

## Feedback Eliminability (Phase 4A Criterion)

A feedback loop may be eliminated iff Phase 4A can **certify**:

> No gate acts on loop wires in the logical frame, possibly after routing normalization.

This is stronger than Phase 3’s syntactic check, but strictly weaker than full completeness.

---

## Externalization Pattern (Core Mechanism)

Phase 4A attempts to rewrite:

```
Feedback(k, body)
```

into:

```
P_out ; Feedback(k, body') ; P_in
```

where:

- `P_out`, `P_in` are routing-only,
- `body'` is Phase-3-yankable.

This rewrite is justified by an **ExternalizeWitness** produced by loop analysis.

If no witness exists, the feedback must remain.

---

## Determinism Rules

To preserve determinism:

- Traverse feedback nodes in a fixed canonical order.
- Apply rewrite rules in a fixed priority order.
- Normalize routing into a canonical normal form.
- Never depend on hash iteration order.

Residual equality is structural equality of GOIArtifacts.

---

## Debugging Guidance

When debugging Phase 4A extraction failures:

1. Verify atoms carry **logical** wires.
2. Check loop-wire sets are computed in the same logical frame.
3. Dump routing normal form before analysis.
4. Inspect which gates are classified as “touching” loops.
5. If unsure, disable Phase 4A and confirm Phase 3 behavior is unchanged.

---

## Common Failure Modes

| Symptom | Likely Cause |
|-------|-------------|
| Phase 3 goldens change | Phase 4A ran before v1 |
| Yank succeeds incorrectly | Gate touched loop wire physically but not logically |
| Nondeterministic output | Unordered traversal or rewrite choice |
| SWAPs appear | Materialization leaked into extraction |
| Residual mutated unexpectedly | Non-canonical routing normalization |

---

## Relationship to Future Phases

### Phase 4B (ZX post‑pass)
Phase 4A simplifies residual structure, making ZX translation smaller and more canonical.

### Phase 4C (Lie / exponentials)
Phase 4A remains valid because analytic atoms are opaque and support-based reasoning still applies.

---

## Summary (Mental Model)

Think of Phase 4A as:

> “Phase 3, plus the ability to recognize when routing is disguising a gate‑free loop.”

It **does not** compute, optimize, or simplify gates.  
It only exposes when feedback is *already* pure routing.

When Phase 4A cannot prove safety, it must back off.

That discipline is what keeps the extractor sound.

---

## Reference

- `developer_phase4a_gateatom_decision.md`
- Phase 3 extraction note
- Phase 4A test plan

