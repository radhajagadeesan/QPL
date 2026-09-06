# Known Limitations

**This document is the sole current limitations authority** for Granthi
v1.0.0.  Other documents describe designs or history; when they mention a
restriction, this file's statement governs.

Last updated: 2026-09-06 (v1.0.1).

---

## 0. Seq composition and beta boundaries — both resolved 2026-09-05

General `Seq` composition (two derived legs, command- or phase-bearing
siblings, uncertified permuting legs) is **supported** as of checkpoint
`semantic-seqcut-20260905`: every cut kind selects one `CutTransport` and
composes through the relational `seq_cut` authority, transactionally
(`docs/COMPILER_INVARIANTS.md`, Invariant S). The former Part-L refusals
are replaced by positive semantic gates.

**Noncontiguous-beta — resolved** as of checkpoint
`beta-boundary-20260905` (`COMPILER_INVARIANTS.md`, Invariant B).
Historically the β-reduced Apply recorded only a string default, so the
root's frames fell back to the `type_of`-canonical contiguous frame
padded with function-layout spectators: for the `C` witness this claimed
ingress `(0,4,8,12)` — advertising the function value's first wire as an
external input — where the derivation makes `(0,1,8,9)`, and the
recorded frames leaked against the artifact. The boundary is now
inherited from the argument artifact's exact ingress and the body
artifact's exact egress, with the substitution cut recorded as a
validated `BetaSubstitution` and the closed function-value layout
preserved as a residual port. Witness `C` is exact in both modes, and
the Python suite carries **zero red witnesses**.

### Source higher-order specialization

The sealed `Source` interface accepts the abstract higher-order quantum
switch, and that closed abstraction compiles. A fixed `H`/`S` control built
directly with `Source.case_bool` also compiles. Applying the abstract switch
to closed `H` and `S` function values currently fails during Raw boundary
normalization with:

```text
route par^-: wire 0 is placed twice
```

This is an executable-coverage limitation, not a Source typing restriction.
The Source elaborator retains the manuscript's prescribed context-left
`G_Gamma tensor (A+B)` case expansion; it does not switch to a
coherence-equivalent mirror lowering merely to avoid the diagnostic.
`ocaml/test/test_source_semantics.ml` records the limitation and will also
accept a future successful compilation.

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
  outer PlusMap has a 5/1 or worse split, **when they reach the dense
  Strategy-B fallback**.
- Higher-order Apply/Lam chains inside PlusMap branches are opaque to
  auto-flatten, but they no longer end at this ceiling in the shipped
  path: the blockwise open-use Block machinery compiles them from their
  completed branches.  The former blocked example,
  `ocaml/demos/ctrl_ho_eta_e2e.ml` (summand payload `I ⊗ ((Q⊸Q) ⊗ Q)`,
  total width 4), **now compiles exactly**: the emitted circuit acts as
  the block-diagonal of its completed branches on the 80-dimensional
  selected boundary, with zero leakage and zero phase, in both
  materialization modes
  (`python/tests/test_release_safety.py::test_F1_ctrl_ho_compiles_and_is_exact_on_its_selected_block`).
- The width-3 ceiling remains real for constructions that genuinely fall
  through to the dense Strategy-B synthesis (no completed-Block route
  and an asymmetric split); no currently shipped demo exercises that
  fallback at width > 3.
- Earlier phrasing "OCaml pipeline's elaborated terms are always
  decomposable" was too strong. Precise statement: **first-order
  elaborated terms are always decomposable**; higher-order branches
  (Apply chains under λ) are opaque to auto-flatten and take the
  completed-Block path instead.

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

## 6. Unequal-width distributivity: RESOLVED by the boundary-frame repair

**Status: fixed.** This section previously recorded that composition
across an unequal-width `DistL` was unsupported, with the
distributivity-naturality square at full-unitary fidelity 0.5.

The witness `ocaml/demos/dist_l_naturality_probe.{ml,output}` (`A = Q`,
`B = Q ⊗ Q`, `C = Q`) now reports **fidelity 1.0**, and the regression
suite checks the square exactly (`rtol=0`) with zero leakage.

What changed: `WirePerm` plus payload-width bookkeeping was never able to
describe the tag-dependent location of a tensor spectator. Compilation
now carries explicit boundary **frames** — exact embeddings with sectors
and sector-conditioned port placements — and reconciles mismatched frames
at each splice with **Align**. A distributor whose two canonical readings
are related by its own wire permutation keeps the canonical frames; one
whose readings differ in width selects a shared narrower layout and is
gate-free, with the conversion moved to the splice.

