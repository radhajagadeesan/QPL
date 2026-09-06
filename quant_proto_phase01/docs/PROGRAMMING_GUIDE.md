# Granthi Programming Guide

**The authoritative guide to writing Granthi programs (v1.0.1).**

Granthi programs are written in the ergonomic `let%source` Source syntax:
ordinary OCaml syntax, checked and elaborated by a PPX rewriter into the
sealed `Qpl_surface.Source` calculus, then compiled to pytket circuits.
Every program in this guide is compiled verbatim by
[`ocaml/examples/doc_examples.ml`](../ocaml/examples/doc_examples.ml),
which `dune test` builds with the real PPX and runs through the real
backend — the snippets here cannot drift from what the compiler accepts.

Internals (the sealed calculus itself, the Raw/Linear layer, the Bridge,
the Python backend) are *not* user syntax; see
[`OCAML_DSL.md`](OCAML_DSL.md) and
[`COMPILER_API_GUIDE.md`](COMPILER_API_GUIDE.md) if you need them.
Known restrictions live in [`LIMITATIONS.md`](LIMITATIONS.md), the sole
current limitations authority.

---

## 1. Setup and a first program

Prerequisites: OCaml 4.14 with `dune` and `ppxlib` (≥ 0.37), and Python
3.10+ with `numpy`, `pytest`, and `pytket` (the backend; OCaml tests call
into it, so install Python first). From the repository:

```bash
# Python backend
cd quant_proto_phase01
pip install -r requirements.txt

# OCaml frontend
opam install dune ppxlib      # inside an OCaml 4.14 switch
cd ocaml
dune build
dune test
```

A Granthi source file needs the PPX in its `dune` stanza:

```lisp
(executable
 (name my_program)
 (preprocess (pps qpl_source_ppx))
 (libraries qpl_surface))
```

The smallest program applies a certified gate to a qubit:

```ocaml
let%source hello (x : q) = h x
```

`let%source` introduces a Source binding.  Every parameter carries a type
annotation from the Source grammar; the body is checked for linearity and
typing by the rewriter and re-checked by the sealed calculus.  The result
is an ordinary OCaml value — a closed Source term — which you can hand to
the compiler:

```ocaml
match Qpl_surface.Bridge.compile_show (Qpl_surface.Source.emit hello) with
| Bridge.CompileOk (perm, gates) -> Printf.printf "%d gates\n" gates
| Bridge.CompileError e -> prerr_endline e
```

## 2. The type grammar

Source parameter and annotation types:

| Syntax | Meaning |
|---|---|
| `q` | one qubit |
| `qbool` | the coherent boolean (a two-label sum, one wire) |
| `('a, 'b) tensor` | pair of resources |
| `('a, 'b) plus` | first-order sum (tag + payload) |
| `('a, 'b) lolli` | linear function (a wire bundle, physically real) |
| `M.t` | a declared datatype (§6) |
| `'v` | a type variable, introduced by a visible witness parameter (§8) |

**First-order restriction:** a sum's components may not contain `lolli`.
The rewriter rejects `((q, q) lolli, q) plus` at the annotation with a
located error; the sealed calculus enforces the same restriction
independently.  This is the soundness fix for the higher-order coherent
case (see `LIMITATIONS.md §4`); it is a canonical-form requirement, not a
loss of expressiveness — function values live in the λ-context, never in
a sum payload.

## 3. Linearity

Every bound variable is consumed **exactly once**.  Violations are
compile-time errors located at the offending token:

- a dropped `split` binder: *"r is bound here but never used"*;
- a variable consumed twice: *"variable x is used on both sides here"*
  (whether through a pair or through function/argument positions of an
  application);
- case/match branches that consume different variables: *"both case
  branches must consume the same nominal linear context"* — branches
  share one context and each branch must consume all of it.

## 4. Tensors, functions, application

Pairs are ordinary tuples; tensor elimination is `let (a, b) = split …`:

```ocaml
let%source quickstart (p : (q, q) tensor) =
  let (l, r) = split p in
  (h l, s r)
```

Linear functions are parameters of `lolli` type, applied like ordinary
OCaml functions (application nests and curries):

```ocaml
let%source compose2 (f : (q, q) lolli) (g : (q, q) lolli) (x : q) =
  f (g x)
```

A `lolli` parameter is a wire bundle — a physically real function value —
and application is boundary splicing with another concrete circuit, not
"instantiation" of a template.

## 5. Coherent case

### Over `qbool`

`case` is tag-preserving: the scrutinee's tag survives in the result,
paired with the branch value.  Both branches must return the same
first-order type and consume the same context:

```ocaml
let%source fixed_control (p : (qbool, q) tensor) =
  let (c, target) = split p in
  case c
    ~zero:(h target)
    ~one_:(s target)
```

The quantum switch is the canonical example — both branches consume both
functions, in opposite composition orders:

```ocaml
let%source qswitch_hs (p : (qbool, q) tensor) =
  let (b, x) = split p in
  case b
    ~zero:(h (s x))
    ~one_:(s (h x))
```

### Over a general first-order sum

`~left_:`/`~right_:` scrutinize any `('a, 'b) plus`:

```ocaml
let%source sum_case (s : (q, q) plus) (y : q) =
  case s
    ~left_:(h y)
    ~right_:(z y)
```

