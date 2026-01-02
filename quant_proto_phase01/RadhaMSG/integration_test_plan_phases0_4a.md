# Integration Test Plan — Phases 0–4A (End-to-End Lockdown)

**Status:** Proposed (to be implemented as Phase 4A integration test expansion)  
**Scope:** Whole compiler pipeline from AST → (Circuit, WirePerm) or residual GOIArtifact, including materialization  
**Goal:** Ensure Phases 0–3 remain **frozen** while Phase 4A increases extraction completeness **without regressions**.

---

## 0. Principles / What “Gelling” Means

The integration suite must prove:

1. **Regression safety:** Every Phase 0–3 golden stays bit-identical.
2. **Strict additivity:** Phase 4A extracts **more**, never less, never differently on Phase 3-success cases.
3. **Pipeline coherence:** lowering → GOI normalization → extraction → backend lowering → (optional) materialization works as one system.
4. **Locked invariants hold end-to-end**, not only locally:
   - Structure vs computation (no gates from structure; no SWAPs from extraction)
   - SWAP policy (no SWAPs unless explicit materialize=True)
   - Determinism (same AST ⇒ identical outputs)
   - DistL/DistR loud failure at compile-time
   - GOI checkpoint (“routes not computes”) when extraction succeeds
   - Residual preservation (failure to extract returns residual GOI artifact)

---

## 1. Test Organization (Suggested Layout)

```
tests/
  integration/
    test_e2e_phase0_3_regression.py
    test_e2e_phase4a_delta_extracts_more.py
    test_e2e_materialization_swap_policy.py
    test_e2e_determinism.py
    test_e2e_dist_compile_failures.py
    test_e2e_residual_preservation.py
    test_e2e_backend_pytket_sanity.py
  goldens/
    phase0_3_lockdown/
      ... existing, unchanged ...
    phase4a_extracts_more/
      ... new ...
    phase4a_stays_residual/
      ... new ...
```

**Rule:** do not mix Phase 4A goldens with Phase 0–3 goldens.

---

## 2. Canonical “End-to-End” Compile Entrypoints Under Test

Integration tests should exercise exactly the public surfaces you care about:

### 2.1 Primary entrypoint
- `compile(ast, materialize=False)` returning either:
  - `Extracted(Circuit, WirePerm)` OR
  - `Residual(GOIArtifact)`

### 2.2 Optional entrypoint (materialization)
- `compile(ast, materialize=True)` returning either:
  - `Extracted(Circuit, identity_perm)` where SWAPs may be present, OR
  - **must not happen**: residual + materialize (should error early or skip, per invariant “Residual GOI artifacts never materialize”)

### 2.3 Debug / internal entrypoints (only if stable)
- `lower_to_goi(ast) -> GOIArtifact`
- `normalize(goi) -> GOIArtifact`
- `try_extract_v1(goi)` and `try_extract_v2(goi)`

Use these only when they are stable and part of the intended developer API; otherwise, keep tests at the public `compile`.

---

## 3. Golden Format and What Gets Locked

Because your Phase 0–3 behavior is specification, goldens should lock:

### For extracted results
- **Command stream** (pytket op list or your internal command IR), including:
  - gate names,
  - wire indices (logical indices, if that’s your stable representation),
  - parameters (if any),
  - ordering.
- **Final WirePerm** in canonical serialized form.
- **No SWAPs** when `materialize=False`.
- **Only unitary gates** (pytket ops) in extracted circuit.

### For residual results
You currently do not serialize residuals to JSON; tests compare dataclasses directly.
Integration should at least lock:
- residual kind (GOIArtifact),
- list of atoms (gate_name + wires),
- loop structure + routing/permutation if present,
- deterministic equality across multiple compile invocations.

**Recommendation:** define a stable `residual_fingerprint(goi)` string for integration tests (without committing to full JSON). Use it in Phase 4A suites to get reproducible diffs.

---

