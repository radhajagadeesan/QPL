# Developer Guide (Phase 1)

This document is the authoritative guide for developers working on the
Phase 1 structural quantum compiler prototype.

Phase 1 is **complete in scope** once all tests pass. Further work
(e.g. `TenTerm`, distributivity compilation, higher-order constructs)
belongs to later phases.

---

## 1. What is being implemented (Phase 1 summary)

### Core research claim (validated incrementally)

> Every well-typed higher-order quantum program admits a static compilation
> to a first-order unitary circuit, where all apparent feedback is structural
> wiring (permutations), not operational looping.

Phase 1 implements the **structural backbone** needed to make this claim precise.

---

### What Phase 1 *does implement*

#### A. Shape-based typing
Located in:
```
src/lang/types.py
src/typing_/check.py
```

Types are **shape trees**:
- `Q`
- `Ten(A, B)`   (tensor ⊗)
- `Plus(A, B)`  (sum ⊕, structural only)

Typing enforces:
- arity correctness
- exact shape matching for `Seq`
- no implicit coercions

---

#### B. Structural AST (no operational meaning)
Located in:
```
src/lang/terms.py
```

Structural terms include:
- `Id`
- `Seq`
- tensor twists and associators
- sum twists and associators
- distributivity terms (typed but *not compiled*)

These terms **do not represent computation**.
They represent *rewiring only*.

---

#### C. Permutation-based wiring semantics
Located in:
```
src/core/perm.py
```

All structure compiles to **WirePerm**:
- permutations compose
- permutations invert
- permutations represent wiring, not gates

This is the *only* representation of structure in Phase 1.

---

#### D. Compilation to pytket (unitary, first-order)
Located in:
```
src/compile/to_pytket.py
```

Compilation maintains:
- a current `WirePerm`
- a pytket `Circuit`

Rules:
- structural terms update the permutation only
- gate terms emit pytket ops **reindexed through the current permutation**
- SWAPs are *never* emitted here

---

#### E. Optional SWAP materialization (debug only)
Located in:
```
src/backends/materialize.py
```

Purpose:
- visualize wiring
- debug structure
- make permutations explicit if desired

Invariant:
- materialization must not change the order or identity of non-SWAP gates

---

### What Phase 1 explicitly does *not* implement

These are **not bugs**:

- `TenTerm` (parallel composition with offsets)
- compilation of distributivity (`DistL`, `DistR`)
- any operational meaning of `Plus`
- higher-order execution / feedback / trace
- alternative IRs (`src/ir/` is reserved)

---

## 2. Test suite philosophy (very important)

The test suite is **contract-driven**.

Every test locks a semantic invariant that must survive refactors.

If a test fails, assume the compiler is wrong — not the test.

---

## 3. Test directory structure & naming

Tests live in a **flat, numbered layout**:

```
tests/
  test_00_*.py   Typing and shape foundations
  test_10_*.py   Permutation algebra
  test_11_*.py   Permutation convention lock
  test_20_*.py   Tensor (⊗) structural laws
  test_21_*.py   Sum (⊕) structural laws
  test_22_*.py   Distributivity deferred
  test_30_*.py   Gate emission (no structure)
  test_31_*.py   Gate emission under structure
  test_32_*.py   Determinism
  test_40_*.py   SWAP materialization
  test_50_*.py   End-to-end / randomized
```

The numbers encode the **compiler pipeline**.
Do not randomize or collapse them.

---

## 4. New Phase 1 tests (what they lock)

The newly added tests are **essential** Phase 1 guards.

### `test_11_perm_convention_lock.py`
Locks the **WirePerm direction convention**.

Why this matters:
- a silent inversion here misroutes all gates
- this is the most common refactor regression

Action required once:
- align expected values with your chosen convention
- then never change lightly

---

### `test_23_structure_no_swaps_regression.py`
Locks the invariant:

> Structure = metadata, not SWAP gates

If this fails, structural compilation has leaked into computation.

---

### `test_32_compile_determinism.py`
Ensures:
- compilation is deterministic
- no accidental dependence on dict/set iteration order

This protects CI and debugging sanity.

---

### `test_41_materialize_equivalence_small.py`
Ensures:
- materialization only *adds* SWAPs
- non-SWAP gates are identical and in the same order

This proves materialization is observational only.

---

## 5. Running tests (Windows 11)

PowerShell:

```powershell
$env:PYTHONPATH="src"
pytest -q
```

Optional deterministic override:

```powershell
$env:QPL_SEED="999"
pytest -q
```

---

## 6. Required invariants (non-negotiable)

All Phase 1 code must preserve:

1. Structural terms emit **no gates**
2. Compiler emits **no SWAPs by default**
3. Gates are reindexed through `WirePerm`
4. Compilation is deterministic
5. Distributivity fails loudly at compile time
6. Randomized tests pass with fixed seeds

If you violate one of these, add a new test or fix the code.

---

## 7. How to add new code safely

### Adding a new structural term
You must update:
- `lang/terms.py`
- `typing_/check.py`
- `compile/to_pytket.py` (permutation only)

You must add tests for:
- typing
- structural equality / permutation effect
- “no SWAPs” regression

---

### Adding a new gate
You must add tests for:
- basic emission
- emission under non-trivial structure
- determinism

---

## 8. Windows note (important)

Files like:
```
*.py:Zone.Identifier
```

are Windows “Mark of the Web” artifacts.
They should not be committed.

Recommended `.gitignore` entry:
```
*:Zone.Identifier
```

---

## 9. Phase boundary reminder

Phase 1 ends when:
- structure is fully permutation-based
- compilation always produces a flat unitary circuit
- tests fully lock invariants

The **next step** is `TenTerm` offsets.
Do not weaken Phase 1 invariants to implement it.

---

End of developer guide.
