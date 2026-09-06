> **HISTORICAL RECORD — staging design study; the described staging.ml/.mli was never shipped**
> Retained verbatim for provenance (pre-release design note).  It describes the system as
> it stood at that checkpoint, not the current system.  For current
> documentation start at [`../INDEX.md`](../INDEX.md).

# OCaml Staging: Representation and Soundness

This document describes the OCaml representation used in `ocaml/lib/staging.ml` for verifying soundness of the staging approach.

---

## 1. Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                    OCaml (Meta-Level)                       │
│  - Unrestricted copying, iteration, recursion               │
│  - Combinators: iterate, fold, pow2, indexed_fold           │
│  - Generates object-language terms                          │
└─────────────────────────────────────────────────────────────┘
                              │
                              │ produces
                              ▼
┌─────────────────────────────────────────────────────────────┐
│              Object Language (Linear λ-calculus)            │
│  - Types: Q, I, ⊗, +, ⊸                                     │
│  - Terms: id, seq, gates, structural isos, exp_i            │
│  - Linearity enforced by construction                       │
└─────────────────────────────────────────────────────────────┘
                              │
                              │ compiles to
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    Python Backend                           │
│  - Type checking, compilation to pytket circuits            │
└─────────────────────────────────────────────────────────────┘
```

---

## 2. Type Representation

### 2.1 Interface (staging.mli)

```ocaml
type 'a ty                                           (* abstract *)

