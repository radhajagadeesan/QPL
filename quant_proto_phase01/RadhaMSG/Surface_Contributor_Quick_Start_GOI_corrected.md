
# Surface Language Contributor Quick‑Start (GOI‑Corrected)

**Audience:** new contributors working on the surface language frontend  
**Goal:** productivity *without violating GOI or Phase 0–4C invariants*

---

## 0. Mental Model (Normative)

You are building a **frontend only**.

```
Surface syntax
  → elaboration (macro‑only)
  → existing core IR
  → locked Phase 0–4C pipeline
```

Nothing new may reach Phase 0–4C.

**All routing semantics live on the GOI boundary.**

---

## 1. Absolute Rules

- ❌ Do NOT modify Phase 0–4C
- ❌ Do NOT assume input→output semantics
- ❌ Do NOT assume Id compiles to identity
- ❌ Do NOT introduce coproducts, feedback, recursion, or runtime branching

- ✅ All constructs elaborate away
- ✅ Structural programs compile to **GOI boundary permutations**
- ✅ Certification is implicit via compilation

---

## 2. GOI Boundary Convention (Required)

For any morphism `f : A → B`, compilation produces a **permutation on a doubled boundary**.

- `id_A` compiles to the **through‑wire involution** `J_A`
- Involution means: `p ∘ p = id` **on the GOI boundary**
- Composition is performed by **boundary identification + feedback**, never substitution

If you are unsure where a permutation lives, stop and ask.

---

## 3. Structural vs Unitary

- **Structural**: compiles to `(WirePerm, optional global phase)`
- **Unitary**: may include opaque atoms

Structural ≠ syntactic: it is checked by the compiler.

---

## 4. Typical Workflow

1. Modify surface AST / elaboration only
2. Ensure all constructs elaborate to existing core IR
3. Add tests asserting:
   - compilation success
   - no residual GOI
   - no Phase 4B invocation
4. Submit PR using the engineering contract

---

## 5. Common Errors

- Treating `(+)` as a coproduct
- Treating `case` as runtime branching
- Assuming identity permutation
- Reasoning on outputs instead of GOI boundaries

---

## 6. Completion Criteria

Your work is done iff:
- all tests pass
- extraction succeeds
- you can explain why GOI invariants are preserved

When unsure, ask before coding.
