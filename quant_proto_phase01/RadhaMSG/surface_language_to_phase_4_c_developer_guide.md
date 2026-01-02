# Surface Language → Phase 4C Integration Guide (GOI‑Corrected)

**Audience:** senior developers
**Scope:** frontend integration only

---

## 0. Purpose

Add a certified surface language **without altering GOI semantics**.

---

## 1. GOI Semantic Model (Normative)

- Morphisms compile to **GOI boundary permutations**
- Identity `id_A` ↦ through‑wire involution `J_A`
- Composition uses feedback on shared boundaries
- All certification checks occur on GOI permutations

---

## 2. Surface Language Role

- Pure presentation layer
- All higher‑order constructs are macros
- `(+)` is monoidal, not coproduct

---

## 3. Datatypes and `case`

- Datatypes fix a canonical `(+)` representation
- `case` is compile‑time routing
- No runtime inspection or branching

---

## 4. Exponentials

`expᵢ(θ, J)` allowed iff:
- `J` is structural
- compiler certifies involution on GOI boundary

Elaborates to opaque unitary atom only.

---

## 5. Guarantees

Certified programs:
- always extract
- never invoke Phase 4B
- preserve GOI invariants

---

## 6. Non‑Goals

- No analytic normalization
- No semantic rewriting
- No GOI modification
