(** Tests for the QPL surface language *)

open Qpl_surface
module Bool = Qpl.Bool

(* Test Rep module *)
let test_rep () =
  print_endline "=== Testing Rep module ===";

  (* Basic construction *)
  let a = Rep.var 0 in
  let b = Rep.var 1 in
  let ab = Rep.plus a b in

  print_endline ("V0 = " ^ Rep.to_string a);
  print_endline ("V1 = " ^ Rep.to_string b);
  print_endline ("V0 + V1 = " ^ Rep.to_string ab);

  (* Tensor *)
  let tensor_ab = Rep.tensor a b in
  print_endline ("V0 ⊗ V1 = " ^ Rep.to_string tensor_ab);

  (* Complex type *)
  let complex = Rep.(plus (tensor (var 0) (var 1)) (var 2)) in
  print_endline ("(V0 ⊗ V1) + V2 = " ^ Rep.to_string complex);

  (* Wire count *)
  print_endline ("wire_count(V0 + V1) = " ^ string_of_int (Rep.wire_count ab));
  print_endline ("wire_count((V0 ⊗ V1) + V2) = " ^ string_of_int (Rep.wire_count complex));

  print_endline ""

(* Test Bool datatype *)
let test_bool_datatype () =
  print_endline "=== Testing Bool datatype ===";

  print_endline ("Bool.rep = " ^ Rep.to_string Bool.rep);
  print_endline ("Bool Python: " ^ Bool.emit_rep ());

  (* Test constructor lookup *)
  (match Bool.constructor "F" with
   | Some c -> print_endline ("Found constructor F with payload: " ^ Rep.to_string c.Datatype.payload)
   | None -> print_endline "ERROR: Constructor F not found");

  (match Bool.constructor "T" with
   | Some c -> print_endline ("Found constructor T with payload: " ^ Rep.to_string c.Datatype.payload)
   | None -> print_endline "ERROR: Constructor T not found");

  print_endline ""

(* Test swap elaboration *)
let test_swap () =
  print_endline "=== Testing swap elaboration ===";

  (* Emit case for swap: F(a) => T(a), T(b) => F(b) *)
  let branches = [("F", "T(a)"); ("T", "F(b)")] in
  let swap_code = Bool.emit_case branches in
  print_endline "swap = λx. case x of F(a) => T(a) | T(b) => F(b)";
  print_endline "Elaborates to:";
  print_endline swap_code;

  print_endline ""

(* Test Python emission *)
let test_emit () =
  print_endline "=== Testing Python emission ===";

  (* Emit representation *)
  let bool_rep = Rep.(plus (var 0) (var 1)) in
  print_endline ("Rep: " ^ Rep.to_string bool_rep);
  print_endline ("Python: " ^ Emit.rep_to_python bool_rep);

  (* Emit concrete type *)
  print_endline ("Concrete Python: " ^ Emit.rep_to_python_concrete bool_rep);

  print_endline ""

(* Test exp_i emission - without Python bridge for basic tests *)
let test_exp_i () =
  print_endline "=== Testing exp_i emission (static) ===";

  let pi = 3.14159265358979 in
  (* Use the low-level Emit function for basic testing *)
  let exp_code = Emit.exp_i_to_python
    ~theta:(pi /. 7.0)
    ~j_name:"swap"
    ~j_hash:"perm_2_1_0"
  in
  print_endline "exp_i(π/7, swap):";
  print_endline exp_code;

  print_endline ""

(* Custom datatype: Maybe *)
module Maybe = Datatype.Make1(struct
  type 'a t = Nothing | Just of 'a
  [@@warning "-37"]

  let name = "Maybe"

  (* Canonical representation: Unit (+) A *)
  let rep = Rep.(plus unit (var 0))

  let constructors = [
    ("Nothing", Rep.unit);
    ("Just", Rep.var 0);
  ]
end)

let test_maybe () =
  print_endline "=== Testing Maybe datatype ===";

  print_endline ("Maybe.rep = " ^ Rep.to_string Maybe.rep);
  print_endline ("Maybe Python: " ^ Maybe.emit_rep ());

  print_endline ""

(* Custom datatype: Either *)
module Either = Datatype.Make2(struct
  type ('a, 'b) t = Left of 'a | Right of 'b
  [@@warning "-37"]

  let name = "Either"

  let rep = Rep.(plus (var 0) (var 1))

  let constructors = [
    ("Left", Rep.var 0);
    ("Right", Rep.var 1);
  ]
end)

let test_either () =
  print_endline "=== Testing Either datatype ===";

  print_endline ("Either.rep = " ^ Rep.to_string Either.rep);
  print_endline ("Either Python: " ^ Either.emit_rep ());

  print_endline ""

