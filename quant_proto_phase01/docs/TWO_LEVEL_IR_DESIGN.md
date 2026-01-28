# Granthi Two-Level IR Architecture

**Design Document: IR1 (Flat) and IR2 (GOI) Intermediate Representations**

This document describes the compiler's two-level IR architecture:

1. **IR1: Flat IR** — acyclic, first-order, layout-driven compilation target.
2. **IR2: GOI IR** — cyclic, routed, feedback-aware semantic layer.

IR2 is not a replacement for IR1. It is a *second semantic layer* that explains and controls feedback, from which we attempt to return to IR1 via **sound extraction**.

---

## Part I — IR Architecture

### Overview

```
Source AST
    │
    ▼
┌─────────────────────────────────────────────────────┐
│  IR1: Flat IR                                       │
│  • Wire layouts (tensor, one-hot tagged sums)       │
│  • Structural permutations (pure wire reordering)   │
│  • Gate atoms (opaque unitaries)                    │
│  • Deterministic command stream                     │
│  └─── No feedback, always executable ───┘           │
└─────────────────────────────────────────────────────┘
    │
    │ (when Feedback present)
    ▼
┌─────────────────────────────────────────────────────┐
│  IR2: GOI IR                                        │
│  • Boundary doubling (A → A* ⊗ B)                   │
│  • Explicit loop metadata                           │
│  • Routed execution semantics                       │
│  └─── Extraction attempts collapse to IR1 ───┘      │
└─────────────────────────────────────────────────────┘
    │
    ▼
pytket Circuit + WirePerm
```

---

## IR1 — Flat IR

**Location:** `src/compile/to_pytket.py` (compile function)

### Purpose

IR1 is the *workhorse IR* of the compiler. It represents quantum programs as **flat, acyclic wiring plus gates**. Every executable artifact ultimately lives in IR1.

---

### IR1 Core Components

#### 1. Wire Layout Model

**Location:** `src/lang/types.py`

Types determine **wire layouts**. We use **Option B: flat log-tag encoding** for sums.

---

##### Tensor (`⊗`) — Simple Concatenation

```
A ⊗ B  ≡  [ A_wires | B_wires ]
width(A ⊗ B) = width(A) + width(B)
```

**Example: Q ⊗ Q**
```
Type:   Q ⊗ Q
Width:  2
Layout: [ q₀ | q₁ ]
        ─────────
         0    1
```

**Example: (Q ⊗ Q) ⊗ Q**
```
Type:   (Q ⊗ Q) ⊗ Q
Width:  3
Layout: [ q₀ | q₁ | q₂ ]
        ────────────────
         0    1    2
```

---

##### Sum (`+`) — Option B: Flat Log-Tag + Shared Payload

```
A₁ + A₂ + ... + Aₙ  ≡  [ tag_bits | shared_payload ]
k = ceil(log2(n))
width(sum) = k + max(width(Aᵢ))
```

**Invariant:** Tag register stores index i ∈ {0,...,n-1}. Unused payload wires are |0⟩.

**Example: Q + Q**
```
Type:   Q + Q
Width:  2  (1 tag bit + 1 shared payload)
Layout: [ tag | payload ]
        ─────────────
         0      1

State |Left(ψ)⟩:  tag=|0⟩, payload=|ψ⟩
State |Right(φ)⟩: tag=|1⟩, payload=|φ⟩
```

**Example: (Q + Q) + Q (nested sum flattens to 3-ary)**
```
Type:   (Q + Q) + Q
Width:  3  (ceil(log2(3))=2 tag bits + max(1)=1 payload)
Layout: [ tag₀ | tag₁ | payload ]
        ─────────────────────────
         0      1       2

Tag values: 0=first Q, 1=second Q, 2=third Q. Code 3 is unreachable.
```

---

##### Mixed: A ⊗ (B + C)

```
A ⊗ (B + C)  ≡  [ A_wires | tag_bits | shared_payload ]
width = width(A) + ceil(log2(n)) + max(width(Bᵢ))
```

**Example: Q ⊗ (Q + Q)**
```
Type:   Q ⊗ (Q + Q)
Width:  3
Layout: [ q_A | tag | payload ]
        ────────────────────
          0     1      2

The A component occupies wire 0.
The sum (Q + Q) occupies wires 1-2 (1 tag + 1 payload).
```

**Example: (Q + Q) ⊗ Q**
```
Type:   (Q + Q) ⊗ Q
Width:  3
Layout: [ tag | payload | q_C ]
        ─────────────────────
         0      1        2

The sum (Q + Q) occupies wires 0-1.
The C component occupies wire 2.
```

---

#### 2. Structural Layer — Pure Permutations

**Location:** `src/core/perm.py`

With one-hot encoding, **all structural operations are pure wire permutations** (no gates needed).

A `WirePerm` is a bijection on wire indices:
```python
@dataclass
class WirePerm:
    new_to_old: List[int]  # new_to_old[new_idx] = old_idx
```

---

##### TwistTen: A ⊗ B → B ⊗ A

