# Certification Model and `exp_i` Behavior

**Audience:** surface language and compiler frontend developers  
**Status:** normative clarification

This document clarifies the **intended certification workflow** and the precise behavior of `exp_i`.

---

## 1. Core Intention (Short Answer)

**Certification is implicit at admissibility boundaries.**

In particular:

- `exp_i(theta, J)` **automatically triggers certification** of `J`.
- There is **no separate certification step required** from users.
- If certification fails, `exp_i` fails immediately with a precise error.

This keeps the surface language usable while preserving all Phase 0–4C invariants.

---

## 2. User-Facing Model

From the user’s perspective:

```ml
exp_i(theta, J)
```

means:

> “Construct the exponential of the involutive structural program `J`.”

Users do **not**:
- manually certify `J`
- run a separate command
- think about permutations or GOI artifacts

If `J` is not admissible, the program is simply rejected at the `exp_i` site.

---

## 3. Why Certification Lives Inside `exp_i`

This design choice:

- avoids a two-phase programming model
- matches the theory: admissibility is checked exactly at Δ-primitives
- minimizes redundant compilation work
- keeps Phase 0–4C as the *single source of truth*

Certification is therefore **not a global pass** and **not user-invoked by default**.

---

## 4. Frontend / Backend Responsibility Split

### 4.1 OCaml Frontend Responsibilities

The OCaml surface frontend must:

- ensure `J` has type `A → A`
- ensure `J` is syntactically structural (no unitary atoms, no feedback)
- emit Python code that *requests certification* of `J`

The frontend does **not** attempt to prove involution itself.

---

### 4.2 Python Backend Responsibilities (No Compiler Changes)

The Python side provides a small wrapper API, implemented using existing code:

```python
def certify_invol(term):
    circuit, perm = compile(term, materialize=False)
    if not perm.compose(perm).is_identity():
        raise CertificationError("not involutive")
    return canonical_id(perm)
```

This function:

- uses the **existing compiler**
- checks the semantic condition `p ∘ p = id`
- returns a stable identifier for use by `exp_i`

No new compiler logic is introduced.

---

## 5. Construction of `exp_i`

Once certification succeeds:

1. `certify_invol(J)` returns a canonical identifier (derived from `WirePerm`).
2. `exp_i(theta, J)` emits:
   - a fresh opaque Phase-4C exponential atom
   - parameterized by `theta` and the canonical identifier
3. The inverse atom is registered automatically as `exp_i(-theta, J)`.

No rewriting or propagation occurs.

---

## 6. Error Behavior

If certification fails:

- compilation stops immediately
- the error is attributed to the `exp_i(...)` site
- the error message should include:
  - that `J` is not involutive
  - the arity/support of the permutation
  - (optionally) a short summary of the permutation behavior

This ensures errors are actionable and local.

---

## 7. Optional Explicit Certification API

For developers and tests only, the following helpers may be exposed:

- `certify_struct(f)` — checks that `f` compiles to `WirePerm`
- `certify_invol(J)` — checks involution and returns canonical ID

These are **not required** for writing surface programs.

---

## 8. Summary (Contract)

- Certification is **implicit**, not a separate user step.
- `exp_i` is the **certification boundary**.
- Python performs the definitive semantic check using the locked compiler.
- This design preserves usability, soundness, and determinism.

Any alternative model (e.g. manual certification passes) is out of scope.
