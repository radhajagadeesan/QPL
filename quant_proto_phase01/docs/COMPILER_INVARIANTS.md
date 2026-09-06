# Compiler invariants

**Status:** Agreed and implemented 2026-08-31. Every invariant below is
enforced; each section states its enforcement point and its tests. Work
deliberately deferred is collected under *The frame-aware round* at the end.

This document is the compiler's contract. It exists because the defect
pattern in this codebase has been *per-site* handling of properties that
should be structural: a property gets fixed at the sites someone happened to
look at, and reappears at the sites they did not. Every invariant below is
stated once, given a single enforcement point, and given a test.

**Rule for new primitives.** Any new term constructor or emitter case must
state which of these invariants apply to it and route through the named
enforcement point. A primitive that handles an invariant "in its own way" is
a defect regardless of whether its output happens to be correct.

---

## Invariant L — canonical layout: maximal connected sum frame

Every source type has **one** canonical physical layout. There is no opaque
alternative sum representation.

Define leaves of a type by flattening connected `⊕` structure only:

$$
\operatorname{leaves}(A \oplus B) = \operatorname{leaves}(A) \mathbin{+\!\!+} \operatorname{leaves}(B),
\qquad
\operatorname{leaves}(T) = [T] \quad (T \text{ not headed by } \oplus).
$$

For $m = |\operatorname{leaves}(T)|$,

$$
\operatorname{width}(T)
=
\lceil \log_2 m \rceil
+
\max_{L \in \operatorname{leaves}(T)} \operatorname{width}(L).
$$

**Flatten only a connected `Plus` tree — never across `Tensor`, `Lolli`, or
any other non-sum constructor.**

### Consequences

- `NPlusMap`, binary `PlusMap`, `case_hom`, additive associativity, and
  distributivity all agree on representation.
- Invariant W below holds globally, with no carved-out exception.
- No coercions between representation classes are needed, because there is
  only one class.
- Associativity changes logical leaf *numbering* only, never the
  representation class. Reassociated sum syntax must compile to the identical
  frame.

### Offsets for `NPlusMap`

For declared summands $A_i$, let

$$
m_i = |\operatorname{leaves}(A_i)|,
\qquad
o_i = \sum_{j<i} m_j .
$$

Local leaf tag $t$ of branch $i$ embeds as global tag $o_i + t$. **Source and
target offsets are computed independently.**

The emitter must call the canonical layout of the complete domain and
codomain. It must **not** independently allocate

$$
\lceil \log_2 n \rceil + \max_i \operatorname{width}(A_i),
$$

which was the defect: that formula produces a layout no isometry connects to
the declared type.

Worked case: `NPlusMap((Z₃, Z₅), (Id, Id))` has $3 + 5 = 8$ unit leaves, hence
$\lceil\log_2 8\rceil + 0 = 3$ wires — not $1 + 3 = 4$.

### Invalid tag words

Tag words outside the valid leaf range receive the fixed unitary complement,
**preferably identity where source and target complement coordinates agree**.

### Frame separation: `DatatypeControl` vs `NPlusMap`

Canonicalising `NPlusMap` surfaced that `control` was lowering to
`NPlusMap([A]*n, branches)`, declaring `A ⊕ … ⊕ A` while *meaning* `D ⊗ A`.
Those are isomorphic types with **different canonical layouts** whenever
`|leaves(A)|` is not a power of two — for `A = Z₃`, `D ⊗ A` is
`[tag 2 | payload 2]` while `A⊕A⊕A` flattens to 9 leaves = `[tag 4 | payload 0]`.
Same width, different embedding of the 9 valid states into 16.

The IR now separates them:

```
DatatypeControl : D ⊗ A → D ⊗ A     tensor frame  [D_tag | A payload]
NPlusMap        : ⊕ᵢ Aᵢ → ⊕ᵢ Bᵢ     canonical flat-sum frame
```

