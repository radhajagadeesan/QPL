# QPL User Manual

## Certified Surface Language & Compiler Pipeline

**Version:** 1.0
**Project Status:** Programming complete, pipeline locked
**License:** MIT (open source)
**Corresponding Author:** Radha Jagadeesan (rjagadee@depaul.edu)

---

## Table of Contents

1. [Introduction](#1-introduction)
2. [Installation](#2-installation)
3. [Quick Start](#3-quick-start)
4. [Surface Language Reference](#4-surface-language-reference)
5. [Writing Programs](#5-writing-programs)
6. [Running the Compiler](#6-running-the-compiler)
7. [Examples](#7-examples)
8. [Error Messages and Troubleshooting](#8-error-messages-and-troubleshooting)
9. [Advanced Topics](#9-advanced-topics)
10. [Contributing](#10-contributing)

---

## 1. Introduction

### 1.1 What This System Does

This repository provides:

- A **surface programming language** for composing quantum and structural programs
- A **certified compilation pipeline** with locked, deterministic semantics
- Guaranteed circuit extraction for certified programs
- Reproducible compilation artifacts across runs

### 1.2 Key Properties

| Property | Description |
|----------|-------------|
| No recursion | All programs are finite and terminate |
| No runtime branching | `case` expressions elaborate at compile time |
| Higher-order elimination | All λ/let constructs elaborate away |
| Deterministic output | Same input always produces identical output |
| Certified extraction | Certified programs always extract to circuits |

### 1.3 What This System Does NOT Provide

To avoid confusion, these are **explicit non-features**:

- No dynamic control flow or measurement
- No recursion or fixpoints
- No classical branching at runtime
- No implicit copying or projection
- No user-visible optimization passes

If you need these features, this system is not the right tool.

---

## 2. Installation

### 2.1 Prerequisites

| Component | Version | Purpose |
|-----------|---------|---------|
| Python | 3.10+ | Core compiler |
| OCaml | 4.14+ | Surface language frontend (optional) |
| pip | Latest | Package management |

### 2.2 Basic Installation (Python only)

```bash
# Clone the repository
git clone https://github.com/radhajagadeesan/QPL.git
cd QPL/quant_proto_phase01

# Create virtual environment (recommended)
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -U pip
pip install pytest pytket

# Verify installation
PYTHONPATH=src pytest -q
```

### 2.3 Full Installation (with OCaml frontend)

```bash
# Install OCaml (if not present)
# On Ubuntu/Debian:
sudo apt install opam
opam init
opam install dune

# Build surface language
cd surface
dune build
dune test
```

### 2.4 Verify Installation

Run the sanity check:

```bash
PYTHONPATH=src python -c "
from lang.types import Q, Ten
from lang.terms import TwistTen
from compile.to_pytket import compile

# Compile a simple structural program
result = compile(TwistTen(Q(), Q()))
print(f'Permutation: {result.perm.new_to_old}')
print(f'Gates: {result.circuit.n_gates}')
"
```

Expected output:
```
Permutation: [1, 0]
Gates: 0
```

---

## 3. Quick Start

### 3.1 Your First Program (Python API)

```python
from lang.types import Q, Ten, Plus
from lang.terms import Id, Seq, TenTerm, TwistPlus, H, CX
from compile.to_pytket import compile

# Example 1: Bell state preparation
bell_state = Seq(H(0), CX(0, 1))
result = compile(bell_state)
print(f"Gates: {result.circuit.n_gates}")  # Output: 2

# Example 2: Structural swap (one-hot encoding)
swap = TwistPlus(Q(), Q())
result = compile(swap)
print(f"Permutation: {result.perm.new_to_old}")  # Output: [1, 0, 3, 2]
print(f"Gates: {result.circuit.n_gates}")         # Output: 0 (pure permutation)
```

### 3.2 Your First Program (Surface Language)

Create a file `myprogram.surf`:

```ml
(* Sum symmetry - swap Left and Right *)
def swap : (A + B) → (B + A) =
  λx. case x of
    | Left(a)  => Right(a)
    | Right(b) => Left(b)
(* Compiles to: X[0] (tag flip only, no computational gates) *)

(* Tensor symmetry - swap components *)
def twist : (A ⊗ B) → (B ⊗ A) =
  λe. let (x ⊗ y) : A ⊗ B = e in (y ⊗ x)
(* Compiles to: wire permutation [1, 0] *)

(* Bell state preparation *)
def bellState : (Q ⊗ Q) → (Q ⊗ Q) =
  H[0] ; CX[0,1]
(* Compiles to: 2-gate circuit *)
```

---

## 4. Surface Language Reference

The surface language is a **linear lambda calculus** with tensor products and sums.
All higher-order constructs (λ, let, case) elaborate away at compile time—the
core IR contains only sequential/parallel composition of gates and structural isomorphisms.

### 4.1 Types

| Syntax | Meaning | Example |
|--------|---------|---------|
| `Q` | Single qubit | `Q` |
| `I` | Unit type (0 wires) | `I` |
| `A ⊗ B` | Tensor product | `Q ⊗ Q` |
| `A + B` | Sum type (tagged) | `Q + Q` |
| `Name['a, 'b]` | Named type | `Bool[Q, Q]` |

**Wire layout for sums:** `A + B` uses `1 + max(width(A), width(B))` wires—one tag qubit followed by the payload.

### 4.2 Core Constructs

#### Variables and Lambda

```ml
x                     (* variable reference *)
λx:A. e               (* lambda abstraction *)
f e                   (* application *)
```

Lambdas are **macros**—they elaborate away via substitution. No closures exist at runtime.

#### Let Bindings

```ml
let x = e1 in e2      (* simple let *)
let (x ⊗ y) : A ⊗ B = e1 in e2   (* tensor destructuring *)
```

Tensor destructuring binds `x` to the first component and `y` to the second.
Both variables must be used linearly in `e2`.

#### Case Expressions

```ml
case e of
  | Left(a)  => f(a)
  | Right(b) => g(b)
```

Case is **structural routing**, not runtime branching. For quantum superpositions,
case expressions elaborate to controlled gates. For pure structural operations
(e.g., swapping constructors), they elaborate to tag flips (X gates) only.

### 4.3 Composition

| Syntax | Type | Meaning |
|--------|------|---------|
| `f ; g` | `A → C` when `f : A → B`, `g : B → C` | Sequential composition |
| `f ⊗ g` | `A ⊗ C → B ⊗ D` when `f : A → B`, `g : C → D` | Parallel composition |
| `id[A]` | `A → A` | Identity |

### 4.4 Gates

**Single-qubit gates:**

| Syntax | Description |
|--------|-------------|
| `H[i]` | Hadamard |
| `X[i]`, `Y[i]`, `Z[i]` | Pauli gates |
| `S[i]`, `Sdg[i]` | S gate and its inverse |
| `T[i]`, `Tdg[i]` | T gate and its inverse |
| `Rx[θ,i]`, `Ry[θ,i]`, `Rz[θ,i]` | Rotation gates |

**Multi-qubit gates:**

| Syntax | Description |
|--------|-------------|
| `CX[i,j]` | CNOT (controlled-X) |
| `CZ[i,j]` | Controlled-Z |
| `CCX[i,j,k]` | Toffoli |

### 4.5 Structural Isomorphisms (Derivable)

The following isomorphisms are **structural**—they compile to wire permutations
and tag flips only (no computational gates). They can be written explicitly
using case and let, or invoked as primitives.

#### Tensor Symmetry: `A ⊗ B → B ⊗ A`

```ml
(* As primitive *)
twist⊗[A, B]

(* Eta-expanded (equivalent) *)
let (x ⊗ y) : A ⊗ B = e in (y ⊗ x)
```

#### Sum Symmetry: `A + B → B + A`

```ml
(* As primitive *)
twist+[A, B]

(* Eta-expanded *)
λx. case x of
  | Left(a)  => Right(a)
  | Right(b) => Left(b)
```

This emits an X gate to flip the tag qubit.

#### Tensor Associativity: `(A ⊗ B) ⊗ C → A ⊗ (B ⊗ C)`

```ml
(* As primitive *)
assoc⊗L[A, B, C]

(* Eta-expanded *)
let (ab ⊗ c) : (A ⊗ B) ⊗ C = e in
let (a ⊗ b) : A ⊗ B = ab in
  (a ⊗ (b ⊗ c))
```

#### Sum Associativity: `(A + B) + C → A + (B + C)`

```ml
(* As primitive *)
assoc+L[A, B, C]

(* Eta-expanded *)
λx. case x of
  | Left(inner) => case inner of
      | Left(a)  => Left(a)
      | Right(b) => Right(Left(b))
  | Right(c) => Right(Right(c))
```

#### Distributivity: `A ⊗ (B + C) → (A ⊗ B) + (A ⊗ C)`

```ml
(* As primitive *)
distL[A, B, C]

(* Eta-expanded *)
let (a ⊗ bc) : A ⊗ (B + C) = e in
case bc of
  | Left(b)  => Left(a ⊗ b)
  | Right(c) => Right(a ⊗ c)
```

All these eta-expanded forms compile to the **same circuits** as their primitive
counterparts—pure structural rewiring with no computational gates.

### 4.6 Exponential of Involution

```ml
exp_i(θ, J)
```

Where `J` must be a **certified involution** (structural term where `J ; J = id`).
This implements `exp(iθJ)` as a quantum operation.

### 4.7 Datatypes

Datatypes are finite, non-recursive sum types:

```ml
(* Two-constructor datatype *)
datatype Bool['a, 'b] = F of 'a | T of 'b

(* Three-constructor datatype *)
datatype Triple['a, 'b, 'c] = A of 'a | B of 'b | C of 'c

(* Unit type *)
datatype Unit = U of I
```

**Restrictions:**
- No recursive datatypes
- Finite number of constructors
- Each constructor has exactly one payload

---

## 5. Writing Programs

### 5.1 Structural Programs

Structural programs compile to **wire permutations and tag flips only** (no computational gates).
All the monoidal isomorphisms (symmetry, associativity, distributivity) are structural:

```ml
(* Sum symmetry via case *)
def swap : (A + B) → (B + A) =
  λx. case x of
    | Left(a)  => Right(a)
    | Right(b) => Left(b)
(* Compiles to: X[0] (tag flip) *)

(* Tensor symmetry via let *)
def twist : (A ⊗ B) → (B ⊗ A) =
  λe. let (x ⊗ y) : A ⊗ B = e in (y ⊗ x)
(* Compiles to: wire permutation [1, 0] *)

(* Distributivity *)
def distL : A ⊗ (B + C) → (A ⊗ B) + (A ⊗ C) =
  λe. let (a ⊗ bc) : A ⊗ (B + C) = e in
    case bc of
      | Left(b)  => Left(a ⊗ b)
      | Right(c) => Right(a ⊗ c)
(* Compiles to: wire permutation (moves tag to front) *)
```

### 5.2 Quantum Programs

Quantum programs apply gates to wires:

```ml
(* Bell state preparation *)
def bellState : (Q ⊗ Q) → (Q ⊗ Q) =
  H[0] ; CX[0,1]
(* Compiles to: 2-gate circuit *)

(* GHZ state *)
def ghz3 : (Q ⊗ Q ⊗ Q) → (Q ⊗ Q ⊗ Q) =
  H[0] ; CX[0,1] ; CX[0,2]
```

### 5.3 Quantum Control (Case on Superpositions)

When the scrutinee of a case is in superposition, the branches elaborate to
**controlled gates**:

```ml
(* Quantum switch: apply f;g or g;f depending on control qubit *)
def qswitch : (I + I) ⊗ Q → (I + I) ⊗ Q =
  λx. let (ctrl ⊗ target) : (I + I) ⊗ Q = x in
    case ctrl of
      | Left(u)  => Left(u)  ⊗ (S[1] ; H[1])   (* control=0: S then H *)
      | Right(u) => Right(u) ⊗ (H[1] ; S[1])   (* control=1: H then S *)
(* Compiles to: controlled gates based on tag qubit *)
```

### 5.4 Using Exponentials

To use `exp_i(θ, J)`, the term `J` must be:
1. **Structural** (compiles to permutation + tag flips only)
2. **Involutive** (`J ; J = id`)

```ml
(* Valid: swap is an involution *)
def phaseSwap : (A + B) → (A + B) =
  exp_i(π/7, swap)

(* Invalid: 3-cycle rotation is NOT an involution *)
(* This will be rejected by the compiler *)
def badExp : (A + B + C) → (A + B + C) =
  exp_i(π/4, rotate)  (* ERROR: rotate has order 3, not 2 *)
```

---

## 6. Running the Compiler

### 6.1 Python API

```python
from lang.types import Q, Ten
from lang.terms import Seq, H, CX
from compile.to_pytket import compile

# Create term
term = Seq(H(0), CX(0, 1))

# Compile
result = compile(term, materialize=False)

# Access results
print(f"Circuit: {result.circuit}")
print(f"Permutation: {result.perm}")
print(f"Gate count: {result.circuit.n_gates}")
```

### 6.2 Compiler Options

| Option | Default | Description |
|--------|---------|-------------|
| `materialize` | `False` | If `True`, append SWAPs to realize final permutation |
| `explain` | `False` | If `True`, include compilation log |

```python
# With materialization (adds SWAPs to circuit)
result = compile(term, materialize=True)

# With explanation log
result = compile(term, explain=True)
print(result.log)
```

### 6.3 JSON Bridge Interface

For integration with other tools:

```bash
echo '{"type": "compile", "term": {"node": "TwistPlus", "a": {"node": "Q"}, "b": {"node": "Q"}}}' | python surface/bridge.py
```

Output:
```json
{"success": true, "perm": {"n": 3, "new_to_old": [0, 2, 1]}, "circuit_size": 1}
```

The bridge supports gates (with automatic width inference) and distributivity:

```bash
# Bell state: H[0] ; CX[0,1]
echo '{"type": "compile", "term": {"node": "Seq", "f": {"node": "H", "i": 0}, "g": {"node": "CX", "i": 0, "j": 1}}}' | python surface/bridge.py
```

Output:
```json
{"success": true, "perm": {"n": 2, "new_to_old": [0, 1]}, "circuit_size": 2}
```

### 6.4 Checking Involutions

```bash
echo '{"type": "check_involution", "term": {"node": "TwistPlus", "a": {"node": "Q"}, "b": {"node": "Q"}}}' | python surface/bridge.py
```

Output:
```json
{"success": true, "is_involution": true, "perm": {"n": 3, "new_to_old": [0, 2, 1]}}
```

### 6.5 OCaml Embedded DSL

The OCaml embedded DSL provides full access to the compiler via the bridge:

```ocaml
open Qpl_surface

(* Set project root for bridge *)
let () = Bridge.set_project_root "/path/to/quant_proto_phase01"

(* Bell state: H[0] ; CX[0,1] *)
let bell = Bridge.TSeq (Bridge.TH 0, Bridge.TCX (0, 1))

let () = match Bridge.compile bell with
  | Bridge.CompileOk (perm, size) ->
    Printf.printf "Gates: %d\n" size  (* Output: 2 *)
  | Bridge.CompileError err ->
    Printf.printf "Error: %s\n" err

(* GHZ state: H[0] ; CX[0,1] ; CX[0,2] *)
let ghz = Bridge.TSeq (
  Bridge.TH 0,
  Bridge.TSeq (Bridge.TCX (0, 1), Bridge.TCX (0, 2))
)

(* Distributivity *)
let dist = Bridge.TDistR (Rep.var 0, Rep.var 1, Rep.var 2)

(* Involution check + exp_i *)
let swap = Bridge.TTwistPlus (Rep.var 0, Rep.var 1)
let () = match Qpl.check_involution swap with
  | Qpl.Involutive perm -> print_endline "Swap is involutive"
  | Qpl.NotInvolutive _ -> print_endline "Not involutive"
  | Qpl.CheckError err -> print_endline err
```

**Supported OCaml Bridge Terms:**

| Category | Terms |
|----------|-------|
| Structural | `TId`, `TSeq`, `TTenTerm`, `TTwistTen`, `TTwistPlus`, `TAssocTenL/R`, `TAssocPlusL/R` |
| Distributivity | `TDistL`, `TDistR` |
| Single-qubit gates | `TH`, `TS`, `TSdg`, `TT`, `TTdg`, `TX`, `TY`, `TZ`, `TRx`, `TRy`, `TRz`, `TPhase` |
| Two-qubit gates | `TCX`, `TCZ`, `TCRz` |
| Three-qubit gate | `TCCX` |

---

## 7. Examples

### 7.1 Structural Examples

#### Identity
```python
from lang.terms import Id
from lang.types import Ten, Q

term = Id(Ten(Q(), Q()))
# Compiles to: perm = [0, 1], gates = 0
```

#### Swap (Tensor)
```python
from lang.terms import TwistTen

term = TwistTen(Q(), Q())
# Compiles to: perm = [1, 0], gates = 0
```

#### Swap (Sum)
```python
from lang.terms import TwistPlus

term = TwistPlus(Q(), Q())
# Compiles to: perm = [1, 0, 3, 2], gates = 0 (pure permutation)
# One-hot layout: Q + Q has width 4 (2 tags + 1 + 1)
```

### 7.2 Quantum Circuits

#### Bell State
```python
term = Seq(H(0), CX(0, 1))
# |00⟩ → (|00⟩ + |11⟩)/√2
```

#### GHZ State
```python
term = Seq(H(0), CX(0, 1), CX(0, 2))
# |000⟩ → (|000⟩ + |111⟩)/√2
```

### 7.3 QSwitch: Higher-Order Quantum Control

QSwitch is a higher-order combinator that switches composition order based on a quantum control bit:

```ml
(* Surface definition *)
QSwitch(f, g) : QBool ⊗ Q → QBool ⊗ Q =
  case ctrl of
  | Zero => (ctrl, g;f data)   -- apply g then f
  | One  => (ctrl, f;g data)   -- apply f then g
```

**QSwitch(H, S) instantiation:**
```python
from lang.terms import H, S, Seq, CS, X
from lang.types import Q, Ten
from compile.to_pytket import compile

ty = Ten(Q(), Q())

# QSwitch(H,S): anti-controlled-S ; H ; controlled-S
qswitch_hs = Seq(
    X(0, ty),       # anti-control setup
    CS(0, 1, ty),   # S if ctrl was 0
    X(0, ty),       # restore ctrl
    H(1, ty),       # H unconditional
    CS(0, 1, ty),   # S if ctrl is 1
)

result = compile(qswitch_hs)
# Circuit: 5 gates on 2 qubits
# Semantics:
#   |0⟩|ψ⟩ → |0⟩(S;H)|ψ⟩
#   |1⟩|ψ⟩ → |1⟩(H;S)|ψ⟩
```

### 7.4 Demos

Interactive demos are available in the `demos/` directory:

| File | Description |
|------|-------------|
| `qswitch_demo.py` | Quantum switch demo |
| `qswitch_demo.html` | HTML animation (open in browser) |
| `zn_controlled_phase_demo.py` | Zn controlled phase rotation (Z2, Z4, Z5) |
| `case_demo.py` | Case/pattern matching compilation |
| `exp_twist_demo.py` | Exponential of structural involutions |

**Run a demo:**
```bash
PYTHONPATH=src python demos/qswitch_demo.py
PYTHONPATH=src python demos/zn_controlled_phase_demo.py
```

**View HTML animation:**
```bash
# Open in browser
xdg-open demos/qswitch_demo.html  # Linux
open demos/qswitch_demo.html       # macOS
```

### 7.5 Algorithmic Examples

See `surface/demos/algorithmic_snippets.ml` for:
- Deutsch-Jozsa algorithm
- Hidden Subgroup Problem (standard and phase-kickback)
- Simon's algorithm

---

## 8. Error Messages and Troubleshooting

### 8.1 Common Errors

| Error | Cause | Solution |
|-------|-------|----------|
| `TypeCheckError` | Type mismatch in composition | Check that output type of f matches input type of g in `f ; g` |
| `NotImplementedError: Feedback` | Used Feedback | Feedback is reserved for future use; not currently supported |
| `Term is not structural` | Non-structural term in `exp_i` | Ensure J contains no gates |
| `not involutive` | J ∘ J ≠ id | Use a proper involution (e.g., swap, not rotation) |

### 8.2 Debugging Tips

1. **Use `explain=True`** to see compilation steps:
   ```python
   result = compile(term, explain=True)
   for line in result.log:
       print(line)
   ```

2. **Check permutation structure**:
   ```python
   perm = result.perm
   print(f"n = {perm.n}, mapping = {perm.new_to_old}")
   ```

3. **Verify involution**:
   ```python
   from core.perm import compose, identity
   p_squared = compose(perm, perm)
   is_invol = (p_squared == identity(perm.n))
   ```

---

## 9. Advanced Topics

### 9.1 Higher-Order Terms

Higher-order terms use **compact-closed structure** (cup/cap wiring):

```python
from lang.terms import FunVar, Lam, Apply

# Function variable (identity on A ⊗ B wires)
FunVar(name, dom, cod)  # x : A → B

# Lambda abstraction (boundary exposure)
Lam(name, dom, cod, body)  # λx:A→B. body

# Application (boundary splicing)
Apply(f, arg)  # f arg
```

Since all types are self-dual (`A* = A`), a function `A ⊸ B` is physically `width(A) + width(B)` wires. Lambda exposes wires; application connects them. No feedback or loops are involved.

### 9.2 Pipeline Architecture

```
Surface Program
    │
    ▼ (elaboration)
Core IR (Id, Seq, TenTerm, gates, structural isos)
    │
    ▼ (Phase 0 compilation)
(Circuit, Permutation)
    │
    ▼ (optional: materialize)
Circuit with SWAPs
```

### 9.4 Invariants

The compiler maintains these invariants:

1. **Determinism**: Same input → identical output
2. **Structural → perm only**: Structural terms compile to permutations without gates
3. **Acyclic compilation**: All terms compile to flat circuits (no loops)
4. **Involution certification**: `exp_i` rejects non-involutive inputs

---

## 10. Contributing

### 10.1 Development Setup

```bash
# Clone and install in development mode
git clone https://github.com/radhajagadeesan/QPL.git
cd QPL/quant_proto_phase01
pip install -e .
pip install pytest

# Run tests
PYTHONPATH=src pytest -v
```

### 10.2 Running Tests

```bash
# All tests
PYTHONPATH=src pytest

# Specific test file
PYTHONPATH=src pytest tests/test_integration_phases0_3.py

# Surface language tests
cd surface && dune test
```

### 10.3 Project Structure

```
quant_proto_phase01/
├── src/
│   ├── lang/           # Types and terms
│   ├── compile/        # Compilation to pytket circuits
│   ├── core/           # Permutation algebra
│   ├── backends/       # Circuit backends
│   └── typing_/        # Type checking
├── surface/
│   ├── lib/            # OCaml surface language
│   ├── test/           # Surface tests
│   └── examples/       # Example programs
├── demos/              # Interactive demos
│   ├── qswitch_demo.py           # Quantum switch demo
│   ├── zn_controlled_phase_demo.py  # Zn controlled phase (Z2, Z4, Z5)
│   ├── qswitch_demo.html         # HTML animation
│   └── README.md                 # Demo instructions
├── tests/              # Python tests
└── docs/               # Documentation
```

### 10.4 Contribution Guidelines

- All contributions must respect **locked pipeline invariants**
- Do not modify Phase 0-4C semantics
- Add tests for new features
- Maintain determinism guarantees

---

## Appendix A: Syntax Summary

```
Types:
  ty ::= Q                       (* qubit *)
       | I                       (* unit *)
       | ty ⊗ ty                 (* tensor *)
       | ty + ty                 (* sum *)
       | Name[ty, ...]           (* named type *)

Terms:
  term ::= x                              (* variable *)
         | λx:ty. term                    (* lambda abstraction *)
         | term term                      (* application *)
         | let x = term in term           (* let binding *)
         | let (x ⊗ y) : ty ⊗ ty = term in term
                                          (* tensor destructuring *)
         | case term of branches          (* case expression *)
         | Ctor(term)                     (* constructor application *)
         | term ; term                    (* sequential composition *)
         | term ⊗ term                    (* parallel composition *)
         | id[ty]                         (* identity *)
         | Gate[args]                     (* quantum gate *)
         | exp_i(θ, term)                 (* exponential of involution *)

Branches:
  branches ::= | Ctor(x) => term | ...

Definitions:
  def ::= datatype Name[vars] = ctors
        | name : ty → ty = term
```

---

## Appendix B: Supported Gates

| Gate | Syntax | Description |
|------|--------|-------------|
| Hadamard | `H[i]` | `(1/√2)[[1,1],[1,-1]]` |
| S | `S[i]` | `[[1,0],[0,i]]` (π/2 phase) |
| S† | `Sdg[i]` | `[[1,0],[0,-i]]` (inverse of S) |
| T | `T[i]` | `[[1,0],[0,e^{iπ/4}]]` (π/4 phase) |
| T† | `Tdg[i]` | `[[1,0],[0,e^{-iπ/4}]]` (inverse of T) |
| X | `X[i]` | `[[0,1],[1,0]]` (Pauli-X) |
| Y | `Y[i]` | `[[0,-i],[i,0]]` (Pauli-Y) |
| Z | `Z[i]` | `[[1,0],[0,-1]]` (Pauli-Z) |
| Rx | `Rx[θ,i]` | X-rotation by angle θ |
| Ry | `Ry[θ,i]` | Y-rotation by angle θ |
| Rz | `Rz[θ,i]` | Z-rotation by angle θ |
| Phase | `Phase[θ,i]` | Global phase gate |
| CNOT | `CX[i,j]` | Controlled-X |
| CZ | `CZ[i,j]` | Controlled-Z |
| CRz | `CRz[θ,i,j]` | Controlled Rz |
| Toffoli | `CCX[i,j,k]` | Controlled-controlled-X |

---

*End of User Manual*
