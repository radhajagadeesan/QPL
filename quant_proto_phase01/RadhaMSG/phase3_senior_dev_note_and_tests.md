# Phase 3 Implementation Note (Senior Developer Handoff)
**Project:** Quantum compiler prototype (Phases 0–3)  
**Phase:** 3 — Explicit GOI (Feedback), sound extraction, residual preservation  
**Audience:** Implementing developer / maintainer  
**Status:** Actionable, test-driven plan (no weakening of Phase 0–2 invariants)

---

## 0. Non-negotiables (repeat these before coding)
Phases 0–2 are **complete and frozen**. Their behavior is the spec.

### 0.1 Structure = metadata only
- Structural terms compile only to `WirePerm`.
- Structural compilation emits **no gates** and **no SWAPs**.

### 0.2 Computation = gates only
- Gates emit unitary pytket ops.
- Indices rewritten with:
  ```
  physical = perm.apply_new_to_old(logical)
  ```

### 0.3 SWAP policy
- `compile(..., materialize=False)` emits **zero SWAPs**.
- SWAPs appear only when materializing:
  - `compile(..., materialize=True)` or
  - explicit `swaps_for_perm + apply_swaps`.

### 0.4 Determinism
Same AST → identical command stream + final permutation.

### 0.5 Distributivity deferred
`DistL` / `DistR` may typecheck but compilation must fail loudly.

### 0.6 GOI checkpoint invariant (Phase 3 must preserve)
> Whenever extraction succeeds, GOI collapses to a **boundary permutation**.
GOI routes; it does not compute.

---

## 1. Phase 3 goal statement
Phase 3 introduces **one explicit fenced feedback operator** and the minimum GOI plumbing needed to:
- build an explicit GOI artifact when feedback is present,
- attempt **sound** feedback elimination (restricted yanking),
- return either:
  - **Extracted**: `(Circuit, WirePerm)` (flat artifact), or
  - **ResidualGOI**: a preserved GOI object for future refinement (ZX, etc.).

No implicit feedback. No runtime execution semantics beyond routing+extraction.

---

## 2. Deliverables checklist (implementation tasks)

### 2.1 AST / Terms
Add exactly one new term constructor:

- `Feedback(k: int, body: Term)`

**Canonical interpretation (Phase 3):**
- `body : (A ⊗ X) → (B ⊗ X)` where `width(X)=k`
- then `Feedback_k(body) : A → B`

**Fence requirement:** feedback cycles exist *only* by this syntactic node.

### 2.2 GOI IR
Implement / confirm:

- `GOIArtifact` (Residual GOI object)

Minimum fields:
- `n_in: int`, `n_out: int`
- `perm: WirePerm` (routing metadata)
- `atoms: list[GateAtom]` (opaque gate commands with concrete wire indices)
- `loops: list[LoopSpec]`

Phase 3 canonical loop:
- `LoopSpec(k)` loops the **last `k` output wires** back to the **last `k` input wires**.

### 2.3 Phase 3 entrypoint
Implement:

- `compile_goi(term, materialize=False) -> Extracted | GOIArtifact`

Rules:
- If term contains **no Feedback**, `compile_goi` must extract and match `compile` exactly (command stream + perm).
- If term contains Feedback:
  - compile to GOIArtifact,
  - normalize,
  - attempt extraction,
  - return residual GOIArtifact on failure (not error).
- Materialization applies **only** for extracted results.

### 2.4 Normalization (firewall)
Implement:

- `normalize_goi(goi: GOIArtifact) -> GOIArtifact`

Goal:
- push all structural routing into permutations / index rewriting
- **never rewrite inside atoms**

Firewall rule:
> Structural rewrites may move gates around via index rewriting, but never into the gate atom.

Typical implementation strategy:
- For each atom wire index `i`, rewrite to `perm.apply_new_to_old(i)`
- Set `perm` to identity afterward.

### 2.5 Extraction / elimination (restricted yanking)
Implement:

- `try_extract(goi: GOIArtifact) -> Extracted | GOIArtifact`

Phase 3 criterion (sound, incomplete):
- A loop is eliminable iff **no atom touches any loop wire** after normalization.

Canonical loop-wire set:
- For loop `k` and `n_out`, loop wires are `{n_out-k, …, n_out-1}`.

If eliminable:
- compute induced boundary permutation (erase loop/internal wires)
- return Extracted:
  - same atoms (same order, same params) — only routing changes
  - new boundary perm
If not eliminable:
- return residual GOIArtifact unchanged (except any normalization you choose to apply deterministically).

> Note: This is “restricted yanking” derived by check, not axiomatically assumed.

### 2.6 Residual usability
Residual GOIArtifact must:
- preserve loop metadata,
- preserve atoms,
- preserve enough routing information for later ZX / stronger extraction passes.

Strongly recommended:
- `GOIArtifact.serialize()` deterministic representation (JSON-like dict) for debugging & tests.

---

## 3. Implementation sequencing (how to get green fast)
1. Implement `Feedback` node + plumbing so parser/constructor can build it.
2. Implement GOIArtifact + LoopSpec canonical form.
3. Implement `compile_goi` as:
   - delegate to `compile` when no Feedback is present (must match goldens).
4. Implement normalization + yankability + try_extract.
5. Implement feedback compilation path:
   - compile body → GOIArtifact
   - attach LoopSpec
   - normalize + try_extract.
6. Run integration tests + golden tests after each step.

---

## 4. Comprehensive test list (what must exist)

