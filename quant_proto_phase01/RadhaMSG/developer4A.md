# developer.md — Integrating Phase 4A (Extraction++) into the Extractor Pipeline

This note explains how to plug **Phase 4A** into the existing **Phase 0–3** compiler/extractor pipeline **without changing** any Phase 0–3 observable behavior.

Phase 4A is **strictly additive**:
- It must not change any Phase 3 success/failure boundary or output.
- It only attempts additional extraction when Phase 3 returns a **residual GOIArtifact**.

---

## 0. Ground Rules (Do Not Violate)

These are the practical “integration” restatements of the locked invariants:

- **Phase 3 is the spec** for any case it extracts.
- **Never rewrite inside gate atoms.** Phase 4A may only re-associate / normalize routing and reindex gate *attachments*.
- **No SWAPs unless materialize=True**.
- **Residual GOI never materializes.** If v2 cannot extract, return residual GOIArtifact.
- **Deterministic outputs**: same AST → byte-identical:
  - command stream + final `WirePerm`, or
  - residual GOIArtifact serialization.

---

## 1. Where Phase 4A Fits

### Existing structure (conceptual)
Most codebases in this project follow a split like:

- `compile(ast, materialize=False) -> (Circuit, WirePerm) | GOIArtifact`
- Phase 3 provides:
  - `normalize(goi) -> goi'`
  - `try_extract_v1(goi') -> ExtractResult` where:
    - `Extracted(Circuit, WirePerm)` or
    - `Residual(GOIArtifact)`

### Phase 4A insertion point
Add a new extractor **after** Phase 3:

```
try_extract_v2(goi):
    r1 = try_extract_v1(goi)
    if r1 is Extracted: return r1  # bit-for-bit identical
    goi2 = normalize_routing_v2(r1.residual)
    r2 = extract_with_feedback_analysis(goi2)  # may succeed or remain residual
    return r2
```

**Important:** `try_extract_v2` must never pre-normalize in a way that changes Phase 3 outputs. It must call v1 first.

---

## 2. Minimal API Additions

### 2.1 New function
Create a module and function:

- `compile/goi/extract_v2.py`
  - `try_extract_v2(goi: GOIArtifact) -> ExtractResult`

### 2.2 Optional helper modules
- `compile/goi/routing_nf2.py`
  - `normalize_routing_v2(goi: GOIArtifact) -> GOIArtifact`
- `compile/goi/loop_analysis.py`
  - `analyze_feedback_eliminable(node: FeedbackNode) -> ExternalizeWitness | None`
  - `apply_witness(node: FeedbackNode, w: ExternalizeWitness) -> GOIArtifact` (routing-only rewrite)

### 2.3 Result type compatibility
Do **not** change the public result type. Reuse Phase 3’s `ExtractResult` variants.

If Phase 3 uses something like:
- `Extracted(circ, perm)`
- `Residual(goi)`

then Phase 4A returns the same.

---

## 3. Wiring Changes in the Compiler

### 3.1 Compile pipeline hook
Wherever Phase 3 currently does:

```
goi = lower_to_goi(ast)
goi = normalize(goi)
res = try_extract_v1(goi)
return res
```

change to:

```
goi = lower_to_goi(ast)
goi = normalize(goi)              # Phase 3 normalization (existing)
res = try_extract_v2(goi)         # NEW: v2 delegates to v1 first
return res
```

No other ordering changes.

### 3.2 Materialization stays downstream
Do not move or duplicate the materialization pass. Keep:

- `materialize=False` ⇒ circuit contains no swaps; routing is expressed only via `WirePerm`.
- `materialize=True` ⇒ explicit swap insertion occurs *only if the extracted artifact is flat*.

If compilation currently does:

```
if materialize:
    circuit = insert_swaps(circuit, perm)
    perm = identity
```

keep that logic unchanged and ensure it is called only when extraction is `Extracted`.

---

## 4. Determinism: How to Keep It Bulletproof

