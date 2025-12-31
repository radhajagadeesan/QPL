# Phase 0+1 Summary Tests (Executable Documentation)

This folder contains **top-level narrative tests** for the Phase 0+1 spec.

These are *not* fine-grained unit tests. They are meant to read like executable documentation:

- a "cyclic-looking" / structural program still compiles to a **flat** unitary circuit
- **no SWAPs by default**
- structure is carried only as **WirePerm metadata**
- explicit SWAP materialization is debug-only and preserves non-SWAP gate order
- compilation is deterministic

## How to run

From the repo root (with `src/` on your `PYTHONPATH`):

```bash
pytest -q
```

If your project does not automatically place `src/` on `PYTHONPATH`, run:

```bash
PYTHONPATH=src pytest -q
```

## Notes

The tests use light reflection so small renames won't break them.
If a test fails with an error like "Expected one of: compile / to_pytket ...",
export one of the expected entrypoints or adjust the helper.
