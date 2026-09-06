# Strict linearity for coherent branch contexts

**Status: implemented 2026-08-31.** Decision record for the linearity strand;
normative content lives in `docs/COMPILER_INVARIANTS.md` (Invariant Λ).

Shipped: `oshift`/`OShift` removed at all six library sites; `partition` and
`branches` GADTs added; `o_n_plusmap` rewritten to take them; `context_rep`
computes the conclusion context via `partition_rep` (with `| BNil, _ -> .`,
so the compiler *proves* zero branches impossible); 5 demo sites and 3 doc
files migrated. The referee's weakening witness now fails to compile with
`Error: Unbound value oshift`, and all 27 demo `.output` files came back
byte-identical — emission never saw the padding, so the migration is
provably semantics-preserving.

## The defect

`linear.mli` exports

```ocaml
val oshift : 'b ty -> ('g, 'a) oterm -> ('b * 'g, 'a) oterm
```

which adds an unused variable to a context. It admits term-level weakening in
the exported `oterm` API:

```ocaml
olam "x" q (q -@ q)
  (olam "y" q q
    (oshift q (ovar "x" q)))        (* λx.λy.x — y discarded *)
```

The `prog` GADT is strictly linear (its `weaken` was removed), but the
`oterm` surface is not, so an unqualified "exact linearity" claim over the
exported API is false.

The defect is worse than an unused escape hatch. All four `o_n_plusmap`
demos are **built on it**:

```ocaml
let pad b = oshift qq_ty (oshift qq_ty b) in
let branches = [| pad (apply_f_branch "f0");
                  pad (apply_f_branch "f1");
                  pad (apply_f_branch "f2") |] in
o_n_plusmap summand_tys ia_ty branches
```

`apply_f_branch "fi"` has a genuine **one-slot** context holding `fi`;
`pad` inflates it to three so the array typechecks. Slot 2 therefore means
`f0` in branch 0 and `f1` in branch 1 — the positional context type is
decorative, and the demo's own comment says so: *"Variable lookup at Bridge
level is by name, so each branch's named var binds correctly."*

`context_rep` silently depends on the fiction too:

```ocaml
| ONPlusMap (_, _, branches) -> context_rep branches.(0)     (* linear.ml:621 *)
```

This is only correct because padding inflates branch 0 to the whole Γ.

## The decision

Source terms remain **strictly linear**: no weakening constructor exists.
Identity completion of inactive resources belongs to the semantics and the
compiler, not to the source syntax. Two rules, no third:

**1. Partitioned alternatives.** Branches are typed under their own
branch-local contexts. A total, disjoint partition witness shows those
contexts exactly cover the conclusion context — no omitted resources.
Lowering identity-completes the inactive contexts internally.

**2. Shared context.** The same context is required in every alternative and
each branch uses it linearly; exactly one alternative executes:

$$
\frac{\Gamma, x{:}A \vdash M : C \qquad \Gamma, y{:}B \vdash N : C}
     {\Gamma, z{:}A \oplus B \vdash \mathsf{case}\ z\ \mathsf{of}\ x \mapsto M \mid y \mapsto N : C}
$$

This is neither contraction nor weakening: every possible execution uses each
resource exactly once.

**No third rule for mixed contexts** — the mixed case is derivable from these
two. See the completeness argument below.

Terminology: this is **inactive-context completion**, not weakening.

## Completeness: the mixed case is derivable

The situation where some resources are branch-local and others are shared does
arise, but it requires no third primitive. Suppose

$$
\Gamma_L, \Delta, x{:}A \vdash M_L : C,
\qquad
\Gamma_R, \Delta, y{:}B \vdash M_R : D,
$$

with $\Gamma_L, \Gamma_R$ branch-local and $\Delta$ shared. Package $\Delta$ as
$G_\Delta$ and route it through the sum by distributivity:

$$
G_\Delta \otimes (A \oplus B)
\;\xrightarrow{\ \mathrm{dist}_r\ }\;
(G_\Delta \otimes A) \oplus (G_\Delta \otimes B).
$$

The branches now abstract over the routed $G_\Delta$, leaving only
branch-local contexts free:

$$
\Gamma_L \vdash \widehat{M}_L : G_\Delta \otimes A \multimap C,
\qquad
\Gamma_R \vdash \widehat{M}_R : G_\Delta \otimes B \multimap D,
$$

so the strictly partitioned open plus-map applies directly:

$$
\Gamma_L, \Gamma_R \vdash
\widehat{M}_L \oplus \widehat{M}_R :
(G_\Delta \otimes A) \oplus (G_\Delta \otimes B) \multimap C \oplus D.
$$

For the homogeneous tag-preserving case, append `undist`:

$$
\mathrm{undist} \circ (\widehat{M}_L \oplus \widehat{M}_R) \circ \mathrm{dist}_r .
$$

Consequences:

- $\Delta$ is **not** a free context duplicated across the plus-map premises;
  it is a linear *input* routed through the sum payload.
- $\Gamma_L, \Gamma_R$ are handled by the ordinary strict context partition.
- No weakening, contraction, or mixed-context primitive is required.
- `ocase_hom` is precisely the closed-branch / shared-context specialization
  of this factorization.

**Design rule for $\Delta$ membership.** Each branch must consume the routed
$G_\Delta$ linearly. If a resource is not needed in *every* alternative, it
does not belong in $\Delta$ — it belongs in a branch-local partition. This is
what keeps the shared context honest and prevents $\Delta$ from becoming a
back-door for unused resources.

**Constraint on future work.** A mixed-context *convenience combinator* may
later be added, but it must desugar to `dist_r` ; partitioned-⊕-map ;
`undist`. It must **not** be introduced as a new typing rule or AST
constructor — doing so would reintroduce exactly the ambiguity this design
removes.

The two fundamental mechanisms are therefore complete:

1. strict *n*-way partition for branch-local resources;
2. shared resources routed explicitly through the sum payload by
   distributivity.

## Witness encoding

A total *n*-way partition is an iterated binary split, reusing the existing
`split` witness verbatim (the shipped form lives in `ocaml/lib/linear.ml`;
its use is exercised by the `o_n_plusmap` demos and tests):

```ocaml
(* existing, unchanged *)
type (_, _, _) split =
  | SNil   : (unit, unit, unit) split
  | SLeft  : ('g1, 'g2, 'g) split -> ('a * 'g1, 'g2, 'a * 'g) split
  | SRight : ('g1, 'g2, 'g) split -> ('g1, 'a * 'g2, 'a * 'g) split

(* new: total, disjoint cover — every variable has exactly one owner *)
type (_, _) partition =
  | PLast : ('g, 'g * unit) partition
  | PCons : ('g1, 'g2, 'g) split * ('g2, 'gs) partition
         -> ('g, 'g1 * 'gs) partition

(* new: heterogeneous branch vector; each branch carries its summand type,
   so arity agreement is structural rather than a runtime check *)
type (_, _) branches =
  | BNil  : (unit, 'c) branches
  | BCons : 'a ty * ('g, 'c) oterm * ('gs, 'c) branches
         -> ('g * 'gs, 'c) branches
```

`PLast` forces the final branch's context to be *exactly* the remainder, so
nothing can be left over; each `PCons` step consumes a `split`, which has no
drop constructor. The `'parts` index of `partition` and of `branches` are the
same right-nested tuple, so the two travel together and cannot disagree.

New signature (the summand-type array disappears into `branches`):

```ocaml
val o_n_plusmap :
  'c ty ->
  ('parts, 'c) branches ->
  ('whole, 'parts) partition ->
  ('whole, [`Lolli of 'sum_in * 'sum_out]) oterm
```

`context_rep` for `ONPlusMap` is then a real computation rather than a peek at
branch 0 — a fold over the branches and the witness, mirroring the existing
`split_rep`. OCaml accepts `| BNil, _ -> .` in that fold, i.e. it *proves* the
zero-branch case impossible.

### What this closes, structurally

| Failure mode | How it is excluded |
|:---|:---|
| Resource padded in every branch, consumed nowhere | Unrepresentable — no drop constructor; `PLast` forces exact remainder |
| Branch declared to own a resource but ignoring it | Impossible — branch is linear at its own context, no padding available |
| Zero branches | Compiler-refuted (`BNil, _ -> .`) |
| Summand-type / branch-count mismatch | Structural — summand type carried in `BCons` |
| Padded branch smuggled out as an ordinary term | Nothing to smuggle — there is no padding term; the witness is not a term and yields no `oterm` |

## Worked migration: `select_3`

Before:

```ocaml
let pad b = oshift qq_ty (oshift qq_ty b) in
let branches = [| pad (apply_f_branch "f0");
                  pad (apply_f_branch "f1");
                  pad (apply_f_branch "f2") |] in
