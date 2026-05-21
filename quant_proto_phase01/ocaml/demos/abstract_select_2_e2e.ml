(** Abstract select_2 as an open term (full source language)

    Full pipeline: OCaml open_term -> Bridge -> Python compile -> Circuit

    This demo exercises three things:

    (a) BUILD the abstract select_2 as a lambda term.

        Mathematically (curried form):
          select_{2,A} : (A⊸A) ⊸ (A⊸A) ⊸ (QBool⊗A ⊸ QBool⊗A)
          select_{2,A} := λf_0. λf_1. λp.
            dist_l ; [id_I⊗f_0 | id_I⊗f_1] ; undist_l   applied to p

        Implemented (tupled form, isomorphic via currying):
          select_{2,A} : ((A⊸A) ⊗ (A⊸A) ⊗ (QBool⊗A)) ⊸ (QBool⊗A)
          select_{2,A} := λinput. let (f_0, (f_1, p)) = input in
            (dist_l ; [id_I⊗f_0 | id_I⊗f_1] ; undist_l)(p)

        The function parameters f_0, f_1 are ABSTRACT (wire bundles, not gates).
        Each PlusMap branch uses ONLY its respective function — strict linearity
        is satisfied via SPLIT CONTEXT: left branch's context has f_0, right's
        has f_1, no sharing.

    (b) INSTANTIATE with concrete H, S via single boundary-splicing Apply
        on the tupled argument (H_value, (S_value, p_id)).

    (c) VERIFY equality at base types: partial trace over the function-value
        wires recovers the 2-qubit meta-level control z2 q [|H; S|].
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

(* ========================================================================= *)
(* Types                                                                      *)
(* ========================================================================= *)

let qq_ty = q -@ q              (* Q⊸Q *)
let bool_ty = one ++ one         (* QBool = I + I *)
let qba_ty = bool_ty ** q        (* QBool ⊗ Q *)
let ia_ty = one ** q             (* I ⊗ Q (summand after dist_l) *)

(* Tupled input type: (Q⊸Q) ⊗ ((Q⊸Q) ⊗ (QBool⊗Q)) *)
let input_ty = qq_ty ** (qq_ty ** qba_ty)

(* ========================================================================= *)
(* Abstract select_2 (tupled form)                                            *)
(* ========================================================================= *)

let abstract_select_2 =
  (* Left branch (tag=0): receive I⊗Q via oid, destructure to (i, a),
     apply f_0 to a, produce (i, f_0(a)). Context = [f_0]. *)
  let left_branch =
    oletpair "i" "a" one q (oid ia_ty)
      (opair (ovar "i" one)
             (oapp (ovar "f0" qq_ty) (ovar "a" q) (SRight (SLeft SNil)))
             (SLeft (SRight (SRight SNil))))
      (SRight SNil)
  in
  (* Right branch (tag=1): same with f_1. Context = [f_1]. *)
  let right_branch =
    oletpair "i" "a" one q (oid ia_ty)
      (opair (ovar "i" one)
             (oapp (ovar "f1" qq_ty) (ovar "a" q) (SRight (SLeft SNil)))
             (SLeft (SRight (SRight SNil))))
      (SRight SNil)
  in

  (* oplusmap with split: f_0 → left, f_1 → right. Outer context = [f_1, f_0]. *)
  let pm = oplusmap ia_ty ia_ty left_branch right_branch (SRight (SLeft SNil)) in

  (* Pipeline: dist_l ; pm ; undist_l, applied to p. *)
  let dist_term = oembed (dist_l one one q) in
  let undist_term = oembed (undist_l one one q) in
  let dist_pm = oseq dist_term pm (SRight (SRight SNil)) in
  let pipeline = oseq dist_pm undist_term (SLeft (SLeft SNil)) in
  (* pipeline : Lolli of qba_ty * qba_ty, context [f_1, f_0] *)

  (* Body of the outer lambda: destructure tupled input then apply pipeline to p.

     Outer body context after first oletpair = [f0, rest]
     Inner body context after second oletpair = [f1, p, f0]
     oapp combines: function (pipeline) needs [f1, f0]; arg (p) needs [p]
  *)
  let body =
    oletpair "f0" "rest" qq_ty (qq_ty ** qba_ty) (ovar "input" input_ty)
      (oletpair "f1" "p" qq_ty qba_ty (ovar "rest" (qq_ty ** qba_ty))
        (oapp pipeline (ovar "p" qba_ty)
              (SLeft (SRight (SLeft SNil))))   (* f1 → func, p → arg, f0 → func *)
        (SRight (SLeft SNil)))                  (* f0 → body-outer, rest → pair *)
      (SLeft SNil)                              (* input → pair *)
  in

  (* Single outer lambda with tupled input. *)
  olam "input" input_ty qba_ty body


(* ========================================================================= *)
(* Demo                                                                       *)
(* ========================================================================= *)

let () =
  banner "ABSTRACT SELECT_2 (Full Source Language - oterm)";
  print_endline "\nFull pipeline: OCaml oterm -> Bridge -> Python compile -> Circuit\n";

  (* --- Part 1: Show the abstract term --- *)
  banner "Part 1: Abstract select_2 Term";
  Printf.printf "Curried type (math):  (Q⊸Q) ⊸ (Q⊸Q) ⊸ (QBool⊗Q ⊸ QBool⊗Q)\n";
  Printf.printf "Tupled type (impl):   ((Q⊸Q) ⊗ ((Q⊸Q) ⊗ (QBool⊗Q))) ⊸ (QBool⊗Q)\n";
  Printf.printf "Definition:\n";
  Printf.printf "  select_2 := λinput. let (f_0, (f_1, p)) = input in\n";
  Printf.printf "    (dist_l ; [id_I⊗f_0 | id_I⊗f_1] ; undist_l)(p)\n\n";

  let bridge_term = emit_oterm abstract_select_2 in
  let json = Bridge.term_to_json bridge_term in
  Printf.printf "Bridge JSON (abbreviated):\n  %s\n\n"
    (if String.length json > 200 then String.sub json 0 200 ^ "..." else json);

  (* --- Part 2: Compile the abstract lambda --- *)
  banner "Part 2: Compile Abstract Lambda";
  Printf.printf "Width analysis:\n";
  Printf.printf "  Q⊸Q                                       = 2 qubits\n";
  Printf.printf "  QBool⊗Q                                    = 2 qubits\n";
  Printf.printf "  Input  (Q⊸Q)⊗((Q⊸Q)⊗(QBool⊗Q))            = 6 qubits\n";
  Printf.printf "  Output  QBool⊗Q                            = 2 qubits\n";
  Printf.printf "  Lambda value  width(input)+width(output)   = 8 qubits  (expected)\n\n";

  incr tests_run;
  (match Bridge.compile_show bridge_term with
   | Bridge.CompileOk _ ->
       Printf.printf "Abstract compilation SUCCESS!\n";
       incr tests_passed
   | Bridge.CompileError err ->
       Printf.printf "Abstract compilation FAILED: %s\n" err);

  (* --- Part 3: Instantiate with concrete H, S --- *)
  banner "Part 3: Instantiate with concrete H, S";
  print_endline "Build argument tuple (H_value, (S_value, Id(QBool⊗Q))) and";
  print_endline "Apply abstract select_2 to it via boundary splicing.\n";

  let h_value = olam "hx" q q (oapp (oembed gate_h) (ovar "hx" q) (SRight SNil)) in
  let s_value = olam "sy" q q (oapp (oembed gate_s) (ovar "sy" q) (SRight SNil)) in

  (* Argument: (H_value, (S_value, Id(QBool⊗Q))) — all closed. *)
  let arg = opair0 h_value (opair0 s_value (oid qba_ty)) in

  let bridge_select = emit_oterm abstract_select_2 in
  let bridge_arg = emit_oterm arg in

  let applied = Bridge.TApply (bridge_select, bridge_arg) in

  incr tests_run;
  (match Bridge.compile_show applied with
   | Bridge.CompileOk _ ->
       Printf.printf "Instantiation SUCCESS!\n";
       incr tests_passed
   | Bridge.CompileError err ->
       Printf.printf "Instantiation FAILED: %s\n" err);

  (* --- Part 4: Verify against meta-level control --- *)
  (* --- Closed structural check: same body shape but f_0=H, f_1=S as closed gates --- *)
  banner "Part 3.5: Closed structural check (sanity)";
  let closed_select =
    let l = par0 (id one) gate_h in
    let r = par0 (id one) gate_s in
    let pm = omap0 ia_ty ia_ty l r in
    seq0 (seq0 (dist_l one one q) pm) (undist_l one one q)
  in
  Printf.printf "closed_select (dist_l ; omap0(id⊗H, id⊗S) ; undist_l):\n";
  (match Bridge.compile_show (emit closed_select) with
   | Bridge.CompileOk _ -> ()
   | Bridge.CompileError err -> Printf.printf "FAILED: %s\n" err);

  banner "Part 4: Verify against meta-level control z2 q [|H; S|]";
  print_endline "Partial trace over function-value wires should recover the";
  print_endline "2-qubit meta-level coherent control circuit.\n";

  let z2 = datatype ~name:"Z2" ~arity:2 ~labels:["0"; "1"] ~ops:[] in
  let meta_control = control z2 q [| gate_h; gate_s |] in
  let bridge_meta = emit meta_control in

  Printf.printf "Meta control z2 q [|H; S|]:\n";
  (match Bridge.compile_show bridge_meta with
   | Bridge.CompileOk _ -> ()
   | Bridge.CompileError err -> Printf.printf "FAILED: %s\n" err);

  incr tests_run;
  (match Bridge.eq_circ_partial applied bridge_meta with
   | Bridge.EqCircOk (true, fidelity) ->
       Printf.printf "  ✓ Tr_{f_0,f_1}[select_2(H,S)] = control z2 q [|H;S|] (fidelity=%.6f)\n" fidelity;
       incr tests_passed
   | Bridge.EqCircOk (false, fidelity) ->
       Printf.printf "  ✗ Tr_{f_0,f_1}[select_2(H,S)] ≠ control z2 q [|H;S|] (fidelity=%.6f)\n" fidelity
   | Bridge.EqCircError err ->
       Printf.printf "  ✗ Partial trace check ERROR: %s\n" err);

  (* --- Summary --- *)
  banner "Summary";
  Printf.printf "\n  Tests: %d/%d passed\n" !tests_passed !tests_run;
  if !tests_passed = !tests_run then
    print_endline "\n  ALL TESTS PASSED"
  else begin
    Printf.printf "\n  %d TESTS FAILED\n" (!tests_run - !tests_passed);
    exit 1
  end;
  print_endline ""
