(** DECISIVE PROBE for the "layout normalization" question.

    Referee's concern: under a LITERAL layout V_{A⊗B} = V_A ⊗ V_B (paper
    Appendix F), dist_L at unequal-width summands would need tag-conditioned
    swaps (gates). If the implementation normalizes the layout (⊕ outermost),
    dist_L is pure wire relabeling (0 gates) regardless of widths.

    Test: dist_l at (Q ⊕ (Q⊗Q)) ⊗ Q  where w_A=1, w_B=2, w_C=1 — UNEQUAL.
      Signature: (A ⊕ B) ⊗ C → (A ⊗ C) ⊕ (B ⊗ C)

    Zero gates  ⇒  code normalizes  ⇒  the formal statement in Appendix F
                                       should be tightened to describe the
                                       normalized layout; the width hedges
                                       (dist_R row, factor_n, η-case
                                       emission, toolchain (a)) can come out.
    Nonzero    ⇒  code matches the literal Appendix F definition; the
                  width-hedge patches stand as written.
*)

open Qpl_surface
open Linear

let () =
  let a_ty = q in
  let b_ty = q ** q in
  let c_ty = q in
  let term = dist_l a_ty b_ty c_ty in

  print_endline "";
  print_endline "===============================================================";
  print_endline "  dist_l at UNEQUAL widths — layout-normalization probe";
  print_endline "===============================================================";
  Printf.printf "  Type: (Q ⊕ (Q⊗Q)) ⊗ Q  →  (Q⊗Q) ⊕ ((Q⊗Q)⊗Q)\n";
  Printf.printf "  Widths: w_A=%d, w_B=%d, w_C=%d\n"
    (Rep.wire_count (ty_to_rep a_ty))
    (Rep.wire_count (ty_to_rep b_ty))
    (Rep.wire_count (ty_to_rep c_ty));
  print_endline "";

  print_endline "-- Default compile (non-materialized) --";
  (match Bridge.compile_show (emit term) with
   | Bridge.CompileOk (_, sz) ->
       Printf.printf "  gate count: %d\n" sz
   | Bridge.CompileError err ->
       Printf.printf "  compile error: %s\n" err)