## 4. Integration Suite 1 — Phase 0–3 Regression Lockdown (Must Stay Identical)

### Test: `test_e2e_phase0_3_regression.py`

**Purpose:** prove Phase 4A integration does not change any existing locked behavior.

**Method:**
- Run the entire existing Phase 0–3 golden corpus.
- For each program:
  - compile(materialize=False): assert identical extracted/residual results to golden.
  - compile(materialize=True): assert identical output to golden, if materialization is part of prior spec.

**Assertions:**
- Exact match on command stream + WirePerm for extracted outputs.
- Exact match on residual fingerprint for residual outputs.
- No SWAPs for `materialize=False`.

---

## 5. Integration Suite 2 — Phase 4A Delta: “Extracts More”

### Test: `test_e2e_phase4a_delta_extracts_more.py`

**Purpose:** demonstrate strict additivity:
- Phase 3 leaves residual,
- Phase 4A extracts (Circuit, WirePerm).

**Corpus location:**
- `tests/goldens/phase4a_extracts_more/`

**Each case must assert:**
1. `try_extract_v1(normalized_goi)` returns `Residual`.
2. `try_extract_v2(normalized_goi)` returns `Extracted`.
3. `compile(materialize=False)`:
   - emits zero SWAPs,
   - emits only unitary gates,
   - matches golden command stream,
   - matches golden WirePerm.

**Required coverage buckets:**
- Externalizable gates via routing conjugation
- Deeper routing normalization (associativity / administrative structure)
- Multiple feedback nodes where only some become yankable post-Phase4A
- Nested feedback unlocking (inner becomes extractable)

---

## 6. Integration Suite 3 — Phase 4A Negative Delta: Must Remain Residual

### Test: `test_e2e_phase4a_stays_residual.py`

**Purpose:** ensure Phase 4A does not overreach.

**Corpus:**
- `tests/goldens/phase4a_stays_residual/`

**Each case must assert:**
- Phase 3 residual
- Phase 4A residual (identical residual fingerprint across runs)
- No errors (sound incompleteness policy)
- No SWAPs (materialize=False)

**Coverage buckets:**
- Gate truly touches loop wire
- Ambiguous cases where disjointness cannot be certified
- Would require rewriting inside gate atom to succeed (forbidden)

---

## 7. Integration Suite 4 — Materialization & SWAP Policy

### Test: `test_e2e_materialization_swap_policy.py`

**Purpose:** prove SWAP invariant end-to-end.

For a mix of extracted programs (Phase 0–3 and Phase 4A-extracted):

1. `compile(materialize=False)`:
   - assert command stream contains **no SWAP ops**.
2. `compile(materialize=True)`:
   - assert SWAP ops are permitted,
   - assert final WirePerm is identity (or canonical “consumed” perm),
   - assert circuit semantics correspond to applying perm physically.

**Also assert:**
- residual programs may not be materialized.
  - If API supports materialize on residuals, test must check it fails loudly and deterministically.
  - If API returns residual unchanged, assert no SWAPs emitted and residual unchanged (but your spec says “Residual GOI artifacts never materialize,” so failing loudly is typically cleaner).

---

## 8. Integration Suite 5 — Determinism & Stability

### Test: `test_e2e_determinism.py`

**Purpose:** enforce “same AST ⇒ identical output.”

For each program in the combined corpus (Phase 0–3 goldens + Phase 4A corpora):
- run compile twice (or N times with fixed seed if any).
- assert identical:
  - extracted circuit commands (exact list),
  - WirePerm serialization,
  - residual fingerprint.

Also test determinism across:
- different process executions (if CI can do that),
- different Python versions (if relevant).

---

## 9. Integration Suite 6 — DistL/DistR Loud Failures

### Test: `test_e2e_dist_compile_failures.py`

**Purpose:** ensure distributivity typechecks but fails at compile-time.

Create a small corpus of AST programs that include `DistL` / `DistR` in reachable code paths:
- They may parse and typecheck.
- Compile must raise a specific exception type or error code.

