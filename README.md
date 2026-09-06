# Granthi

**Higher-order quantum programming via unitary wiring — v1.0.0**

Granthi is a research quantum programming language and compiler.  Programs
are written in a linearly typed OCaml surface syntax, checked at compile
time, and compiled to pytket circuits.  Structural operations
(associativity, commutativity, distributivity) compile to zero gates;
computational content (gates, coherent case analysis, controlled
dispatch) emits real quantum gates.

## Status

**Version 1.0.0 — a usable research language.**  The public user
interface is the ergonomic `let%source` Source syntax described below and
in the [Programming Guide](quant_proto_phase01/docs/PROGRAMMING_GUIDE.md).
The internal Raw/Bridge OCaml APIs and the Python term IR remain
compiler-facing compatibility layers: available, tested, but not the
recommended user syntax and not covered by the public interface promise.

## Five-minute quickstart

Prerequisites: OCaml 4.14 (opam) and Python 3.10+.  Install the Python
backend first — the OCaml test suite calls into it:

```bash
cd quant_proto_phase01
pip install -r requirements.txt        # numpy, pytest, pytket

opam install dune ppxlib               # inside an OCaml 4.14 switch
cd ocaml
dune build
dune test
```

A Granthi program is ordinary OCaml under `let%source`.  The quantum
switch — coherently choosing the order of two operations — is four lines
(this exact program is compiled by
[`ocaml/examples/doc_examples.ml`](quant_proto_phase01/ocaml/examples/doc_examples.ml)
in `dune test`):

```ocaml
let%source qswitch_hs (p : (qbool, q) tensor) =
  let (b, x) = split p in
  case b
    ~zero:(h (s x))
    ~one_:(s (h x))
```

Datatypes are ordinary variants; matching is ordinary `match`:

```ocaml
type traffic = Red | Amber | Green [@@source.datatype]

let%source signal (d : Traffic.t) (y : q) =
  match d with
  | Red -> h y
  | Amber -> s y
  | Green -> t y
```

Run the compiled documentation examples and a demo:

```bash
dune exec examples/doc_examples.exe
dune exec demos/source_quickstart_e2e.exe
```

## What the language provides

- **Linear typing**: every quantum variable is consumed exactly once,
  enforced at compile time with located diagnostics.
- **Higher-order functions** as physically real wire bundles (boundary
  exposure/splicing; no closures, no runtime).
- **Coherent case** over `qbool` and general first-order sums —
  tag-preserving, with identical branch contexts.
- **First-order datatypes** (`[@@source.datatype]`, the Qudit(n)
  abstraction) with selection, exhaustive matching, and certified label
  permutations/involutions; general sums remain first-order.
- **Certified host operations** (`Op` combinators: composition, tensor,
  coherences, distributors, exponentials of involutions, phases).
- **A tested compilation pipeline**: Source → sealed calculus → Bridge →
  Python compiler → pytket circuits, with gate-free structural
  distributivity and semantic sequential-composition checking.

## Repository layout

- `quant_proto_phase01/ocaml/` — the language: PPX frontend (`ppx/`),
  sealed Source calculus (`lib/`), compiled doc examples (`examples/`),
  concise counterparts + coverage ledger (`counterparts/`), demos, tests.
- `quant_proto_phase01/python/` — the compiler backend (internal).
- `quant_proto_phase01/docs/` — documentation
  ([index](quant_proto_phase01/docs/INDEX.md)).

## Documentation

- [Programming Guide](quant_proto_phase01/docs/PROGRAMMING_GUIDE.md) —
  **start here**: the authoritative language guide, with compiled examples.
- [Examples and demos](quant_proto_phase01/ocaml/demos/README.md) —
  concise Source counterparts and the retained compiler demos.
- [Limitations](quant_proto_phase01/docs/LIMITATIONS.md) — the sole
  current limitations authority.
- [Verification](quant_proto_phase01/docs/VERIFICATION.md) — how to
  reproduce the test and demo results.
- [Documentation index](quant_proto_phase01/docs/INDEX.md) — current
  versus historical documents.
- Internal/advanced: [sealed and Raw OCaml APIs](quant_proto_phase01/docs/OCAML_DSL.md),
  [compiler pipeline](quant_proto_phase01/docs/COMPILER_API_GUIDE.md),
  [datatype elaboration](quant_proto_phase01/docs/DATATYPE_ELABORATION.md).

> ⚠️ The Python layer (`python/src/`) checks types and widths but does
> **not** enforce linearity; terms authored directly against it can
> miscompile.  It is an internal backend.  Write programs in
> `let%source`.

## Author / Citation

Radha Jagadeesan — DePaul University — radha.jagadeesan@gmail.com

To appear at **OOPSLA 2026**:

> Samson Abramsky and Radha Jagadeesan. *Granthi: Higher-Order Quantum
> Programming via Unitary Wiring.* Proceedings of the ACM on Programming
> Languages (PACMPL), OOPSLA 2026. To appear.

```bibtex
@article{AbramskyJagadeesan2026Granthi,
  author  = {Samson Abramsky and Radha Jagadeesan},
  title   = {Granthi: Higher-Order Quantum Programming via Unitary Wiring},
  journal = {Proc. ACM Program. Lang.},
  year    = {2026},
  note    = {OOPSLA 2026, to appear},
}
```

## Reporting bugs

Please report bugs, unexpected compiler behavior, or documentation issues
via [GitHub Issues](https://github.com/radhajagadeesan/QPL/issues).  A
minimal `let%source` reproducer is ideal.

## License

MIT. See [LICENSE](LICENSE).
