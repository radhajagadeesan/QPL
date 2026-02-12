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
| `A + B` | Sum type (tagged union) | ceil(log2(n)) + max(width(Aᵢ)) |
| `A ⊸ B` | Linear function type | width(A) + width(B) |

### Function Types (Linear Arrow)

Function types `A ⊸ B` represent linear morphisms as **wire bundles**:

```
width(A ⊸ B) = width(A) + width(B)
layout(A ⊸ B) = [A_wires | B_wires]
```

A function value is a circuit fragment boundary exposing its **argument slot** (A wires) and **result slot** (B wires). Examples:
- `Q ⊸ Q` has width 2 (argument wire + result wire)
- `(Q ⊗ Q) ⊸ Q` has width 3 (2 argument wires + 1 result wire)

Lambda creates function wires, application connects them via boundary splicing.

### Sum Type Encoding (Option B: Log-Tag + Shared Payload)

Sum types use a **flat log-sized tag register + shared payload**:

```
width(A₁ + ... + Aₙ) = ceil(log2(n)) + max(width(Aᵢ))
```

Wire layout: `[tag₀ | ... | tag_{k-1} | payload₀ | ... | payload_{W-1}]`

Where:
- k = ceil(log2(n)) tag qubits encoding the variant index
- W = max(width(Aᵢ)) shared payload width

Examples:
- `I + I` (Bool) = 1 wire: just the tag (payloads are width 0)
- `Q + Q` = 2 wires: 1 tag + 1 shared payload
- `(Q + Q) + Q` = 3 wires: 2 tags + 1 payload

Tensor structurals compile to pure permutations. Sum structurals emit X gates on tag bits (tracked symbolically).

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

### Phase-Weighted Bifunctors

Phase-weighted combinators apply quantum phases to specific branches of sum types,
enabling interference patterns for quantum control flow.

#### phased_omap0 (Binary Sums)

For binary sum types `A + B`, applies phase `z = e^{iθ}` to the left branch:

```ocaml
phased_omap0 : Complex.t → 'a ty → 'b ty → (A → C) → (B → D) → (A+B → C+D)
```

**Semantics:**
- Left branch (tag=0): applies `z · f` (phase z times f)
- Right branch (tag=1): applies `g` (no phase)

**Example (OCaml):**
```ocaml
open Qpl_surface.Linear

(* Apply -1 phase to left branch of Bool = I + I *)
let neg_one = Complex.neg Complex.one
let phase_w = phased_omap0 neg_one one bool_ty (id one) (id bool_ty)
(* Compiles to: X[0]; X[1]; CU1(1.0); X[1]; X[0] for 2-tag-qubit type *)
```

**Requirements:**
- Phase must have modulus 1: |z| = 1

#### phased_control (N-ary Datatypes)

Generalizes to n-ary datatypes with per-branch phases:

```ocaml
phased_control : datatype_desc → Complex.t array → 'a ty → (A → A) array → D ⊗ A → D ⊗ A
```

For a datatype `D` with k branches, applies phase `zᵢ` when control is in branch i.

**Efficient encoding:** Uses ⌈log₂(k)⌉ tag qubits instead of nested binary sums.

**Example (OCaml):**
```ocaml
(* W = I + Bool is a 3-element witness type *)
let w_datatype = datatype ~name:"W" ~arity:3
  ~labels:["sc"; "eval_false"; "eval_true"] ~ops:[]

(* Apply phases [-1, +1, +i] to branches 0, 1, 2 *)
let phases = [|
  Complex.polar 1.0 Float.pi;       (* branch 0: -1 = e^{iπ} *)
  Complex.one;                       (* branch 1: +1 = e^{0} - trivial *)
  Complex.polar 1.0 (Float.pi/.2.0) (* branch 2: +i = e^{iπ/2} *)
|]
let phase_w_nary = phased_control w_datatype phases one [| id one; id one; id one |]
(* Trivial phase (+1) on branch 1 is skipped - no gates emitted *)
```

**Compilation pattern** for applying phase `e^{iθ}` to tag value i (2 tag qubits):
1. X gates flip bits that are 0 in the binary representation of i
2. Multi-controlled U1(θ/π) gate (half-turns)
3. X gates restore original state

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
let (x, y) = e1 in e2   (* Tensor elimination (letpair) *)
case e of               (* Case expression *)
  | F(x) => branch1
  | T(y) => branch2
