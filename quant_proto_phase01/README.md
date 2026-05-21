# Granthi

**Higher-Order Quantum Programming via Unitary Wiring**

Granthi is an experimental quantum programming language/compiler for writing
linear typed programs and compiling them to quantum circuits. The OCaml surface
language enforces linear use of quantum data; the backend lowers structural
operations, case analysis, and higher-order wiring into pytket circuits.

Structural operations (associativity, commutativity, distributivity) compile
to zero gates; computational content (gates, controlled operations, case
analysis) emits real quantum gates.

## Status

Research prototype. APIs and semantics are still evolving.

## Features

- **Linear type system** with compile-time enforcement (OCaml GADT surface language)
- **Higher-order functions** via boundary exposure/splicing (no closures, no runtime)
- **Sum types** with flat log-sized tag encoding and coherent case analysis
- **N-ary datatypes** with multi-controlled branch dispatch
- **Curried higher-order n-ary dispatch** via `o_n_plusmap`, `n_dist`, `n_factor`
- **Parameterized algorithms** via OCaml functors (Deutsch-Jozsa, HSP, Simon's)
- **Full compilation pipeline**: OCaml surface language → Bridge → Python compiler → pytket circuits

## Quick Start

### Requirements

- OCaml 4.14 with opam, dune, yojson
- Python 3.10+ with numpy, pytest, pytket, pytket-pyzx

Assumes an initialized opam switch. If you don't have one, run
`opam switch create 4.14.2 && eval $(opam env)` before `opam install dune yojson`.

### Build and test the OCaml surface language

```bash
eval $(opam env) && cd ocaml && dune build && dune test
```

### Run demos

```bash
eval $(opam env) && cd ocaml
dune exec demos/algorithms_e2e.exe
dune exec demos/short_circuit_e2e.exe
dune exec demos/abstract_qswitch_oterm_e2e.exe
dune exec demos/n_plusmap_e2e.exe
dune exec demos/curried_select_3_ndist_e2e.exe
```

### Run Python backend tests

```bash
PYTHONPATH=python/src pytest python/tests
```

## Project Structure

```
python/src/       Python core (types, terms, compiler)
python/tests/     pytest test suite
python/demos/     Python demonstrations
ocaml/lib/        OCaml surface language (Linear GADT, elaborator, bridge)
ocaml/test/       OCaml tests
ocaml/demos/      OCaml E2E demos (full pipeline to circuits)
docs/             Documentation
```

## Documentation

- [Programming Guide](docs/PROGRAMMING_GUIDE.md) — language features and usage
- [Compiler API Guide](docs/COMPILER_API_GUIDE.md) — compilation pipeline
- [API Reference](docs/API_REFERENCE.md) — type and term reference
- [OCaml DSL Guide](docs/OCAML_DSL.md) — OCaml surface language
- [Limitations](docs/LIMITATIONS.md) — known limitations

## Author / Citation

Radha Jagadeesan — DePaul University — radha.jagadeesan@gmail.com

Citation information forthcoming.

## License

[MIT](LICENSE)
