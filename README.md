# Granthi

Higher-order quantum programming via unitary wiring.

Granthi is an experimental quantum programming language/compiler for writing
linear typed programs and compiling them to quantum circuits. The OCaml surface
language enforces linear use of quantum data, while the backend lowers structural
operations, case analysis, and higher-order wiring into pytket circuits.

## Status

Research prototype. APIs and semantics are still evolving.

## What It Does

- Enforces no-cloning/no-discarding through a linear type discipline
- Provides an OCaml surface language for typed quantum programs
- Compiles structural isomorphisms such as associativity, twist, and distributivity
- Supports sum types, n-ary datatypes, case analysis, and controlled operations
- Supports higher-order programs (lambdas, application) via boundary splicing
- Emits pytket circuits through a Python backend
- Includes executable demos and regression tests

## Repository Layout

- `quant_proto_phase01/ocaml/` — OCaml surface language, elaborator, bridge, demos, tests
- `quant_proto_phase01/python/` — Python core compiler and pytket backend
- `quant_proto_phase01/docs/` — user and developer documentation
- `quant_proto_phase01/python/tests/` — Python regression tests

The code currently lives under `quant_proto_phase01/` as a single project.

## Quick Start

### OCaml surface language (primary user-facing layer)

```bash
cd quant_proto_phase01/ocaml
opam install dune yojson
dune build
dune test
```

### Demos

```bash
cd quant_proto_phase01/ocaml
dune exec demos/algorithms_e2e.exe
dune exec demos/short_circuit_e2e.exe
dune exec demos/n_plusmap_e2e.exe
```

### Python backend tests

```bash
cd quant_proto_phase01
PYTHONPATH=python/src pytest python/tests
```

## Requirements

- OCaml 4.14 or compatible — opam, dune, yojson
- Python 3.10+ — numpy, pytest, pytket

## Documentation

Start here:

- [`quant_proto_phase01/README.md`](quant_proto_phase01/README.md)
- [`quant_proto_phase01/docs/PROGRAMMING_GUIDE.md`](quant_proto_phase01/docs/PROGRAMMING_GUIDE.md)
- [`quant_proto_phase01/docs/OCAML_DSL.md`](quant_proto_phase01/docs/OCAML_DSL.md)
- [`quant_proto_phase01/docs/COMPILER_API_GUIDE.md`](quant_proto_phase01/docs/COMPILER_API_GUIDE.md)
- [`quant_proto_phase01/docs/LIMITATIONS.md`](quant_proto_phase01/docs/LIMITATIONS.md)

## License

MIT. See [LICENSE](LICENSE).
