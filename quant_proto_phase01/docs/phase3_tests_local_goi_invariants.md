# Phase 3 Test Plan (A): Local GOI Invariants
**Purpose:** Comprehensive tests that validate Phase 3’s *local* GOI invariants: explicit feedback fencing, routing-only semantics on successful extraction, sound (incomplete) extraction, determinism, and the normalization firewall.

**Scope:** These tests target Phase 3 components in isolation:
- GOI IR construction (GOIArtifact)
- normalization (`normalize_goi`)
- yankability check (`is_yankable`)
- collapse (`collapse_feedback`)
- extraction (`try_extract`)
- Phase-3 entrypoint (`compile_goi`) *only as far as it produces residual vs extracted, without requiring full end-to-end equivalence to Phase 0–2 (covered in plan B).*

> **Non-goal:** Proving completeness. All tests assume *sound-only* behavior.

---

## A0. Conventions and Harness

### A0.1 File layout
Recommend:
- `tests/test_phase3_local_invariants.py`
- `tests/test_phase3_normalization_firewall.py`
- `tests/test_phase3_feedback_elimination.py`
- `tests/test_phase3_residual_preservation.py`

### A0.2 Assertions utilities
Create tiny helpers in `tests/utils_goi.py`:

- `assert_no_swaps(circ)`
- `assert_atoms_equal(a1, a2)` (gate type & params identical; wire indices may differ)
- `assert_same_cmd_stream(c1, c2)` (stable textual rendering)
- `extract_cmd_stream(circ) -> List[str]` (deterministic text)
- `assert_perm_eq(p, q)`
- `gate_support(atom) -> set[int]` (its wires)

### A0.3 Deterministic command stream rendering
A single canonical rendering (string list) is essential for determinism checks:
- gate name
- parameters (if any)
- wire tuple
- in exact emission order

---

## A1. Feedback Fencing and “No Implicit GOI”
### A1.1 No cycles unless `Feedback`
**Test:** compile a term with only Phase 0–2 constructs; ensure `compile_goi(term)` contains **no loops** in residual form, and if extracted, still no loops.
- **Expected:** `ResidualGOI.loops == []` or extracted artifact.

### A1.2 Feedback produces explicit loop metadata
**Test:** `compile_goi(Feedback_k(body))` returns residual or extracted, but intermediate GOI artifact must include a `LoopSpec(k)` during extraction attempt.
- **Expected:** If extraction fails → returned ResidualGOI has `loops != []`.
- **Expected:** If extraction succeeds → extracted; and *no* residual loop remains.

---

## A2. Normalization Firewall (Structural rewrites do not enter atoms)
### A2.1 Atom identity preserved
Construct a GOIArtifact:
- `perm = nontrivial` (e.g., swap wires 0 and 1)
- `atoms = [H@0, CX@(0,2), S@1]`
Run `normalize_goi`.
- **Expected:**
  - same atom *types* in same order: `[H, CX, S]`
  - only wire indices changed by `perm.apply_new_to_old`
  - resulting `perm == identity`

### A2.2 “Opaque atom” property
Introduce a fake “analytic exponential” atom (or use any parametrized gate) and ensure normalization:
- does not alter its parameters or gate name
- only rewrites its wire indices
- order unchanged

---

## A3. Yankability (Eliminability) Check
### A3.1 Yankable when loop wires are untouched
Build residual artifact:
- `n_out = 6`
- loop `k = 2` ⇒ loop wires `{4,5}`
- atoms touch only `{0,1,2,3}`
- **Expected:** `is_yankable(goi) == True`

### A3.2 Not yankable when any atom touches a loop wire
Same, but add `H@5`.
- **Expected:** `is_yankable(goi) == False`

### A3.3 Multiwire gates intersecting loop
Add `CX@(3,4)` where 4 is in loop.
- **Expected:** not yankable

### A3.4 Multiple loops (if supported)
If implementation allows multiple loops, verify:
- yankability fails if any loop wire set is touched
- yankability succeeds only if all loop wire sets are untouched

---

## A4. Feedback Collapse: “Routes, does not compute”
### A4.1 Collapse preserves atoms and returns boundary perm only
Given a yankable GOIArtifact with nontrivial routing perm and loop `k>0`:
- run `try_extract`
- **Expected:**
  - extracted atoms equal (same gate list, same order, same params)
  - returned `WirePerm` equals induced boundary routing
  - loop is removed (no residual)

### A4.2 Collapse depends only on routing when yankable
Create two GOIArtifacts identical except for atom list that touches no loop wires.
- **Expected:** resulting boundary permutation is identical in both extractions.

---

## A5. Residual Preservation (Failure is not error)
### A5.1 Extraction failure returns ResidualGOI, unchanged
Create artifact with gate touching loop wire.
- **Expected:** `try_extract(goi)` returns ResidualGOI
- **Expected:** residual contains:
  - same atoms (including the loop-touching one)
  - same loop spec
  - sufficient routing information to attempt later ZX refinement

### A5.2 No accidental materialization in residual path
Call `compile_goi(term, materialize=True)` where extraction fails.
- **Expected:** returns ResidualGOI (no SWAPs inserted, since not a circuit)

---

## A6. Determinism of Phase 3 Operations
### A6.1 normalize_goi deterministic
Run normalize twice; compare serialized GOIArtifact representation.
- **Expected:** identical

### A6.2 try_extract deterministic
Run try_extract twice; compare outputs (command stream + perm, or residual serialization).
- **Expected:** identical

### A6.3 compile_goi deterministic (Phase 3-only)
Run `compile_goi` twice on same AST; compare outputs.
- **Expected:** identical

---

## A7. Interactions with Phase 2 `TenTerm` (Local)
### A7.1 Offsets applied before permutation rewrite (still true)
Construct a term where:
- left branch has a gate at logical wire 0
- right branch has a gate at its logical wire 0 but offset to `nA`
- add structural permutation after TenTerm
- In GOI compilation, verify rewritten physical indices reflect:
  1) offset
  2) then perm.apply_new_to_old
- **Expected:** stable, deterministic, left-emitted before right-emitted

---

## A8. Distributivity (Now Implemented in Phase 4C)
### A8.1 DistL/DistR compile successfully
- **Expected:** Both `compile` and `compile_goi` handle distributivity correctly with tagged layout model.
- DistL is identity on wires; DistR moves tag to front.
- Both are structural (no gates).

---

## A9. Materialization semantics preserved
### A9.1 Extracted + materialize=False produces no SWAPs
For a yankable term that extracts:
- `compile_goi(..., materialize=False)` returns extracted with no SWAPs.

### A9.2 Extracted + materialize=True may insert SWAPs (only then)
- Verify SWAP insertion happens only when requested and only in extracted branch.

---

## A10. Suggested Minimal Fixture Terms
(Use actual constructors from the codebase; names below are conceptual.)

- `Gate(H, i)` / `Gate(CX, i, j)` etc.
- `Seq(f, g)` / `TenTerm(f,g)`
- `Struct(Swap/Assoc/...)` producing perms
- `Feedback_k(body)` new Phase 3 construct

---

## A11. Acceptance Criteria for (A)
Phase 3 is locally correct when:
- firewall holds (atoms opaque)
- no implicit loops exist
- extraction succeeds iff yankability holds (sound)
- extraction failure preserves residual GOI
- determinism holds for all Phase 3 passes
- Phase 2 offset/permutation rewrite ordering still holds
- distributivity compiles correctly (Phase 4C tagged layout)
- SWAP policy unchanged
