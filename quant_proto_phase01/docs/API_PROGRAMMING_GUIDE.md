# QPL Compiler API Programming Guide

Practical reference for building and compiling quantum programs.

---

## 1. Entry Points + Result Shapes

### compile() — Phases 0–2

```python
from compile.to_pytket import compile, Compiled

result = compile(term, materialize=False)
# Returns: Compiled(circuit, perm, log=None)
```

**Result shape:**
```python
@dataclass(frozen=True)
class Compiled:
    circuit: pytket.Circuit
    perm: WirePerm
    log: Optional[List[str]] = None  # if explain=True
```

**Usage:**
```python
result = compile(term, materialize=False)
circ = result.circuit   # pytket Circuit
perm = result.perm      # WirePerm
```

### compile_goi() — Phase 3 (with Feedback)

```python
from compile.to_pytket import compile_goi, CompiledGOI
from compile.goi import GOIArtifact

result = compile_goi(term, materialize=False)
# Returns: CompiledGOI | GOIArtifact
```

**Distinguishing extracted vs residual:**
```python
from compile.goi import GOIArtifact

if isinstance(result, GOIArtifact):
    # Residual — extraction failed, feedback not eliminated
    print("Residual GOI:", result.loops, result.atoms)
else:
    # Extracted — success
    circ = result.circuit
    perm = result.perm
```

**Result shapes:**
```python
@dataclass(frozen=True)
class CompiledGOI:
    circuit: pytket.Circuit
    perm: WirePerm
    log: Optional[List[str]] = None

@dataclass(frozen=True)
class GOIArtifact:
    n_in: int
    n_out: int
    perm: WirePerm
    atoms: Tuple[GateAtom, ...]
    loops: Tuple[LoopSpec, ...]
```

---

## 2. Term Constructors / AST Nodes

### Type Constructors

```python
from lang.types import Q, Ten, Plus, width

# Atomic qubit type
q = Q()                      # width 1

# Tensor (parallel)
t = Ten(Q(), Q())            # Q ⊗ Q, width 2
t3 = Ten(Ten(Q(), Q()), Q()) # (Q ⊗ Q) ⊗ Q, width 3

# Sum (coproduct)
s = Plus(Q(), Q())           # Q ⊕ Q, width 2

# Get width
w = width(t)                 # returns 2
```

**Helper for Q^n:**
```python
def qpow(n: int):
    """Build Q ⊗ Q ⊗ ... ⊗ Q (n times, right-associated)."""
    ty = Q()
    for _ in range(n - 1):
        ty = Ten(ty, Q())
    return ty

ty4 = qpow(4)  # 4-qubit type
```

### Term Constructors

```python
from lang.terms import (
    # Basic
    Id, Seq, TenTerm,
    # Structural (tensor)
    TwistTen, AssocTenL, AssocTenR,
    # Structural (sum)
    TwistPlus, AssocPlusL, AssocPlusR,
    # Distributivity (structural with tagged layout)
    DistL, DistR,
    # Gates
    H, S, CX,
    # Phase 3 feedback
    Feedback,
)
```

#### Identity
```python
Id(ty)                       # id : ty → ty
```

#### Sequential Composition
```python
Seq(f, g)                    # f ; g (binary)
Seq(f, g, h)                 # f ; (g ; h) (variadic)
Seq(f, g, h, i)              # f ; (g ; (h ; i))
```

#### Tensor / Parallel Composition
```python
TenTerm(f, g)                # f ⊗ g
```

#### Structural Isomorphisms (Tensor)
```python
TwistTen(a, b)               # twist : a ⊗ b → b ⊗ a
AssocTenL(a, b, c)           # assocL : (a ⊗ b) ⊗ c → a ⊗ (b ⊗ c)
AssocTenR(a, b, c)           # assocR : a ⊗ (b ⊗ c) → (a ⊗ b) ⊗ c
```

#### Structural Isomorphisms (Sum)
```python
TwistPlus(a, b)              # twist : a ⊕ b → b ⊕ a
AssocPlusL(a, b, c)          # assocL : (a ⊕ b) ⊕ c → a ⊕ (b ⊕ c)
AssocPlusR(a, b, c)          # assocR : a ⊕ (b ⊕ c) → (a ⊕ b) ⊕ c
```

