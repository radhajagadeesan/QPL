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

(* Test: Bell state via OCaml bridge *)
let test_bell_state () =
  print_endline "=== Testing Bell state (H[0] ; CX[0,1]) via OCaml bridge ===";

  let bell = Bridge.TSeq (Bridge.TH 0, Bridge.TCX (0, 1)) in

  match Bridge.compile bell with
  | Bridge.CompileOk (perm, size) ->
    print_endline "✓ Bell state compiled successfully";
    print_endline (Printf.sprintf "  perm.n = %d" perm.n);
    print_endline (Printf.sprintf "  circuit_size = %d" size);
    (* Bell state: H + CX = 2 gates *)
    assert (size = 2);
    print_endline "✓ Gate count correct (2 gates)"
  | Bridge.CompileError err ->
    print_endline ("✗ Bell state compilation failed: " ^ err);
    assert false

(* Test: GHZ state via OCaml bridge *)
let test_ghz_state () =
  print_endline "=== Testing GHZ state (H[0] ; CX[0,1] ; CX[0,2]) via OCaml bridge ===";

  let ghz = Bridge.TSeq (
    Bridge.TH 0,
    Bridge.TSeq (Bridge.TCX (0, 1), Bridge.TCX (0, 2))
  ) in

  match Bridge.compile ghz with
  | Bridge.CompileOk (perm, size) ->
    print_endline "✓ GHZ state compiled successfully";
    print_endline (Printf.sprintf "  perm.n = %d" perm.n);
    print_endline (Printf.sprintf "  circuit_size = %d" size);
    (* GHZ: H + CX + CX = 3 gates *)
    assert (size = 3);
    print_endline "✓ Gate count correct (3 gates)"
  | Bridge.CompileError err ->
    print_endline ("✗ GHZ state compilation failed: " ^ err);
    assert false

(* Test: Distributivity via OCaml bridge *)
let test_distributivity () =
  print_endline "=== Testing DistR via OCaml bridge ===";

  (* DistR: A ⊗ (B + C) -> (A ⊗ B) + (A ⊗ C) *)
  let dist = Bridge.TDistR (Rep.var 0, Rep.var 1, Rep.var 2) in

  match Bridge.compile dist with
  | Bridge.CompileOk (perm, size) ->
    print_endline "✓ DistR compiled successfully";
    print_endline (Printf.sprintf "  perm.n = %d" perm.n);
    print_endline (Printf.sprintf "  perm.new_to_old = [%s]"
      (String.concat ", " (List.map string_of_int perm.new_to_old)));
    print_endline (Printf.sprintf "  circuit_size = %d" size);
    (* DistR is structural - no gates *)
    assert (size = 0);
    print_endline "✓ DistR is structural (0 gates)"
  | Bridge.CompileError err ->
    print_endline ("✗ DistR compilation failed: " ^ err);
    assert false

(* Test: DistL via OCaml bridge *)
let test_distl () =
  print_endline "=== Testing DistL via OCaml bridge ===";

  (* DistL: (A + B) ⊗ C -> (A ⊗ C) + (B ⊗ C) *)
  let dist = Bridge.TDistL (Rep.var 0, Rep.var 1, Rep.var 2) in

  match Bridge.compile dist with
  | Bridge.CompileOk (perm, size) ->
    print_endline "✓ DistL compiled successfully";
    print_endline (Printf.sprintf "  perm.n = %d" perm.n);
    print_endline (Printf.sprintf "  perm.new_to_old = [%s]"
      (String.concat ", " (List.map string_of_int perm.new_to_old)));
    print_endline (Printf.sprintf "  circuit_size = %d" size);
    (* DistL is structural - no gates *)
    assert (size = 0);
    print_endline "✓ DistL is structural (0 gates)"
  | Bridge.CompileError err ->
    print_endline ("✗ DistL compilation failed: " ^ err);
    assert false

(* Test: Rotation gate via OCaml bridge *)
let test_rotation_gate () =
  print_endline "=== Testing Rz(π/4, 0) via OCaml bridge ===";

  let pi = 3.14159265358979 in
  let rz = Bridge.TRz (pi /. 4.0, 0) in

  match Bridge.compile rz with
  | Bridge.CompileOk (_perm, size) ->
    print_endline "✓ Rz compiled successfully";
    print_endline (Printf.sprintf "  circuit_size = %d" size);
    assert (size = 1);
    print_endline "✓ Rz emits 1 gate"
  | Bridge.CompileError err ->
    print_endline ("✗ Rz compilation failed: " ^ err);
    assert false

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

  test_bell_state ();
  print_endline "";

  test_ghz_state ();
  print_endline "";

  test_distributivity ();
  print_endline "";

  test_distl ();
  print_endline "";

  test_rotation_gate ();
  print_endline "";

  print_endline "All bridge tests passed!"
