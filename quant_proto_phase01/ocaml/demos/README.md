# Examples and demos

## Where to look first

Concise, current Source programs live in two places:

- [`../examples/doc_examples.ml`](../examples/doc_examples.ml) — the
  Programming Guide's programs, compiled by `dune test`.
- [`../counterparts/surface_programs.ml`](../counterparts/surface_programs.ml)
  — a concise Source counterpart for **every** behaviour exercised by the
  34 historical demos in this directory: the quantum-switch family,
  selectors at arities 2–11, nested controls, algorithm cores, datatype
  group operations (Z₃…Z₁₁ shifts/negations/additions), branch-swap
  exponentials, per-label phased dispatch, the short-circuit witness, the
  QS₂/QS₃ simulators, and more.

The Source demos in this directory (`source_*.ml`, `test_first_order.ml`)
are small end-to-end entry points:

```sh
dune exec demos/source_quickstart_e2e.exe
dune exec demos/source_fixed_control_e2e.exe
dune exec demos/source_datatype_e2e.exe
dune exec demos/source_exp_twist_e2e.exe
```

## The coverage ledger

[`../counterparts/coverage.tsv`](../counterparts/coverage.tsv) is the
**authoritative ledger** relating the 34 demos to their concise Source
counterparts.  It is machine-validated on every `dune test` run by the
`run_counterparts` harness, which:

- executes over a hundred semantic checks comparing each counterpart to a
  legacy Raw/Linear or handwritten sealed oracle (circuit equality at
  fidelity 1.0, composition laws, compile pins),
- cross-checks the ledger against `manifest.tsv`,
- lexically forbids Raw/Linear/Bridge constructions and manual routing
  witnesses inside the surface-authored counterpart file.

## Why the 34 Raw demos are retained

`Linear` remains the Raw implementation language.  The historical demos
built with it serve as **independent oracles** and compiler regression
coverage: 32 have committed golden `.output` files diffed byte-for-byte
by CI and `artifact/reproduce.sh`; 2 (`dump_abstract_qswitch`,
`dump_select_5_inst`) are serialization dumps with no golden fixture, by
design.  They may express terms the sealed Source deliberately rejects,
so they should not be copied as new user syntax.

`manifest.tsv` classifies each demo (`Source`, `Raw-language diagnostic`,
`Raw/backend probe`); `coverage.tsv` records each row's counterpart,
oracle, test, and status.

## Split rows, honestly

Some rows are `split-migrated`: their expressible behaviour has a
verified Source counterpart, but the demo *also* tests machinery that is
not a surface subject, so the Raw demo remains load-bearing:

- rows 4, 9, 10, 17 — backend/Raw inspection (guard certification,
  distributivity layout probes, the nested open-branch PlusMap
  mechanism);
- rows 1, 5 — the abstract open-branch ⊕-map form is excluded from the
  sealed calculus by design, and wire-level `Apply` of certified op
  values into case-bodied lambdas currently trips the
  canonical-normal-form gates (a recorded finding; the instantiated
  content is verified through the sugar instances);
- row 21 — the full 7-qubit QS₃ simulator equality stays in the retained
  demo (component equalities and compile pins are in the harness; the
  full-width comparison exceeds the harness's unitary-simulation budget).

The `remaining` column of `coverage.tsv` states each residue precisely.

## Golden outputs

A `golden` manifest entry has a checked-in `.output` file; runs are
compared byte-for-byte and goldens are never regenerated to hide a
difference.  Every executable exits nonzero on failure.
