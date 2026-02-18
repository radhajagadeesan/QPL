(** Test: Case expressions via Bridge

    This test verifies that TCase bridge terms compile correctly
    through the Python backend to controlled gates.

    The Linear DSL case_ is for true pattern-matching (binding variables),
    while for morphism-level case (bifunctor), we use omap0.
*)

open Qpl_surface

(* Project root is auto-detected by Bridge.get_project_root *)

(* Test: TCase via Bridge directly *)
let test_tcase_hs () =
  print_endline "=== Testing TCase(Q, Q, Id, H, S) via Bridge ===\n";

  (* Build TCase directly:
     TCase(ty_left, ty_right, scrut, left, right)
       scrut: produces A + B
       left: A → C
       right: B → D

     For testing: scrut = Id(Q+Q), left = H[0], right = S[0]
  *)
  let ty_q = Rep.var 0 in
  let ty_sum = Rep.Plus (ty_q, ty_q) in

  let scrut = Bridge.TId ty_sum in
  let left = Bridge.TH 0 in
  let right = Bridge.TS 0 in

  let case_term = Bridge.TCase (ty_q, ty_q, scrut, left, right) in

  print_endline "Bridge term: TCase(Q, Q, Id(Q+Q), H[0], S[0])";
  print_endline "JSON:";
  print_endline (Bridge.term_to_json case_term);
  print_endline "";

  match Bridge.compile case_term with
  | Bridge.CompileOk (perm, size) ->
    print_endline "✓ Compiled successfully";
    Printf.printf "  perm.n = %d\n" perm.n;
    Printf.printf "  circuit_size = %d gates\n" size;
    (* Expected: Id(scrut) then X; CH; X; CS = 4 gates *)
    assert (size = 4);
    print_endline "✓ Gate count correct (4 gates: X; CH; X; CS)"
  | Bridge.CompileError err ->
    Printf.printf "✗ Compilation failed: %s\n" err;
    assert false

(* Test: TCase with identity branches *)
let test_tcase_id_id () =
  print_endline "\n=== Testing TCase(Q, Q, Id, Id, Id) via Bridge ===\n";

  let ty_q = Rep.var 0 in
  let ty_sum = Rep.Plus (ty_q, ty_q) in

  let scrut = Bridge.TId ty_sum in
  let left = Bridge.TId ty_q in
  let right = Bridge.TId ty_q in

  let case_term = Bridge.TCase (ty_q, ty_q, scrut, left, right) in

  print_endline "Bridge term: TCase(Q, Q, Id, Id, Id)";
  print_endline "";

  match Bridge.compile case_term with
  | Bridge.CompileOk (perm, size) ->
    print_endline "✓ Compiled successfully";
    Printf.printf "  perm.n = %d\n" perm.n;
    Printf.printf "  circuit_size = %d gates\n" size;
    (* Identity branches should produce 0 gates *)
    assert (size = 0);
    print_endline "✓ Gate count correct (0 gates for identity branches)"
  | Bridge.CompileError err ->
    Printf.printf "✗ Compilation failed: %s\n" err;
    assert false

(* Test: TCase asymmetric (H;S on left, Id on right) *)
let test_tcase_asymmetric () =
  print_endline "\n=== Testing TCase asymmetric (H;S on left, Id on right) ===\n";

  let ty_q = Rep.var 0 in
  let ty_sum = Rep.Plus (ty_q, ty_q) in

  let scrut = Bridge.TId ty_sum in
  let left = Bridge.TSeq (Bridge.TH 0, Bridge.TS 0) in  (* H ; S *)
  let right = Bridge.TId ty_q in  (* Id *)

  let case_term = Bridge.TCase (ty_q, ty_q, scrut, left, right) in

  print_endline "Bridge term: TCase(Q, Q, Id, H;S, Id)";
  print_endline "";

  match Bridge.compile case_term with
  | Bridge.CompileOk (perm, size) ->
    print_endline "✓ Compiled successfully";
    Printf.printf "  perm.n = %d\n" perm.n;
    Printf.printf "  circuit_size = %d gates\n" size;
    (* Left branch H;S produces X; CH; CS; X = 4 gates *)
    assert (size = 4);
    print_endline "✓ Gate count correct (4 gates: X; CH; CS; X)"
  | Bridge.CompileError err ->
    Printf.printf "✗ Compilation failed: %s\n" err;
    assert false

