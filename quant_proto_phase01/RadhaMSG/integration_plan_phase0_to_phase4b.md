# Phase 0–4B Comprehensive Integration Test Plan (Pipeline-Level)

**Purpose:** lock down end-to-end behavior of the compiler pipeline across **Phases 0–4B** with emphasis on:
- **non-interference** (0–4A unchanged),
- **rollback safety** of 4B,
- **determinism**,
- **SWAP policy**,
- **DistL/DistR loud failures**,
- **GOI checkpoint invariant** (“GOI routes; it does not compute.”),
- **firewall** (never rewrite inside gate atoms).

This plan assumes Phase 4A is complete and test-locked, and Phase 4B is behind an `enable_zx` flag (default **False**).

---

## 0. Test Harness Conventions (Pipeline-Level)

### 0.1 Canonical pipeline entrypoints
All integration tests should drive the **same top-level entrypoints** used by real users:
- `compile(ast, materialize=False, enable_zx=<bool>, ...) -> CompileResult`
- (optional) `lower_to_pytket(result.circuit, perm, materialize=<bool>) -> pytket.Circuit`
- (optional) `materialize_swaps(...)` — only for materialize=True tests

### 0.2 Stable serialization
For golden tests and determinism checks, define stable serializers:
- `serialize_commands(cmd_stream) -> bytes/str`
- `serialize_circuit(circuit) -> bytes/str` (logical-wire representation, stable gate ordering)
- `serialize_perm(wireperm) -> bytes/str`
- `serialize_residual(goi_artifact) -> bytes/str` (canonical form)
- `digest(x) = sha256(serialize_*)`

**Rule:** never hash Python reprs that include pointer addresses or unordered sets.

### 0.3 Golden directory structure
Example:
```
tests/goldens/
  phase0_2/
  phase3/
  phase4a/
  phase4b/
  negative_residuals/
```

Goldens should include both:
- the **input program** (or AST fixture), and
- the **expected output**:
  - extracted: `(Circuit, WirePerm)` + cmd stream if applicable
  - residual: `GOIArtifact` canonical serialization

---

## 1. Regression Lock: Phases 0–4A Must Not Change

### 1.1 Full regression suite (enable_zx=False)
**Run all existing Phase 0–4A golden tests** with:
- `enable_zx=False` (default)
- `materialize=False` (and your existing materialize=True suite if present)

**Assertions:**
- All outputs are **bit-identical** to existing goldens:
  - cmd stream
  - extracted circuit serialization
  - final `WirePerm`
  - residual serialization (where applicable)

### 1.2 Non-interference sanity (enable_zx=True but v2 already extracts)
Select a representative sample of Phase 0–4A cases that already extract at v1 or v2.
Re-run with `enable_zx=True`.

**Assertion:** outputs remain **bit-identical** to goldens.  
(4B must not run when v2 succeeds; this test catches accidental invocation.)

---

## 2. Phase 4B Feature-Gating and Rollback Safety

### 2.1 Flag gating tests
For each of the Phase 4B corpora (positive + negative below):
- Run once with `enable_zx=False`
- Run once with `enable_zx=True`

**Assertions:**
- `enable_zx=False`: result matches the Phase 4A baseline (usually residual)
- `enable_zx=True`: may change only in expected positive cases; must be identical in negative cases

### 2.2 Rollback safety tests
For crafted residuals that trigger translation/rewrite failure paths (e.g., unsupported constructs, intentionally malformed diagrams):
- With `enable_zx=True`, `try_extract_zx` must return **exactly the original residual** (byte-identical serialization).

**Assertion:** `serialize_residual(out) == serialize_residual(in)`.

---

## 3. Phase 4B Positive Corpus (New Goldens)

Goal: establish new goldens demonstrating:
- v1 fails → v2 fails → residual
- 4B structural ZX pass succeeds
- output becomes extracted `(Circuit, WirePerm)`

### 3.1 Required positive categories
Create test families that are *structural-only obstacles*:

1. **Routing-only loop that becomes gate-free after structural normalization**
   - Residual has feedback, but all gates can be proven off loop wires after routing normalization.
2. **Permutation cancellation around feedback boundary**
   - Residual includes adjacent inverse routing layers blocking v2 recognition.
3. **Two-stage structural simplification**
   - Requires identity removal + boundary permutation canonicalization to expose extractable form.

### 3.2 Assertions for each positive golden
- With `enable_zx=False`: residual equals Phase 4A golden residual.
- With `enable_zx=True`: extracted result equals Phase 4B golden extracted output.
- Determinism: repeated runs produce identical digests.

---

## 4. Phase 4B Negative Corpus (Must Remain Residual)

Goal: ensure soundness is not “improved” incorrectly.

### 4.1 Required negative categories
1. **Genuine gate–feedback interaction**
   - A gate’s declared support touches loop wires in a way that cannot be removed by routing-only rewrites.
2. **Nested feedback with gate involvement**
   - Any case where extraction would require semantic gate reasoning.
3. **Opaque gate barriers**
   - A routing-only simplification is blocked by a gate box; must remain residual.

### 4.2 Assertions
- With `enable_zx=True`: output is residual and **byte-identical to the v2 residual**.
- No partial normalization leakage.

---

## 5. Determinism (Whole-Pipeline)

