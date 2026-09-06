# Legacy Python-driven e2e/golden harness (historical)

> **HISTORICAL / AUXILIARY.**  This directory predates the current
> OCaml-native test suites.  It is a pytest harness that shells out to
> `dune` and compares backend goldens for a handful of early phase-0
> terms, plus early "surface" tests written against a since-replaced
> prototype elaborator.  **It is not the current Source implementation's
> test suite and is not part of the v1.0.0 verification surface.**
>
> The current verification surface is: `dune test` under `ocaml/`
> (including the frontend conformance harness, the counterpart coverage
> harness, and the datatype invariants) and
> `PYTHONPATH=python/src pytest python/tests` — see
> `docs/VERIFICATION.md`.

Kept for archaeology; may skip or fail without the legacy layout it
assumed.  Do not extend it.
