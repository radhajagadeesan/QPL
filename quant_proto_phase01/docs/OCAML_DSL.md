# OCaml Surface Language

This document describes the OCaml surface language for Granthi, including the two-level staging architecture.

---

## Overview

Granthi uses a **two-level staging architecture**:

```
┌─────────────────────────────────────────────────────────────┐
│                    OCaml (Meta-Level)                       │
│  - Unrestricted: copying, iteration, recursion              │
│  - Generates object-language terms at compile time          │
│  - GADT-enforced linearity via phantom types                │
└─────────────────────────────────────────────────────────────┘
                              │
                              │ produces
                              ▼
┌─────────────────────────────────────────────────────────────┐
│              Object Language (Linear λ-calculus)            │
│  - Types: Q, I, ⊗, ⊕, ⊸                                     │
│  - Terms: id, seq, gates, structural isos                   │
│  - Linearity enforced by construction                       │
└─────────────────────────────────────────────────────────────┘
                              │
                              │ elaborates to
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    Python Core IR                           │
│  - Type checking, compilation to pytket circuits            │
└─────────────────────────────────────────────────────────────┘
```

**Key insight:** OCaml provides classical computation (loops, recursion, copying) at the *meta-level*. The generated programs live in a *linear λ-calculus* where every qubit is used exactly once.

---

## Two Interfaces

The OCaml surface language provides two interfaces:

| Interface | Module | Use Case |
|-----------|--------|----------|
| **Direct AST** | `Ast` | Full surface syntax with λ, let, case |
| **Linear DSL** | `Linear` | GADT-enforced linearity, sealed types |

### Direct AST (`Ast` module)

The `Ast` module provides ML-style syntax that elaborates to core IR:

```ocaml
open Qpl_surface.Ast

(* Types *)
type ty =
  | TyQ                     (* Qubit *)
  | TyUnit                  (* Unit type I *)
  | TyTensor of ty * ty     (* A ⊗ B *)
  | TyPlus of ty * ty       (* A ⊕ B *)
  | TyArrow of ty * ty      (* A → B (elaborates away) *)
  | TyNamed of string * ty list  (* Named types *)

(* Terms *)
type term =
  | Var of string           (* Variable reference *)
  | Lam of var * ty * term  (* λx:A. e *)
  | App of term * term      (* f e *)
  | Let of var * term * term        (* let x = e1 in e2 *)
  | LetTen of var * var * ty * ty * term * term
                            (* let (x ⊗ y) = e1 in e2 *)
  | Case of term * (pattern * term) list
                            (* case e of p1 => e1 | ... *)
  | Seq of term * term      (* f ; g *)
  | GateH of int            (* H[i] *)
  | GateS of int            (* S[i] *)
  | ...                     (* other gates *)
```

### Linear DSL (`Linear` module)

The `Linear` module provides **GADT-enforced linearity** where OCaml's type system guarantees every linear variable is used exactly once:

```ocaml
open Qpl_surface.Linear

(* Types are phantom-typed witnesses *)
type 'a ty
val q    : [`Q] ty
val one  : [`One] ty
val ( ** ) : 'a ty -> 'b ty -> [`Tensor of 'a * 'b] ty
val ( ++ ) : 'a ty -> 'b ty -> [`Plus of 'a * 'b] ty
val ( -@ ) : 'a ty -> 'b ty -> [`Lolli of 'a * 'b] ty

