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

# Example 2: Structural swap (no gates)
swap = TwistPlus(Q(), Q())
result = compile(swap)
print(f"Permutation: {result.perm.new_to_old}")  # Output: [1, 0]
print(f"Gates: {result.circuit.n_gates}")         # Output: 0
```

### 3.2 Your First Program (Surface Language)

Create a file `myprogram.surf`:

```ml
(* Define a boolean datatype *)
datatype Bool['a, 'b] = F of 'a | T of 'b

(* Swap function - structural, no gates *)
def swap : Bool['a, 'b] → Bool['b, 'a] =
  λx. case x of
    | F(a) => T(a)
    | T(b) => F(b)

(* Bell state preparation *)
def bellState : (Q ⊗ Q) → (Q ⊗ Q) =
  H[0] ; CX[0,1]
```

---

## 4. Surface Language Reference

### 4.1 Types

| Syntax | Meaning | Example |
|--------|---------|---------|
| `Q` | Single qubit | `Q` |
| `I` | Unit type | `I` |
| `A ⊗ B` | Tensor product | `Q ⊗ Q` |
| `A + B` | Sum type (monoidal) | `Q + Q` |
| `Name['a, 'b]` | Named type with parameters | `Bool[Q, Q]` |

### 4.2 Terms

#### Variables and Binding

| Syntax | Meaning |
|--------|---------|
| `x` | Variable reference |
| `λx:A. e` | Lambda abstraction (elaborates away) |
| `let x = e1 in e2` | Let binding (elaborates away) |
| `f e` | Application |

#### Composition

| Syntax | Meaning | Example |
|--------|---------|---------|
| `f ; g` | Sequential composition | `H[0] ; S[0]` |
| `f ⊗ g` | Parallel (tensor) composition | `H[0] ⊗ H[1]` |

#### Case Expressions

```ml
case x of
  | F(a) => T(a)
  | T(b) => F(b)
```

**Important:** `case` is a compile-time macro, NOT runtime branching.

#### Structural Primitives

| Syntax | Type | Description |
|--------|------|-------------|
| `id[A]` | `A → A` | Identity |
| `twist⊗[A, B]` | `A ⊗ B → B ⊗ A` | Tensor swap |
| `twist+[A, B]` | `A + B → B + A` | Sum swap |
| `assoc⊗L` | `(A ⊗ B) ⊗ C → A ⊗ (B ⊗ C)` | Tensor reassociation |

#### Gates (Unitary Primitives)

| Syntax | Description | Wires |
|--------|-------------|-------|
| `H[i]` | Hadamard | 1 |
| `S[i]` | S gate (π/2 phase) | 1 |
| `T[i]` | T gate (π/4 phase) | 1 |
| `X[i]` | Pauli-X | 1 |
| `Y[i]` | Pauli-Y | 1 |
| `Z[i]` | Pauli-Z | 1 |
| `CX[i,j]` | CNOT (controlled-X) | 2 |
| `CZ[i,j]` | Controlled-Z | 2 |
| `CCX[i,j,k]` | Toffoli (controlled-controlled-X) | 3 |
| `Rz[θ,i]` | Z-rotation by angle θ | 1 |

#### Exponential of Involution

```ml
exp_i(θ, J)
```

Where `J` must be a **certified involution** (structural term where `J ; J = id`).

### 4.3 Datatypes

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

Structural programs compile to **permutations only** (no gates):

```ml
(* Swap two summands *)
def swap : Bool['a, 'b] → Bool['b, 'a] =
  λx. case x of
    | F(a) => T(a)
    | T(b) => F(b)

(* This compiles to permutation [1, 0] with 0 gates *)
```

### 5.2 Unitary Programs

Unitary programs contain gates:

```ml
(* Bell state preparation *)
def bellState : (Q ⊗ Q) → (Q ⊗ Q) =
  H[0] ; CX[0,1]

