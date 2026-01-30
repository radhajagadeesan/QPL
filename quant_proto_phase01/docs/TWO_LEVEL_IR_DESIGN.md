# Granthi IR Architecture

**Design Document: Flat IR with Direct Compilation**

This document describes the compiler's intermediate representation and compilation strategy.

---

## Overview

The compiler uses a **single flat IR** with direct recursive-descent compilation. There is no separate "IR2" layer for typical programs. GOI (Geometry of Interaction) machinery exists only for the explicit `Feedback` term, which is rarely used.

```
OCaml Surface Language
    │
    │ elaborate() — β-reduce, substitute, transform case
    ▼
Python Core IR (lang/terms.py)
    │
    │ compile() — direct recursive descent
    ▼
┌─────────────────────────────────────────────────────┐
│  Flat IR (implicit, not reified)                    │
│  • Wire layouts (tensor, log-tag sums)              │
│  • Structural permutations (WirePerm)               │
│  • Gate atoms emitted to pytket                     │
│  • Deterministic, acyclic                           │
└─────────────────────────────────────────────────────┘
    │
    ▼
pytket Circuit + WirePerm
```

**Key point:** The "IR" is not a separate data structure. It's the compilation discipline — how we traverse the AST while accumulating permutations and emitting gates.

---

## Wire Layout Model

**Location:** `src/lang/types.py`

Types determine **wire layouts**.

### Tensor (`⊗`) — Simple Concatenation

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

### Sum (`⊕`) — Option B: Flat Log-Tag + Shared Payload

```
A₁ ⊕ A₂ ⊕ ... ⊕ Aₙ  ≡  [ tag_bits | shared_payload ]
k = ceil(log2(n))
width(sum) = k + max(width(Aᵢ))
```

**Invariant:** Tag register stores index i ∈ {0,...,n-1}. Unused payload wires are |0⟩.

**Example: Q ⊕ Q**
```
Type:   Q ⊕ Q
Width:  2  (1 tag bit + 1 shared payload)
Layout: [ tag | payload ]
        ─────────────
         0      1

State |Left(ψ)⟩:  tag=|0⟩, payload=|ψ⟩
State |Right(φ)⟩: tag=|1⟩, payload=|φ⟩
```

**Example: (Q ⊕ Q) ⊕ Q (nested sum flattens to 3-ary)**
```
Type:   (Q ⊕ Q) ⊕ Q
Width:  3  (ceil(log2(3))=2 tag bits + max(1)=1 payload)
Layout: [ tag₀ | tag₁ | payload ]
        ─────────────────────────
         0      1       2

Tag values: 0=first Q, 1=second Q, 2=third Q
```

### Dual (`*`) — Self-Dual Types

```
A* ≡ A    (all types are self-dual)
width(Dual(A)) = width(A)
```

The `Dual(A)` type tracks polarity for documentation but has no effect on layout.

### Function Types — Tensor Encoding

Since all types are self-dual: `A ⊸ B ≡ A* ⊗ B ≡ A ⊗ B`

A function `Q → Q` is physically 2 wires. Functions are circuit fragments with exposed dual inputs, not closures.

---

## Structural Layer — Pure Permutations

**Location:** `src/core/perm.py`

Structural operations compile to **wire permutations** (tracked symbolically, not emitted as SWAPs).

```python
@dataclass
class WirePerm:
    new_to_old: List[int]  # new_to_old[new_idx] = old_idx
```

### Structural Operations Summary

| Term | Type | Wire Perm | Tag Effect | Gates |
|------|------|-----------|------------|-------|
| `TwistTen(A,B)` | A⊗B → B⊗A | block swap | — | 0 |
| `TwistPlus(A,B)` | A⊕B → B⊕A | identity | X on tag | 1 |
| `AssocTenL/R` | reassociate ⊗ | identity | — | 0 |
| `AssocPlusL/R` | reassociate ⊕ | identity | identity | 0 |
| `DistL` | (A⊕B)⊗C → (A⊗C)⊕(B⊗C) | identity | — | 0 |
| `DistR` | A⊗(B⊕C) → (A⊗B)⊕(A⊗C) | move tag to front | — | 0 |

**Key Invariant:**
> Tensor structurals = pure wire permutations (no gates).
> Sum structurals = symbolic tag permutations, lowered to X gates only at emission.

---

## Higher-Order Compilation — Cup/Cap (No GOI)

**Location:** `src/lang/terms.py`, `src/compile/to_pytket.py`

Higher-order programs compile via **compact-closed structure**, not GOI:

