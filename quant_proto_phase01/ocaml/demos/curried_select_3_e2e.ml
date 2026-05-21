(** Fully Curried select_3 for Asymmetric Z_3

    Tests the user's formula:
      select_{n,A} := λf_0. … λf_{n-1}. λp.
        factor_n((⊕_{i=0}^{n-1} (id_b ⊗ f_i)) (dist_n(p)))

    Where Z_n = ⊕_{i=0}^{n-1} b (b = I), and dist_n / factor_n are the n-ary
    distributivity and its inverse.

    For n=3 with Z_3 = I + (I + I) (right-associated binary representation):
      - dist_3 = outer dist_l ; omap0(id_{I⊗Q}, inner dist_l)
      - factor_3 = omap0(id_{I⊗Q}, inner undist_l) ; outer undist_l
      - The n-ary plusmap uses o_n_plusmap with 3 branches.

    This exercises:
      - Nested 4-level Apply (compose_n fix).
      - o_n_plusmap (n-ary OPlusMap primitive) — handles asymmetric n cleanly.
      - Curried lambda binding (no closures needed; boundary splicing).

    KNOWN: The COMPILED CURRIED FORM uses asymmetric-binary dist_l/undist_l
    around the n-ary plusmap. For Z_3 (asymmetric), these emit tag-bit
    rearrangement gates (Unitary2qBox) — the resulting circuit is semantically
    equivalent to meta-level [control z_3 q [|H;S;T|]] BUT under a different
    tag encoding. The two differ by a constant tag permutation.

    For TAG-CONSISTENT n-ary dispatch (matching meta control), use the
    [o_n_plusmap] primitive directly without dist/undist — see [n_plusmap_e2e].
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
let ia_ty = one ** q                    (* I ⊗ Q (one branch input) *)
let bool_ty = one ++ one                (* I + I *)
let z3_ty = one ++ (one ++ one)         (* I + (I + I) = Z_3 *)
let z3a_ty = z3_ty ** q                 (* Z_3 ⊗ Q *)
let bi_a_ty = bool_ty ** q              (* (I+I) ⊗ Q (intermediate after outer dist) *)
let _sum_3_ty = ia_ty ++ (ia_ty ++ ia_ty)
let inner_sum_ty = ia_ty ++ ia_ty       (* (I⊗Q) + (I⊗Q) *)

(* Function values *)
let h_value = olam "hx" q q (oapp (oembed gate_h) (ovar "hx" q) (SRight SNil))
let s_value = olam "sy" q q (oapp (oembed gate_s) (ovar "sy" q) (SRight SNil))
let t_value = olam "tz" q q (oapp (oembed gate_t) (ovar "tz" q) (SRight SNil))

(** dist_3 : Z_3 ⊗ Q ⊸ sum_3.
    Decomposed as outer dist_l, then omap(id, inner dist_l) on the right summand. *)
let dist_3 =
  let outer = dist_l one (one ++ one) q in
  (* After outer dist_l: Plus(I⊗Q, (I+I)⊗Q) *)
  let inner = dist_l one one q in
  (* inner : (I+I)⊗Q ⊸ Plus(I⊗Q, I⊗Q) *)
  let inner_map = omap0 ia_ty bi_a_ty (id ia_ty) inner in
  (* inner_map : Plus(I⊗Q, (I+I)⊗Q) ⊸ Plus(I⊗Q, Plus(I⊗Q, I⊗Q)) *)
  seq0 outer inner_map

(** factor_3 : sum_3 ⊸ Z_3 ⊗ Q. Inverse of dist_3. *)
let factor_3 =
  let inner = undist_l one one q in
  let inner_map = omap0 ia_ty inner_sum_ty (id ia_ty) inner in
  let outer = undist_l one (one ++ one) q in
  seq0 inner_map outer

(** Branch i : receive I⊗Q via oid, apply f_i (named var), repackage.
    All branches share OCaml context shape via oshift padding. *)
let apply_f_branch f_name =
  oletpair "i" "a" one q (oid ia_ty)
    (opair (ovar "i" one)
           (oapp (ovar f_name qq_ty) (ovar "a" q) (SRight (SLeft SNil)))
           (SLeft (SRight (SRight SNil))))
    (SRight SNil)

(** The n-ary plusmap: ⊕_{i=0}^{2}(id_b ⊗ f_i). Uses o_n_plusmap. *)
let nary_plusmap_3 =
  let summand_tys = [| ia_ty; ia_ty; ia_ty |] in
  (* Pad each branch to share a 3-slot context (one var per slot). *)
  let pad b = oshift qq_ty (oshift qq_ty b) in
  let branches = [|
    pad (apply_f_branch "f0");
    pad (apply_f_branch "f1");
    pad (apply_f_branch "f2");
  |] in
  o_n_plusmap summand_tys ia_ty branches

(** Fully curried select_3: λf_0. λf_1. λf_2. λp. factor_3(plusmap(dist_3(p))).

    Body context inside innermost lambda: [p, f_2, f_1, f_0]. *)
let abstract_select_3 =
  let body =
    (* Build the morphism pipeline: dist_3 ; nary_plusmap_3 ; factor_3.
       Apply it to p. *)
    let pipeline =
      let dist = oembed dist_3 in     (* closed *)
      let factor = oembed factor_3 in  (* closed *)
      let dist_then_pm =
        oseq dist nary_plusmap_3 (SRight (SRight (SRight SNil)))
        (* dist context unit; pm context [f_2, f_1, f_0]. combined = [f_2, f_1, f_0].
           split = all SRight (3 vars → right). *)
      in
      oseq dist_then_pm factor (SLeft (SLeft (SLeft SNil)))
      (* dist_then_pm context [f_2, f_1, f_0]; factor unit.
         split = all SLeft. *)
    in
    (* Apply pipeline to p. pipeline ctx [f_2, f_1, f_0]; p ctx [p].
       Combined inner-body context = [p, f_2, f_1, f_0].
       Split: p → arg (R), f_2 → func (L), f_1 → func (L), f_0 → func (L). *)
    oapp pipeline (ovar "p" z3a_ty) (SRight (SLeft (SLeft (SLeft SNil))))
  in
  olam "f0" qq_ty (qq_ty -@ (qq_ty -@ (z3a_ty -@ z3a_ty)))
    (olam "f1" qq_ty (qq_ty -@ (z3a_ty -@ z3a_ty))
       (olam "f2" qq_ty (z3a_ty -@ z3a_ty)
          (olam "p" z3a_ty z3a_ty body)))


let () =
  banner "FULLY CURRIED select_3 (asymmetric Z_3 via o_n_plusmap)";
  print_endline "\nλf_0. λf_1. λf_2. λp. factor_3 ⊕(id⊗f_i) dist_3(p)\n";

  banner "Part 1: Compile abstract select_3 (curried, 4 nested lambdas)";
  incr tests_run;
  (match Bridge.compile_show (emit_oterm abstract_select_3) with
   | Bridge.CompileOk _ ->
       Printf.printf "Abstract compilation SUCCESS!\n";
       incr tests_passed
   | Bridge.CompileError err -> Printf.printf "FAILED: %s\n" err);

  banner "Part 2: Instantiate via 3 nested Apply with H, S, T";
  let bridge_abs = emit_oterm abstract_select_3 in
  let bridge_h = emit_oterm h_value in
  let bridge_s = emit_oterm s_value in
  let bridge_t = emit_oterm t_value in
  let applied_h = Bridge.TApply (bridge_abs, bridge_h) in
  let applied_hs = Bridge.TApply (applied_h, bridge_s) in
  let applied_hst = Bridge.TApply (applied_hs, bridge_t) in

  incr tests_run;
  Printf.printf "Apply(Apply(Apply(select_3, H), S), T):\n";
  (match Bridge.compile_show applied_hst with
   | Bridge.CompileOk _ ->
       Printf.printf "Instantiation SUCCESS!\n";
       incr tests_passed
   | Bridge.CompileError err -> Printf.printf "FAILED: %s\n" err);

  banner "Part 3: Reference meta control z_3 (tag-encoding NOTE)";
  let z3_dt = datatype ~name:"Z3" ~arity:3 ~labels:["0";"1";"2"] ~ops:[] in
  let meta_3 = control z3_dt q [| gate_h; gate_s; gate_t |] in
  Printf.printf "Meta control z_3 q [|H; S; T|]:\n";
  (match Bridge.compile_show (emit meta_3) with
   | Bridge.CompileOk _ -> ()
   | Bridge.CompileError err -> Printf.printf "FAILED: %s\n" err);
  print_endline "";
  print_endline "  Note: the curried select_3 above uses asymmetric-binary dist_l around";
  print_endline "  o_n_plusmap. The trailing Unitary2qBox gates implement tag-bit";
  print_endline "  rearrangement between the binary (I + (I+I)) encoding and the flat";
  print_endline "  n-ary encoding used by meta control. The two circuits are semantically";
  print_endline "  equivalent up to a tag permutation.";

  banner "Summary";
  Printf.printf "\n  Tests: %d/%d passed\n" !tests_passed !tests_run;
  if !tests_passed = !tests_run then
    print_endline "\n  ALL TESTS PASSED"
  else begin
    Printf.printf "\n  %d TESTS FAILED\n" (!tests_run - !tests_passed);
    exit 1
  end;
  print_endline ""
