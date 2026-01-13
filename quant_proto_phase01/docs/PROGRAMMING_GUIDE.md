# Granthi Programming Guide

This guide explains how to **write and run Granthi programs** using the surface language. It does not describe compiler internals, IR structure, or advanced semantics.

For compiler API details, see `COMPILER_API_GUIDE.md`.

---

## Types

### Primitive Types

| Type | Description |
|------|-------------|
| `Q` | Qubit (1 wire) |
| `I` | Unit (0 wires) |

### Type Constructors

| Constructor | Meaning | Wire Width |
|-------------|---------|------------|
| `A ⊗ B` | Tensor product (parallel wires) | width(A) + width(B) |
| `A + B` | Sum type (tagged union) | 2 + width(A) + width(B) |
| `A → B` | Function type (morphism) | Compile-time only |

### Function Types

Function types `A → B` represent morphisms from A to B. They are **compile-time constructs** used for:
- Lambda abstractions: `λx:A. body` has type `A → B` if body has type B
- Higher-order functions: passing and returning morphisms
- Let bindings: `let f = ... in ...`

Function types elaborate away during compilation—they don't correspond to physical wires. The body of a function becomes a circuit fragment that gets inlined at application sites.

### Sum Type Encoding (One-Hot Leaf Tags)

Sum types use **one-hot leaf-tag encoding**. An n-ary sum `A₁ + A₂ + ... + Aₙ` has:
- **N tag wires** (one-hot: exactly one is |1⟩)
- **Payload wires** for each summand

Wire layout: `[tag₁ | tag₂ | ... | tagₙ | A₁ | A₂ | ... | Aₙ]`

Examples:
- `Q + Q` = 4 wires: `[t₁, t₂, q₁, q₂]`
- `(Q + Q) + Q` = 6 wires: `[t₁, t₂, t₃, q₁, q₂, q₃]` (nested sums flatten)

This encoding makes **all structural operations on sums compile to pure wire permutations** (no gates needed).

### Syntax

```ocaml
Q                       (* Qubit *)
I                       (* Unit *)
A ⊗ B                   (* Tensor product *)
A + B                   (* Sum type *)
A → B                   (* Function type *)
Bool['a, 'b]            (* Named datatype *)
```

### Datatypes

Define custom sum types with constructors:

```ocaml
datatype Bool['a, 'b] = F of 'a | T of 'b
datatype Bit = Zero of I | One of I
datatype Maybe['a] = None of I | Some of 'a
```

---

## Terms

### Composition

| Syntax | Meaning |
|--------|---------|
| `f ; g` | Sequential composition (f then g) |
| `f ⊗ g` | Parallel composition (f and g on separate wires) |

### Gates

#### Single-Qubit Gates

| Gate | Description |
|------|-------------|
| `H[i]` | Hadamard on wire i |
| `X[i]`, `Y[i]`, `Z[i]` | Pauli gates |
| `S[i]`, `Sdg[i]` | S gate and S-dagger (±π/2 phase) |
| `T[i]`, `Tdg[i]` | T gate and T-dagger (±π/4 phase) |

#### Parameterized Gates

| Gate | Description |
|------|-------------|
| `Rz[θ,i]` | Z rotation by θ radians |
| `Rx[θ,i]` | X rotation by θ radians |
| `Ry[θ,i]` | Y rotation by θ radians |
| `Phase[φ,i]` | Global phase e^{iφ} |

#### Two-Qubit Gates

| Gate | Description |
|------|-------------|
| `CX[i,j]` | CNOT (control i, target j) |
| `CZ[i,j]` | Controlled-Z |
| `CH[i,j]` | Controlled-Hadamard |
| `CS[i,j]`, `CSdg[i,j]` | Controlled-S and S-dagger |
| `CRz[θ,i,j]` | Controlled-Rz |

#### Three-Qubit Gates

| Gate | Description |
|------|-------------|
| `CCX[i,j,k]` | Toffoli (controls i,j, target k) |

### Structural Primitives

All structural primitives compile to **pure wire permutations** (no gates).

#### Tensor Isomorphisms

| Primitive | Type |
|-----------|------|
| `id[A]` | A → A |
| `twist⊗[A,B]` | A ⊗ B → B ⊗ A |
| `assoc⊗L[A,B,C]` | (A ⊗ B) ⊗ C → A ⊗ (B ⊗ C) |
| `assoc⊗R[A,B,C]` | A ⊗ (B ⊗ C) → (A ⊗ B) ⊗ C |

