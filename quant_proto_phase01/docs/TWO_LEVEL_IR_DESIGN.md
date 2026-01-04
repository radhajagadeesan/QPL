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
│  • Wire layouts (tensor, tagged sums)               │
│  • Structural permutations + tag management         │
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

Types determine **wire layouts**:

**Tensor (`⊗`)**
```
A ⊗ B  ≡  [ A_wires | B_wires ]
width(A ⊗ B) = width(A) + width(B)
```

**Sum (`⊕`) — Tagged Representation**
```
A ⊕ B  ≡  [ tag | A_wires | B_wires ]
width(A ⊕ B) = 1 + width(A) + width(B)
```

The tag wire is an explicit qubit that encodes branch choice. This representation enables distributivity without wire duplication or classical control.

---

#### 2. Structural Layer

**Location:** `src/core/perm.py`

Structural operations are **layout isomorphisms**. They involve:

- **Wire permutations** — reordering of physical wires (tensor twists, associators)
- **Tag flips** — X gates on tag wires (sum twists)

The `TaggedPerm` dataclass captures both:
```python
@dataclass
class TaggedPerm:
    perm: WirePerm           # Wire reordering
    tag_flips: FrozenSet[int]  # Positions needing X gates
```

**Structural Operations:**

| Term | Permutation | Tag Flips |
|------|-------------|-----------|
| `TwistTen(A,B)` | Swaps A and B wire blocks | None |
| `TwistPlus(A,B)` | Swaps A and B wire blocks | X on tag wire |
| `AssocTenL/R` | Reassociates wire blocks | None |
| `AssocPlusL/R` | Reassociates wire blocks + tags | (TODO: tag recoding) |
| `DistL` | Identity | None |
| `DistR` | Moves tag to front | None |

**Invariant:**
> Structural operations never perform nontrivial unitary evolution on payload (non-tag) wires.

---

#### 3. Gate Atoms

**Location:** `src/lang/terms.py`

Gates are opaque, unitary primitives:
- Single-qubit: `H`, `S`, `Sdg`, `T`, `Tdg`, `X`, `Y`, `Z`, `Rx`, `Ry`, `Rz`, `Phase`
- Two-qubit: `CX`, `CZ`, `CRz`
- Three-qubit: `CCX`

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
| Layout | Tagged sums, tensor products |
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

1. Fix **tagged sums and layout invariants** from day one.
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
- Added `TaggedPerm` for permutation + tag flips
- Implemented distributivity (`DistL`, `DistR`) structurally
- Updated invariants: structural ≠ permutation-only (tag flips allowed)
- Re-validated IR2 extraction logic

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
| Tagged sums | Belong in IR1 from the start |
| GOI | Never computes; only explains routing |

---

## Current Status

| Phase | Status | Key Contributions |
|-------|--------|-------------------|
| 0–1 | Complete | Permutation discipline, gates, typing |
| 2 | Complete | `TenTerm` parallel composition |
| 3 | Complete | GOI feedback, extraction |
| 4C | Complete | Tagged layout, distributivity |
| 5 | Complete | Higher-order compilation via GOI |

**Test coverage:** 1145+ tests passing

---

## Final Takeaway

> **IR1:** Flat, layout-driven, executable.
> **IR2:** Routed, cyclic, explanatory.
> **Extraction:** A sound bridge from IR2 back to IR1.

Everything else — phases, refinements, completeness — fits cleanly on top of this split.
