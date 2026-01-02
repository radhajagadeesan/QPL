# Surface Engineering Contract & PR Template (GOI‑Corrected)

**Status:** Normative and binding

---

## A. Locked Invariants

- Phase 0–4C semantics are immutable
- GOI boundary conventions are authoritative
- Identity compiles to `J_A`, not literal identity
- Certification occurs on GOI boundary permutations

Any PR violating these is invalid.

---

## B. Semantic Target

- SMCC with tensor `⊗`
- Monoidal `(+)` (no coproduct UP)
- GOI‑based compilation and certification
- Opaque unitary atoms (Phase 4C)

---

## C. Structural Definition (Authoritative)

A term is **structural** iff compilation yields:

```
(WirePerm p on GOI boundary, optional phase)
```

No other definition is permitted.

---

## D. Involution Certification

A term `J : A → A` is involutive iff:

- it is structural
- compiler returns permutation `p`
- `p ∘ p = id` on the GOI boundary

Syntactic checks are forbidden.

---

## E. PR Checklist (Required)

- [ ] Only surface frontend modified
- [ ] No Phase 0–4C code touched
- [ ] No coproduct semantics
- [ ] No runtime branching or feedback
- [ ] Identity handled as `J_A`
- [ ] Certification via compiler output
- [ ] Tests assert GOI‑correct behavior

Reviewer must explicitly approve.
