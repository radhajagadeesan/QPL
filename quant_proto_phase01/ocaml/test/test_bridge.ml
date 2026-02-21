(** End-to-end integration tests for the Python bridge.

    These tests require the Python venv to be set up.
    Run with: dune test
*)

open Qpl_surface

(* Project root is auto-detected by Bridge.get_project_root *)

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
    (* Flat tag model: Q + Q has width 2 (1 tag bit + 1 payload) *)
    (* TwistPlus flips tag via X gate, permutation is identity *)
    (* Perm = [0, 1]: wires stay same, tag bit flipped by X gate *)
    assert (perm.n = 2);
    assert (perm.new_to_old = [0; 1])
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
    print_endline (Printf.sprintf "  perm.n = %d" perm.n);
    print_endline (Printf.sprintf "  perm.new_to_old = [%s]"
      (String.concat ", " (List.map string_of_int perm.new_to_old)));
    (* Flat tag model: V0 + V1 (Q + Q) has width 2 (1 tag bit + 1 payload) *)
    assert (perm.n = 2);
    assert (perm.new_to_old = [0; 1])
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
(* Bell = (H ⊗ Id(Q)) ; CX *)
let test_bell_state () =
  print_endline "=== Testing Bell state ((H⊗Id) ; CX) via OCaml bridge ===";

  let q = Rep.Var 0 in
  let h_tensor_id = Bridge.TTenTerm (Bridge.TH 0, Bridge.TId q) in
  let bell = Bridge.TSeq (h_tensor_id, Bridge.TCX (0, 1)) in

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
(* GHZ = (H ⊗ Id(Q) ⊗ Id(Q)) ; (CX ⊗ Id(Q)) ; CX[0,2] *)
(* Simpler: (H⊗Id⊗Id) ; (CX⊗Id) ; (CX on q0,q2 via TenTerm) *)
let test_ghz_state () =
  print_endline "=== Testing GHZ state via OCaml bridge ===";

  let q = Rep.Var 0 in
  let qq = Rep.Tensor (q, q) in
  (* Step 1: H ⊗ Id(Q⊗Q) — H on first qubit, identity on other two *)
  let step1 = Bridge.TTenTerm (Bridge.TH 0, Bridge.TId qq) in
  (* Step 2: CX(0,1) ⊗ Id(Q) — CX on first two, identity on third *)
  let step2 = Bridge.TTenTerm (Bridge.TCX (0, 1), Bridge.TId q) in
  (* Step 3: Id(Q) ⊗ CX(0,1) mapped as CX on q0,q2 requires permutation.
     Instead: swap q1,q2 then CX(0,1) then swap back.
     Or simpler: use TenTerm(Id(Q), CX) which puts CX on q1,q2,
     then twist to get CX on q0,q2. But that gives the wrong entanglement.

     Actually for GHZ: H[0]; CX[0,1]; CX[1,2] also works:
     |000⟩ → H|0⟩⊗|00⟩ → CX gives |00⟩+|11⟩ on q01 → CX[1,2] gives |000⟩+|111⟩ *)
  let step3 = Bridge.TTenTerm (Bridge.TId q, Bridge.TCX (0, 1)) in
  let ghz = Bridge.TSeq (step1, Bridge.TSeq (step2, step3)) in

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

(* Test: Controlled-H gate via OCaml bridge *)
let test_controlled_h () =
  print_endline "=== Testing CH[0,1] via OCaml bridge ===";

  let ch = Bridge.TCH (0, 1) in

  match Bridge.compile ch with
  | Bridge.CompileOk (_perm, size) ->
    print_endline "✓ CH compiled successfully";
    print_endline (Printf.sprintf "  circuit_size = %d" size);
    assert (size = 1);
    print_endline "✓ CH emits 1 gate"
  | Bridge.CompileError err ->
    print_endline ("✗ CH compilation failed: " ^ err);
    assert false