This is an internal IR separation only — source calculus, denotational rule,
and reference emitter are unchanged, and it makes no claim to fix the general
distributivity limitation. It was *required*, not merely tidy:
`phased_control` lowers to `seq0 (control D A) (PhasedCtrl D A)`, and
`PhasedCtrl` already carried the `D ⊗ A` typing, so a flat-sum `control` put
two different frames in series at equal width.

### Emission strategy: capability dispatch

Selected before any circuit mutation:

```
if has_open_branches:              require fast path, else reject
elif fast_path_supports:           fast path (exact-tag dispatch)
elif source_frame == target_frame: dense block synthesis
else:                              reject (asymmetric synthesis)
```

`fast_path_supports` holds when every summand is a single leaf, so branch *i*
owns exactly tag value *i*. Dense synthesis is never invoked with `env=None`
on an open block: an open branch compiled standalone carries its own
free-variable context wires, and splatting its top-left corner would keep
every index in range while silently miscompiling.

### Status and verification

**Enforced.** Tests: `python/tests/test_nplusmap_frame_dispatch.py` —
`NPlusMap((Z₃,Z₅),(Id,Id))` at exactly 3 wires with unitary `I₈`;
reassociated sum syntax yielding an identical frame and unitary; all four
dispatch arms; rejection before circuit mutation.

---

## Invariant W — width consistency

Stated over **frames**, not types:

$$
\texttt{n\_qubits} \;=\; \texttt{source\_frame.width} \;=\; \texttt{target\_frame.width}.
$$

For frame-free terms — which is most of them — the frame width *is* the
logical width, giving the corollary

$$
\texttt{compile}(t)\texttt{.circuit.n\_qubits} \;=\; \operatorname{width}(\texttt{type\_of}(t)[1]).
$$

**The type-level form is not global.** Terms whose physical boundary carries
spectator coordinates legitimately exceed it: `Lam`/`Apply` need function-layout
wires, and `Sum_αβ` transports the inactive premise context through each branch
(`SUM_INTRODUCTION_DESIGN.md`, (Sum-through)) so its target frame is wider than
$\operatorname{width}(A \oplus B)$. Asserting the type-level equality globally
would be wrong, and would contradict the Sum specification.

This separation already exists in the compiler: `compile()` sizes its register
with `_internal_width(term)` — *"for most terms `max(width(dom), width(cod))`;
for higher-order terms we need extra wires"* — computed compositionally. That
function is the frame width; extending it is how a new primitive declares a
wider boundary.

Free-variable context wires are a third spectator category alongside
`Lam`/`Apply` layout wires and Sum's transported context.

### Direct-boundary Lam allocation

`Lam` is **not** licensed to widen a public root. Its allocation contract:

- **The body's allocation already includes the captured context.** A free
  variable is typed as the identity on its own wires
  (`typing_/check.type_of(Var) → (ty, ty)`), so the context $\Gamma$ of an
  open lambda is inside the body's typing judgment and therefore inside
  `_internal_width(body)`. The recurrence is
  $\max(w_A + w_B,\; \texttt{body\_internal})$ — adding `ctx_w` on top
  counted $\Gamma$ twice, compounding per nesting level (the abstract
  QSwitch allocated 12 wires against its selected 8-wire carrier; the
  η-expanded switch 34 against 14), with the excess surviving only as a
  root `('fn_layout', 'residual')` port fixed at $|0\rangle$.
- **At a public (closed, env-free) `Lam` root, the register equals the
  selected semantic carrier.** A function value *is* its $w_A + w_B$ wire
  bundle; `compile()` refuses a larger allocation before the circuit is
  created, and root finalization re-checks the final frames. Unexplained
  Lam-root `fn_layout` widening is refused, never recorded.