- **`Cup(A)`**: η_A : I → A ⊗ A* — allocate 2·width(A) wires (pure wiring, 0 gates)
- **`Cap(A)`**: ε_A : A* ⊗ A → I — identify/connect wires (pure wiring, 0 gates)

Since A* = A, lambda abstraction just exposes wires (cup), and application connects them (cap).

```
λx:(A→B). body    compiles to    Cup exposes A⊗B wires; body uses them
Apply(f, arg)     compiles to    Cap connects f's output wires to arg
```

**No feedback, no loops, no GOI** — higher-order is just wire bookkeeping.

---

## Quantum Branching — Controlled Gates

**Location:** `src/compile/to_pytket.py` (Case handling), `surface/lib/elaborate.ml`

Case expressions on sum types compile to **controlled/anti-controlled gate sequences**:

```
case ctrl of Left => body_L | Right => body_R

Compiles to:
  X[tag]                    ← flip tag (0→1)
  Controlled-body_L[tag,…]  ← fires when tag=1 (original 0)
  X[tag]                    ← flip back (1→0)
  Controlled-body_R[tag,…]  ← fires when tag=1 (original 1)
```

Gate mapping: `H→CH`, `S→CS`, `X→CX`, `CX→CCX`, `Rz→CRz`, etc.

The tag qubit passes through unchanged. Both branches execute coherently on superpositions.

---

## Gate Atoms

**Location:** `src/lang/terms.py`

Gates are opaque unitary primitives:
- Single-qubit: `H`, `S`, `Sdg`, `T`, `Tdg`, `X`, `Y`, `Z`, `Rx`, `Ry`, `Rz`, `Phase`
- Two-qubit: `CX`, `CZ`, `CH`, `CS`, `CSdg`, `CRz`
- Three-qubit: `CCX`
- Exponentials: `ExpSwap` (exp(iθ·SWAP)), `ExpInvolution` (exp(iθ·P) for involution P)

Gates:
- Act on specific wire indices
- Are reindexed through the current permutation at emission time
- Are never rewritten internally

---

## Compilation Output

**Location:** `src/compile/to_pytket.py` → `Compiled` dataclass

```python
@dataclass
class Compiled:
    circuit: pytket.Circuit  # Emitted gate sequence
    perm: WirePerm           # Final boundary permutation
    log: Optional[List[str]] # Debug trace (if explain=True)
```

**Key properties:**
- Deterministic: same AST → identical output
- No SWAPs by default (permutation is symbolic); use `materialize=True` to emit SWAPs
- Acyclic — always directly executable

---

## GOI / Feedback (Rarely Used)

**Location:** `src/compile/goi.py`, `src/compile/to_pytket.py` (compile_goi)

The `Feedback(k, body)` term introduces explicit loops. This is the **only** place GOI semantics apply:

```python
@dataclass
class GOIArtifact:
    n_in: int                    # Input boundary width
    n_out: int                   # Output boundary width
    perm: WirePerm               # Routing permutation
    atoms: Tuple[GateAtom, ...]  # Gate sequence
    loops: Tuple[LoopSpec, ...]  # Explicit loop metadata
```

**Extraction rule:** Feedback is eliminable iff no gate touches loop wires (yanking).

**Important:** GOI is NOT used for higher-order compilation. It's only for explicit `Feedback` terms, which are rare in practice.

---

## Compilation Discipline

### Sequential Composition (`;`)

Gates emitted in order. Permutations composed.

### Parallel Composition (`⊗`)

Deterministic offset semantics:
- Left branch: offset = 0
- Right branch: offset = width(left)
- Emission order: left first, then right

### Permutation Accumulation

The compiler maintains a `WirePerm p` throughout traversal:
1. Structural ops compose into `p`
2. Gate indices are reindexed through `p` at emission: `phys = p.apply_new_to_old(logical)`
3. Final `p` is returned as `Compiled.perm`

---

## Summary

| Aspect | Value |
|--------|-------|
| IR structure | Flat, acyclic, single-level |
| Layout | Option B: log-tag + shared payload |
| Tensor structurals | Pure wire permutations (0 gates) |
| Sum structurals | Tag permutations (X gates for TwistPlus) |
| Higher-order | Cup/cap wiring (0 gates, no GOI) |
| Quantum case | Anti-controlled + controlled gates |
| Output | pytket Circuit + WirePerm |
| GOI/Feedback | Only for explicit `Feedback` term (rare) |

**Design principle:** The compiler does minimal work. Structural operations are permutations, not gates. Higher-order is wiring, not computation. Only actual quantum gates become circuit gates.