### 4.1 Canonical traversal
When v2 walks a GOIArtifact:
- Use a fixed traversal (e.g., preorder).
- Use stable node IDs or stable structural ordering.
- Never iterate over hash-map iteration order.

### 4.2 Rule priority
If multiple rewrites/witnesses apply, choose deterministically:
- fixed priority list (A > B > C > D, as in the design doc),
- tie-break lexicographically on (node_id, wire_index, etc.).

### 4.3 Canonical routing NF
`normalize_routing_v2` must be deterministic and should:
- eliminate `Id`,
- cancel `P ; P^{-1}`,
- reassociate routing composition to a canonical bracketing,
- **not** cross gate boundaries unless via gate-support reindexing (no atom inspection).

---

## 5. What Phase 4A is Allowed to Change

Only **residual** GOIArtifacts (returned from v1) may be transformed, and only via:
- routing algebra normalization,
- gate attachment reindexing under `WirePerm` commutation,
- routing-only cut elimination around feedback boundaries.

It may change the **representation** of the residual, but must remain deterministic.
(Tests should pin residual serialization where relevant.)

---

## 6. Test Integration Checklist

### 6.1 Absolute requirement: Phase 0–3 goldens unchanged
Add/keep a regression test target that:
- runs the full existing golden suite,
- asserts byte-identical outputs.

This should be the first CI step for Phase 4A.

### 6.2 New Phase 4A goldens
Add a new directory, e.g.:

- `tests/goldens/phase4a_extracts_more/`

Each case must assert:
- v1 result is residual,
- v2 result is extracted,
- `materialize=False` yields zero swaps and only unitary pytket gates,
- final `WirePerm` matches expected.

### 6.3 Negative cases
Add explicit cases that must remain residual under v2:
- gates truly touching loop wires,
- ambiguous cases where disjointness is not certified,
- cases that would require rewriting inside atoms.

---

## 7. Logging / Debugging (Recommended)

Add debug flags that can be enabled in tests/dev mode:
- emit witness summaries:
  - which feedback node was unlocked,
  - which rule fired,
  - what loop wire set was certified,
  - which permutations were used for externalization.

Do not enable this in production output streams; keep it behind a flag.

---

## 8. Common Integration Pitfalls

- **Running routing_nf2 before v1**: can change Phase 3 outputs → forbidden.
- **Materializing residual artifacts**: violates invariant.
- **Commuting across gates without reindexing support**: changes semantics.
- **Using non-deterministic data structures**: breaks determinism.
- **Accidentally introducing SWAP commands** in the extracted circuit: violates SWAP policy.

---

## 9. “Done” Criteria (for PR acceptance)

A Phase 4A integration PR is acceptable iff:
- All Phase 0–3 golden tests remain identical.
- New Phase 4A tests demonstrate extraction on a strict superset.
- No new compile-time failures are introduced (except existing DistL/DistR loud failures).
- Determinism tests pass (repeat compile yields identical outputs).
- `materialize=False` emits zero swaps on all extracted cases.

---

## Appendix: Reference Pseudocode

```python
def try_extract_v2(goi):
    r1 = try_extract_v1(goi)
    if r1.is_extracted():
        return r1  # exact Phase 3 behavior

    g = r1.residual()
    g = normalize_routing_v2(g)

    # Walk feedback nodes deterministically
    for fb in feedback_nodes_in_canonical_order(g):
        if phase3_yankable(fb):
            g = yank_feedback(g, fb)
            continue

        w = analyze_feedback_eliminable(fb)
        if w is not None:
            g = apply_witness(g, fb, w)
            # After witness rewrite, Phase 3 should handle the yank
            if phase3_yankable(fb):
                g = yank_feedback(g, fb)

    # Final attempt: if feedback-free, flatten; else residual
    return flatten_if_feedback_free_else_residual(g)
```

This is only a shape guide; keep your existing Phase 3 extraction as the authoritative implementation.