- **$(+)$ tag and prescribed block/padding coordinates are carrier
  structure**, part of the selected coproduct carrier — they never trip the
  refusal and are not `fn_layout`. The audited coproduct representation
  shares one payload carrier: all summands embed onto the same physical
  payload wires under their mutually orthogonal tag sectors
  (`frames._canonical_codes(Plus)`), and no compiler rule allocates
  disjoint per-summand payload registers. Sparse padding consists of
  unused codes, or fixed zero positions for narrower summands, inside the
  chosen tagged representation — it adds no wires beyond
  $\lceil\log_2 n\rceil + \max_i \operatorname{width}(A_i)$. This layout
  is minimal *within the chosen explicit-tag, factor-preserving
  representation*; a globally packed encoding could sometimes use fewer
  qubits, but it would be a different boundary representation.
- Unchanged and distinct from allocator drift: `Apply`-rooted β artifacts
  keep their emission-determined function-layout workspace and in-carrier
  β residual ports (`test_nf1_partS_beta_boundary`), env sub-compiles keep
  typed context coordinates, open roots keep free-variable context, and
  the legacy `EncodeQubit`/`DecodeQubit` ancilla policy is excluded.
- **Scope of the guard.** The 2026-09 audit found no *other* current
  source of non-boundary root wires: after the Lam correction, every
  audited public artifact's register equals its selected carrier. The
  stronger constructor-independent statement — no non-$(+)$ constructor
  creates surviving root wires outside the carrier — is *satisfied* by
  all audited paths, but it is enforced mechanically only for `Lam` roots
  (plus Invariant W's corollary for spectator-free terms). A future
  constructor with its own widening rule would need its own gate; the
  Lam-root guard does not automatically cover it.

Gates: `python/tests/test_lam_direct_boundary.py`.

**Enforcement point:** an assertion at the end of top-level `compile()`.
Comparing `n_qubits` against the allocated `n` is tautological (`circ =
Circuit(n)`); the form with teeth is the **corollary** — for a term with no
spectator coordinates, `n == width(cod)`.

**Status: enforced.** Verified to fire: reintroducing the old `NPlusMap`
`_internal_width` formula produces *"frame sized at 4 qubits but the codomain
… has canonical width 3, and NPlusMap has no spectator coordinates"*. That is
exactly the bug it exists to catch, which had previously been found only by
running a demo.

---

## Invariant P — phase propagation

Every emission of a compiled subcircuit under coherent control preserves that
subcircuit's accumulated global phase, promoted to an **exact-tag relative
phase** on each tag value the branch covers.

A scalar $z\cdot I$ is unobservable standing alone and fully observable inside
a branch. Dropping it is therefore silent in isolated tests and wrong in
composition — which is why per-site handling has repeatedly failed here.

**Enforcement point.** Two functions, and commands are obtainable only
together with the phase:

```python
def _compile_branch(branch, *, env=None) -> (cmds, phase_ht):
    """Sole route from a branch TERM to controlled-emission material."""

def _discharge_branch_phase(circ, tag_qubits, tag_values, phase_ht):
    """Promote that scalar to an exact-tag relative phase at every tag value
    the branch covers. Runs even when the branch emitted no gates."""
```

A caller cannot obtain commands without also receiving `phase_ht`, which makes
dropping it a visible omission rather than an invisible default. The raw
pattern `_get_sub_cmds(compile(branch, materialize=True).circuit)` appears
**nowhere** outside `_compile_branch`; its presence anywhere else is a defect.

The emission mechanism itself is deliberately *not* unified —
`_emit_controlled_branch` (single tag qubit, anti-control, optional extra
anti-controls) and `_emit_nway_controlled` (multi-bit exact tag) remain
distinct, because forcing them together would have meant reshaping working
dispatch code. Only the part that was repeatedly got wrong is centralised.

### Defects found and fixed (audited 2026-08-31)

All six are repaired and covered by
`python/tests/test_phase_propagation.py`:

| Site | Defect |
|:---|:---|
| `Ctrl` general fallback | phase dropped |
| `PlusMap` open branch (deferred-Lam) | phase dropped |
| `PlusMap` open branch (plain) | phase dropped |
| `ExpInvolution` identity-body | `exp(iθ·I) = e^{iθ}I` discarded via early `return` commented "global phase, skipped" |
| Strategy B, width-0 branch | block overwritten with `np.eye`, discarding the scalar |
| Strategy A tag base | right summand *i* phased at `n_left + i` instead of `half + i` |

The shape of this list is the argument for the choke-point: seven sites were
hand-fixed across two earlier commits and five still dropped the phase, plus
an off-by-one. Per-site handling did not converge.

### Companion defect: Strategy A tag base

Strategy A's permutation $P$ sends right summand $i$ to tag $\mathit{half} + i$,
but phase promotion loops on $n_{\mathrm{left}} + i$. These agree only when
$n_{\mathrm{left}} = \mathit{half}$. Present in both `PlusMap` and
`PhasedPlusMap`.

Reproduced exactly and now fixed: for `PlusMap(Z₃, QBool, Id, GlobalPhase(π))`
— $n_{\mathrm{left}}=3$, $n_{\mathrm{right}}=2$, $k=3$, $\mathit{half}=4$ —
right codes live at permuted tags 4 and 5, while the old loop phased 3 (unused
filler) and 4, giving $\operatorname{diag}(1,1,1,-1,1)$. The corrected base
yields $\operatorname{diag}(1,1,1,-1,-1)$.

**Status: enforced.** All branch emission routes through `_compile_branch`;
the raw extraction pattern exists nowhere else.

Tests: for each of `omap0`, `phased_omap0`, `omapn`, `control`,
`phased_control`, `case_hom`, `Ctrl`, `ExpInvolution` — compile with and
without a `GlobalPhase` inside a branch and assert the unitary difference is
exactly the promoted tag-relative phase. Plus the asymmetric witness above,
and `Sum_{i,1}(Id, Id) ⟿ diag(i,1)` from `SUM_INTRODUCTION_DESIGN.md`.

---

## Invariant T — tag ordering

Tag registers are **big-endian** throughout: for a $k$-bit tag, index $j$
carries bit $(v \gg (k - 1 - j)) \wedge 1$ of tag value $v$.

**Enforcement point:** `_emit_exact_tag_phase` and `_emit_nway_controlled`.
No emitter may unpack tag bits inline.

**Status:** enforced as of the phased-emitter repair, which unified
`PhasedControl` (previously little-endian, `branch_idx >> bit_pos`) onto the
shared helper.

Tests: `phased_control` and `NPlusMap` produce identical diagonals for the
same index→phase map at arities 3, 4, 5.

---

## Invariant Λ — linearity

Both exported layers are strictly linear: no term-level weakening
constructor exists in `prog` or in `oterm`. Coherent branch assembly uses a
context-completion witness discharged by the *n*-ary sum-map constructor;
inactive resources are identity-through wires.

Full statement, encoding, and migration: **`docs/BRANCH_CONTEXT_LINEARITY.md`**.

**Status: enforced on both layers.** `prog`'s `weaken` and `oterm`'s `oshift`
are both removed; `o_n_plusmap` takes a `branches` vector and a total
`partition` witness. The referee's weakening witness now fails to compile
(`Error: Unbound value oshift`).

Tests: the `oshift` witness term fails to typecheck; no exported function
lifts a branch from a smaller context to a larger one; migrated demos
reproduce their committed `.output` byte-for-byte.

---

## Invariant S — one relational SeqCut authority

**Status:** implemented 2026-09-05 (checkpoint `semantic-seqcut-20260905`,
Milestones 1–4 of the proof-directed semantic SeqCut plan).

Every `Seq` cut — identity, wire-permutation and code-permutation alike —
selects ONE `CutTransport` (`_pick_cut` → `make_cut_transport` →
`check_selected`) and composes through the ONE relational join
`compile.frames.seq_cut`, differing only in physical lowering. The
composition is TRANSACTIONAL: the consumer and any Align are staged into a
scratch circuit and the parent commits only after the composition
validates. Relays (certified-identity legs, routing handoffs) keep strict
precedence; when none applies the cut composes — it never refuses a
well-formed derivation and never silently replaces a derived boundary with
a frame default.

Supporting structure, each with its own enforcement point:

* **Source links (M1).** Every factor consumed by a prepared branch
  projection reaches a derivation-issued external semantic root through
  recorded `SourcePortRef` links; classification is a lookup
  (`project_branch_root`), never a reconstruction. Gates: Part P.
* **Complete/Block from projections (M2).** Complete consumes the branch's
  per-polarity `BranchMainProjection` unchanged (`complete_projection`);
  the Block cut face is DEFINED by the antecedent branch projections
  through the module-level `_issue_block_face` shared by both open-sum
  adapters; rows only validate, bidirectionally. First-appearance
  alphabets do not exist. Gates: Part Q.
* **Relational join (M3).** `seq_cut` validates its own inputs; cut
  symbols match SEMANTICALLY through the transport (sparse and reordered
  alphabets); presenters resolve by recorded factor ids via
  `split_at_face` (multi-factor, noncontiguous); unmatched factors and
  every `(producer, consumer)` source pair survive on a `JoinRoute` that
  never degrades to `route=None` or a pretended Cartesian product; grafts
  are recorded as `SourceSubstitution`s; shared non-cut resources
  coequalize exactly once under exact lineage agreement. Composite faces
  descend from the surviving premises' own authorities. Gates: Part R.
* **General composition (M4).** A premise that recorded no face at the cut
  presents it from records only (`_whole_premise_face`: a spine presents
  its recorded terminal residual; any other route presents all factors
  jointly, against its recorded interface embedding). A completion
  certificate relates a premise's narrower recorded placement to the
  completed common cut, and face symbols embed through it. Gates: the
  Part-L positive gates (L4, L4b, L4d, L5, L6, L7, L10).

**Deferred red set:** none — the Milestone-5 beta-boundary repair below
closed the two `C` witnesses. The Python suite is fully green.

---

## Invariant B — beta boundaries inherit from artifacts

**Status:** implemented 2026-09-05 (checkpoint `beta-boundary-20260905`,
Milestone 5).

For a β-reduced `Apply(Lam(x, A, body), argument)` the external negative
boundary IS the prepared argument artifact's exact ingress boundary and
the external positive boundary IS the compiled body artifact's exact
egress boundary; the function-value/binder-layout coordinates between
them are internal and never advertised as external input padding. Nothing
is reconstructed from `type_of`, widths, offsets, canonical frames or
code geometry.

* **`BetaSubstitution`** (frames.py): the substitution cut, recorded and
  validated at the β-reduction site. It holds TWO independent typed
  records — the lambda's own domain annotation and the argument
  artifact's recorded output type — validated equal (equal widths are not
  evidence); the binder's physical schedule, which must be the leading
  slice of the argument's recorded egress (the emitters' own result-slot
  rule); the argument occurrence's cut lineage; and the owner actually
  installed for the binder, checked with `check_installed` against the
  live environment. Stored on the Artifact (`substitution`).
