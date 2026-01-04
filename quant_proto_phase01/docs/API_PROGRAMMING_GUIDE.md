# Granthi Programming Guide

Practical guide for writing and compiling quantum programs.

---

## Overview

Granthi provides two ways to write quantum programs:

| Approach | Language | Best For |
|----------|----------|----------|
| **Surface Language** | OCaml | Natural syntax, datatypes, case expressions |
| **Core API** | Python | Programmatic generation, direct AST construction |

Both compile to the same core IR and produce identical circuits.

```
Surface Language (OCaml)
        │
        ▼ elaboration
   Core IR (Python)
        │
        ▼ compilation
  pytket Circuit + WirePerm
```

---

## Part I — Surface Language (OCaml)

The surface language provides ML-style syntax that elaborates to the core IR.

### 1.1 Types

```ocaml
Q                   (* Qubit *)
A ⊗ B               (* Tensor product *)
A + B               (* Sum type (monoidal, not coproduct) *)
I                   (* Unit type *)
Bool['a, 'b]        (* Named datatype with type parameters *)
```

**Key insight:** Sum types use a **tagged layout**:
```
A + B  ≡  [tag | A_wires | B_wires]
width(A + B) = 1 + width(A) + width(B)
```

The tag is an explicit qubit encoding branch choice.

---

### 1.2 Datatypes

Define custom sum types with constructors:

```ocaml
datatype Bool['a, 'b] = F of 'a | T of 'b
```

This defines:
- Type `Bool['a, 'b]` with representation `'a + 'b`
- Constructors `F` and `T` for each branch

**Common datatypes:**
```ocaml
datatype Bit = Zero of I | One of I       (* Classical bit *)
datatype Maybe['a] = None of I | Some of 'a
```

---

### 1.3 Terms

#### Lambda Abstraction
```ocaml
λx:A. body                (* Lambda - elaborates away (macro) *)
```

Lambdas are compile-time only. They do not exist at runtime.

#### Let Binding
```ocaml
let x = e1 in e2          (* Let - elaborates via substitution *)
```

#### Case Expression
```ocaml
case e of
  | F(x) => branch1
  | T(y) => branch2
```

**Key insight:** Case is **structural rewiring**, not runtime branching. It routes data through the tagged layout.

#### Composition
```ocaml
f ; g                     (* Sequential composition *)
f ⊗ g                     (* Parallel/tensor composition *)
```

#### Structural Primitives
```ocaml
id[A]                     (* Identity: A → A *)
twist⊗[A, B]              (* Tensor twist: A ⊗ B → B ⊗ A *)
twist+[A, B]              (* Sum twist: A + B → B + A *)
assoc⊗L[A, B, C]          (* Tensor associator left *)
assoc⊗R[A, B, C]          (* Tensor associator right *)
assoc+L[A, B, C]          (* Sum associator left *)
assoc+R[A, B, C]          (* Sum associator right *)
```

#### Gates
```ocaml
H[i]                      (* Hadamard on wire i *)
S[i]                      (* S gate on wire i *)
X[i], Y[i], Z[i]          (* Pauli gates *)
T[i]                      (* T gate *)
CX[i, j]                  (* CNOT: control i, target j *)
Rz[θ, i]                  (* Rz rotation by θ *)
```

#### Exponential of Involution
```ocaml
exp_i(θ, J)               (* e^{iθJ} where J is involutive *)
```

---

### 1.4 Definitions

```ocaml
(* Type definition *)
datatype Bool['a, 'b] = F of 'a | T of 'b

(* Term definition *)
def swap : Bool['a, 'b] → Bool['b, 'a] =
  λx. case x of
    | F(a) => T(a)
    | T(b) => F(b)
```

---

### 1.5 Example: Swap via Case

```ocaml
datatype Bool['a, 'b] = F of 'a | T of 'b

def swap : Bool[Q, Q] → Bool[Q, Q] =
  λx. case x of
    | F(q) => T(q)
    | T(q) => F(q)
```

This elaborates to `TwistPlus(Q, Q)` — a structural permutation with a tag flip.

---

### 1.6 Example: Bell State

```ocaml
def bell : Q ⊗ Q → Q ⊗ Q =
  H[0] ; CX[0, 1]
```

---

### 1.7 Example: GHZ State

```ocaml
def ghz : Q ⊗ Q ⊗ Q → Q ⊗ Q ⊗ Q =
  H[0] ; CX[0, 1] ; CX[0, 2]
```

---

### 1.8 Elaboration

The elaboration phase transforms surface syntax to core IR:

| Surface | Core IR |
|---------|---------|
| `λx:A. body` | Substitution (macro expansion) |
| `let x = e1 in e2` | Substitution |
| `case e of ...` | Structural routing via tagged layout |
| `F(e)` | Injection into sum type |
| `f ; g` | `Seq(f, g)` |
| `f ⊗ g` | `TenTerm(f, g)` |

