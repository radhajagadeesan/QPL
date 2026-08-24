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

## Using Granthi

**Granthi's user-facing front-end is the OCaml surface language.** Programs
should be written in OCaml, elaborated to the bridge IR, and passed to the
Python backend for compilation to circuits — the pipeline is
`OCaml → Bridge → Python`.

> ⚠️ **Do not author terms directly against the Python term IR.**
> The Python layer (`python/src/lang/terms.py`, `python/src/compile/`) is a
> low-level compilation backend. It checks widths and domain/codomain matching
> but **does not** enforce linearity, and it will silently accept and
> miscompile terms that violate the OCaml surface's linear type discipline.
> Authoring higher-order or coherent-case programs directly at this layer can
> produce circuits that typecheck but do not implement any well-defined
> semantics. See [`docs/LIMITATIONS.md`](quant_proto_phase01/docs/LIMITATIONS.md#4-python-linearity-checking--language-design)
> for details.

Use `quant_proto_phase01/ocaml/` as the entry point. Every user-facing demo
under `ocaml/demos/` illustrates the correct pattern.

## Repository Layout

- `quant_proto_phase01/ocaml/` — OCaml surface language, elaborator, bridge, demos, tests
- `quant_proto_phase01/python/` — Python core compiler and pytket backend
- `quant_proto_phase01/docs/` — user and developer documentation
- `quant_proto_phase01/python/tests/` — Python regression tests

The code currently lives under `quant_proto_phase01/` as a single project.

## Quick Start

### OCaml surface language (primary user-facing layer)

Assumes an initialized opam switch (OCaml 4.14 or compatible). If you don't
have one, run `opam switch create 4.14.2 && eval $(opam env)` first.

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
- Python 3.10+ — numpy, pytest, pytket, pytket-pyzx

## Documentation

Start here:

- [`quant_proto_phase01/README.md`](quant_proto_phase01/README.md)
- [`quant_proto_phase01/docs/PROGRAMMING_GUIDE.md`](quant_proto_phase01/docs/PROGRAMMING_GUIDE.md)
- [`quant_proto_phase01/docs/OCAML_DSL.md`](quant_proto_phase01/docs/OCAML_DSL.md)
- [`quant_proto_phase01/docs/COMPILER_API_GUIDE.md`](quant_proto_phase01/docs/COMPILER_API_GUIDE.md)
- [`quant_proto_phase01/docs/LIMITATIONS.md`](quant_proto_phase01/docs/LIMITATIONS.md)

## Author / Citation

Radha Jagadeesan — DePaul University — radha.jagadeesan@gmail.com

Citation information forthcoming.

## Reporting Bugs

Please report bugs, unexpected compiler behavior, or documentation issues via
[GitHub Issues](https://github.com/radhajagadeesan/QPL/issues). A minimal
reproducer (an OCaml term, a Bridge JSON dump, or a short Python test that
exhibits the problem) is very helpful.

## License

MIT. See [LICENSE](LICENSE).