* **Compositional inheritance.** The occurrence's DERIVED boundary
  (origin `appcut:beta`) is built from the two premises' boundaries by
  identity; premise faces are recut and re-expressed onto the surviving
  factors; interface, placement and effective-frame records follow the
  same authorities. The effective input frame preserves the closed
  function-value layout as a residual port taken from the argument's
  recorded Par schedule (the factor's own one-state type, owner and
  origin — never a port invented from widths or fixed bits).
* **Ambient lifting.** A premise-local chart lifts into ambient space
  through the child artifact's own recorded ingress/egress wires, the
  lifted factor carrying the child's recorded occurrence — so
  finalisation keeps `appcut:beta` on the returned `Compiled` and never
  silently substitutes a frame default.
* **Lexical restoration.** The binder-id and `term_env` entries installed
  for the β parameter are restored in `try/finally`; sibling reductions
  under one binder name mint distinct installed owners.

The repair is BOUNDARY-ONLY: emitted commands, phase and pending
permutation are pinned unchanged against the pre-repair compilation.
Gates: Part S (`test_nf1_partS_beta_boundary.py`), and release-safety
witness `C` exact in both modes.

---

## Cross-cutting: identity transport

Three separate mechanisms are the same concept and must share vocabulary in
the paper and the code:

| Mechanism | Where | Inactive thing transported |
|:---|:---|:---|
| Inactive-context completion | `o_n_plusmap` partition witness | other branches' contexts |
| `(Sum-complete)` / `(Sum-through)` | `Sum_αβ` | the other premise's context |
| Invalid-tag complement | Invariant L | unused tag coordinates |

