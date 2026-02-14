# Claude Code Instructions

## Core Principles (ALWAYS FOLLOW)

1. **Well-tested code is non-negotiable.** I'd rather have too many tests than too few.
2. **No unnecessary complexity.** All enhancements must be strictly-scoped — avoid over-engineering (premature abstraction, unnecessary complexity).
3. **Never break production.** I'd rather miss a deadline than ship buggy code.

## Workflow and Interaction

- **No coding without analysis** — provide test plan first
- **Data-focused** — before/after comparisons on metrics
- **For every issue:**
  1. First identify issue (bug, smell, design problem, or risk)
  2. List concrete options with tradeoffs
  3. Get explicit approval before making changes
  4. For each option, specify: implementation effort, risk, impact on other code, maintenance burden
  5. Add test explicitly demonstrating fix

## Review Process (For Non-Trivial Changes)

**Work through iteratively, one section at a time, with at least 4 top issues in each:**

1. **Architecture Review**
   - System design and component boundaries
   - Code organization and module structure
   - Patterns and abstractions

2. **Code Quality Review**
   - Readability, testing, and debugging ease
   - Technical debt and optimization opportunities
   - Library choices and dependency management

3. **Tests Review**
   - API coverage gaps (unit, integration, e2e)
   - Error handling and validation coverage
   - Security edge-case coverage

4. **Performance Review**
   - Before/after metrics comparisons
   - Maintainability analysis

**For each stage:** Output explanation, pros/cons, and optimization recommendation. Ask for input on direction before proceeding to next stage.

## Truth Over Convenience (IMPORTANT)

**Always provide actual results from real execution, not fabricated outputs.**

- Run demos and tests; do not generate plausible-looking output by hand
- When showing compilation results, actually compile the terms
- Verify semantics with real unitary matrices, not just printed claims
- If a demo is mostly print statements, add real verification (type_of, compile, get_unitary)
- When something breaks, show the real error - don't hide failures
- The user wants truth, not results that "look right" or "make them happy"

## Development Workflow

- Always run `PYTHONPATH=src pytest` after code changes
- Run Python demos with `PYTHONPATH=src python demos/python/<demo>.py`
- Run OCaml E2E demos with `cd surface && dune exec demos/<demo>.exe`

## Documentation (IMPORTANT)

**Always keep `docs/` up to date when making changes.** Update documentation in the same commit as code changes, not as a separate afterthought.

Documentation files to maintain:
- `docs/PROGRAMMING_GUIDE.md` - User-facing guide covering all language features
- `docs/COMPILER_API_GUIDE.md` - Compiler and compilation API
- `docs/API_REFERENCE.md` - API reference
- `demos/python/README.md` - Python demo documentation
- `surface/demos/README.md` - OCaml E2E demo documentation

Update docs when:
- Adding new language features (types, terms, combinators)
- Adding new OCaml surface language features
- Changing existing APIs or behavior
- Adding new examples or demos

## Project Structure

- `src/` - Python core (types, terms, compilation)
- `surface/` - OCaml surface language
  - `surface/demos/` - OCaml E2E demos (full pipeline to circuits)
- `demos/python/` - Python executable demonstrations
- `tests/` - pytest test suite
- `docs/` - User-facing documentation

## Key Commands

```bash
# Run all tests
PYTHONPATH=src pytest

# Run a Python demo
PYTHONPATH=src python demos/python/qswitch_demo.py

# Build OCaml surface language
cd surface && dune build

# Run OCaml tests
cd surface && dune test

# Run OCaml E2E demo (full pipeline to circuits)
cd surface && dune exec demos/algorithms_e2e.exe
cd surface && dune exec demos/abstract_qswitch_e2e.exe
cd surface && dune exec demos/short_circuit_e2e.exe
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
- **Arrow type** `Arrow(A, B)` represents linear function `A ⊸ B`:
  - `width(A ⊸ B) = width(A) + width(B)` (functions are wire bundles)
  - A function value exposes argument slot + result slot as wires
- Higher-order terms use **boundary exposure/splicing**:
  - `Lam(x, dom, cod, body)` — boundary exposure (x bound to input wires)
  - `Apply(f, arg)` — boundary splicing (connect argument to function's input slot)
  - `Cup(A)` : I → A ⊗ A* (pure wiring, 0 gates)
  - `Cap(A)` : A* ⊗ A → I (pure wiring, 0 gates)
- **Full source language terms**:
  - `Var(name, ty)` — variable reference, identity on wire range from environment
  - `Pair(fst, snd)` — tensor introduction
  - `LetPair(x, y, ty_x, ty_y, pair, body)` — tensor elimination, destructures pairs
  - Compilation tracks `Env = dict[str, (start, width)]` mapping vars to wire ranges

## Linearity Checking (Platform Differences)

**OCaml Surface Language** (`surface/lib/elaborate.ml`):
- Full linearity checking at elaboration time
- `NonLinearUse` error: variable used more than once
- `UnusedVariable` error: bound variable not used
- Context splitting enforced for tensor and higher-order constructs
- Conformance tests: `surface/test/test_src_conformance.ml`

**OCaml Linear GADT Module** (`Qpl_surface.Linear`):
- Linearity enforced at **OCaml compile time** via GADTs
- Non-linear code cannot be written — it's a type error
- Context tracked in type `('g, 'a) prog`
- Conformance tests rewritten using Linear module

**Python Core API** (`src/`):
- **Type checking:** ✅ domain/codomain matching, wire bounds, structural signatures
- **Linearity checking:** ❌ NO — terms trusted to be well-formed
- Ill-formed terms compile without error but produce **incorrect circuits**
- Variables can be duplicated (contraction) or discarded (weakening) without error
- User responsibility to ensure linearity before calling `compile()`

**For linearity guarantees**, use:
1. OCaml Linear GADT module (compile-time GADT enforcement — strongest)
2. OCaml surface language + elaborate (runtime checking)
3. Generate from OCaml and bridge to Python

See `RadhaMSG/SRC_TESTS.md` for conformance test suite with platform notes.

## Compilation Pipeline: OCaml → Python → Circuit

### Two-Stage Architecture

```
OCaml Surface Language          Python Core Compiler
─────────────────────           ────────────────────
surface/lib/elaborate.ml   →    src/compile/to_pytket.py
                           │
  1. β-reduce first-order  │    Direct recursive descent:
     App(Lam(x,A,e), v)   │    - Accumulate WirePerm (no SWAPs)
     → e[v/x]             │    - Emit gates to pytket Circuit
  2. Substitute Let        │    - Offset semantics for TenTerm
     Let(x,e1,e2) → e2    │    - No intermediate representation
  3. Elaborate LetTen      │
     → Seq + wire offsets  │    Output: Compiled(circuit, perm)
  4. Transform Case        │
     → controlled gates    │
  5. Keep higher-order     │
     Lam/Apply for cup/cap │
