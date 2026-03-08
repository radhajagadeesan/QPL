# OCaml E2E Demos (Primary User Language)

**OCaml is the primary user language for this release.** Programs are written using the
OCaml Linear DSL (`ocaml/lib/linear.ml`), which provides GADT-enforced linearity at
compile time. The full pipeline is:

```
OCaml Linear DSL → Elaborate → Bridge (JSON) → Python compile() → pytket Circuit
```

These demos are the main showcase of the system's capabilities. For backend-level
Python demos that exercise the compiler directly, see `python/demos/`.

## Running the Demos

From the `ocaml/` directory:

```bash
# Build all demos
dune build demos/

# Run individual demos
dune exec demos/algorithms_e2e.exe
dune exec demos/qswitch_instantiated_e2e.exe
dune exec demos/abstract_qswitch_oterm_e2e.exe
dune exec demos/zn_controlled_phase_e2e.exe
dune exec demos/short_circuit_e2e.exe
dune exec demos/exp_twist_e2e.exe
dune exec demos/ctrl_lambda_e2e.exe
dune exec demos/verify_nested_ctrl_e2e.exe
dune exec demos/datatype_demo.exe
```

## Demos

### algorithms_e2e.ml

Parameterized quantum algorithms using OCaml functors:
- **Deutsch-Jozsa**: Oracle as plain function parameter
- **HSP Standard Form**: `HSP_Core` functor over abstract types G, X
- **Simon's Algorithm**: `Simon_Core` functor over abstract types Z, Y
- **Bell and GHZ states**: Structural composition patterns

Key pattern: `oracle ; (fourier_transform tensor id)`

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

### ctrl_lambda_e2e.ml

Higher-order ctrl combinator as a curried lambda term:
- `ctrl := λf. undist ∘ (id ⊕ (id_I ⊗ f)) ∘ dist`
- Abstract lambda compilation (f as wire bundle)
- Iterated: `ctrl(X)` = CX, `ctrl²(X)` = CCX, `ctrl³(X)` = CCCX, `ctrl⁴(X)` = CCCCX
- Gate counts are pytket box counts (nested QControlBox); primitive gate counts are higher
- Unitary verification via `eq_circ`

### verify_nested_ctrl_e2e.ml

Mathematical ground-truth verification for nested controls:
- Tests ctrl^k(G) for G in {H, S, Z, T} and k = 1..4 (16 tests)
- Compares compiled unitary against mathematically constructed reference
- Reference: I_{2^n} with bottom-right 2x2 block = G (independent of compiler)
- Uses `verify_ctrl_unitary` bridge command for fidelity comparison

### abstract_qswitch_oterm_e2e.ml

Abstract QSwitch as an open term (full source language):
- Builds QSwitch using `Lam`, `LetPair`, `Var`, `App`, `PlusMap`
- Follows `full_source_language_compilation_spec.md` section 5
- Instantiation with concrete gate pairs and unitary verification

### datatype_demo.ml

Datatype declaration system:
- Bool, G[8], Z_n datatypes
- Operations, control combinator, phase rotations
- E2E compilation of datatype operations
