# Granthi Programming Guide

This guide explains how to **write and run Granthi programs** using the surface language. It does not describe compiler internals, IR structure, or advanced semantics.

For compiler API details, see `COMPILER_API_GUIDE.md`.

---

## Types

### Primitive Types

| Type | Description |
|------|-------------|
| `Q` | Qubit |
| `I` | Unit (no wires) |

### Type Constructors

| Constructor | Meaning |
|-------------|---------|
| `A ⊗ B` | Tensor product (parallel wires) |
| `A + B` | Sum type (tagged union) |

### Syntax

```ocaml
Q                       (* Qubit *)
I                       (* Unit *)
A ⊗ B                   (* Tensor product *)
A + B                   (* Sum type *)
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

| Gate | Description |
|------|-------------|
| `H[i]` | Hadamard on wire i |
| `S[i]` | S gate (π/2 phase) on wire i |
| `X[i]`, `Y[i]`, `Z[i]` | Pauli gates |
| `T[i]` | T gate (π/4 phase) |
| `CX[i,j]` | CNOT (control i, target j) |
| `CS[i,j]` | Controlled-S |
| `Rz[θ,i]` | Z rotation by θ |

### Structural Primitives

| Primitive | Type |
|-----------|------|
| `id[A]` | A → A |
| `twist⊗[A,B]` | A ⊗ B → B ⊗ A |
| `twist+[A,B]` | A + B → B + A |
| `assoc⊗L[A,B,C]` | (A ⊗ B) ⊗ C → A ⊗ (B ⊗ C) |
| `assoc⊗R[A,B,C]` | A ⊗ (B ⊗ C) → (A ⊗ B) ⊗ C |

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
