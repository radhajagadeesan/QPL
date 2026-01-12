# Granthi API Reference

Complete reference for types, terms, and compilation functions.

---

## Types (`src/lang/types.py`)

| Type | Description | Width |
|------|-------------|-------|
| `Q()` | Single qubit | 1 |
| `I()` | Unit type | 0 |
| `Ten(a, b)` | Tensor product a ⊗ b | width(a) + width(b) |
| `Plus(a, b)` | Sum type a + b (one-hot) | 2 + width(a) + width(b) |

### Function Types (Surface Language)

Function types `A → B` exist in the **surface language** (OCaml `TyArrow`):
- Represent morphisms from A to B
- Used for lambda abstractions and higher-order programming
- **No Python type constructor**—handled via higher-order terms

In Python, use `Lam`, `Apply`, `FunVar` for higher-order programming (see Higher-Order Terms).

### One-Hot Encoding

Sum types use one-hot leaf-tag encoding:
- Binary `Plus(A, B)` has 2 tag wires + payloads
- Nested sums flatten: `Plus(Plus(Q,Q), Q)` = 3 tags + 3 data = 6 wires
- Wire layout: `[t₁ | t₂ | ... | tₙ | A₁ | A₂ | ... | Aₙ]`
- Invariant: exactly one tag wire is |1⟩

**Functions:**
```python
from lang.types import Q, I, Ten, Plus, width

width(ty: Ty) -> int       # Number of physical wires
```

---

## Terms (`src/lang/terms.py`)

### Identity and Composition

| Term | Signature | Description |
|------|-----------|-------------|
| `Id(ty)` | `Id(ty: Ty)` | Identity on type |
| `Seq(f, g, ...)` | `Seq(*terms)` | Sequential composition (variadic) |
| `TenTerm(f, g)` | `TenTerm(f, g)` | Parallel composition f ⊗ g |

### Structural Isomorphisms

All compile to **pure wire permutations** (no gates).

| Term | Type Signature |
|------|----------------|
| `TwistTen(a, b)` | a ⊗ b → b ⊗ a |
| `TwistPlus(a, b)` | a + b → b + a |
| `AssocTenL(a, b, c)` | (a ⊗ b) ⊗ c → a ⊗ (b ⊗ c) |
| `AssocTenR(a, b, c)` | a ⊗ (b ⊗ c) → (a ⊗ b) ⊗ c |
| `AssocPlusL(a, b, c)` | (a + b) + c → a + (b + c) |
| `AssocPlusR(a, b, c)` | a + (b + c) → (a + b) + c |
| `DistL(a, b, c)` | (a + b) ⊗ c → (a ⊗ c) + (b ⊗ c) |
| `DistR(a, b, c)` | a ⊗ (b + c) → (a ⊗ b) + (a ⊗ c) |

### Gates

All gates take wire indices and an ambient type `ty_total`.

**Single-qubit gates:**

| Gate | Signature | Description |
|------|-----------|-------------|
| `H(i, ty)` | Hadamard | |
| `X(i, ty)` | Pauli-X | |
| `Y(i, ty)` | Pauli-Y | |
| `Z(i, ty)` | Pauli-Z | |
| `S(i, ty)` | S gate (π/2 phase) | |
| `Sdg(i, ty)` | S-dagger | |
| `T(i, ty)` | T gate (π/4 phase) | |
| `Tdg(i, ty)` | T-dagger | |

**Parameterized single-qubit gates:**

| Gate | Signature | Description |
|------|-----------|-------------|
| `Rx(theta, i, ty)` | X rotation by θ | |
| `Ry(theta, i, ty)` | Y rotation by θ | |
| `Rz(theta, i, ty)` | Z rotation by θ | |
| `Phase(theta, i, ty)` | Global phase | |

**Two-qubit gates:**

| Gate | Signature | Description |
|------|-----------|-------------|
| `CX(i, j, ty)` | CNOT (control i, target j) | |
| `CZ(i, j, ty)` | Controlled-Z | |
| `CH(i, j, ty)` | Controlled-Hadamard | |
| `CS(i, j, ty)` | Controlled-S | |
| `CSdg(i, j, ty)` | Controlled-S-dagger | |
| `CRz(theta, i, j, ty)` | Controlled-Rz by θ | |

**Three-qubit gates:**

| Gate | Signature | Description |
|------|-----------|-------------|
| `CCX(i, j, k, ty)` | Toffoli (controls i,j, target k) | |

### Exponentials of Involutions

**Typing rule:**
```
P : A → A    P² = id
─────────────────────
exp_i(θ, P) : A → A
```

| Term | Type | Description |
|------|------|-------------|
| `ExpInvolution(θ, P, ty)` | A → A | exp(iθ·P) where P : A → A is involution |
| `ExpSwap(θ, i, j, ty)` | Q⊗Q → Q⊗Q | Atomic exp(iθ·SWAP) on wires i, j |

**Signatures:**
```python
ExpInvolution(theta: float, body: Term, ty_total: Ty) -> Term
# Requires: body : A → A and body² = id
# Returns: term of type A → A

ExpSwap(theta: float, i: int, j: int, ty_total: Ty) -> Term
# Returns: term of type ty_total → ty_total
```

**ExpSwap unitary:**
```
exp(iθ · SWAP) = cos(θ)·I + i·sin(θ)·SWAP
```

**ExpInvolution compilation:**
1. Compile body P to WirePerm π
2. Verify π² = identity (involutive)
3. Decompose π into disjoint transpositions (a₁,b₁), (a₂,b₂), ...
4. Emit `ExpSwap(θ, aₖ, bₖ)` for each transposition

