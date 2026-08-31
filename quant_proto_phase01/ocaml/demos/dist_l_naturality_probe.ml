(** Documentation probe: unequal-width distributivity naturality.

    STATUS: this file is NOT a passing regression test. It is an
    executable witness that documents the implementation incompleteness
    described in `docs/LIMITATIONS.md §6` ("Unequal-width distributivity:
    composition unsupported"). The repair architecture is spelled out in
    `docs/LAYOUT_FRAME_REPAIR.md`.

    Under the current compiler, distributivity naturality with respect
    to `id_{A⊕B} ⊗ X_C` at unequal-width summands is expected to
    fail — the standalone distributor emits zero gates and an identity
    WirePerm, but that metadata cannot express the tag-dependent
    location of a tensor spectator in the target payload. This file
    runs the concrete regression witness and prints what the compiler
    actually does, so the incompleteness is visible and diff-trackable.

    Once the layout-frame repair lands, the observed fidelity should
    flip from 0.5 to 1.0 — that is the signal that the fix is in place,
    at which point this file's committed output will diff against the
    fresh run, and both this file and LIMITATIONS §6 should be updated.

    Regression witness:  A = Q,  B = Q ⊗ Q,  C = Q,

      P_L = (id_{A⊕B} ⊗ X_C) ; dist_l(A, B, C)
      P_R = dist_l(A, B, C) ; [ (id_A ⊗ X_C) ⊕ (id_B ⊗ X_C) ]

    Both have type  (A ⊕ B) ⊗ C  ⟶  (A ⊗ C) ⊕ (B ⊗ C).

    Wire budget:
      (A ⊕ B) ⊗ C          : tag(1) + payload(max(1,2)=2) + C(1) = 4 wires
      (A ⊗ C) ⊕ (B ⊗ C)    : tag(1) + payload(max(2,3)=3)        = 4 wires

    Valid codewords: |A|·|C| + |B|·|C| = 2·2 + 4·2 = 4 + 8 = 12
    out of 2^4 = 16 basis states. *)

open Qpl_surface
open Linear

let banner title =
  print_endline "";
  print_endline (String.make 74 '=');
  Printf.printf "  %s\n" title;
  print_endline (String.make 74 '=')

(* Types *)
let a_ty = q
let b_ty = q ** q
let c_ty = q

(* Building blocks *)
let id_ab      = id (a_ty ++ b_ty)
let x_c        = gate_x                         (* : Q → Q, acts on C *)
let dist       = dist_l a_ty b_ty c_ty
let left_branch  = par0 (id a_ty) x_c            (* : A ⊗ C → A ⊗ C *)
let right_branch = par0 (id b_ty) x_c            (* : B ⊗ C → B ⊗ C *)
let out_omap =
  omap0 (a_ty ** c_ty) (b_ty ** c_ty) left_branch right_branch

(* P_L = (id_{A⊕B} ⊗ X_C) ; dist_l *)
let p_l = seq0 (par0 id_ab x_c) dist

(* P_R = dist_l ; [ (id_A ⊗ X_C) ⊕ (id_B ⊗ X_C) ] *)
let p_r = seq0 dist out_omap

let () =
  banner "dist_l NATURALITY PROBE  (documentation of LIMITATIONS §6)";

  print_endline "";
  print_endline "  This probe DOCUMENTS the current-implementation behavior";
  print_endline "  described in docs/LIMITATIONS.md §6.  It does not assert";
  print_endline "  correctness; it reports what the compiler actually does.";
  print_endline "";
  print_endline "  P_L = (id_{A⊕B} ⊗ X_C) ; dist_l(A, B, C)";
  print_endline "  P_R = dist_l(A, B, C) ; [ (id_A ⊗ X_C) ⊕ (id_B ⊗ X_C) ]";
  print_endline "";
  print_endline "  Both : (A ⊕ B) ⊗ C  →  (A ⊗ C) ⊕ (B ⊗ C)";
  print_endline "  Wires: 4 (tag 1 + payload 2 + C 1);  4 (tag 1 + payload 3).";
  print_endline "  Valid codewords: 4 + 8 = 12 of 16 basis states.";

  banner "PART 1: Compile P_L with materialize=False (symbolic wire perms)";
  print_endline "";
  (match Bridge.compile_show (emit p_l) with
   | Bridge.CompileOk _ -> ()
   | Bridge.CompileError err -> Printf.printf "  compile error: %s\n" err);

  banner "PART 2: Compile P_R with materialize=False (symbolic wire perms)";
  print_endline "";
  (match Bridge.compile_show (emit p_r) with
   | Bridge.CompileOk _ -> ()
   | Bridge.CompileError err -> Printf.printf "  compile error: %s\n" err);

  banner "PART 3: Compile P_L with materialize=True (SWAPs emitted)";
  print_endline "";
  (match Bridge.compile_show_materialized (emit p_l) with
   | Bridge.CompileOk _ -> ()
   | Bridge.CompileError err -> Printf.printf "  compile error: %s\n" err);

  banner "PART 4: Compile P_R with materialize=True (SWAPs emitted)";
  print_endline "";
  (match Bridge.compile_show_materialized (emit p_r) with
   | Bridge.CompileOk _ -> ()
   | Bridge.CompileError err -> Printf.printf "  compile error: %s\n" err);

  banner "PART 5: Observed unitary equality  (Bridge.eq_circ, materialize=True)";
  print_endline "";
  print_endline "  Bridge.eq_circ compiles both terms with materialize=True and";
  print_endline "  compares full 2^4 = 16-dim unitaries, including 12 valid";
  print_endline "  codewords + 4 padding basis states.";
  print_endline "";
  (match Bridge.eq_circ (emit p_l) (emit p_r) with
   | Bridge.EqCircOk (true, f) ->
       Printf.printf "  Observed: P_L = P_R   (fidelity = %.6f)\n" f;
       print_endline "";
       print_endline "  Full agreement observed. This indicates the layout-frame";
       print_endline "  repair (see docs/LAYOUT_FRAME_REPAIR.md) has landed";
       print_endline "  or the incompleteness has otherwise been resolved.";
       print_endline "  Please update docs/LIMITATIONS.md §6 accordingly."
   | Bridge.EqCircOk (false, f) ->
       Printf.printf "  Observed: P_L ≠ P_R   (fidelity = %.6f)\n" f;
       print_endline "";
       print_endline "  This is the current-implementation behavior documented in";
       print_endline "  docs/LIMITATIONS.md §6. Under the current WirePerm-based";
       print_endline "  layout state, the tag-dependent location of C in the target";
       print_endline "  payload cannot be represented; P_L unconditionally X's wire 3";
       print_endline "  (which is C only in the tag=1 branch), while P_R correctly";
       print_endline "  X's wire 2 in the tag=0 branch and wire 3 in the tag=1";
       print_endline "  branch via tag-conditioned dispatch. Repair architecture is";
       print_endline "  specified in docs/LAYOUT_FRAME_REPAIR.md."
   | Bridge.EqCircError err ->
       Printf.printf "  bridge error: %s\n" err);

  banner "END OF PROBE";
  print_endline "";
  print_endline "  This file exits 0 on both the documented behavior (fidelity 0.5)";
  print_endline "  and the post-repair behavior (fidelity 1.0). A change of behavior";
  print_endline "  is signalled by a diff against the committed .output file, not by";
  print_endline "  a test-runner failure."