Each is "the inactive part passes through unchanged". None is weakening.

---

## Verification summary

| Invariant | Enforcement | Status |
|:---|:---|:---|
| L — canonical layout | canonical layout of whole dom/cod + capability dispatch | **enforced** |
| W — width consistency | corollary assertion at top-level `compile()` | **enforced** (verified to fire) |
| P — phase propagation | `_compile_branch` / `_discharge_branch_phase` | **enforced**, 6 defects fixed |
| T — tag ordering | shared big-endian helpers | **enforced** |
| Λ — linearity | no weakening constructor; partition witness | **enforced** on `prog` and `oterm` |

Focused suites at the time this table was first recorded:
`test_nplusmap_frame_dispatch.py`, `test_phase_propagation.py`,
`test_sum_introduction.py`, `test_case_expr_first_order_guard.py`.
Current full-surface baselines (v1.0.0, 2026-09-05): Python suite 1570
passed / 0 failed; complete `dune test` green; 32 golden demos
byte-identical plus 2 no-fixture dumps.  See `docs/VERIFICATION.md`.

---

## The frame-aware round (recorded when deferred; item 1 since completed)

Four items were deliberately deferred from the round this document first
recorded. They shared one missing piece — the canonical-frame inclusions
$j_i^\pm$ did not exist explicitly in the implementation — so each would
otherwise have required ad-hoc frame conversions, which is the defect
class this document exists to stop. Deferred items are **rejected before
emission**, never silently miscompiled.