After elaboration, only these remain:
- Sequential composition (`;`)
- Tensor composition (`⊗`)
- Structural primitives (`Id`, `Twist`, `Assoc`, `Dist`)
- Gate primitives (`H`, `S`, `CX`, etc.)

---

### 1.9 Running OCaml Programs

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
    Printf.printf "Compiled: %d gates, perm = [%s]\n"
      size
      (String.concat ", " (List.map string_of_int perm.new_to_old))
  | Bridge.CompileError msg ->
    Printf.printf "Error: %s\n" msg
```

---

## Part II — Core API (Python)

For programmatic AST construction, use the Python API directly.

### 2.1 Types

```python
from lang.types import Q, Ten, Plus, width

q = Q()                      # Qubit, width 1
qq = Ten(Q(), Q())           # Q ⊗ Q, width 2
s = Plus(Q(), Q())           # Q ⊕ Q, width 3 (1 tag + 2 data)

w = width(qq)                # Returns 2
```

**Helper for Q^n:**
```python
def qpow(n: int):
    """Build Q ⊗ Q ⊗ ... ⊗ Q (n times)."""
    ty = Q()
    for _ in range(n - 1):
        ty = Ten(ty, Q())
    return ty
```

---

### 2.2 Terms

```python
from lang.terms import (
    Id, Seq, TenTerm,
    TwistTen, AssocTenL, AssocTenR,
    TwistPlus, AssocPlusL, AssocPlusR,
    DistL, DistR,
    H, S, CX,
    Feedback,
)
```

**Composition:**
```python
Id(ty)                       # Identity
Seq(f, g)                    # Sequential: f ; g
Seq(f, g, h)                 # Variadic: f ; g ; h
TenTerm(f, g)                # Parallel: f ⊗ g
```

**Structural:**
```python
TwistTen(a, b)               # Tensor twist: a ⊗ b → b ⊗ a
TwistPlus(a, b)              # Sum twist: a ⊕ b → b ⊕ a
AssocTenL(a, b, c)           # (a ⊗ b) ⊗ c → a ⊗ (b ⊗ c)
DistL(a, b, c)               # (a ⊕ b) ⊗ c → (a ⊗ c) ⊕ (b ⊗ c)
DistR(a, b, c)               # a ⊗ (b ⊕ c) → (a ⊗ b) ⊕ (a ⊗ c)
```

**Gates:**
```python
H(i, ty_total)               # Hadamard on wire i
S(i, ty_total)               # S gate on wire i
CX(i, j, ty_total)           # CNOT: control i, target j
```

**Feedback (GOI):**
```python
Feedback(k, body)            # Loop k wires back
# body : (A ⊗ X) → (B ⊗ X), width(X) = k
# result : A → B
```

**Higher-Order (GOI Apply):**
```python
FunVar(name, dom, cod)       # Function variable x : A → B
Lam(name, dom, cod, body)    # Lambda: λx:A→B. body
Apply(f, arg)                # Application: f arg (via GOI)
```

---

### 2.3 Compilation

```python
from compile.to_pytket import compile, compile_goi, compile_higher_order

# Standard compilation (Phases 0-2)
result = compile(term, materialize=False)
circ = result.circuit        # pytket Circuit
perm = result.perm           # WirePerm

# With feedback (Phase 3)
result = compile_goi(term, materialize=False)
if isinstance(result, GOIArtifact):
    print("Residual:", result.loops)
else:
    print("Extracted:", result.circuit)

# Higher-order via GOI (function composition)
result = compile_higher_order(term, explain=True)
# Produces GOI conjugation form: (f†) ⊗ f
```

**Result types:**
```python
@dataclass
class Compiled:
    circuit: pytket.Circuit
    perm: WirePerm
    log: Optional[List[str]]

@dataclass
class GOIArtifact:
    n_in: int
    n_out: int
    perm: WirePerm
    atoms: Tuple[GateAtom, ...]
    loops: Tuple[LoopSpec, ...]
```

---

### 2.4 Inspecting Results

**Circuit commands:**
```python
for cmd in result.circuit.get_commands():
    name = cmd.op.type.name          # "H", "CX", etc.
    wires = [q.index[0] for q in cmd.qubits]
    print(f"{name}({wires})")
```

**Wire permutation:**
```python
perm = result.perm
print(f"Width: {perm.n}")
print(f"Mapping: {perm.new_to_old}")
```

---

### 2.5 Example: Bell State

```python
from lang.types import Q, Ten
from lang.terms import Seq, H, CX
from compile.to_pytket import compile

ty = Ten(Q(), Q())
bell = Seq(H(0, ty), CX(0, 1, ty))

result = compile(bell, materialize=False)
# Circuit: H(0), CX(0,1)
# Perm: [0, 1] (identity)
```

---

### 2.6 Example: Feedback Extraction

```python
from lang.terms import Seq, Feedback, H, S
from compile.to_pytket import compile_goi
from compile.goi import GOIArtifact