#### Sum Isomorphisms

| Primitive | Type |
|-----------|------|
| `twist+[A,B]` | A + B → B + A |
| `assoc+L[A,B,C]` | (A + B) + C → A + (B + C) |
| `assoc+R[A,B,C]` | A + (B + C) → (A + B) + C |

#### Distributivity

| Primitive | Type |
|-----------|------|
| `distL[A,B,C]` | (A + B) ⊗ C → (A ⊗ C) + (B ⊗ C) |
| `distR[A,B,C]` | A ⊗ (B + C) → (A ⊗ B) + (A ⊗ C) |

### Exponentials of Involutions

For a structural involution `P : A → A` (where P² = id), you can compute:

```
exp_i(θ, P) : A → A
```

This implements the unitary:
```
exp(iθP) = cos(θ)·id + i·sin(θ)·P
```

**Typing rule:**
```
P : A → A    P² = id
─────────────────────
exp_i(θ, P) : A → A
```

| Primitive | Type | Description |
|-----------|------|-------------|
| `exp_i(θ, P)` | A → A | Exponential of involution P : A → A |
| `ExpSwap(θ, i, j)` | Q⊗Q → Q⊗Q | Atomic exp(iθ·SWAP) on wires i,j |

The compiler:
1. Verifies P is involutive (P² = id)
2. Decomposes P into disjoint transpositions
3. Emits `ExpSwap` gates for each transposition

### Qubit Encoding Isomorphism

Convert between primitive qubit Q and encoded qubit I + I:

| Primitive | Type | Description |
|-----------|------|-------------|
| `encode` | Q → I + I | Encode primitive qubit to one-hot (allocates ancilla) |
| `decode` | I + I → Q | Decode one-hot back to primitive qubit (frees ancilla) |

**Circuit implementations:**
- `encode`: CX[0,1]; X[0]
- `decode`: X[0]; CX[0,1]

**Roundtrips are identity:**
- `encode ; decode = id` on Q
- `decode ; encode = id` on valid I + I states

This enables using structural operations (which are free on I + I) on primitive qubits.

### Binding Forms

```ocaml
λx:A. body              (* Lambda abstraction *)
let x = e1 in e2        (* Let binding *)
case e of               (* Case expression *)
  | F(x) => branch1
  | T(y) => branch2
```

Lambdas and let bindings are compile-time constructs that elaborate away via substitution.

---

## Examples

### Bell State

```ocaml
def bell : Q ⊗ Q → Q ⊗ Q =
  H[0] ; CX[0, 1]
```

### GHZ State

```ocaml
def ghz : Q ⊗ Q ⊗ Q → Q ⊗ Q ⊗ Q =
  H[0] ; CX[0, 1] ; CX[0, 2]
```

### Swap (Structural Involution)

```ocaml
(* Bool swap: F ↔ T *)
datatype Bool['a, 'b] = F of 'a | T of 'b

def swap : Bool['a,'b] → Bool['b,'a] =
  λx. case x of
    | F(a) => T(a)
    | T(b) => F(b)

(* This elaborates to twist+[A,B] - a pure permutation *)
```

### Exponential of Swap

```ocaml
(* exp(iπ/4 · swap) creates superposition of id and swap *)
def exp_swap : Bool[Q,Q] → Bool[Q,Q] =
  exp_i[π/4, swap]
```

### Conditional Composition (QSwitch)

```ocaml
(* Apply different gate orders based on control qubit *)
def QSwitch(f, g) : (I + I) ⊗ Q → (I + I) ⊗ Q =
  λx. case fst(x) of
    | Left(u)  => Left(u) ⊗ (g ; f) snd(x)   (* g then f *)
    | Right(u) => Right(u) ⊗ (f ; g) snd(x)  (* f then g *)
```

When the control is in superposition, this creates a coherent mixture of both orderings.

---

## Running Programs

### OCaml Programs

```bash
cd surface
dune build
dune exec ./examples/my_program.exe
```

### Compiling to Circuits

Programs compile through the Python backend to produce pytket circuits:

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

---

## Key Properties

### Structural Operations are Free

With one-hot leaf-tag encoding, **all structural operations compile to pure wire permutations**:
- `twist+`, `assoc+L`, `assoc+R` - no gates
- `distL`, `distR` - no gates
- `twist⊗`, `assoc⊗L`, `assoc⊗R` - no gates