#### Gate Constructors
```python
# Single-qubit gates
H(i, ty_total)               # Hadamard on wire i
S(i, ty_total)               # S (phase) on wire i

# Two-qubit gate
CX(i, j, ty_total)           # CNOT: control i, target j

# Defaults (for 2-qubit context)
H()                          # H(0, Ten(Q(), Q()))
H(0)                         # H(0, Ten(Q(), Q()))
S(1)                         # S(1, Ten(Q(), Q()))
CX()                         # CX(0, 1, Ten(Q(), Q()))
```

**Examples:**
```python
ty = qpow(3)                 # 3-qubit type

# H on wire 0 of 3-qubit system
h = H(0, ty)

# CX from wire 1 to wire 2
cx = CX(1, 2, ty)

# Sequence: H then CX
prog = Seq(H(0, ty), CX(0, 1, ty))
```

#### Phase 3: Feedback
```python
Feedback(k, body)            # Feedback_k(body)
```

Where:
- `body` has type `(A ⊗ X) → (B ⊗ X)` with `width(X) = k`
- Result has type `A → B`

**Example:**
```python
ty = qpow(3)                 # 3 wires
body = Seq(H(0, ty), S(1, ty))  # gates on wires 0,1 only
term = Feedback(k=1, body=body) # loop wire 2 back
# Result type: 2 wires (external)
```

### Name Aliases

These aliases are also exported for convenience:
```python
TensorTwist = TwistTen
TensorAssocL = AssocTenL
TensorAssocR = AssocTenR
SumTwist = TwistPlus
SumAssocL = AssocPlusL
SumAssocR = AssocPlusR
```

---

## 3. Circuit Command Stream Extraction

The circuit is a **pytket Circuit**. Extract commands canonically:

```python
# Get all commands
commands = circ.get_commands()

# For each command:
for cmd in commands:
    op_name = cmd.op.type.name      # "H", "S", "CX", "SWAP", etc.
    qubits = [q.index[0] for q in cmd.qubits]  # wire indices
    print(f"{op_name}({qubits})")
```

**Canonical serialization helper:**
```python
def extract_cmd_stream(circ) -> list[str]:
    """Canonical command stream for determinism checks."""
    result = []
    for cmd in circ.get_commands():
        name = cmd.op.type.name
        wires = [q.index[0] for q in cmd.qubits]
        result.append(f"{name}({','.join(map(str, wires))})")
    return result

# Usage:
stream = extract_cmd_stream(result.circuit)
# ['H(0)', 'CX(0,1)', 'S(1)']
```

**Compare two circuits:**
```python
def circuits_equal(c1, c2) -> bool:
    return extract_cmd_stream(c1) == extract_cmd_stream(c2)
```

---

## 4. WirePerm Inspection

```python
from core.perm import WirePerm, identity, compose, inverse

# Access permutation data
perm.n                       # number of wires
perm.new_to_old              # list: new_position → old_position

# Apply permutation
old_wire = perm.apply_new_to_old(new_wire)

# Construct permutations
p = WirePerm([1, 0, 2, 3])           # from list (n inferred)
p = WirePerm(4, [1, 0, 2, 3])        # explicit n + list
p = WirePerm(n=4, new_to_old=[1,0,2,3])  # keyword args

# Identity permutation
p = identity(4)              # [0, 1, 2, 3]

# Compose: (q ∘ p)[i] = p[q[i]]
p3 = compose(q, p)

# Inverse
p_inv = inverse(p)

# Restrict to subset of wires
p_sub = perm.restrict({0, 1, 2})  # new perm on 3 wires
```

**Inspect permutation:**
```python
result = compile(term)
perm = result.perm

print(f"Width: {perm.n}")
print(f"Mapping: {perm.new_to_old}")

# Check if identity
is_identity = (perm.new_to_old == list(range(perm.n)))
```

**Get width from types:**
```python
from lang.types import width
from typing_.check import type_of

dom, cod = type_of(term)
n = width(dom)
```

---

## 5. SWAP Detection ("No SWAPs by Default")

SWAPs are pytket SWAP gates. Detect by checking `cmd.op.type.name`:

