# Controlled-F with Structural Operations

This document explains how controlled operations work in Granthi when the controlled operation is **structural** (a pure wire permutation). The key insight: the control structure is "compiled into the wires" — no controlled gates needed beyond creating the initial superposition.

---

## 1. Layout Architecture

### Tensor: A ⊗ B

Simple concatenation:
```
Layout(A ⊗ B) = [A_wires | B_wires]
width(A ⊗ B) = width(A) + width(B)
```

### Sum: A + B (One-Hot Leaf-Tag Encoding)

Flattens the Plus tree, then:
```
Layout(A₁ + A₂ + ... + Aₙ) = [t₁ | t₂ | ... | tₙ | A₁_wires | A₂_wires | ... | Aₙ_wires]
                             ←── n tag wires ──→  ←────── payload wires ──────→

width(sum) = n + Σ width(Aᵢ)
```

### Mixed: A ⊗ (B + C)

Tags are nested inside the tensor:
```
Layout(A ⊗ (B + C)) = [A_wires | t₀ | t₁ | B_wires | C_wires]
```

### Key Property

**No reverse mapping exists.** Given just wires, you cannot tell which are tags vs data. The type carries the semantic structure.

---

## 2. Structural Operations Are Free

With one-hot leaf-tag encoding, **all structural operations compile to pure wire permutations** — zero gates:

| Operation | Type | Gates |
|-----------|------|-------|
| `twist⊗[A,B]` | A⊗B → B⊗A | 0 |
| `assoc⊗L/R` | regrouping | 0 |
| `twist+[A,B]` | A+B → B+A | 0 |
| `assoc+L/R` | regrouping | 0 (identity) |
| `distR[A,B,C]` | A⊗(B+C) → (A⊗B)+(A⊗C) | 0 |
| `distL[A,B,C]` | (A+B)⊗C → (A⊗C)+(B⊗C) | 0 |

**Why?** One-hot encoding avoids tag bit flips. Operations just reorder wire positions.

---

## 3. Q vs I + I

Both represent a 2D Hilbert space, but with different physical encodings:

| Type | Physical Wires | Basis States | Valid States |
|------|----------------|--------------|--------------|
| `Q` | 1 | \|0⟩, \|1⟩ | All 2 |
| `I + I` | 2 | \|00⟩, \|01⟩, \|10⟩, \|11⟩ | Only \|01⟩, \|10⟩ (one-hot) |

For `I + I`:
- Logical \|0⟩_L = \|10⟩ (physical)
- Logical \|1⟩_L = \|01⟩ (physical)

**Trade-off:** `I + I` uses 2 wires, but structural operations (like logical X = twist+) are free.

---

## 4. Controlled-F: The Key Insight

### Setup

- **Control:** `I + I` in superposition
- **Data:** type A
- **Operation:** f : A → A is structural (a permutation)

### Why It Works

After distribution, data lives in **different wire positions** depending on the tag:

```
(I+I) ⊗ A  →  distR  →  A + A

Layout: [t₀ | t₁ | A₀_wires | A₁_wires]

State:  α|10⟩|ψ⟩|0...0⟩ + β|01⟩|0...0⟩|ψ⟩
              ↑    ↑              ↑    ↑
             A₀   A₁            A₀   A₁
```

The data |ψ⟩ occupies **different physical wires** based on which tag is active!

### Applying Controlled-F

Apply `id` to A₀ wires, `f` (structural permutation) to A₁ wires:

```
Result: α|10⟩|ψ⟩|0...0⟩ + β|01⟩|0...0⟩|f(ψ)⟩
```

The permutation on A₁ is **unconditional** — but because amplitude only occupies those wires in the |01⟩ branch, it effectively becomes controlled!

### What Needs Gates vs What's Free

| Operation | Gates Required? |
|-----------|-----------------|
| Create superposition on control | **YES** (e.g., logical H) |
| twist+ on control (logical X) | No (permutation) |
| Controlled-f where f is structural | No (permutation) |
| Controlled-f where f has gates | **YES** (controlled gates) |

