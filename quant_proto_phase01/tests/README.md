# Phase 1 Test Additions (Drop-in)

These files are intended to be *added into your existing* `tests/` directory.

They are designed to be:
- compatible with a flat, numbered test layout
- deterministic (seeded)
- robust to minor API refactors (via small helper shims)

## Additions
- `conftest.py` : shared seed fixture
- `helpers.py`  : small stable helpers (imports/introspection)
- `test_11_perm_convention_lock.py` : pins WirePerm mapping direction
- `test_23_structure_no_swaps_regression.py` : structural terms must not emit SWAPs
- `test_32_compile_determinism.py` : compilation determinism
- `test_41_materialize_equivalence_small.py` : materialize adds SWAPs only

## Run
```bash
PYTHONPATH=src pytest -q
```

Optionally override seed:
```bash
QPL_SEED=999 PYTHONPATH=src pytest -q
```
