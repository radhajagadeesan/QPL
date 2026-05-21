# Granthi

**Higher-Order Quantum Programming via Unitary Wiring**

Granthi is a quantum programming language compiler where programs are
written in a linear type system that enforces no-cloning and no-discarding
at compile time. The compiler translates typed terms directly to quantum
circuits — structural operations (associativity, commutativity, distributivity)
compile to zero gates, while computational content (gates, controlled
operations, case analysis) emits real quantum gates.

The project lives in [`quant_proto_phase01/`](quant_proto_phase01/). See
[`quant_proto_phase01/README.md`](quant_proto_phase01/README.md) for a full
overview, install instructions, and demos.

## Quick Start

Requirements: Python 3.10+ with pytket, OCaml 4.14 with opam.

```bash
# Python tests
cd quant_proto_phase01
PYTHONPATH=python/src pytest python/tests

# OCaml build + tests
eval $(opam env) && cd ocaml && dune build && dune test

# Demos (full pipeline to circuits)
dune exec demos/abstract_qswitch_oterm_e2e.exe
dune exec demos/n_plusmap_e2e.exe
dune exec demos/curried_select_3_ndist_e2e.exe
```

## Features

- **Linear type system** with compile-time enforcement (OCaml GADT surface language)
- **Higher-order functions** via boundary exposure/splicing (no closures, no runtime)
- **Sum types** with flat log-sized tag encoding and coherent case analysis
- **N-ary datatypes** with multi-controlled branch dispatch
- **Curried higher-order n-ary dispatch** via `o_n_plusmap`, `n_dist`, `n_factor`
- **Parameterized algorithms** via OCaml functors (Deutsch-Jozsa, HSP, Simon's)
- **Full pipeline**: OCaml surface language → Bridge → Python compiler → pytket circuits

## Author

Radha Jagadeesan — DePaul University — radha.jagadeesan@gmail.com

## License

[MIT](LICENSE)