This means structural rewiring has zero quantum cost.

### Involution Certification

When using `exp_i[θ,P]`, the compiler:
1. Compiles P to a wire permutation π
2. Verifies π² = identity (involutive check)
3. Decomposes π into disjoint swaps
4. Emits certified `ExpSwap` gates

If P is not involutive, compilation fails with an error.

---

## Demos and Examples

Granthi includes worked demonstrations in the `demos/` directory. These are the **best starting point** for understanding how programs behave end-to-end.

See `demos/README.md` for full details. Key demos:

| Demo | File | What it Shows |
|------|------|---------------|
| QSwitch | `qswitch_demo.py` | Higher-order quantum switch combinator |
| ExpInvolution | `exp_twist_demo.py` | Composition law: exp(θ);exp(θ) = exp(2θ) |
| Pauli Conjugation | `pauli_conjugation_demo.py` | exp(π/4,X);Z;exp(-π/4,X) = Y on qubit as I+I |

### ExpInvolution Demo

Verifies the composition law for exponentials of involutions:
```
exp_i(π/4, twist) ; exp_i(π/4, twist) = exp_i(π/2, twist) = i·SWAP
```

Extracts unitaries from compiled circuits and compares mathematically.

### Pauli Conjugation Demo

Verifies the Pauli identity using qubit as `I + I` (one-hot encoding):
```
exp_i(π/4, X) ; Z ; exp_i(-π/4, X) = Y
```

Where:
- X = `twist+[I,I]` (structural swap of tags)
- Z = Z gate on wire 1
- Y = `twist ; S[1] ; Sdg[0]`

Shows both 4×4 physical unitaries and 2×2 logical qubit submatrices.

**No knowledge of compiler internals is required to understand the demos.**

---

## OCaml Staging (Meta-Level Programming)

Granthi supports a two-level architecture where **OCaml** serves as a staging/meta-language for generating object-language programs:

### Key Insight

OCaml provides unrestricted classical computation (copying, iteration, recursion) at the **meta-level**. The generated programs live in a **linear λ-calculus** where linearity is enforced.

This means combinators like `iterate`, `fold`, and `pow2` are OCaml functions that *generate* object-language terms.

### Staging Combinators

| Combinator | Type | Description |
|------------|------|-------------|
| `iterate n ty f` | `int -> ty -> tm -> tm` | Generates f ; f ; ... ; f (n times) |
| `fold ty [f1;f2;...]` | `ty -> tm list -> tm` | Generates f1 ; f2 ; ... ; fn |
| `pow2 f` | `tm -> tm` | Generates f ; f |
| `power_of_2 n f` | `int -> tm -> tm` | Generates f^(2^n) via repeated squaring |
| `indexed_fold n ty gen` | `int -> ty -> (int -> tm) -> tm` | Generates gen(0) ; gen(1) ; ... ; gen(n-1) |

### Examples

```ocaml
open Qpl_surface.Staging

(* iterate: Apply Hadamard 3 times *)
let h3 = iterate 3 q (h 0 q)
(* Produces: H ; H ; H *)

(* fold: Compose a sequence of different gates *)
let hst = fold q [h 0 q; s 0 q; t 0 q]
(* Produces: H ; S ; T *)

(* indexed_fold: Generate stage-dependent rotations *)
let rz_sequence = indexed_fold 4 q (fun k ->
  rz (Float.pi /. Float.pow 2.0 (Float.of_int k)) 0 q
)
(* Produces: Rz[π] ; Rz[π/2] ; Rz[π/4] ; Rz[π/8] *)

(* power_of_2: Efficient repeated squaring *)
let h8 = power_of_2 3 (h 0 q)
(* Produces: H^8 = H ; H ; H ; H ; H ; H ; H ; H *)
```

### Building and Running

```bash
cd surface
eval $(opam env)
dune build examples/staging_demo.exe
./_build/default/examples/staging_demo.exe
```

See `surface/examples/staging_demo.ml` for complete examples.

---

## Further Reading

- `API_REFERENCE.md` — Complete type and term reference
- `COMPILER_API_GUIDE.md` — Python API for compiler embedding
- `CNTRLFexample.md` — Controlled operations with structural f (layout, logical H, free control)
- `demos/README.md` — Demo instructions
- `RadhaMSG/ocaml_staging_plan_optionA.md` — Design document for OCaml staging