Swaps the wire blocks for A and B.

**Example: TwistTen(Q, Q)**
```
Input:  [ q₀ | q₁ ]       Output: [ q₁ | q₀ ]
         0    1                    0    1

Permutation: [1, 0]
             new_to_old[0] = 1  (new wire 0 ← old wire 1)
             new_to_old[1] = 0  (new wire 1 ← old wire 0)
```

---

##### TwistPlus: A + B → B + A

Flips the tag bit (symbolic tag permutation, lowered to X gate).

**Example: TwistPlus(Q, Q)**
```
Input:  [ tag | payload ]    Output: [ tag⊕1 | payload ]
          0      1                     0        1

Wire permutation: identity [0, 1]
Tag flip: X gate on wire 0
```

This is **involutive**: applying it twice gives identity (X·X = I).

---

##### DistL: (A + B) ⊗ C → (A ⊗ C) + (B ⊗ C)

Tags are already at the front — this is **identity on wires**.

**Example: DistL(Q, Q, Q)**
```
Input type:  (Q + Q) ⊗ Q
Input:       [ tag | payload | q_C ]
               0      1        2

Output type: (Q ⊗ Q) + (Q ⊗ Q)
Output:      [ tag | payload | q_C ]
               0      1        2

Permutation: [0, 1, 2]  (identity)
```

---

##### DistR: A ⊗ (B + C) → (A ⊗ B) + (A ⊗ C)

Moves the tag bits from the middle to the front.

**Example: DistR(Q, Q, Q)**
```
Input type:  Q ⊗ (Q + Q)
Input:       [ q_A | tag | payload ]
               0      1      2

Output type: (Q ⊗ Q) + (Q ⊗ Q)
Output:      [ tag | q_A | payload ]
               0      1      2

Permutation: [1, 0, 2]
             new wire 0 ← old wire 1 (tag)
             new wire 1 ← old wire 0 (A)
             new wire 2 stays
```

---

##### Structural Operations Summary

| Term | Type | Wire Perm | Tag Effect | Gates |
|------|------|-----------|------------|-------|
| `TwistTen(Q,Q)` | Q⊗Q → Q⊗Q | [1, 0] | — | 0 |
| `TwistPlus(Q,Q)` | Q+Q → Q+Q | [0, 1] (identity) | X on tag | 1 |
| `AssocTenL(Q,Q,Q)` | (Q⊗Q)⊗Q → Q⊗(Q⊗Q) | [0, 1, 2] | — | 0 |
| `AssocPlusL(Q,Q,Q)` | (Q+Q)+Q → Q+(Q+Q) | identity | identity | 0 |
| `DistL(Q,Q,Q)` | (Q+Q)⊗Q → (Q⊗Q)+(Q⊗Q) | [0, 1, 2] | — | 0 |
| `DistR(Q,Q,Q)` | Q⊗(Q+Q) → (Q⊗Q)+(Q⊗Q) | [1, 0, 2] | — | 0 |

**Key Invariant:**
> With Option B encoding, structural tensor operations are pure wire permutations.
> Structural sum operations use symbolic tag permutations (tracked in TaggedPerm),
> lowered to gates only at emission time.

---

#### 3. Gate Atoms

**Location:** `src/lang/terms.py`

Gates are opaque, unitary primitives:
- Single-qubit: `H`, `S`, `Sdg`, `T`, `Tdg`, `X`, `Y`, `Z`, `Rx`, `Ry`, `Rz`, `Phase`
- Two-qubit: `CX`, `CZ`, `CH`, `CS`, `CSdg`, `CRz`
- Three-qubit: `CCX`
- Exponentials: `ExpSwap` (exp(iθ·SWAP))

Gates:
- Act only on payload wires
- Are reindexed through the current permutation at emission time
- Are never rewritten internally

---

#### 4. Composition Discipline

**Sequential composition (`;`):** Gates emitted in order.

**Parallel composition (`⊗`):** Deterministic offset semantics:
- Left branch: offset = 0
- Right branch: offset = width(left)
- Emission order: left first, then right

---

#### 5. Flat Artifact

**Location:** `src/compile/to_pytket.py` → `Compiled` dataclass

IR1 compilation produces:
```python
@dataclass
class Compiled:
    circuit: pytket.Circuit  # Deterministic command stream
    perm: WirePerm           # Final boundary permutation
    log: Optional[List[str]] # Explanation trace (if explain=True)
```

**Key properties:**
- Deterministic: same AST → identical output
- No SWAPs by default (unless `materialize=True`)
- No feedback — always directly executable

---

### IR1 Summary

IR1 answers: **"What does this program do *without* feedback?"**

| Property | Value |
|----------|-------|
| Structure | Flat, acyclic |
| Layout | One-hot tagged sums, tensor products |
| Structural | Pure wire permutations (no gates) |
| Output | pytket Circuit + WirePerm |
| Feedback | None |

---

## IR2 — GOI IR (Feedback Layer)

**Location:** `src/compile/goi.py`, `src/compile/to_pytket.py` (compile_goi function)