(* This compiles to a 2-gate circuit *)
```

### 5.3 Using Exponentials

To use `exp_i(θ, J)`, the term `J` must be:
1. **Structural** (compiles to permutation only, no gates)
2. **Involutive** (`J ; J = id`, i.e., `p ∘ p = identity` for the permutation)

```ml
(* Valid: swap is an involution *)
def phaseSwap : Bool['a, 'b] → Bool['a, 'b] =
  exp_i(π/7, swap)

(* Invalid: rotation is NOT an involution (order 3, not 2) *)
(* This will be rejected by the compiler *)
def badExp : Triple['a, 'b, 'c] → Triple['a, 'b, 'c] =
  exp_i(π/4, rotate)  (* ERROR: rotate is not involutive *)
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
{"success": true, "perm": {"n": 2, "new_to_old": [1, 0]}, "circuit_size": 0}
```

### 6.4 Checking Involutions

```bash
echo '{"type": "check_involution", "term": {"node": "TwistPlus", "a": {"node": "Q"}, "b": {"node": "Q"}}}' | python surface/bridge.py
```

Output:
```json
{"success": true, "is_involution": true, "perm": {"n": 2, "new_to_old": [1, 0]}}
```

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
# Compiles to: perm = [1, 0], gates = 0
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

### 7.3 Algorithmic Examples

See `surface/examples/algorithmic_snippets.surf` for:
- Deutsch-Jozsa algorithm
- Hidden Subgroup Problem (standard and phase-kickback)
- Simon's algorithm

---

## 8. Error Messages and Troubleshooting

### 8.1 Common Errors

| Error | Cause | Solution |
|-------|-------|----------|
| `TypeCheckError` | Type mismatch in composition | Check that output type of f matches input type of g in `f ; g` |
| `NotImplementedError: Distributivity` | Used DistL/DistR | Distributivity is deferred; use explicit structural rewiring |
| `NotImplementedError: Feedback` | Used Feedback | Use `compile_goi()` for terms with feedback |
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

### 9.1 GOI Compilation

For terms with feedback (advanced use):

```python
from compile.to_pytket import compile_goi

result = compile_goi(term_with_feedback)
```

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

### 9.3 Invariants

The compiler maintains these invariants:

1. **Determinism**: Same input → identical output
2. **Structural → perm only**: Structural terms compile to permutations without gates
3. **No residual GOI**: Certified programs fully extract
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
│   ├── compile/        # Compilation phases
│   ├── core/           # Permutation algebra
│   ├── backends/       # Circuit backends
│   └── typing_/        # Type checking
├── surface/
│   ├── lib/            # OCaml surface language
│   ├── test/           # Surface tests
│   └── examples/       # Example programs
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
  term ::= x                     (* variable *)
         | λx:ty. term           (* abstraction *)
         | term term             (* application *)
         | let x = term in term  (* let binding *)
         | case term of branches (* case *)
         | Ctor(term)            (* constructor *)
         | term ; term           (* sequence *)
         | term ⊗ term           (* tensor *)
         | id[ty]                (* identity *)
         | twist⊗[ty, ty]        (* tensor swap *)
         | twist+[ty, ty]        (* sum swap *)
         | Gate[args]            (* gate *)
         | exp_i(θ, term)        (* exponential *)

Definitions:
  def ::= datatype Name[vars] = ctors
        | name : ty → ty = term
```

---

## Appendix B: Supported Gates

| Gate | Syntax | Matrix |
|------|--------|--------|
| Hadamard | `H[i]` | `(1/√2)[[1,1],[1,-1]]` |
| S | `S[i]` | `[[1,0],[0,i]]` |
| T | `T[i]` | `[[1,0],[0,e^{iπ/4}]]` |
| X | `X[i]` | `[[0,1],[1,0]]` |
| Y | `Y[i]` | `[[0,-i],[i,0]]` |
| Z | `Z[i]` | `[[1,0],[0,-1]]` |
| CNOT | `CX[i,j]` | Controlled-X |
| CZ | `CZ[i,j]` | Controlled-Z |
| Toffoli | `CCX[i,j,k]` | Controlled-controlled-X |
| Rz | `Rz[θ,i]` | `[[1,0],[0,e^{iθ}]]` |

---

*End of User Manual*
