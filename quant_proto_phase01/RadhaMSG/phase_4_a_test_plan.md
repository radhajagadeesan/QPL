# Phase 4A — Extraction++ Test Plan

This document defines the **comprehensive test plan** for Phase 4A. Its purpose is to guarantee:

- Strict additivity over Phase 3,
- No regression of Phase 0–3 behavior,
- Deterministic extraction results,
- Preservation of all locked invariants.

---

## Global Meta‑Constraint

All Phase 0–3 golden files **must remain unchanged**.

Phase 4A tests are additive and live in a separate namespace.

---

## A. Unit Tests — Loop Interaction Analysis

### A1. Gate support under permutation

- Construct small `WirePerm` instances and gate atoms.
- Verify:
  - correct reindexing of `support(G)` under conjugation,
  - determinism of support computation.

### A2. Loop-wire disjointness certification

- Explicitly mark loop wires.
- Test cases where:
  - disjointness is provable (expect witness),
  - disjointness is not provable (expect failure).

### A3. Witness determinism

- Same GOIArtifact ⇒ byte-identical witness serialization.

---

## B. Local GOI Invariant Tests (New Phase 4A Capabilities)

Each test must assert:

- Phase 3 extraction fails (returns residual).
- Phase 4A extraction succeeds.
- Output satisfies all locked invariants.

### B1. Externalizable gate via routing conjugation

- Gate appears adjacent to feedback loop syntactically.
- After routing normalization, gate acts only on non-loop wires.

### B2. Routing hidden behind associativity

- Same as B1, but requires reassociation to expose routing.

### B3. Mixed gates

- Some gates externalizable, some truly touch loop wires.
- Expected result: residual preserved.

### B4. Nested feedback unlocking

- Inner feedback becomes yankable after Phase 4A rewriting.
- Outer feedback remains residual if necessary.

### B5. Firewall regression

- Use opaque/mock gate atoms that fail if inspected.
- Ensure Phase 4A never touches gate internals.

---

## C. End‑to‑End Integration Tests (New Goldens)

Directory:

```
tests/goldens/phase4a_extracts_more/
```

Each golden must assert:

- Phase 3 → residual GOIArtifact.
- Phase 4A → `(Circuit, WirePerm)`.
- `compile(materialize=False)` emits:
  - zero SWAPs,
  - unitary pytket gates only.
- Final permutation matches expected.
- Determinism hash is stable.

---

## D. Negative Integration Tests

Programs that must **remain residual** under Phase 4A:

1. Gates that genuinely act on loop wires.
2. Ambiguous routing where disjointness cannot be certified.
3. Cases requiring rewriting inside gate atoms to succeed.

Expected outcome:

- Phase 4A returns residual GOIArtifact.
- No errors are raised.

---

## E. Regression Tests — Phase 0–3 Lockdown

- Re-run entire existing golden corpus.
- Assert:
  - identical command streams,
  - identical permutations,
  - identical residual artifacts,
  - identical determinism hashes.

---

## F. Performance Sanity Tests (Optional but Recommended)

- Medium-sized residual GOIArtifacts.
- Assert:
  - no exponential blowup,
  - extraction time within CI thresholds.

---

## Pass Criteria

Phase 4A is considered complete when:

- All new tests pass.
- All existing goldens are unchanged.
- Phase 4A goldens demonstrate strictly increased extraction power.

---

## Summary

This test plan enforces Phase 4A’s core promise:

> **Extract more, never extract incorrectly, never regress.**

It provides high confidence that extraction completeness increases without any loss of soundness or determinism.

