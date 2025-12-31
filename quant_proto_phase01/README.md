# Quantum Proto (Phases 0–1)

Pipeline:

Source AST  ==>  (permutation metadata)  ==>  pytket Circuit

## Install

```bash
pip install -U pip
pip install pytest pytket
```

## Run tests

```bash
PYTHONPATH=src pytest -q
```

Notes:
- Structural isomorphisms compile to permutations carried as metadata.
- `materialize=True` appends SWAPs to realize the final permutation for debugging.
- Distributivity compilation is intentionally deferred (needs a sum-aware layout model).