This section is a complete inventory. Implement as pytest.  
Group A = local GOI invariants. Group B = top-level integration lockdown.

### A. Local GOI invariant tests (Phase 3)
These tests should not depend on the full compiler; they can create GOIArtifacts directly.

#### A1. Feedback fencing
- A1.1 No loops for non-Feedback terms: GOIArtifact loops list empty unless Feedback exists.
- A1.2 Feedback produces explicit LoopSpec(k) in residual form.
- A1.3 No implicit cycles: ensure any cycle-like behavior only comes from Feedback node.

#### A2. Normalization firewall
- A2.1 Atom identity preserved:
  - same gate names + params + ordering pre/post normalize
- A2.2 Only indices change by perm.apply_new_to_old
- A2.3 After normalization, perm is identity (or the chosen canonical normal form).
- A2.4 Parametrized gates (incl. “analytic exponential” placeholder) remain opaque.

#### A3. Yankability
- A3.1 Yankable if loop wires untouched
- A3.2 Not yankable if any atom touches any loop wire
- A3.3 Multiwire gate intersects loop wire → not yankable
- A3.4 If multiple loops supported, yankable only if none are touched.

#### A4. Collapse correctness (routing only)
- A4.1 try_extract on yankable returns Extracted and removes loop
- A4.2 try_extract preserves atom list exactly
- A4.3 Resulting perm depends only on routing when yankable

#### A5. Residual preservation
- A5.1 try_extract returns residual on non-yankable (no exception)
- A5.2 residual preserves loops+atoms
- A5.3 compile_goi(materialize=True) on residual never inserts swaps

#### A6. Determinism (Phase 3 core)
- A6.1 normalize_goi deterministic
- A6.2 try_extract deterministic
- A6.3 compile_goi deterministic (residual/extracted stable)

#### A7. Phase 2 interaction sanity
- A7.1 TenTerm offsets applied before perm rewrite (still true under GOI path)
- A7.2 Emission order: left then right, preserved.

#### A8. Distributivity still deferred
- A8.1 compile_goi fails loudly on DistL/DistR just like compile.

#### A9. SWAP policy preservation
- A9.1 extracted + materialize=False emits zero swaps
- A9.2 extracted + materialize=True may emit swaps
- A9.3 residual never emits swaps regardless of materialize flag

---

### B. Integrated lockdown tests (Phases 0–3 end-to-end)
These are “spec freeze” tests with goldens. They must run in CI.

#### B1. Phase 0–2 frozen behavior
For curated suite terms (no Feedback):
- `compile(term, materialize=False)` matches goldens exactly:
  - command stream
  - final perm
  - no swaps

Curated suite must include:
- pure structure (nontrivial perm)
- pure gates (H/S/CX mix)
- structure + gates interleaving
- deep seq nesting
- TenTerm offsets + following structure
- associator shuffles (tensor nesting)
- widths >= 8 once, to catch indexing edge cases

#### B2. Phase 3 must match Phase 0–2 on acyclic terms
For the same curated suite:
- `compile_goi(term, materialize=False)` must extract and match the exact same goldens.

This is the single most important Phase 3 integration guarantee.

#### B3. Extractable feedback cases
At least these cases:
- B3.1 `Feedback(k=1, body)` where body gates touch only non-loop wires → extracts; no extra gates; no swaps by default
- B3.2 `Feedback(k=2, body)` with gates on external wires only → extracts
- B3.3 nested feedback (optional): both yankable → extracts

Also verify:
- extracted circuit stream equals body’s stream when feedback adds no gates.

#### B4. Residual feedback cases
- B4.1 single 1-qubit gate on loop wire → residual GOIArtifact
- B4.2 2-qubit gate intersecting loop wire → residual
- B4.3 determinism: two runs yield identical residual serialization

#### B5. Global SWAP materialization
- B5.1 `compile(..., materialize=False)` swap-free always
- B5.2 `compile_goi(..., materialize=False)` swap-free when extracted
- B5.3 residual never materializes swaps
- B5.4 materialize=True allowed to insert swaps only in extracted branch

#### B6. Error discipline
- B6.1 DistL/DistR still fails loudly in both compile and compile_goi
- B6.2 no “silent residualization” for distributivity (unless explicitly designed later)

---

## 5. Golden workflow (must be followed)
Goldens are a spec lock. To generate:
- run `scripts/generate_goldens.py`
- commit updated goldens only when you **intend** to change the spec.

---

## 6. Ready-to-implement starting fixtures (recommended)
These are small, high-signal terms to implement early:

1) `t0_pure_structure`: `TwistTen(Q,Q)`  
2) `t1_pure_gates`: `Seq(H(0), CX(0,1), S(1))` on `Q⊗Q`  
3) `t3_tenterm_offsets`: `TenTerm(H on left Q, S on right Q)`  
4) `feedback_yankable`: `Feedback(1, body=Seq(H@0, S@1) on 3-wire context)`  
5) `feedback_residual`: `Feedback(1, body=H@loopwire)`  

These fixtures already appear in the integration suite you generated.

---

## 7. Definition of “Done”
Phase 3 is complete when:
- All Phase 0–2 tests and goldens remain unchanged.
- `compile_goi` matches `compile` on all acyclic terms.
- Yankable feedback extracts to flat circuit+perm.
- Non-yankable feedback returns residual GOIArtifact without error.
- Determinism holds (streams/perms/residual stable).
- SWAP policy holds globally.