The cost is visible and intended: splices that previously emitted nothing
now emit an alignment permutation where the frames genuinely disagree
(two `ToffoliBox`es in this witness). See `docs/LAYOUT_FRAME_REPAIR.md`
for the full design and `docs/COMPILER_INVARIANTS.md` for the invariants.

Known remaining inefficiency: adjacent Aligns are not yet cancelled, so a
chain of splices can emit an alignment and its inverse back to back
(the selector's INNER pipeline grew from 13 to 23 commands; the
complete curried selector — abstract or applied — compiles at **25
gates**, which is the optimization baseline). The applied H/S/T selector
has an **independent exact semantic oracle**: the framed action equals
the expected H/S/T dispatch at `rtol=0` with zero leakage, in both
materialization modes
(`python/tests/test_release_safety.py::test_D_curried_selector_is_h_s_t`),
alongside the Align mechanism's own exact framed-semantics and
zero-leakage assertions (`python/tests/test_align_acceptance.py`).  A
dense semantic oracle for the UNAPPLIED abstract function value (the
16-qubit curried λ itself) remains deferred with Align normalization and
is tracked in `docs/ALIGN_NORMALIZATION.md`.  The missing item is a
peephole plus one abstract-value oracle, not a soundness gap.

---

## 8. Coherent ⊕-introduction (`Sum_αβ`) — closed-premise Raw only; no sealed-Source introduction

The formal source calculus contains a coherent ⊕-introduction rule

$$
\dfrac{\Gamma_1 \vdash W_1 : A \qquad \Gamma_2 \vdash W_2 : B}
      {\Gamma_1, \Gamma_2 \vdash [W_1 \mid W_2] : A \oplus B}
$$

that produces an `A ⊕ B` value with a freshly-allocated tag qubit
prepped to `α|0⟩ + β|1⟩`, distinct from `Map_αβ(R_1, R_2) : (A ⊕ B) ⊸
(C ⊕ D)` (which transforms an already-tagged sum).

**What is implemented:** a CLOSED-PREMISE introduction exists at the
internal Raw layer and below — `Linear.sum_ α β r₁ r₂` lowers through
`Bridge.TSum` to the backend `Sum` node per
`docs/SUM_INTRODUCTION_DESIGN.md` (the Flat-Sum realization: canonical-
frame inclusions, inactive-context identity transport, exact-tag branch
coefficients, premise global phase promoted, padding fixed).

**What is deliberately NOT exposed:** the sealed `Source` calculus and
the `let%source` surface expose **no sum introduction at all** (see the
conformance fixture `test/source_conformance/reject/no_sum_introduction`),
and the Raw constructor takes **closed** premises only — there is no
open-premise (free-context) introduction anywhere.  Do not describe
Granthi as supporting general coherent ⊕-introduction at the user
surface.

**Status:** closed-premise Raw/backend introduction implemented and
tested; sealed-surface introduction intentionally absent in v1.0.0.

---

## 9. Legacy `EncodeQubit` / `DecodeQubit` — explicitly excluded

`EncodeQubit` and `DecodeQubit` (defined in
`python/src/lang/terms.py`) are Python direct-API primitives that
encode a qubit into a two-wire one-hot representation
(`Q → I + I` via CX + X, and back). This encoding is **superseded** by
the current log-tag layout, under which `Plus(one, one)` is a single
tag qubit with no payload — so the one-hot two-wire semantics does not
match the shipped representation.

These primitives are **outside the active formal interface**: they are
not exposed through the OCaml surface, not carried by the OCaml → Bridge
JSON encoding, and not reachable from the OCaml-only entry point that
the artifact prescribes for user-facing use. They remain in the Python
term IR only to keep the Python direct-API test suite
(`python/tests/test_encode_decode.py`) and the Python-side
`case_demo.py` intact.

Both class docstrings carry an explicit `LEGACY` marker pointing at
this entry. The reviewer (R1)'s ART-7 concern is addressed by explicit
exclusion (as opposed to removal or realignment); users following the
OCaml-only pipeline will never encounter them, and the Python direct
API is itself deprecated for user-facing use (see README warnings).

**Status:** CONDITIONAL / documented exclusion. No fix required beyond
this entry.

---

