# API Reference (Phase 0–1)

This document provides the complete API reference for the Phase 0–1 structural quantum compiler.

---

## Quick Answers

### 1. TenTerm name + signature

**Location:** `src/lang/terms.py`

```python
from lang.terms import TenTerm

# Constructor signature:
TenTerm(f: Term, g: Term)
```

- `TenTerm` represents parallel composition: `f ⊗ g`
- Both arguments are `Term` objects (not types or sizes)
- Types are inferred from the sub-terms

---

### 2. Gate constructor signatures

**Location:** `src/lang/terms.py`

```python
from lang.terms import H, S, CX

# Hadamard gate on wire i
H(i: int = 0, ty_total: Ty = Ten(Q(), Q()))

# S (phase) gate on wire i
S(i: int = 0, ty_total: Ty = Ten(Q(), Q()))

# Controlled-X with control i, target j
CX(i: int = 0, j: int = 1, ty_total: Ty = Ten(Q(), Q()))
```

**Notes:**
- All gates have **default arguments** for 2-qubit context
- `i`, `j` are **integer wire indices** (0-based)
- `ty_total` is the **ambient type** of the whole circuit
- For n-qubit circuits, pass the appropriate type: `ty_total=Ten(Ten(Q(), Q()), Q())` for 3 qubits

**Examples:**
```python
# 2-qubit circuit (uses defaults)
H()          # H on wire 0
CX()         # CX on wires 0, 1
S(1)         # S on wire 1

# 3-qubit circuit (explicit type)
ty3 = Ten(Ten(Q(), Q()), Q())
H(0, ty3)
CX(0, 2, ty3)
S(2, ty3)
```

---

### 3. Compiler entrypoint

**Location:** `src/compile/to_pytket.py`

```python
from compile.to_pytket import compile, Compiled

result: Compiled = compile(term, *, materialize=False, explain=False)
```

**Signature:**
```python
def compile(
    term: Term,
    *,
    materialize: bool = False,  # If True, insert SWAPs for final perm
    explain: bool = False       # If True, populate result.log
) -> Compiled
```

**Returns:** `Compiled` object (not a raw Circuit)

```python
@dataclass
class Compiled:
    circuit: Circuit      # pytket Circuit
    perm: WirePerm        # Final wire permutation
    log: Optional[List[str]]  # Explanation log (if explain=True)
```

**Example:**
```python
from compile.to_pytket import compile
from lang.terms import Seq, H, CX, TwistTen
from lang.types import Q

prog = Seq(TwistTen(Q(), Q()), H(), CX())
result = compile(prog)

circ = result.circuit   # pytket Circuit
perm = result.perm      # WirePerm showing final wire mapping
```

---

### 4. Materializer entrypoint

**Location:** `src/backends/materialize.py`

```python
from backends.materialize import swaps_for_perm, apply_swaps

# Step 1: Convert WirePerm to list of swap pairs
swaps: List[Tuple[int, int]] = swaps_for_perm(perm)

# Step 2: Apply swaps to circuit
apply_swaps(circ, swaps)
```

**Signatures:**
```python
def swaps_for_perm(p: WirePerm) -> List[Tuple[int, int]]
def apply_swaps(circ: Circuit, swaps: List[Tuple[int, int]]) -> None
```

**Notes:**
- There is **no single `materialize(circ, perm)` function**
- Use the two-step API: `swaps_for_perm()` then `apply_swaps()`
- Or use `compile(term, materialize=True)` to do it automatically

**Example:**
```python
from compile.to_pytket import compile
from backends.materialize import swaps_for_perm, apply_swaps

result = compile(prog, materialize=False)
circ = result.circuit.copy()
swaps = swaps_for_perm(result.perm)
apply_swaps(circ, swaps)
# circ now contains explicit SWAP gates
```

---

### 5. How pytket is exposed

**Yes, standard pytket API is used:**

```python
from pytket.circuit import Circuit

circ = Circuit(n)           # Create n-qubit circuit
circ.H(qubit)               # Add Hadamard
circ.S(qubit)               # Add S gate
circ.CX(control, target)    # Add CNOT
circ.SWAP(a, b)             # Add SWAP

cmds = circ.get_commands()  # Get list of commands
for cmd in cmds:
    op_type = cmd.op.type   # OpType enum
    qubits = cmd.qubits     # List of Qubit objects
```

**Introspection:**
```python
for cmd in circ.get_commands():
    op_name = cmd.op.type.name  # "H", "S", "CX", "SWAP"
    qubit_indices = [q.index[0] for q in cmd.qubits]
```

---

## Complete API Reference

### Types (`src/lang/types.py`)

| Type | Description | Example |
|------|-------------|---------|
| `Q()` | Single qubit wire | `Q()` |
| `Ten(a, b)` | Tensor product a ⊗ b | `Ten(Q(), Q())` |
| `Plus(a, b)` | Sum type a ⊕ b | `Plus(Q(), Q())` |

