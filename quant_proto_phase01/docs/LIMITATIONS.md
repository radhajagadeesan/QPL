# Known Limitations

Last updated: 2026-03-08.

---

## 1. Sum Type Arity — pytket

**Root cause:** pytket provides `Unitary1qBox` (1 qubit), `Unitary2qBox` (2 qubits), and `Unitary3qBox` (3 qubits) but no general `UnitaryNqBox`. Tag permutation unitaries and full PlusMap block-diagonal unitaries are emitted through these boxes.

**Precise pytket limitation:** `pytket.circuit` exposes `Unitary1qBox`, `Unitary2qBox`, and `Unitary3qBox` only. There is no `UnitaryNqBox` for arbitrary n. If pytket added one, limitations 1a and 1b would be eliminated.

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

**What this blocks:**

- Opaque branches on deeply left-skewed sums with 6+ summands where the
  outer PlusMap has a 5/1 or worse split.
- **Higher-order Apply/Lam chains inside PlusMap branches, when the total
  width (tag + max payload) exceeds 3.** Compiled terms whose branches
  contain `oapp`/`olam` cascades (e.g., `oapp (ovar "f") (ovar "h") ...`
  where `f` is a Granthi λ-bound function value) present as opaque
  branches to the auto-flatten pass; the fallback (Strategy A/B) then
  hits the width-3 ceiling for any sum whose input summand exceeds
  1-qubit payload. Concrete example:
  `ocaml/demos/ctrl_ho_eta_e2e.ml` — the `oplusmap` there has summand
  payload width 3 (`I ⊗ ((Q⊸Q) ⊗ Q)`) and hits this ceiling.
- Earlier phrasing "OCaml pipeline's elaborated terms are always
  decomposable" was too strong. Precise statement: **first-order
  elaborated terms are always decomposable**; higher-order branches
  (Apply chains under λ) are opaque to auto-flatten and share the
  Python-API branch limit.

**OCaml-side:** The `omap0`/`oplusmap0` smart constructors accept nested Plus summands
(e.g., `W = I ⊕ Bool` where `Bool = I⊕I`). For flat n-ary sums, prefer `omapn`/`control`.

---

## 2. ExpInvolution: ≤ 3 qubits — pytket

`ExpInvolution(θ, P)` synthesizes the unitary cos(θ)·I + i·sin(θ)·U and emits it via `Unitary1qBox`, `Unitary2qBox`, or `Unitary3qBox`.

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

> ⚠️ **The Python term IR is not a user-facing programming language.** It is a
> low-level compilation backend intended to consume already-well-formed terms
> emitted by the OCaml elaborator. Authoring terms directly at this layer
> bypasses Granthi's type discipline. Use the OCaml surface language under
> `ocaml/` as the entry point.

The Python core API does **not** enforce linearity. `typing_.check.type_of` /
`assert_well_typed` verify widths and domain/codomain matching, but do not
track variable usage. Consequently:

- Variables can be duplicated (contraction) or discarded (weakening) without
  error.
- Ill-formed terms compile to incorrect circuits silently.
- Higher-order case values whose branches are `Lam` values will typecheck and
  compile without error, but `PlusMap` sees zero top-level gates in each
  branch (the internal gates are hidden inside the Lam boundary) and lifts
  nothing — the resulting circuit contains no coherent controlled operations
  and does not implement the intended semantics of either the naïve
  higher-order case rule or the corresponding Granthi Reading. Concrete
  worked example and empirical demonstration:
  `ocaml/demos/qif_cnot_verify_e2e.ml` (header comment).