val q      : [`Q] ty
val unit   : [`Unit] ty
val tensor : 'a ty -> 'b ty -> [`Tensor of 'a * 'b] ty
val plus   : 'a ty -> 'b ty -> [`Plus of 'a * 'b] ty
val lolli  : 'a ty -> 'b ty -> [`Lolli of 'a * 'b] ty
```

### 2.2 Implementation (staging.ml)

```ocaml
type _ ty = Rep.t    (* phantom type parameter, actual rep is Rep.t *)

let q      = Rep.var 0
let unit   = Rep.Unit
let tensor a b = Rep.Tensor (a, b)
let plus   a b = Rep.Plus (a, b)
let lolli  a b = Rep.Tensor (a, b)   (* Int construction: A ⊸ B ≅ A ⊗ B *)
```

### 2.3 Soundness Notes

**Phantom types:** The type parameter `'a` in `'a ty` is phantom—it exists only at the OCaml type level and is erased at runtime. The actual representation is always `Rep.t`.

**Type safety:** The phantom type ensures that:
- `tensor q q` has OCaml type `` [`Tensor of [`Q] * [`Q]] ty ``
- `plus q unit` has OCaml type `` [`Plus of [`Q] * [`Unit]] ty ``

This prevents mixing incompatible types at the OCaml level, even though the runtime representation is uniform.

**Lolli representation:** Linear functions use the Int (interaction) construction where `A ⊸ B` is represented as `A ⊗ B`. This is sound because:
- In compact-closed categories, `A ⊸ B ≅ A* ⊗ B`
- For self-dual types (which we have), `A* = A`, so `A ⊸ B ≅ A ⊗ B`

---

## 3. Term Representation

### 3.1 Interface (staging.mli)

```ocaml
type 'a tm                                           (* abstract *)

val id   : 'a ty -> ('a -> 'a) tm
val seq  : ('a -> 'b) tm -> ('b -> 'c) tm -> ('a -> 'c) tm
val par  : ('a -> 'b) tm -> ('c -> 'd) tm ->
           ([`Tensor of 'a * 'c] -> [`Tensor of 'b * 'd]) tm
val h    : int -> 'a ty -> ('a -> 'a) tm
(* ... etc *)
```

### 3.2 Implementation (staging.ml)

```ocaml
type _ tm = Bridge.term   (* phantom type, actual rep is Bridge.term *)

let id ty       = Bridge.TId ty
let seq f g     = Bridge.TSeq (f, g)
let par f g     = Bridge.TTenTerm (f, g)
let h i _       = Bridge.TH i
```

### 3.3 Typing Discipline

The phantom type `'a` in `'a tm` encodes the morphism type:
- `('a -> 'b) tm` represents a term of type `A → B`
- OCaml's type system ensures composition is well-typed:

```ocaml
val seq : ('a -> 'b) tm -> ('b -> 'c) tm -> ('a -> 'c) tm
(*         ^^^^^^^^         ^^^^^^^^
           codomain of f = domain of g (both 'b)
*)
```

**Key invariant:** If OCaml accepts `seq f g`, then the underlying `Bridge.TSeq(f, g)` is composable (codomain of f matches domain of g).

---

## 4. Involution Representation

### 4.1 Interface

```ocaml
type 'a invol                                        (* abstract *)

val certify_invol    : ('a -> 'a) tm -> 'a invol
val invol_twist_ten  : 'a ty -> 'b ty -> [`Tensor of 'a * 'b] invol
val invol_twist_plus : 'a ty -> 'b ty -> [`Plus of 'a * 'b] invol
val exp_i            : float -> 'a invol -> ('a -> 'a) tm
```

### 4.2 Implementation

```ocaml
type _ invol = Bridge.term

let certify_invol term =
  match Bridge.check_involution term with
  | Bridge.InvolutionOk (true, _) -> term
  | Bridge.InvolutionOk (false, _) ->
      failwith "Term is not involutive: P² ≠ id"
  | Bridge.InvolutionError msg ->
      failwith ("Involution check failed: " ^ msg)

let invol_twist_ten a b  = Bridge.TTwistTen (a, b)
let invol_twist_plus a b = Bridge.TTwistPlus (a, b)

let exp_i theta invol = Bridge.TExpInvolution (theta, invol)
```

### 4.3 Soundness

**Certification:** `certify_invol` calls the Python backend to verify P² = id. This is a runtime check that gates `exp_i`:
- Only certified involutions can be exponentiated
- Twist operations are known involutions (no runtime check needed)

**Sealed witness:** The `'a invol` type is abstract—users cannot forge involution witnesses without going through `certify_invol` or the known-good constructors.

---

## 5. Meta-Level Combinators

### 5.1 Implementation

```ocaml
let rec iterate n ty f =
  if n <= 0 then Bridge.TId ty
  else if n = 1 then f
  else seq f (iterate (n - 1) ty f)

let fold ty fs =
  match fs with
  | [] -> Bridge.TId ty
  | [f] -> f
  | f :: rest -> List.fold_left seq f rest

let pow2 f = seq f f

let rec power_of_2 n f =
  if n <= 0 then f
  else power_of_2 (n - 1) (pow2 f)

let indexed_fold n ty gen =
  let stages = List.init n gen in
  fold ty stages
```

### 5.2 Soundness Analysis

**iterate:**
- Base case: `iterate 0 f = id` (identity term)
- Inductive: `iterate (n+1) f = f ; iterate n f`
- Type: If `f : A → A`, then `iterate n f : A → A`

**fold:**
- Base case: `fold ty [] = id ty`
- Inductive: `fold ty (f::fs) = f ; fold ty fs`
- Requires all terms to have matching types (enforced by OCaml phantom types)

**power_of_2:**
- `power_of_2 0 f = f`
- `power_of_2 (n+1) f = power_of_2 n (f ; f)`
- Produces `f^(2^n)` with O(n) term size

**indexed_fold:**
- Generator `gen : int -> ('a -> 'a) tm` is called at meta-level
- Produces `gen(0) ; gen(1) ; ... ; gen(n-1)`
- Each `gen(k)` must return same type (enforced by signature)

---

## 6. Soundness Properties

### 6.1 Type Safety

**Claim:** If `e : ('a -> 'b) tm` is well-typed in OCaml, then `to_bridge e` produces a well-typed Bridge term.

**Argument:**
1. Base terms (`id`, `h`, `twist_ten`, etc.) produce correctly-typed Bridge terms by construction
2. `seq` requires matching phantom types: `('a -> 'b) tm -> ('b -> 'c) tm -> ('a -> 'c) tm`
3. OCaml's type checker ensures the phantom types align
4. Therefore composition is well-typed

### 6.2 Linearity

**Claim:** Meta-level "copying" does not violate object-level linearity.

**Argument:**
1. `iterate n f` produces `f ; f ; ... ; f` as an AST
2. Each `f` in the sequence is a *description* of a morphism, not a runtime value
3. At runtime, the circuit applies `f` sequentially—no qubit duplication
4. The "copying" is of code, not of quantum states

### 6.3 Involution Certification

**Claim:** `exp_i theta p` is only valid when `p` is involutive.

**Argument:**
1. `exp_i` requires `'a invol` argument
2. `'a invol` can only be constructed via:
   - `certify_invol` (runtime-checked)
   - `invol_twist_ten` / `invol_twist_plus` (known involutions)
3. Therefore `exp_i` always receives a valid involution

### 6.4 Abstraction Safety

**Claim:** Users cannot forge ill-typed or invalid terms.

**Argument:**
1. `ty`, `tm`, `invol` are abstract types (hidden implementation)
2. Only the module's exported functions can construct values
3. All exported constructors produce well-formed terms
4. Therefore all user-constructed terms are valid

---

## 7. Potential Soundness Gaps

### 7.1 Type Erasure at Bridge Level

The phantom types are erased when converting to `Bridge.term`. Type checking happens again in Python. If the OCaml types don't match the Python semantics, there could be a mismatch.

**Mitigation:** The `Rep.t` representation matches Python's type representation exactly.

### 7.2 Iterate with n=0

~~`iterate 0 f` returns `Bridge.TId (Rep.var 0)`, which is identity on Q regardless of `f`'s actual type.~~

**Fixed:** `iterate` now takes an explicit type parameter:
```ocaml
val iterate : int -> 'a ty -> ('a -> 'a) tm -> ('a -> 'a) tm

let rec iterate n ty f =
  if n <= 0 then Bridge.TId ty  (* correct type *)
  else if n = 1 then f
  else seq f (iterate (n - 1) ty f)
```

This ensures `iterate 0 ty f` returns `id_ty` for any type.

### 7.3 Runtime vs Compile-Time Checking

Involution certification happens at OCaml runtime (calls Python). If the Python backend has bugs, invalid involutions could be certified.

**Mitigation:** The Python backend has extensive tests for involution checking.

---

## 8. Summary

| Property | Mechanism | Status |
|----------|-----------|--------|
| Type safety | Phantom types + sealed interface | Sound |
| Composition | OCaml type matching | Sound |
| Linearity | AST copying, not qubit copying | Sound |
| Involution | Runtime certification + known-good | Sound |
| Abstraction | Abstract types in .mli | Sound |
| iterate base | Explicit type parameter | Sound |

The staging representation is sound.
