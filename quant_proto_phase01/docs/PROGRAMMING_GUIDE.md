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

See `demos/README.md` for:

| Format | File | Requirements |
|--------|------|--------------|
| Static output | `qswitch_demo_output.md` | None |
| HTML animation | `qswitch_demo.html` | Any browser |
| Python script | `qswitch_demo.py` | Python + pytket |
| Detailed walkthrough | `quantum_switch_demo.py` | Python + pytket |

The demos show:
- Higher-order programs (QSwitch)
- Conditional composition
- Full compilation pipeline

**No knowledge of compiler internals is required to understand the demos.**

---

## Further Reading

- `API_REFERENCE.md` — Complete type and term reference
- `COMPILER_API_GUIDE.md` — Python API for compiler embedding
- `demos/README.md` — Demo instructions