Assertions:
- exception type matches spec,
- error message contains required “loud” marker text,
- failure is deterministic.

Also include negative controls:
- Similar programs without `DistL/DistR` compile fine.

---

## 10. Integration Suite 7 — Residual Preservation

### Test: `test_e2e_residual_preservation.py`

**Purpose:** ensure extractor never mutates residuals unpredictably and preserves residual artifacts under compile variations.

For each residual program:
- compile multiple times
- assert exact residual fingerprint equality

If there is any pipeline variation (e.g., toggling debug flags), ensure:
- debug changes do not alter the residual artifact data model unless explicitly allowed.

---

## 11. Integration Suite 8 — Backend Sanity (pytket)

### Test: `test_e2e_backend_pytket_sanity.py`

**Purpose:** prove that extracted circuits are valid pytket objects and contain only allowed unitary operations.

Assertions:
- circuit builds successfully
- gate set is within allowed list (unitary only)
- no swaps when materialize=False

Optional (if you have a simulator available in test env):
- small random-state check: applying the circuit equals applying the composed unitary from the source semantics for tiny cases.

---

## 12. Coverage Matrix (What to Include)

Your integration corpus should cover, at minimum:

### Core constructs
- pure structural fragments (compile → WirePerm only)
- pure gates without feedback
- feedback with no gates touching loop wires (Phase 3 extractable)
- feedback with gates that can be externalized (Phase 4A extractable)
- feedback with gates truly touching loop wires (must remain residual)

### Composition patterns
- sequential composition
- tensor/parallel composition
- nested feedback
- multiple feedbacks in one artifact
- routing-heavy admin structure around feedback

### Edge behavior
- DistL/DistR failure
- determinism stress cases (many small perms and atoms)
- materialize behavior on extracted vs residual outputs

---

## 13. Acceptance Criteria (“All Gelling” Definition)

Phase 4A is integrated correctly iff:

1. **All Phase 0–3 goldens pass unchanged**.
2. Phase 4A delta corpus shows **new extractions** (v1 residual → v2 extracted).
3. Phase 4A negative corpus remains residual.
4. Determinism tests pass across all corpora.
5. SWAP policy holds:
   - no swaps in `materialize=False`,
   - swaps only in `materialize=True` and only after extraction.
6. DistL/DistR failures remain loud and deterministic.
7. Backend sanity checks pass for all extracted circuits.

---

## 14. Practical Implementation Notes

### 14.1 Keep v1 as the spec
In `try_extract_v2`, always:

- call `try_extract_v1` first
- if v1 succeeds, return exactly that output

This makes regression protection structural, not just test-based.

### 14.2 Add a residual fingerprint helper (recommended)
Even if residuals aren’t serialized, define:

- `residual_fingerprint(goi) -> str`

that deterministically encodes:
- loops,
- routing,
- gate atoms (name + wires),
- any relevant admin structure.

Use it only in tests to stabilize diffs.

---

## Appendix A — Minimal “Golden” API

If you don’t already have a golden harness, define:

- `render_extracted(result) -> str`
- `render_residual(goi) -> str` (fingerprint)
- `assert_matches_golden(name, rendered)`

This keeps goldens easy to diff and review.

---

## Appendix B — Suggested Corpus Naming

- `p0_struct_only_*`
- `p1_gate_only_*`
- `p3_feedback_yankable_*`
- `p3_feedback_residual_*`
- `p4a_extracts_more_*`
- `p4a_stays_residual_*`
- `dist_fail_*`
- `swap_policy_*`

Consistent naming makes it obvious what each case is asserting.

---

## Summary

This integration plan turns “Phases 0–4A are gelling” into a mechanically enforceable statement:

- old behavior remains frozen,
- Phase 4A is strictly additive,
- invariants are locked end-to-end,
- and failures are loud only where specified (DistL/DistR), while extraction remains soundly incomplete.