```python
def has_swaps(circ) -> bool:
    """Check if circuit contains any SWAP gates."""
    for cmd in circ.get_commands():
        if cmd.op.type.name.upper() == "SWAP":
            return True
    return False

def assert_no_swaps(circ):
    """Assert circuit has no SWAPs."""
    swaps = [cmd for cmd in circ.get_commands()
             if cmd.op.type.name.upper() == "SWAP"]
    assert not swaps, f"Found SWAPs: {swaps}"

def count_swaps(circ) -> int:
    """Count SWAP gates in circuit."""
    return sum(1 for cmd in circ.get_commands()
               if cmd.op.type.name.upper() == "SWAP")
```

**Invariant:**
- `compile(term, materialize=False)` → **never has SWAPs**
- `compile(term, materialize=True)` → may have SWAPs (to realize permutation)
- `compile_goi(term, materialize=False)` → **no SWAPs if extracted**
- Residual GOIArtifact has no circuit (no SWAPs possible)

---

## 6. Complete Working Examples

### Example 1: Basic Compilation
```python
from lang.types import Q, Ten, width
from lang.terms import Seq, TwistTen, H, S, CX
from compile.to_pytket import compile

# Build 2-qubit type
ty = Ten(Q(), Q())

# Build program: twist then H on wire 0
prog = Seq(TwistTen(Q(), Q()), H(0, ty))

# Compile
result = compile(prog, materialize=False)

# Inspect
print(f"Commands: {[c.op.type.name for c in result.circuit.get_commands()]}")
print(f"Perm: {result.perm.new_to_old}")

# No SWAPs
assert not any(c.op.type.name == "SWAP" for c in result.circuit.get_commands())
```

### Example 2: Phase 3 Feedback
```python
from lang.types import Q, Ten
from lang.terms import Seq, Feedback, H, S
from compile.to_pytket import compile_goi
from compile.goi import GOIArtifact

def qpow(n):
    ty = Q()
    for _ in range(n - 1):
        ty = Ten(ty, Q())
    return ty

# 3-qubit body, loop 1 wire
ty = qpow(3)
body = Seq(H(0, ty), S(1, ty))  # gates on wires 0,1 only
term = Feedback(k=1, body=body)

result = compile_goi(term)

if isinstance(result, GOIArtifact):
    print("Residual - gates touch loop wires")
    print(f"Atoms: {result.atoms}")
    print(f"Loops: {result.loops}")
else:
    print("Extracted!")
    print(f"Circuit width: {result.perm.n}")  # 2 (external)
    print(f"Commands: {[c.op.type.name for c in result.circuit.get_commands()]}")
```

### Example 3: Determinism Check
```python
from compile.to_pytket import compile

# Same term compiled twice should be identical
r1 = compile(prog)
r2 = compile(prog)

# Compare command streams
def cmd_stream(circ):
    return [(c.op.type.name, [q.index[0] for q in c.qubits])
            for c in circ.get_commands()]

assert cmd_stream(r1.circuit) == cmd_stream(r2.circuit)
assert r1.perm.new_to_old == r2.perm.new_to_old
```

---

## 7. Quick Import Reference

```python
# Types
from lang.types import Q, Ten, Plus, width

# Terms
from lang.terms import (
    Id, Seq, TenTerm,
    TwistTen, AssocTenL, AssocTenR,
    TwistPlus, AssocPlusL, AssocPlusR,
    H, S, CX,
    Feedback,  # Phase 3
)

# Type checking
from typing_.check import type_of, assert_well_typed

# Compilation
from compile.to_pytket import compile, compile_goi, Compiled, CompiledGOI

# Permutations
from core.perm import WirePerm, identity, compose, inverse

# GOI (Phase 3)
from compile.goi import GOIArtifact, GateAtom, LoopSpec

# Materialization
from backends.materialize import swaps_for_perm, apply_swaps
```

---

## 8. Summary Table

| What | How |
|------|-----|
| Compile (Phases 0-2) | `compile(term) → Compiled(circuit, perm)` |
| Compile (Phase 3) | `compile_goi(term) → CompiledGOI \| GOIArtifact` |
| Check if residual | `isinstance(result, GOIArtifact)` |
| Get commands | `circ.get_commands()` |
| Get op name | `cmd.op.type.name` |
| Get wire indices | `[q.index[0] for q in cmd.qubits]` |
| Get perm mapping | `perm.new_to_old` |
| Apply perm | `perm.apply_new_to_old(i)` |
| Check for SWAP | `cmd.op.type.name.upper() == "SWAP"` |
| Get type width | `width(ty)` |
| Get term type | `type_of(term) → (dom, cod)` |
