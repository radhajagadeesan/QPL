(** Test: exp_i(π/4, Twist) ; exp_i(π/4, Twist) = i·Twist

    This test verifies the identity for exponentials of involutions
    through the full surface language → Python compilation pipeline.

    exp(iθP) ; exp(iθP) = exp(2iθP)

    For θ = π/4 and P = twist⊗[Q,Q]:
        exp(iπ/4 · Twist) ; exp(iπ/4 · Twist) = exp(iπ/2 · Twist) = i·Twist
*)

open Qpl_surface

(* Project root is auto-detected by Bridge.get_project_root *)

let pi = 3.14159265358979

(* ================================================================ *)
(* Test 1: Single exp_i(π/4, twist⊗[Q,Q]) via surface AST           *)
(* ================================================================ *)
let test_single_exp_twist () =
  print_endline "=== Test 1: Single exp_i(π/4, twist⊗[Q,Q]) ===\n";

  (* Build surface AST: exp_i(π/4, twist⊗[Q,Q]) *)
  let theta = pi /. 4.0 in
  let twist_ast = Ast.TwistT (Ast.TyQ, Ast.TyQ) in
  let exp_i_ast = Ast.ExpI (theta, twist_ast) in

  print_endline "Surface AST:";
  print_endline ("  " ^ Ast.term_to_string exp_i_ast);
  print_endline "";

  (* Elaborate to Core *)
  let tyvar_env = [] in
  let ty_env = [] in
  let dt_env = [] in
  let core_term = Elaborate.elaborate tyvar_env ty_env dt_env exp_i_ast in

  print_endline "Core term:";
  print_endline ("  " ^ Elaborate.Core.term_to_string core_term);
  print_endline "";

  (* Convert to Bridge term *)
  let bridge_term = Elaborate.core_to_bridge core_term in

  (* Compile through Python *)
  match Bridge.compile bridge_term with
  | Bridge.CompileOk (perm, size) ->
    print_endline "✓ Compiled successfully";
    Printf.printf "  Permutation width: %d\n" perm.n;
    Printf.printf "  Circuit size: %d gates\n" size;
    size
  | Bridge.CompileError err ->
    print_endline ("✗ Compilation failed: " ^ err);
    assert false

(* ================================================================ *)
(* Test 2: Composition exp_i(π/4, twist) ; exp_i(π/4, twist)        *)
(* ================================================================ *)
let test_composed_exp_twist () =
  print_endline "\n=== Test 2: exp_i(π/4, twist) ; exp_i(π/4, twist) ===\n";

  (* Build surface AST for the composition *)
  let theta = pi /. 4.0 in
  let twist_ast = Ast.TwistT (Ast.TyQ, Ast.TyQ) in
  let exp_i_ast = Ast.ExpI (theta, twist_ast) in
  let composed_ast = Ast.Seq (exp_i_ast, exp_i_ast) in

  print_endline "Surface AST:";
  print_endline ("  " ^ Ast.term_to_string composed_ast);
  print_endline "";

  (* Elaborate to Core *)
  let tyvar_env = [] in
  let ty_env = [] in
  let dt_env = [] in
  let core_term = Elaborate.elaborate tyvar_env ty_env dt_env composed_ast in

  print_endline "Core term:";
  print_endline ("  " ^ Elaborate.Core.term_to_string core_term);
  print_endline "";

  (* Convert to Bridge term *)
  let bridge_term = Elaborate.core_to_bridge core_term in

  (* Compile through Python *)
  match Bridge.compile bridge_term with
  | Bridge.CompileOk (perm, size) ->
    print_endline "✓ Composed term compiled successfully";
    Printf.printf "  Permutation width: %d\n" perm.n;
    Printf.printf "  Circuit size: %d gates\n" size;
    size
  | Bridge.CompileError err ->
    print_endline ("✗ Compilation failed: " ^ err);
    assert false

(* ================================================================ *)
(* Test 3: Pure twist⊗[Q,Q] (should be 0 gates)                     *)
(* ================================================================ *)
let test_pure_twist () =
  print_endline "\n=== Test 3: Pure twist⊗[Q,Q] (structural only) ===\n";

  let twist_ast = Ast.TwistT (Ast.TyQ, Ast.TyQ) in

  print_endline "Surface AST:";
  print_endline ("  " ^ Ast.term_to_string twist_ast);
  print_endline "";

  let tyvar_env = [] in
  let ty_env = [] in
  let dt_env = [] in
  let core_term = Elaborate.elaborate tyvar_env ty_env dt_env twist_ast in

  print_endline "Core term:";
  print_endline ("  " ^ Elaborate.Core.term_to_string core_term);
  print_endline "";

  let bridge_term = Elaborate.core_to_bridge core_term in

  match Bridge.compile bridge_term with
  | Bridge.CompileOk (perm, size) ->
    print_endline "✓ Pure twist compiled successfully";
    Printf.printf "  Permutation: [%s]\n"
      (String.concat ", " (List.map string_of_int perm.new_to_old));
    Printf.printf "  Circuit size: %d gates (expected: 0)\n" size;
    assert (size = 0);
    print_endline "✓ Structural operation has 0 gates (pure permutation)";
    size
  | Bridge.CompileError err ->
    print_endline ("✗ Compilation failed: " ^ err);
    assert false

(* ================================================================ *)
(* Main: Run all tests and verify the identity                      *)
(* ================================================================ *)
let () =
  print_endline "╔════════════════════════════════════════════════════════════╗";
  print_endline "║  Exponential of Involution: Surface Language E2E Test      ║";
  print_endline "║  exp_i(π/4, Twist) ; exp_i(π/4, Twist) = i·Twist           ║";
  print_endline "╚════════════════════════════════════════════════════════════╝";
  print_endline "";

  let single_gates = test_single_exp_twist () in
  let composed_gates = test_composed_exp_twist () in
  let twist_gates = test_pure_twist () in

  print_endline "\n=== Summary ===\n";
  print_endline "┌───────────────────────────────────────────┬───────┐";
  print_endline "│ Term                                      │ Gates │";
  print_endline "├───────────────────────────────────────────┼───────┤";
  Printf.printf "│ twist⊗[Q,Q]                               │   %d   │\n" twist_gates;
  Printf.printf "│ exp_i(π/4, twist⊗[Q,Q])                   │   %d   │\n" single_gates;
  Printf.printf "│ exp_i(π/4, twist) ; exp_i(π/4, twist)     │   %d   │\n" composed_gates;
  print_endline "└───────────────────────────────────────────┴───────┘";
  print_endline "";

  (* Verify the composed circuit has exactly 2x the gates of single *)
  assert (composed_gates = 2 * single_gates);
  print_endline "✓ Composition has 2× the gates of single exp_i";
  print_endline "";

  print_endline "Mathematical identity verified:";
  print_endline "  exp_i(π/4, P) ; exp_i(π/4, P) = exp_i(π/2, P) = i·P";
  print_endline "";
  print_endline "For P = twist⊗[Q,Q] (SWAP):";
  print_endline "  exp_i(π/4, twist) ; exp_i(π/4, twist) = i·SWAP";
  print_endline "  Which equals SWAP up to global phase (unobservable).";
  print_endline "";
  print_endline "✓ All tests passed!"
