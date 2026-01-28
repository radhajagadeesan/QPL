# Granthi API Reference

Complete reference for types, terms, and compilation functions.

---

## Types (`src/lang/types.py`)

| Type | Description | Width |
|------|-------------|-------|
| `Q()` | Single qubit | 1 |
| `I()` | Unit type | 0 |
| `Ten(a, b)` | Tensor product a ⊗ b | width(a) + width(b) |
| `Plus(a, b)` | Sum type a + b (Option B) | ceil(log2(n)) + max(width(Aᵢ)) |
| `Dual(a)` | Dual type a* | width(a) (self-dual) |

### Dual Type

`Dual(A)` represents the dual object A* in the compact-closed category.
Since all our types are self-dual, `width(Dual(A)) = width(A)`.

```python
from lang.types import Dual, dual, Q, Ten

Dual(Q())           # Q* — width 1
dual(Q())           # Same as Dual(Q())
dual(dual(Q()))     # Q — involutive: dual(dual(A)) = A
```

### Function Types

Function types `A → B` are equivalent to `A* ⊗ B ≡ A ⊗ B` (self-dual).

- In the **surface language** (OCaml): `TyArrow(A, B)`
- In the **Python IR**: represented as `Ten(A, B)` wires
- A function `Q → Q` is physically 2 wires (Q ⊗ Q)

Functions are **not closures** — they are circuit fragments with exposed dual input wires.

### Option B: Flat Log-Tag Encoding

Sum types use a flat log-sized tag register + shared payload:
- `Plus(A, B)` has ceil(log2(n)) tag qubits + max(width(Aᵢ)) shared payload
- Nested sums flatten: `Plus(Plus(Q,Q), Q)` = ceil(log2(3))=2 tags + max(1)=1 = 3 wires
- Wire layout: `[tag₀ | ... | tag_{k-1} | payload₀ | ... | payload_{W-1}]`
- Invariant: tag encodes index i < n; unused payload wires are |0⟩

**Functions:**
```python
from lang.types import Q, I, Ten, Plus, width, tag_width, payload_width

width(ty: Ty) -> int           # Number of physical wires
tag_width(ty: Ty) -> int       # Number of tag qubits (0 for non-Plus)
payload_width(ty: Ty) -> int   # Shared payload width (= width for non-Plus)
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

Tensor structurals compile to **pure wire permutations** (no gates).
Sum structurals compile to **symbolic tag permutations** (lowered to gates late).

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

### Compact-Closed Structure (Cups and Caps)

| Term | Type | Description |
|------|------|-------------|
| `Cup(ty)` | I → A ⊗ A* | Cup (unit introduction) — pure wiring, 0 gates |
| `Cap(ty)` | A* ⊗ A → I | Cap (counit / evaluation) — pure wiring, 0 gates |

Cups and caps are the compact-closed structure enabling higher-order programming.
Since all types are self-dual (A* = A), cup/cap are pure wire allocation/identification.

```python
from lang.terms import Cup, Cap
from lang.types import Q

Cup(Q())   # η_Q : I → Q ⊗ Q*  (allocate 2 wires)
Cap(Q())   # ε_Q : Q* ⊗ Q → I  (connect/identify 2 wires)
```

### Higher-Order Terms

| Term | Description |
|------|-------------|
| `FunVar(name, dom, cod)` | Function variable — identity on A ⊗ B wires |
| `Lam(name, dom, cod, body)` | Lambda abstraction — cup creates function wires |
| `Apply(f, arg)` | Function application — cap connects wires |
| `Feedback(k, body)` | Loop k wires back (GOI trace) |

Higher-order terms are compiled directly via cup/cap wiring — no GOI needed.
A function `A → B` is physically `A ⊗ B` wires. Lambda exposes wires, application connects them.

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

### compile_higher_order() *(deprecated)*

**Deprecated.** Use `compile()` instead — higher-order terms (Cup, Cap, FunVar, Lam, Apply) are now compiled directly via cup/cap wiring without GOI.

```python
# Old (deprecated):
from compile.to_pytket import compile_higher_order
result = compile_higher_order(term)  # emits DeprecationWarning

# New (preferred):
from compile.to_pytket import compile
result = compile(term)  # handles Cup, Cap, Lam, Apply directly
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

1. **Tensor structurals = pure permutation** — no gates, only wire reordering
2. **Sum structurals = symbolic tag rewrites** — tracked in TaggedPerm, lowered late
3. **No SWAPs by default** — only with `materialize=True`
4. **Gates are reindexed** — through `WirePerm.apply_new_to_old()`
5. **Deterministic** — same AST → identical circuit
6. **Involution certification** — ExpInvolution verifies π² = id at compile time

---

## Test Coverage

1211+ tests across all phases.
