# Align normalization

**Status:** Open — deliberately deferred **post-v1.0.0**.  Filed
2026-09-01, immediately after the boundary-frame / Align correctness
repair landed.  This is optimization/normalization debt (circuit size at
splices), **not a correctness or soundness blocker**: v1.0.0 ships with
the correct, tested Align behaviour.

**Not a soundness gap.** The correctness repair is complete and green; this
task is about the *cost* of what it emits. Normalization deliberately belongs
after correctness, not folded into it.

---

## Motivation

Align reconciles a producer's output frame with a consumer's input frame at
each splice, emitting `A† ; G_C ; A`. Nothing currently looks across
neighbouring splices, so a chain emits an alignment and its inverse back to
back, and several alignments in sequence stay as separate permutation boxes.

The visible symptom is `ocaml/demos/curried_select_3_e2e`: the
selector's INNER pipeline went from **13 to 23 commands** — ten
`ToffoliBox`es, repeatedly on the same wire triple — and the complete
curried selector (abstract 16-qubit form and applied H/S/T form alike)
sits at a **25-gate** baseline.  That 25-gate figure is the optimization
target for this task.

Note what that demo does and does not establish. It establishes successful
compilation and unchanged printed result lines. It does **not** itself compute
a numerical semantic equivalence — but the APPLIED H/S/T selector already has
an independent exact oracle (`rtol=0`, zero leakage, both materialization
modes: `python/tests/test_release_safety.py::test_D_curried_selector_is_h_s_t`);
what remains deferred with this task is a dense oracle for the UNAPPLIED
abstract function value. The splice is correct by the tested Align
mechanism — the exact framed-semantics (`rtol=0`) and zero-leakage assertions
live in `python/tests/test_align_acceptance.py` — but a dedicated semantic
oracle for the curried selector is part of this task, not evidence already in
hand.

## Gates

This task is done when **all** of the following hold:

1. **Cancel adjacent inverse Aligns.** `A` immediately followed by `A†` (in
   either order) across a splice boundary emits nothing.

2. **Compose consecutive Align permutations.** Two or more alignments in
   sequence with no intervening gate on their wires collapse to a single
   permutation box, or to nothing when the composite is the identity.

3. **`curried_select_3_e2e` drops from 23 to at most 15 commands**, ideally
   back toward the pre-repair 13.

4. **Add an exact framed-semantics and zero-leakage oracle for the curried
   selector.** Compare `U_sem = (u_out)† G u_in` against an independently
   constructed expected action with `rtol=0`, and assert
   `leak = ||(I − u_out u_out†) G u_in|| = 0`. Do not build the oracle out of
   the compiler's own frame code.

5. **Naturality fidelity stays 1.0** — `ocaml/demos/dist_l_naturality_probe`
   must not regress from the value the correctness repair achieved.

6. **Rerun every gate:** full Python suite (zero warnings), `dune test
   --force`, the OCaml bridge round-trip, and the 34-demo sweep against
   committed HEAD, with every diff classified as intended / serialization-only
   / semantic regression.

## Cautions carried forward from the correctness round

Three defects in that round were each hidden by a test that agreed with the
bug. They are worth re-reading before touching Align again:

- **A symmetric permutation is not an adequate witness.** `DistR(Q,I,I)` has
  perm `[1,0]`, which is self-inverse, so a direction error passed; only
  `DistR(Q⊗Q,I,I)` at `[2,0,1]` exposed it. This is the same trap that hid the
  pending-permutation direction behind `TwistTen(Q,Q)`. Any cancellation rule
  must be tested on an **asymmetric** alignment.

- **Do not build the oracle from the code under test.** The `dist_r` defect
  survived the unit suite because the test asserted the identity and the bug
  produced the identity. Cancellation rules must be checked against
  independently computed semantics, not against "the circuit got shorter".

- **Cheaper must not mean different.** Every cancellation has to preserve the
  framed semantics exactly (`rtol=0`) and keep leakage at zero, including the
  cases where the two frames genuinely differ and the alignment is doing real
  work.

## Pointers

- `python/src/compile/align.py` — `align_permutation`, `build_align`,
  `align_as_wire_permutation`, `emit_align`, `transported_frame`
- `python/src/compile/frames.py` — `Frame`, `Sector`, `Port`,
  `semantic_action`, `leakage`, `distributor_iso`
- `docs/LAYOUT_FRAME_REPAIR.md` — the delivered design
- `docs/LIMITATIONS.md` §6 — where this inefficiency is recorded
