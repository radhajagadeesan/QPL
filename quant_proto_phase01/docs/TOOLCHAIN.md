# Granthi Compiler Toolchain

This document describes the two-stage compilation pipeline from source language to quantum circuits.

---

## Architecture Overview

```
┌────────────────────────────────────────────────────────────────────────┐
│                        OCaml Surface Language                          │
│                        ocaml/lib/*.ml                                │
│                                                                        │
│  Source:  λx. let (c ⊗ t) = x in case c of L => S;H | R => H;S        │
└────────────────────────────────────────────────────────────────────────┘
                                    │
                    elaborate.ml    │  Parse → Type-check → Elaborate
                                    │  • β-reduce applications
                                    │  • Substitute let-bindings
                                    │  • Transform case → controlled gates
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│                          Core IR (JSON)                                │
│                                                                        │
│  {"Seq": [{"X": [0]}, {"CS": [0,1]}, {"CH": [0,1]}, ...]}             │
└────────────────────────────────────────────────────────────────────────┘
                                    │
                    bridge.py       │  JSON → Python Term AST
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│                        Python Core Compiler                            │
│                        src/compile/to_pytket.py                        │
│                                                                        │
│  Recursive descent:                                                    │
│  • Accumulate wire permutations (symbolic, no SWAPs)                   │
│  • Emit gates to pytket Circuit                                        │
│  • Track tag permutations for sum types                                │
└────────────────────────────────────────────────────────────────────────┘
                                    │
                    compile()       │
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│                        pytket Circuit + WirePerm                       │
│                                                                        │
│  Circuit: X q[0]; CS q[0],q[1]; CH q[0],q[1]; X q[0]; CH q[0],q[1];.. │
│  Perm: identity (or final wire remapping)                              │
└────────────────────────────────────────────────────────────────────────┘
```

---

## Stage 1: OCaml Elaboration

**Location:** `ocaml/`

The OCaml frontend handles parsing, type-checking, and normalization. It produces a first-order Core IR with all high-level constructs eliminated.

### Build

```bash
cd ocaml
dune build
```

### What Elaboration Does

| Input Construct | Transformation | Output |
|-----------------|----------------|--------|
| `Var x` (simple) | Resolve to `Id(ty)` | `Id` |
| `Var x` (arrow) | Resolve to `FunVar(x,a,b)` | `FunVar` |
| `Let(x, e1, e2)` | Substitute: `e2[e1/x]` | *eliminated* |
| `LetTen(x1,x2,e1,e2)` | Decompose to `Seq` + offsets | `Seq` |
| `App(Lam(x,A,e), v)` | β-reduce: `e[v/x]` | *eliminated* |
| `Case(e, L=>b1, R=>b2)` | Anti-control + control pattern | controlled gates |
| `TyArrow(A,B)` | Encode as `A ⊗ B` | `Ten(A,B)` |
| `TyNamed("Bool")` | Expand to `Plus(Unit,Unit)` | `Plus(...)` |

### Case Transformation (Anti-Control Pattern)

```
case ctrl of Left => body_L | Right => body_R

                    ↓ elaborate

X[tag]; C-body_L[tag,...]; X[tag]; C-body_R[tag,...]
─────   ─────────────────   ─────   ─────────────────
flip    anti-control Left   flip    control Right
```

The tag qubit passes through unchanged. Both branches execute coherently on superposition inputs.

### JSON Bridge

OCaml serializes the Core IR to JSON. Python's `bridge.py` deserializes it to `lang/terms.py` AST nodes.

```bash
# Run OCaml demo that outputs JSON
cd ocaml && dune exec demos/qswitch_demo.exe

# Run OCaml E2E demo (full pipeline to circuits)
cd ocaml && dune exec demos/abstract_qswitch_oterm_e2e.exe

# Python reads JSON and compiles
PYTHONPATH=python/src python -c "from bridge import load_term; ..."
```

---

## Stage 2: Python Compilation

**Location:** `python/src/`

The Python compiler performs direct recursive-descent over the Core IR, producing a pytket circuit.

### Run

```bash
cd quant_proto_phase01
PYTHONPATH=python/src python python/demos/qswitch_demo.py
PYTHONPATH=python/src pytest  # Run tests
```

### Compilation Process

1. **Traverse AST** — Walk the term tree recursively
2. **Accumulate permutations** — Structural ops (twist, assoc, dist) become `WirePerm` compositions
3. **Emit gates** — Gate terms emit to pytket, indices reindexed through current permutation
4. **Return result** — `Compiled(circuit, perm)` with final circuit and boundary permutation

### Key Compilation Rules

