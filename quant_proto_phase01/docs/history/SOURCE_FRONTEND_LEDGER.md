> **HISTORICAL RECORD — Phase-1 feasibility ledger, superseded by ocaml/counterparts/coverage.tsv**
> Retained verbatim for provenance (checkpoints source-ppx-slice-20260905 / source-frontend-datatypes-20260905).  It describes the system as
> it stood at that checkpoint, not the current system.  For current
> documentation start at [`../INDEX.md`](../INDEX.md).

# Source Frontend Feasibility Ledger (corrected, 34 rows)

Status: **superseded as the living authority by
`ocaml/counterparts/coverage.tsv`**, which the `run_counterparts` CI
test validates row-by-row.  This file remains the Phase-1 feasibility
analysis; the Phase-2 addendum at the end records what has since been
implemented.  Companion to `history/SOURCE_FRONTEND_SLICE_REPORT.md`.  One row
per file in `ocaml/demos/` (the 34-demo manifest).  Every
classification below was re-derived from the demo's actual contents and
from the sealed `source.mli` at HEAD `a052e14`, not carried over from
the design spike.

## What the verified MVP surface provides

Proven by `test/test_source_ppx_slice.ml` (positive, circuit-equal to
handwritten sealed oracles) and `test/source_frontend/` (compile-reject
with located diagnostics):

- `let%source` with annotated parameters over the sealed grammar
  (`q`, `qbool`, `tensor`, `plus`, `lolli`, datatype `M.t`, and type
  variables introduced by **visible** leading witness parameters
  `(a : 'a P.t)`);
- variables, pairs, general application (including `lolli` parameters
  applied and composed, e.g. `f (g x)`);
- `let (a, b) = split p in …`;
- `case b ~zero:… ~one_:…` over `qbool` (tag-preserving);
- builtin gates `h s t x y z cx not_bool` and certified host
  **endomorphisms** applied by name;
- `type t = C0 | … [@@source.datatype]` and
  `M.select ~target [op0; …; opN]` literal lists (no GADT vector
  constructors in user code).

The host `Op`/`Datatype` layer (compose, tensor, twist, assoc, dist,
`exp_i`, involutions, `rz`, `phase`, `seal`, `select`) is ordinary OCaml
by design — operations are certified values built outside `let%source`
and passed in or applied.  "NOW (op-level)" below means the semantic
content lives there and the `let%source` part is a thin, expressible
wrapper.

## Extensions referenced below

- **E1 — general case sugar.** Surface syntax for the *already sealed*
  tag-preserving `case`/`case0` over `('a,'b) plus` and labeled
  datatype case.  Pure frontend work; no sealed-API change.
- **E2 — additive op functor + richer involutions.** Sealed-API
  extension: `Op.plus : ('a,'b) op -> ('c,'d) op -> (('a,'c) plus,
  ('b,'d) plus) op` (P-witnessed) and branch-swap involutions (or
  conjugation of involutions by coherence ops) so `Op.exp_i` reaches
  branch permutations.  Extends the certified `Op` layer only; does not
  touch the term calculus.
- **E3 — annotation-directed host ops.** Today the surface types an
  unknown host operation as an endomorphism; a non-endomorphism op
  (e.g. `Op.dist_left`) is caught by the sealed GADT but with an
  unlocated type error.  E3 adds a `(op : ty)` application rule for
  ergonomics.  Soundness is unaffected either way.

## A structural fact the corrected ledger hinges on

The sealed `case` requires both branches to consume the **same nominal
linear context**.  A `lolli` *parameter* (a wire-bundle function
variable) used in only one branch therefore cannot appear in a sealed
case — this is by design (it is exactly the open-branch ⊕-map the
calculus refuses; see `test/source_conformance/reject/no_plusmap.ml`).
Consequences used below:

- `qswitch` (both branches use both `f` and `g`) **is** expressible —
  proven in the slice.
- Abstract `ctrl := λf.…` / curried `select_n` over *term-level*
  function parameters, each used in one branch, are **not** sealed
  Source terms.  Their certified equivalent is host-level currying over
  op values plus `Datatype.select` — host ops are not linear variables,
  so fixed-instance branches share the same (possibly empty) context.

