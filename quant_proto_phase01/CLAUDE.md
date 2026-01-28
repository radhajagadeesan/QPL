# Claude Code Instructions

## Development Workflow

- Always run `PYTHONPATH=src pytest` after code changes
- Run demos with `PYTHONPATH=src python demos/<demo>.py`

## Documentation (IMPORTANT)

**Always keep `docs/` up to date when making changes.** Update documentation in the same commit as code changes, not as a separate afterthought.

Documentation files to maintain:
- `docs/PROGRAMMING_GUIDE.md` - User-facing guide covering all language features
- `docs/COMPILER_API_GUIDE.md` - Compiler and compilation API
- `docs/API_REFERENCE.md` - API reference
- `demos/README.md` - Update when adding new demos

Update docs when:
- Adding new language features (types, terms, combinators)
- Adding new OCaml surface language features
- Changing existing APIs or behavior
- Adding new examples or demos

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

- Structural operations (twist, assoc, dist) compile to symbolic tag permutations + wire permutations
- Sum types use **Option B: flat log-sized tag register + shared payload** encoding
  - `width(A ⊕ B) = ceil(log2(n)) + max(width(Aᵢ))` where n = number of leaf summands
  - TwistPlus emits X gate (tag flip), tracked symbolically in TaggedPerm
  - AssocPlus is identity (flattened layout)
  - DistL is identity; DistR moves tag bits to front
- ExpInvolution requires involutive body (P² = id)
- Use `materialize=True` in compile() when SWAP gates must be emitted
- Higher-order terms use **cup/cap wiring** (no GOI):
  - `A ⊸ B ≡ A* ⊗ B ≡ A ⊗ B` (self-dual types)
  - `Cup(A)` : I → A ⊗ A* (pure wiring, 0 gates)
  - `Cap(A)` : A* ⊗ A → I (pure wiring, 0 gates)
  - `Dual(A)` type tracks polarity; `width(Dual(A)) = width(A)`
  - `compile_higher_order()` is deprecated; use `compile()` directly
