# Granthi Compiler API Guide

This guide is for developers extending or embedding the Granthi compiler. It explains the Python core API, compilation functions, and higher-order compilation hooks.

For surface language programming, see `PROGRAMMING_GUIDE.md`.
For IR architecture details, see `TWO_LEVEL_IR_DESIGN.md`.

---

## Overview

The compiler has two entry points:

| Entry Point | Language | Use Case |
|-------------|----------|----------|
| Surface language | OCaml | User programs with natural syntax |
| Core API | Python | Programmatic AST construction, compiler embedding |

Both produce identical circuits via the same compilation pipeline.

---

## Core API: Types

```python
from lang.types import Q, I, Ten, Plus, width

q = Q()                 # Qubit (width 1)
u = I()                 # Unit (width 0)
qq = Ten(Q(), Q())      # Q ⊗ Q (width 2)
s = Plus(Q(), Q())      # Q + Q (width 4: 2 tags + 2 data, one-hot encoding)

w = width(qq)           # Returns 2
w = width(s)            # Returns 4
```

### One-Hot Sum Encoding

Sum types use one-hot leaf-tag encoding:
- Binary `Plus(A, B)` has width = 2 + width(A) + width(B)
- Nested sums flatten: `Plus(Plus(Q,Q), Q)` has width 6 (3 tags + 3 data)
- Wire layout: `[tags... | payloads...]`

This makes all structural operations on sums compile to pure permutations.

---

## Core API: Terms

### Composition

```python
from lang.terms import Id, Seq, TenTerm

Id(ty)                  # Identity on type
Seq(f, g)               # Sequential: f ; g
Seq(f, g, h)            # Variadic: f ; g ; h
TenTerm(f, g)           # Parallel: f ⊗ g
```

### Gates

```python
from lang.terms import H, S, X, Y, Z, T, Tdg, Sdg, CX, CZ, CS, CH, CCX, Rz, Rx, Ry

# All gates take wire index and ambient type
ty = Ten(Q(), Q())

# Single-qubit
H(0, ty)                # Hadamard on wire 0
S(1, ty)                # S gate on wire 1
X(0, ty), Y(0, ty), Z(0, ty)  # Pauli gates
T(0, ty), Tdg(0, ty)    # T and T-dagger
Sdg(0, ty)              # S-dagger

# Two-qubit
CX(0, 1, ty)            # CNOT: control 0, target 1
CZ(0, 1, ty)            # Controlled-Z
CS(0, 1, ty)            # Controlled-S
CH(0, 1, ty)            # Controlled-H

# Parameterized
Rz(0.5, 0, ty)          # Rz(θ) on wire 0
Rx(0.5, 0, ty)          # Rx(θ) on wire 0
Ry(0.5, 0, ty)          # Ry(θ) on wire 0

# Three-qubit
ty3 = Ten(Ten(Q(), Q()), Q())
CCX(0, 1, 2, ty3)       # Toffoli
```

### Structural Primitives

All structural primitives compile to **pure wire permutations** (no gates).

```python
from lang.terms import (
    TwistTen, TwistPlus,
    AssocTenL, AssocTenR, AssocPlusL, AssocPlusR,
    DistL, DistR
)

# Tensor isomorphisms
TwistTen(a, b)          # a ⊗ b → b ⊗ a
AssocTenL(a, b, c)      # (a ⊗ b) ⊗ c → a ⊗ (b ⊗ c)
AssocTenR(a, b, c)      # a ⊗ (b ⊗ c) → (a ⊗ b) ⊗ c

# Sum isomorphisms (pure permutations with one-hot encoding)
TwistPlus(a, b)         # a + b → b + a (swaps tags and data)
AssocPlusL(a, b, c)     # (a + b) + c → a + (b + c)
AssocPlusR(a, b, c)     # a + (b + c) → (a + b) + c

# Distributivity (pure permutations)
DistL(a, b, c)          # (a + b) ⊗ c → (a ⊗ c) + (b ⊗ c)
DistR(a, b, c)          # a ⊗ (b + c) → (a ⊗ b) + (a ⊗ c)
```

### Exponentials of Involutions

```python
from lang.terms import ExpSwap, ExpInvolution

# Atomic exponential of SWAP
ExpSwap(theta, i, j, ty)  # exp(iθ · SWAP) on wires i, j

# Exponential of structural involution
# P must compile to involutive permutation (π² = id)
ExpInvolution(theta, body, ty)  # exp(iθ · P)
```

