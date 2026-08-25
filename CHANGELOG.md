# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html)
loosely — this is a research prototype; version bumps track soundness,
compatibility, and observable-behavior changes rather than strict API
churn.

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