ty = qpow(3)
body = Seq(H(0, ty), S(1, ty))  # Gates on wires 0, 1 only
term = Feedback(k=1, body=body)  # Loop wire 2

result = compile_goi(term)
# Extracts because gates don't touch loop wire
# Result: 2-wire circuit with H, S
```

---

## Part III — Compilation Pipeline

### 3.1 Pipeline Stages

```
Source (OCaml)
    │
    ▼ elaboration
Core IR (Python AST)
    │
    ▼ type checking
Typed IR
    │
    ▼ compilation (Phases 0-2)
Flat Circuit + WirePerm
    │
    ▼ [optional] GOI (Phase 3)
Extracted Circuit | Residual GOIArtifact
    │
    ▼ [optional] materialization
Circuit with SWAPs
```

### 3.2 Key Invariants

1. **Structural = metadata only** — no gates emitted
2. **No SWAPs by default** — only with `materialize=True`
3. **Deterministic** — same input → identical output
4. **Gates reindexed through WirePerm** — logical → physical mapping

### 3.3 SWAP Policy

```python
compile(term, materialize=False)    # Never has SWAPs
compile(term, materialize=True)     # May have SWAPs
compile_goi(term, materialize=False) # No SWAPs if extracted
```

---

## Part IV — Quick Reference

### Import Summary

```python
# Types
from lang.types import Q, Ten, Plus, width

# Terms
from lang.terms import (
    Id, Seq, TenTerm,
    TwistTen, AssocTenL, AssocTenR,
    TwistPlus, AssocPlusL, AssocPlusR,
    DistL, DistR,
    H, S, CX, Feedback,
)

# Compilation
from compile.to_pytket import compile, compile_goi
from compile.goi import GOIArtifact

# Permutations
from core.perm import WirePerm, identity, compose, inverse
```

### Cheat Sheet

| Task | Code |
|------|------|
| Compile term | `compile(term)` |
| Compile with feedback | `compile_goi(term)` |
| Check if residual | `isinstance(result, GOIArtifact)` |
| Get commands | `circ.get_commands()` |
| Get gate name | `cmd.op.type.name` |
| Get wire indices | `[q.index[0] for q in cmd.qubits]` |
| Get perm mapping | `perm.new_to_old` |
| Check for SWAPs | `any(c.op.type.name == "SWAP" for c in circ.get_commands())` |
| Get type width | `width(ty)` |
| Compile higher-order | `compile_higher_order(term)` |

---

## Part V — Higher-Order Compilation (GOI)

### 5.1 GOI Representation

In the Geometry of Interaction model:
- A morphism `f : A → B` is represented as `End(A* ⊗ B)`
- A unitary `U : A → A` becomes `(U† ⊗ U)` on `A* ⊗ A`

```python
from compile.goi import make_unitary_value, goi_seq, execute_trace

# Create GOI representation of H : Q → Q
h_goi = make_unitary_value('H', (0,), n_a=1, inverse_gate_name='H')
# Result: (H ⊗ H) on 2 wires (H is self-adjoint)

# Create GOI representation of S : Q → Q
s_goi = make_unitary_value('S', (0,), n_a=1, inverse_gate_name='Sdg')
# Result: (Sdg ⊗ S) on 2 wires
```

### 5.2 Composition via Feedback

```python
# Compose H ; S via GOI
composed = goi_seq(h_goi, s_goi, n_shared=1)
traced = execute_trace(composed)

# Result: 4 gates on 2 wires
# Wire 0: Sdg, H  (= (H;S)† = S†;H†)
# Wire 1: H, S    (= H;S)
```

### 5.3 QSwitch Example

```python
from lang.terms import H, S, Seq, CS, X
from lang.types import Q, Ten
from compile.to_pytket import compile

ty = Ten(Q(), Q())

# QSwitch(H, S) : QBool ⊗ Q → QBool ⊗ Q
qswitch_hs = Seq(
    X(0, ty),       # anti-control
    CS(0, 1, ty),   # S if ctrl=0
    X(0, ty),       # restore
    H(1, ty),       # H unconditional
    CS(0, 1, ty),   # S if ctrl=1
)

result = compile(qswitch_hs)
# 5 gates: X, CS, X, H, CS
# Semantics:
#   |0⟩|ψ⟩ → |0⟩(S;H)|ψ⟩
#   |1⟩|ψ⟩ → |1⟩(H;S)|ψ⟩
```

---

## Part VI — Demos

Interactive demos in `demos/`:

| File | Description |
|------|-------------|
| `qswitch_demo.py` | Runnable Python demo |
| `qswitch_demo.html` | HTML animation (browser) |
| `qswitch_demo_output.md` | Static output |

```bash
# Run demo
PYTHONPATH=src python demos/qswitch_demo.py

# View HTML animation
open demos/qswitch_demo.html
```
