# Phase 0–4C Comprehensive Integration Test Plan (End-to-End)

**Purpose:** lock down end-to-end behavior across **Phases 0–4C** with strong regression guarantees, deterministic outputs, and strict adherence to the locked invariants:
- **Structure vs computation** (structural ⇒ WirePerm only; no gates, no swaps)
- **SWAP policy** (`materialize=False` ⇒ no swaps; swaps only via explicit materialization)
- **Determinism** (same AST ⇒ identical outputs)
- **DistL/DistR loud failures**
- **GOI checkpoint invariant** (“GOI routes; it does not compute.”)
- **Firewall** (never rewrite inside gate atoms; only use declared support)
- **Rollback safety** for Phase 4B ZX post-pass
- **New gate vocabulary** (Phase 4C) with canonical parameter serialization

This plan assumes:
- Phase 4A is complete and locked
- Phase 4B is behind `enable_zx` (default False)
- Phase 4C introduces new primitive unitary atoms (including exponentials) as opaque gates
- Phase 4D (semantic propagation) is a non-goal

---

## 0. Test Harness and Golden Infrastructure

### 0.1 Canonical top-level entrypoints
All integration tests must drive the same public entrypoints used by real users:

- `compile(ast, materialize: bool, enable_zx: bool, ...) -> CompileResult`
- If extracted: `CompileResult.circuit`, `CompileResult.perm`
- If residual: `CompileResult.residual_goi`
- Optional backend step (only when extracted):
  - `lower_to_pytket(circuit, perm, materialize: bool) -> pytket.Circuit`

### 0.2 Canonical serialization (required for determinism/goldens)
Define stable serializers (no `repr`, no unordered containers):
- `ser_cmds(cmd_stream) -> bytes`
- `ser_circuit(circuit) -> bytes` (logical-wire model; stable gate ordering)
- `ser_perm(perm) -> bytes`
- `ser_residual(goi_artifact) -> bytes` (canonical form; sorted)
- `ser_error(err) -> (type, code, stable_message_fragment)`

Define `digest = sha256(serialized)` for comparisons.

### 0.3 Golden structure
Recommended:
```
tests/goldens/
  phase0_2/
  phase3/
  phase4a/
  phase4b/
  phase4c/
  negative_residuals/
  dist_failures/
```

Each golden fixture includes:
- input program or AST fixture
- expected outcome:
  - extracted: circuit + perm (+ optional cmd stream)
  - residual: residual serialization
  - loud-failure: stable error signature

---

## 1. Regression Lock: Phase 0–4B Must Remain Unchanged

### 1.1 Default mode regression (enable_zx=False)
Run all existing Phase 0–4B goldens with:
- `enable_zx=False`
- `materialize=False` and any existing `materialize=True` suite

**Assertion:** all outputs are bit-identical.

### 1.2 4B non-interference regression (enable_zx=True where v2 extracts)
Select a representative sample of v1/v2-extractable cases (no residual after v2).
Run with `enable_zx=True`.

**Assertion:** bit-identical to goldens (4B must not run).

---

## 2. Phase 4C Regression: Old Programs Must Not Change

### 2.1 Core regression suite
Re-run all Phase 0–4B goldens after adding 4C code paths.

**Assertion:** unchanged outputs.

### 2.2 DistL/DistR loud failure invariants
Re-run all distributivity failure fixtures with and without `enable_zx`.

**Assertion:** identical loud-failure signatures.

---

## 3. Phase 4C New Gate Vocabulary: Integration Coverage

Phase 4C adds new primitive unitaries as **opaque GateAtoms**. Integration tests must cover:

### 3.1 Gate admission and typing
Fixtures for each new primitive gate kind:
- minimal valid usage
- wrong arity
- invalid parameter type (if applicable)
- parameter omitted where required

**Assertions:**
- valid fixtures compile
- invalid fixtures fail with stable error signatures
- failures are not affected by `enable_zx`

### 3.2 Backend lowering to pytket (unitary-only)
For each new gate kind (including exponentials):
- compile to extracted circuit (no feedback)
- lower to pytket
- validate:
  - produced pytket ops are unitary-only per your policy
  - arity matches
  - deterministic emission order

**Assertions:**
- stable serialization of lowered circuit across runs
- no SWAPs when `materialize=False`

### 3.3 Canonical parameter serialization
Add “format stability” tests:
- same parameter value via different syntactic forms (e.g. `0.5`, `1/2`, `0.5000` if supported)
- roundtrip parse/serialize
- ensure `ser_circuit` is stable and canonical

**Assertions:**
- exact match to golden serialization
- repeated runs hash-identical

---

## 4. Interaction with Routing: Support Reindexing is Mandatory

These tests ensure new 4C atoms respect the Phase 4A decision that **GateAtom wires are logical** and commute with routing by support reindexing.

### 4.1 Pure routing commutation
Construct fixtures where routing (permutation) surrounds a new exponential gate:
- `Perm ; ExpGate(S) ; Perm^{-1}`

**Assertions:**
- extraction/normalization can commute routing past the gate (structurally)
- resulting circuit/perm is deterministic and matches a golden

### 4.2 Routing normalization + 4B ZX mode
Take a fixture that becomes extractable only after routing normalization (Phase 4A), and replace a standard gate with an exponential gate.

