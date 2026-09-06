# Verification and Reproduction

How to reproduce Granthi's verification results (v1.0.x) from a clean
checkout, and what to expect.  Counts below are the recorded baseline at
the v1.0.0 release (2026-09-05); suites grow over time, so treat them as
"at least" rather than frozen.

## Setup (order matters)

The OCaml suite invokes the Python backend, so install Python first:

```bash
cd quant_proto_phase01
pip install -r requirements.txt        # numpy, pytest, pytket

# OCaml 4.14 switch, then:
opam install dune ppxlib               # ppxlib >= 0.37 (frontend PPX)
```

## The verification surface

All commands from `quant_proto_phase01/` unless noted.

**1. Python backend suite** — expected: all pass (baseline 1570 passed, 0 failed):

```bash
PYTHONPATH=python/src pytest python/tests -q
```

**2. Complete OCaml build and test suite** — expected: exit 0:

```bash
cd ocaml
dune build
dune test
```

`dune test` includes, among the unit/property suites:

- **Frontend conformance** (`test/source_frontend/`): every valid
  fixture compiles and every reject fixture fails with its exact located
  diagnostic — baseline 1 compile-pass + 23 compile-fail fixtures.
- **Semantic frontend tests** (`test_source_ppx_slice`,
  `test_source_ppx_ext`): concise programs circuit-equal (fidelity 1.0)
  to handwritten sealed oracles, with pinned wire/gate/permutation
  facts.
- **Datatype invariants** (`test_source_datatype_ops`): forward
  permutation convention, structural left-association pins, direct
  padding fixes at arities 5 and 11, involution certification, nominal
  separation.
- **Counterpart coverage** (`counterparts/run_counterparts`): the
  34-row ledger — baseline 112 checks, 0 failed, plus ledger
  cross-validation and the anti-vacuity scan.
- **Documentation examples** (`examples/doc_examples`): every program in
  the Programming Guide compiles end-to-end.

**3. The demo battery** — expected: 32 golden demos byte-identical to
their committed `.output` files, plus 2 no-fixture dumps
(`dump_abstract_qswitch`, `dump_select_5_inst`) exiting 0:

```bash
cd .. && ./artifact/reproduce.sh
```

`reproduce.sh` exits nonzero on any golden difference, any runtime
error, **or any missing golden fixture** outside the two documented
dumps.

## What the checks establish

- The PPX frontend is a *semantic* component: the sealed calculus
  re-proves typing/linearity of everything it emits, and the oracle
  equalities prove it preserved meaning (a well-typed-but-wrong
  expansion would fail circuit equality).
- All four distributivity constructors compile gate-free, and the tested
  naturality witnesses (including the unequal-width probe
  `dist_l_naturality_probe`) pass at fidelity 1.0.
- Sequential composition is checked by the relational SeqCut authority;
  beta-reduced applications inherit exact boundaries from their argument
  artifacts.  Compositions the authority cannot certify are **refused**,
  never silently miscompiled.

## Honest notes

- Never regenerate a `.output` file to make a diff pass; a golden
  difference is a finding to report.
- `docs/LIMITATIONS.md` is the sole current limitations authority.
- Align normalization (circuit-size optimization at splices) is
  deliberately deferred post-v1.0.0 and is not a correctness item; see
  `docs/ALIGN_NORMALIZATION.md`.