## The ledger

Statuses: **NOW** (writable with the verified MVP), **NOW (op-level)**
(host `Op`/`Datatype` layer + thin `let%source` wrapper), **REJECT**
(the surface counterpart is a compile-reject fixture with a located
diagnostic), **EXT(…)** (needs the named extension), **HARNESS** (the
demo's subject is Raw/Core machinery or a documented backend property;
it has no surface counterpart by design and stays handwritten).
"Check" is the automated obligation of the future migrated counterpart.

| # | Demo | Status | Surface counterpart and automated check |
|---|------|--------|------------------------------------------|
| 1 | `abstract_qswitch_oterm_e2e` | NOW | `let%source qswitch` (slice case B, verbatim) at `q`; `emit` + `Bridge.eq_circ` against the demo's open-term circuits. The Raw PlusMap-with-open-branches machinery the demo also exercises remains a Raw-layer test. |
| 2 | `abstract_select_2_e2e` | NOW (op-level) | Host currying over op values + 2-label `[@@source.datatype]` selector: `fun f g -> B2.select ~target:a [f; g]`; `eq_circ` vs the demo. The *term-level* abstract branches (each lolli parameter in one branch) are not sealed Source — see the structural fact above. |
| 3 | `algorithms_e2e` | NOW | Gate pipelines are application chains; functor parameterization stays host-level over op values; `eq_circ` vs demo circuits. Re-verify branch forms row-by-row at migration (any non-qbool case → E1). |
| 4 | `ctrl_ho_eta_e2e` | HARNESS | Subject is Raw Guard-2 (target-only first-order check) certification. Companion fixed-control `ctrl(G)` for concrete gates is NOW via `case b ~zero:y ~one_:(g y)`. |
| 5 | `ctrl_lambda_e2e` | HARNESS + NOW (op-level) | Abstract `λf.ctrl f` is not a sealed Source term (open-branch ⊕-map, by design). Instantiated `ctrl(g)` for certified `g`: NOW; `eq_circ` vs the demo's Part-2 instantiations. |
| 6 | `curried_select_3_e2e` | NOW (op-level) | `fun f0 f1 f2 -> Z3.select ~target [f0; f1; f2]` + `let%source` applier; `eq_circ` vs meta `control z_3`. Term-level curried lambda stays Raw. |
| 7 | `curried_select_3_ndist_e2e` | NOW (op-level) | Same counterpart as row 6 (the n-ary dist internals are backend, invisible from the surface); `eq_circ` vs meta control. |
| 8 | `datatype_demo` | NOW | `[@@source.datatype]` + selector literal lists reproduce the declarations; the JSON dumps remain harness output. |
| 9 | `dist_l_naturality_probe` | HARNESS | Documents the LIMITATIONS §6 backend incompleteness (unequal-width dist composition). Subject is Raw structural composition; the surface never names `dist` (by design). Re-evaluated: still no surface counterpart; the sealed `Op.dist_left` exists host-side but the probe targets the backend. |
| 10 | `dist_unequal_width_probe` | HARNESS | Decisive layout probe (0-gate DistL claim about the ⊕-outermost layout). Backend property; no surface subject. Re-evaluated: unchanged. |
| 11 | `dump_abstract_qswitch` | NOW | **Corrected:** the dumped term is exactly the slice-B `qswitch`; counterpart = `let%source qswitch` + `emit`, harness keeps `Bridge.term_to_json`. |
| 12 | `dump_select_5_inst` | NOW | Proven shape: slice case C is a 5-way selector (demo instantiates H,S,T,X,Y; slice pinned H,S,T,X,Z). Counterpart trivially adjusts the literal list; harness dumps JSON. |
| 13 | `exp_swap_T3_e2e` | EXT(E2) | Branch-swap exponentials `exp(iθ·swap_12)`, `exp(iθ·swap_23)` need branch-swap involutions / `Op.plus`; the coherence pieces (`assoc_plus`, `twist_plus`) are already sealed ops. Harness keeps the reference-unitary equality. |
| 14 | `exp_twist_e2e` | NOW (op-level) + EXT(E2) | Tensor-twist exponentials: `Op.exp_i θ (involution_twist …)` — already sealed (`source_exp_twist_e2e` is the existing sealed counterpart). The `exp_i(π/4, twist_plus I I)` part shares row 13's E2 gap. |
| 15 | `n_plusmap_e2e` | NOW (op-level) | Flat n-ary `Datatype.select` reproduces `o_n_plusmap` select_n content (slice C proves arity 5); `eq_circ_partial` harness vs meta `control z_n` stays. |
| 16 | `nested_apply_e2e` | NOW | `compose_n` is `f1 (f2 (… (fn x)))` with lolli parameters — the slice-B application pattern n-deep; `eq_circ` vs demo. |
| 17 | `nested_select_e2e` | HARNESS + NOW (op-level) | Subject is the nested open-branch PlusMap *mechanism* (deferred-Lam propagation) — Raw-layer, stays. Operational content (select_4/select_8) is a flat selector: NOW (op-level). |
| 18 | `phased_map_probe_e2e` | HARNESS + NOW (op-level) | **Corrected split:** the raw NPlusMap/PhasedPlusMap ART-3/ART-4 probes stay harness (no `phased_map` in the sealed calculus — see `reject/no_phased_map.ml`). Concrete phase content is expressible now via `Op.phase`/`Op.rz` host ops. |
| 19 | `qif_cnot_verify_e2e` | NOW + REJECT | **Corrected:** Reading A (fixed-control qif) is positive: `let%source qif_cnot (p : (qbool, q) tensor) = let (b, y) = split p in case b ~zero:y ~one_:(x y)`; pin CNOT via `eq_circ`. Reading B (function-valued qif, `lolli` beneath plus) is a compile-reject with the `reject_lolli_under_plus` diagnostic family. |
| 20 | `qs2_dummy_sim_e2e` | NOW (op-level) | Controlled-SWAP construction from selector over `[Op.id …; Op.twist …]`-style certified ops + `let%source` wrapper; the permutation-action verification harness stays. Verify composition details at migration. |
| 21 | `qs3_pn_dummy_sim_e2e` | NOW (op-level) | Arity-8 `[@@source.datatype]` + selector literal list of composed coherence ops; action harness stays. Verify at migration. |
| 22 | `qswitch_eta_endoQ_e2e` | NOW | The η-expanded first-order canonical form is lam/app over lolli parameters — MVP application territory; `eq_circ` vs demo. Verify the exact η-shape at migration. |
| 23 | `qswitch_eta_expansion_e2e` | NOW (proven) | Slice case B **is** this demo's subject: one polymorphic `qswitch` with a visible `(a : 'a P.t)` witness, instantiated per payload. |
| 24 | `qswitch_instantiated_e2e` | NOW (proven) | Slice `qswitch_hs` (pinned: 4 qubits, 6 gates X·CS·CH·X·CH·CS, perm `[2,3,0,1]`, `eq_circ` = 1.0 vs oracle). |
| 25 | `reader_qif_ocaml_attempt` | REJECT + HARNESS | **Corrected split:** the reader's term (`q ⊸ q` beneath plus) as a surface program is a compile-reject fixture with a located first-order-sum diagnostic; the Raw-layer construction-and-refusal regression stays handwritten. |
| 26 | `short_circuit_e2e` | EXT(E1) | `W = I + (I + I)` dispatch needs surface sugar for the *already sealed* general case; phase marking is NOW via `Op.phase`. No sealed-API change required — E1 is frontend-only. |
| 27 | `source_datatype_e2e` | NOW (proven) | Slice case C shape (datatype + selector + wrapper). |
| 28 | `source_exp_twist_e2e` | NOW | Already a sealed host-op program (`Op.value (Op.exp_i …)`); optional `let%source` wrapper. |
| 29 | `source_fixed_control_e2e` | NOW (proven) | The MVP `case` sugar (this is also row 19's Reading A pattern). |
| 30 | `source_quickstart_e2e` | NOW (proven) | Slice case A (pinned: 4 qubits, 2 gates, perm `[2,3,0,1]`, `eq_circ` = 1.0 vs oracle). |
| 31 | `test_first_order` | NOW | Host `Op.exp_i (π/4) Op.involution_x`; wrapper optional. |
| 32 | `verify_nested_ctrl_e2e` | NOW | `ctrl^k(G)` by nesting `case` (tag-preserving; the `~zero:` branch returns the untouched inner tensor, both branches consume the same context); the reference-unitary harness (`verify_ctrl_unitary`) stays. |
| 33 | `zn_controlled_phase_e2e` | NOW | `[@@source.datatype]` Z_n + selector literal list of `Op.rz`/`Op.phase` ops; `eq_circ` vs demo. |
| 34 | `zn_group_ops_e2e` | NOW (op-level) + EXT(E2) | Shift/negation coherence chains compose from sealed `Op.twist_plus`/`Op.assoc_plus_*`; tag-controlled parts via selector. The residual `omap0` branch-wise op maps need E2 (`Op.plus`). |

## Tallies

- NOW / NOW (op-level), including the 6 slice-proven rows: **22**
  (rows 1, 2, 3, 6, 7, 8, 11, 12, 15, 16, 20, 21, 22, 23, 24, 27, 28,
  29, 30, 31, 32, 33).
- Split rows (positive counterpart plus a reject or harness residue,
  or a partial E2 residue): **6** (rows 5, 14, 17, 18, 19, 34;
  rows 19 and 25 carry the mandated Reading-A/Reading-B separation).
- HARNESS-only (Raw/Core or backend-property probes, no surface
  subject by design): **4** (rows 4, 9, 10 — plus row 17's mechanism
  half; row 25's harness half).
- EXT-only: **2** (row 13 → E2, row 26 → E1).

No row requires weakening the sealed calculus.  E1 is frontend sugar
for an existing sealed construct; E2 extends only the certified `Op`
layer; E3 is an ergonomics rule.  Migration of the 34 counterparts is
**not** performed in this slice (per instruction); each NOW row's
obligation is: write the counterpart, `emit`, compile, and
`Bridge.eq_circ` against the existing demo's construction, with pinned
facts where the demo pins them.

## Phase-2 addendum (implemented; coverage.tsv is the authority)

- **E1 and E3 are implemented and tested** (`case s ~left_:/~right_:`
  over first-order sums; `((op : (dom, cod) lolli) argument)` for
  certified non-endomorphisms), with located rejection fixtures.
- **The datatype operation/elimination layer is implemented** — the
  narrow design that replaced this ledger's broader E2 sketch (no
  `Op.plus`, no branch-swap involution grammar over raw sums):
  `Datatype.Make(...)()` now exposes `cases`/`cases0` (exhaustive
  tag-preserving datatype case, reached by ordinary `match` syntax in
  `let%source`), `permute`, and `involution_permute` (certified label
  permutations with constructor-name PPX sugar, forward convention,
  padding states fixed).  See
  `docs/DATATYPE_ELABORATION.md` for the shipped design and
  the canonical LEFT-association decision (fixed by the clean calculus
  in `narymonoidal.tex`/`datatypes-new.tex` and pinned structurally by
  `test_source_datatype_ops`).
- Consequently rows **13, 14, 18, 26, and 34** — the E2/blocked entries
  above — are **migrated**: branch-swap exponentials via datatype
  involutions tensored with payload identities (row 13), the plus-swap
  exponential via the two-label datatype involution (row 14), per-label
  phased dispatch derived from `Op.phase` composed into `select`
  branches (row 18), the concrete W3 = Qudit(3) toggle / ctrl_W /
  and_sc programs (row 26 — not the paper's general `Aux + QBool` with
  nontrivial `Aux`), and Z_n shifts/negations/additions for
  n ∈ {3, 4, 5, 8, 11} (row 34).
- All 34 rows now carry an executed concise Source counterpart; the
  remaining split residues are backend-inspection or normalization
  matters (rows 4, 5, 9, 10, 17, 21 notes in coverage.tsv), none of
  them datatype-related.