(* Programs track linear context at type level *)
type ('g, 'a) prog
(* 'g = linear context (type-level tuple)
   'a = object-language type *)
```

**Context tracking:** The type `('g, 'a) prog` tracks which linear variables are in scope:
- `unit` = empty context
- `'a * 'g` = context with variable of type `'a`

---

## Staging: Meta-Level vs Object-Level

### The Key Distinction

| Level | What happens | Linearity |
|-------|--------------|-----------|
| **Meta-level** (OCaml) | Loops, recursion, copying of *code* | Unrestricted |
| **Object-level** (Generated) | Quantum operations on *qubits* | Linear |

### Example: Copying Code, Not Qubits

```ocaml
(* Meta-level: iterate generates code by "copying" f *)
let h3 = iterate 3 q gate_h
(* Produces object-level term: H ; H ; H *)

(* This is NOT copying qubits! It's copying the description
   of the Hadamard gate to build a longer circuit. *)
```

At runtime, `H ; H ; H` applies Hadamard three times to the *same* qubit sequentially. No qubit duplication occurs.

### Meta-Level Combinators

The `Linear` module provides combinators that use OCaml recursion to generate object-level programs:

| Combinator | Description | Generated Code |
|------------|-------------|----------------|
| `iterate n ty f` | Repeat f n times | `f ; f ; ... ; f` |
| `fold ty [f1;f2;...]` | Sequence list | `f1 ; f2 ; ... ; fn` |
| `pow2 n ty f` | Repeated squaring | `f^(2^n)` |
| `indexed_fold n ty gen` | Parameterized sequence | `gen(0) ; gen(1) ; ...` |

```ocaml
(* Generate rotation sequence with decreasing angles *)
let rotations = indexed_fold 4 q (fun k ->
  gate_rz (Float.pi /. float_of_int (1 lsl k))
)
(* Produces: Rz[π] ; Rz[π/2] ; Rz[π/4] ; Rz[π/8] *)
```

---

## Elaboration: Surface → Core IR

The elaborator transforms surface language to first-order core IR:

```
Surface Language                    Core IR
────────────────                    ───────
λx:A. body           ──────────►    (eliminated by β-reduction)
let x = e1 in e2     ──────────►    (substituted away)
let (x⊗y) = e in b   ──────────►    Seq + wire offset tracking
case e of ...        ──────────►    Anti-control pattern (X; C-gates; X; C-gates)
App(Lam(x,e), v)     ──────────►    e[v/x] (β-reduced)
```

### What Gets Eliminated

| Surface Construct | Elaboration Result |
|-------------------|-------------------|
| `Lam`, `App` | β-reduced away (first-order) |
| `Let` | Substituted away |
| `LetTen` | `Seq` with wire offset tracking |
| `Case` | Anti-controlled gate sequences |
| `Ctor` | Transparent (becomes payload) |

### What Remains (Core IR)

After elaboration, only these constructs remain:
- `Id`, `Seq`, `TenTerm` — composition
- `TwistTen`, `AssocTenL`, etc. — structural isomorphisms
- `H`, `S`, `CX`, etc. — gates
- `ExpInvolution` — exponentials of involutions

### Anti-Control Pattern for Case

Case expressions compile to the anti-control pattern:

```
case ctrl of Left(x) => body_L | Right(y) => body_R

Compiles to:
  X[tag]           ← flip tag (0→1)
  C-body_L         ← fires when original tag was 0
  X[tag]           ← flip back
  C-body_R         ← fires when original tag was 1
```

On superposition inputs, both branches execute coherently.

---

## GADT-Enforced Linearity

The `Linear` module uses OCaml's type system to enforce linearity at compile time.

### How It Works

1. **Phantom types** track object-language types
2. **Context splitting** in type signatures enforces linear use
3. **Sealed interface** prevents forgery of invalid terms

### Example: Context Splitting

```ocaml
(* Pair requires splitting context between components *)
val pair : ('g1, 'a) prog -> ('g2, 'b) prog
        -> ('g1 * 'g2, [`Tensor of 'a * 'b]) prog

(* Application splits context between function and argument *)
val app : ('g1, [`Lolli of 'a * 'b]) prog -> ('g2, 'a) prog
       -> ('g1 * 'g2, 'b) prog
```

If you try to use a variable twice, OCaml's type checker rejects it:

```ocaml
(* This won't compile - x would be used twice *)
let bad = pair var var  (* Type error! *)

(* This works - each var consumes its context slot *)
let good = pair var (weaken var)  (* Different context positions *)
```

### Soundness Properties

| Property | Mechanism |
|----------|-----------|
| Type safety | Phantom types + sealed interface |
| Linearity | Context splitting in signatures |
| Composition | OCaml type matching ensures domain/codomain agree |
| Abstraction | Abstract types prevent forgery |

---

## Datatype Declarations

Granthi supports finite linear datatypes:

```ocaml
let bool = datatype
  ~name:"Bool"
  ~arity:2
  ~labels:["false"; "true"]
  ~ops:[
    ("H", lolli self self);
    ("X", lolli self self);
  ]
```

**Key properties:**
- Fixed arity k at compile time
- No constructors, case analysis, or observation
- Elaborates to `I^{⊕k}` (k-ary sum of unit)
- Operations are primitive constants

### Coherent Control

The `control` combinator applies operations based on a datatype value:

```ocaml
let ctrl_gate = control bool q [| gate_h; gate_s |]
(* Type: Bool ⊗ Q ⊸ Bool ⊗ Q
   Applies H when Bool=false, S when Bool=true *)
```

On superposition inputs, both branches execute coherently (quantum control).

---

## Building and Running

```bash
cd surface
eval $(opam env)

# Build
dune build

# Run demos (full pipeline to circuits)
dune exec demos/algorithms_e2e.exe
dune exec demos/abstract_qswitch_e2e.exe
dune exec demos/zn_controlled_phase_e2e.exe
dune exec demos/linear_demo.exe

# Run tests
dune test
```

---

## File Structure

```
surface/
├── lib/
│   ├── ast.ml          # Surface language AST
│   ├── elaborate.ml    # Elaboration to Core IR
│   ├── linear.ml       # GADT-enforced Linear DSL
│   ├── linear.mli      # Linear DSL interface
│   ├── bridge.ml       # Bridge to Python
│   └── rep.ml          # Type representation
├── demos/              # All OCaml demos (full pipeline to circuits)
│   ├── algorithms_e2e.ml
│   ├── abstract_qswitch_e2e.ml
│   ├── qswitch_instantiated_e2e.ml
│   ├── zn_controlled_phase_e2e.ml
│   ├── linear_demo.ml
│   └── datatype_demo.ml
└── test/
```

---

## Further Reading

- **PROGRAMMING_GUIDE.md** — Meta-level combinators, datatype declarations
- **STAGING_SOUNDNESS.md** — Formal soundness arguments for staging
- **IR_DESIGN.md** — Wire layouts and IR architecture
- **CLAUDE.md** — Compilation pipeline and elaboration rules