| Limitation | Root cause | Fix path |
|:---|:---:|:---|
| 1a. Sum ≤ 8 summands | pytket | pytket `UnitaryNqBox` |
| 1b. PlusMap Strategy B ≤ 3 width (fallback) | pytket | pytket `UnitaryNqBox` (auto-flatten preferred) |
| 2. ExpInvolution ≤ 3 qubits | pytket | pytket `UnitaryNqBox` |
| 3. Feedback not compiled | language design | Future work |
| 4. No Python linearity checking | language design | Use OCaml pipeline |
| 6. Unequal-width DistL composition | compilation strategy | Layout-frame repair (see `docs/LAYOUT_FRAME_REPAIR.md`) |
| 8. Coherent ⊕-introduction (`Sum_αβ`) — ART-5 | source-language primitive absent from surface | Design deferred; see `docs/SUM_INTRODUCTION_DESIGN.md` |
| 9. Legacy `EncodeQubit` / `DecodeQubit` — ART-7 | pre-log-tag one-hot encoding | Excluded via `LEGACY` docstring markers; not reachable from OCaml surface |

## 10. Block/Sum executable coverage

The executable Block/Sum backend uses an environment-aware direct lowering
for open branches. Its dense synthesis fallback is presently restricted to
closed blocks whose completed source and target share a canonical frame.
Blocks requiring dense synthesis across noncoincident frames are rejected
before emission. **This is an executable-coverage restriction, not a
restriction of the source calculus, denotational rule, or reference
emitter.**

Strategy is chosen by capability dispatch, before any circuit mutation:

```
if has_open_branches(block):        require fast_path_supports(block); emit_fast(block, env)
elif fast_path_supports(block):     emit_fast(block, env)
elif source_frame == target_frame:  synthesize_block(block)
else:                               reject: asymmetric Block synthesis
```

`fast_path_supports` holds when every summand is a single leaf, so branch
*i* owns exactly tag value *i* and exact-tag dispatch applies. Dense
synthesis is **never** invoked with `env=None` on an open block: compiling
an open branch standalone yields a unitary carrying its own free-variable
context wires, whose top-left corner is unrelated to the branch's action.
Splatting that would keep every index in range and silently miscompile —
which is what this dispatch exists to prevent.

Deferred to the frame-aware repair round — collected with the other three
deferred items under *The frame-aware round* in
`docs/COMPILER_INVARIANTS.md`. The repair is two-sided synthesis

$$
U_{\mathrm{sel}} = \sum_i \gamma_i\, j_i^+ U_i (j_i^-)^\dagger,
\qquad\text{equivalently}\qquad
U j_i^- = j_i^+ \gamma_i U_i,
$$

followed by the fixed canonical bijection from unused source words to
unused target words.  The branch inclusions/projections DO now exist
explicitly: the implementation records `SourcePortRef` provenance,
per-polarity `BranchMainProjection`s, completed-branch Blocks, and
`CutFace` interfaces (`python/src/compile/frames.py`), and the open-use
Block path compiles through them — this is exactly how
`ctrl_ho_eta_e2e` now compiles as blockdiag on its 80-dimensional
selected boundary with zero leakage and phase (§1b).  The remaining
restriction is precisely the **asymmetric CLOSED dense synthesis**
case: closed blocks whose completed source and target frames do not
coincide, where the currently recorded authority is still insufficient
and the term is rejected before emission rather than approximated.

Tests: `python/tests/test_nplusmap_frame_dispatch.py` — canonical frame,
reassociation invariance, open-branch routing, rejection before emission,
asymmetric-frame rejection.

---

**What the executable backend covers** (qualified — see §10 for the
Block/Sum coverage restriction):

- Binary sums (`A ⊕ B`): all operations **whose branches meet the
  Block/Sum coverage conditions in §10**
- Nested sums up to 8 summands: auto-flattened to NPlusMap (preferred), with Strategy A/B fallback for opaque branches
- Tensor types: unlimited nesting depth and width
- Higher-order terms: Lam, Apply, Cup, Cap, Var, LetPair
- All gates with arbitrary control nesting via `QControlBox` (O(1) pytket boxes per ctrl level; primitive gate count is higher)
- Multi-controlled composites: `Ctrl(PlusMap(...))`, `Ctrl(ExpInvolution(...))`, etc.
- Full OCaml → Python → circuit pipeline

Cases outside §10's coverage are **rejected before emission**, never
silently miscompiled.
