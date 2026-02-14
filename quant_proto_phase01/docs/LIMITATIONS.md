# Known Limitations

This document lists all known limitations of the QPL compiler. Each entry states what fails, why, and what the workaround is (if any).

Last updated: 2026-02-14.

---

## 1. Sum Type Arity (pytket backend)

**Affected operations:** `TwistPlus`, `AssocPlus`, `PlusMap`, `PhasedPlusMap`, `PhasedControl`, and any structural operation that emits a tag permutation.

**Root cause:** pytket provides `Unitary2qBox` (2 qubits) and `Unitary3qBox` (3 qubits) but no general `UnitaryNqBox`. Tag permutations and full PlusMap unitaries are emitted through these boxes.

### 1a. Tag permutations: k ≤ 3 tag qubits (up to 8 summands)

Tag register width k = ceil(log₂(n)) where n is the number of leaf summands after flattening. `_emit_tag_perm_unitary` supports k ≤ 3.

| Summands (n) | Tag bits (k) | Supported? |
|:---:|:---:|:---:|
| 2 | 1 | ✅ no unitary needed (X gate) |
| 3–4 | 2 | ✅ `Unitary2qBox` |
| 5–8 | 3 | ✅ `Unitary3qBox` |
| 9+ | 4+ | ❌ `NotImplementedError` |

**What this blocks:** Any sum type with 9+ leaf summands. In practice this means 4+ levels of binary `⊕` nesting (e.g., `((((Q+Q)+(Q+Q))+((Q+Q)+(Q+Q)))+Q)`).

### 1b. PlusMap / PhasedPlusMap: Strategy B full unitary (w ≤ 3 total width)

When PlusMap has an **asymmetric split** (one side has more than half the codeword space), Strategy A (tag permutation sandwich with MSB control) cannot partition left/right indices. Strategy B builds the full block-diagonal unitary and emits it as a single box.

Total width w = k + payload_width. Strategy B requires w ≤ 3 (for `Unitary3qBox`).

With single-qubit payloads (pw = 1):

| Split | n | k | w | Strategy | Supported? |
|:---:|:---:|:---:|:---:|:---:|:---:|
| 2/1 | 3 | 2 | 3 | A | ✅ |
| 3/1 | 4 | 2 | 3 | B | ✅ |
| 2/2 | 4 | 2 | 3 | A | ✅ |
| 4/1 | 5 | 3 | 4 | A | ✅ |
| 3/2 | 5 | 3 | 4 | A | ✅ |
| 5/1 | 6 | 3 | 4 | B (w=4) | ❌ |
| 4/2 | 6 | 3 | 4 | A | ✅ |
| 3/3 | 6 | 3 | 4 | A | ✅ |

**What this blocks:** Deeply left-skewed sums with 6+ summands where the outer PlusMap has a 5/1 or worse split. Balanced or moderately skewed splits up to 8 summands work via Strategy A.

### 1c. PhasedPlusMap / PhasedControl: phase emission (k ≤ 2 tag qubits)

Phase application on tag subspaces uses `U1` (1 tag bit) or `CU1` (2 tag bits). For k ≥ 3 tag bits, the multi-controlled `U1` decomposition is not yet implemented.

| Tag bits (k) | Arity | Supported? |
|:---:|:---:|:---:|
| 1 | 2 | ✅ `U1` |
| 2 | 3–4 | ✅ `CU1` |
| 3+ | 5+ | ❌ `NotImplementedError` |

**What this blocks:** `PhasedPlusMap` and `PhasedControl` on sum types with 5+ summands. Plain `PlusMap` is unaffected (no phase).

---

## 2. Feedback (reserved, not compiled)

`Feedback(k, body)` exists as a term constructor but has no compilation path. Any term containing `Feedback` raises `NotImplementedError`.

**Status:** Reserved for future traced monoidal structure. No workaround.

---

## 3. Multi-Controlled Gates (Ctrl nesting)

`Ctrl(Ctrl(f))` (doubly-controlled gates) supports:
- Primitive gates: `H`, `S`, `X`, `Y`, `Z`, `Rz`, `Rx`, `Ry` → single control via hardcoded map
- `CX` → `CCX` (Toffoli)
- `TenTerm(f, g)` → recursive decomposition
- `Ctrl(inner)` → accumulates controls

All other doubly-controlled bodies (e.g., `Ctrl(PlusMap(...))`) raise `NotImplementedError`.

**Workaround:** Decompose into supported primitives before wrapping in `Ctrl`.

---

## 4. Python Linearity Checking

The Python core API does **not** enforce linearity. Variables can be duplicated (contraction) or discarded (weakening) without error. Ill-formed terms compile to **incorrect circuits** silently.

**Workaround:** Use the OCaml surface language, which enforces linearity at elaboration time (runtime check) or via the Linear GADT module (compile-time enforcement).

See `COMPILER_API_GUIDE.md` for details.

---

## Summary: What Works

For reference, here is what is fully supported with no limitations:

- **Binary sums** (`A ⊕ B`): all operations (PlusMap, PhasedPlusMap, Case, TwistPlus, structural ops)
- **Nested sums up to 4 summands** in any bracketing: all operations including asymmetric PlusMap
- **Nested sums up to 8 summands** with balanced or moderately balanced splits: PlusMap via Strategy A, structural ops via tag permutations
- **Tensor types**: unlimited nesting depth and width
- **Higher-order terms**: Lam, Apply, Cup, Cap, Var, LetPair
- **All gates**: H, S, X, Y, Z, T, Rz, Rx, Ry, CX, plus controlled variants
- **Full OCaml → Python → circuit pipeline**: elaboration, Bridge serialization, compilation