**1. Unequal-width distributivity (§6 of `LIMITATIONS.md`) — COMPLETED.**
The boundary-frame/Align repair landed (`docs/LAYOUT_FRAME_REPAIR.md` is
now the implemented record): the naturality witness
`demos/dist_l_naturality_probe` (`A = Q`, `B = Q⊗Q`, `C = Q`), which
previously showed full-unitary fidelity 0.5, now reports fidelity 1.0,
and all four distributors compile gate-free.

**2. Asymmetric-frame block synthesis.** Dense synthesis requires the
completed source and target to share a canonical frame. Example:
`NPlusMap((Bool,Bool),(DecodeQubit,DecodeQubit))` — dom `(k=2,pw=0)`, cod
`(k=1,pw=1)`, same total width, different frames. The repair is two-sided
synthesis

$$
U_{\mathrm{sel}} = \sum_i \gamma_i\, j_i^+ U_i (j_i^-)^\dagger,
\qquad\text{equivalently}\qquad
U j_i^- = j_i^+ \gamma_i U_i,
$$

followed by the fixed canonical bijection from unused source words to unused
target words.

**3. `Sum` with open premises.** (Sum-complete) requires identity transport
of the inactive premise context, $\overline{\mathcal A}_1 = \mathsf{Par}(\mathcal A_1,
\mathsf{Wire}_{\Gamma_2})$, expressed through the same inclusions. Closed
premises are supported today.

**4. `control`'s relationship to distributivity.** `DatatypeControl` sidesteps
the `D ⊗ A ≅ ⊕ᵢ A` isomorphism by keeping the two in separate frames rather
than converting between them. Making that conversion gate-free in general is
item 1.

These are **executable-coverage restrictions, not restrictions of the source
calculus, the denotational rules, or the reference emitter.**