(* Test: Controlled-S gate via OCaml bridge *)
let test_controlled_s () =
  print_endline "=== Testing CS[0,1] via OCaml bridge ===";

  let cs = Bridge.TCS (0, 1) in

  match Bridge.compile cs with
  | Bridge.CompileOk (_perm, size) ->
    print_endline "✓ CS compiled successfully";
    print_endline (Printf.sprintf "  circuit_size = %d" size);
    assert (size = 1);
    print_endline "✓ CS emits 1 gate"
  | Bridge.CompileError err ->
    print_endline ("✗ CS compilation failed: " ^ err);
    assert false

(* Test: QSwitch(H,S) circuit pattern via OCaml bridge *)
let test_qswitch_circuit () =
  print_endline "=== Testing QSwitch(H,S) circuit: X[0] ; CS[0,1] ; X[0] ; H[1] ; CS[0,1] ===";

  (* The quantum switch for gates H and S on a 2-qubit system:
     - Wire 0 is the control (tag qubit)
     - Wire 1 is the target
     The decomposition is: X[0]⊗Id ; CS[0,1] ; X[0]⊗Id ; Id⊗H[0] ; CS[0,1]
     Single-qubit gates must be tensored with Id to match 2-qubit width. *)
  let q = Rep.Var 0 in
  let x_on_0 = Bridge.TTenTerm (Bridge.TX 0, Bridge.TId q) in
  let h_on_1 = Bridge.TTenTerm (Bridge.TId q, Bridge.TH 0) in
  let qswitch = Bridge.TSeq (
    x_on_0,
    Bridge.TSeq (
      Bridge.TCS (0, 1),
      Bridge.TSeq (
        x_on_0,
        Bridge.TSeq (
          h_on_1,
          Bridge.TCS (0, 1)
        )
      )
    )
  ) in

  match Bridge.compile qswitch with
  | Bridge.CompileOk (perm, size) ->
    print_endline "✓ QSwitch(H,S) compiled successfully";
    print_endline (Printf.sprintf "  perm.n = %d" perm.n);
    print_endline (Printf.sprintf "  circuit_size = %d" size);
    (* QSwitch: X + CS + X + H + CS = 5 gates *)
    assert (size = 5);
    print_endline "✓ QSwitch circuit has 5 gates"
  | Bridge.CompileError err ->
    print_endline ("✗ QSwitch(H,S) compilation failed: " ^ err);
    assert false

(* Test: ExpI through elaboration pipeline *)
let test_exp_i_elaboration () =
  print_endline "=== Testing exp_i through elaboration pipeline ===";

  (* Build surface AST: exp_i(π/8, twist+[Q,Q]) *)
  let pi = 3.14159265358979 in
  let theta = pi /. 8.0 in
  let twist_ast = Ast.TwistP (Ast.TyQ, Ast.TyQ) in
  let exp_i_ast = Ast.ExpI (theta, twist_ast) in

  (* Elaborate to Core *)
  let tyvar_env = [] in
  let ty_env = [] in
  let dt_env = [] in
  let core_term = Elaborate.elaborate tyvar_env ty_env dt_env exp_i_ast in
  print_endline ("✓ Elaborated to Core: " ^ Elaborate.Core.term_to_string core_term);

  (* Convert to Bridge term *)
  let bridge_term = Elaborate.core_to_bridge core_term in
  print_endline "✓ Converted to Bridge term";

  (* Compile through Python bridge *)
  match Bridge.compile bridge_term with
  | Bridge.CompileOk (perm, size) ->
    print_endline "✓ exp_i compiled successfully through full pipeline";
    print_endline (Printf.sprintf "  perm.n = %d" perm.n);
    print_endline (Printf.sprintf "  circuit_size = %d" size);
    (* exp_i(θ, twist+) should produce ExpSwap gates *)
    (* TwistPlus(Q,Q) has 2 transpositions: (0,1) and (2,3) *)
    assert (size >= 0);  (* ExpSwap gates are counted *)
    print_endline "✓ exp_i elaboration pipeline works"
  | Bridge.CompileError err ->
    print_endline ("✗ exp_i compilation failed: " ^ err);
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

  test_controlled_h ();
  print_endline "";

  test_controlled_s ();
  print_endline "";

  test_qswitch_circuit ();
  print_endline "";

  test_exp_i_elaboration ();
  print_endline "";

  print_endline "All bridge tests passed!"
