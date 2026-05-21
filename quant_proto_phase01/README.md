# Granthi

**Higher-Order Quantum Programming via Unitary Wiring**

Granthi is a quantum programming language compiler where programs are
written in a linear type system that enforces no-cloning and no-discarding
at compile time. The compiler translates typed terms directly to quantum
circuits — structural operations (associativity, commutativity,
distributivity) compile to zero gates, while computational content
(gates, controlled operations, case analysis) emits real quantum gates.

## Features

- **Linear type system** with compile-time enforcement (OCaml GADT surface language)
- **Higher-order functions** via boundary exposure/splicing (no closures, no runtime)
- **Sum types** with flat log-sized tag encoding and coherent case analysis
- **N-ary datatypes** with multi-controlled branch dispatch
- **Parameterized algorithms** via OCaml functors (Deutsch-Jozsa, HSP, Simon's)
- **Full compilation pipeline**: OCaml surface language → Bridge → Python compiler → pytket circuits

## Quick Start

### Requirements

- Python 3.10+ with pytket (`pip install pytket`)
- OCaml 4.14 with opam (`opam install dune yojson`)

### Run Python tests

```bash
PYTHONPATH=python/src pytest python/tests
```

### Build and test OCaml surface language

```bash
eval $(opam env) && cd ocaml && dune build && dune test
```

### Run demos

```bash
# OCaml E2E demos (full pipeline to circuits)
eval $(opam env) && cd ocaml && dune exec demos/abstract_qswitch_oterm_e2e.exe
eval $(opam env) && cd ocaml && dune exec demos/algorithms_e2e.exe
eval $(opam env) && cd ocaml && dune exec demos/ctrl_lambda_e2e.exe
eval $(opam env) && cd ocaml && dune exec demos/short_circuit_e2e.exe
eval $(opam env) && cd ocaml && dune exec demos/zn_controlled_phase_e2e.exe

# Python demos
PYTHONPATH=python/src python python/demos/qswitch_demo.py
PYTHONPATH=python/src python python/demos/case_demo.py
PYTHONPATH=python/src python python/demos/exp_twist_demo.py
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

## Author

Radha Jagadeesan — DePaul University — radha.jagadeesan@gmail.com

## License

[MIT](LICENSE)