---

## 5. Logical H on I + I

To put the control qubit in superposition, we need logical Hadamard:

```
|0⟩_L = |10⟩  →  (|10⟩ + |01⟩)/√2
|1⟩_L = |01⟩  →  (|10⟩ - |01⟩)/√2
```

### Circuit

```
CX[1,0] ; H[1] ; CX[1,0]
```

**3 gates:** 2 CNOTs + 1 Hadamard.

### Trace Through

**|10⟩ (logical |0⟩):**
```
|10⟩ →CX[1,0]→ |10⟩ →H[1]→ (|10⟩+|11⟩)/√2 →CX[1,0]→ (|10⟩+|01⟩)/√2  ✓
       (ctrl=0,
        no flip)
```

**|01⟩ (logical |1⟩):**
```
|01⟩ →CX[1,0]→ |11⟩ →H[1]→ (|10⟩-|11⟩)/√2 →CX[1,0]→ (|10⟩-|01⟩)/√2  ✓
       (ctrl=1,
        flip)
```

### In Granthi

```python
from lang.types import Unit, Plus
from lang.term import Seq, CX, H

ty = Plus(Unit(), Unit())  # I + I
H_logical = Seq(CX(1, 0, ty), H(1, ty), CX(1, 0, ty))
```

---

## 6. Full Example: Controlled-SWAP

**Goal:** Apply SWAP to data conditionally based on control qubit in superposition.

### Types

```
Control: I + I          (2 wires)
Data:    Q ⊗ Q          (2 wires)
Total:   (I+I) ⊗ (Q⊗Q)  (4 wires)
```

### Program

```python
from lang.types import Unit, Plus, Ten, Q
from lang.term import Seq, CX, H, TwistTensor, DistR, UndistR

# Types
ctrl = Plus(Unit(), Unit())      # I + I
data = Ten(Q(), Q())             # Q ⊗ Q
full = Ten(ctrl, data)           # (I+I) ⊗ (Q⊗Q)

# Step 1: Create superposition on control (GATES HERE)
H_logical = Seq(CX(1, 0, ctrl), H(1, ctrl), CX(1, 0, ctrl))

# Step 2: Distribute (FREE - permutation)
dist = DistR(ctrl, data)  # → (Q⊗Q) + (Q⊗Q)

# Step 3: Apply id to left branch, twist⊗ to right branch (FREE - permutation)
# twist⊗ on right branch wires is a structural SWAP
controlled_swap = ...  # permutation on right branch wires

# Step 4: Undistribute (FREE - permutation)
undist = UndistR(ctrl, data)

# Full circuit
circuit = Seq(H_logical, dist, controlled_swap, undist)
```

### Gate Count

- **Superposition creation:** 3 gates (2 CX + 1 H)
- **Controlled-SWAP structure:** 0 gates (all permutations)
- **Total:** 3 gates

Compare to standard controlled-SWAP (Fredkin gate): **5+ gates**.

---

## 7. The Payoff

1. **Pay once** for superposition creation (logical H = 3 gates)
2. **Get arbitrary structural control for free** — all controlled permutations are just wire routing
3. **Compose freely** — multiple controlled-structural operations with same control cost nothing extra

The control structure is **compiled into the wire layout**, not implemented with controlled gates.

---

## 8. Limitations

This only works when the controlled operation is **structural** (a permutation):
- twist⊗, twist+ ✓
- assoc⊗, assoc+ ✓
- dist, undist ✓
- SWAP (as twist⊗) ✓

For non-structural operations (H, T, Rz, CX, etc.), you still need actual controlled gates.

---

## See Also

- `demos/pauli_conjugation_demo.py` — Pauli gates on I+I
- `demos/exp_twist_demo.py` — Exponentials of structural involutions
- `docs/PROGRAMMING_GUIDE.md` — Full language reference
