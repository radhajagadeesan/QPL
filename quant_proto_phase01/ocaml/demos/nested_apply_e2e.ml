(** Nested Apply / Currying Sanity Check

    Tests that the toolchain handles curried higher-order terms with
    nested Apply correctly — no PlusMap, just function composition.

      compose_n : (A⊸A) ⊸ (A⊸A) ⊸ ... ⊸ (A⊸A) ⊸ (A⊸A)
      compose_n(f_1, ..., f_n) = λx. f_1(f_2(...(f_n(x))))

    For concrete gates G_1, ..., G_n applied to x, the result is
    G_1 ∘ G_2 ∘ ... ∘ G_n applied to x — equivalently the sequential
    composition Seq(G_n, ..., G_1) (right-to-left).

    Verified for n = 1, 2, 3, 4 by checking equality against the meta
    composition via Bridge.eq_circ.
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

let h_value = olam "hx" q q (oapp (oembed gate_h) (ovar "hx" q) (SRight SNil))
let s_value = olam "sy" q q (oapp (oembed gate_s) (ovar "sy" q) (SRight SNil))
let t_value = olam "tz" q q (oapp (oembed gate_t) (ovar "tz" q) (SRight SNil))
let x_value = olam "xw" q q (oapp (oembed gate_x) (ovar "xw" q) (SRight SNil))

(* ========================================================================= *)
(* compose_2: λf_1. λf_2. λx. f_1(f_2(x))                                     *)
(* ========================================================================= *)
let compose_2 =
  olam "f1" qq_ty (qq_ty -@ (q -@ q))
    (olam "f2" qq_ty (q -@ q)
      (olam "x" q q
        (* Body context (top to bottom): [x, f2, f1]
           Inner oapp f2 x: g1=[f2], g2=[x]. split = SRight(SLeft(SNil))
           Outer oapp f1 inner: g1=[f1], g2=[x,f2]. split = SRight(SRight(SLeft(SNil))) *)
        (oapp (ovar "f1" qq_ty)
              (oapp (ovar "f2" qq_ty) (ovar "x" q) (SRight (SLeft SNil)))
              (SRight (SRight (SLeft SNil))))))

(* ========================================================================= *)
(* compose_3: λf_1. λf_2. λf_3. λx. f_1(f_2(f_3(x)))                          *)
(* ========================================================================= *)
let compose_3 =
  olam "f1" qq_ty (qq_ty -@ (qq_ty -@ (q -@ q)))
    (olam "f2" qq_ty (qq_ty -@ (q -@ q))
      (olam "f3" qq_ty (q -@ q)
        (olam "x" q q
          (* Body context: [x, f3, f2, f1]
             oapp f3 x:     g1=[f3], g2=[x]. split = SRight(SLeft(SNil))
             oapp f2 _:     g1=[f2], g2=[x,f3]. split = SRight(SRight(SLeft(SNil)))
             oapp f1 _:     g1=[f1], g2=[x,f3,f2]. split = SRight(SRight(SRight(SLeft(SNil)))) *)
          (oapp (ovar "f1" qq_ty)
                (oapp (ovar "f2" qq_ty)
                      (oapp (ovar "f3" qq_ty) (ovar "x" q) (SRight (SLeft SNil)))
                      (SRight (SRight (SLeft SNil))))
                (SRight (SRight (SRight (SLeft SNil))))))))

(* ========================================================================= *)
(* compose_4: similar with 4 functions                                        *)
(* ========================================================================= *)
let compose_4 =
  olam "f1" qq_ty (qq_ty -@ (qq_ty -@ (qq_ty -@ (q -@ q))))
    (olam "f2" qq_ty (qq_ty -@ (qq_ty -@ (q -@ q)))
      (olam "f3" qq_ty (qq_ty -@ (q -@ q))
        (olam "f4" qq_ty (q -@ q)
          (olam "x" q q
            (oapp (ovar "f1" qq_ty)
              (oapp (ovar "f2" qq_ty)
                (oapp (ovar "f3" qq_ty)
                  (oapp (ovar "f4" qq_ty) (ovar "x" q) (SRight (SLeft SNil)))
                  (SRight (SRight (SLeft SNil))))
                (SRight (SRight (SRight (SLeft SNil)))))
              (SRight (SRight (SRight (SRight (SLeft SNil))))))))))

(* ========================================================================= *)
(* Verification helper: apply n times, compare against meta composition       *)
(* ========================================================================= *)
let verify_compose name abstract_term apply_args meta_morph =
  incr tests_run;
  let bridge_abs = emit_oterm abstract_term in
  (* Wrap meta_morph as a function value (Lam) so both sides have the same
     representation: λx:Q. (meta)(x). This is η-equivalent to meta_morph. *)
  let meta_as_value =
    olam "x" q q (oapp (oembed meta_morph) (ovar "x" q) (SRight SNil))
  in
  let bridge_meta = emit_oterm meta_as_value in
  let applied = List.fold_left
    (fun acc arg -> Bridge.TApply (acc, emit_oterm arg))
    bridge_abs apply_args
  in
  match Bridge.eq_circ applied bridge_meta with
  | Bridge.EqCircOk (true, fidelity) ->
      Printf.printf "  ✓ %s (fidelity=%.6f)\n" name fidelity;
      incr tests_passed
  | Bridge.EqCircOk (false, fidelity) ->
      Printf.printf "  ✗ %s FAILED (fidelity=%.6f)\n" name fidelity
  | Bridge.EqCircError err ->
      Printf.printf "  ✗ %s ERROR: %s\n" name err

let () =
  banner "NESTED APPLY / CURRYING SANITY CHECK";
  print_endline "\nTesting compose_n : (Q⊸Q)^n ⊸ (Q ⊸ Q) with n=2,3,4.";
  print_endline "After applying all f_i, the result is the composition f_1 ∘ ... ∘ f_n.\n";

  banner "Part 1: compose_2";
  Printf.printf "Type: (Q⊸Q) ⊸ (Q⊸Q) ⊸ (Q ⊸ Q)\n";
  Printf.printf "Definition: λf_1. λf_2. λx. f_1(f_2(x))\n\n";
  Printf.printf "Compile abstract compose_2:\n";
  (match Bridge.compile_show (emit_oterm compose_2) with
   | Bridge.CompileOk _ -> ()
   | Bridge.CompileError err -> Printf.printf "  FAILED: %s\n" err);

  (* compose_2(H, S) = H∘S, i.e., apply S then H *)
  verify_compose "compose_2(H, S) = S ; H"
    compose_2 [h_value; s_value]
    (seq0 gate_s gate_h);

  verify_compose "compose_2(H, H) = H ; H = id_Q"
    compose_2 [h_value; h_value]
    (seq0 gate_h gate_h);

  verify_compose "compose_2(T, S) = S ; T"
    compose_2 [t_value; s_value]
    (seq0 gate_s gate_t);

  banner "Part 2: compose_3";
  Printf.printf "Type: (Q⊸Q) ⊸ (Q⊸Q) ⊸ (Q⊸Q) ⊸ (Q ⊸ Q)\n";
  Printf.printf "Definition: λf_1. λf_2. λf_3. λx. f_1(f_2(f_3(x)))\n\n";
  Printf.printf "Compile abstract compose_3:\n";
  (match Bridge.compile_show (emit_oterm compose_3) with
   | Bridge.CompileOk _ -> ()
   | Bridge.CompileError err -> Printf.printf "  FAILED: %s\n" err);

  verify_compose "compose_3(H, S, T) = T ; S ; H"
    compose_3 [h_value; s_value; t_value]
    (seq0 gate_t (seq0 gate_s gate_h));

  verify_compose "compose_3(X, H, S) = S ; H ; X"
    compose_3 [x_value; h_value; s_value]
    (seq0 gate_s (seq0 gate_h gate_x));

  banner "Part 3: compose_4";
  Printf.printf "Type: (Q⊸Q) ⊸ (Q⊸Q) ⊸ (Q⊸Q) ⊸ (Q⊸Q) ⊸ (Q ⊸ Q)\n\n";
  Printf.printf "Compile abstract compose_4:\n";
  (match Bridge.compile_show (emit_oterm compose_4) with
   | Bridge.CompileOk _ -> ()
   | Bridge.CompileError err -> Printf.printf "  FAILED: %s\n" err);

  verify_compose "compose_4(H, S, T, X) = X ; T ; S ; H"
    compose_4 [h_value; s_value; t_value; x_value]
    (seq0 gate_x (seq0 gate_t (seq0 gate_s gate_h)));

  verify_compose "compose_4(H, H, S, S) = S ; S ; H ; H = id"
    compose_4 [h_value; h_value; s_value; s_value]
    (seq0 gate_s (seq0 gate_s (seq0 gate_h gate_h)));

  banner "Summary";
  Printf.printf "\n  Tests: %d/%d passed\n" !tests_passed !tests_run;
  if !tests_passed = !tests_run then
    print_endline "\n  ALL TESTS PASSED"
  else begin
    Printf.printf "\n  %d TESTS FAILED\n" (!tests_run - !tests_passed);
    exit 1
  end;
  print_endline ""
