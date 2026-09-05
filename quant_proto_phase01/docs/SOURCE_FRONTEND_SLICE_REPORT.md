# Source Frontend Vertical Slice — Report

Status: **uncommitted, for review.**  Companion:
`SOURCE_FRONTEND_LEDGER.md` (corrected 34-row feasibility ledger).
Base: HEAD `a052e14` ("feat: add sealed Source calculus").  No
production, demo, `.output`, Python, or paper file was modified; the
working tree adds only the frontend, its tests, and these two
documents (see §7).

## 1. What was built

A ppxlib rewriter (`ocaml/ppx/qpl_source_ppx.ml`) that elaborates
`let%source` bindings written in ordinary OCaml syntax into the
**unchanged** sealed `Qpl_surface.Source` combinators, plus:

- `ocaml/ppx/qpl_source_pp.ml` — standalone driver
  (`Ppxlib.Driver.standalone`), used by the compile-reject harness via
  `ocamlc -ppx "… --as-ppx"` and for read-only expansion display.  The
  rewriter never writes files; no environment variable changes its
  behavior.
- `ocaml/test/test_source_ppx_slice.ml` — the three positive cases,
  each verified against a handwritten sealed oracle through
  `Bridge.eq_circ`, with pinned circuit facts.  Runs under `dune test`.
- `ocaml/test/source_frontend_harness.ml` +
  `ocaml/test/source_frontend/` — compile-pass/compile-fail
  conformance: 1 canary pass fixture and 6 reject fixtures whose
  `.diag` files pin both the **source location** (file, line,
  character span) and the diagnostic text.  Runs under `dune test`.

Dependency direction: `qpl_surface` (the library) is untouched and has
no new dependency.  ppxlib is a build-time dependency of the separate
`qpl_surface.source_ppx` library (kind `ppx_rewriter`); user programs
opt in with `(preprocess (pps qpl_source_ppx))`.  The generated code
refers to `Qpl_surface.Source` by fully qualified paths, so it links
against the sealed library only.

## 2. Trust statement (corrected)

The PPX is a **semantic compiler component**.  The sealed GADT
re-checks typing, linearity, context partitioning, and the first-order
sum restriction of whatever the rewriter emits — so a buggy rewriter
cannot produce an ill-typed or non-linear term.  It can, however,
produce a *well-typed wrong* term: swapped operations, exchanged
branches, misrouted variables.  The sealed GADT does **not** prove the
rewriter preserved the user's meaning.  That is established only by
this slice's tests: positive expansion checks against handwritten
sealed oracles with circuit equality (`eq_circ`, fidelity 1.0) and
pinned gate/wire/permutation facts.

## 3. Explicitness rules (as implemented)

- Every Source parameter carries an annotation in the sealed grammar:
  `q`, `qbool`, `('a,'b) tensor/plus/lolli`, a datatype `M.t`, or a
  type variable.
- Every type variable is introduced by a **visible** leading witness
  parameter `(a : 'a P.t)` — an ordinary OCaml parameter of the
  generated value.  There are no hidden arguments.
- Result types are computed bottom-up by the Source typing rules from
  the parameter annotations (application peels `lolli`, tuples build
  `tensor`, `split` projects, `case` yields `(qbool, branch) tensor`).
  An explicit result annotation is accepted and checked; it is required
  whenever a leaf type cannot be determined.
- Handwritten `use`/`U0`/`UL`/`UR`/`using`/`run_lam`/`run_split` do
  not appear in user programs (they appear only in the expansion).
- Datatype selectors take literal lists; no `VCons`/`VNil`/`@:` in
  user code.

## 4. Positive cases

### 4A. source_quickstart

User source:

```ocaml
let%source quickstart_sugar (p : (q, q) tensor) =
  let (l, r) = split p in
  (h l, s r)
```

Generated expansion (via the read-only standalone driver):

```ocaml
let quickstart_sugar =
  Qpl_surface.Source.lam ~name:"p"
    (Qpl_surface.Source.S.tensor Qpl_surface.Source.q Qpl_surface.Source.q)
    (Qpl_surface.Source.S.tensor Qpl_surface.Source.q Qpl_surface.Source.q)
    {
      Qpl_surface.Source.run_lam =
        (fun p ->
           Qpl_surface.Source.let_tensor ~left_name:"l" ~right_name:"r"
             Qpl_surface.Source.q Qpl_surface.Source.q
             (Qpl_surface.Source.use p)
             {
               Qpl_surface.Source.run_split =
                 (fun l r ->
                    Qpl_surface.Source.pair
                      (Qpl_surface.Source.Op.apply Qpl_surface.Source.Op.h
                         (Qpl_surface.Source.use l))
                      (Qpl_surface.Source.Op.apply Qpl_surface.Source.Op.s
                         (Qpl_surface.Source.use r))
                      (Qpl_surface.Source.UL
                         (Qpl_surface.Source.UR Qpl_surface.Source.U0)))
             } (Qpl_surface.Source.UL Qpl_surface.Source.U0))
    }
```