**Assertions:**
- with `enable_zx=False`: should behave as Phase 4A expects (extract or residual)
- with `enable_zx=True`: if residual exists, 4B can run, but must treat the exp gate as opaque
- in negative cases: residual must be byte-identical to v2 residual

---

## 5. Extraction Soundness with New Gates (Feedback Interaction)

### 5.1 Positive: gate off loop wires
Construct feedback fixtures where:
- exp gate exists but provably does not touch loop wires (mod routing)

**Assertions:**
- extraction succeeds (v1/v2 or via 4B if needed)
- output is `(Circuit, WirePerm)` and contains the exp gate atom
- determinism hash stable

### 5.2 Negative: gate touches loop wires
Construct feedback fixtures where:
- exp gate support overlaps loop wires in an unavoidable way

**Assertions:**
- extraction remains residual (even with `enable_zx=True`)
- residual is byte-identical to v2 residual (rollback/no partial normalization)

---

## 6. Phase 4B + 4C Combined (Critical Integration)

This is the “new behavior zone”: residuals with exp gates where ZX may simplify structure but must never inspect gates.

### 6.1 4B positive corpus with exp gates as opaque boxes
Create cases where:
- v2 residual exists due to structural obstruction
- exp gates are present but not on the critical loop wires after structural simplification
- 4B should succeed

**Assertions:**
- `enable_zx=False`: residual (baseline)
- `enable_zx=True`: extracted `(Circuit, WirePerm)` golden
- exp gates are preserved as opaque atoms (same parameters, same supports up to reindexing)

### 6.2 4B negative corpus with exp gates blocking simplification
Create cases where:
- structural simplification would require crossing an exp gate (not allowed)
- 4B must fail and return residual unchanged

**Assertions:**
- residual unchanged (byte-identical)
- no partial rewrites leak

### 6.3 Firewall canary tests
Use a canary gate atom that throws if internals are inspected.
Include exp gates in the same fixture.

**Assertions:**
- 4B rewrite schedule never inspects gate internals
- only declared support/ports used

---

## 7. SWAP Policy End-to-End (Including New Gates)

### 7.1 materialize=False ⇒ zero swaps
For representative extracted circuits in:
- Phase 0–2
- Phase 3
- Phase 4A
- Phase 4B (zx-extracted)
- Phase 4C (exp gates)

**Assertions:**
- zero swaps in emitted command stream and/or lowered pytket circuit
- structural-only programs emit no gates

### 7.2 materialize=True ⇒ swaps only at materialization
For extracted programs (including exp gate programs):
- run compile with `materialize=True`
- ensure swaps appear only after extraction and only in the materialization stage

### 7.3 residuals must never materialize
For negative feedback fixtures (incl. exp gates):
- `materialize=True` must still yield residual and must not introduce swaps or backend lowering.

---

## 8. Determinism Matrix (Whole Pipeline)

For each category, run N times (recommend N=5):

- structural-only (perm-only)
- gates, no feedback (flat extraction)
- feedback extracted by v2
- residual stays residual
- residual extracted by 4B
- exp-gate no feedback
- exp-gate with feedback extracted
- exp-gate with feedback residual

**Assertions:**
- all relevant digests stable across runs:
  - command stream
  - circuit
  - perm
  - residual
  - error signatures

Also test toggles:
- `enable_zx=False` vs `enable_zx=True` should differ only in 4B positive cases
- `materialize=False` vs `materialize=True` should differ only by explicit swaps stage (when extracted)

---

## 9. Backend Sanity (Post-Extraction Only)

For all extracted outputs (including exp gates):
- lower to pytket
- verify:
  - unitary-only operations
  - arities correct
  - stable serialization

Optional (if you already have it):
- small-state equivalence check for tiny circuits; keep it out of goldens if nondeterministic.

---

## 10. Suggested Test File Layout (pytest)

- `tests/integration/test_regression_phase0_4b_goldens.py`
- `tests/integration/test_phase4c_regression_no_change.py`
- `tests/integration/test_phase4c_gate_admission.py`
- `tests/integration/test_phase4c_backend_lowering.py`
- `tests/integration/test_phase4c_param_serialization.py`
- `tests/integration/test_phase4c_support_reindexing.py`
- `tests/integration/test_phase4c_feedback_positive.py`
- `tests/integration/test_phase4c_feedback_negative.py`
- `tests/integration/test_phase4b_with_phase4c_positive.py`
- `tests/integration/test_phase4b_with_phase4c_negative.py`
- `tests/integration/test_swap_policy_end_to_end.py`
- `tests/integration/test_dist_loud_failures.py`
- `tests/integration/test_firewall_canary.py`
- `tests/integration/test_determinism_matrix.py`
- `tests/integration/test_backend_sanity_phase4c.py`

---

## 11. Definition of Done (0–4C)

Phase 0–4C pipeline is “gelling” when:

- ✅ All Phase 0–4B goldens unchanged (regression lock)
- ✅ 4C new-gate fixtures compile, lower, and serialize deterministically
- ✅ 4C feedback interaction behaves soundly (extract or residual as expected)
- ✅ 4B + 4C integration corpora pass (opaque boxes; rollback-safe)
- ✅ Determinism matrix stable across runs
- ✅ SWAP policy holds across all configurations
- ✅ DistL/DistR loud failures remain loud and stable
- ✅ Firewall canary passes (no gate inspection)

---

*End of Phase 0–4C integration test plan.*