At compile time, `ExpInvolution`:
1. Compiles body P to WirePerm π
2. Verifies π is involutive (π² = identity)
3. Decomposes π into disjoint transpositions
4. Emits `ExpSwap(θ, a, b)` for each transposition (a, b)

---

## Permutation Module

```python
from core.perm import WirePerm, is_involution, decompose_involution

# Create permutation
p = WirePerm([1, 0])    # Swap wires 0 and 1

# Check involution
assert is_involution(p)  # p ∘ p = identity

# Decompose into transpositions
swaps = decompose_involution(p)  # [(0, 1)]
```

---

## Compilation

### Basic Compilation

```python
from compile.to_pytket import compile, Compiled

result: Compiled = compile(term, materialize=False, explain=False)

# Result fields:
result.circuit          # pytket Circuit
result.perm             # WirePerm (final wire permutation)
result.log              # List[str] if explain=True
```

### With Feedback (GOI)

```python
from lang.terms import Feedback
from compile.to_pytket import compile_goi
from compile.goi import GOIArtifact

# Feedback loops k wires back
term = Feedback(k=1, body=body)

result = compile_goi(term, materialize=False)

if isinstance(result, GOIArtifact):
    # Residual: feedback could not be eliminated
    print("Loops:", result.loops)
else:
    # Extracted: collapsed to flat circuit
    print("Circuit:", result.circuit)
```

### Higher-Order Compilation

```python
from compile.to_pytket import compile_higher_order

result = compile_higher_order(term, explain=False)
```

Higher-order compilation uses the Geometry of Interaction (GOI) representation where a morphism `f : A → B` becomes an endomorphism on `A* ⊗ B`.

---

## GOI Module

For direct GOI manipulation:

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
# U : A → A becomes (U† ⊗ U) on A* ⊗ A
h_goi = make_unitary_value('H', (0,), n_a=1, inverse_gate_name='H')
s_goi = make_unitary_value('S', (0,), n_a=1, inverse_gate_name='Sdg')

# Compose via GOI (uses feedback internally)
composed = goi_seq(h_goi, s_goi, n_shared=1)

# Execute trace to collapse loop wires
result = execute_trace(composed)
```

---

## Involution Certification (exp_i)

The compiler provides involution checking for `ExpInvolution`:

```python
from lang.terms import TwistPlus, ExpInvolution
from lang.types import Q, Plus
from compile.to_pytket import compile

# TwistPlus is involutive: swap ∘ swap = id
twist = TwistPlus(Q(), Q())
ty = Plus(Q(), Q())

# Create exp(iθ · twist)
term = ExpInvolution(theta=0.5, body=twist, ty_total=ty)

# Compile - verifies involution and emits ExpSwap atoms
result = compile(term)
```

If the body is not involutive, compilation raises an error:
```
InvolutionError: ExpInvolution body must be involutive (π² ≠ id)
```

---

## Example: Building and Compiling

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

## Example: QSwitch via Core API

```python
from lang.terms import H, S, Seq, CS, X
from lang.types import Q, Ten
from compile.to_pytket import compile

ty = Ten(Q(), Q())

# QSwitch(H, S): X; CS; X; H; CS
# Applies S;H if ctrl=0, H;S if ctrl=1
qswitch_hs = Seq(
    X(0, ty),
    CS(0, 1, ty),
    X(0, ty),
    H(1, ty),
    CS(0, 1, ty),
)

result = compile(qswitch_hs)
# 5 gates on 2 qubits
```

---

## Example: Structural Operations

```python
from lang.types import Q, Plus
from lang.terms import TwistPlus, DistR
from compile.to_pytket import compile

a, b, c = Q(), Q(), Q()

# TwistPlus: Q + Q → Q + Q (pure permutation)
twist = TwistPlus(a, b)
result = compile(twist)
assert result.circuit.n_gates == 0  # No gates!
assert result.perm.new_to_old == [1, 0, 3, 2]  # Swaps tags and data

# DistR: Q ⊗ (Q + Q) → (Q ⊗ Q) + (Q ⊗ Q) (pure permutation)
dist = DistR(a, b, c)
result = compile(dist)
assert result.circuit.n_gates == 0  # No gates!
```

---

## Running Python Programs

```bash
cd quant_proto_phase01
PYTHONPATH=src python my_program.py
```

---

## Further Reading

- `API_REFERENCE.md` — Complete API signatures
- `TWO_LEVEL_IR_DESIGN.md` — IR architecture and GOI semantics
- `demos/qswitch_demo.py` — Working higher-order example