Verified: compiles through the bridge to **4 qubits, 2 gates, wire
permutation `[2,3,0,1]`** (pinned), and `Bridge.eq_circ` against the
handwritten sealed oracle (the committed
`source_quickstart_e2e` construction) reports **equal, fidelity
1.000000**.

### 4B. Genuinely polymorphic qswitch

User source — the witness convention is explicit and visible, and the
body is the mandated shape:

```ocaml
let%source qswitch (a : 'a P.t)
    (f : ('a, 'a) lolli) (g : ('a, 'a) lolli) (p : (qbool, 'a) tensor) =
  let (b, x) = split p in
  case b
    ~zero:(f (g x))
    ~one_:(g (f x))
```

Generated expansion (complete):

```ocaml
let qswitch (a : 'a Qpl_surface.Source.P.t) =
  Qpl_surface.Source.lam ~name:"f"
    (Qpl_surface.Source.S.lolli (Qpl_surface.Source.S.data a)
       (Qpl_surface.Source.S.data a))
    (Qpl_surface.Source.S.lolli
       (Qpl_surface.Source.S.lolli (Qpl_surface.Source.S.data a)
          (Qpl_surface.Source.S.data a))
       (Qpl_surface.Source.S.lolli
          (Qpl_surface.Source.S.tensor Qpl_surface.Source.qbool
             (Qpl_surface.Source.S.data a))
          (Qpl_surface.Source.S.tensor Qpl_surface.Source.qbool
             (Qpl_surface.Source.S.data a))))
    {
      Qpl_surface.Source.run_lam =
        (fun f ->
           Qpl_surface.Source.lam ~name:"g"
             (Qpl_surface.Source.S.lolli (Qpl_surface.Source.S.data a)
                (Qpl_surface.Source.S.data a))
             (Qpl_surface.Source.S.lolli
                (Qpl_surface.Source.S.tensor Qpl_surface.Source.qbool
                   (Qpl_surface.Source.S.data a))
                (Qpl_surface.Source.S.tensor Qpl_surface.Source.qbool
                   (Qpl_surface.Source.S.data a)))
             {
               Qpl_surface.Source.run_lam =
                 (fun g ->
                    Qpl_surface.Source.lam ~name:"p"
                      (Qpl_surface.Source.S.tensor Qpl_surface.Source.qbool
                         (Qpl_surface.Source.S.data a))
                      (Qpl_surface.Source.S.tensor Qpl_surface.Source.qbool
                         (Qpl_surface.Source.S.data a))
                      {
                        Qpl_surface.Source.run_lam =
                          (fun p ->
                             Qpl_surface.Source.let_tensor ~left_name:"b"
                               ~right_name:"x" Qpl_surface.Source.qbool
                               (Qpl_surface.Source.S.data a)
                               (Qpl_surface.Source.use p)
                               {
                                 Qpl_surface.Source.run_split =
                                   (fun b x ->
                                      Qpl_surface.Source.case_bool ~result:a
                                        ~scrutinee:(Qpl_surface.Source.use b)
                                        ~zero:(Qpl_surface.Source.app
                                                 (Qpl_surface.Source.use f)
                                                 (Qpl_surface.Source.app
                                                    (Qpl_surface.Source.use g)
                                                    (Qpl_surface.Source.use x)
                                                    (Qpl_surface.Source.UR
                                                       (Qpl_surface.Source.UL
                                                          Qpl_surface.Source.U0)))
                                                 (Qpl_surface.Source.UR
                                                    (Qpl_surface.Source.UR
                                                       (Qpl_surface.Source.UL
                                                          Qpl_surface.Source.U0))))
                                        ~one_:(Qpl_surface.Source.app
                                                 (Qpl_surface.Source.use g)
                                                 (Qpl_surface.Source.app
                                                    (Qpl_surface.Source.use f)
                                                    (Qpl_surface.Source.use x)
                                                    (Qpl_surface.Source.UR
                                                       (Qpl_surface.Source.UL
                                                          Qpl_surface.Source.U0)))
                                                 (Qpl_surface.Source.UR
                                                    (Qpl_surface.Source.UL
                                                       (Qpl_surface.Source.UR
                                                          Qpl_surface.Source.U0))))
                                        ~using:(Qpl_surface.Source.UL
                                                  (Qpl_surface.Source.UR
                                                     (Qpl_surface.Source.UR
                                                        (Qpl_surface.Source.UR
                                                           Qpl_surface.Source.U0)))))
                               }
                               (Qpl_surface.Source.UL
                                  (Qpl_surface.Source.UR
                                     (Qpl_surface.Source.UR
                                        Qpl_surface.Source.U0))))
                      })
             })
    }
```

