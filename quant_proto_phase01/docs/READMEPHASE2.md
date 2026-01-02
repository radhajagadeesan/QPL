# Phase 2 Spec: TenTerm (Controlled Parallel Composition with Offsets)

**Status:** Phase 1 is **complete and frozen**. Phase 2 is **additive**: it introduces `TenTerm` while preserving all Phase 0–1 invariants.

This spec is intentionally written in the same style as Phase 1: **invariants**, **what’s new**, and **what’s deferred**.

---

## Phase 0–1 invariants (still non-negotiable)

These are treated as *specification* and must remain locked by tests.

### Structure = metadata only
- Structural terms compile **only** to `WirePerm` updates.
- Structural compilation emits **no gates** and **no SWAPs**.

### Computation = gates only
- Gate terms emit unitary pytket operations (`H`, `S`, `CX`) on the circuit.
- Gate indices are rewritten through the compiler’s current `WirePerm` using the fixed convention:
  - `WirePerm.apply_new_to_old(new_idx)` is used to obtain the physical wire for a logical wire.
- The compiler never emits SWAPs by default.

### SWAPs appear only when explicitly materialized
- `compile(term, materialize=False)` must produce **no SWAP** operations.
- SWAPs may appear only when explicitly requested:
  - `compile(term, materialize=True)`, or
  - manual materialization via `swaps_for_perm(result.perm)` then `apply_swaps(result.circuit, swaps)`.

### Determinism
- Same AST → identical compiled result (circuit command stream and final permutation), across repeated runs.

### Distributivity (implemented in Phase 4C)
- `DistL/DistR` are now fully supported with the tagged layout model.
- DistL is identity on wires; DistR moves the tag from position 1 to position 0.
- Both compile to structural permutations (no gates).

### Flat first-order unitary artifact
- Compilation always yields a flat first-order pytket `Circuit` plus a final `WirePerm`.
- No runtime feedback, looping, tracing, or higher-order execution.

---

## Phase 2 goal

Introduce **controlled parallel composition** (`TenTerm`) so programs can operate on sub-blocks (tensor factors) without rewriting everything into a single global term, while preserving all Phase 0–1 invariants.

---

## New feature: `TenTerm(f, g)`

### Meaning
`TenTerm(f, g)` represents parallel composition: **`f ⊗ g`**.

If
- `f : A → A'`
- `g : B → B'`

then
- `TenTerm(f, g) : (A ⊗ B) → (A' ⊗ B')`.

Types are inferred from sub-terms (as in the Phase 0–1 type checker).

### Offset semantics (the Phase 2 “core law”)

Let the input type of the `TenTerm` be `A ⊗ B`. Let:

- `nA = width(A)`  (number of qubit wires in the left block)
- `nB = width(B)`  (number of qubit wires in the right block)

Then compilation behaves as:

- compile the **left** branch `f` with `offset = 0`
- compile the **right** branch `g` with `offset = nA`

For any gate in a branch:

1. Start with the gate’s **local** wire indices (within that branch).
2. Add the branch **offset** to obtain a **global logical** index.
3. Rewrite through the **current `WirePerm`** using the fixed convention:
   - `physical = perm.apply_new_to_old(global_logical)`
4. Emit the pytket gate at `physical`.

Equivalently:

```
physical_index = perm.apply_new_to_old(local_index + offset)
```

### Ordering and determinism
- **Spec:** the compiler emits gates from the left branch first, then the right branch.
- This is pinned by tests.

### No new feedback / trace
- Phase 2 introduces no GOI feedback, no trace, no looping, no runtime recursion.
- TenTerm is purely **spatial** (parallel placement with offsets).

---

## Phase 2 invariants (added)

### Correct offsets
- Right-branch gates are shifted by exactly `width(A)` (before permutation rewrite).
- Left-branch gates are unshifted.

### Block locality
- Branch-local indices must be within the branch’s local width.
- Out-of-block indices must raise a loud error during compilation (or type checking).

### Structure remains metadata
- Structural terms inside a branch still compile only to `WirePerm` updates.
- TenTerm does not cause structural terms to materialize into SWAPs.

---

## Deferred in Phase 2 (explicitly out of scope)

- ~~Distributivity compilation (still deferred).~~ **Now implemented in Phase 4C.**
- Any trace/feedback operator (GOI feedback), fixpoint, or runtime iteration.
- Any change to the Phase 0–1 permutation convention.
- Any change to "no SWAPs by default."

---

## Definition of Done (Phase 2)

1. `TenTerm` exists in `lang.terms` and type-checks via `typing_.check`.
2. `compile.to_pytket.compile(...)` supports `TenTerm` using the offset semantics above.
3. All Phase 0–1 tests remain unchanged and pass.
4. New Phase 2 tests pass and lock:
   - offset convention
   - left-then-right emission order
   - determinism
   - no-SWAP-by-default remains absolute
   - materialization preserves non-SWAP gate order
5. Integration tests demonstrate Phases 0–2 end-to-end behavior.

---