```

**Lambda (λ)**: Creates function wires. In the Python core, `Lam(x, A, B, body)` exposes A wires as input boundary.

**Let binding**: Substituted away during elaboration.

**Letpair**: Destructures tensor products. `let (x, y) = e1 in e2` binds `x` to the first width(A) wires and `y` to the next width(B) wires. In Python: `LetPair(x, y, A, B, pair, body)`.

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

Granthi includes worked demonstrations in two directories:
- `python-demos/` — Python API demonstrations
- `surface/ocaml-demos/` — OCaml E2E demos (full pipeline to circuits)

See `python-demos/README.md` for full details.

### Python Demos

| Demo | File | What it Shows |
|------|------|---------------|
| QSwitch (basic) | `qswitch_demo.py` | Higher-order quantum switch combinator |
| QSwitch (term) | `qswitch_term_demo.py` | QSwitch as Case term with DistR |
| QSwitch (abstract) | `qswitch_abstract_demo.py` | Abstract QSwitch type and wire layout |
| **QSwitch (abstract circuit)** | `qswitch_abstract_circuit_theory_demo.py` | THEORY: Abstract QSwitch circuit diagrams |
| **QSwitch (instantiation)** | `qswitch_instantiation_demo.py` | QSwitch[H,H] vs QSwitch[H,S], simplification analysis |
| **QSwitch (curried)** | `qswitch_curried_theory_demo.py` | THEORY: Curried λb.λf.λg.λx type derivation |
| **Zn Controlled Phase** | `zn_controlled_phase_demo.py` | Z2, Z4, Z5 controlled phase rotation via Ctrl combinator |
| ExpInvolution | `exp_twist_demo.py` | Composition law: exp(θ);exp(θ) = exp(2θ) |
| Pauli Conjugation | `pauli_conjugation_demo.py` | exp(π/4,X);Z;exp(-π/4,X) = Y on qubit as I+I |

### OCaml E2E Demos

| Demo | File | What it Shows |
|------|------|---------------|
| Abstract QSwitch | `abstract_qswitch_e2e.ml` | QSwitch pattern with anti-control compilation |
| Instantiated QSwitch | `qswitch_instantiated_e2e.ml` | Compositional use of QSwitch combinator |
| Zn Controlled Phase | `zn_controlled_phase_e2e.ml` | Z2, Z4, Z5 with binary decomposition |
| **Short-Circuit Conjunction** | `short_circuit_e2e.ml` | Witness routing, phased_omap0, phased_control |

### Running Demos

```bash
# Python demos
PYTHONPATH=src python python-demos/<demo>.py            # Run demo
PYTHONPATH=src python python-demos/<demo>.py --circuits # Show ASCII circuit diagrams

# OCaml E2E demos
cd surface && dune exec ocaml-demos/<demo>.exe
```

Most demos support the `--circuits` flag to display circuit diagrams. Demos marked "THEORY" explain types and wire layouts without compiling circuits.

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

## OCaml Linear DSL (Meta-Level Programming)

> **See also:** [OCAML_DSL.md](OCAML_DSL.md) for comprehensive documentation of the OCaml surface language, staging architecture, and elaboration.

Granthi supports a two-level architecture where **OCaml** serves as a staging/meta-language for generating object-language programs. The `Linear` module provides a **GADT-enforced** linear DSL where linearity is checked at OCaml compile time.

### Key Insight

OCaml provides unrestricted classical computation (copying, iteration, recursion) at the **meta-level**. The generated programs live in a **linear λ-calculus** where linearity is enforced by OCaml's type system via GADTs.

Programs have type `('g, 'a) prog` where:
- `'g` is the linear context (tracked at the type level)
- `'a` is the object-language type

### Meta-Level Combinators

| Combinator | Description |
|------------|-------------|
| `iterate n ty f` | Generates f ; f ; ... ; f (n times) |
| `fold ty [f1;f2;...]` | Generates f1 ; f2 ; ... ; fn |
| `pow2 n ty f` | Generates f^(2^n) via repeated squaring |
| `indexed_fold n ty gen` | Generates gen(0) ; gen(1) ; ... ; gen(n-1) |

### Examples