o_n_plusmap summand_tys ia_ty branches
```

After — branches at their genuine one-slot contexts, ownership in the witness:

```ocaml
let branches =
  BCons (ia_ty, apply_f_branch "f0",
  BCons (ia_ty, apply_f_branch "f1",
  BCons (ia_ty, apply_f_branch "f2", BNil))) in

let part3 =                         (* Γ = f0 * (f1 * (f2 * unit)) *)
  PCons (SLeft (SRight (SRight SNil)),      (* f0 → branch 0 *)
  PCons (SLeft (SRight SNil),               (* f1 → branch 1 *)
  PLast))                                   (* f2 → branch 2, exactly *)
in
o_n_plusmap ia_ty branches part3
```

The `pad` lines disappear; nothing else in the demo changes.

## Migration inventory

**Library — 6 `OShift` sites, all deleted:**

| Location | What |
|:---|:---|
| `linear.mli:409-410` | `val oshift` + doc comment |
| `linear.ml:508` | `OShift` GADT constructor |
| `linear.ml:554` | `let oshift ty inner = OShift (ty, inner)` |
| `linear.ml:614` | `context_rep` case |
| `linear.ml:659` | `emit_oterm` case |
| `linear.ml:670` | `is_apply_target` case |

plus **add** `partition` / `branches`, and **rewrite** `o_n_plusmap` and its
`context_rep` case.

**Demos — 5 sites / 4 files:** `n_plusmap_e2e.ml` (×2, select_3 and select_5),
`curried_select_3_e2e.ml`, `curried_select_3_ndist_e2e.ml`,
`dump_select_5_inst.ml`.

**Docs — 4 occurrences / 3 files:** `API_REFERENCE.md:192`,
`PROGRAMMING_GUIDE.md:387`, `OCAML_DSL.md:354,360`. All three currently
*recommend* the padding idiom; `OCAML_DSL.md:360` reproduces it as a worked
example. Each needs two edits, not one:

1. Replace the `oshift` padding recommendation with the partition-witness
   form (worked `select_3` above).
2. Add the **shared-resource recipe** — the user-facing register of the
   completeness argument: *"if a resource is needed by every branch, do not
   put it in the branch context; route it through the sum payload with
   `dist_r`, and recover the tag-preserving form with `undist`."* The
   metatheory stays in this note; the guides carry only the pattern and
   the membership rule (a resource not needed in every alternative belongs
   in a branch-local partition, not in Δ).

**Tests — none.** `test/` contains no `oshift`.

## Verified unchanged

Emission drops the padding entirely and binds variables by name:

```ocaml
| OShift (_, inner) -> emit_oterm inner        (* linear.ml:659 *)
| OHere (name, ty)  -> Bridge.TVar (name, ty)
```

so the Bridge term for `pad (apply_f_branch "f0")` is byte-identical to that
for `apply_f_branch "f0"`. Therefore: **emitted JSON unchanged ⇒ circuits
unchanged ⇒ every committed `.output` must come back byte-identical.**

Consequently this phase requires **no Bridge and no Python change**, and the
five demos' `.output` files serve as a free end-to-end regression check.
Binary examples using `OPlusMap`'s existing `split` witness are unaffected.

## Regression checks

1. The `oshift` witness term no longer typechecks (compile-fail test).
2. No exported function converts a branch under a smaller context into an
   ordinary `oterm` under a larger one.
3. A resource padded in every branch is rejected — by construction,
   demonstrated as an unrepresentable-term note rather than a runtime test.
4. Existing *n*=2 and *n*=3 coherent-branch demos still pass.
5. Matrix test confirming inactive resources undergo identity transport.
6. All five migrated demos reproduce their committed `.output` byte-for-byte.

## Wording for the paper and artifact

> The exported context-indexed source API admits no term-level weakening.
> Coherent branch assembly instead takes a context-completion witness,
> supplied at and discharged by the *n*-ary sum-map constructor, which
> interprets inactive resources as identity-through wires. Every conclusion
> resource is therefore consumed in an active branch or transported unchanged
> through an inactive branch; a resource present in no branch is not
> expressible.

## Explicitly out of scope here

`o_n_plusmap`'s result type keeps the loose `'sum_in` / `'sum_out` indices.
That is a **sum-type frame** question, not a linearity one — it is the same
defect as the `NPlusMap` typing/emission mismatch (declared flattened width
vs. emitted outer-tag-plus-payload width) and is handled in the layout-frame
phase, not here. This note closes the context/linearity strand only.