**Why this is safe by design at the OCaml layer.** The OCaml surface enforces
the **first-order sum-payload restriction** at the case sugars and the
datatype `control` combinators. A type is first-order iff it contains no
Lolli (⊸) anywhere; sum-typed payloads must be first-order. Function values
may be consumed inside a branch, but not returned as a summand of a sum.
This closes the LICS-style causal-loop pathology (e.g., "let (x' ⊗ f) =
qif x then X else id in f x'") because the corresponding sum type
`(Unit ⊗ (Q ⊸ Q)) ⊕ (Unit ⊗ (Q ⊸ Q))` fails `first_order` and is rejected.

Enforcement points:
- **OCaml smart constructors:** `case_hom0`, `case_hom`, `ocase_hom0`,
  `ocase_hom`, datatype `control`, datatype `phased_control`. These
  raise `Invalid_argument` at the call site with a first-order error
  message.
- **Python defense-in-depth:** `_assert_first_order_sum_payloads` in
  `python/src/compile/to_pytket.py` walks the compiled term and rejects
  any sum-producing subterm (`PlusMap`, `NPlusMap`, `Case`,
  `PhasedPlusMap`, `PhasedControl`) whose output type contains Lolli in
  a sum payload. Catches Python-authored terms and any OCaml
  construction that bypasses the guarded sugars.

**Workaround for higher-order-looking code:** eta-expand at the sum-payload
boundary. Where a naive term would put payload `(A ⊸ B)`, use its wire
encoding `(A ⊗ B)` — same physical circuit, no Lolli in the sum. See
`ocaml/demos/qswitch_eta_expansion_e2e.ml`.

**Regression tests:** `ocaml/test/test_first_order_sum_payloads.ml` +
`ocaml/demos/reader_qif_ocaml_attempt.ml`.

---

### 4a. OCaml — prefer case sugars over raw ⊕-Map primitives

The first-order guard is attached to the case sugars (`case_hom`,
`case_hom0`, `ocase_hom`, `ocase_hom0`) and the datatype `control` /
`phased_control` combinators — where the sum-payload type is passed as
an explicit `ty_c` argument. It is **not** attached to the raw ⊕-Map
primitives `omap0`, `omap`, `omapn`, `oplusmap0`, `oplusmap`,
`o_n_plusmap`, because the branch codomain types are GADT type
variables — erased at runtime, so the smart constructor has no
`Rep.t` value to inspect.

Consequence: a user reaching directly for the raw ⊕-Map primitives with
Lolli-carrying branches **will build a term that OCaml accepts** and
that satisfies `emit` / `emit_oterm`. The term will then fail at
`Bridge.compile` with the same first-order error, via the Python
defense. The error is caught — just one pipeline stage later than the
guarded sugars.

**Recommendation:** use the case sugars and the datatype `control`
combinators for all coherent branching. Reach for `omap0` / `oplusmap0`
directly only when you are certain the branches are first-order or you
are consciously accepting the deferred error site.

**Workaround for legitimate higher-order-looking code:** same as above —
eta-expand at the sum-payload boundary.

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

## 6. Unequal-width distributivity: composition unsupported

Composition across an unequal-width `DistL` is currently unsupported.
The standalone distributor emits zero gates and an identity `WirePerm`,
but that metadata cannot represent the tag-dependent location of a
tensor spectator in the target payload. Consequently, distributivity
naturality can fail under subsequent branch operations.

The regression witness uses `A = Q`, `B = Q ⊗ Q`, and `C = Q`. The two
sides of the distributivity-naturality square have full-unitary fidelity
0.5; they disagree on all 4 tag-zero codewords and agree on the 8
tag-one codewords. The tag-zero computation can also leave the valid
codeword subspace. Unequal-width distributors and analogous nested-width
cases should therefore not be relied upon until the layout-frame repair
is complete.

Compilation-strategy limitation (not a pytket limitation). Fix path is
documented in `docs/LAYOUT_FRAME_REPAIR.md`; a failing regression
witness lives at `ocaml/demos/dist_l_naturality_probe.{ml,output}`.

---

## 7. ~~Phased ⊕-Map / phased control: three confirmed bugs~~ — FIXED

**Status: FIXED.** Post-repair verification: `ocaml/demos/phased_map_probe_e2e.{ml,output}` — six checks, all fidelity 1.0.

**Repair summary.** All three bugs shared the phased-emitter code path
and were repaired jointly. A single big-endian helper
`_emit_exact_tag_phase(circ, tag_qubits, tag_value, θ_ht)` was added to
`python/src/compile/to_pytket.py` and used by both `PhasedPlusMap`
Strategy A and `PhasedControl`. In OCaml, `phased_control` was
reworked to compile as `(control dt a_ty branches) ; PhasedCtrl`, so
branches are honored via the ordinary `control` combinator and the
`PhasedCtrl` node remains a phase-only backend primitive. No IR
schema change.

Historical description of the three bugs (pre-fix):

**ART-3 — Nested `phased_omap0` phases only one inner tag value.**
`phased_omap0 z (A⊕B) C f g` at nested left summand `A⊕B` should apply
phase `z` to all inputs whose outer tag is `left` — semantically the
target diagonal on the 2-tag basis is `diag(z, z, 1, ?)`. The compiler
instead emits `X q[0]; X q[1]; CU1(π) q[0,1]; X q[0]; X q[1]`, which is
an anti-control-anti-control CU1 pattern that yields `diag(z, 1, 1, 1)`
— phase `z` fires only at the single innermost-innermost tag basis
state. Observed fidelity against the correct diagonal: 0.5.

Related side observation: `omap0 A B (phase z A) (id B)` compiles to
zero gates (identity), indicating branch-local phase via `phase` inside
`omap0` is also lost — same code-path family, deferred to the same
repair.

**ART-4a — `phased_control` silently ignores its branches argument.**
`phased_control desc phases A branches` compiles to bit-for-bit the
same circuit for `branches = [id; id; …]` and for `branches = [X; H;
Z; …]`. Only the `phases` array is honored; the `branches` array is
dropped. Confirmed fidelity 1.0 between the all-id and nontrivial
variants at arity 3.

**ART-4b — `phased_control` and `control` disagree on tag ordering.**
At arity 3 (2 tag qubits, 3 branches), `phased_control desc [z₁; z₂;
z₃] q [id; id; id]` and `control desc q [phase z₁ q; phase z₂ q;
phase z₃ q]` produce different unitaries (fidelity 0.25 = 1/4). The
two APIs use different array-index → tag-basis-state conventions.

All three fixed jointly in this repair pass.

---

## 8. Coherent ⊕-introduction (`Sum_αβ`) — not exposed as an artifact primitive

The formal source calculus contains a coherent ⊕-introduction rule

$$
\dfrac{\Gamma_1 \vdash W_1 : A \qquad \Gamma_2 \vdash W_2 : B}
      {\Gamma_1, \Gamma_2 \vdash [W_1 \mid W_2] : A \oplus B}
$$

that produces an `A ⊕ B` value with a freshly-allocated tag qubit
prepped to `α|0⟩ + β|1⟩`, distinct from `Map_αβ(R_1, R_2) : (A ⊕ B) ⊸
(C ⊕ D)` (which transforms an already-tagged sum). The artifact ships
the Map family end-to-end (`PlusMap`, `NPlusMap`, `PhasedPlusMap`,
`case_hom`, `datatype control`, additive iso families) but does not
expose a first-class coherent ⊕-introduction constructor.

The natural derivation `Sum = Map at source I` is not usable in the
current DSL: while `val one : [`One] ty` exists at the type level,
there is no term-level introduction for a value of type `one`
(no `unit_intro`, no `star`, no `(unit, [`One]) prog` primitive), so
the state-prep morphisms `R_1 : (unit, one ⊸ A) prog` that `omap0 one
one _ _` would need cannot be constructed. Sum is genuinely a missing
primitive, not merely absent sugar.

The repair plan — add `Sum` to the DSL by copying the `Map` emitter
with the source side blank (no input tag, no input payload; fresh
output tag ancilla prepped to `α|0⟩+β|1⟩`) — is documented in
`docs/SUM_INTRODUCTION_DESIGN.md`.

**Status:** OPEN. Implementation deferred; design agreed.

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
| 6. Unequal-width DistL composition | compilation strategy | Layout-frame repair (see `docs/LAYOUT_FRAME_REPAIR.md`) |
| ~~7. Phased ⊕-Map / phased control (ART-3, ART-4a, ART-4b)~~ | ~~phased-emitter code path~~ | **FIXED** — big-endian `_emit_exact_tag_phase` helper + OCaml `control ; PhasedCtrl` composition |
| 8. Coherent ⊕-introduction (`Sum_αβ`) — ART-5 | source-language primitive absent from surface | Design deferred; see `docs/SUM_INTRODUCTION_DESIGN.md` |

**What works without limitation:**

- Binary sums (`A ⊕ B`): all operations
- Nested sums up to 8 summands: auto-flattened to NPlusMap (preferred), with Strategy A/B fallback for opaque branches
- Tensor types: unlimited nesting depth and width
- Higher-order terms: Lam, Apply, Cup, Cap, Var, LetPair
- All gates with arbitrary control nesting via `QControlBox` (O(1) pytket boxes per ctrl level; primitive gate count is higher)
- Multi-controlled composites: `Ctrl(PlusMap(...))`, `Ctrl(ExpInvolution(...))`, etc.
- Full OCaml → Python → circuit pipeline
