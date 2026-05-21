(** Nested PlusMap Sanity Check (select_4, select_8 via balanced binary)

    Tests that nested binary PlusMap with OPEN branches works correctly —
    the (+)/⊕ analog of the nested Apply test (compose_n).

    Uses BALANCED binary decomposition: Z_4 = (I+I) + (I+I), Z_8 = balanced
    quad-pair. Each level dispatches on one tag bit using oplusmap with split
    context. The deferred-Lam mechanism must propagate through multiple
    nesting layers.

    Note: asymmetric n (Z_3, Z_5, etc.) requires either auto-flattening into
    NPlusMap or explicit padding — not exercised here.

    Verifies: select_n(f_0, ..., f_{n-1}) traced over function wires equals
    the meta-level control z_n q [|f_0; ...; f_{n-1}|].
*)

open Qpl_surface
open Linear

let tests_run = ref 0
let tests_passed = ref 0

let banner title =
  print_endline "";
  print_endline (String.make 74 '=');
  Printf.printf "  %s\n" title;
  print_endline (String.make 74 '=')

let qq_ty = q -@ q
let ia_ty = one ** q             (* I ⊗ Q *)
let bool_ty = one ++ one         (* binary sum *)
let b_a_ty = bool_ty ** q        (* (I+I) ⊗ Q *)

(* Function values *)
let h_value = olam "hx" q q (oapp (oembed gate_h) (ovar "hx" q) (SRight SNil))
let s_value = olam "sy" q q (oapp (oembed gate_s) (ovar "sy" q) (SRight SNil))
let t_value = olam "tz" q q (oapp (oembed gate_t) (ovar "tz" q) (SRight SNil))
let x_value = olam "xw" q q (oapp (oembed gate_x) (ovar "xw" q) (SRight SNil))

(** Apply-f branch: receives I⊗Q via oid, applies f (named var) to the Q part.
    Context: [f_name]. Output type: I⊗Q. *)
let apply_f_branch f_name =
  oletpair "i" "a" one q (oid ia_ty)
    (opair (ovar "i" one)
           (oapp (ovar f_name qq_ty) (ovar "a" q) (SRight (SLeft SNil)))
           (SLeft (SRight (SRight SNil))))
    (SRight SNil)

(** Build a 2-way pipeline: dist_l ; PlusMap(apply_f_i, apply_f_j) ; undist_l.
    Operates on (I+I) ⊗ Q. Each branch applies one function (named var).
    Context: [f_j, f_i] (j on top per oplusmap split). *)
let pair_pipeline f_i f_j =
  let pm = oplusmap ia_ty ia_ty
    (apply_f_branch f_i) (apply_f_branch f_j)
    (SRight (SLeft SNil))
  in
  let dist = oembed (dist_l one one q) in
  let undist = oembed (undist_l one one q) in
  let dist_pm = oseq dist pm (SRight (SRight SNil)) in
  oseq dist_pm undist (SLeft (SLeft SNil))

(* ========================================================================= *)
(* select_4 : Z_4 = (I+I) + (I+I)  (balanced binary)                          *)
(* ========================================================================= *)

(** Left outer branch: apply pair_pipeline(f_0, f_1) to (I+I)⊗Q. Context: [f_1, f_0]. *)
let left_outer_branch_4 =
  oapp (pair_pipeline "f0" "f1") (oid b_a_ty) (SLeft (SLeft SNil))

(** Right outer branch: apply pair_pipeline(f_2, f_3) to (I+I)⊗Q. Context: [f_3, f_2]. *)
let right_outer_branch_4 =
  oapp (pair_pipeline "f2" "f3") (oid b_a_ty) (SLeft (SLeft SNil))

(** Outer pipeline for Z_4. Context: [f_3, f_2, f_1, f_0]. *)
let outer_pipeline_4 =
  let pm = oplusmap b_a_ty b_a_ty
    left_outer_branch_4 right_outer_branch_4
    (SRight (SRight (SLeft (SLeft SNil))))
  in
  let dist = oembed (dist_l bool_ty bool_ty q) in
  let undist = oembed (undist_l bool_ty bool_ty q) in
  let dist_pm = oseq dist pm (SRight (SRight (SRight (SRight SNil)))) in
  oseq dist_pm undist (SLeft (SLeft (SLeft (SLeft SNil))))

