(** End-to-end integration tests for the Python bridge.

    These tests require the Python venv to be set up.
    Run with: dune test
*)

open Qpl_surface

(* Set project root for bridge *)
let () =
  Bridge.set_project_root "/home/rjagadee/projects/QPL/quant_proto_phase01"

(* Test: TwistPlus is involutive *)
let test_twist_plus_involution () =
  print_endline "=== Testing TwistPlus involution (via Python) ===";

  let swap = Bridge.TTwistPlus (Rep.var 0, Rep.var 1) in

  match Qpl.check_involution swap with
  | Qpl.Involutive perm ->
    print_endline "✓ TwistPlus is involutive";
    print_endline (Printf.sprintf "  perm.n = %d" perm.n);
    print_endline (Printf.sprintf "  perm.new_to_old = [%s]"
      (String.concat ", " (List.map string_of_int perm.new_to_old)));
    (* Tagged layout: Q + Q has width 3 (1 tag + 1 + 1) *)
    (* Perm = [0, 2, 1]: tag stays at 0, data wires swap *)
    assert (perm.n = 3);
    assert (perm.new_to_old = [0; 2; 1])
  | Qpl.NotInvolutive _ ->
    print_endline "✗ TwistPlus should be involutive!";
    assert false
  | Qpl.CheckError err ->
    print_endline ("✗ Error: " ^ err);
    assert false

(* Test: Identity is involutive *)
let test_identity_involution () =
  print_endline "=== Testing Identity involution (via Python) ===";

  let id_term = Bridge.TId (Rep.plus (Rep.var 0) (Rep.var 1)) in

  match Qpl.check_involution id_term with
  | Qpl.Involutive perm ->
    print_endline "✓ Identity is involutive";
    print_endline (Printf.sprintf "  perm.new_to_old = [%s]"
      (String.concat ", " (List.map string_of_int perm.new_to_old)));
    (* Tagged layout: V0 + V1 has width 3 (1 tag + 1 + 1) *)
    assert (perm.new_to_old = [0; 1; 2])
  | Qpl.NotInvolutive _ ->
    print_endline "✗ Identity should be involutive!";
    assert false
  | Qpl.CheckError err ->
    print_endline ("✗ Error: " ^ err);
    assert false

(* Test: Certified exp_i emission *)
let test_certified_exp_i () =
  print_endline "=== Testing certified exp_i emission ===";

  let pi = 3.14159265358979 in
  let swap = Bridge.TTwistPlus (Rep.var 0, Rep.var 1) in

  match Qpl.exp_i ~theta:(pi /. 7.0) ~j_term:swap ~j_name:"swap" with
  | Ok code ->
    print_endline "✓ exp_i certified successfully";
    print_endline "Generated code:";
    print_endline code
  | Error err ->
    print_endline ("✗ exp_i failed: " ^ err);
    assert false

(* Test: Full Bool swap example from the design docs *)
let test_bool_swap_example () =
  print_endline "=== Testing Bool swap (end-to-end) ===";

  (* Bool[A,B] = F of A | T of B
     swap : Bool[A,B] -> Bool[B,A]
     swap = λx. case x of F(a) => T(a) | T(b) => F(b)

     This elaborates to TwistPlus(A, B) *)

  let swap = Qpl.swap_term () in

  (* 1. Check it's involutive *)
  (match Qpl.check_involution swap with
   | Qpl.Involutive perm ->
     print_endline "✓ Bool.swap is involutive";
     print_endline (Printf.sprintf "  Permutation: [%s]"
       (String.concat ", " (List.map string_of_int perm.new_to_old)))
   | Qpl.NotInvolutive _ ->
     print_endline "✗ Bool.swap should be involutive!";
     assert false
   | Qpl.CheckError err ->
     print_endline ("✗ Error checking Bool.swap: " ^ err);
     assert false);

  (* 2. Emit exp_i(π/7, swap) *)
  let pi = 3.14159265358979 in
  (match Qpl.exp_i ~theta:(pi /. 7.0) ~j_term:swap ~j_name:"Bool.swap" with
   | Ok code ->
     print_endline "✓ exp_i(π/7, Bool.swap) certified";
     print_endline "Generated Python:";
     print_endline code
   | Error err ->
     print_endline ("✗ exp_i failed: " ^ err);
     assert false);

  print_endline ""

(* Run all tests *)
let () =
  print_endline "QPL Bridge Integration Tests";
  print_endline "============================";
  print_endline "";

  test_twist_plus_involution ();
  print_endline "";

  test_identity_involution ();
  print_endline "";

  test_certified_exp_i ();
  print_endline "";

  test_bool_swap_example ();

  print_endline "All bridge tests passed!"
