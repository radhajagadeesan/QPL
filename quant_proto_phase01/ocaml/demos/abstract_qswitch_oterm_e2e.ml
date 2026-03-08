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

    Case desugaring via ocase_hom:
      Γ ⊗ (A+B) →[distR] (Γ⊗I) + (Γ⊗I) →[f̂⊕ĝ] (I⊗Q) + (I⊗Q) →[undistL] (I+I)⊗Q

    ocase_hom handles the dist_r/plusmap/undist_l plumbing internally.
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

(** (Q⊸Q) ⊗ ((Q⊸Q) ⊗ (Bool ⊗ Q))  — right associated *)
let input_ty = qq_ty ** (qq_ty ** bq_ty)

(* ========================================================================= *)
(* Abstract QSwitch as a Lambda term                                          *)
(* ========================================================================= *)

(** Approach: structural rearrangement + ocase_hom.

    The input f ⊗ (g ⊗ (b ⊗ x)) is rearranged to b ⊗ (f ⊗ (g ⊗ x))
    using structural isomorphisms (assoc, twist — all 0 gates).
    Then twist converts Bool⊗Γ to Γ⊗Bool for ocase_hom's G⊗(A+B) convention.
    ocase_hom handles dist_r/plusmap/undist_l internally.

    NO destructuring, NO re-pairing, NO split witnesses in the body.
    The only splits are inside the branches (inherent to function application).

    Branch: Γ⊗I → I⊗Q where Γ = (Q⊸Q) ⊗ ((Q⊸Q) ⊗ Q)
      let (payload, tag) = input in      -- payload:Γ, tag:I
      let (f, gx) = payload in           -- f:Q⊸Q, gx:(Q⊸Q)⊗Q
      let (g, x) = gx in                 -- g:Q⊸Q, x:Q
      (tag, f(g(x)))                     -- for left branch
      (tag, g(f(x)))                     -- for right branch
*)

let abstract_qswitch : (unit, [`Lolli of _ * _]) oterm =
  let gx_ty = qq_ty ** q in         (* (Q⊸Q) ⊗ Q *)
  let payload_ty = qq_ty ** gx_ty in (* (Q⊸Q) ⊗ ((Q⊸Q) ⊗ Q) = Γ *)
  let gi_ty = payload_ty ** one in   (* Γ ⊗ I — branch input after dist_r *)

  (* Structural rearrangement (all 0 gates):
     f ⊗ (g ⊗ (b ⊗ x)) → b ⊗ (f ⊗ (g ⊗ x))

     Step 1: swap g and b inside the inner tensor
       f ⊗ (g ⊗ (b ⊗ x)) → f ⊗ (b ⊗ (g ⊗ x))
     Step 2: swap f and b to bring b to the front
       f ⊗ (b ⊗ (g ⊗ x)) → b ⊗ (f ⊗ (g ⊗ x)) *)
  let rearrange =
    let swap_inner =  (* g ⊗ (b ⊗ x) → b ⊗ (g ⊗ x) *)
      seq0 (assoc_tensor_r qq_ty bool_ty q)
        (seq0 (par0 (twist_tensor qq_ty bool_ty) (id q))
              (assoc_tensor_l bool_ty qq_ty q)) in
    let step1 = par0 (id qq_ty) swap_inner in  (* f ⊗ (...) → f ⊗ (b ⊗ gx) *)
    let swap_outer =  (* f ⊗ (b ⊗ gx) → b ⊗ (f ⊗ gx) = b ⊗ Γ *)
      seq0 (assoc_tensor_r qq_ty bool_ty gx_ty)
        (seq0 (par0 (twist_tensor qq_ty bool_ty) (id gx_ty))
              (assoc_tensor_l bool_ty qq_ty gx_ty)) in
    seq0 step1 swap_outer  (* input_ty → Bool ⊗ Γ *)
  in

  (* Left branch (b=0): CLOSED morphism Γ⊗I → I⊗Q, apply g then f.
     Context after oletpairs: [payload, tag] → [f, gx, tag] → [g, x, f, tag] *)
  let left_branch =
    oletpair0 "payload" "tag" payload_ty one (oid gi_ty)
      (oletpair "f" "gx" qq_ty gx_ty (ovar "payload" payload_ty)
        (oletpair "g" "x" qq_ty q (ovar "gx" gx_ty)
          (opair (ovar "tag" one)
                 (oapp (ovar "f" qq_ty)
                       (oapp (ovar "g" qq_ty) (ovar "x" q)
                             (SLeft (SRight SNil)))       (* g→left, x→right *)
                       (SRight (SRight (SLeft SNil))))    (* g,x→right, f→left *)
                 (SRight (SRight (SRight (SLeft SNil))))) (* tag→left, rest→right *)
          (SRight (SLeft (SRight SNil))))   (* gx→left, (f,tag)→right *)
        (SLeft (SRight SNil)))             (* payload→left, tag→right *)
  in
  (* Right branch (b=1): CLOSED morphism Γ⊗I → I⊗Q, apply f then g. *)
  let right_branch =
    oletpair0 "payload" "tag" payload_ty one (oid gi_ty)
      (oletpair "f" "gx" qq_ty gx_ty (ovar "payload" payload_ty)
        (oletpair "g" "x" qq_ty q (ovar "gx" gx_ty)
          (opair (ovar "tag" one)
                 (oapp (ovar "g" qq_ty)
                       (oapp (ovar "f" qq_ty) (ovar "x" q)
                             (SRight (SLeft SNil)))       (* x→right, f→left *)
                       (SLeft (SRight (SRight SNil))))    (* g→left, (x,f)→right *)
                 (SRight (SRight (SRight (SLeft SNil))))) (* tag→left, rest→right *)
          (SRight (SLeft (SRight SNil))))
        (SLeft (SRight SNil)))
  in

  (* Pipeline: rearrange → twist → ocase_hom (ALL CLOSED) *)
  let pipeline =
    oseq0 (oembed (seq0 rearrange (twist_tensor bool_ty payload_ty)))
          (ocase_hom one one payload_ty q left_branch right_branch)
  in

  (* Body: just apply the closed pipeline to the input. ONE split. *)
  olam "input" input_ty bq_ty
    (oapp pipeline (ovar "input" input_ty) (SRight SNil))


(* ========================================================================= *)
(* Demo                                                                        *)
(* ========================================================================= *)

let () =
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
  print_endline "The existing meta-level qswitch[H,S] is expected to compile to 6 gates.";
  print_endline "The abstract lambda should compile to a larger circuit";
  print_endline "(it includes the function application overhead).\n";

  let meta_qswitch_hs =
    (* Using case sugar: twist + case_hom with make_branch *)
    let left  = make_branch q one (seq0 gate_s gate_h) in
    let right = make_branch q one (seq0 gate_h gate_s) in
    seq0 (twist_tensor bool_ty q) (case_hom one one q q left right)
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
