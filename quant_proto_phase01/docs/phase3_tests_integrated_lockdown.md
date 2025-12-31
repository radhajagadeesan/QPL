# Phase 3 Test Plan (B): End-to-End Integrated Lockdown
**Purpose:** An integration suite that locks down observable behavior end-to-end, ensuring Phase 3 is purely additive and that Phases 0–2 remain frozen as the specification.

**Scope:** These tests exercise:
- `compile(term, materialize=...)` (Phases 0–2 path)
- `compile_goi(term, materialize=...)` (Phase 3 path)
- equivalence where required
- residual behavior where expected
- determinism and SWAP policies globally

---

## B0. Ground Rules for Integration Tests

### B0.1 “Frozen means frozen”
Any change in:
- circuit command stream, or
- final permutation,
for a Phase 0–2 term is a **breaking change**.

### B0.2 Canonical circuit comparison
Define a canonical textual stream:
- command name + params + wires in order
- no nondeterministic object ids
- stable formatting

Store expected command streams and expected perms in golden files:
- `tests/golden/*.txt` for circuits
- `tests/golden/*.perm.json` (or similar)

### B0.3 No SWAPs by default
Integration tests must enforce:
- `compile(..., materialize=False)` emits zero SWAPs
- `compile_goi(..., materialize=False)` emits zero SWAPs when extracted

---

## B1. Regression Suite: Phase 0–2 Behavioral Lockdown
### B1.1 Existing Phase 0–2 corpus
Re-run all existing tests unchanged.

### B1.2 Top-level “spec freeze” samples
Curate a set of representative terms:
1. pure structural permutations (tensor twists, associators)
2. pure gates with no structure
3. mixed structure + gates
4. deep nesting of tensor and seq
5. `TenTerm` offsets + following structural perm
6. “large enough” widths (e.g., width 8–12) to detect indexing errors

For each term:
- `compile(term, materialize=False)` must match golden stream + golden perm exactly.

---

## B2. Phase 3 Compatibility on Acyclic Terms
### B2.1 For all Phase 0–2 terms, compile_goi extracts identically
For each frozen term `t` (no Feedback):
- `compile_goi(t, materialize=False)` must return **Extracted**
- extracted circuit stream must equal `compile(t)` stream
- extracted perm must equal `compile(t)` perm
- no SWAPs

This is the most important integration guarantee: Phase 3 must not perturb the old world.

---

## B3. Phase 3: Extractable Feedback Cases
### B3.1 Pure-routing feedback collapses to permutation
Pick `Feedback_k(body)` where:
- body contains only structural routing on loop wires
- gates (if any) touch only non-loop wires

**Expected:**
- `compile_goi` returns Extracted
- circuit contains only the gates from the body (none added by feedback)
- final perm equals the induced boundary routing
- no SWAPs unless materialize=True

### B3.2 Nested feedback (optional)
If you allow nested `Feedback`, include a case where:
- inner feedback is yankable
- outer feedback is yankable
Expected: extraction succeeds and yields flat circuit+perm.

---

## B4. Phase 3: Residual Feedback Cases
### B4.1 Gate touches loop ⇒ residual
Construct `Feedback_k(body)` where a single gate touches a loop wire.
**Expected:**
- `compile_goi` returns ResidualGOI
- residual includes:
  - loop spec
  - atom list including the loop-touching gate
  - routing perm metadata

### B4.2 Residual is stable under repeated compilation
Run `compile_goi` twice.
**Expected:** residual serialization identical.

---

## B5. SWAP Materialization Policies (Global)
### B5.1 Old compiler remains SWAP-free by default
For all Phase 0–2 terms:
- `compile(t, materialize=False)` contains zero SWAPs
- `compile(t, materialize=True)` may insert SWAPs, but only via the existing materialization pipeline

### B5.2 Phase 3 extracted honors same SWAP policy
For all extractable terms (including feedback-yankable):
- `compile_goi(t, materialize=False)` contains zero SWAPs
- `compile_goi(t, materialize=True)` may insert SWAPs only in extracted branch

### B5.3 Phase 3 residual never materializes
For all residual cases:
- `compile_goi(t, materialize=True)` returns ResidualGOI (no SWAPs inserted)

---

## B6. Determinism End-to-End
### B6.1 Deterministic circuit stream and perm
For each term in the suite:
- run compile / compile_goi N times
- compare streams and perms
- **Expected:** identical across runs

---

## B7. Error Discipline: Distributivity Remains Deferred
### B7.1 DistL/DistR still fail loudly
For terms containing distributivity constructors:
- `compile` must fail loudly (existing behavior)
- `compile_goi` must fail loudly the same way
No silent residualization for distributivity (unless explicitly designed later).

---

## B8. Coverage Targets
Ensure the suite hits:
- multiple widths and offsets
- sequential composition depth
- tensor nesting depth
- permutations that substantially reorder wires
- multi-qubit gates interacting with permutations
- feedback with k=1,2,3 (at least)
- residual due to 1-qubit and 2-qubit gate on loop wires

---

## B9. Golden-Test Workflow
Recommended workflow:
1. Select suite terms and assign stable names (e.g., `spec_001_*`).
2. Generate golden streams + perms once.
3. Commit goldens; tests compare exactly.

This is essential to preserve the “Phases 0–2 are the spec” posture.

---

## B10. Acceptance Criteria for (B)
Phase 3 passes integration when:
- all Phase 0–2 goldens pass unchanged
- compile_goi matches compile on all acyclic terms
- extractable feedback cases collapse correctly
- residual cases are stable and preserve GOI info
- SWAP policy holds globally
- determinism holds globally
- distributivity remains loudly unsupported
