# Release Notes

## v1.0.1 — Documentation and reproduction corrections

A patch release: documentation, comments, reproduction scripts, and
release presentation only.  No compiler semantics, circuit output,
golden files, or the v1.0.0 tag were touched.

Highlights:

- **Limitations brought up to date with the shipped compiler**:
  `ctrl_ho_eta_e2e` compiles exactly through the open-use Block path
  (80-dimensional selected boundary, zero leakage and phase, both
  modes) and is no longer listed as width-blocked; §10 now records the
  implemented `SourcePortRef` / `BranchMainProjection` /
  completed-Block / `CutFace` machinery, retaining only the real
  asymmetric closed dense-synthesis restriction.
- **Curried-selector record corrected**: 23 commands is the inner
  pipeline; the complete selector is the 25-gate optimization baseline;
  the applied H/S/T selector already carries an exact independent
  oracle (`rtol=0`, zero leakage, both materialization modes); a dense
  oracle for the unapplied abstract function value remains deferred
  with Align normalization.
- **Reviewer instructions repaired**: `ppxlib>=0.37` added to the
  native install; Docker results mount corrected; `PYTHONPATH`
  prepends the repository backend.
- **Stale API/example docs fixed**: no `weaken`, exact `o_n_plusmap`
  signature, legacy Raw QSwitch clearly labeled with pointers to the
  current Source program; no public reference to unavailable files.
- v1.0.0 published as a GitHub Release from its immutable tag.

The v1.0.0 verification baselines are unchanged and still govern
(`docs/VERIFICATION.md`).

---

## v1.0.0 — Granthi as a usable research language

### Summary

Granthi v1.0.0 makes the language usable: programs are written in the
ergonomic `let%source` Source syntax — ordinary OCaml syntax with linear
typing, coherent case analysis, first-order datatypes, and higher-order
functions as physically real wire bundles — and compiled through the
sealed Source calculus to pytket circuits.

**Interface promise.** The public v1.0.0 interface is the `let%source`
Source surface (and the sealed `Qpl_surface.Source` module it targets).
The internal Raw/Linear, Bridge, and Python compiler APIs remain in the
tree, tested, for compiler development and regression purposes; they are
*not* promised as stable public APIs.

### Highlights

- **Ergonomic frontend.**  `let%source` bindings with annotated
  parameters; tuples and `split`; linear application; `case` over
  `qbool` and general first-order sums; ordinary `match` over declared
  datatypes; visible polymorphism witnesses (`(a : 'a P.t)`);
  annotation-directed non-endomorphism host operations.  Every
  violation of linearity, typing, or exhaustiveness is a located
  compile-time diagnostic.
- **Sealed Source calculus.**  The PPX's target re-proves typing,
  linearity, context routing, and the first-order sum restriction
  independently — and the frontend's *meaning*-preservation is pinned by
  circuit-equality tests against handwritten oracles.
- **First-order datatypes** (`[@@source.datatype]`): the Qudit(n)
  abstraction — generative nominal types elaborating to hidden
  first-order sums, with selection, exhaustive matching, and certified
  label permutations/involutions (forward convention, padding fixed,
  canonical left-associated representation pinned structurally).  Group
  operations are derived, not assumed: shifts/negations are declared
  permutations; addition is a selector of shifts.
- **Complete counterpart coverage.**  All 34 historical demo behaviours
  have executed concise Source counterparts, semantically checked
  against legacy oracles (112 checks at the release baseline) under a
  machine-validated coverage ledger; the retained Raw demos continue to
  serve as independent oracles and golden regressions.
- **Compiler completions.**  Gate-free distributivity for all four
  distributors with naturality witnesses at fidelity 1.0; the blockwise
  open-sum backend with capability dispatch; semantic relational SeqCut
  composition; beta-boundary inheritance.  Compositions the authorities
  cannot certify are refused, never silently miscompiled.

### Limitations and deferrals

`docs/LIMITATIONS.md` is the sole authority.  In brief: general sums are
first-order by design (the v0.2 soundness fix, unchanged); the sealed
surface exposes no coherent ⊕-introduction (a closed-premise Raw
introduction exists internally); some fallback code paths have pytket
width ceilings; **Align normalization is deferred post-v1.0.0** — it
concerns circuit size at splices, not correctness
(`docs/ALIGN_NORMALIZATION.md`).

### Verification baseline (2026-09-05)

- Python backend suite: **1570 passed / 0 failed**.
- Complete OCaml `dune build` + `dune test`: green — frontend harness
  (1 pass + 23 located reject fixtures), counterpart coverage
  (**112 / 0** with ledger cross-validation and anti-vacuity scan),
  datatype invariants, compiled documentation examples.
- Demo battery: **32 golden demos byte-identical** to committed outputs
  plus 2 intentional no-fixture dumps.

See `docs/VERIFICATION.md` for reproduction commands.

---

## v0.2 — Soundness fix: first-order restriction on sum payloads

### Summary