Note what a case *cannot* do: select a **function value** coherently.
Branches of `lolli` type are rejected ("a case result must be
first-order data") — that is the unsound "Reading B" of the higher-order
qif, closed by the first-order restriction.

## 6. Datatypes: the Qudit(n) abstraction

Declare a nominal n-state datatype with ordinary variant syntax:

```ocaml
type traffic = Red | Amber | Green [@@source.datatype]
```

This generates a sealed module `Traffic` (capitalized type name) with
`Traffic.t`, `Traffic.p` (its type witness), arity, and labels.
Constructor order is declaration order and is the sole label/code
authority.  The hidden representation is an internal first-order sum;
no injection, observation, equality test, or representation access is
exposed — constructors are *labels*, not runtime state preparation.
Declarations are generative: two same-arity datatypes are distinct
types.

### Selection

`select` dispatches certified operations by label (one operation per
constructor, checked at the exact arity):

```ocaml
let traffic_gate = Traffic.select ~target:P.q [ Op.h; Op.s; Op.t ]

let%source dispatch (p : (Traffic.t, q) tensor) = traffic_gate p
```

### Matching

Exhaustive `match` on a datatype scrutinee, with the tag preserved in
the result:

```ocaml
let%source signal (d : Traffic.t) (y : q) =
  match d with
  | Red -> h y
  | Amber -> s y
  | Green -> t y
```

Arms may appear in any order (declaration order is authoritative), must
cover every constructor exactly once, carry no payloads or guards or
wildcards, return one first-order type, and consume one shared context.
Each violation has a located diagnostic (missing constructor, duplicate
arm, unknown constructor, constructor of another datatype, wildcard,
context mismatch, higher-order result).

### Permutations and involutions

A certified label permutation lists, at position *i*, the destination of
constructor *i* (forward: |i⟩ ↦ |p(i)⟩):

```ocaml
let rotate = Traffic.permute [ Amber; Green; Red ]     (* Red→Amber, … *)

let swap_red_amber = Traffic.involution_permute [ Amber; Red; Green ]

let partial_swap = Op.exp_i (Float.pi /. 4.0) swap_red_amber
```

`permute` validates length, range, and bijectivity; `involution_permute`
additionally proves p(p(i)) = i — a 3-cycle is a valid permutation but is
rejected as an involution.  For non-power-of-two arities the padding
states of the tag register are untouched.  Group structure is *derived*,
not assumed: shifts and negations are declared permutations, and modular
addition is `Zn.select ~target:Zn.p [shift_0; …; shift_(n-1)]`.

## 7. Host operations

The gate names `h s t x y z cx not_bool` are built in.  Any other
lowercase identifier applied in a source body is a **host operation** — a
certified `('a, 'a) op` value defined in ordinary OCaml with the sealed
`Op` combinators (`Op.compose`, `Op.tensor`, `Op.twist`, `Op.exp_i`,
`Op.rz`, `Op.phase`, `Op.seal`, datatype `select`/`permute`, …), then
used by name:

```ocaml
let partial_twist = Op.exp_i (Float.pi /. 4.0) (Op.involution_twist P.q)

let%source blend (p : (q, q) tensor) = partial_twist p
```

A non-endomorphism host operation (a distributor, a coherence whose
domain differs from its codomain) is applied with an explicit annotation
that fixes both types before OCaml inference:

```ocaml
let dl = Op.dist_left P.q P.q P.q

let%source distribute (p : (((q, q) plus, q) tensor)) =
  (dl : ((((q, q) plus, q) tensor,
          ((q, q) tensor, (q, q) tensor) plus) lolli)) p
```

This is how the formal closed-operation environment Σ is realized:
operations are lexically resolved OCaml bindings of sealed `Source.op`
values.  There is no runtime operation registry.

## 8. Polymorphism with visible witnesses

A type variable in Source annotations is introduced by an explicit
leading witness parameter `(a : 'a P.t)` — an ordinary, visible OCaml
parameter.  There are no hidden arguments.  The polymorphic quantum
switch:

```ocaml
let%source qswitch (a : 'a P.t)
    (f : ('a, 'a) lolli) (g : ('a, 'a) lolli) (p : (qbool, 'a) tensor) =
  let (b, x) = split p in
  case b
    ~zero:(f (g x))
    ~one_:(g (f x))
```

Instantiate by applying the witness: `qswitch P.q`,
`qswitch (P.tensor P.q P.q)`, ….

## 9. Diagnostics summary

The rewriter reports, at precise source locations: unknown types,
lolli-under-plus, unbound variables, dropped/duplicated variables,
overlapping application contexts, case/match context mismatches,
non-first-order branch results, mixed case label sets, non-sum
scrutinees, non-exhaustive/duplicate/unknown/foreign/wildcard match
arms, bad host-operation annotations, and malformed permutation lists.
The sealed calculus re-checks typing, linearity, context routing, and
the first-order restriction independently — a frontend bug cannot
produce an ill-typed or non-linear term (semantic fidelity is separately
pinned by circuit-equality tests against handwritten oracles; see
[`VERIFICATION.md`](VERIFICATION.md)).

## 10. Building and running

```bash
cd quant_proto_phase01/ocaml
dune build                       # everything
dune test                        # complete suite, incl. doc examples
dune exec examples/doc_examples.exe   # this guide's programs
dune exec demos/source_quickstart_e2e.exe
```

For the demo catalogue and its relation to the concise counterparts, see
[`../ocaml/demos/README.md`](../ocaml/demos/README.md).  For
reproduction commands and expected results, see
[`VERIFICATION.md`](VERIFICATION.md).

## Appendix: what the expansion looks like (implementation detail)

The rewriter elaborates `let%source` into the sealed calculus, which
uses explicit context-routing witnesses (`U0`/`UL`/`UR`), rank-2 binder
records (`run_lam`/`run_split`), and typed `use` occurrences.  **These
never appear in user programs** — they are the generated target, shown
here only so the expansion is not mysterious.  Display it read-only
with the standalone driver:

```bash
dune exec ppx/qpl_source_pp.exe -- path/to/file.ml
```

For the sealed API itself see [`OCAML_DSL.md`](OCAML_DSL.md); for the
datatype elaboration design see
[`DATATYPE_ELABORATION.md`](DATATYPE_ELABORATION.md).
