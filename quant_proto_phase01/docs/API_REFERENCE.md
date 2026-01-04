# Granthi API Reference

Complete reference for types, terms, and compilation functions.

---

## Types (`src/lang/types.py`)

| Type | Description | Width |
|------|-------------|-------|
| `Q()` | Single qubit | 1 |
| `I()` | Unit type | 0 |
| `Ten(a, b)` | Tensor product a ⊗ b | width(a) + width(b) |
| `Plus(a, b)` | Sum type a + b | 1 + width(a) + width(b) |

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

**Three-qubit gates:**

| Gate | Signature | Description |
|------|-----------|-------------|
| `CCX(i, j, k, ty)` | Toffoli (controls i,j, target k) | |

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
from core.perm import WirePerm, identity, compose, inverse

p = WirePerm([1, 0, 2])      # new_to_old mapping
e = identity(n)              # Identity permutation
q = compose(p2, p1)          # Composition
inv = inverse(p)             # Inverse

old_idx = p.apply_new_to_old(new_idx)
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

## Invariants

1. **Structural = permutation + tag flips only** — no gates on payload wires
2. **No SWAPs by default** — only with `materialize=True`
3. **Gates are reindexed** — through `WirePerm.apply_new_to_old()`
4. **Deterministic** — same AST → identical circuit

---

## Test Coverage

1145+ tests across all phases.
