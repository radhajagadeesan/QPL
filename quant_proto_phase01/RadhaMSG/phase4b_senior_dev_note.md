# Phase 4B Senior Developer Note — ZX Residual Post‑Pass (Option C: pytket ↔ PyZX bridge)

**Audience:** implementers and reviewers working on GOI extraction.  
**Status baseline:** Phases 0–4A are **locked**; Phase 4B is an **optional** completeness augmenter on **residuals only**.  
**Core constraint:** **Rollback-safe** and **non-interfering** with all Phase 0–4A outputs.

---

## 1. Goal and Non‑Goals

### Goal
Improve extraction completeness *without affecting soundness* by adding a deterministic ZX-based post-pass applied **only** to residual `GOIArtifact`s:

- Pipeline: `try_extract_v1` → `try_extract_v2` → **(if residual) `try_extract_zx`**.
- If `try_extract_zx` succeeds, return a flat `(Circuit, WirePerm)`.
- If it fails, return the **original residual GOIArtifact unchanged**.

### Non-goals
- No new syntax, no new gates (that is Phase 4C).
- No changes to Phase 0–4A extracted results or goldens.
- No “best-effort” partial rewrites: either extract, or leave residual untouched.

---

## 2. Locked Invariants (Phase 0–4A carry-through)

These are **hard requirements** for Phase 4B:

1. **Non-interference**
   - If v1 succeeds: return v1 output **bit-identical**.
   - Else if v2 succeeds: return v2 output **bit-identical**.
   - 4B runs only on v2 residuals.

2. **Firewall**
   - Never rewrite inside `GateAtom`s (or any gate representation).
   - ZX may treat gates as opaque **boxes** with a declared interface (arity + support/ports).
   - ZX rewrites must never inspect or alter gate internals or parameters.

3. **Determinism**
   - Same input residual ⇒ identical outcome (same extracted circuit/perm, or identical residual).
   - Rewrite order must be fixed; no nondeterministic “optimize” passes.

4. **SWAP policy**
   - `materialize=False` ⇒ zero SWAPs.
   - 4B must not materialize, introduce SWAPs, or lower to a backend.

5. **Distributivity**
   - `DistL/DistR` compile-time loud failures remain unchanged.

---

## 3. Option (C) Implementation Strategy

**Chosen approach:** remain “tket-native” at the boundaries while borrowing PyZX’s rewrite engine internally.

- Native representation: **`pytket.zx.ZXDiagram`**
- Internal rewrite engine: **PyZX graph** via `pytket.extensions.pyzx`
- Return path: back to `ZXDiagram`, then to your flat `(Circuit, WirePerm)` representation.

### Dependencies (already installed)
- `pytket`
- `pytket.zx`
- `pyzx`
- `pytket-pyzx` (`pytket.extensions.pyzx`)

---

## 4. Interfaces and Dataflow

### 4.1 Public interface

```python
def try_extract_zx(residual: GOIArtifact) -> ExtractResult:
    '''
    Input: residual GOIArtifact from try_extract_v2
    Output:
      - Extracted(Circuit, WirePerm) on success, OR
      - Residual(GOIArtifact) exactly equal to input residual on failure
    '''
```

**Hard rule:** `try_extract_zx` must be invoked only after `try_extract_v2` fails.

### 4.2 Canonical pipeline

1. **Eligibility filter (optional but recommended)**
   - Reject residuals containing unsupported constructs (e.g., explicit DistL/DistR should not reach here anyway).
   - Reject if translation would require inspecting gate internals.

2. **Translate residual → `ZXDiagram`**
3. **Convert `ZXDiagram` → PyZX graph**
4. **Deterministic rewrite schedule on PyZX graph**
5. **Convert PyZX graph → `ZXDiagram`**
6. **Try to extract flat circuit+perm from `ZXDiagram`**
7. **On failure at any stage:** return original residual unchanged.

---

## 5. ZX Translation Design

### 5.1 What structure is represented?
Phase 4B targets cases where extraction fails only due to **structural routing/cycle artifacts** and can be resolved by ZX normalization without touching gates.

**Represent:**
- Boundary wires (logical indices)
- Structural routing / permutations
- Feedback/cups/caps style connections **as wiring**
- Opaque gate boxes with ordered ports

**Do not represent:**
- Anything requiring gate decomposition
- Semantic commutations that depend on gate algebra

### 5.2 Opaque gate boxes
A gate is modeled as a ZX “box” node with:
- A stable identifier (for determinism/logging)
- Ordered input/output ports
- Optional annotation containing the GateAtom’s declared **support** (logical wires)

