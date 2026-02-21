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

### 1b. PlusMap Strategy B: total width ≤ 3

When PlusMap has an asymmetric split (one side exceeds half the codeword space), Strategy A (tag permutation sandwich with MSB control) cannot partition left/right indices. Strategy B builds the full block-diagonal unitary and emits it as a single box.

Total width w = k + payload_width. Strategy B requires w ≤ 3 (for `Unitary3qBox`).

**What this blocks:** Deeply left-skewed sums with 6+ summands where the outer PlusMap has a 5/1 or worse split. Balanced or moderately skewed splits up to 8 summands work via Strategy A.

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

## 5. Iterated ctrl: Exponential Gate Blowup — compilation strategy

The `ctrl` combinator (and any iterated controlled construction) compiles by **materializing the sub-circuit at each level** and then wrapping every gate with one additional control qubit. This produces exponential gate growth:

| k | ctrl^k(X) | ctrl^k(H) | ctrl^k(S) |
|:---:|---:|---:|---:|
| 1 | 1 | 9 | 5 |
| 2 | 15 | 25 | 22 |
| 3 | 31 | 133 | 106 |
| 4 | 105 | 627 | 480 |
| 5 | 298 | — | — |

(Gate counts after `DecomposeBoxes` + `RebaseTket` to CX + single-qubit primitives.)

**Root cause:** The compilation strategy is inductive — `ctrl^k(f)` compiles `ctrl^{k-1}(f)` into N primitive gates, then individually controls each one, producing ~3–5× N gates. After k levels this gives **O(c^k)** total gates (c ≈ 3–5 depending on gate type).

**What the math says:** In the paper's semantics, each `ctrl` adds one control qubit — it is a structural operation (wiring). `ctrl^k(X)` is semantically a single C^kX gate, which has known efficient decompositions:

- **O(k²)** primitive gates without ancillae
- **O(k)** with one dirty ancilla (Barenco et al.)

**What the compiler does instead:** It treats each `ctrl` application as "control every gate in the sub-circuit", never recognizing that the iterated structure is a single multi-controlled gate.

**Possible fix:** Pattern-match on iterated `ctrl` applications (e.g., `ctrl(ctrl(...(ctrl(U))...))`) and emit a single `QControlBox` or `CnX` with the correct number of controls, then let pytket decompose optimally. This would reduce the growth from O(c^k) to O(k²) or O(k).

Not a pytket limitation — this is a compiler optimization opportunity.

---

## Summary

| Limitation | Root cause | Fix path |
|:---|:---:|:---|
| 1a. Sum ≤ 8 summands | pytket | pytket `UnitaryNqBox` |
| 1b. PlusMap Strategy B ≤ 3 width | pytket | pytket `UnitaryNqBox` |
| 2. ExpInvolution ≤ 3 qubits | pytket | pytket `UnitaryNqBox` |
| 3. Feedback not compiled | language design | Future work |
| 4. No Python linearity checking | language design | Use OCaml pipeline |
| 5. Iterated ctrl exponential blowup | compilation strategy | Pattern-match iterated ctrl → single C^kU |

**What works without limitation:**

- Binary sums (`A ⊕ B`): all operations
- Nested sums up to 8 summands (balanced splits): PlusMap, PhasedPlusMap, PhasedControl, structural ops
- Tensor types: unlimited nesting depth and width
- Higher-order terms: Lam, Apply, Cup, Cap, Var, LetPair
- All gates with arbitrary control nesting via `QControlBox` (correct but not gate-optimal for iterated ctrl, see §5)
- Multi-controlled composites: `Ctrl(PlusMap(...))`, `Ctrl(ExpInvolution(...))`, etc.
- Full OCaml → Python → circuit pipeline