Semantic evidence in the expansion itself: in `~zero:` the routing
`UR (UL U0)` / `UR (UR (UL U0))` threads `x` into `g` first and the
result into `f` (that is, `f (g x)`), while `~one_:` threads `x` into
`f` first (`g (f x)`) — the two branches route the *same* nominal
context `{f, g, x}` through opposite compositions, which is exactly
the qswitch semantics and is where a well-typed-but-wrong rewriter
could silently swap branches.  The circuit tests below close that gap.

Verified:

- The polymorphic abstraction typechecks against the unchanged sealed
  GADT, and `qswitch P.q` emits and compiles as a closed higher-order
  Source term (12 qubits, 6 gates — the abstract-boundary form).
- The first-order specialization with the same body shape:

```ocaml
let%source qswitch_hs (p : (qbool, q) tensor) =
  let (b, x) = split p in
  case b
    ~zero:(h (s x))
    ~one_:(s (h x))
```

compiles to **4 qubits, 6 gates `X, CS, CH, X, CH, CS`, permutation
`[2,3,0,1]`** (pinned — the anti-control sandwich with H∘S on the
zero branch and S∘H on the one branch), and `Bridge.eq_circ` against
the handwritten `case_bool` oracle reports **equal, fidelity
1.000000**.

### 4C. Datatype selector, literal-list syntax

User source:

```ocaml
type z5 = E0 | E1 | E2 | E3 | E4 [@@source.datatype]

let z5_gate = Z5.select ~target:P.q [ Op.h; Op.s; Op.t; Op.x; Op.z ]

let%source selector_sugar (p : (Z5.t, q) tensor) = z5_gate p
```

Generated expansion (complete):

```ocaml
module Z5 =
  ((Qpl_surface.Source.Datatype.Make)(struct
      type tail =
        Qpl_surface.Source.Datatype.zero
          Qpl_surface.Source.Datatype.succ
          Qpl_surface.Source.Datatype.succ
          Qpl_surface.Source.Datatype.succ
          Qpl_surface.Source.Datatype.succ
      let name = "z5"
      let labels =
        Qpl_surface.Source.Datatype.VCons
          ("E0", (Qpl_surface.Source.Datatype.VCons
            ("E1", (Qpl_surface.Source.Datatype.VCons
              ("E2", (Qpl_surface.Source.Datatype.VCons
                ("E3", (Qpl_surface.Source.Datatype.VCons
                  ("E4", Qpl_surface.Source.Datatype.VNil)))))))))
    end))(struct  end)
type z5 = Z5.t[@@warning "-34"]
let z5_gate =
  Z5.select ~target:P.q
    (Qpl_surface.Source.Datatype.VCons
       (Op.h, (Qpl_surface.Source.Datatype.VCons
         (Op.s, (Qpl_surface.Source.Datatype.VCons
           (Op.t, (Qpl_surface.Source.Datatype.VCons
             (Op.x, (Qpl_surface.Source.Datatype.VCons
               (Op.z, Qpl_surface.Source.Datatype.VNil))))))))))
let selector_sugar =
  Qpl_surface.Source.lam ~name:"p"
    (Qpl_surface.Source.S.tensor (Qpl_surface.Source.S.data Z5.p)
       Qpl_surface.Source.q)
    (Qpl_surface.Source.S.tensor (Qpl_surface.Source.S.data Z5.p)
       Qpl_surface.Source.q)
    {
      Qpl_surface.Source.run_lam =
        (fun p ->
           Qpl_surface.Source.Op.apply z5_gate (Qpl_surface.Source.use p))
    }
```

(The nesting of the `VCons` chains is shown compacted here for
readability; the driver output differs only in whitespace.)

Verified: `Z5.arity = 5`, `Z5.labels = [E0; E1; E2; E3; E4]` (the
generative `Datatype.Make` still runs its own label validation);
`selector_sugar` compiles to **8 qubits, 25 gates, permutation
`[4,5,6,7,0,1,2,3]`** (pinned), and `Bridge.eq_circ` against the
handwritten GADT-vector oracle reports **equal, fidelity 1.000000**.

## 5. Compile-reject cases

Harness: `source_frontend_harness.ml` copies each fixture into a fresh
temporary directory and runs
`ocamlc -I <qpl_surface> -ppx "<qpl_source_pp.exe> --as-ppx"
-stop-after typing -c`, requiring exit code 2 and every fragment of
the fixture's `.diag` file in stderr.  Each `.diag` pins the **source
location** (file, line, character span) as well as the message.  A
canary pass fixture (`pass_quickstart.ml`) proves a broken driver
cannot make the rejects pass vacuously.  All observed diagnostics
below are real harness output.

