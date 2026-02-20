# OCaml E2E Demos

End-to-end demonstrations of the full compilation pipeline:

```
OCaml Linear DSL -> Bridge -> Python compile() -> pytket Circuit
```

## Running the Demos

From the `ocaml/` directory:

```bash
# Build all demos
dune build demos/

# Run individual demos
dune exec demos/algorithms_e2e.exe
dune exec demos/algorithmic_snippets.exe
dune exec demos/abstract_qswitch_e2e.exe
dune exec demos/qswitch_instantiated_e2e.exe
dune exec demos/zn_controlled_phase_e2e.exe
dune exec demos/short_circuit_e2e.exe
dune exec demos/exp_twist_e2e.exe
dune exec demos/ctrl_from_dist_e2e.exe
dune exec demos/linear_demo.exe
dune exec demos/datatype_demo.exe
```

## Demos

### algorithms_e2e.ml (NEW)

Parameterized quantum algorithms using OCaml functors:
- **Deutsch-Jozsa**: Oracle as plain function parameter
- **HSP Standard Form**: `HSP_Core` functor over abstract types G, X
- **Simon's Algorithm**: `Simon_Core` functor over abstract types Z, Y
- **Bell and GHZ states**: Structural composition patterns

Key pattern: `oracle ; (fourier_transform tensor id)`

### algorithmic_snippets.ml

Concise algorithmic examples in Linear GADT (replaces Ast-based version):
- Bell state, GHZ state, Deutsch-Jozsa, HSP, Simon, Bool swap
- All verified at compile time and compiled E2E

### abstract_qswitch_e2e.ml

Abstract QSwitch pattern using structural isomorphisms:
- `dist_l ; omap0 ; undist_l`
- Parameterized over gate pairs (f, g)
- Full Bridge -> Python compilation

### qswitch_instantiated_e2e.ml

Compositional use of abstract QSwitch:
- Multiple instantiations (H/S, X/Z, rotations)
- Sequential composition
- Self-inverse case (f = g)

### zn_controlled_phase_e2e.ml

Coherent control over cyclic groups:
- Z2 (Bool): CZ gate (1 gate)
- Z4: Binary decomposition with CS, CZ (2 gates)
- Z5: CRz binary decomposition (3 gates)
- Z8: NPlusMap n-ary coherent sum eliminator (8 branches, no manual decomposition)
- O(log n) gate count via binary decomposition

### short_circuit_e2e.ml

Short-circuit conjunction with witness routing and quantum phase marking:
- `toggle_W`, `ctrl_W`, `and_sc` structural operations
- `phased_omap0` for phase-weighted bifunctors
- `phased_control` for n-ary datatypes
- Creates interference between execution paths

### exp_twist_e2e.ml

Exponential of involution (`exp_i`) E2E verification:
- `TwistTen(Q,Q)` compilation sanity check
- `exp_i(pi/4, twist)` via direct unitary synthesis
- `exp_i(pi/4, twist) ; exp_i(pi/4, twist)` composition
- Composition law: `exp(pi/4);exp(pi/4) = exp(pi/2)` via `eq_circ`
- `exp_i(pi/4, twist_plus I I)` on sum types

Uses the `exp_i` Linear DSL combinator (wraps `ExpInvolution`).

### ctrl_from_dist_e2e.ml

Control from distributivity — the categorical construction:
- `ctrl(f) = undist ∘ (id ⊕ (id_I ⊗ f)) ∘ dist`
- Iterated: `ctrl(X)` = CX, `ctrl²(X)` = CCX, `ctrl³(X)` = CCCX, `ctrl⁴(X)` = CCCCX
- Each level compiles to exactly 1 gate (CnX)
- Unitary verification: `ctrl(X) = CX` via `eq_circ`

Demonstrates that coherent control emerges from structural isomorphisms alone.

### linear_demo.ml

Core Linear DSL features:
- Closed terms, context splitting, variables, lambda
- Meta-level combinators: iterate, fold, pow2, indexed_fold
- E2E compilation of all examples

### datatype_demo.ml

Datatype declaration system:
- Bool, G[8], Z_n datatypes
- Operations, control combinator, phase rotations
- E2E compilation of datatype operations