### 5.1 Determinism matrix
For each selected fixture in:
- Phase 0–2 (no feedback)
- Phase 3 extracted
- Phase 4A extracted
- Phase 4A residual
- Phase 4B positive (zx-extracted)
- Phase 4B negative (zx-residual)

Run the full pipeline **N times** (recommend N=5) with fixed environment.

**Assertions:**
- `digest(cmd_stream)` stable
- `digest(extracted circuit)` stable
- `digest(perm)` stable
- `digest(residual)` stable

### 5.2 Permutation determinism
Explicitly test:
- same AST ⇒ same final `WirePerm`, even when enable_zx toggled (in cases where result should not change)

---

## 6. SWAP Policy Integration Tests

### 6.1 No swaps when materialize=False
For each extracted class (Phase 0–4B extracted):
- run with `materialize=False`
- lower to pytket (or inspect IR) and assert:
  - **zero SWAP operations emitted**
  - structural compilation emits no swaps or gates

### 6.2 Swaps only via explicit materialization
For representative extracted circuits:
- run with `materialize=True`
- assert:
  - swaps may appear **only** in materialization stage
  - **no residual GOIArtifact ever materializes**

### 6.3 Cross-check
For a case that remains residual (negative corpus):
- `materialize=True` must still not introduce swaps (since residual cannot lower/materialize).

---

## 7. DistL / DistR Loud-Failure Tests (Pipeline)

Create fixtures that typecheck but must fail at compile time.

**Assertions:**
- compilation raises your designated compile-time error
- error message includes stable identifier (e.g., “DistL/DistR not supported”)
- enabling ZX must not affect this behavior

---

## 8. GOI Checkpoint Invariant Tests

### 8.1 Checkpoint consistency
For extracted cases (from v1, v2, and zx):
- assert that GOI evaluation collapses to a **boundary permutation**:
  - extracted output includes `WirePerm`
  - no residual GOI components remain

### 8.2 “GOI routes; it does not compute.”
For structural-only terms:
- result must be **WirePerm-only**
- no gates emitted

For gate terms without feedback:
- result must be flat circuit + perm, no residual GOI.

---

## 9. Firewall Tests (No gate inspection)

### 9.1 Canary gate atoms
Add a special test-only gate atom variant that:
- explodes/raises if any code tries to inspect internals beyond declared interface/support

Run Phase 4B positive and negative corpora with this canary gate available.

**Assertions:**
- 4B does not touch gate internals
- only uses declared support/ports

### 9.2 Rule audit test (optional)
Instrument rewrite pass to assert it never rewrites through/inside box nodes.

---

## 10. Backend Sanity Tests (Post-Extraction)

For extracted outputs (including 4B positives):
- lower to pytket
- verify:
  - only unitary ops (as per Phase invariants)
  - wire counts correct
  - serialization stable

Optional:
- run a tiny simulator equivalence check for small circuits if you already have it, but **avoid** introducing nondeterministic simulation artifacts into golden expectations.

---

## 11. Coverage Targets and “Definition of Done” for 4B

### 11.1 Minimum acceptance criteria
- ✅ All Phase 0–4A goldens unchanged (enable_zx=False)
- ✅ enable_zx=True does not affect any v1/v2-extracted cases
- ✅ A positive 4B corpus exists and is golden-locked
- ✅ A negative corpus exists and is locked to remain residual
- ✅ Determinism suite passes across all categories
- ✅ SWAP policy suite passes
- ✅ Firewall canary suite passes
- ✅ DistL/DistR loud-failure suite passes

### 11.2 Suggested initial corpus sizing
- Phase 4B positives: 10–20 cases
- Phase 4B negatives: 20–50 cases (soundness guardrail > completeness)

---

## 12. Practical Test File Outline

Suggested files (pytest naming, adjust to your repo):

- `tests/integration/test_regression_phase0_4a_goldens.py`
- `tests/integration/test_phase4b_flag_gating.py`
- `tests/integration/test_phase4b_positive_goldens.py`
- `tests/integration/test_phase4b_negative_residuals.py`
- `tests/integration/test_phase4b_rollback_safety.py`
- `tests/integration/test_phase4b_determinism.py`
- `tests/integration/test_swap_policy_pipeline.py`
- `tests/integration/test_dist_loud_failures.py`
- `tests/integration/test_firewall_canary.py`
- `tests/integration/test_backend_sanity_phase4b.py`

---

## 13. Notes on Maintaining Goldens

- Keep goldens small, explicit, and human-reviewable.
- Prefer:
  - stable JSON for circuits/perms/residuals
  - strict sorting and canonicalization in serializers
- Whenever goldens change, require:
  - a changelog entry explaining why, and
  - proof that Phase 0–4A behavior is unchanged.

---

## 14. Quick Checklist for CI

In CI, run in this order:

1. Phase 0–4A regression (`enable_zx=False`)
2. Phase 4B gating tests
3. Phase 4B positive goldens (`enable_zx=True`)
4. Phase 4B negative residuals (`enable_zx=True`)
5. Determinism suite (multi-run)
6. SWAP policy suite
7. Firewall canary suite
8. Backend sanity suite

This ordering catches “non-interference” bugs as early as possible.

---

*End of integration plan.*
