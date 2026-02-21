(** exp(i*theta*Twist) E2E Demo in Linear GADT

    Full pipeline: OCaml Linear DSL -> Bridge -> Python compile -> Circuit

    Mirrors the Python exp_twist_demo.py. Verifies:
    1. TwistTen(Q,Q) compiles (sanity check)
    2. exp_i(pi/4, twist) compiles via direct unitary synthesis
    3. exp_i(pi/4, twist) ; exp_i(pi/4, twist) composition
    4. Composition law: exp(pi/4);exp(pi/4) = exp(pi/2) (key verification)
    5. TwistPlus: exp_i(pi/4, twist_plus I I) compiles
*)

open Qpl_surface
open Linear

let pi = Float.pi

let tests_run = ref 0
let tests_passed = ref 0

let banner title =
  print_endline "";
  print_endline (String.make 74 '=');
  Printf.printf "  %s\n" title;
  print_endline (String.make 74 '=')

let compile_and_report name term =
  Printf.printf "\n%s:\n" name;
  match Bridge.compile_show term with
  | Bridge.CompileOk _ -> true
  | Bridge.CompileError err ->
      Printf.printf "  FAILED: %s\n" err;
      false

let check_eq_circ name term1 term2 =
  Printf.printf "\n%s:\n" name;
  incr tests_run;
  match Bridge.eq_circ term1 term2 with
  | Bridge.EqCircOk (true, fidelity) ->
      Printf.printf "  EQUAL (fidelity=%.6f)\n" fidelity;
      incr tests_passed;
      true
  | Bridge.EqCircOk (false, fidelity) ->
      Printf.printf "  NOT EQUAL (fidelity=%.6f)\n" fidelity;
      false
  | Bridge.EqCircError err ->
      Printf.printf "  ERROR: %s\n" err;
      false

(* ========================================================================= *)
(* Type and term definitions                                                  *)
(* ========================================================================= *)

(** TwistTen(Q, Q) : (Q tensor Q) -> (Q tensor Q) *)
let twist_qq = twist_tensor q q

(** exp_i(pi/4, twist) *)
let exp_twist_single = exp_i (pi /. 4.0) twist_qq

(** exp_i(pi/4, twist) ; exp_i(pi/4, twist) *)
let exp_twist_composed = seq0 exp_twist_single exp_twist_single

(** exp_i(pi/2, twist) -- direct *)
let exp_twist_half_pi = exp_i (pi /. 2.0) twist_qq

(** TwistPlus(I, I) : (I + I) -> (I + I) *)
let twist_plus_ii = twist_plus one one

(** exp_i(pi/4, twist_plus I I) *)
let exp_twist_plus = exp_i (pi /. 4.0) twist_plus_ii

(* ========================================================================= *)
(* Demo sections                                                              *)
(* ========================================================================= *)

let () =
  banner "exp(i*theta*Twist) E2E Demo";
  print_endline "";
  print_endline "Full pipeline: OCaml Linear DSL -> Bridge -> Python compile -> Circuit";
  print_endline "Mirrors the Python exp_twist_demo.py verification.";

  (* --- Part 1: TwistTen(Q,Q) sanity check --- *)
  banner "Part 1: TwistTen(Q,Q) Compilation (sanity check)";
  let twist_term = emit twist_qq in
  let ok1 = compile_and_report "TwistTen(Q,Q)" twist_term in
  incr tests_run;
  if ok1 then begin
    incr tests_passed;
    (* Self-equality sanity *)
    let _ = check_eq_circ "eq_circ(twist, twist) [sanity]" twist_term twist_term in
    ()
  end;

  (* --- Part 2: exp_i(pi/4, twist) --- *)
  banner "Part 2: exp_i(pi/4, TwistTen(Q,Q))";
  let exp_single_term = emit exp_twist_single in
  let ok2 = compile_and_report "exp_i(pi/4, twist)" exp_single_term in
  incr tests_run;
  if ok2 then incr tests_passed;

  (* --- Part 3: exp_i(pi/4, twist) ; exp_i(pi/4, twist) --- *)
  banner "Part 3: exp_i(pi/4, twist) ; exp_i(pi/4, twist) Composition";
  let composed_term = emit exp_twist_composed in
  let ok3 = compile_and_report "exp(pi/4);exp(pi/4) composed" composed_term in
  incr tests_run;
  if ok3 then incr tests_passed;

  (* --- Part 4: Composition law --- *)
  banner "Part 4: Composition Law";
  print_endline "  Verify: exp(pi/4);exp(pi/4) = exp(pi/2)";
  let half_pi_term = emit exp_twist_half_pi in
  let ok4a = compile_and_report "exp_i(pi/2, twist) [direct]" half_pi_term in
  incr tests_run;
  if ok4a then incr tests_passed;
  let _ = check_eq_circ
    "eq_circ(exp(pi/4);exp(pi/4), exp(pi/2)) [composition law]"
    composed_term half_pi_term in

  (* --- Part 5: TwistPlus --- *)
  banner "Part 5: exp_i(pi/4, TwistPlus(I, I))";
  let exp_plus_term = emit exp_twist_plus in
  let ok5 = compile_and_report "exp_i(pi/4, twist_plus I I)" exp_plus_term in
  incr tests_run;
  if ok5 then incr tests_passed;

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