### Purpose

IR2 exists to give **semantic meaning to feedback**. When a program contains `Feedback(k, body)`, IR2 provides the interpretation.

---

### Conceptual Shift: Doubling and Endomorphisms

In IR2, a program `f : A → B` is reinterpreted as an **endomorphism on an interaction boundary**:

```
f̂ : A* ⊗ B → A* ⊗ B
```

This is the Geometry of Interaction (GOI) move:
- Programs become *networks with ports*
- Execution becomes **routing of tokens**
- Feedback becomes **explicit wiring**, not recursion

---

### IR2 Core Components

#### 1. GOIArtifact

**Location:** `src/compile/goi.py`

```python
@dataclass
class GOIArtifact:
    n_in: int                    # Input boundary width
    n_out: int                   # Output boundary width
    perm: WirePerm               # Routing permutation
    atoms: Tuple[GateAtom, ...]  # Gate sequence
    loops: Tuple[LoopSpec, ...]  # Explicit loop metadata
```

Loops are **syntactic and fenced** — introduced only via `Feedback(k, body)`.

---

#### 2. Normalization Firewall

Structural rewrites may:
- Move gates via index rewriting through the permutation
- Normalize routing to identity

But must **never rewrite inside gate atoms**.

---

#### 3. Extraction (IR2 → IR1)

**Location:** `src/compile/to_pytket.py` (compile_goi)

Extraction attempts to collapse a GOI artifact back to IR1.

**Phase 3 Rule (Sound, Incomplete):**
> Feedback is eliminable iff no gate touches loop wires.

**Outcomes:**

| Condition | Result |
|-----------|--------|
| Yankable (no gates on loop wires) | `CompiledGOI` — flat circuit + perm |
| Not yankable | `GOIArtifact` — preserved residual |

**Checkpoint Invariant:**
> When extraction succeeds, GOI collapses to a boundary permutation. GOI explains routing; it does not compute.

---

### Higher-Order Compilation

IR2 also enables **higher-order compilation** via GOI conjugation:

- A unitary `U : A → A` becomes `(U† ⊗ U)` on `A* ⊗ A`
- Function composition uses feedback to connect shared boundaries
- `execute_trace` collapses loop wires to produce external circuits

See `compile_higher_order()` and `demos/qswitch_demo.py` for examples.

### IR2 Summary

IR2 answers: **"How does this program behave *with* feedback?"**

| Property | Value |
|----------|-------|
| Structure | Cyclic, routed |
| Feedback | Explicit loop metadata |
| Output | CompiledGOI or GOIArtifact |
| Extraction | Sound but incomplete |
| Higher-order | Via GOI conjugation |

---

## Part II — Development History

### The Clean Architecture (What We Should Have Done)

In hindsight, the clean story would be:

1. Fix **one-hot tagged sums and layout invariants** from day one.
2. Build IR1 fully on top of that representation.
3. Add IR2 as a semantic layer for feedback.
4. Refine extraction completeness.

---

### What We Actually Did (Chronology)

**Phase 0–2: Early IR1**
- Built flat compilation discipline: permutations, gates, offsets, determinism
- Initially treated all structure as permutation-only
- Deferred sum types and distributivity

**Phase 3: IR2 Introduction**
- Added explicit GOI feedback via `Feedback(k, body)`
- Introduced `GOIArtifact` and extraction logic
- Clarified the doubling/endomorphism perspective

**Phase 4C: IR1 Refinement**
- Realized sums require **tagged layouts**
- Initially used binary tags (1 tag wire per Plus node)
- Implemented distributivity (`DistL`, `DistR`) structurally

**Phase 5: One-Hot Encoding**
- Switched to **one-hot leaf-tag encoding**
- All structural operations become pure permutations
- No more X gates for TwistPlus
- No more tag recoding for AssocPlus
- Added `ExpSwap` and `ExpInvolution` for exponentials of involutions

---

### Why This Reorganization Matters

By separating:
- **IR architecture** (what the system *is*)
- **Development history** (how we got there)

We get a clean conceptual model:

| Layer | Role |
|-------|------|
| IR1 | Canonical flat target — always executable |
| IR2 | Semantic overlay for feedback — explanatory |
| Option B sums | Flat log-tag + shared payload, belong in IR1 |
| GOI | Never computes; only explains routing |

---

## Current Status

| Phase | Status | Key Contributions |
|-------|--------|-------------------|
| 0–1 | Complete | Permutation discipline, gates, typing |
| 2 | Complete | `TenTerm` parallel composition |
| 3 | Complete | GOI feedback, extraction |
| 4C | Complete | Tagged layout, distributivity |
| 5 | Complete | One-hot encoding, higher-order, exp involutions |

**Test coverage:** 1211+ tests passing

---

## Final Takeaway

> **IR1:** Flat, layout-driven, executable. Structural = pure permutation.
> **IR2:** Routed, cyclic, explanatory.
> **Extraction:** A sound bridge from IR2 back to IR1.

Everything else — phases, refinements, completeness — fits cleanly on top of this split.