**Utility functions:**
```python
width(ty: Ty) -> int          # Number of physical wires
pretty(ty: Ty) -> str         # Pretty-print type
flatten_tensor(ty) -> List    # Flatten tensor tree
flatten_plus(ty) -> List      # Flatten plus tree
```

---

### Terms (`src/lang/terms.py`)

#### Identity and Composition
| Term | Signature | Description |
|------|-----------|-------------|
| `Id(ty)` | `Id(ty: Ty)` | Identity on type |
| `Seq(f, g, ...)` | `Seq(f, g, *rest)` | Sequential composition (variadic) |
| `TenTerm(f, g)` | `TenTerm(f: Term, g: Term)` | Parallel composition f ⊗ g |

#### Structural Isomorphisms (Tensor)
| Term | Type Signature |
|------|----------------|
| `TwistTen(a, b)` | `a ⊗ b → b ⊗ a` |
| `AssocTenL(a, b, c)` | `(a ⊗ b) ⊗ c → a ⊗ (b ⊗ c)` |
| `AssocTenR(a, b, c)` | `a ⊗ (b ⊗ c) → (a ⊗ b) ⊗ c` |

**Aliases:** `TensorTwist`, `TensorAssocL`, `TensorAssocR`

#### Structural Isomorphisms (Sum)
| Term | Type Signature |
|------|----------------|
| `TwistPlus(a, b)` | `a ⊕ b → b ⊕ a` |
| `AssocPlusL(a, b, c)` | `(a ⊕ b) ⊕ c → a ⊕ (b ⊕ c)` |
| `AssocPlusR(a, b, c)` | `a ⊕ (b ⊕ c) → (a ⊕ b) ⊕ c` |

**Aliases:** `SumTwist`, `SumAssocL`, `SumAssocR`

#### Distributivity (Typed but NOT compiled in Phase 0–1)
| Term | Type Signature |
|------|----------------|
| `DistL(a, b, c)` | `(a ⊕ b) ⊗ c → (a ⊗ c) ⊕ (b ⊗ c)` |
| `DistR(a, b, c)` | `a ⊗ (b ⊕ c) → (a ⊗ b) ⊕ (a ⊗ c)` |

**Note:** Compilation raises `NotImplementedError` for distributivity.

#### Gates
| Gate | Signature | Description |
|------|-----------|-------------|
| `H(i, ty_total)` | `H(i=0, ty_total=Ten(Q(),Q()))` | Hadamard on wire i |
| `S(i, ty_total)` | `S(i=0, ty_total=Ten(Q(),Q()))` | S gate on wire i |
| `CX(i, j, ty_total)` | `CX(i=0, j=1, ty_total=Ten(Q(),Q()))` | CNOT control=i, target=j |

---

### Permutations (`src/core/perm.py`)

```python
from core.perm import WirePerm, identity, compose, inverse

# Construction (flexible)
p = WirePerm([1, 0, 2, 3])           # From list
p = WirePerm(4, [1, 0, 2, 3])        # With explicit n
p = WirePerm(n=4, new_to_old=[...])  # Keyword args

# Operations
e = identity(n)           # Identity permutation
q = compose(p2, p1)       # Composition: p2 ∘ p1
inv = inverse(p)          # Inverse permutation

# Application
old_idx = p.apply_new_to_old(new_idx)
```

---

### Type Checking (`src/typing_/check.py`)

```python
from typing_.check import type_of, assert_well_typed, TypeCheckError

dom, cod = type_of(term)    # Get domain and codomain types
assert_well_typed(term)     # Raises TypeCheckError if ill-typed
```

---

## Example: Complete Workflow

```python
from lang.types import Q, Ten
from lang.terms import Seq, H, CX, TwistTen
from compile.to_pytket import compile
from backends.materialize import swaps_for_perm, apply_swaps

# 1. Define types
ty2 = Ten(Q(), Q())

# 2. Build program
prog = Seq(
    TwistTen(Q(), Q()),   # Swap wires
    H(0, ty2),            # H on wire 0
    CX(0, 1, ty2),        # CNOT
)

# 3. Compile (no SWAPs in output)
result = compile(prog)
print(f"Circuit: {result.circuit}")
print(f"Final perm: {result.perm}")

# 4. Optionally materialize SWAPs
result_mat = compile(prog, materialize=True)
print(f"With SWAPs: {result_mat.circuit}")
```

---

## Invariants (Phase 0–1)

1. **Structure = metadata only**: Structural terms emit NO gates
2. **No SWAPs by default**: `compile()` never emits SWAPs unless `materialize=True`
3. **Gates are reindexed**: Gate wires go through `WirePerm.apply_new_to_old()`
4. **Deterministic**: Same AST → identical circuit
5. **Distributivity deferred**: Raises `NotImplementedError`

---

End of API Reference.
