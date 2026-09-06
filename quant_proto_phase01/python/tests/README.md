# Python backend regression tests

The regression suite for the internal Python compiler backend.  Run from
`quant_proto_phase01/`:

```bash
PYTHONPATH=python/src pytest python/tests -q
```

Expected: all tests pass (v1.0.0 baseline: 1570 passed / 0 failed; the
suite grows over time).

The suite covers the term IR, typing/width checks, structural lowering
(twist/assoc/dist as gate-free wire permutations), sum encodings and the
blockwise open-sum machinery, the relational SeqCut composition
authority, beta-boundary inheritance, exponentials, datatype dispatch,
tag permutations, and the golden fixtures produced by the OCaml bridge.

These tests exercise **internal** layers.  Language-level behaviour is
tested from the OCaml side (`ocaml/test/`, `ocaml/counterparts/`); see
`docs/VERIFICATION.md` for the complete verification surface.