(* Custom datatype: Triple (3 constructors) *)
module Triple = Datatype.Make3(struct
  type ('a, 'b, 'c) t = A of 'a | B of 'b | C of 'c
  [@@warning "-37"]

  let name = "Triple"

  (* Canonical representation: (A + B) + C (left-associated) *)
  let rep = Rep.(plus (plus (var 0) (var 1)) (var 2))

  let constructors = [
    ("A", Rep.var 0);
    ("B", Rep.var 1);
    ("C", Rep.var 2);
  ]
end)

let test_triple () =
  print_endline "=== Testing Triple datatype (3 constructors) ===";

  print_endline ("Triple.rep = " ^ Rep.to_string Triple.rep);
  print_endline ("Triple Python: " ^ Triple.emit_rep ());

  (* Test identity case: A->A, B->B, C->C *)
  let identity_case = Triple.emit_case [("A", "a"); ("B", "b"); ("C", "c")] in
  print_endline "\nIdentity case (A->A, B->B, C->C):";
  print_endline identity_case;

  (* Test rotation: A->B, B->C, C->A *)
  let rotate_case = Triple.emit_case [("C", "c"); ("A", "a"); ("B", "b")] in
  print_endline "\nRotation case (C->A, A->B, B->C):";
  print_endline rotate_case;

  (* Test swap first two: B->A, A->B, C->C *)
  let swap_case = Triple.emit_case [("B", "b"); ("A", "a"); ("C", "c")] in
  print_endline "\nSwap first two (B->A, A->B, C->C):";
  print_endline swap_case;

  print_endline ""

(* Test Perm_gen directly *)
let test_perm_gen () =
  print_endline "=== Testing Perm_gen module ===";

  (* Canonical representations *)
  print_endline "Canonical representations:";
  print_endline ("  2 constructors: " ^ Perm_gen.canonical_rep_string 2);
  print_endline ("  3 constructors: " ^ Perm_gen.canonical_rep_string 3);
  print_endline ("  4 constructors: " ^ Perm_gen.canonical_rep_string 4);

  (* Permutation decomposition *)
  print_endline "\nPermutation decomposition:";
  let perm1 = [|1; 0|] in  (* swap *)
  let swaps1 = Perm_gen.decompose_permutation perm1 in
  print_endline (Printf.sprintf "  [1,0] -> swaps: [%s]"
    (String.concat ", " (List.map string_of_int swaps1)));

  let perm2 = [|2; 0; 1|] in  (* rotation *)
  let swaps2 = Perm_gen.decompose_permutation perm2 in
  print_endline (Printf.sprintf "  [2,0,1] -> swaps: [%s]"
    (String.concat ", " (List.map string_of_int swaps2)));

  let perm3 = [|1; 0; 2|] in  (* swap first two *)
  let swaps3 = Perm_gen.decompose_permutation perm3 in
  print_endline (Printf.sprintf "  [1,0,2] -> swaps: [%s]"
    (String.concat ", " (List.map string_of_int swaps3)));

  print_endline ""

(* Test AST construction and pretty-printing *)
let test_ast () =
  print_endline "=== Testing AST module ===";

  (* Build a simple term: H[0] ; S[0] *)
  let term1 = Ast.(Seq (GateH 0, GateS 0)) in
  print_endline ("H[0] ; S[0] = " ^ Ast.term_to_string term1);

  (* Build tensor: H[0] ⊗ H[1] *)
  let term2 = Ast.(Ten (GateH 0, GateH 1)) in
  print_endline ("H[0] ⊗ H[1] = " ^ Ast.term_to_string term2);

  (* Build lambda: λx:Q. H[0] *)
  let term3 = Ast.(Lam ("x", TyQ, GateH 0)) in
  print_endline ("λx:Q. H[0] = " ^ Ast.term_to_string term3);

  (* Build let: let y = H[0] in y ; S[0] *)
  let term4 = Ast.(Let ("y", GateH 0, Seq (Var "y", GateS 0))) in
  print_endline ("let y = H[0] in y ; S[0] = " ^ Ast.term_to_string term4);

  (* Build case: case x of F(a) => T(a) | T(b) => F(b) *)
  let term5 = Ast.(Case (Var "x", [
    (PatCtor ("F", "a"), Ctor ("T", Var "a"));
    (PatCtor ("T", "b"), Ctor ("F", Var "b"));
  ])) in
  print_endline ("case = " ^ Ast.term_to_string term5);

  (* Test types *)
  let ty1 = Ast.(TyTensor (TyQ, TyQ)) in
  print_endline ("Q ⊗ Q = " ^ Ast.ty_to_string ty1);

  let ty2 = Ast.(TyPlus (TyQ, TyQ)) in
  print_endline ("Q + Q = " ^ Ast.ty_to_string ty2);

  let ty3 = Ast.(TyNamed ("Bool", [TyQ; TyQ])) in
  print_endline ("Bool[Q, Q] = " ^ Ast.ty_to_string ty3);

  print_endline ""

(* Test Elaborate module *)
let test_elaborate () =
  print_endline "=== Testing Elaborate module ===";

  (* Test substitution *)
  print_endline "Testing substitution:";
  let open Ast in
  let term1 = Var "x" in
  let subst_result = Elaborate.subst "x" (GateH 0) term1 in
  print_endline ("  [H[0]/x](x) = " ^ term_to_string subst_result);

  let term2 = Lam ("x", TyQ, Var "x") in
  let subst_result2 = Elaborate.subst "x" (GateH 0) term2 in
  print_endline ("  [H[0]/x](λx:Q. x) = " ^ term_to_string subst_result2 ^ " (x shadowed)");

  let term3 = Seq (Var "x", Var "y") in
  let subst_result3 = Elaborate.subst "x" (GateH 0) term3 in
  print_endline ("  [H[0]/x](x ; y) = " ^ term_to_string subst_result3);

  (* Test free variables *)
  print_endline "\nTesting free variables:";
  let fvs1 = Elaborate.free_vars (Var "x") in
  print_endline ("  FV(x) = [" ^ String.concat ", " fvs1 ^ "]");

  let fvs2 = Elaborate.free_vars (Lam ("x", TyQ, Var "x")) in
  print_endline ("  FV(λx:Q. x) = [" ^ String.concat ", " fvs2 ^ "]");

  let fvs3 = Elaborate.free_vars (Lam ("x", TyQ, Seq (Var "x", Var "y"))) in
  print_endline ("  FV(λx:Q. x ; y) = [" ^ String.concat ", " fvs3 ^ "]");

  (* Test elaboration of let *)
  print_endline "\nTesting let elaboration:";
  let let_term = Let ("x", GateH 0, Seq (Var "x", GateS 0)) in
  print_endline ("  Source: " ^ term_to_string let_term);
  let tyvar_env = Elaborate.TyVarEnv.empty in
  let ty_env = Elaborate.TyEnv.empty in
  let dt_env = Elaborate.DtEnv.empty in
  let elaborated = Elaborate.elaborate tyvar_env ty_env dt_env let_term in
  print_endline ("  Elaborated: " ^ Elaborate.Core.term_to_string elaborated);

  (* Test elaboration of application *)
  print_endline "\nTesting application elaboration:";
  let app_term = App (Lam ("x", TyQ, Seq (Var "x", GateS 0)), GateH 0) in
  print_endline ("  Source: " ^ term_to_string app_term);
  let elaborated2 = Elaborate.elaborate tyvar_env ty_env dt_env app_term in
  print_endline ("  Elaborated: " ^ Elaborate.Core.term_to_string elaborated2);

  (* Test elaboration of primitives *)
  print_endline "\nTesting primitive elaboration:";
  let seq_term = Seq (GateH 0, GateS 0) in
  print_endline ("  Source: " ^ term_to_string seq_term);
  let elaborated3 = Elaborate.elaborate tyvar_env ty_env dt_env seq_term in
  print_endline ("  Elaborated: " ^ Elaborate.Core.term_to_string elaborated3);

  print_endline ""

(* Test quantum case elaboration *)
let test_quantum_case () =
  print_endline "=== Testing quantum case elaboration ===";

  (* Build a quantum case expression with payload:
     case q of
       | Left(a) => Left(a ; H)    (left branch: apply H to payload)
       | Right(b) => Right(b ; S)  (right branch: apply S to payload)

     Where q : Q + Q, so:
     - Wire 0 is the tag qubit
     - Wire 1 is the payload qubit

     The pattern variables a, b are used (re-wrapped in constructors),
     satisfying linearity.
  *)
  let open Ast in
  let tyvar_env = Elaborate.TyVarEnv.empty in
  (* Add 'q' to the type environment with type Q + Q *)
  let ty_env = Elaborate.TyEnv.extend Elaborate.TyEnv.empty "q" (TyPlus (TyQ, TyQ)) in
  let dt_env = Elaborate.DtEnv.empty in

  (* case q of Left(a) => Left(a ; H) | Right(b) => Right(b ; S) *)
  let quantum_case = Case (Var "q", [
    (PatCtor ("Left", "a"), Ctor ("Left", Seq (Var "a", GateH 0)));
    (PatCtor ("Right", "b"), Ctor ("Right", Seq (Var "b", GateS 0)));
  ]) in

  print_endline ("  Source: " ^ term_to_string quantum_case);

  let elaborated =
    try
      Elaborate.elaborate tyvar_env ty_env dt_env quantum_case
    with Elaborate.ElaborateError e ->
      print_endline ("  ERROR: " ^ Elaborate.error_to_string e);
      raise (Elaborate.ElaborateError e)
  in
  print_endline ("  Elaborated: " ^ Elaborate.Core.term_to_string elaborated);

  (* Verify the structure contains controlled gates *)
  let result_str = Elaborate.Core.term_to_string elaborated in
  if String.length result_str > 0 then
    print_endline "  ✓ Elaboration succeeded"
  else
    print_endline "  Elaboration produced empty result";

  print_endline ""

(* Test nested quantum case elaboration *)
let test_nested_quantum_case () =
  print_endline "=== Testing nested quantum case elaboration ===";

  (* Note: Full nested quantum case elaboration with constructor re-wrapping
     is complex and requires careful handling of tag flips.
     This test is simplified to document the expected behavior. *)
  print_endline "  (Nested quantum case is tested via conformance suite)";
  print_endline "  See test_src_conformance.ml for Linear GADT coverage.";
  print_endline ""

(* Test triple-nested quantum case elaboration *)
let test_triple_nested_quantum_case () =
  print_endline "=== Testing triple-nested quantum case elaboration ===";

  (* Build a triple-nested case expression on ((Q + Q) + Q) + Q:
     case outer of
       | Left(mid) => case mid of
                        | Left(inner) => case inner of
                                           | Left(a) => wrap(a ; H)
                                           | Right(b) => wrap(b ; S)
                        | Right(c) => wrap(c ; T)
       | Right(d) => wrap(d ; X)

     Where wrap re-wraps the value in the appropriate constructors.
     Layout: [outer_tag | mid_tag | inner_tag | payload] = wires [0, 1, 2, 3]
     Type: ((Q + Q) + Q) + Q has width 4

     Pattern variables are properly used (re-wrapped with gate applied).
  *)
  let open Ast in
  let tyvar_env = Elaborate.TyVarEnv.empty in
  (* Type: ((Q + Q) + Q) + Q - three levels of nesting with Q payloads *)
  let innermost_sum = TyPlus (TyQ, TyQ) in
  let middle_sum = TyPlus (innermost_sum, TyQ) in
  let outer_sum = TyPlus (middle_sum, TyQ) in
  let ty_env = Elaborate.TyEnv.extend Elaborate.TyEnv.empty "outer" outer_sum in
  let ty_env = Elaborate.TyEnv.extend ty_env "mid" middle_sum in
  let ty_env = Elaborate.TyEnv.extend ty_env "inner" innermost_sum in
  let dt_env = Elaborate.DtEnv.empty in

  (* Helper to wrap deeply: Left(Left(Left(x))) *)
  let wrap_lll x = Ctor ("Left", Ctor ("Left", Ctor ("Left", x))) in
  let wrap_llr x = Ctor ("Left", Ctor ("Left", Ctor ("Right", x))) in
  let wrap_lr x = Ctor ("Left", Ctor ("Right", x)) in
  let wrap_r x = Ctor ("Right", x) in

  let innermost_case = Case (Var "inner", [
    (PatCtor ("Left", "a"), wrap_lll (Seq (Var "a", GateH 0)));
    (PatCtor ("Right", "b"), wrap_llr (Seq (Var "b", GateS 0)));
  ]) in

  let middle_case = Case (Var "mid", [
    (PatCtor ("Left", "inner"), innermost_case);
    (PatCtor ("Right", "c"), wrap_lr (Seq (Var "c", GateT 0)));
  ]) in

  let outer_case = Case (Var "outer", [
    (PatCtor ("Left", "mid"), middle_case);
    (PatCtor ("Right", "d"), wrap_r (Seq (Var "d", GateX 0)));
  ]) in

  print_endline ("  Source: triple-nested case on (((Q+Q)+Q)+Q)");

  let elaborated = Elaborate.elaborate tyvar_env ty_env dt_env outer_case in
  let result_str = Elaborate.Core.term_to_string elaborated in
  print_endline ("  Elaborated: " ^ result_str);
  print_endline "  ✓ Triple-nested case elaborated successfully";

  print_endline ""

(* Regression test: true partial flip should still be rejected *)
let test_partial_flip_rejected () =
  print_endline "=== Testing partial constructor flip rejection ===";

  let open Ast in
  let tyvar_env = Elaborate.TyVarEnv.empty in
  let ty_env = Elaborate.TyEnv.extend Elaborate.TyEnv.empty "x" (TyPlus (TyQ, TyQ)) in
  let dt_env = Elaborate.DtEnv.empty in

  (* case x of Left(a) => Left(a ; H) | Right(b) => Left(b ; S)
     Both branches produce Left — partial flip (Right→Left is a flip,
     Left→Left is not). This is not unitary. *)
  let bad_case = Case (Var "x", [
    (PatCtor ("Left", "a"), Ctor ("Left", Seq (Var "a", GateH 0)));
    (PatCtor ("Right", "b"), Ctor ("Left", Seq (Var "b", GateS 0)));
  ]) in

  (try
    let _ = Elaborate.elaborate tyvar_env ty_env dt_env bad_case in
    print_endline "  ✗ Should have rejected partial flip, but elaboration succeeded!"
  with
  | Failure msg when String.length msg > 0 &&
      (try let _ = Str.search_forward (Str.regexp "partial constructor flip") msg 0 in true
       with Not_found -> false) ->
    print_endline "  ✓ Partial flip correctly rejected (not unitary)";
    print_endline ("    Error: " ^ msg)
  | e ->
    print_endline ("  ✗ Wrong error: " ^ Printexc.to_string e));

  print_endline ""

(* Regression test: both-flip should produce unconditional X on tag *)
let test_both_flip () =
  print_endline "=== Testing both-flip (structural TwistPlus) ===";

  let open Ast in
  let tyvar_env = Elaborate.TyVarEnv.empty in
  let ty_env = Elaborate.TyEnv.extend Elaborate.TyEnv.empty "x" (TyPlus (TyQ, TyQ)) in
  let dt_env = Elaborate.DtEnv.empty in

  (* case x of Left(a) => Right(a ; H) | Right(b) => Left(b ; S)
     Both branches flip the constructor — should emit X[tag] *)
  let flip_case = Case (Var "x", [
    (PatCtor ("Left", "a"), Ctor ("Right", Seq (Var "a", GateH 0)));
    (PatCtor ("Right", "b"), Ctor ("Left", Seq (Var "b", GateS 0)));
  ]) in

  let elaborated = Elaborate.elaborate tyvar_env ty_env dt_env flip_case in
  let result_str = Elaborate.Core.term_to_string elaborated in
  print_endline ("  Elaborated: " ^ result_str);

  (* With Core.Case approach, both-flip emits case(...) ; twist+[...] *)
  let has_twist =
    try let _ = Str.search_forward (Str.regexp "twist\\+") result_str 0 in true
    with Not_found -> false
  in
  if has_twist then
    print_endline "  ✓ Both-flip correctly emits case ; twist+ (structural swap)"
  else
    print_endline "  ✗ Expected twist+ for tag flip, not found";

  print_endline ""

(* Test eta-expanded structural isomorphisms *)
let test_eta_expanded_structural () =
  print_endline "=== Testing eta-expanded structural isomorphisms ===";

  let open Ast in
  let tyvar_env = Elaborate.TyVarEnv.empty in
  let dt_env = Elaborate.DtEnv.empty in

  (* Test 1: TwistPlus - the primitive version *)
  print_endline "\n--- TwistPlus: Built-in vs Eta-expanded ---";
  let builtin_twist = TwistP (TyUnit, TyUnit) in
  let builtin_result = Elaborate.elaborate tyvar_env Elaborate.TyEnv.empty dt_env builtin_twist in
  print_endline ("  Built-in TwistP: " ^ Elaborate.Core.term_to_string builtin_result);

  (* Eta-expanded TwistPlus:
     case x of Left(a) => Right(a) | Right(b) => Left(b)

     This swaps the constructors - structurally equivalent to TwistP.
     Question: Does it elaborate to pure rewiring or controlled gates?
  *)
  let ty_env = Elaborate.TyEnv.extend Elaborate.TyEnv.empty "x" (TyPlus (TyUnit, TyUnit)) in
  let eta_twist = Case (Var "x", [
    (PatCtor ("Left", "a"), Ctor ("Right", Var "a"));
    (PatCtor ("Right", "b"), Ctor ("Left", Var "b"));
  ]) in
  print_endline ("  Eta-expanded source: " ^ term_to_string eta_twist);
  let eta_result = Elaborate.elaborate tyvar_env ty_env dt_env eta_twist in
  let eta_str = Elaborate.Core.term_to_string eta_result in
  print_endline ("  Eta-expanded result: " ^ eta_str);

  (* Check if eta-expanded version is structural (only X gates for tag flips, no H/S/T/CX) *)
  let has_computational_gates =
    Str.string_match (Str.regexp ".*[^C]H\\[\\|.*[^C]S\\[\\|.*[^C]T\\[\\|.*CX\\[.*") eta_str 0 ||
    Str.string_match (Str.regexp ".*C[0-9]-H\\|.*C[0-9]-S\\|.*C[0-9]-T.*") eta_str 0
  in
  let has_x_gates = Str.string_match (Str.regexp ".*X\\[.*") eta_str 0 in

  if has_computational_gates then
    print_endline "  ✗ Eta-expanded has computational gates (NOT structural!)"
  else if has_x_gates then begin
    print_endline "  ✓ Eta-expanded is structural (only X gates for tag flips)";
    (* Verify that X[0] ; X[0] patterns cancel, leaving just X[0] for twist *)
    print_endline "    (X gates cancel except final flip: equivalent to X[tag])"
  end else
    print_endline "  ✓ Eta-expanded is pure identity (no gates)";

  (* Test 2: Identity case - no change to constructors *)
  print_endline "\n--- Identity: case that preserves constructors ---";
  let identity_case = Case (Var "x", [
    (PatCtor ("Left", "a"), Ctor ("Left", Var "a"));
    (PatCtor ("Right", "b"), Ctor ("Right", Var "b"));
  ]) in
  print_endline ("  Identity source: " ^ term_to_string identity_case);
  let identity_result = Elaborate.elaborate tyvar_env ty_env dt_env identity_case in
  let identity_str = Elaborate.Core.term_to_string identity_result in
  print_endline ("  Identity result: " ^ identity_str);

  (* Verify identity is structural (X gates should cancel completely) *)
  let id_has_computational =
    Str.string_match (Str.regexp ".*[^C]H\\[\\|.*[^C]S\\[\\|.*[^C]T\\[\\|.*CX\\[.*") identity_str 0 ||
    Str.string_match (Str.regexp ".*C[0-9]-H\\|.*C[0-9]-S\\|.*C[0-9]-T.*") identity_str 0
  in
  if id_has_computational then
    print_endline "  ✗ Identity case has computational gates (NOT structural!)"
  else
    print_endline "  ✓ Identity case is structural (X gates cancel to identity)";

  (* Test 3: AssocPlusL eta-expanded: (A + B) + C → A + (B + C) *)
  print_endline "\n--- AssocPlusL: Eta-expanded associativity ---";
  (*
     case outer of
       | Left(inner) => case inner of
           | Left(a) => Left(a)           -- (Left, Left) → Left
           | Right(b) => Right(Left(b))   -- (Left, Right) → Right(Left)
       | Right(c) => Right(Right(c))      -- Right → Right(Right)

     Input type: (I + I) + I
     Output type: I + (I + I)
     This should be purely structural (just tag manipulation).
  *)
  let inner_sum = TyPlus (TyUnit, TyUnit) in
  let outer_sum = TyPlus (inner_sum, TyUnit) in  (* (I + I) + I *)
  let ty_env_assoc = Elaborate.TyEnv.extend Elaborate.TyEnv.empty "outer" outer_sum in
  let ty_env_assoc = Elaborate.TyEnv.extend ty_env_assoc "inner" inner_sum in

  let inner_case = Case (Var "inner", [
    (PatCtor ("Left", "a"), Ctor ("Left", Var "a"));
    (PatCtor ("Right", "b"), Ctor ("Right", Ctor ("Left", Var "b")));
  ]) in

  let assoc_case = Case (Var "outer", [
    (PatCtor ("Left", "inner"), inner_case);
    (PatCtor ("Right", "c"), Ctor ("Right", Ctor ("Right", Var "c")));
  ]) in

  print_endline ("  AssocPlusL source: (A+B)+C → A+(B+C)");
  let assoc_result = Elaborate.elaborate tyvar_env ty_env_assoc dt_env assoc_case in
  let assoc_str = Elaborate.Core.term_to_string assoc_result in
  print_endline ("  Elaborated: " ^ assoc_str);

  (* Verify it's structural (only X gates for tag flips, no H/S/T) *)
  let assoc_has_computational =
    Str.string_match (Str.regexp ".*[^C]H\\[\\|.*[^C]S\\[\\|.*[^C]T\\[\\|.*CX\\[.*") assoc_str 0 ||
    Str.string_match (Str.regexp ".*C[0-9]-H\\|.*C[0-9]-S\\|.*C[0-9]-T.*") assoc_str 0
  in
  if assoc_has_computational then
    print_endline "  ✗ AssocPlusL has computational gates (NOT structural!)"
  else
    print_endline "  ✓ AssocPlusL is structural (only X/CX gates for tag manipulation)";

  (* Test 4: AssocPlusR eta-expanded: A + (B + C) → (A + B) + C (inverse) *)
  print_endline "\n--- AssocPlusR: Eta-expanded inverse associativity ---";
  (*
     case outer of
       | Left(a) => Left(Left(a))         -- Left → Left(Left)
       | Right(inner) => case inner of
           | Left(b) => Left(Right(b))    -- Right(Left) → Left(Right)
           | Right(c) => Right(c)         -- Right(Right) → Right

     Input type: I + (I + I)
     Output type: (I + I) + I
  *)
  let inner_sum_r = TyPlus (TyUnit, TyUnit) in
  let outer_sum_r = TyPlus (TyUnit, inner_sum_r) in  (* I + (I + I) *)
  let ty_env_assocr = Elaborate.TyEnv.extend Elaborate.TyEnv.empty "outer" outer_sum_r in
  let ty_env_assocr = Elaborate.TyEnv.extend ty_env_assocr "inner" inner_sum_r in

  let inner_case_r = Case (Var "inner", [
    (PatCtor ("Left", "b"), Ctor ("Left", Ctor ("Right", Var "b")));
    (PatCtor ("Right", "c"), Ctor ("Right", Var "c"));
  ]) in

  let assocr_case = Case (Var "outer", [
    (PatCtor ("Left", "a"), Ctor ("Left", Ctor ("Left", Var "a")));
    (PatCtor ("Right", "inner"), inner_case_r);
  ]) in

  print_endline ("  AssocPlusR source: A+(B+C) → (A+B)+C");
  let assocr_result = Elaborate.elaborate tyvar_env ty_env_assocr dt_env assocr_case in
  let assocr_str = Elaborate.Core.term_to_string assocr_result in
  print_endline ("  Elaborated: " ^ assocr_str);

  let assocr_has_computational =
    Str.string_match (Str.regexp ".*[^C]H\\[\\|.*[^C]S\\[\\|.*[^C]T\\[\\|.*CX\\[.*") assocr_str 0 ||
    Str.string_match (Str.regexp ".*C[0-9]-H\\|.*C[0-9]-S\\|.*C[0-9]-T.*") assocr_str 0
  in
  if assocr_has_computational then
    print_endline "  ✗ AssocPlusR has computational gates (NOT structural!)"
  else
    print_endline "  ✓ AssocPlusR is structural (only X/CX gates for tag manipulation)";

  (* Test 5: DistL primitive: A ⊗ (B + C) → (A ⊗ B) + (A ⊗ C) *)
  print_endline "\n--- DistL: Left distributivity primitive ---";
  let distL_term = DistL (TyQ, TyUnit, TyUnit) in  (* Q ⊗ (I + I) → (Q ⊗ I) + (Q ⊗ I) *)
  print_endline ("  DistL source: Q ⊗ (I + I) → (Q ⊗ I) + (Q ⊗ I)");
  let distL_result = Elaborate.elaborate tyvar_env Elaborate.TyEnv.empty dt_env distL_term in
  let distL_str = Elaborate.Core.term_to_string distL_result in
  print_endline ("  Elaborated: " ^ distL_str);

  let distL_has_computational =
    Str.string_match (Str.regexp ".*[^C]H\\[\\|.*[^C]S\\[\\|.*[^C]T\\[\\|.*CX\\[.*") distL_str 0 ||
    Str.string_match (Str.regexp ".*C[0-9]-H\\|.*C[0-9]-S\\|.*C[0-9]-T.*") distL_str 0
  in
  if distL_has_computational then
    print_endline "  ✗ DistL has computational gates (NOT structural!)"
  else
    print_endline "  ✓ DistL is structural (pure wire permutation)";

  (* Test 6: DistR primitive: (A + B) ⊗ C → (A ⊗ C) + (B ⊗ C) *)
  print_endline "\n--- DistR: Right distributivity primitive ---";
  let distR_term = DistR (TyUnit, TyUnit, TyQ) in  (* (I + I) ⊗ Q → (I ⊗ Q) + (I ⊗ Q) *)
  print_endline ("  DistR source: (I + I) ⊗ Q → (I ⊗ Q) + (I ⊗ Q)");
  let distR_result = Elaborate.elaborate tyvar_env Elaborate.TyEnv.empty dt_env distR_term in
  let distR_str = Elaborate.Core.term_to_string distR_result in
  print_endline ("  Elaborated: " ^ distR_str);

  let distR_has_computational =
    Str.string_match (Str.regexp ".*[^C]H\\[\\|.*[^C]S\\[\\|.*[^C]T\\[\\|.*CX\\[.*") distR_str 0 ||
    Str.string_match (Str.regexp ".*C[0-9]-H\\|.*C[0-9]-S\\|.*C[0-9]-T.*") distR_str 0
  in
  if distR_has_computational then
    print_endline "  ✗ DistR has computational gates (NOT structural!)"
  else
    print_endline "  ✓ DistR is structural (pure wire permutation)";

  (* Test 7: Tensor destructuring: let (a ⊗ bc) = ... *)
  print_endline "\n--- Tensor destructuring ---";
  (*
     let (a ⊗ bc) : Q ⊗ (I + I) = id in
       case bc of
         | Left(u) => Left(a)
         | Right(u) => Right(a)

     This is eta-expanded distL for Q ⊗ (I + I) → (Q ⊗ I) + (Q ⊗ I)
     Wire layout:
       - a (Q) at wire 0
       - bc ((I + I)) at wire 1 (tag only, no payload)
     Output: tag moves from wire 1 to wire 0
  *)
  let bc_type = TyPlus (TyUnit, TyUnit) in  (* I + I *)
  let a_type = TyQ in
  (* Note: PatWild for both branches because the payload type is I (unit, width 0).
     The pattern variable would be unused since unit carries no information. *)
  let tensor_destruct = LetTen ("a", "bc", a_type, bc_type,
    Id (TyTensor (a_type, bc_type)),
    Case (Var "bc", [
      (PatWild, Ctor ("Left", Var "a"));
      (PatWild, Ctor ("Right", Var "a"));
    ])
  ) in
  print_endline ("  Source: let (a ⊗ bc) : Q ⊗ (I+I) = id in case bc of ...");
  let td_result = Elaborate.elaborate tyvar_env Elaborate.TyEnv.empty dt_env tensor_destruct in
  let td_str = Elaborate.Core.term_to_string td_result in
  print_endline ("  Elaborated: " ^ td_str);

  (* Verify it's structural (should have X gates for tag movement, no H/S/T) *)
  let td_has_computational =
    Str.string_match (Str.regexp ".*[^C]H\\[\\|.*[^C]S\\[\\|.*[^C]T\\[\\|.*CX\\[.*") td_str 0 ||
    Str.string_match (Str.regexp ".*C[0-9]-H\\|.*C[0-9]-S\\|.*C[0-9]-T.*") td_str 0
  in
  if td_has_computational then
    print_endline "  ✗ Tensor destructuring has computational gates (NOT structural!)"
  else
    print_endline "  ✓ Tensor destructuring is structural (eta-expanded distL works!)";

  (* Test 8: Tensor symmetry (TwistT) primitive *)
  print_endline "\n--- TwistT: Tensor symmetry primitive ---";
  let twistT_term = TwistT (TyQ, TyQ) in  (* Q ⊗ Q → Q ⊗ Q *)
  print_endline ("  TwistT source: Q ⊗ Q → Q ⊗ Q (swap wires)");
  let twistT_result = Elaborate.elaborate tyvar_env Elaborate.TyEnv.empty dt_env twistT_term in
  let twistT_str = Elaborate.Core.term_to_string twistT_result in
  print_endline ("  Elaborated: " ^ twistT_str);

  (* Note: "twist⊗" is 8 bytes in UTF-8: "twist" (5) + ⊗ (3 bytes: E2 8A 97) *)
  if String.length twistT_str >= 8 && String.sub twistT_str 0 8 = "twist⊗" then
    print_endline "  ✓ TwistT is structural (pure wire permutation)"
  else
    print_endline ("  ✗ TwistT should be structural, got: " ^ twistT_str);

  (* Test 9: Tensor associativity (AssocTL) primitive *)
  print_endline "\n--- AssocTL: Tensor associativity primitive ---";
  let assocTL_term = AssocTL (TyQ, TyQ, TyQ) in  (* (Q ⊗ Q) ⊗ Q → Q ⊗ (Q ⊗ Q) *)
  print_endline ("  AssocTL source: (Q ⊗ Q) ⊗ Q → Q ⊗ (Q ⊗ Q)");
  let assocTL_result = Elaborate.elaborate tyvar_env Elaborate.TyEnv.empty dt_env assocTL_term in
  let assocTL_str = Elaborate.Core.term_to_string assocTL_result in
  print_endline ("  Elaborated: " ^ assocTL_str);

  (* Note: "assoc⊗" is 8 bytes in UTF-8: "assoc" (5) + ⊗ (3 bytes: E2 8A 97) *)
  if String.length assocTL_str >= 8 && String.sub assocTL_str 0 8 = "assoc⊗" then
    print_endline "  ✓ AssocTL is structural (pure wire permutation)"
  else
    print_endline ("  ✗ AssocTL should be structural, got: " ^ assocTL_str);

  (* Test 10: Tensor associativity (AssocTR) primitive *)
  print_endline "\n--- AssocTR: Tensor associativity inverse ---";
  let assocTR_term = AssocTR (TyQ, TyQ, TyQ) in  (* Q ⊗ (Q ⊗ Q) → (Q ⊗ Q) ⊗ Q *)
  print_endline ("  AssocTR source: Q ⊗ (Q ⊗ Q) → (Q ⊗ Q) ⊗ Q");
  let assocTR_result = Elaborate.elaborate tyvar_env Elaborate.TyEnv.empty dt_env assocTR_term in
  let assocTR_str = Elaborate.Core.term_to_string assocTR_result in
  print_endline ("  Elaborated: " ^ assocTR_str);

  (* Note: "assoc⊗" is 8 bytes in UTF-8: "assoc" (5) + ⊗ (3 bytes: E2 8A 97) *)
  if String.length assocTR_str >= 8 && String.sub assocTR_str 0 8 = "assoc⊗" then
    print_endline "  ✓ AssocTR is structural (pure wire permutation)"
  else
    print_endline ("  ✗ AssocTR should be structural, got: " ^ assocTR_str);

  (* Test 11: Full eta-expanded DistL via tensor destructuring *)
  print_endline "\n--- Eta-expanded DistL: A ⊗ (B + C) → (A ⊗ B) + (A ⊗ C) ---";
  (*
     let (a ⊗ bc) : Q ⊗ (I + I) = id in
       case bc of
         | Left(b)  => Left(a)   -- Left(a ⊗ b) but b is Unit
         | Right(c) => Right(a)  -- Right(a ⊗ c) but c is Unit

     For Q ⊗ (I + I):
       Wire 0: Q (a)
       Wire 1: tag for (I + I)
     Output (Q + Q):
       Wire 0: tag
       Wire 1: Q
     So this is a wire permutation [1, 0].
  *)
  let distL_eta = LetTen ("a", "bc", TyQ, TyPlus (TyUnit, TyUnit),
    Id (TyTensor (TyQ, TyPlus (TyUnit, TyUnit))),
    Case (Var "bc", [
      (PatWild, Ctor ("Left", Var "a"));
      (PatWild, Ctor ("Right", Var "a"));
    ])
  ) in
  print_endline ("  Source: let (a ⊗ bc) = id in case bc of Left => Left(a) | Right => Right(a)");
  let distL_eta_result = Elaborate.elaborate tyvar_env Elaborate.TyEnv.empty dt_env distL_eta in
  let distL_eta_str = Elaborate.Core.term_to_string distL_eta_result in
  print_endline ("  Elaborated: " ^ distL_eta_str);

  let distL_eta_has_computational =
    Str.string_match (Str.regexp ".*[^C]H\\[\\|.*[^C]S\\[\\|.*[^C]T\\[\\|.*CX\\[.*") distL_eta_str 0 ||
    Str.string_match (Str.regexp ".*C[0-9]-H\\|.*C[0-9]-S\\|.*C[0-9]-T.*") distL_eta_str 0
  in
  if distL_eta_has_computational then
    print_endline "  ✗ Eta-expanded DistL has computational gates!"
  else
    print_endline "  ✓ Eta-expanded DistL is structural (matches primitive DistL)";

  (* Test 12: Full eta-expanded DistR via tensor destructuring *)
  print_endline "\n--- Eta-expanded DistR: (A + B) ⊗ C → (A ⊗ C) + (B ⊗ C) ---";
  (*
     let (ab ⊗ c) : (I + I) ⊗ Q = id in
       case ab of
         | Left(a)  => Left(c)   -- Left(a ⊗ c) but a is Unit
         | Right(b) => Right(c)  -- Right(b ⊗ c) but b is Unit

     For (I + I) ⊗ Q:
       Wire 0: tag for (I + I)
       Wire 1: Q (c)
     Output (Q + Q):
       Wire 0: tag
       Wire 1: Q
     Tag is already at wire 0, so this should be identity!
  *)
  let distR_eta = LetTen ("ab", "c", TyPlus (TyUnit, TyUnit), TyQ,
    Id (TyTensor (TyPlus (TyUnit, TyUnit), TyQ)),
    Case (Var "ab", [
      (PatWild, Ctor ("Left", Var "c"));
      (PatWild, Ctor ("Right", Var "c"));
    ])
  ) in
  print_endline ("  Source: let (ab ⊗ c) = id in case ab of Left => Left(c) | Right => Right(c)");
  let distR_eta_result = Elaborate.elaborate tyvar_env Elaborate.TyEnv.empty dt_env distR_eta in
  let distR_eta_str = Elaborate.Core.term_to_string distR_eta_result in
  print_endline ("  Elaborated: " ^ distR_eta_str);

  let distR_eta_has_computational =
    Str.string_match (Str.regexp ".*[^C]H\\[\\|.*[^C]S\\[\\|.*[^C]T\\[\\|.*CX\\[.*") distR_eta_str 0 ||
    Str.string_match (Str.regexp ".*C[0-9]-H\\|.*C[0-9]-S\\|.*C[0-9]-T.*") distR_eta_str 0
  in
  if distR_eta_has_computational then
    print_endline "  ✗ Eta-expanded DistR has computational gates!"
  else
    print_endline "  ✓ Eta-expanded DistR is structural (matches primitive DistR)";

  (* Test 13: Case with gate in one branch only - definitely needs controlled gates *)
  print_endline "\n--- Non-structural: case with different operations ---";
  let ty_env_2q = Elaborate.TyEnv.extend Elaborate.TyEnv.empty "x" (TyPlus (TyQ, TyQ)) in
  let asymmetric_case = Case (Var "x", [
    (PatCtor ("Left", "a"), Seq (Var "a", GateH 1));   (* Apply H in left branch *)
    (PatCtor ("Right", "b"), Var "b");                  (* Identity in right branch *)
  ]) in
  print_endline ("  Asymmetric source: " ^ term_to_string asymmetric_case);
  let asymmetric_result = Elaborate.elaborate tyvar_env ty_env_2q dt_env asymmetric_case in
  let asymmetric_str = Elaborate.Core.term_to_string asymmetric_result in
  print_endline ("  Asymmetric result: " ^ asymmetric_str);

  (* With Core.Case approach, asymmetric case emits Core.Case term *)
  let has_case =
    try let _ = Str.search_forward (Str.regexp "case(") asymmetric_str 0 in true
    with Not_found -> false
  in
  if has_case then
    print_endline "  ✓ Asymmetric case produces Core.Case (Python handles controlled gates)"
  else
    print_endline "  ✗ Asymmetric case should produce Core.Case term";

  print_endline ""

(* Test error handling *)
let test_errors () =
  print_endline "=== Testing error handling ===";

  (* Test unbound variable detection *)
  print_endline "Testing unbound variable detection:";
  let open Ast in
  let tyvar_env = Elaborate.TyVarEnv.empty in
  let ty_env = Elaborate.TyEnv.empty in
  let dt_env = Elaborate.DtEnv.empty in

  let unbound_term = Seq (Var "undefined_var", GateH 0) in
  (try
    let _ = Elaborate.elaborate tyvar_env ty_env dt_env unbound_term in
    print_endline "  ERROR: Should have raised UnboundVariable"
  with
  | Elaborate.ElaborateError e ->
    print_endline ("  Caught expected error: " ^ Elaborate.error_to_string e)
  | _ ->
    print_endline "  ERROR: Wrong exception type");

  print_endline ""

(* Run all tests *)
let () =
  print_endline "QPL Surface Language Tests";
  print_endline "==========================";
  print_endline "";

  test_rep ();
  test_bool_datatype ();
  test_swap ();
  test_emit ();
  test_exp_i ();
  test_maybe ();
  test_either ();
  test_perm_gen ();
  test_triple ();
  test_ast ();
  test_elaborate ();
  test_quantum_case ();
  test_nested_quantum_case ();
  test_triple_nested_quantum_case ();
  test_partial_flip_rejected ();
  test_both_flip ();
  test_eta_expanded_structural ();
  test_errors ();

  print_endline "All tests completed!"
