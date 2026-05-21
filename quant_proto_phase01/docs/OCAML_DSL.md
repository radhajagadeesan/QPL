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
  | TyVar of tyvar          (* Type variable: 'a *)
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

**Gate combinators:**

| Combinator | Type | Gate |
|------------|------|------|
| `gate_h` | `Q ⊸ Q` | Hadamard |
| `gate_s` | `Q ⊸ Q` | S (phase π/2) |
| `gate_t` | `Q ⊸ Q` | T (phase π/4) |
| `gate_x` | `Q ⊸ Q` | Pauli-X |
| `gate_y` | `Q ⊸ Q` | Pauli-Y |
| `gate_z` | `Q ⊸ Q` | Pauli-Z |
| `gate_rz θ` | `Q ⊸ Q` | Rz(θ) rotation |
| `gate_cx` | `Q⊗Q ⊸ Q⊗Q` | CNOT |
| `phase z ty` | `A ⊸ A` | Scalar phase e^{iθ} (requires \|z\|=1) |
| `phased_omap0 z a b f g` | `A⊕B ⊸ A⊕B` | Phase-weighted PlusMap: applies phase z to left branch |

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

### Case Sugar Combinators

Case expressions on `A⊕B` with shared context require manual dist/omap/undist plumbing.
The case sugar combinators handle this at the `prog` level (closed, unit context):

| Combinator | Type | Description |
|------------|------|-------------|
| `make_branch g a body` | `G⊗A → A⊗C` | Build branch from `body : G → C` (twist + parallel) |
| `case_hom0 a b c f g` | `A⊕B → (A⊕B)⊗C` | Homogeneous case, no context |
| `case_hom a b g c f g` | `G⊗(A⊕B) → (A⊕B)⊗C` | Homogeneous case with shared context |
| `case_het0 a b f g` | `A⊕B → (A⊗C)⊕(B⊗D)` | Heterogeneous case, no context (alias for `omap0`) |
| `case_het a b g f g` | `G⊗(A⊕B) → (A⊗C)⊕(B⊗D)` | Heterogeneous case with context |

These desugar to existing structural ops — no new GADT constructors needed.

> **Binary vs N-ary:** `omap0`, `oplusmap0`, and the case sugar accept nested Plus
> summands (e.g., `W = I ⊕ Bool` where `Bool = I⊕I`). The compiler handles nested
> sums via auto-flatten or Strategy A/B. For flat n-ary sums with 3+ summands,
> prefer `omapn`/`control` for direct compilation against the flat tag encoding.

```ocaml
(* Example: ctrl using case_hom + make_branch *)
let ctrl f =
  let left  = make_branch q one (id q) in
  let right = make_branch q one f in
  seq0 (twist_tensor (one ++ one) q)
       (case_hom one one q q left right)
```

### Oterm Case Sugar

The same case sugar pattern is available at the **oterm level** for the full source
language (lambdas, variables, function application):

| Combinator | Type | Description |
|------------|------|-------------|
| `ocase_hom0 a b c f g` | `A⊕B → (A⊕B)⊗C` | Homogeneous case, no context (oterm) |
| `ocase_hom a b g c f g` | `G⊗(A⊕B) → (A⊕B)⊗C` | Homogeneous case with context (oterm) |
| `ocase_het0 a b f g` | `A⊕B → (A⊗C)⊕(B⊗D)` | Heterogeneous case, no context (alias for `oplusmap0`) |
| `ocase_het a b g f g` | `G⊗(A⊕B) → (A⊗C)⊕(B⊗D)` | Heterogeneous case with context (oterm) |
| `omake_branch g a body` | `G⊗A → A⊗C` | Embed prog-level `make_branch` as oterm |

**Key difference:** Oterm branches are bare tensor-typed oterms (their output type
becomes the output summand), not morphisms. For prog-level `make_branch` branches,
use `oembed (case_hom ...)` instead.

### Coherent Control

The `control` combinator applies operations based on a datatype value:

```ocaml
let ctrl_gate = control bool q [| gate_h; gate_s |]
(* Type: Bool ⊗ Q ⊸ Bool ⊗ Q
   Applies H when Bool=false, S when Bool=true *)
```

On superposition inputs, both branches execute coherently (quantum control).

### Higher-Order n-ary Dispatch (`o_n_plusmap`)

For **higher-order** n-ary dispatch (branches reference outer-bound variables),
use the oterm-level `o_n_plusmap` primitive. This is the n-ary analog of binary
`oplusmap` — it produces the flat n-ary encoding directly and handles
asymmetric Z_n (n ≠ power of 2) cleanly without nested-binary tag mismatches.

```ocaml
val o_n_plusmap : 'a ty array -> 'c ty -> ('g, 'c) oterm array
              -> ('g, [`Lolli of 'sum_in * 'sum_out]) oterm
```

- `summand_types`: array of input summand types `[|a_0; ...; a_{n-1}|]`
- `output_ty`: common output type `c` for all branches
- `branches`: array of bare oterms, each producing a value of type `c`. All
  branches share the OCaml context type `'g` — use `oshift` to pad branches
  whose body references only a subset of `'g`'s variables.
