(** Exponentials of branch-swaps on T = Q + (Q + Q).

    T = Q1 + (Q2 + Q3) with right association (3 leaf summands of width 1).
    Tag width = ceil(log2(3)) = 2; payload width = 1; total = 3 qubits.

    Let
      swap_12 = assoc_plus_r ; (twist_plus q q  +  id q) ; assoc_plus_l
      swap_23 = id q  +  twist_plus q q                              (via omap0)

    Each is an involution on T (square = id). We then form
      E12(theta) = exp_i(theta, swap_12)
      E23(theta) = exp_i(theta, swap_23)

    The demo compiles each at theta = pi/4 (and pi/2), then checks
      (a) composition law: E_ij(pi/4) ; E_ij(pi/4) = E_ij(pi/2)
      (b) non-commutation:  E12 ; E23  =/=  E23 ; E12
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
  | Bridge.CompileOk (_, size) ->
      Printf.printf "  circuit_size = %d\n" size;
      true
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

let check_neq_circ name term1 term2 =
  Printf.printf "\n%s:\n" name;
  incr tests_run;
  match Bridge.eq_circ term1 term2 with
  | Bridge.EqCircOk (false, fidelity) ->
      Printf.printf "  NOT EQUAL as expected (fidelity=%.6f)\n" fidelity;
      incr tests_passed;
      true
  | Bridge.EqCircOk (true, fidelity) ->
      Printf.printf "  UNEXPECTEDLY EQUAL (fidelity=%.6f)\n" fidelity;
      false
  | Bridge.EqCircError err ->
      Printf.printf "  ERROR: %s\n" err;
      false

(* ========================================================================= *)
(* Type and term definitions                                                  *)
(* ========================================================================= *)

(* T = Q + (Q + Q) -- right associated *)
let qq_sum   = q ++ q                (* Q + Q     *)
let _t_ty    = q ++ qq_sum           (* Q + (Q+Q) -- documentation only *)

(* swap_12 : T -> T
   re-associate to (Q+Q)+Q, twist the inner pair, re-associate back. *)
let swap_12 =
  seq0 (assoc_plus_r q q q)
    (seq0 (omap0 qq_sum q (twist_plus q q) (id q))
          (assoc_plus_l q q q))

(* swap_23 : T -> T
   leave the outer Q1 alone; twist the inner (Q+Q). *)
let swap_23 = omap0 q qq_sum (id q) (twist_plus q q)

(* Exponentials *)
let e12_pi4   = exp_i (pi /. 4.0) swap_12
let e23_pi4   = exp_i (pi /. 4.0) swap_23
let e12_pi2   = exp_i (pi /. 2.0) swap_12
let e23_pi2   = exp_i (pi /. 2.0) swap_23

(* Compositions *)
let e12_then_e12 = seq0 e12_pi4 e12_pi4
let e23_then_e23 = seq0 e23_pi4 e23_pi4
let e12_then_e23 = seq0 e12_pi4 e23_pi4
let e23_then_e12 = seq0 e23_pi4 e12_pi4

(* ========================================================================= *)
(* Demo sections                                                              *)
(* ========================================================================= *)

let () =
  banner "exp_i on branch-swaps of T = Q + (Q + Q)";
  print_endline "";
  print_endline "T has 3 leaf summands of width 1 -> width(T) = 2 tag + 1 payload = 3 qubits.";

  (* --- Part 1: swap_12 and swap_23 as raw involutions --- *)
  banner "Part 1: swap_12 and swap_23 (raw involutions)";
  let ok1a = compile_and_report "swap_12 = assoc_r ; (twist+id) ; assoc_l" (emit swap_12) in
  incr tests_run; if ok1a then incr tests_passed;
  let ok1b = compile_and_report "swap_23 = id + twist (omap0)" (emit swap_23) in
  incr tests_run; if ok1b then incr tests_passed;

  (* --- Part 2: E12(pi/4) and E23(pi/4) --- *)
  banner "Part 2: E12(pi/4) and E23(pi/4)";
  let e12_term = emit e12_pi4 in
  let e23_term = emit e23_pi4 in
  let ok2a = compile_and_report "E12(pi/4) = exp_i(pi/4, swap_12)" e12_term in
  incr tests_run; if ok2a then incr tests_passed;
  let ok2b = compile_and_report "E23(pi/4) = exp_i(pi/4, swap_23)" e23_term in
  incr tests_run; if ok2b then incr tests_passed;

  (* --- Part 3: Composition law --- *)
  banner "Part 3: Composition law  E(pi/4);E(pi/4) = E(pi/2)";
  let _ = compile_and_report "E12(pi/2) [direct]" (emit e12_pi2) in
  let _ = compile_and_report "E23(pi/2) [direct]" (emit e23_pi2) in
  let _ = check_eq_circ
    "E12(pi/4);E12(pi/4)  =  E12(pi/2)"
    (emit e12_then_e12) (emit e12_pi2) in
  let _ = check_eq_circ
    "E23(pi/4);E23(pi/4)  =  E23(pi/2)"
    (emit e23_then_e23) (emit e23_pi2) in

  (* --- Part 4: Non-commutation --- *)
  banner "Part 4: E12 and E23 do NOT commute";
  print_endline "  (swap_12 and swap_23 generate S_3; their exponentials";
  print_endline "   inherit the non-abelian structure.)";
  let _ = check_neq_circ
    "E12(pi/4);E23(pi/4)  =/=  E23(pi/4);E12(pi/4)"
    (emit e12_then_e23) (emit e23_then_e12) in

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
