# Granthi Python Layer

> ⚠️ **This is not the user-facing front-end.** If you want to write Granthi
> programs, use the OCaml surface language under
> [`../ocaml/`](../ocaml/). See the [top-level README](../../README.md) and `docs/PROGRAMMING_GUIDE.md`.

## What this layer is

The Python code here is Granthi's **low-level compilation backend**:

- `src/lang/terms.py` — the term IR that the OCaml elaborator produces and the
  compiler consumes.
- `src/lang/types.py` — the type representation.
- `src/compile/to_pytket.py` — the compiler from term IR to pytket circuits.
- `src/typing_/check.py` — width and domain/codomain checking.
- `tests/` — regression tests for the backend.
- `demos/` — legacy Python demonstrations (kept for backend testing; not the
  recommended way to write programs).

## What this layer is not

It is **not** a user-facing programming language:

- **No linearity checking.** Variables can be duplicated (contraction) or
  discarded (weakening) without error. Ill-formed terms compile to incorrect
  circuits silently.
- **No coherence guarantees for higher-order case values.** Terms that construct
  a coherent superposition of function values (e.g., a case whose branches are
  `Lam` values) will typecheck under the width-only `assert_well_typed` and
  compile to circuits that do not implement any well-defined semantics — the
  branch gates hide inside the Lam boundary and are silently dropped by
  `PlusMap`.

See [`../docs/LIMITATIONS.md`](../docs/LIMITATIONS.md#4-python-linearity-checking--language-design)
for details.

## When to touch code here

- You are running the backend test suite (`PYTHONPATH=src pytest tests`).
- You are extending the compiler, the term IR, or the pytket lowering.
- You are debugging output produced by the OCaml → Bridge → Python pipeline.

For everything else — including writing new demos, new terms, and new tests
of language behavior — start in [`../ocaml/`](../ocaml/).
