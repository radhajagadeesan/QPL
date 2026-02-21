(** Abstract QSwitch as an open term (full source language)

    Full pipeline: OCaml open_term -> Bridge -> Python compile -> Circuit

    Builds the abstract QSwitch as a LAMBDA TERM using the full
    source language (Lam, LetPair, Var, App, PlusMap), following
    full_source_language_compilation_spec.md section 5.

    QSwitch : (Q⊸Q) ⊗ (Q⊸Q) ⊗ Bool ⊗ Q  →  Bool ⊗ Q

    The term (from the paper):
      λf. λg. λp.
        let (b, x) = p in
        case b of
          b₀ ↦ f(g(x))
          b₁ ↦ g(f(x))

    Case desugaring (distR pattern from the paper):
      Γ ⊗ (A+B) →[distL] (I⊗Γ) + (I⊗Γ) →[f̂⊕ĝ] (I⊗Q) + (I⊗Q) →[undistL] (I+I)⊗Q

    The PlusMap branches f̂, ĝ are CLOSED morphisms (bare LetPair chains),
    not lambda values. They receive the context Γ = f⊗(g⊗x) via distribution,
    destructure it, and apply the functions.
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

(** Bool = I + I *)
let bool_ty = one ++ one

(** Q ⊸ Q *)
let qq_ty = q -@ q

(** Bool ⊗ Q *)
let bq_ty = bool_ty ** q

(** (Q⊸Q) ⊗ (Q⊸Q) ⊗ Bool ⊗ Q  — right associated *)
let rest2_ty = bq_ty            (* Bool ⊗ Q *)
let rest_ty = qq_ty ** rest2_ty (* (Q⊸Q) ⊗ (Bool ⊗ Q) *)
let input_ty = qq_ty ** rest_ty (* (Q⊸Q) ⊗ ((Q⊸Q) ⊗ (Bool ⊗ Q)) *)

(* ========================================================================= *)
(* Abstract QSwitch as a Lambda term                                          *)
(* ========================================================================= *)

(** Context-distribution approach (from the paper's case desugaring):

    PlusMap branches must be closed MORPHISMS, not lambdas.
    The context Γ = (Q⊸Q) ⊗ ((Q⊸Q) ⊗ Q) is bundled into the payload
    BEFORE distribution. After dist_l, each summand is I ⊗ Γ.
    The branches destructure Γ from input — they're bare LetPair chains.

    Branch: I⊗Γ → I⊗Q
      let (tag, payload) = input in      -- tag:I, payload:Γ
      let (f, gx) = payload in           -- f:Q⊸Q, gx:(Q⊸Q)⊗Q
      let (g, x) = gx in                 -- g:Q⊸Q, x:Q
      (tag, f(g(x)))                     -- for left branch
      (tag, g(f(x)))                     -- for right branch
*)

let abstract_qswitch : (unit, [`Lolli of _ * _]) oterm =
  (* Payload type: (Q⊸Q) ⊗ ((Q⊸Q) ⊗ Q) *)
  let gx_ty = qq_ty ** q in         (* (Q⊸Q) ⊗ Q *)
  let payload_ty = qq_ty ** gx_ty in (* (Q⊸Q) ⊗ ((Q⊸Q) ⊗ Q) *)
  let ip_ty = one ** payload_ty in   (* I ⊗ payload *)
  let _iq_ty = one ** q in           (* I ⊗ Q — used by type_of, not directly *)

  (* Left branch (b=0): CLOSED morphism I⊗Γ → I⊗Q, apply g then f.
     All variables bound by oletpair from the oid scrutinee.

     Context after each oletpair:
       1st: [tag:one, payload:payload_ty]
       2nd: [f:qq, gx:gx_ty, tag:one]
       3rd: [g:qq, x:q, f:qq, tag:one]

     Innermost splits:
       opair:     tag→left, (g,x,f)→right
       oapp(f,·): f→left, (g,x)→right
       oapp(g,x): g→left, x→right *)
  let left_branch =
    oletpair0 "tag" "payload" one payload_ty (oid ip_ty)
      (oletpair "f" "gx" qq_ty gx_ty (ovar "payload" payload_ty)
        (oletpair "g" "x" qq_ty q (ovar "gx" gx_ty)
          (opair (ovar "tag" one)
                 (oapp (ovar "f" qq_ty)
                       (oapp (ovar "g" qq_ty)
                             (ovar "x" q)
                             (SLeft (SRight SNil)))
                       (SRight (SRight (SLeft SNil))))
                 (SRight (SRight (SRight (SLeft SNil)))))
          (SRight (SLeft (SRight SNil))))
        (SRight (SLeft SNil)))
  in
  (* Right branch (b=1): CLOSED morphism I⊗Γ → I⊗Q, apply f then g.
     Same context structure as left branch.

     Innermost splits (swapped application order):
       opair:     tag→left, (g,x,f)→right
       oapp(g,·): g→left, (x,f)→right
       oapp(f,x): f→left, x→right *)
  let right_branch =
    oletpair0 "tag" "payload" one payload_ty (oid ip_ty)
      (oletpair "f" "gx" qq_ty gx_ty (ovar "payload" payload_ty)
        (oletpair "g" "x" qq_ty q (ovar "gx" gx_ty)
          (opair (ovar "tag" one)
                 (oapp (ovar "g" qq_ty)
                       (oapp (ovar "f" qq_ty)
                             (ovar "x" q)
                             (SRight (SLeft SNil)))
                       (SLeft (SRight (SRight SNil))))
                 (SRight (SRight (SRight (SLeft SNil)))))
          (SRight (SLeft (SRight SNil))))
        (SRight (SLeft SNil)))
  in
  (* Body: destructure input, re-pair, dist, plusmap, undist.

     Context after oletpairs:
       1st: [f:qq, rest:rest_ty]
       2nd: [g:qq, rest2:rest2_ty, f:qq]
       3rd: [b:bool_ty, x:q, g:qq, f:qq]

     repaired = (b, (f, (g, x))) pairs all variables.
     pipeline is fully closed (oseq0/oplusmap0).
     oapp: pipeline is closed → all context goes to argument. *)
  let body =
    oletpair "f" "rest" qq_ty rest_ty (ovar "input" input_ty)
      (oletpair "g" "rest2" qq_ty rest2_ty (ovar "rest" rest_ty)
        (oletpair "b" "x" bool_ty q (ovar "rest2" rest2_ty)
          (let repaired =
            opair (ovar "b" bool_ty)
                  (opair (ovar "f" qq_ty)
                         (opair (ovar "g" qq_ty)
                                (ovar "x" q)
                                (SRight (SLeft SNil)))
                         (SRight (SRight (SLeft SNil))))
                  (SLeft (SRight (SRight (SRight SNil))))
          in
          let pipeline =
            oseq0 (oembed (dist_l one one payload_ty))
              (oseq0 (oplusmap0 ip_ty ip_ty left_branch right_branch)
                     (oembed (undist_l one one q)))
          in
          oapp pipeline repaired
            (SRight (SRight (SRight (SRight SNil)))))
          (SRight (SLeft (SRight SNil))))
        (SRight (SLeft SNil)))
      (SLeft SNil)
  in
  olam "input" input_ty bq_ty body


(* ========================================================================= *)
(* Demo                                                                        *)
(* ========================================================================= *)

let () =
  let project_root = Filename.dirname (Sys.getcwd ()) in
  Bridge.set_project_root project_root;

  banner "ABSTRACT QSWITCH (Full Source Language - oterm)";
  print_endline "\nFull pipeline: OCaml oterm -> Bridge -> Python compile -> Circuit\n";

  (* --- Part 1: Show the abstract term --- *)
  banner "Part 1: Abstract QSwitch Term";
  Printf.printf "Type: (Q⊸Q) ⊗ ((Q⊸Q) ⊗ (Bool ⊗ Q))  ⊸  Bool ⊗ Q\n\n";

  let bridge_term = emit_oterm abstract_qswitch in
  Printf.printf "Bridge JSON (abbreviated):\n";
  let json = Bridge.term_to_json bridge_term in
  Printf.printf "  %s\n\n" (if String.length json > 200 then String.sub json 0 200 ^ "..." else json);

  (* --- Part 2: Compile the abstract lambda --- *)
  banner "Part 2: Compile Abstract Lambda";
  incr tests_run;
  (match Bridge.compile_show bridge_term with
   | Bridge.CompileOk _ ->
       Printf.printf "Compilation SUCCESS!\n";
       incr tests_passed
   | Bridge.CompileError err ->
       Printf.printf "Compilation FAILED: %s\n" err);

  (* --- Part 3: Compare with existing meta-level QSwitch --- *)
  banner "Part 3: Comparison with Meta-level QSwitch";
  print_endline "The existing meta-level qswitch[H,S] compiles to 6 gates.";
  print_endline "The abstract lambda should compile to a larger circuit";
  print_endline "(it includes the function application overhead).\n";

  let meta_qswitch_hs =
    let distribute = dist_l one one q in
    let left_branch = par0 (id one) (seq0 gate_s gate_h) in
    let right_branch = par0 (id one) (seq0 gate_h gate_s) in
    let apply_branches = omap0 (one ** q) (one ** q) left_branch right_branch in
    let undistribute = undist_l one one q in
    seq0 distribute (seq0 apply_branches undistribute)
  in
  let meta_term = emit meta_qswitch_hs in
  incr tests_run;
  Printf.printf "Meta-level QSwitch[H,S]:\n";
  (match Bridge.compile_show meta_term with
   | Bridge.CompileOk _ ->
       incr tests_passed
   | Bridge.CompileError err ->
       Printf.printf "Meta-level FAILED: %s\n" err);

  (* --- Part 4: Wire-level Apply to concrete H, S --- *)
  banner "Part 4: Wire-Level Apply (Boundary Splicing)";
  print_endline "Applying abstract QSwitch to H, S via boundary splicing.";
  print_endline "NOT beta-reduction — using general Apply path.\n";

  (* Build H and S as function values: Lam("x", Q, Q, H(x)) *)
  let h_value = olam "hx" q q (oapp (oembed gate_h) (ovar "hx" q) (SRight SNil)) in
  let s_value = olam "sy" q q (oapp (oembed gate_s) (ovar "sy" q) (SRight SNil)) in

  (* Build argument: (H_value, (S_value, Id(Bool⊗Q))) — all closed *)
  let arg = opair0 h_value (opair0 s_value (oid bq_ty)) in

  (* Emit to Bridge terms *)
  let bridge_qswitch = emit_oterm abstract_qswitch in
  let bridge_arg = emit_oterm arg in

  (* Wrap QSwitch in Seq(qswitch, Id(Arrow)) to prevent beta-reduction.
     This makes isinstance(t.f, Lam) == False in Python,
     forcing the general Apply (boundary splicing) path. *)
  let arrow_rep = ty_to_rep (input_ty -@ bq_ty) in
  let wrapped = Bridge.TSeq (bridge_qswitch, Bridge.TId arrow_rep) in

  (* Build application term *)
  let applied = Bridge.TApply (wrapped, bridge_arg) in

  Printf.printf "Type analysis:\n";
  Printf.printf "  QSwitch type: input_ty[w=%d] ⊸ bq_ty[w=%d]\n"
    (Rep.wire_count (ty_to_rep input_ty)) (Rep.wire_count (ty_to_rep bq_ty));
  Printf.printf "  Arrow width: %d (= %d + %d)\n"
    (Rep.wire_count arrow_rep)
    (Rep.wire_count (ty_to_rep input_ty)) (Rep.wire_count (ty_to_rep bq_ty));
  Printf.printf "  Expected circuit width: %d qubits\n\n"
    (Rep.wire_count arrow_rep);

  (* Dump applied JSON for debugging *)
  let applied_json = Bridge.term_to_json applied in
  Printf.printf "Applied term JSON:\n%s\n\n" applied_json;

  incr tests_run;
  (match Bridge.compile_show applied with
   | Bridge.CompileOk _ ->
       Printf.printf "Wire-level Apply compilation SUCCESS!\n";
       incr tests_passed
   | Bridge.CompileError err ->
       Printf.printf "Wire-level Apply compilation FAILED: %s\n" err);

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