### Qubit Encoding Isomorphism

| Term | Type | Description |
|------|------|-------------|
| `EncodeQubit()` | Q → I + I | Encode primitive qubit to one-hot |
| `DecodeQubit()` | I + I → Q | Decode one-hot back to primitive qubit |

**Signatures:**
```python
EncodeQubit() -> Term
# Returns: term of type Q → (I ⊕ I)

DecodeQubit() -> Term
# Returns: term of type (I ⊕ I) → Q
```

**Circuits:**
- `encode`: CX[0,1]; X[0] — maps |0⟩⊗|0⟩ → |10⟩, |1⟩⊗|0⟩ → |01⟩
- `decode`: X[0]; CX[0,1] — maps |10⟩ → |0⟩⊗|0⟩, |01⟩ → |1⟩⊗|0⟩

**Properties:**
- `encode ; decode = id` on Q ⊗ |0⟩ subspace
- `decode ; encode = id` on valid I+I states (|01⟩, |10⟩)
- Superposition preserved through roundtrip

**Note:** The ancilla (wire 1) must be |0⟩ for encode, and is returned to |0⟩ by decode.

### Higher-Order Terms

| Term | Description |
|------|-------------|
| `Feedback(k, body)` | Loop k wires back (GOI trace) |
| `FunVar(name, dom, cod)` | Function variable |
| `Lam(name, dom, cod, body)` | Lambda abstraction |
| `Apply(f, arg)` | Function application |

---

## Compilation (`src/compile/to_pytket.py`)

### compile()

Standard compilation to pytket circuit.

```python
from compile.to_pytket import compile, Compiled

result: Compiled = compile(term, materialize=False, explain=False)

# Result fields:
result.circuit   # pytket Circuit
result.perm      # WirePerm (final wire permutation)
result.log       # List[str] if explain=True
```

### compile_goi()

Compilation with feedback support.

```python
from compile.to_pytket import compile_goi
from compile.goi import GOIArtifact

result = compile_goi(term, materialize=False, explain=False)

# Returns Compiled if feedback extracted, GOIArtifact if residual
if isinstance(result, GOIArtifact):
    print("Residual loops:", result.loops)
else:
    print("Extracted:", result.circuit)
```

### compile_higher_order()

Higher-order compilation via GOI.

```python
from compile.to_pytket import compile_higher_order

result = compile_higher_order(term, explain=False)
```

---

## Permutations (`src/core/perm.py`)

```python
from core.perm import WirePerm, identity, compose, inverse, is_involution, decompose_involution

p = WirePerm([1, 0, 2])      # new_to_old mapping
e = identity(n)              # Identity permutation
q = compose(p2, p1)          # Composition
inv = inverse(p)             # Inverse

old_idx = p.apply_new_to_old(new_idx)
```

### Involution Functions

```python
from core.perm import is_involution, decompose_involution

# Check if permutation is involutive (p ∘ p = id)
is_involution(p: WirePerm) -> bool

# Decompose involution into disjoint transpositions
# Requires: is_involution(p) == True
decompose_involution(p: WirePerm) -> List[Tuple[int, int]]
```

**Example:**
```python
p = WirePerm([1, 0, 3, 2])   # Two swaps: (0,1) and (2,3)
assert is_involution(p)
swaps = decompose_involution(p)  # [(0, 1), (2, 3)]
```

---

## Type Checking (`src/typing_/check.py`)

```python
from typing_.check import type_of, assert_well_typed

dom, cod = type_of(term)     # Get domain and codomain
assert_well_typed(term)      # Raises TypeCheckError if invalid
```

---

## GOI Module (`src/compile/goi.py`)

```python
from compile.goi import (
    GateAtom,
    GOIArtifact,
    LoopSpec,
    make_unitary_value,
    goi_seq,
    execute_trace,
)

# Create GOI representation of a unitary
h_goi = make_unitary_value('H', (0,), n_a=1, inverse_gate_name='H')

# Compose via GOI
composed = goi_seq(h_goi, s_goi, n_shared=1)

# Execute trace (collapse loops)
result = execute_trace(composed)
```

---

## Example: Complete Workflow

```python
from lang.types import Q, Ten
from lang.terms import Seq, H, CX
from compile.to_pytket import compile

# Build term
ty = Ten(Q(), Q())
bell = Seq(H(0, ty), CX(0, 1, ty))

# Compile
result = compile(bell)

# Inspect
print(f"Qubits: {result.circuit.n_qubits}")
print(f"Gates: {result.circuit.n_gates}")
for cmd in result.circuit.get_commands():
    print(f"  {cmd}")
```

---

## Example: Exponential of Involution

```python
from lang.types import Q, Plus
from lang.terms import TwistPlus, ExpInvolution
from compile.to_pytket import compile

# TwistPlus(Q, Q) is involutive: swap ∘ swap = id
ty = Plus(Q(), Q())
twist = TwistPlus(Q(), Q())

# exp(i * 0.5 * twist)
term = ExpInvolution(theta=0.5, body=twist, ty_total=ty)
result = compile(term)

# Produces ExpSwap gates for each transposition in the permutation
```

---

## Invariants

1. **Structural = pure permutation** — no gates, only wire reordering (one-hot encoding)
2. **No SWAPs by default** — only with `materialize=True`
3. **Gates are reindexed** — through `WirePerm.apply_new_to_old()`
4. **Deterministic** — same AST → identical circuit
5. **Involution certification** — ExpInvolution verifies π² = id at compile time

---

## Test Coverage

1169+ tests across all phases.
