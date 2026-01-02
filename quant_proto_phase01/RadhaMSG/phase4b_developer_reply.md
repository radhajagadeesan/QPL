# Phase 4B — Developer Reply / Clarification

Thanks for the careful analysis — your concern is valid, and you are right about the **circuit-level limitation** of the current `pytket-pyzx` bridge. Residual `GOIArtifact`s are *not* circuits precisely because they may contain **feedback / compact structure**, so we should not attempt to route them through `tk_to_pyzx` or any circuit-based conversion.

Below is the clarified direction for Phase 4B, incorporating your points and tightening the success criterion to align with the GOI invariants.

---

## 1. Acknowledgement (you are right)

- The existing bridge utilities operate at the **Circuit** level.
- Residual GOIArtifacts can contain **loops / feedback** that are not circuit-representable.
- Therefore:
  - **Do not use `tk_to_pyzx` / `pyzx_to_tk` on residuals.**
  - **Do not assume residuals can be converted to circuits before normalization.**

This is correct and intentional.

---

## 2. Clarified Phase 4B MVP Direction (Agreed Plan)

We will proceed with a **conservative MVP** that is rollback-safe, deterministic, and respects the GOI firewall.

### Canonical approach (approved)

**Implement a direct translation:**

```
GOIArtifact  →  PyZX Graph  →  (deterministic structural rewrites)
                                    ↓
                           check extractability
                                    ↓
                        (Circuit, WirePerm)  OR  residual unchanged
```

Key points:

- PyZX graphs *can* represent non-circuit ZX structure (cups/caps, compact structure).
- Gates are represented as **opaque box vertices** with ordered ports.
- No reliance on PyZX circuit extraction or heuristic simplification.

This corresponds most closely to your **Option B**, with a clarified success criterion (see §4).

---

## 3. What Phase 4B Is Allowed to Do (and Not Do)

### Allowed
- Construct a PyZX graph directly from GOI structure:
  - boundaries (logical wire order preserved),
  - routing/permutation structure,
  - feedback via cups/caps or equivalent wiring,
  - opaque gate boxes as rewrite barriers.
- Apply **deterministic, structural-only rewrites**:
  - identity wire contraction,
  - cancellation of inverse routing,
  - canonicalization of boundary wiring,
  - elimination of *routing-only* cycles when provably gate-free.
- Extract a **flat circuit + explicit `WirePerm`** *only if* the structure collapses appropriately.

### Forbidden
- Running PyZX heuristic passes (`full_reduce`, `optimize`, etc.).
- Inspecting or rewriting inside gate atoms.
- Using PyZX’s circuit extraction unless it is proven to:
  - preserve boundary order,
  - be deterministic,
  - and respect gate opacity (for MVP, do not rely on it).

---

## 4. Critical Clarification: Success Criterion (GOI-aware)

The success condition for Phase 4B is **not merely “acyclic graph.”**

The correct condition is:

> After structural normalization, all feedback/cycle structure has collapsed into an **explicit boundary permutation**, and the remaining gate boxes form a DAG that can be deterministically linearized.

Equivalently:
- **Acyclic modulo boundary permutation**, yielding:
  ```
  (flat Circuit, WirePerm)
  ```

This mirrors the Phase 3/4A GOI checkpoint invariant:
> *“GOI routes; it does not compute.”*

Any residual cyclic structure that genuinely interacts with a gate must remain residual.

---

## 5. MVP Scope (Approved)

For the initial implementation:

- Single-loop and simple residuals are sufficient.
- No nested or higher-order compact structure required.
- Deterministic rewrite schedule only.
- Entire feature gated behind `enable_zx=False` (default off).
- Full Phase 0–4A regression suite must pass unchanged.

Your proposed conservative MVP is therefore **approved**, with the success criterion above.

---

## 6. Explicit Rollback Rule (Non-Negotiable)

At **any** failure point:
- translation failure,
- rewrite failure,
- ambiguity,
- extractability failure,

the function must return the **original residual GOIArtifact unchanged**.

No partial normalization may leak.

---

## 7. Summary (one paragraph)

You are correct that residuals cannot go through the circuit bridge. Phase 4B should therefore construct a PyZX graph directly from the GOIArtifact, run only deterministic structural rewrites, and succeed **only** when the structure collapses to a flat circuit plus an explicit boundary permutation. This is aligned with the GOI acyclicity invariant and keeps Phase 4B sound, rollback-safe, and strictly non-interfering with Phases 0–4A.

Thanks for flagging this — your instinct here was exactly right.

---

*End of developer clarification.*
