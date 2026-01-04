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

Types determine **wire layouts**. We use **one-hot leaf-tag encoding** for sums.

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

##### Sum (`+`) — One-Hot Leaf Tags

```
A + B  ≡  [ tag_A | tag_B | A_wires | B_wires ]
width(A + B) = 2 + width(A) + width(B)
```

**Invariant:** Exactly one tag wire is |1⟩, the rest are |0⟩.

**Example: Q + Q**
```
Type:   Q + Q
Width:  4
Layout: [ t₁ | t₂ | q_L | q_R ]
        ─────────────────────────
         0    1     2     3

State |Left(ψ)⟩:  t₁=|1⟩, t₂=|0⟩, q_L=|ψ⟩, q_R=|0⟩
State |Right(φ)⟩: t₁=|0⟩, t₂=|1⟩, q_L=|0⟩, q_R=|φ⟩
```

**Example: (Q + Q) + Q (nested sum flattens)**
```
Type:   (Q + Q) + Q
Width:  6  (3 leaf tags + 3 payloads)
Layout: [ t₁ | t₂ | t₃ | q₁ | q₂ | q₃ ]
        ─────────────────────────────────
         0    1    2    3    4    5

This is an n-ary sum with 3 summands, using one-hot encoding.
```

---

##### Mixed: A ⊗ (B + C)

```
A ⊗ (B + C)  ≡  [ A_wires | tag_B | tag_C | B_wires | C_wires ]
width = width(A) + 2 + width(B) + width(C)
```

**Example: Q ⊗ (Q + Q)**
```
Type:   Q ⊗ (Q + Q)
Width:  5
Layout: [ q_A | t₁ | t₂ | q_B | q_C ]
        ─────────────────────────────
          0    1    2    3     4

The A component occupies wire 0.
The sum (Q + Q) occupies wires 1-4 (2 tags + 2 payloads).
```

**Example: (Q + Q) ⊗ Q**
```
Type:   (Q + Q) ⊗ Q
Width:  5
Layout: [ t₁ | t₂ | q_L | q_R | q_C ]
        ─────────────────────────────
         0    1    2     3     4

The sum (Q + Q) occupies wires 0-3.
The C component occupies wire 4.
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

Swaps both the tag wires AND the payload blocks.

**Example: TwistPlus(Q, Q)**
```
Input:  [ t₁ | t₂ | q_L | q_R ]    Output: [ t₂ | t₁ | q_R | q_L ]
          0    1    2     3                  0    1    2     3

Permutation: [1, 0, 3, 2]
             Swaps tags (0↔1) and payloads (2↔3)
```

This is **involutive**: applying it twice gives identity.

---

##### DistL: (A + B) ⊗ C → (A ⊗ C) + (B ⊗ C)

Tags are already at the front — this is **identity on wires**.

**Example: DistL(Q, Q, Q)**
```
Input type:  (Q + Q) ⊗ Q
Input:       [ t₁ | t₂ | q_L | q_R | q_C ]
               0    1    2     3     4

Output type: (Q ⊗ Q) + (Q ⊗ Q)
Output:      [ t₁ | t₂ | q_L | q_R | q_C ]
               0    1    2     3     4

Permutation: [0, 1, 2, 3, 4]  (identity)
```

The wire layout is already correct! The type changes but the physical wires don't move.

---

##### DistR: A ⊗ (B + C) → (A ⊗ B) + (A ⊗ C)

Moves the tag wires from the middle to the front.

**Example: DistR(Q, Q, Q)**
```
Input type:  Q ⊗ (Q + Q)
Input:       [ q_A | t₁ | t₂ | q_B | q_C ]
               0     1    2    3     4

Output type: (Q ⊗ Q) + (Q ⊗ Q)
Output:      [ t₁ | t₂ | q_A | q_B | q_C ]
               0    1    2     3     4

Permutation: [1, 2, 0, 3, 4]
             new wire 0 ← old wire 1 (first tag)
             new wire 1 ← old wire 2 (second tag)
             new wire 2 ← old wire 0 (A payload)
             new wires 3,4 stay in place
```

The tags move from positions [1,2] to positions [0,1].

---

##### Structural Operations Summary

| Term | Type | Permutation | Gates |
|------|------|-------------|-------|
| `TwistTen(Q,Q)` | Q⊗Q → Q⊗Q | [1, 0] | 0 |
| `TwistPlus(Q,Q)` | Q+Q → Q+Q | [1, 0, 3, 2] | 0 |
| `AssocTenL(Q,Q,Q)` | (Q⊗Q)⊗Q → Q⊗(Q⊗Q) | [0, 1, 2] | 0 |
| `AssocPlusL(Q,Q,Q)` | (Q+Q)+Q → Q+(Q+Q) | reorders tags+payloads | 0 |
| `DistL(Q,Q,Q)` | (Q+Q)⊗Q → (Q⊗Q)+(Q⊗Q) | [0, 1, 2, 3, 4] | 0 |
| `DistR(Q,Q,Q)` | Q⊗(Q+Q) → (Q⊗Q)+(Q⊗Q) | [1, 2, 0, 3, 4] | 0 |

**Key Invariant:**
> With one-hot encoding, structural operations are **always** pure permutations. No X gates, no tag recoding, no gates on any wires.

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
| One-hot sums | Belong in IR1 from the start |
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

**Test coverage:** 1169+ tests passing

---

## Final Takeaway

> **IR1:** Flat, layout-driven, executable. Structural = pure permutation.
> **IR2:** Routed, cyclic, explanatory.
> **Extraction:** A sound bridge from IR2 back to IR1.

Everything else — phases, refinements, completeness — fits cleanly on top of this split.
