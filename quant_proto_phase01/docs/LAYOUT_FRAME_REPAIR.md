# Layout-frame repair: gate-free fix for unequal-width distributivity

**Status:** Design outline, filed 2026-08-30. **Deferred by decision** to the
frame-aware repair round — see *The frame-aware round* in
`docs/COMPILER_INVARIANTS.md`, which collects this with the three other items
that share the missing piece (the canonical-frame inclusions $j_i^\pm$ do not
exist explicitly; index maps are computed inline).

Partially superseded: the canonical layout policy this note argues for is now
enforced as **Invariant L**, and `NPlusMap` uses the canonical frame. What
remains deferred is the composition side — unequal-width `dist_l` naturality,
whose witness is `demos/dist_l_naturality_probe` (full-unitary fidelity 0.5).

**Motivation.** The current compiler represents post-composition layout
state by a `WirePerm` plus payload-width bookkeeping. This suffices for
equal-width sums but cannot describe the tag-conditioned location of a
tensor spectator on the target side of an unequal-width `DistL`. The
regression witness `ocaml/demos/dist_l_naturality_probe.{ml,output}` shows
the concrete naturality failure: full-unitary fidelity 0.5, disagreement
on all 4 tag-zero codewords, with the tag-zero computation potentially
leaving the valid codeword subspace. Documented in
`docs/LIMITATIONS.md §6`.

**Design goal.** Distributors remain gate-free; the compiler explicitly
carries the richer semantic address information needed to compose them
correctly.

---

## Repair outline

### 1. Replace `WirePerm` as the complete layout state.

Introduce a `LayoutFrame` containing:

- physical tag positions;
- valid tag values;
- for each tag branch, a map from logical wire paths to physical wires;
- padding positions;
- physical register width.

### 2. Give every compiled term input and output frames.

Conceptually return:

```
Compiled(circuit, input_frame, output_frame, global_perm)
```

Correctness should mean:

$$
C \, E_{F_{\text{in}}}(x) = E_{F_{\text{out}}}(f(x))
$$

for every valid logical codeword $x$.

### 3. Make distributivity update only the frame.

`dist_l` emits no gates. For the failing example, its target frame records:

- tag 0: `A → wire 1`, `C → wire 3`, `padding → wire 2`
- tag 1: `B_1 → wire 1`, `B_2 → wire 2`, `C → wire 3`

Thus $C$ remains on physical wire 3 in both branches even though its
target *type* address changes.

### 4. Pass frames through sequential composition.

`Seq(f, g)` must compile `g` against the actual output frame of `f`. It
must **not** reconstruct a fresh canonical layout solely from `dom(g)`.

### 5. Make `TenTerm`, `PlusMap`, and gates frame-aware.

In particular, `PlusMap` must not assume:

```
physical wire = payload_base + branch_local_index
```

It should resolve each branch-local logical address through the current
frame. If the same logical operation targets different physical wires in
different branches, emit exact-tag-controlled operations. If all
branches target the same wire, emit one unconditional operation.

### 6. Separate frame changes from materialized permutations.

A global `WirePerm` may still be converted to SWAPs. A tag-dependent
logical frame is **not** a global wire permutation and must **not** be
materialized as ordinary SWAPs. If the public output requires a
canonical frame, add an explicit final canonicalization pass; that pass
may require controlled gates.

### 7. Lock the invariant with tests.

Add:

- the failing naturality square;
- exhaustive valid-codeword preservation;
- coherent-superposition comparisons;
- `dist ; undist = id` inside surrounding programs;
- both left and right distributivity;
- unequal and nested summand widths;
- checks that padding remains zero;
- assertions that standalone distributors remain gate-free.

---

This preserves the intended story: **distributors themselves remain
gate-free, while the compiler explicitly carries the richer semantic
address information needed to compose them correctly.**