| Fixture | Offending code | Located diagnostic (observed) |
|---|---|---|
| `reject_dropped_variable.ml` | `let (l, r) = split p in h l` | `line 7, characters 10-11` (exactly the binder `r`): `Source: r is bound here but never used; both tensor components must be consumed exactly once` |
| `reject_duplicated_variable.ml` | `(h x, s x)` | `line 6, characters 2-12` (the pair): `Source: variable x is used on both sides here; a linear variable is consumed exactly once` |
| `reject_app_overlap.ml` | `f (f x)` | `line 7, characters 2-9` (the application): `Source: variable f is used on both sides here; a linear variable is consumed exactly once` |
| `reject_case_context_mismatch.ml` | `case b ~zero:(h u) ~one_:(h v)` | `lines 6-8` (the case): `Source: both case branches must consume the same nominal linear context; ~zero: uses [u] but ~one_: uses [v]` |
| `reject_lolli_under_plus.ml` | `(p : ((q, q) lolli, q) plus)` | `line 5, characters 21-33` (exactly the `(q, q) lolli` annotation): `Source: a sum admits only first-order data; (q, q) lolli contains a function space beneath plus` |
| `reject_selector_arity.ml` | 3-label datatype, `Z3.select ~target:P.q [ Op.h; Op.s ]` | `line 9, characters 10-46` (the select application): OCaml type error `This expression has type (Datatype.zero, 'a) Datatype.vector but an expression was expected of type (Datatype.zero Datatype.succ, (q, q) op) Datatype.vector` — the length-indexed vector pins 3 vs 2 |
| _(canary)_ `pass_quickstart.ml` | valid quickstart program | accepted (exit 0) |

Note the division of labor, which is the intended architecture: the
first five rejections are the **rewriter's own located diagnostics**
(raised before the GADT ever sees the term, at the precise token);
the selector-arity rejection is deliberately left to the **sealed
GADT's length-indexed vector**, demonstrating that the frontend does
not weaken the calculus — even syntax it rewrites (literal lists) is
re-checked by the sealed types.

## 6. Test runs (all real output)

- `dune test` (full OCaml suite, from `ocaml/`): exit 0, no failures —
  all pre-existing suites plus the two new ones.
- Slice: `ALL SLICE CHECKS PASSED` — every `PASS` line for quickstart
  facts/oracle, qswitch compile, qswitch_hs facts/oracle, Z5
  arity/labels, selector facts/oracle.
- Frontend conformance:
  `Source frontend: 1 compile-pass and 6 compile-fail fixtures verified.`
- The existing sealed-API conformance harness
  (`source_typecheck_harness`) still passes untouched (its own pass /
  reject / runtime-gate lines all `PASS`).

## 7. Files touched (everything is uncommitted)

New: `ocaml/ppx/{dune, qpl_source_ppx.ml, qpl_source_pp.ml}`,
`ocaml/test/test_source_ppx_slice.ml`,
`ocaml/test/source_frontend_harness.ml`,
`ocaml/test/source_frontend/pass/pass_quickstart.ml`,
`ocaml/test/source_frontend/reject/*.{ml,diag}` (6 pairs),
`docs/SOURCE_FRONTEND_LEDGER.md`, this report.

Modified: `ocaml/test/dune` only (the slice test stanza, the harness
executable, and its runtest rule).

Not touched: `ocaml/lib/` (sealed calculus unchanged), `ocaml/demos/`,
all `.output` files, all of `python/`, SeqCut/Align/compiler layout,
the paper, `RadhaMSG/`.

## 8. Known MVP limitations (honest list)

1. **Host non-endomorphisms.** An unknown host operation applied in a
   source body is typed as an endomorphism.  A non-endomorphism op
   (e.g. `Op.dist_left`) therefore produces a *sound but unlocated*
   rejection from the sealed GADT rather than a frontend diagnostic
   (ledger extension E3).
2. **Case sugar covers `qbool` only.**  The sealed general
   tag-preserving `case` over `('a,'b) plus` has no surface syntax yet
   (ledger extension E1).
3. **Binary tuples only** in pair syntax and split patterns; nesting
   must be written explicitly.
4. **No non-tuple `let`** (sequencing) inside source bodies yet.
5. The `qswitch` abstract instantiation is exercised at `P.q`
   compile-only in the slice; its instance-level circuit equality is
   covered via `qswitch_hs` (the same body shape with gates in
   place).  A migrated row-1/row-23 counterpart will also `eq_circ`
   the instantiated abstract form against the Raw open-term circuits.

## 9. What is explicitly not claimed

- No demo migration was performed (per instruction); the ledger
  records per-row feasibility and each row's future automated check.
- The sealed GADT's acceptance of the expansions proves typing,
  linearity, routing well-formedness, and the first-order sum
  restriction — **not** meaning preservation.  Meaning preservation
  is exactly what the oracle-equality tests in §4 establish, and any
  frontend change must keep them green.
