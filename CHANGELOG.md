# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html)
loosely — this is a research prototype; version bumps track soundness,
compatibility, and observable-behavior changes rather than strict API
churn.

## [1.0.0] — 2026-09-05 — Granthi v1.0.0

Granthi is now a usable research language.  The public user interface is
the ergonomic `let%source` Source syntax; internal Raw/Bridge/Python
compiler APIs remain available but are not part of the public interface
promise.

### Added
- **Ergonomic `let%source` frontend** (`ocaml/ppx/`, ppxlib ≥ 0.37):
  annotated parameters over the sealed type grammar, tuples/`split`,
  linear application, `case` over `qbool` and general first-order sums,
  annotation-directed non-endomorphism host operations, visible
  polymorphism witnesses, and located diagnostics for every linearity,
  typing, and exhaustiveness violation (23 compile-reject conformance
  fixtures).
- **Sealed Source calculus** (`Qpl_surface.Source`): intrinsically typed,
  linearity- and context-checked; no Raw injection, no public Unit, no
  open-branch sum map; one-way `emit` to the Bridge.
- **First-order datatype elaboration** (`[@@source.datatype]`, the
  Qudit(n) abstraction): generative nominal datatypes with `select`,
  exhaustive ordinary `match`, and certified label permutations and
  involutions (`permute`, `involution_permute`, constructor-name PPX
  sugar; forward convention; padding states fixed; canonical
  left-associated hidden representation pinned structurally).  Derived
  group operations: Zₙ shifts/negations as declared permutations,
  addition as selector-of-shifts.  Per-label phased dispatch derived
  from `Op.phase` composed into selector branches.
- **34-demo Source counterpart coverage** (`ocaml/counterparts/`): every
  historical demo behaviour has an executed concise Source counterpart,
  verified against legacy Raw/Linear or handwritten sealed oracles
  (baseline 112 checks / 0 failed), with a machine-validated coverage
  ledger (`coverage.tsv`) and an anti-vacuity lexical scan.
- **Compiled documentation examples** (`ocaml/examples/doc_examples.ml`):
  every program advertised in the Programming Guide builds with the real
  PPX and compiles end-to-end in `dune test`.
- Canonical dependency manifests (`requirements.txt`, dune-project
  version/dependency declarations) and a reworked CI and reproduction
  surface.

### Changed
- **Open-sum/distributivity completion:** all four distributivity
  constructors (`DistL`/`DistR`/`UndistL`/`UndistR`) compile gate-free
  under the boundary-frame/Align repair; the previously failing
  unequal-width naturality witness now passes at fidelity 1.0.  The
  open-sum backend is blockwise with capability dispatch (see
  `docs/LIMITATIONS.md §10`).
- **Semantic relational SeqCut:** general `Seq` composition goes through
  a single `CutTransport` → `seq_cut` authority (transactional; refusals
  instead of miscompilation).
- **Beta-boundary repair:** beta-reduced applications inherit exact
  boundaries from argument artifacts; the last red witness closed at
  checkpoint `beta-boundary-20260905`.
- Documentation restructured for v1.0.0: `docs/PROGRAMMING_GUIDE.md`
  rewritten around the Source syntax; `docs/INDEX.md`,
  `docs/VERIFICATION.md` added; historical records moved to
  `docs/history/`; `docs/LIMITATIONS.md` is the sole limitations
  authority.

### Known limitations / deferred
- See `docs/LIMITATIONS.md` (authoritative).  Notably: general sums
  remain first-order (by design — the soundness fix); sealed-surface
  coherent ⊕-introduction is intentionally absent (closed-premise Raw
  introduction exists); pytket width ceilings on some fallback paths;
  **Align normalization is deferred post-v1.0.0** — an
  optimization/normalization item, not a correctness blocker
  (`docs/ALIGN_NORMALIZATION.md`).

### Verification baseline (2026-09-05)
- Python suite: 1570 passed / 0 failed.
- Complete OCaml `dune build` + `dune test`: green, including the
  frontend harness (1 pass + 23 reject fixtures), counterpart coverage
  (112/0), datatype invariants, and compiled doc examples.
- Demos: 32 golden demos byte-identical to committed outputs; 2
  intentional no-fixture dumps run successfully.

---

## [0.2] — Soundness fix: first-order restriction on sum payloads

**No loss of expressiveness.** The restriction is a canonical-form
requirement: every higher-order program has a first-order representative
obtained by full η-expansion (atomic arguments as explicit λ-arguments;
ambient function values in the λ-context, not in a sum payload). New
demos `qswitch_eta_endoQ_e2e.ml` and `ctrl_ho_eta_e2e.ml` illustrate
the pattern.

### Added
- `first_order` predicate in `ocaml/lib/linear.ml` with guards on
  `case_hom`, `case_hom0`, `ocase_hom`, `ocase_hom0`, datatype
  `control`, and `phased_control`.
- Python-side defense-in-depth check
  `_assert_first_order_sum_payloads` in
  `python/src/compile/to_pytket.py`.
- Regression tests:
  - `ocaml/test/test_first_order_sum_payloads.ml` (7 tests)
  - `ocaml/test/test_first_order_directional.ml` (6 tests certifying
    Guard 2's target-only property)
- Demos:
  - `ocaml/demos/reader_qif_ocaml_attempt.ml` — regression for the
    externally-reported term
  - `ocaml/demos/qswitch_eta_expansion_e2e.ml` — generic qswitch at
    any first-order payload
  - `ocaml/demos/qswitch_eta_endoQ_e2e.ml` — η-expanded qswitch at
    higher-order `A = Q ⊸ Q`
  - `ocaml/demos/ctrl_ho_eta_e2e.ml` — directional guard certification
    via raw split-context `oplusmap`
  - `ocaml/demos/qif_cnot_verify_e2e.ml` — CNOT via case_hom, with an
    updated header describing the actual soundness fix

### Changed
- `docs/LIMITATIONS.md §4` rewritten to describe the actual
  enforcement (first-order restriction on sum payloads) rather than
  the earlier "⊕-as-routing-interface" framing.
- `docs/LIMITATIONS.md §1b` tightened: previous "OCaml pipeline
  elaborated terms are always decomposable" was too strong. Precise
  statement: *first-order* elaborated terms are always decomposable;
  higher-order Apply/Lam chains inside PlusMap branches are opaque
  to auto-flatten and share the Python-API branch-width limit.
- Top-level `README.md` and `quant_proto_phase01/python/README.md`
  extended with the OCaml-side prescribed-route caveat.

### Compatibility
- All previous demos run unchanged.
- Full OCaml `dune test` suite: exit 0.
- Full Python `pytest` suite: 537 passed.
- All 24 OCaml demos: pass.

### Attribution
Prompted by a soundness report from **Kengo Hirata**, based on the
LICS 2026 paper *Causality in Pure Quantum Computation with Quantum
Control* by Kengo Hirata and Takeshi Tsukada
([Dagstuhl DOI](https://drops.dagstuhl.de/entities/document/10.4230/LIPIcs.LICS.2026.57)).

---

## [0.1] — OOPSLA 2026 Artifact Evaluation submission

Initial public release. Zenodo v1 and v2 archives correspond to the
`oopsla26-ae` and `oopsla26-ae-v2` git tags respectively.