```ocaml
open Qpl_surface.Linear

(* iterate: Apply Hadamard 3 times *)
let h3 = iterate 3 q gate_h
(* Produces: H ; H ; H *)

(* fold: Compose a sequence of different gates *)
let hsh = fold q [gate_h; gate_s; gate_h]
(* Produces: H ; S ; H *)

(* indexed_fold: Generate stage-dependent rotations *)
let rz_sequence = indexed_fold 4 q (fun k ->
  gate_rz (Float.pi /. float_of_int (k + 1))
)
(* Produces: Rz[π] ; Rz[π/2] ; Rz[π/3] ; Rz[π/4] *)

(* pow2: Efficient repeated squaring *)
let h8 = pow2 3 q gate_h
(* Produces: H^8 *)
```

### Building and Running

```bash
cd surface
eval $(opam env)
dune build examples/linear_demo.exe
dune exec examples/linear_demo.exe
```

See `surface/examples/linear_demo.ml` for complete examples.

---

## Datatype Declarations

Granthi supports **finite linear datatypes** that elaborate to `I^{⊕k}` (k-ary monoidal sums of unit). These datatypes:

- Have a **compile-time fixed arity** k
- Provide **no constructors, case analysis, or observation**
- Declare **operations as primitive constants**
- Enable **coherent control** without observation

### Datatype Syntax

```ocaml
open Qpl_surface.Linear

let bool = datatype
  ~name:"Bool"
  ~arity:2
  ~labels:["false"; "true"]
  ~ops:[
    ("H", lolli self self);
    ("X", lolli self self);
  ]
```

This declares:
- Type `Bool` with 2 branches, elaborating to `I ⊕ I`
- Operations `H : Bool ⊸ Bool` and `X : Bool ⊸ Bool`
- No pattern matching or observation on Bool values

### Operation Type Signatures

Use `self` for self-reference, plus standard type constructors:

| Constructor | Description |
|-------------|-------------|
| `self` | The datatype being declared |
| `ty_one` | Unit type I |
| `ty_q` | Qubit type Q |
| `a **. b` | Tensor product A ⊗ B |
| `a ++. b` | Sum A ⊕ B |
| `lolli a b` | Linear arrow A ⊸ B |
| `of_ty t` | Embed existing type witness |

### Using Datatypes

```ocaml
(* Access the type representation *)
let bool_ty = rep_ty bool  (* I ⊕ I *)

(* Use operations *)
let circuit = seq0 (op bool "H") (op bool "X")

(* Coherent control combinator *)
let controlled = control bool q [| gate_h; gate_x |]
(* Type: Bool ⊗ Q ⊸ Bool ⊗ Q *)
(* Applies H when false, X when true - coherently *)
```

### Example: Cyclic Group Z_n

```ocaml
(* Create Z_n datatype *)
let z_n n =
  datatype
    ~name:(Printf.sprintf "Z%d" n)
    ~arity:n
    ~labels:(List.init n string_of_int)
    ~ops:[
      ("mul", lolli (self **. self) (self **. self));
      ("inv", lolli self self);
    ]

let z4 = z_n 4  (* Z_4 = I ⊕ I ⊕ I ⊕ I *)

(* Phase rotations P_g = Rz(2πg/n) for g ∈ Z_n *)
let phase_rotation n g =
  gate_rz (2.0 *. Float.pi *. float_of_int g /. float_of_int n)

(* Coherent selector: λg. case g of 0 => P_0 | ... | (n-1) => P_{n-1} *)
(* This is NOT observational - it's coherent selection *)
let z4_phases = Array.init 4 (phase_rotation 4)

(* Control combinator: A ⊗ Z_4 ⊸ A ⊗ Z_4 *)
let z4_controlled = control z4 q z4_phases
```

### Key Properties

1. **No observation**: Datatypes provide no way to inspect which branch a value is in
2. **Operations are primitives**: `mul`, `inv`, etc. are opaque to the surface language
3. **Coherent control**: The `control` combinator applies operations indexed by datatype value, coherently
4. **Elaborates to I^{⊕k}**: The type `Bool` becomes `I ⊕ I`, `Z_4` becomes `I ⊕ I ⊕ I ⊕ I`

See `surface/examples/datatype_demo.ml` for complete examples.

---

## Further Reading

- `OCAML_DSL.md` — OCaml surface language, staging architecture, and elaboration
- `API_REFERENCE.md` — Complete type and term reference
- `COMPILER_API_GUIDE.md` — Python API for compiler embedding
- `STAGING_SOUNDNESS.md` — Formal soundness arguments for OCaml staging
- `IR_DESIGN.md` — Wire layouts and IR architecture
- `python-demos/README.md` — Python demo instructions
- `surface/ocaml-demos/README.md` — OCaml E2E demo instructions
