# Known Limitations

Last updated: 2026-02-20.

---

## 1. Sum Type Arity — pytket

**Root cause:** pytket provides `Unitary2qBox` (2 qubits) and `Unitary3qBox` (3 qubits) but no general `UnitaryNqBox`. Tag permutation unitaries and full PlusMap block-diagonal unitaries are emitted through these boxes.

**Precise pytket limitation:** `pytket.circuit` exposes `Unitary2qBox` and `Unitary3qBox` only. There is no `UnitaryNqBox` for arbitrary n. If pytket added one, limitations 1a and 1b would be eliminated.

### 1a. Tag permutations: ≤ 8 summands (k ≤ 3 tag qubits)

Tag register width k = ceil(log₂(n)) where n is the number of leaf summands after flattening. `_emit_tag_perm_unitary` supports k ≤ 3.

| Summands (n) | Tag bits (k) | Supported? |
|:---:|:---:|:---:|
| 2 | 1 | ✅ X gate (no unitary box needed) |
| 3–4 | 2 | ✅ `Unitary2qBox` |
| 5–8 | 3 | ✅ `Unitary3qBox` |
| 9+ | 4+ | ❌ `NotImplementedError` |

**Affected operations:** `TwistPlus`, `AssocPlus`, `PlusMap`, `PhasedPlusMap`, and any structural operation that emits a tag permutation on sums with 9+ leaf summands.

### 1b. PlusMap Strategy B: total width ≤ 3 (fallback only)

The compiler now **auto-flattens** nested PlusMap trees to NPlusMap when branches are
decomposable (recursive PlusMap/Case trees, Id on Plus types). Auto-flatten is the
preferred compilation path and handles most cases from the OCaml pipeline.

When auto-flatten fails (opaque branches that cannot be decomposed into per-leaf
morphisms), the compiler falls back to Strategy A or B:

- **Strategy A** (symmetric splits): tag permutation sandwich with MSB control
- **Strategy B** (asymmetric splits): full block-diagonal unitary via `Unitary3qBox`

Strategy B requires total width w = k + payload_width ≤ 3.

**What this blocks:** Opaque branches on deeply left-skewed sums with 6+ summands where the outer PlusMap has a 5/1 or worse split. This only affects direct Python API usage with opaque composed branches — the OCaml pipeline's elaborated terms are always decomposable.

**OCaml-side:** The `omap0`/`oplusmap0` smart constructors accept nested Plus summands
(e.g., `W = I ⊕ Bool` where `Bool = I⊕I`). For flat n-ary sums, prefer `omapn`/`control`.

---

## 2. ExpInvolution: ≤ 3 qubits — pytket

`ExpInvolution(θ, P)` synthesizes the unitary cos(θ)·I + i·sin(θ)·U and emits it via `Unitary2qBox` or `Unitary3qBox`.

| Body width | Supported? |
|:---:|:---:|
| 1 qubit | ✅ `Unitary1qBox` |
| 2 qubits | ✅ `Unitary2qBox` |
| 3 qubits | ✅ `Unitary3qBox` |
| 4+ qubits | ❌ `NotImplementedError` |

**Same root cause as §1:** pytket lacks `UnitaryNqBox`. If pytket added one, this limitation would be eliminated.

---

## 3. Feedback — language design

`Feedback(k, body)` exists as a term constructor but has no compilation path. Any term containing `Feedback` raises `NotImplementedError`.

Reserved for future traced monoidal structure. Not a pytket limitation.

---

## 4. Python Linearity Checking — language design

The Python core API does **not** enforce linearity. Variables can be duplicated (contraction) or discarded (weakening) without error. Ill-formed terms compile to incorrect circuits silently.

**Workaround:** Use the OCaml surface language, which enforces linearity at elaboration time (runtime check) or via the Linear GADT module (compile-time enforcement).

Not a pytket limitation.

---

## 5. ~~Iterated ctrl: Exponential Gate Blowup~~ — FIXED

**Status: FIXED.** The exponential gate blowup from iterated `ctrl` has been eliminated.

The compiler previously used `DecomposeBoxes()` to blow up compound gates (QControlBox, UnitaryNqBox) into primitives before re-controlling each one. This caused exponential growth: at level k, the compound gate from level k-1 was decomposed into many primitives, each wrapped with a new control.

**Fix:** Removed `DecomposeBoxes`. `QControlBox(op, n)` wraps ANY op — including other QControlBoxes — so nested control is expressed directly without decomposition.

**Note on gate counts:** The gate counts reported by `circuit.n_gates` are **pytket box counts** — each `QControlBox` counts as 1 regardless of how many primitive gates it decomposes into. The table below shows pytket box counts, not primitive gate counts:

| k | ctrl^k(X) | ctrl^k(H) |
|:---:|---:|---:|
| 1 | 1 (CX) | 1 (CH) |
| 2 | 1 (CCX) | 1 (QControlBox) |
| 3 | 1 (CnX) | 1 (QControlBox) |
| 4 | 1 (CnX) | 1 (QControlBox) |

`ctrl` controls the **wires** of A, not individual gates. For `ctrl(f)` where `f : A ⊸ A`, the tag qubit gates the entire A wire bundle. pytket handles nested QControlBoxes correctly when computing unitaries.

---

## Summary

| Limitation | Root cause | Fix path |
|:---|:---:|:---|
| 1a. Sum ≤ 8 summands | pytket | pytket `UnitaryNqBox` |
| 1b. PlusMap Strategy B ≤ 3 width (fallback) | pytket | pytket `UnitaryNqBox` (auto-flatten preferred) |
| 2. ExpInvolution ≤ 3 qubits | pytket | pytket `UnitaryNqBox` |
| 3. Feedback not compiled | language design | Future work |
| 4. No Python linearity checking | language design | Use OCaml pipeline |
| ~~5. Iterated ctrl exponential blowup~~ | ~~compilation strategy~~ | **FIXED** — removed DecomposeBoxes, nested QControlBox |

**What works without limitation:**

- Binary sums (`A ⊕ B`): all operations
- Nested sums up to 8 summands: auto-flattened to NPlusMap (preferred), with Strategy A/B fallback for opaque branches
- Tensor types: unlimited nesting depth and width
- Higher-order terms: Lam, Apply, Cup, Cap, Var, LetPair
- All gates with arbitrary control nesting via `QControlBox` (O(1) pytket boxes per ctrl level; primitive gate count is higher)
- Multi-controlled composites: `Ctrl(PlusMap(...))`, `Ctrl(ExpInvolution(...))`, etc.
- Full OCaml → Python → circuit pipeline