| Term | Compilation |
|------|-------------|
| `Id(ty)` | No gates, identity perm |
| `Seq(f, g)` | Compile f, then g; compose perms |
| `TenTerm(f, g)` | Compile f at offset 0, g at offset width(f.dom) |
| `TwistTen(A,B)` | Block-swap permutation, 0 gates |
| `TwistPlus(A,B)` | X gate on tag bit |
| `H(i, ty)` | Emit H at `perm.apply(i)` |
| `CX(c, t, ty)` | Emit CX at `perm.apply(c)`, `perm.apply(t)` |
| `Case(L,R,bl,br)` | Anti-control bl; control br (see above) |
| `ExpInvolution(θ,P)` | Decompose P into transpositions; emit `ExpSwap` for each |

### Type Width Calculation (Option B Encoding)

```python
width(Q()) = 1                           # Qubit
width(Unit()) = 0                        # Unit (no wires)
width(Ten(A, B)) = width(A) + width(B)   # Tensor
width(Plus(A, B)) = ceil(log2(n)) + max(width(Ai))  # Sum (flattened)
```

Sum types use log-sized tag register + shared payload.

---

## Directory Structure

```
quant_proto_phase01/
├── ocaml/                 # OCaml surface language
│   ├── lib/
│   │   ├── ast.ml          # Surface AST
│   │   ├── elaborate.ml    # Elaboration to Core IR
│   │   ├── core.ml         # Core IR types
│   │   └── bridge.ml       # JSON serialization
│   ├── demos/              # OCaml demos and E2E demos (full pipeline to circuits)
│   └── dune-project
│
├── src/                     # Python core compiler
│   ├── lang/
│   │   ├── types.py        # Type system (Q, Ten, Plus, ...)
│   │   └── terms.py        # Term AST (Seq, H, CX, ...)
│   ├── core/
│   │   └── perm.py         # Wire permutations
│   ├── compile/
│   │   └── to_pytket.py    # Main compiler
│   ├── typing_/
│   │   └── check.py        # Type inference
│   └── bridge.py           # JSON → Python AST
│
├── tests/                   # pytest test suite
├── python/demos/            # Python demos with outputs
└── docs/                    # Documentation
```

---

## Usage Patterns

### Pure Python (Direct API)

Build terms directly in Python, no OCaml needed:

```python
from lang.types import Q, Ten
from lang.terms import Seq, H, CX
from compile.to_pytket import compile

ty = Ten(Q(), Q())
bell = Seq(H(0, ty), CX(0, 1, ty))
result = compile(bell)

print(result.circuit.get_commands())
# [H q[0];, CX q[0], q[1];]
```

### Full Pipeline (OCaml → Python)

Write surface language in OCaml, elaborate, bridge to Python:

```ocaml
(* ocaml/demos/my_demo.ml *)
let my_term = ...
let core_ir = elaborate my_term
let json = Core.to_json core_ir
```

```python
# Python side
from bridge import load_term
from compile.to_pytket import compile

term = load_term("my_term.json")
result = compile(term)
```

### Running Demos

```bash
# Python demos
cd quant_proto_phase01
PYTHONPATH=python/src python python/demos/qswitch_demo.py
PYTHONPATH=python/src python python/demos/exp_twist_demo.py
PYTHONPATH=python/src python python/demos/pauli_conjugation_demo.py

# OCaml demos (AST → Core IR)
cd ocaml
dune exec demos/qswitch_demo.exe

# OCaml E2E demos (full pipeline to circuits)
cd ocaml
dune exec demos/abstract_qswitch_oterm_e2e.exe
dune exec demos/zn_controlled_phase_e2e.exe
```

---

## Build Commands Reference

| Task | Command |
|------|---------|
| Build OCaml | `cd ocaml && dune build` |
| Run OCaml tests | `cd ocaml && dune test` |
| Run Python tests | `cd quant_proto_phase01 && PYTHONPATH=python/src pytest` |
| Run Python demo | `PYTHONPATH=python/src python python/demos/<demo>.py` |
| Run OCaml demo | `cd ocaml && dune exec demos/<demo>.exe` |
| Type-check OCaml | `cd ocaml && dune build @check` |

---

## Invariants

1. **OCaml eliminates all bindings** — Python sees no `Var`, `Let`, `LetTen`
2. **OCaml eliminates Case** — Python sees controlled gates, not case expressions (Python `Case` is for direct API use only)
3. **Structural ops are permutations** — TwistTen, AssocTen, DistL/R emit 0 gates
4. **TwistPlus emits X** — Tag flip on log-tag encoding
5. **Compilation is deterministic** — Same AST always produces identical circuit
6. **Permutations are symbolic** — No SWAPs emitted unless `materialize=True`

---

## Further Reading

- `PROGRAMMING_GUIDE.md` — Surface language tutorial
- `COMPILER_API_GUIDE.md` — Python API reference
- `IR_DESIGN.md` — IR architecture details
- `API_REFERENCE.md` — Complete API signatures