(* Test: Linear DSL omap0 (closed bifunctor) *)
let test_omap0 () =
  print_endline "\n=== Testing Linear DSL omap0 (closed bifunctor) ===\n";

  let open Linear in

  (* omap0 : ty_left → ty_right → (unit, A⊸C) → (unit, B⊸D) → (unit, (A+B)⊸(C+D))
     This is the closed version for emission. *)

  (* Build H ⊕ S : (Q + Q) ⊸ (Q + Q) *)
  let f = gate_h in  (* H : Q ⊸ Q *)
  let g = gate_s in  (* S : Q ⊸ Q *)

  (* Note: omap0 is defined but not exposed. We use the Bridge directly. *)
  let bridge_term = Bridge.TPlusMap (Rep.var 0, Rep.var 0, Bridge.TH 0, Bridge.TS 0) in

  print_endline "Bridge term: TPlusMap(Q, Q, H, S)";
  print_endline "This is H ⊕ S : (Q + Q) → (Q + Q)";
  print_endline "";

  (* Just to verify f and g type check *)
  let _ = emit (seq0 f g) in

  match Bridge.compile bridge_term with
  | Bridge.CompileOk (perm, size) ->
    print_endline "✓ Compiled successfully";
    Printf.printf "  perm.n = %d\n" perm.n;
    Printf.printf "  circuit_size = %d gates\n" size;
    (* PlusMap(H, S) = X; CH; X; CS = 4 gates *)
    assert (size = 4);
    print_endline "✓ Gate count correct (4 gates: X; CH; X; CS)"
  | Bridge.CompileError err ->
    Printf.printf "✗ Compilation failed: %s\n" err;
    assert false

(* Test: QSwitch pattern via TCase *)
let test_qswitch_via_case () =
  print_endline "\n=== Testing QSwitch pattern via TCase ===\n";

  let ty_q = Rep.var 0 in
  let ty_sum = Rep.Plus (ty_q, ty_q) in

  (* QSwitch applies H;S on |0⟩ and S;H on |1⟩ *)
  let scrut = Bridge.TId ty_sum in
  let left = Bridge.TSeq (Bridge.TH 0, Bridge.TS 0) in   (* H ; S *)
  let right = Bridge.TSeq (Bridge.TS 0, Bridge.TH 0) in  (* S ; H *)

  let case_term = Bridge.TCase (ty_q, ty_q, scrut, left, right) in

  print_endline "Bridge term: TCase(Q, Q, Id, H;S, S;H)";
  print_endline "Semantics: |0⟩|ψ⟩ → |0⟩(SH|ψ⟩), |1⟩|ψ⟩ → |1⟩(HS|ψ⟩)";
  print_endline "";

  match Bridge.compile case_term with
  | Bridge.CompileOk (perm, size) ->
    print_endline "✓ Compiled successfully";
    Printf.printf "  perm.n = %d\n" perm.n;
    Printf.printf "  circuit_size = %d gates\n" size;
    (* Left: X; CH; CS; X (4), Right: CS; CH (2) = 6 gates *)
    assert (size = 6);
    print_endline "✓ Gate count correct (6 gates for QSwitch pattern)"
  | Bridge.CompileError err ->
    Printf.printf "✗ Compilation failed: %s\n" err;
    assert false

(* Test: TwistPlus via Linear DSL *)
let test_twist_plus_linear () =
  print_endline "\n=== Testing TwistPlus via Linear DSL ===\n";

  let open Linear in

  let ty_q = q in
  let twist = twist_plus ty_q ty_q in

  let bridge_term = emit twist in

  print_endline "Linear DSL: twist_plus q q";
  print_endline ("Bridge JSON: " ^ Bridge.term_to_json bridge_term);
  print_endline "";

  match Bridge.compile bridge_term with
  | Bridge.CompileOk (perm, size) ->
    print_endline "✓ Compiled successfully";
    Printf.printf "  perm.n = %d\n" perm.n;
    Printf.printf "  circuit_size = %d gates\n" size;
    (* TwistPlus emits X gate for tag flip *)
    assert (size = 1);
    print_endline "✓ Gate count correct (1 X gate for tag flip)"
  | Bridge.CompileError err ->
    Printf.printf "✗ Compilation failed: %s\n" err;
    assert false

(* Run all tests *)
let () =
  print_endline "Case Expression Bridge Tests";
  print_endline "============================\n";

  test_tcase_hs ();
  test_tcase_id_id ();
  test_tcase_asymmetric ();
  test_omap0 ();
  test_qswitch_via_case ();
  test_twist_plus_linear ();

  print_endline "\n============================";
  print_endline "All case tests passed!"
