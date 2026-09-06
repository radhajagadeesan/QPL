# Datatype Elaboration

The datatype operation/elimination layer as implemented in Granthi
v1.0.0 (`[@@source.datatype]`, the Qudit(n) abstraction).  The gap it closed was the operation/elimination
half of datatype elaboration — a contained Source-layer gap, not a
compiler or distributivity redesign:

```
nominal datatype permutation / exhaustive match
        ↓
certified Source.op / sealed tag-preserving case on D.t
        ↓
structural permutation / flat dispatch on the hidden Unit-sum representation
```

## Canonical representation decision (corrected)

The designated authority is the CLEAN Source calculus, not the older
developer note: `narymonoidal.tex` fixes the **left-associated**
expansion `bigplus_{i=0}^{n} A_i := (bigplus_{i=0}^{n-1} A_i) ⊕ A_n`,
and `datatypes-new.tex` fixes `Q_n` to that expansion at base `I`.
`Source.Datatype.unit_sum` is therefore left-associated
(`unit_sum n = Plus (unit_sum (n-1), Unit)`), and the flat sums built
by `cases`/`cases0` mirror it.  (An older untracked developer
note wrote the right-associated expansion; it contradicted the clean
calculus and was corrected.  This document is the tracked authority.)

Flat tag codes are the association-invariant left-to-right leaf order
(`flatten_plus`), consumed identically by the datatype dispatch
(`TDatatypeControl`) and the tag-permutation primitive (`TTagPerm`,
forward |i⟩ ↦ |p(i)⟩, identity on padding states by construction) —
which is precisely why passing circuit tests could conceal the
association mismatch.  The association is therefore pinned
STRUCTURALLY, not just behaviorally, in
`test/test_source_datatype_ops.ml`: arity 3 elaborates to exactly
`Plus(Plus(Unit,Unit),Unit)` and arity 4 to
`Plus(Plus(Plus(Unit,Unit),Unit),Unit)` in the serialized
representation carried by permute, select, and the cases pipeline, with
the right-associated tree asserted ABSENT.  Right-associated legacy
oracles are related to sealed counterparts through the explicit
certified sum associator (`assoc_plus_l`/`assoc_plus_r` chains), never
by silently treating the types as identical.  The formal
closed-operation environment Σ of the clean calculus ("datatype
operations elaborate by substituting their certified core
implementations from an elaboration environment Σ") is realized by
lexically resolved OCaml bindings of sealed `Source.op` values — there
is no unsafe runtime operation registry.

## Shipped sealed API (inside `Datatype.Make (SPEC) ()`)

```ocaml
val cases :                      (* exhaustive tag-preserving case *)
  result:'c P.t ->
  scrutinee:('g1, t) term ->
  branches:(arity, (('id, 'x, 'tail) cons, 'c) term) vector ->
  using:('g1, ('id, 'x, 'tail) cons, 'g) uses ->
  ('g, (t, 'c) tensor) term
val cases0 : (* empty-shared-context clause *)
val permute : (arity, int) vector -> (t, t) op
val involution_permute : (arity, int) vector -> t Op.involution
```

- `cases` lowers as a FLAT pipeline in the canonical encoding: the
  n_dist/n_factor law makes both distributed forms of a unit-summand sum
  share the flat layout, so the boundary conversions are wire-level
  identities and dispatch is a single flat `NPlusMap` (an earlier
  nested-binary fold was rejected by its own tests: asymmetric levels
  re-encode tags).  Branch order is declaration order, the tag survives,
  all branches consume the identical complete nominal context, and
  dispatch touches valid labels only (padding states of a
  non-power-of-two arity are untouched — an all-H arity-3 case differs
  from unconditional H exactly on the padding state, by design).
- `permute` takes the exact-arity length-indexed vector (no bare
  arrays), validates range and bijectivity eagerly, copies the images
  immutably, and lowers through the existing trusted `TTagPerm`
  machinery.  Position i carries the destination of constructor i.
- `involution_permute` re-runs all permutation checks and additionally
  proves p(p(i)) = i; a 3-cycle is rejected as an involution even though
  it is a valid permutation.  The compiled `exp_i` path independently
  re-verifies U² ≈ I (defense in depth).

## PPX surface

```ocaml
type d = C0 | C1 | C2 [@@source.datatype]

let%source f (x : D.t) (y : q) =
  match x with
  | C0 -> h y
  | C1 -> s y
  | C2 -> t y

let shift = D.permute [ C1; C2; C0 ]          (* position i ↦ destination *)
let swap01 = D.involution_permute [ C1; C0; C2 ]
```

Located rejections: non-exhaustive match, duplicated arm, unknown
constructor, constructor of another nominal datatype, wildcard arm,
guard, payload pattern, context mismatch across arms, higher-order arm
result; and for permutations: wrong length, duplicated entry, foreign
constructor, unknown constructor.  Arm order is free; declaration order
is the sole code authority.

## Phased dispatch (no new primitive)

Per-label phased dispatch is a DERIVATION, not new API:
`D.select ~target [Op.compose f_i (Op.phase z_i target_p); …]` equals
the legacy `phased_control` (verified by the row-18 counterpart
checks).  No `phased_select` primitive was added.

## Derived group operations (rows 26, 34)

- `Zn.shift i` and `Zn.neg` are user-declared permutations;
- `Zn.add` is `Zn.select ~target:Zn.p [shift_0; …; shift_(n-1)]`;
- the W3 toggle is `W3.permute [Wsc; Wtrue; Wfalse]` and the controlled
  short-circuit program composes it through the ordinary case sugar and
  certified coherences.

## Honest limitations

- Constructor-name sugar (match arms, permutation lists) requires the
  `[@@source.datatype]` declaration in the same compilation unit; the
  sealed int-vector `permute`/`cases` API works across units.
- No constructor payloads in this MVP; no injection, observation,
  equality test, runtime state preparation, or representation access —
  and still no public Unit and no general `Op.plus`.
- W3 is the CONCRETE three-state instance of the short-circuit witness;
  the paper's `Aux + QBool` with an arbitrary nontrivial `Aux` is
  broader and is not claimed.
- `Zn.add` at n ∈ {5, 8, 11} is verified by compile pins plus the
  eq-verified certified shifts it is assembled from (the tensor-squared
  lam simulation exceeds the 2^10 unitary budget); n ∈ {2, 3, 4} adds
  are circuit-equal to the legacy `control` constructions.
