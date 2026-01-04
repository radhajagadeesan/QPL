# Granthi Programming Guide

## Overview

Granthi provides two ways to write quantum programs:

| Approach | Language | Best For |
|----------|----------|----------|
| **Surface Language** | OCaml | Natural syntax, datatypes, case expressions |
| **Core API** | Python | Programmatic generation, direct AST construction |

Both compile to the same core IR and produce identical circuits.

---

## Types

### Primitive Types

| Type | Description |
|------|-------------|
| `Q` | Qubit |
| `I` | Unit (no wires) |

### Type Constructors

| Constructor | Meaning |
|-------------|---------|
| `A ⊗ B` | Tensor product (parallel wires) |
| `A + B` | Sum type (tagged union) |

### Surface Language (OCaml)

```ocaml
Q                       (* Qubit *)
I                       (* Unit *)
A ⊗ B                   (* Tensor *)
A + B                   (* Sum *)
Bool['a, 'b]            (* Named datatype *)
```

### Core API (Python)

```python
from lang.types import Q, I, Ten, Plus

q = Q()                 # Qubit
u = I()                 # Unit
qq = Ten(Q(), Q())      # Q ⊗ Q
s = Plus(Q(), Q())      # Q + Q
```

### Datatypes (Surface Only)

Define custom sum types with constructors:

```ocaml
datatype Bool['a, 'b] = F of 'a | T of 'b
datatype Bit = Zero of I | One of I
datatype Maybe['a] = None of I | Some of 'a
```

---

## Terms

### Composition

| Surface | Python | Type |
|---------|--------|------|
| `f ; g` | `Seq(f, g)` | Sequential composition |
| `f ⊗ g` | `TenTerm(f, g)` | Parallel composition |

### Gates

| Surface | Python | Description |
|---------|--------|-------------|
| `H[i]` | `H(i, ty)` | Hadamard |
| `S[i]` | `S(i, ty)` | S gate |
| `X[i]` | `X(i, ty)` | Pauli X |
| `Y[i]` | `Y(i, ty)` | Pauli Y |
| `Z[i]` | `Z(i, ty)` | Pauli Z |
| `T[i]` | `T(i, ty)` | T gate |
| `CX[i,j]` | `CX(i, j, ty)` | CNOT |
| `CS[i,j]` | `CS(i, j, ty)` | Controlled-S |
| `Rz[θ,i]` | `Rz(theta, i, ty)` | Z rotation |

### Structural Primitives

| Surface | Python | Type Signature |
|---------|--------|----------------|
| `id[A]` | `Id(a)` | A → A |
| `twist⊗[A,B]` | `TwistTen(a, b)` | A ⊗ B → B ⊗ A |
| `twist+[A,B]` | `TwistPlus(a, b)` | A + B → B + A |
| `assoc⊗L[A,B,C]` | `AssocTenL(a, b, c)` | (A ⊗ B) ⊗ C → A ⊗ (B ⊗ C) |
| `assoc⊗R[A,B,C]` | `AssocTenR(a, b, c)` | A ⊗ (B ⊗ C) → (A ⊗ B) ⊗ C |

### Binding Forms (Surface Only)

```ocaml
λx:A. body              (* Lambda - compile-time only *)
let x = e1 in e2        (* Let binding *)
case e of               (* Case expression *)
  | F(x) => branch1
  | T(y) => branch2
```

### Higher-Order (Python Only)

```python
Feedback(k, body)       # Trace/loop k wires
```

---

## Examples

### Bell State

Surface:
```ocaml
def bell : Q ⊗ Q → Q ⊗ Q =
  H[0] ; CX[0, 1]
```

Python:
```python
from lang.types import Q, Ten
from lang.terms import Seq, H, CX

ty = Ten(Q(), Q())
bell = Seq(H(0, ty), CX(0, 1, ty))
```

### GHZ State

Surface:
```ocaml
def ghz : Q ⊗ Q ⊗ Q → Q ⊗ Q ⊗ Q =
  H[0] ; CX[0, 1] ; CX[0, 2]
```

Python:
```python
ty = Ten(Ten(Q(), Q()), Q())
ghz = Seq(H(0, ty), CX(0, 1, ty), CX(0, 2, ty))
```

### QSwitch

```python
from lang.terms import H, S, Seq, CS, X
from lang.types import Q, Ten

ty = Ten(Q(), Q())

# QSwitch(H, S): applies S;H if ctrl=0, H;S if ctrl=1
qswitch_hs = Seq(
    X(0, ty),
    CS(0, 1, ty),
    X(0, ty),
    H(1, ty),
    CS(0, 1, ty),
)
```

---

## Running Programs

### Toolchain

```
Surface Language (OCaml)
        │
        ▼ elaboration
   Core IR (Python)
        │
        ▼ compilation
  pytket Circuit
```

### Python Programs

```bash
cd quant_proto_phase01
PYTHONPATH=src python my_program.py
```

```python
from lang.types import Q, Ten
from lang.terms import Seq, H, CX
from compile.to_pytket import compile

# Build term
ty = Ten(Q(), Q())
bell = Seq(H(0, ty), CX(0, 1, ty))

# Compile to circuit
result = compile(bell)

# Inspect result
print(f"Qubits: {result.circuit.n_qubits}")
print(f"Gates: {result.circuit.n_gates}")
for cmd in result.circuit.get_commands():
    print(f"  {cmd}")
```

### OCaml Programs

```bash
cd surface
dune build
dune exec ./examples/my_program.exe
```

To compile through the Python backend:

```ocaml
open Qpl_surface

let term = Bridge.TSeq (Bridge.TH 0, Bridge.TCX (0, 1))

let () =
  Bridge.set_project_root "/path/to/quant_proto_phase01";
  match Bridge.compile term with
  | Bridge.CompileOk (perm, size) ->
    Printf.printf "Compiled: %d gates\n" size
  | Bridge.CompileError msg ->
    Printf.printf "Error: %s\n" msg
```

### Demos

See `demos/` for runnable examples:

```bash
PYTHONPATH=src python demos/qswitch_demo.py
```
