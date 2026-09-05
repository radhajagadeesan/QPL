# OCaml demos

The sealed `Source` module is the programmer-facing language:

```
OCaml Source DSL -> sealed elaboration -> Linear Raw terms -> Bridge -> compiler
```

`Source` separates first-order data witnesses (`P`) from general Source
types (`S`). Every public sum is first-order. Tensor elimination is
`let_tensor` (also `split` and `let_pair`), and the GADT context indices
enforce linear use and exact branch contexts. There is no public Raw injection,
sum constructor, `PlusMap`, or `NPlusMap`.

## Start here

These examples construct programs using only the sealed Source API:

- `source_quickstart_e2e.ml`: `lam`, `let_tensor`, certified gates, and
  linear pairing.
- `source_fixed_control_e2e.ml`: `case_bool` with exactly the same nominal
  context in both branches.
- `source_datatype_e2e.ml`: a generative three-constructor datatype with an
  exact-arity branch vector.
- `source_exp_twist_e2e.ml`: `exp_i` of the certified tensor involution.
- `test_first_order.ml`: the smallest sealed exponential example.

From `quant_proto_phase01/ocaml/`:

```sh
dune build demos/
dune exec demos/source_quickstart_e2e.exe
dune exec demos/source_fixed_control_e2e.exe
dune exec demos/source_datatype_e2e.exe
dune exec demos/source_exp_twist_e2e.exe
dune exec demos/test_first_order.exe
```

Each executable exits nonzero when compilation fails.

## Raw diagnostics and probes

`Linear` remains the Raw implementation language. Existing demos built with it
are kept for compiler regression coverage, historical witnesses, and backend
inspection. They may express terms rejected by sealed Source, so they should
not be copied as new user syntax.

The complete classification is in `manifest.tsv`:

- `Source`: constructs the program through sealed `Source`.
- `Raw-language diagnostic`: a Raw end-to-end language or semantic witness.
- `Raw/backend probe`: compiler, bridge, routing, representation, or
  serialization inspection.

Complex Raw demos were not mechanically converted in this pass. In particular,
there is deliberately no sealed-Source QSwitch-specialization demo yet: the
abstract Source term is accepted, but specializing its higher-order arguments
to H/S still reaches a recorded Raw-normalization limitation. The fixed-control
Source demo is the supported introduction to coherent case analysis.

## Golden outputs

A `golden` manifest entry has a checked-in `.output` file. An entry marked
`none` is executable but has no golden fixture. The Source demos and converted
first-order smoke test have checked-in goldens; no pre-existing `.output` file
was regenerated or altered by the Source-layer addition.
