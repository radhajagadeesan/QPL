# User-Defined Datatypes in the OCaml Surface DSL

**Audience:** compiler and frontend developers  
**Status:** design decision and recommended implementation plan

This document explains how users define *surface datatypes* in an **embedded OCaml DSL**, why this is nontrivial, and compares two viable approaches: **manual registration** and **PPX-based derivation**. It concludes with a clear recommendation and phased plan.

---

## 1. The Core Challenge

In an embedded DSL, *OCaml types are just OCaml types*.

If a user writes:

```ocaml
type ('a,'b) bool_ty = F of 'a | T of 'b
```

then:

- this is an ordinary OCaml ADT
- the DSL has **no intrinsic knowledge** that this type is meant to be a *surface datatype*
- there is no automatic way to:
  1. recognize it as a DSL datatype
  2. derive its canonical representation as a monoidal `(+)` expression
  3. generate structural combinators (`case`-as-rewiring, constructor packers)
  4. enforce finiteness and non-recursion

So *some explicit registration mechanism is required*.

---

## 2. Two Viable Approaches

### Option A: Manual Datatype Registration (Recommended First)

Users define their OCaml type normally, then explicitly register it with the DSL.

#### Example

```ocaml
type ('a,'b) bool_ty = F of 'a | T of 'b

module Bool = Qpl.Datatype.Make2(struct
  type ('a,'b) t = ('a,'b) bool_ty
  let name = "Bool"

  (* Canonical representation: A (+) B *)
  let rep = Rep.plus (Rep.var 0) (Rep.var 1)

  (* Constructor metadata *)
  let constructors = [
    ("F", Rep.var 0);
    ("T", Rep.var 1)
  ]
end)
```

The functor generates:

- a representation witness for `Bool`
- constructor *packers* (`Bool.pack_F`, `Bool.pack_T`)
- a `Bool.case` combinator implemented as **structural rewiring**

#### Properties

- No PPX machinery
- Semantics fully explicit
- Easy to test and reason about
- Slightly more boilerplate for users

This is the **best starting point** to validate the design.

---

### Option B: PPX-Based Derivation (Ergonomics Layer)

Once the manual approach is stable, introduce a PPX to eliminate boilerplate.

#### User Syntax

```ocaml
[@@deriving qpl]
type ('a,'b) bool_ty = F of 'a | T of 'b
```

#### PPX Expansion (Conceptual)

The PPX generates exactly the same code as Option A:

- the original OCaml type (unchanged)
- a `Qpl.Datatype.Make2` registration module
- constructor packers and `case` combinator

#### Compile-Time Validation

During PPX expansion, enforce:

- datatype is finite
- datatype is non-recursive
- each constructor has exactly one payload

#### Tradeoffs

- Much better user experience
- Moderate implementation effort (≈200–400 LOC)
- Requires committing to a stable surface API

---

## 3. Naming and Semantics Clarification

### Not Coproducts

Although syntax resembles ML ADTs:

- monoidal `(+)` is **not** a coproduct
- generated combinators are **not injections or eliminators**
- there is no universal property

Preferred terminology:

- `pack_C` instead of `inj_C`
- `case` documented as *view rewiring*, not branching

This avoids conceptual confusion.

---

## 4. Interaction with Certification and `exp_i`

- Datatype machinery elaborates away before Phase 4C
- Structural rewiring may be used inside `J` for `exp_i`
- Certification remains semantic:
  - compile `J` → `WirePerm`
  - check `p ∘ p = id`

Datatypes do **not** introduce new certification complexity.

---

## 5. Recommended Phased Plan

### Phase 1 (Now)

- Implement **manual datatype registration**
- Lock canonical `(+)`/`⊗` representations
- Add end-to-end tests

### Phase 2 (Later)

- Add PPX `[@@deriving qpl]`
- Generate the same registration code automatically
- Keep semantics identical

This minimizes risk and maximizes clarity.

---

## 6. Final Recommendation

> Start with **manual registration** to validate semantics and tooling.  
> Add a **PPX derivation** purely as an ergonomics layer once the core is stable.

Both approaches are compatible with:

- monoidal `(+)`
- semantic notion of structural maps
- user-defined unitaries
- automatic certification at `exp_i`
- the locked Phase 0–4C pipeline

No conceptual issues arise; this is an engineering choice only.

