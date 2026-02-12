# OCaml E2E Demos

End-to-end demonstrations of the full compilation pipeline:

```
OCaml Surface → Bridge → Python compile() → pytket Circuit
```

## Running the Demos

From the `surface/` directory:

```bash
# Build all demos
dune build ocaml-demos/

# Run individual demos
dune exec ocaml-demos/abstract_qswitch_e2e.exe
dune exec ocaml-demos/qswitch_instantiated_e2e.exe
dune exec ocaml-demos/zn_controlled_phase_e2e.exe
dune exec ocaml-demos/short_circuit_e2e.exe
```

## Demos

### abstract_qswitch_e2e.ml

Demonstrates the abstract QSwitch pattern:
- Parameterized over gate pairs (f, g)
- Compiles to anti-control pattern
- Shows full Bridge → Python compilation

QSwitch semantics:
- ctrl=0 → f(g(target))
- ctrl=1 → g(f(target))

### qswitch_instantiated_e2e.ml

Shows compositional use of abstract QSwitch:
- Multiple instantiations (H/S, X/Z, rotations)
- Sequential composition of QSwitch operations
- Parameterized sequences with rotation gates
- Self-inverse case (f = g)

### zn_controlled_phase_e2e.ml

Demonstrates coherent control over cyclic groups:
- Z2 (Bool): CZ gate (1 gate)
- Z4: Binary decomposition with CS, CZ (2 gates)
- Z5: CRz binary decomposition with 5th roots of unity (3 gates)

Key insight: Binary decomposition gives O(log n) gate count.

### short_circuit_e2e.ml

Implements short-circuit conjunction with witness routing and quantum phase marking:

**Types:**
- `Bool = I + I` (2-element type)
- `W = I + Bool` (witness: short-circuited vs evaluated path)

**Operations:**
- `toggle_W = id_I ⊕ twist_{I,I}` : W → W (1 gate)
- `ctrl_W(M_0, M_1)` : Bool ⊗ W → Bool ⊗ W (coherent control)
- `and_sc` : (Bool ⊗ Bool) ⊗ W → (Bool ⊗ Bool) ⊗ W (3 gates)

**Quantum extension:**
- `phase_W` applies -1 phase to short-circuit branch
- Creates interference between execution paths

Key insight: Classical short-circuit logic lifts to quantum coherent control
using the same structural patterns as QSwitch.

## Architecture

These demos use the `Bridge` module to:
1. Construct terms as `Bridge.term` values
2. Serialize to JSON via `Bridge.term_to_json`
3. Call Python compilation via `Bridge.compile`
4. Return gate count and wire permutation

The Linear DSL (`Linear` module) provides type-safe term construction,
but for controlled gates (CH, CS, CZ, CRz), we build `Bridge.term` directly.
