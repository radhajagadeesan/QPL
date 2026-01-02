
# End-to-End Test Suite — Surface → Phase 0 (GOI-Corrected)

**Audience:** developers validating the surface frontend and its integration with the locked Phase 0–4C pipeline  
**Status:** normative for surface-language work  
**Purpose:** lock down correct behavior from **surface programs** through **Phase 0 compilation**, using the **GOI boundary semantics**.

This document is implementation-facing and assumes:

- Phases 0–4C are **locked**
- The surface language elaborates to **existing core IR only**
- Certification is **implicit** and occurs at `expᵢ(…)`
- All routing semantics live on the **GOI boundary**, not on raw outputs

Any test that assumes “Id compiles to the identity permutation” is **incorrect**.

---

## 0. What “End-to-End” Means (GOI Interpretation)

“End-to-end starting at surface level down through Phase 0” means:

1. Surface source is accepted/rejected correctly (syntax + surface typing).
2. Elaboration removes *all* surface constructs.
3. Phase 0 compilation produces:
   - a circuit fragment (possibly empty)
   - a **GOI boundary permutation** (`WirePerm`)
4. The following **GOI invariants** are asserted:

- Determinism of compilation
- Structural programs compile to **GOI boundary permutations only**
- `id_A` compiles to the **through-wire involution** `J_A`
- Composition is realized by **boundary identification + feedback**
- `materialize=False` introduces no swaps
- Certified programs never yield residual GOI
- `expᵢ` rejects non-involutive GOI permutations

Later phases may run, but these tests lock the **surface → Phase 0 plumbing**.

---

## 1. Test Harness Layout

### 1.1 Repository Structure

```
tests/
  surface/
    test_surface_parse.py
    test_surface_typing.py
    test_surface_elaboration.py
    goldens/
      *.surf
      *.expect.json
  e2e/
    test_e2e_phase0.py
    test_e2e_determinism.py
    test_e2e_materialize_flag.py
    test_e2e_certification.py
    goldens/
      *.cmds.txt
      *.perm.json
      *.stderr.txt
```

### 1.2 Required Helpers

All helpers must reflect GOI semantics:

- `compile_surface(src, materialize=False)`  
  → `(circuit, perm)` where `perm` is a **GOI boundary permutation**
- `perm_ser(perm)`  
  → canonical serialization of the GOI permutation
- `canonicalize(circuit)`  
  → stable command stream

No helper may reason “on outputs only”.

---

## 2. Golden File Policy (GOI-Safe)

Each end-to-end test stores:

- canonical command stream (`*.cmds.txt`)
- GOI permutation serialization (`*.perm.json`)

Golden updates are allowed **only** when the surface frontend changes.

Phase 0–4C changes must **never** require golden updates.

---

## 3. Surface-Level Tests

### 3.1 Parsing

Tests ensure:
- stable error messages
- no leakage of core IR terminology

### 3.2 Datatype Well-Formedness

Enforce:
- finite datatypes
- non-recursive
- explicit payload structure

No coproduct semantics permitted.

### 3.3 Surface Classification (`s / u / invol`)

Surface checks are **preconditions only**.
All semantic classification is validated by compilation.

---

## 4. Elaboration Tests

### 4.1 Elaboration Completeness

After elaboration, assert:
- no `datatype`
- no `case`
- no `λ`
- only existing core IR nodes

### 4.2 Determinism of Elaboration

Elaboration must produce:
- identical core IR (up to α-equivalence)
- stable `(+)` and `⊗` tree orderings

---

## 5. Phase 0 Compilation Tests (GOI-Critical)

### 5.1 Structural → GOI Permutation

For structural programs compiled with `materialize=False`:

- circuit must be empty
- output must be a `WirePerm`
- permutation acts on a **doubled GOI boundary**

Test cases must include:
- `id_A` → permutation equals `J_A`
- associators and symmetries
- distributors `DistL`, `DistR`
- compositions of the above

### 5.2 `materialize=False`

Assert:
- no SWAPs introduced
- no administrative routing gates

This is checked on the **command stream**, not inferred.

---

## 6. Determinism Tests

For each golden example:

- run compilation twice
- compare:
  - command stream (byte-for-byte)
  - GOI permutation serialization

Any difference is a failure.

---

## 7. Certification Tests (`expᵢ`)

### 7.1 Involution Acceptance

Provide `J : A → A` such that:

- compilation yields GOI permutation `p`
- `p ∘ p = id` on the GOI boundary

Assert:
- `expᵢ(θ, J)` compiles
- exactly one exponential atom emitted
- GOI permutation is unchanged

### 7.2 Involution Rejection

Provide `J : A → A` such that:

- `p ∘ p ≠ id`

Assert:
- `expᵢ` fails
- error message identifies involution failure
- failure occurs *before* any backend invocation

---

## 8. “No Residual GOI” / “No Phase 4B”

For every certified surface program:

- run the full pipeline
- assert:
  - extraction succeeds
  - no residual GOI artifact
  - Phase 4B is never invoked

This is mandatory despite being beyond Phase 0,
because certification guarantees depend on it.

---

## 9. Canonical Example Suite

### Structural
- `id.surf` (checks `id_A ↦ J_A`)
- `twist_plus.surf`
- `assoc_plus.surf`
- `twist_ten.surf`
- `distL.surf`, `distR.surf`
- `combo_structural.surf`

### Certification
- `exp_i_good.surf`
- `exp_i_bad.surf`

### Unitary Smoke Tests
- declared atoms
- small algorithmic snippets (compile + extract only)

---

## 10. Acceptance Criteria

The surface system is correct iff:

- all surface tests pass
- elaboration removes all surface constructs
- Phase 0 compilation yields GOI-correct artifacts
- structural programs compile to `WirePerm` only
- `id_A` compiles to `J_A`
- determinism holds
- `expᵢ` certification is semantic and correct
- certified programs never yield residual GOI

Any failure is a regression.