- Result: a Lolli value `(⊕^n a_i) ⊸ (⊕^n c)` with existential sum types.

```ocaml
(* Example: 3-branch select dispatch (Z_3, asymmetric) *)
let pad b = oshift qq_ty (oshift qq_ty b) in
let pm = o_n_plusmap [| ia; ia; ia |] ia
  [| pad (apply_branch "f0");
     pad (apply_branch "f1");
     pad (apply_branch "f2"); |]
```

See `ocaml/demos/n_plusmap_e2e.ml` for a complete example.

### n-ary Distributivity (`n_dist`, `n_factor`)

To write the textbook curried dispatch formula explicitly:

```
select_{n,A}(f_0, …, f_{n-1})(p) = factor_n((⊕^n (id_b ⊗ f_i))(dist_n(p)))
```

use `n_dist` and `n_factor` — wire-level identity primitives that bridge the
type-level distinction between `Z_n ⊗ A` and `⊕^n (b ⊗ A)`. Both forms share
the same flat n-ary wire encoding (`log_n` tag bits + `width(A)` payload),
so these primitives emit zero gates.

```ocaml
val n_dist   : 'a ty array -> 'b ty
            -> (unit, [`Lolli of 'in_ty * 'out_ty]) prog
val n_factor : 'a ty array -> 'b ty
            -> (unit, [`Lolli of 'in_ty * 'out_ty]) prog
```

- `summand_types`: `[|s_0; …; s_{n-1}|]` for the n-ary sum's summands
- `b_ty`: the data type tensored with each summand

`n_dist` converts `(Plus s_0 (Plus s_1 …)) ⊗ b` → `Plus (s_0 ⊗ b) (Plus (s_1 ⊗ b) …)`.
`n_factor` is its inverse. Both are identity at the wire level.

See `ocaml/demos/curried_select_3_ndist_e2e.ml` for the textbook curried form.

### Curried Higher-Order Dispatch (full source language)

The full source language supports nested Apply on curried lambdas with full
β-reduction. Use this when implementing the textbook curried form:

```ocaml
(* select_3 := λf_0. λf_1. λf_2. λp. n_factor (plusmap (n_dist p)) *)
let abstract_select_3 =
  let body =
    let dist = oembed (n_dist [|one; one; one|] q) in
    let factor = oembed (n_factor [|one; one; one|] q) in
    let pipeline = oseq dist (oseq nary_plusmap factor split2) split1 in
    oapp pipeline (ovar "p" z3a_ty) apply_split
  in
  olam "f0" qq_ty cod_0
    (olam "f1" qq_ty cod_1
       (olam "f2" qq_ty cod_2
          (olam "p" z3a_ty z3a_ty body)))

(* Apply with concrete gates via Bridge.TApply (3 nested Apply) *)
let applied = TApply (TApply (TApply (emit_oterm abstract_select_3, h_value), s_value), t_value)
```

The Python compiler β-reduces nested Apply chains in one pass, so curried
instantiation produces the same compiled circuit as the meta `control z_n`.

---

## Building and Running

```bash
cd ocaml
eval $(opam env)

# Build
dune build

# Run demos (full pipeline to circuits)
dune exec demos/algorithms_e2e.exe
dune exec demos/abstract_qswitch_oterm_e2e.exe
dune exec demos/zn_controlled_phase_e2e.exe

# Run tests
dune test
```

---

## File Structure

```
ocaml/
├── lib/
│   ├── ast.ml          # Surface language AST
│   ├── bridge.ml       # Bridge to Python
│   ├── datatype.ml     # Datatype definitions (Bool, W, etc.)
│   ├── elaborate.ml    # Elaboration to Core IR
│   ├── emit.ml         # Term emission helpers
│   ├── linear.ml       # GADT-enforced Linear DSL
│   ├── linear.mli      # Linear DSL interface
│   ├── perm_gen.ml     # Permutation generation
│   ├── qpl.ml          # QPL module (surface combinators)
│   └── rep.ml          # Type representation
├── demos/              # All OCaml demos (full pipeline to circuits)
│   ├── algorithms_e2e.ml
│   ├── abstract_qswitch_oterm_e2e.ml
│   ├── ctrl_lambda_e2e.ml
│   ├── datatype_demo.ml
│   ├── exp_twist_e2e.ml
│   ├── qswitch_instantiated_e2e.ml
│   ├── short_circuit_e2e.ml
│   ├── verify_nested_ctrl_e2e.ml
│   └── zn_controlled_phase_e2e.ml
└── test/
```

---

## Further Reading

- **PROGRAMMING_GUIDE.md** — Meta-level combinators, datatype declarations
- **STAGING_SOUNDNESS.md** — Formal soundness arguments for staging
- **IR_DESIGN.md** — Wire layouts and IR architecture
- **CLAUDE.md** — Compilation pipeline and elaboration rules