**Invariant:** Box nodes are **rewrite barriers**. No rule may fuse, rewrite, or move through the box except via purely structural wire relabeling that is already legal in Phase 4A (i.e., reindexing support under permutations).

---

## 6. Deterministic Rewrite Schedule (Critical)

### 6.1 Why a schedule (not “optimize”)?
Many ZX libraries provide powerful simplifiers which may be heuristic or order-dependent. Phase 4B requires:
- repeatable results,
- stable goldens,
- minimal “surprises.”

### 6.2 Allowed rewrite families (start conservative)
Only allow rules that simplify **pure structure**:
- Remove identity wires / trivial spiders
- Cancel adjacent inverse permutations / swaps (structural)
- Normalize wire ordering to a canonical boundary order
- Remove “routing-only” cycles when provably gate-free

**Forbidden:**
- Any rule that would cross or rewrite inside an opaque gate box
- Any phase-based simplification that reasons about gate semantics

### 6.3 Pseudo algorithm for deterministic rewriting

```text
normalize_zx_deterministic(graph):
  # Canonicalize node ordering (stable iteration)
  graph = canonicalize(graph)

  repeat until fixpoint:
    changed = False

    # Pass 1: purely local cleanups (in fixed priority)
    changed |= apply_rule_R1_remove_identities(graph)
    changed |= apply_rule_R2_cancel_inverse_swaps(graph)
    changed |= apply_rule_R3_contract_trivial_spiders(graph)

    # Pass 2: routing normalization (canonical boundary order)
    changed |= apply_rule_R4_normalize_boundary_permutation(graph)

    # Pass 3: routing-only cycle elimination (guarded)
    if detect_routing_only_cycle(graph) and cycle_is_gate_free(graph):
        changed |= eliminate_cycle(graph)

    if not changed:
        break

  return graph
```

**Notes:**
- Each rule must iterate nodes/edges in a stable, sorted order.
- `cycle_is_gate_free` must treat gate boxes as obstacles.
- If any rule cannot prove safety, it must not fire.

---

## 7. Success Criterion: “Flat + Boundary Perm”

After normalization, attempt extraction under a strict predicate:

### 7.1 Flatness predicate (conceptual)
A normalized diagram is extractable iff:
- The underlying connectivity can be linearized into:
  - a sequence of opaque gate boxes (acyclic), plus
  - an explicit final boundary permutation (`WirePerm`)
- No feedback/cups/caps remain except as part of the final permutation wiring.

### 7.2 Pseudo extraction from ZX

```text
try_extract_from_zx(diagram):
  # 1) Verify no structural cycles remain (excluding final perm wiring)
  if has_feedback_like_wiring(diagram):
      fail

  # 2) Topologically order opaque gate boxes deterministically
  boxes = topo_sort_boxes(diagram, tie_break=stable_id)

  # 3) Compute boundary permutation induced by remaining wires
  perm = compute_boundary_perm(diagram)

  # 4) Emit flat Circuit in that order, with logical wires
  circ = Circuit(boxes_in_order, logical_wires=True)

  return (circ, perm)
```

**Hard rule:** if any step is ambiguous (multiple valid topo orders), tie-break deterministically.

---

## 8. Error Handling & Rollback Safety

### 8.1 Rollback policy
Any of these conditions must return the **original residual** unchanged:
- translation failure
- rewrite failure/exception
- failure to meet flatness predicate
- extraction failure
- detected nondeterminism (e.g., unstable rewrite outcome across runs in a debug check)

### 8.2 Debug logging (deterministic)
- Log only stable facts: counts, rule applications, stable IDs
- Never log memory addresses or unordered sets
- Suggested fields:
  - residual hash / structural digest
  - translation success/failure reason
  - rewrite pass counts
  - extraction success/failure reason

---

## 9. Integration Points

### 9.1 Compiler pipeline
- `compile_ast(...)` or equivalent should remain unchanged until:
  - v1 + v2 complete
  - residual exists
  - optional flag `enable_zx=True` is set (default **False** initially)

### 9.2 Configuration
Add a flag in your public compile API:

- `enable_zx: bool = False`
- Possibly `zx_level: int = 0..N` (future), but MVP should be a single conservative mode.

---

## 10. Test Plan Outline (Comprehensive)

### 10.1 Regression lock (must pass first)
Re-run **all existing** Phase 0–4A integration tests and goldens:
- Assert bit-identical outputs (command stream, circuit serialization, perms).
- This is the primary guardrail against non-interference regressions.

### 10.2 Phase 4B positive corpus (new goldens)
Cases that are:
- v1 fails → v2 fails → residual remains
- ZX pass succeeds
- Output becomes flat `(Circuit, WirePerm)`