This release adds a soundness guard on sum-type payloads: no `⊸` (Lolli)
may appear inside the target type of `⊕-Map`, `case`, or `⊕-I`.
Function values may still be **consumed** inside a branch, but not
**returned** on a summand. **This is a canonical-form requirement, not
a loss of expressiveness** — every higher-order program has a
first-order representative obtained by full **η-expansion**: bring the
atomic arguments out as explicit λ-arguments and keep ambient function
values in the λ-context (not in a sum payload). Two new demos —
`qswitch_eta_endoQ_e2e.ml` (η-expanded qswitch at `A = Q ⊸ Q`,
compiles to a real 12-gate circuit) and `ctrl_ho_eta_e2e.ml` (the
`ctrl` analog with raw split-context `oplusmap`) — illustrate the
pattern.

### Why

An external report identified that Granthi's previous type discipline
permitted the higher-order coherent-control term

```
let (x' ⊗ f) = (case x of {L1 ↦ I | L0 ↦ X}) in f x'
```

which denotes a non-unitary map. This shape is the canonical example
studied in the LICS 2026 paper *Causality in Pure Quantum Computation
with Quantum Control* by **Kengo Hirata** and **Takeshi Tsukada**
([Dagstuhl DOI](https://drops.dagstuhl.de/entities/document/10.4230/LIPIcs.LICS.2026.57)),
which addresses it by tracking causal dependency in the type system.
This release takes the (more conservative) route of a **first-order
restriction on sum payloads**, which closes the pathology while
preserving η-expanded higher-order use cases (see new demos).

### What changed

- New `first_order` predicate in `linear.ml` plus guards on
  `case_hom`, `case_hom0`, `ocase_hom`, `ocase_hom0`, datatype
  `control`, and `phased_control`.
- Defense-in-depth check in Python's `to_pytket.py`
  (`_assert_first_order_sum_payloads`) catches any construction that
  bypasses the OCaml-level guards, including terms authored directly
  at the Python term IR.
- `docs/LIMITATIONS.md §4` rewritten to describe the actual
  enforcement points (rather than the earlier, incomplete
  "⊕-as-routing-interface" framing).
- `docs/LIMITATIONS.md §1b` tightened: previous phrasing "OCaml
  pipeline elaborated terms are always decomposable" was too strong.
  Precise statement: **first-order** elaborated terms are always
  decomposable; higher-order `oapp`/`olam` chains inside `oplusmap`
  branches are opaque to auto-flatten and share the Python-API
  branch-width limit.
- Top-level `README.md` and `quant_proto_phase01/python/README.md`
  extended with an OCaml-side prescribed-route warning: prefer
  case sugars and datatype `control` over raw `omap0` / `oplusmap0`.
  (The raw primitives remain available; ill-formed use fails at
  `Bridge.compile` via the Python defense.)

### Compatibility

**All demos from the previous version run unchanged.** No first-order
Granthi program is affected. The soundness guard only rejects
constructions that put `⊸` in a sum summand — a pattern no existing
demo used.

- Full OCaml `dune test` suite: exit 0.
- Full Python `pytest` suite: 537 passed.
- All 24 OCaml demos: pass unchanged.

### For users

Higher-order-looking use cases are still expressible via
**η-expansion**: bring the atomic arguments out as explicit
λ-arguments and put the ambient function values in the λ-context, not
in a sum payload. See:

- `ocaml/demos/qswitch_eta_endoQ_e2e.ml` — `qswitch_η` for `A = Q ⊸ Q`,
  fully η-expanded to first-order canonical form (compiles to a real
  12-gate circuit).
- `ocaml/demos/qswitch_eta_expansion_e2e.ml` — generic `qswitch_generic`
  parameterized over any first-order payload A, plus a Part 4 showing
  the ctrl-at-function-type case handled via `case_hom` at wire
  encoding.
- `ocaml/demos/ctrl_ho_eta_e2e.ml` — `ctrl_ho` at `A = Q ⊸ Q` via the
  raw split-context `oplusmap`, certifying that Guard 2 is
  **target-only** (higher-order sources are not rejected).

### New tests and demos

- `ocaml/test/test_first_order_sum_payloads.ml` — 7 tests (3 negative,
  4 positive controls). Directly tests the case sugars, `control`,
  and the Python defense-in-depth.
- `ocaml/test/test_first_order_directional.ml` — 6 tests certifying
  Guard 2's target-only property (higher-order sources / ambient
  contexts are accepted; higher-order targets rejected).
- `ocaml/demos/reader_qif_ocaml_attempt.ml` — regression test for the
  original externally-reported term. Passes when the compilation
  rejects it with the expected first-order error.
- `ocaml/demos/qif_cnot_verify_e2e.ml` — header rewritten to describe
  the accurate soundness fix (replacing the earlier incomplete
  ⊕-as-routing-interface framing).

### Known limitation

`ocaml/demos/ctrl_ho_eta_e2e.ml`'s full pipeline compilation hits the
pytket `Unitary3qBox` ceiling documented in `docs/LIMITATIONS.md §1b`
(higher-order `oapp`/`olam` chains inside `oplusmap` branches with
total width > 3 are opaque to auto-flatten and fall back to Strategy
A/B, which cannot use `UnitaryNqBox` for n > 3). The type-level guard
passes cleanly; codegen is blocked by the pytket width limit, not by
a soundness issue. The demo reports both outcomes explicitly.

### Attribution

Special thanks to **Kengo Hirata** for the concrete report and the
derivation tree that made the exact rule to fix precise.
