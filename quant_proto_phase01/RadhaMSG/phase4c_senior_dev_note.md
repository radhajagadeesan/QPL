# Phase 4C Senior Developer Note — Primitive Unitary Atoms (with 4D as Explicit Non‑Goal)

**Audience:** compiler / extraction implementers  
**Status baseline:** Phases 0–4B are complete and test‑locked.  
**Purpose of Phase 4C:** admit *new primitive unitary gate atoms* (including parameterized exponentials) into the language and compilation pipeline **without changing extraction soundness or normalization behavior**.

---

## 1. Scope and Intent

### 1.1 What Phase 4C does
Phase 4C introduces **additional primitive unitary gate atoms** into the system:
- including *parameterized* unitaries (e.g. exponentials),
- treated as **opaque atoms** by all normalization and extraction logic,
- lowered deterministically to pytket at the backend.

Phase 4C is a **semantic extension of the gate vocabulary**, not an optimization phase.

### 1.2 What Phase 4C explicitly does *not* do
Phase 4C does **not**:
- add algebraic rewrite rules for unitaries,
- propagate or factor exponentials,
- exploit Lie‑theoretic identities,
- change extraction completeness,
- interact semantically with ZX normalization.

All such behavior is deferred to a **future optional phase (Phase 4D)**.

---

## 2. Locked Carry‑Over Invariants (from Phases 0–4B)

Phase 4C must preserve *all* existing invariants:

1. **Structure vs computation**
   - Structural terms compile only to `WirePerm`.
   - Structural compilation emits no gates and no SWAPs.

2. **Gate opacity / firewall**
   - Gate atoms are opaque.
   - Normalization and extraction never rewrite inside gates.
   - Only declared **support wires** may be inspected.

3. **Determinism**
   - Same AST ⇒ identical command stream, circuit, permutation, or residual.
   - Parameter serialization must be canonical.

4. **SWAP policy**
   - `materialize=False` ⇒ zero SWAPs.
   - SWAPs appear only via explicit materialization.

5. **Extraction soundness**
   - Extraction succeeds iff gates do not genuinely interact with feedback loops.
   - Failure returns residual `GOIArtifact`, not an error.

6. **ZX shows only structure**
   - Phase 4B ZX pass treats all gates (including new ones) as opaque boxes.

---

## 3. Conceptual Model: “Primitive Unitary Atoms”

### 3.1 Definition
A **primitive unitary atom** is:
- an indivisible gate at the compiler level,
- known (or assumed) to denote a unitary operator,
- parameterized or non‑parameterized,
- acting on a fixed arity of wires.

The compiler does **not** reason about its internal algebra.

### 3.2 Examples
- Fixed gates: `H`, `X`, `CX`, `CZ`
- Parameterized gates: `Rz(θ)`, `Phase(φ)`
- Semantic generators: `Twist`, `Assoc`
- **Exponentials:** `Exp(θ · Twist)`, `Exp(iθA)` (as atomic gates)

---

## 4. Gate Atom Specification (Required)

Every new primitive unitary must be registered with:

### 4.1 Static metadata
- **Opcode / name** (string or enum)
- **Arity** (number of wires)
- **Parameter schema**
  - none | real | vector | symbolic
- **Declared support**
  - logical wire indices (Phase 4A decision applies)

### 4.2 Backend lowering
A deterministic function:
```python
lower_gate_atom(atom: GateAtom, perm: WirePerm) -> pytket.CircuitFragment
```
Requirements:
- apply `perm` to logical wires at lowering time,
- emit only unitary pytket operations,
- emit gates in a stable, deterministic order.

### 4.3 Canonical parameter serialization
To preserve goldens and determinism:
- parameters must serialize canonically
- e.g. fixed‑precision decimals, normalized symbolic forms
- no reliance on Python float `repr`

---

## 5. Interaction with Routing and Normalization

### 5.1 Allowed interaction: support reindexing
New gate atoms **must** participate in the existing routing commutation logic:

```
Perm ; Gate(wires=S)   ⇔   Gate(wires=Perm(S)) ; Perm
```

This is purely structural and is required so that:
- Phase 4A routing normalization works,
- Phase 4B ZX extraction can move routing past gates.

### 5.2 Forbidden interaction
- No rewriting *inside* gates
- No algebraic reasoning about parameters
- No semantic equivalences exploited

---

## 6. Extraction Behavior (Unchanged)

Phase 4C does **not** change extraction rules.

### 6.1 Extraction succeeds iff
- feedback loops can be proven gate‑free (modulo routing),
- including new gate atoms.

### 6.2 Extraction fails iff
- a new gate atom genuinely touches loop wires in a way that cannot be eliminated structurally.

### 6.3 Result
- Success: `(Circuit, WirePerm)`
- Failure: residual `GOIArtifact`

---

## 7. Algorithms Affected (Summary)

### 7.1 Compilation
- Extend AST → IR translation to admit new gate atoms.
- No changes to structural compilation.

### 7.2 Normalization
- No new rewrite rules.
- Existing routing/perm normalization applies uniformly.

### 7.3 Extraction (v1 / v2 / ZX)
- Treat new gate atoms identically to existing ones.
- Only their **support sets** matter.

---

## 8. Testing Plan (Phase 4C)

### 8.1 Regression (mandatory)
- Re‑run **all Phase 0–4B integration tests**.
- Assert bit‑identical outputs.

### 8.2 New positive tests
- Programs using new primitive unitaries **without feedback**
- Expect successful extraction to flat circuits.

### 8.3 New negative tests
- Programs where new primitives interact with feedback
- Expect residual `GOIArtifact`.

### 8.4 Determinism tests
- Same AST ⇒ identical serialized outputs across runs.

### 8.5 SWAP discipline tests
- Ensure no swaps unless explicit materialization.

### 8.6 Firewall canary tests
- Ensure no code path inspects gate internals or parameters during normalization/extraction.

---

## 9. Phase 4D (Explicit Non‑Goal for Phase 4C)

### 9.1 What Phase 4D would cover
Phase 4D is a **future optional analytic normalization phase**, potentially including:
- semantic propagation of exponentials,
- splitting over ⊕ or ⊗,
- Lie‑theoretic identities (e.g. BCH),
- ZX + analytic interaction.

### 9.2 Why it is excluded from Phase 4C
- Requires semantic reasoning, not structural.
- Risks breaking determinism and rollback safety.
- Violates the extraction firewall if done prematurely.

### 9.3 Contract for Phase 4D (future)
If implemented later, Phase 4D must:
- be explicitly optional,
- be rollback‑safe,
- have a fixed deterministic rewrite schedule,
- never be required for soundness.

---

## 10. Definition of Done for Phase 4C

Phase 4C is complete when:
- new primitive unitary atoms compile and lower correctly,
- all Phase 0–4B tests pass unchanged,
- new Phase 4C tests pass,
- extraction behavior is unchanged except where dictated by support interaction,
- Phase 4D is clearly documented as a non‑goal.

---

## 11. One‑Sentence Summary

> **Phase 4C extends the set of admissible unitary gate atoms while preserving the existing structural, normalization, and extraction discipline; all semantic algebra on these unitaries is deferred to a future optional phase (4D).**

---

*End of Phase 4C senior developer note.*