**Test shape categories:**
1. **Routing-only feedback artifacts**
   - feedback exists but gates provably not on loop wires *after* structural normalization
2. **Permutation cancellations across residual boundaries**
3. **Nested routing normalizations**
   - multiple routing layers that obscure the gate-free loop property

Each should have:
- input program/AST
- expected extracted circuit + perm (new golden)
- determinism rerun assertion

### 10.3 Phase 4B negative corpus (must remain residual)
Cases that should remain residual after 4B:
1. **Genuine gate–feedback interaction**
   - a gate box touches loop wires in an unavoidable way
2. **Ambiguous/non-canonical structure**
   - where extraction would require semantic gate reasoning
3. **ZX-unsupported residual constructs** (if any)

For each:
- assert output is residual and structurally equal to v2 residual
- assert no partial changes (exact residual unchanged)

### 10.4 Determinism tests (explicit)
For representative cases in each corpus:
- run compile/extract twice
- compare serialized output hashes:
  - extracted: hash(circuit) + hash(perm)
  - residual: hash(residual)

### 10.5 SWAP policy checks
- Ensure `materialize=False` yields zero swaps even after 4B success.
- Ensure 4B does not call materialization/lowering code paths.

### 10.6 Firewall tests
Add “canary” gate atoms (or instrumentation) to ensure:
- no rewrite calls inspect gate internals
- only the declared interface/support is used

### 10.7 Backend sanity (post-extraction only)
For 4B-success cases:
- lower to pytket circuit (without materialization) and validate:
  - unitary-only ops
  - wire count matches
  - serialization stable

---

## 11. Suggested File/Module Layout

Example (adjust to your repo conventions):

- `src/compile/extract_zx.py`
  - `try_extract_zx`
  - `to_zxdiagram(residual)`
  - `zxdiagram_to_pyzx / pyzx_to_zxdiagram` bridge helpers
  - `normalize_zx_deterministic`
  - `try_extract_from_zxdiagram`

- `tests/integration/test_phase4b_regression_goldens.py`
- `tests/integration/test_phase4b_positive_goldens.py`
- `tests/integration/test_phase4b_negative_residuals.py`
- `tests/integration/test_phase4b_determinism.py`
- `tests/integration/test_phase4b_firewall.py`
- `tests/integration/test_phase4b_swap_policy.py`

---

## 12. Implementation Checklist (MVP → Hardened)

### MVP (ship behind flag)
- Translation supports a conservative subset
- Deterministic rewrite schedule with 3–5 local structural rules
- Flatness predicate + extraction
- Full regression lock + small positive/negative corpus

### Hardened
- Expand eligible residual fragment (still structural-only)
- Add more guarded structural cycle eliminations
- Improve canonicalization and stable hashing for diagrams
- Broaden the positive corpus with real-world residuals

---

## 13. Review Notes / Things That Commonly Go Wrong

1. **Accidental non-determinism**
   - Iterating over dict/set without sorting
   - Library “simplify” passes with heuristic ordering
2. **Leaking interference**
   - Running 4B on v2 successes (must not happen)
   - Mutating residual in place when intending rollback safety
3. **Firewall violations**
   - “Convenient” decompositions of gate boxes to enable ZX rules
4. **Unstable tie-breaks**
   - Topological order ambiguity without deterministic tie-breaking
5. **Boundary ordering drift**
   - Must preserve logical wire indexing through translation and back

---

## 14. Minimal Pseudocode Skeleton (end-to-end)

```text
def extract_with_phase4b(goi):
  r1 = try_extract_v1(goi)
  if r1.is_extracted(): return r1   # bit-identical

  r2 = try_extract_v2(r1.residual)
  if r2.is_extracted(): return r2   # bit-identical

  if not enable_zx: return r2       # residual

  return try_extract_zx(r2.residual)

def try_extract_zx(residual):
  zx = to_zxdiagram(residual)
  if fail: return residual

  g = zxdiagram_to_pyzx(zx)
  if fail: return residual

  g2 = normalize_zx_deterministic(g)
  if fail: return residual

  zx2 = pyzx_to_zxdiagram(g2)
  if fail: return residual

  extracted = try_extract_from_zxdiagram(zx2)
  if fail: return residual

  return extracted  # (Circuit, WirePerm)
```

---

## Appendix: What “staying in tket land” means here
- **Inputs/outputs** remain your compiler’s native GOI/Circuit/WirePerm types.
- The ZX intermezzo uses **tket-native** `ZXDiagram` and an **official** bridge to PyZX.
- Backend lowering to pytket circuits remains unchanged and is only applied post-extraction, exactly as in Phases 0–4A.
