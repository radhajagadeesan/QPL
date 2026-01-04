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
s = Plus(Q(), Q())      # Q + Q (width 3: 1 tag + 2 data)

w = width(qq)           # Returns 2
```

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
from lang.terms import H, S, X, Y, Z, T, CX, CS, Rz

# All gates take wire index and ambient type
ty = Ten(Q(), Q())

H(0, ty)                # Hadamard on wire 0
S(1, ty)                # S gate on wire 1
CX(0, 1, ty)            # CNOT: control 0, target 1
CS(0, 1, ty)            # Controlled-S
Rz(0.5, 0, ty)          # Rz(0.5) on wire 0
```

### Structural Primitives

```python
from lang.terms import TwistTen, TwistPlus, AssocTenL, AssocTenR

TwistTen(a, b)          # a ⊗ b → b ⊗ a
TwistPlus(a, b)         # a + b → b + a
AssocTenL(a, b, c)      # (a ⊗ b) ⊗ c → a ⊗ (b ⊗ c)
AssocTenR(a, b, c)      # a ⊗ (b ⊗ c) → (a ⊗ b) ⊗ c
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
