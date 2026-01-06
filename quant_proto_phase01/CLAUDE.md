# Claude Code Instructions

## Development Workflow

- Always run `PYTHONPATH=src pytest` after code changes
- Keep `docs/` in sync with any API changes (PROGRAMMING_GUIDE.md, COMPILER_API_GUIDE.md, API_REFERENCE.md)
- Update `demos/README.md` when adding new demos
- Run demos with `PYTHONPATH=src python demos/<demo>.py`

## Project Structure

- `src/` - Python core (types, terms, compilation)
- `surface/` - OCaml surface language
- `demos/` - Executable demonstrations
- `tests/` - pytest test suite
- `docs/` - User-facing documentation

## Key Commands

```bash
# Run all tests
PYTHONPATH=src pytest

# Run a specific demo
PYTHONPATH=src python demos/qswitch_demo.py

# Build OCaml surface language
cd surface && dune build

# Run OCaml tests
cd surface && dune test
```

## Conventions

- Structural operations (twist, assoc, dist) compile to pure wire permutations
- Sum types use one-hot leaf-tag encoding
- ExpInvolution requires involutive body (P² = id)
- Use `materialize=True` in compile() when SWAP gates must be emitted