```

### What OCaml Elaboration Does (source → core IR)

The OCaml elaborator normalizes the source language down to a first-order core IR
of structural ops + gates. **All binding, branching, and application are eliminated.**

| Surface Construct | Elaboration | What Python Receives |
|---|---|---|
| `Var x` (simple type) | Becomes `Id(ty)` | `Id` |
| `Var x` (arrow type) | Becomes `FunVar(x,a,b)` | `FunVar` |
| `Let(x, e1, e2)` | Substitution: `e2[e1/x]` | *gone* |
| `LetTen(x1,x2, A,B, e1, e2)` | `Seq(e1', e2')` + wire offset tracking | `Seq` |
| `App(Lam(x,A,e), v)` (first-order) | β-reduce: `e[v/x]` | *gone* |
| `App(f, arg)` (higher-order) | Kept as `Apply(f', arg')` | `Apply` |
| `Lam(x, A→B, body)` | Kept as `Lam(x,a,b,body')` | `Lam` |
| `Case(e, branches)` (quantum) | Anti-ctrl + ctrl gate sequences | controlled gates (`CH`, `CS`, etc.) |
| `Ctor(name, payload)` | Transparent (becomes payload) | *gone* |
| `TyArrow(A,B)` | Encoded as `A ⊗ B` (self-dual) | `Ten(A,B)` |
| `TyNamed("Bool",...)` | Expanded to underlying Plus structure | `Plus(...)` |

### Quantum Case Elaboration (Anti-Control Pattern)

Both OCaml and Python use the same pattern for case on sum types:

```
case ctrl of Left => body_L | Right => body_R

Elaborates/compiles to:
  X[tag]                    ← flip tag (0→1)
  Controlled-body_L[tag,…]  ← fires when tag=1 (original 0)
  X[tag]                    ← flip back (1→0)
  Controlled-body_R[tag,…]  ← fires when tag=1 (original 1)

Gate mapping: H→CH, S→CS, X→CX, CX→CCX, Rz→CRz, etc.
```

Tag qubit passes through unchanged. Branches operate on payload wires only.
On superposition inputs, both branches execute coherently.

### Python-Only Term Types

These exist for direct Python-API usage. The OCaml pipeline does not generate them:

- `Case(ty_left, ty_right, left, right)` — Python-side case (OCaml elaborates case away into controlled gates before bridging)
- `Cup(ty)`, `Cap(ty)` — compact-closed structure (OCaml compiles Lam/Apply directly)
- `Var(name, ty)`, `Pair(fst, snd)`, `LetPair(...)` — full source language terms
- `Feedback(k, body)` — reserved for future use (not currently compiled)
- `EncodeQubit()`, `DecodeQubit()` — qubit ↔ one-hot encoding
- `ExpSwap`, `ExpInvolution` — exponentials of structural involutions

### Key Differences: OCaml vs Python

1. **Normalization**: OCaml does β-reduction, let-elimination, case→controlled gates.
   Python does NO normalization — it receives already-normalized terms.

2. **Variables**: OCaml has `Var`, `Let`, `LetTen`, pattern matching.
   Python has `Var`, `LetPair` for direct API use; these compile via environment tracking.

3. **Types**: OCaml has `TyArrow`, `TyNamed`, `TyVar`.
   Python has `Q`, `Unit`, `Ten`, `Plus`, `Dual`, `Arrow`.

4. **Wire tracking**: OCaml tracks variable→wire via `TyEnv` during elaboration.
   Python tracks wire positions via `WirePerm` + `Env` (var→wire range) during compilation.

5. **Bridge**: OCaml serializes Core IR → JSON → Python `bridge.py` → `lang/terms.py` → `compile()`
