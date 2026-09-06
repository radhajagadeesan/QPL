# Granthi

**Higher-Order Quantum Programming via Unitary Wiring — v1.0.0**

Granthi is a research quantum programming language and compiler.  The
public user interface is the ergonomic `let%source` Source syntax: linear
typing with located diagnostics, coherent case analysis, first-order
datatypes, and higher-order functions as physically real wire bundles,
compiled through the sealed Source calculus and the Python backend to
pytket circuits.

The [Programming Guide](docs/PROGRAMMING_GUIDE.md) is the authoritative
language document; its programs are compiled verbatim by
[`ocaml/examples/doc_examples.ml`](ocaml/examples/doc_examples.ml) in
`dune test`.

## Quick start

Prerequisites: OCaml 4.14 (opam) and Python 3.10+.  Install the Python
backend first — the OCaml suite invokes it:

```bash
pip install -r requirements.txt      # numpy, pytest, pytket
opam install dune ppxlib             # inside an OCaml 4.14 switch
cd ocaml
dune build
dune test
```

Write a program:

```ocaml
let%source quickstart (p : (q, q) tensor) =
  let (l, r) = split p in
  (h l, s r)
```

Run examples and demos:

```bash
cd ocaml
dune exec examples/doc_examples.exe
dune exec demos/source_quickstart_e2e.exe
dune exec demos/source_datatype_e2e.exe
```

## Project structure

```
ocaml/ppx/           PPX frontend (let%source, match, permutation sugar)
ocaml/lib/           sealed Source calculus + internal Raw/Linear + Bridge
ocaml/examples/      compiled documentation examples
ocaml/counterparts/  concise Source counterparts for all 34 demos + coverage.tsv
ocaml/demos/         demo executables (Source demos + retained compiler demos)
ocaml/test/          OCaml test suites and compile-reject harnesses
python/src/          Python compiler backend (internal)
python/tests/        Python regression suite
docs/                documentation (see docs/INDEX.md)
```

## Layers and their status

| Layer | Status |
|---|---|
| `let%source` Source syntax (PPX) | **Public v1.0.0 interface** |
| Sealed `Qpl_surface.Source` calculus | Public (the PPX's target; usable directly, verbose) |
| `Qpl_surface.Linear` / Raw / `Bridge` | Internal compiler-facing layers; tested, kept for regression and inspection; not a stable public API |
| Python term IR (`python/src/lang`) | Internal backend; **does not enforce linearity** — do not author terms against it |

## Documentation

- [Programming Guide](docs/PROGRAMMING_GUIDE.md) — the language, with compiled examples
- [Examples and demos](ocaml/demos/README.md) — Source counterparts and the 34 retained demos
- [Limitations](docs/LIMITATIONS.md) — sole current limitations authority
- [Verification](docs/VERIFICATION.md) — reproduction commands and expected results
- [Documentation index](docs/INDEX.md) — current vs. historical documents
- [OCaml API layers](docs/OCAML_DSL.md), [Compiler pipeline](docs/COMPILER_API_GUIDE.md),
  [Datatype elaboration](docs/DATATYPE_ELABORATION.md) — internal/advanced

## Author / Citation

Radha Jagadeesan — DePaul University — radha.jagadeesan@gmail.com

To appear at **OOPSLA 2026** (Samson Abramsky and Radha Jagadeesan,
*Granthi: Higher-Order Quantum Programming via Unitary Wiring*).  See the
[top-level README](../README.md#author--citation) for BibTeX.

## Reporting bugs

[GitHub Issues](https://github.com/radhajagadeesan/QPL/issues) — a
minimal `let%source` reproducer is ideal.

## License

[MIT](LICENSE)
