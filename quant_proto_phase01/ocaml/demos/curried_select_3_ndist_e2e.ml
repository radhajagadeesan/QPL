(** Fully Curried select_3 using n-ary dist/factor (Option 3)

    Implements the user's formula using the n-ary distributivity primitives
    [n_dist] and [n_factor], which are wire-level identities. This avoids
    the asymmetric-binary tag-rearrangement overhead that the binary-dist
    version had — the resulting circuit matches meta [control z_3] exactly.

      select_{n,A} := λf_0. … λf_{n-1}. λp.
        n_factor((⊕^n (id_b ⊗ f_i)) (n_dist(p)))

    For Z_3 with summand_tys = [|I; I; I|], b = I, A = Q:
      - n_dist  : Z_3 ⊗ Q ⊸ ⊕^3 (I ⊗ Q)     [wire-level identity]
      - plusmap : ⊕^3 (I ⊗ Q) ⊸ ⊕^3 (I ⊗ Q)  [o_n_plusmap with 3 branches]
      - n_factor: ⊕^3 (I ⊗ Q) ⊸ Z_3 ⊗ Q     [wire-level identity]
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
let ia_ty = one ** q
(* Z_3 = I + (I + I), right-associated nested binary. The wire encoding is
   the flat 3-leaf form (2 tag bits + 0 payload); the OCaml type is just a
   convenient way to express n=3 at the type level. *)
let z3_ty = one ++ (one ++ one)
let z3a_ty = z3_ty ** q

let h_value = olam "hx" q q (oapp (oembed gate_h) (ovar "hx" q) (SRight SNil))
let s_value = olam "sy" q q (oapp (oembed gate_s) (ovar "sy" q) (SRight SNil))
let t_value = olam "tz" q q (oapp (oembed gate_t) (ovar "tz" q) (SRight SNil))

(** Per-branch term applying f_name to the Q part of an I⊗Q input. *)
let apply_f_branch f_name =
  oletpair "i" "a" one q (oid ia_ty)
    (opair (ovar "i" one)
           (oapp (ovar f_name qq_ty) (ovar "a" q) (SRight (SLeft SNil)))
           (SLeft (SRight (SRight SNil))))
    (SRight SNil)

(** The n-ary plusmap using o_n_plusmap (3 branch-local contexts, covered
    exactly by the partition witness). *)
let nary_plusmap_3 =
  o_n_plusmap ia_ty
    (BCons (ia_ty, apply_f_branch "f0",
     BCons (ia_ty, apply_f_branch "f1",
     BCons (ia_ty, apply_f_branch "f2", BNil))))
    (PCons (SLeft (SRight (SRight SNil)),
     PCons (SLeft (SRight SNil),
     PLast)))

(** Fully curried select_3.

    Note on identity coercion: [n_dist] and [n_factor] are wire-level
    identities but at the OCaml type level they bridge the "binary nested"
    and "flat n-ary" representations. We use them existentially typed —
    the type signature accommodates the structural mismatch. *)
let abstract_select_3 =
  (* Body context inside innermost lambda: [p, f_2, f_1, f_0]. *)
  let body =
    let summand_tys = [| one; one; one |] in
    let dist = oembed (n_dist summand_tys q) in
    let factor = oembed (n_factor summand_tys q) in
    let pipeline =
      let dist_then_pm =
        oseq dist nary_plusmap_3 (SRight (SRight (SRight SNil)))
      in
      oseq dist_then_pm factor (SLeft (SLeft (SLeft SNil)))
    in
    oapp pipeline (ovar "p" z3a_ty) (SRight (SLeft (SLeft (SLeft SNil))))
  in
  olam "f0" qq_ty (qq_ty -@ (qq_ty -@ (z3a_ty -@ z3a_ty)))
    (olam "f1" qq_ty (qq_ty -@ (z3a_ty -@ z3a_ty))
       (olam "f2" qq_ty (z3a_ty -@ z3a_ty)
          (olam "p" z3a_ty z3a_ty body)))


let () =
  banner "FULLY CURRIED select_3 via n_dist / n_factor";
  print_endline "\nλf_0. λf_1. λf_2. λp. n_factor ⊕(id_b⊗f_i) n_dist(p)\n";

  banner "Part 1: Compile abstract select_3";
  incr tests_run;
  (match Bridge.compile_show (emit_oterm abstract_select_3) with
   | Bridge.CompileOk _ ->
       Printf.printf "Abstract compilation SUCCESS!\n";
       incr tests_passed
   | Bridge.CompileError err -> Printf.printf "FAILED: %s\n" err);

  banner "Part 2: Instantiate with H, S, T (3 nested Apply)";
  let bridge_abs = emit_oterm abstract_select_3 in
  let bridge_h = emit_oterm h_value in
  let bridge_s = emit_oterm s_value in
  let bridge_t = emit_oterm t_value in
  let applied_hst =
    Bridge.TApply (
      Bridge.TApply (
        Bridge.TApply (bridge_abs, bridge_h),
        bridge_s),
      bridge_t)
  in
  incr tests_run;
  Printf.printf "Apply(Apply(Apply(select_3, H), S), T):\n";
  (match Bridge.compile_show applied_hst with
   | Bridge.CompileOk _ ->
       Printf.printf "Instantiation SUCCESS!\n";
       incr tests_passed
   | Bridge.CompileError err -> Printf.printf "FAILED: %s\n" err);

  banner "Part 3: Verify against meta control z_3";
  let z3_dt = datatype ~name:"Z3" ~arity:3 ~labels:["0";"1";"2"] ~ops:[] in
  let meta_3 = control z3_dt q [| gate_h; gate_s; gate_t |] in
  Printf.printf "Meta control z_3 q [|H; S; T|]:\n";
  (match Bridge.compile_show (emit meta_3) with
   | Bridge.CompileOk _ -> ()
   | Bridge.CompileError err -> Printf.printf "FAILED: %s\n" err);

  incr tests_run;
  (match Bridge.eq_circ_partial applied_hst (emit meta_3) with
   | Bridge.EqCircOk (true, fidelity) ->
       Printf.printf "  ✓ curried select_3(H,S,T) = control z_3 [|H;S;T|] (fidelity=%.6f)\n" fidelity;
       incr tests_passed
   | Bridge.EqCircOk (false, fidelity) ->
       Printf.printf "  ✗ mismatch (fidelity=%.6f)\n" fidelity
   | Bridge.EqCircError err ->
       Printf.printf "  ✗ ERROR: %s\n" err);

  banner "Summary";
  Printf.printf "\n  Tests: %d/%d passed\n" !tests_passed !tests_run;
  if !tests_passed = !tests_run then
    print_endline "\n  ALL TESTS PASSED"
  else begin
    Printf.printf "\n  %d TESTS FAILED\n" (!tests_run - !tests_passed);
    exit 1
  end;
  print_endline ""