(** Full select_4 lambda: tupled input (f_0, (f_1, (f_2, (f_3, p)))). *)
let abstract_select_4 =
  let z4_ty = bool_ty ++ bool_ty in
  let z4a_ty = z4_ty ** q in
  let input_ty = qq_ty ** (qq_ty ** (qq_ty ** (qq_ty ** z4a_ty))) in
  let body =
    oletpair "f0" "rest1" qq_ty (qq_ty ** (qq_ty ** (qq_ty ** z4a_ty))) (ovar "input" input_ty)
      (oletpair "f1" "rest2" qq_ty (qq_ty ** (qq_ty ** z4a_ty)) (ovar "rest1" (qq_ty ** (qq_ty ** (qq_ty ** z4a_ty))))
        (oletpair "f2" "rest3" qq_ty (qq_ty ** z4a_ty) (ovar "rest2" (qq_ty ** (qq_ty ** z4a_ty)))
          (oletpair "f3" "p" qq_ty z4a_ty (ovar "rest3" (qq_ty ** z4a_ty))
            (oapp outer_pipeline_4 (ovar "p" z4a_ty)
                  (SLeft (SRight (SLeft (SLeft (SLeft SNil))))))
            (SRight (SLeft (SRight (SRight SNil)))))
          (SRight (SLeft (SRight SNil))))
        (SRight (SLeft SNil)))
      (SLeft SNil)
  in
  olam "input" input_ty z4a_ty body

(* ========================================================================= *)
(* Verification helper                                                        *)
(* ========================================================================= *)

let verify_eq_partial name term1 term2 =
  incr tests_run;
  match Bridge.eq_circ_partial term1 term2 with
  | Bridge.EqCircOk (true, fidelity) ->
      Printf.printf "  ✓ %s (fidelity=%.6f)\n" name fidelity;
      incr tests_passed
  | Bridge.EqCircOk (false, fidelity) ->
      Printf.printf "  ✗ %s FAILED (fidelity=%.6f)\n" name fidelity
  | Bridge.EqCircError err ->
      Printf.printf "  ✗ %s ERROR: %s\n" name err


let () =
  banner "NESTED PlusMap (select_4) SANITY CHECK";
  print_endline "\nTests nested binary PlusMap with open branches —";
  print_endline "the (+)/⊕ analog of nested Apply (compose_n).";
  print_endline "Balanced binary: Z_4 = (I+I) + (I+I).\n";

  (* --- select_4 with H, S, T, X --- *)
  banner "Part 1: select_4 abstract circuit (Z_4 = (I+I)+(I+I))";
  Printf.printf "Compile abstract select_4:\n";
  (match Bridge.compile_show (emit_oterm abstract_select_4) with
   | Bridge.CompileOk _ -> ()
   | Bridge.CompileError err -> Printf.printf "FAILED: %s\n" err);

  banner "Part 2: select_4(H, S, T, X) instantiated";
  let z4_ty = bool_ty ++ bool_ty in
  let z4a_ty = z4_ty ** q in
  let arg_4 = opair0 h_value (opair0 s_value (opair0 t_value (opair0 x_value (oid z4a_ty)))) in
  let applied_4 = Bridge.TApply (emit_oterm abstract_select_4, emit_oterm arg_4) in

  Printf.printf "select_4(H, S, T, X):\n";
  (match Bridge.compile_show applied_4 with
   | Bridge.CompileOk _ -> ()
   | Bridge.CompileError err -> Printf.printf "FAILED: %s\n" err);

  banner "Part 3: Meta control z_4 q [|H; S; T; X|]";
  let z4_dt = datatype ~name:"Z4" ~arity:4 ~labels:["0";"1";"2";"3"] ~ops:[] in
  let meta_4 = control z4_dt q [| gate_h; gate_s; gate_t; gate_x |] in
  (match Bridge.compile_show (emit meta_4) with
   | Bridge.CompileOk _ -> ()
   | Bridge.CompileError err -> Printf.printf "FAILED: %s\n" err);

  banner "Part 4: Partial trace verification";
  verify_eq_partial "Tr_{f_0..f_3}[select_4(H,S,T,X)] = control z_4 [|H;S;T;X|]"
    applied_4 (emit meta_4);

  (* Additional combos to catch any branch-order bugs *)
  let arg_xthx = opair0 x_value (opair0 t_value (opair0 h_value (opair0 x_value (oid z4a_ty)))) in
  let applied_xthx = Bridge.TApply (emit_oterm abstract_select_4, emit_oterm arg_xthx) in
  let meta_xthx = control z4_dt q [| gate_x; gate_t; gate_h; gate_x |] in
  verify_eq_partial "select_4(X,T,H,X) = control z_4 [|X;T;H;X|]"
    applied_xthx (emit meta_xthx);

  let arg_hhss = opair0 h_value (opair0 h_value (opair0 s_value (opair0 s_value (oid z4a_ty)))) in
  let applied_hhss = Bridge.TApply (emit_oterm abstract_select_4, emit_oterm arg_hhss) in
  let meta_hhss = control z4_dt q [| gate_h; gate_h; gate_s; gate_s |] in
  verify_eq_partial "select_4(H,H,S,S) = control z_4 [|H;H;S;S|]"
    applied_hhss (emit meta_hhss);

  banner "Summary";
  Printf.printf "\n  Tests: %d/%d passed\n" !tests_passed !tests_run;
  if !tests_passed = !tests_run then
    print_endline "\n  ALL TESTS PASSED"
  else begin
    Printf.printf "\n  %d TESTS FAILED\n" (!tests_run - !tests_passed);
    exit 1
  end;
  print_endline ""
