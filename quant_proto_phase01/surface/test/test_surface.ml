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

  (* Build a quantum case expression:
     case q of
       | Zero(u) => S[1] ; H[1]    (left branch: S then H on payload wire)
       | One(u)  => H[1] ; S[1]    (right branch: H then S on payload wire)

     This is the quantum switch pattern.
     Wire 0 is the tag qubit, Wire 1 is the payload.

     Expected elaboration (anti-controlled-left ; controlled-right):
     X[0] ; CS[0,1] ; CH[0,1] ; X[0] ; CH[0,1] ; CS[0,1]
  *)
  let open Ast in
  let tyvar_env = Elaborate.TyVarEnv.empty in
  (* Add 'q' to the type environment with type QBool = (I + I) *)
  let ty_env = Elaborate.TyEnv.extend Elaborate.TyEnv.empty "q" (TyPlus (TyUnit, TyUnit)) in
  let dt_env = Elaborate.DtEnv.empty in

  let qswitch_case = Case (Var "q", [
    (PatCtor ("Zero", "u"), Seq (GateS 1, GateH 1));
    (PatCtor ("One", "u"), Seq (GateH 1, GateS 1));
  ]) in

  print_endline ("  Source: " ^ term_to_string qswitch_case);

  let elaborated = Elaborate.elaborate tyvar_env ty_env dt_env qswitch_case in
  print_endline ("  Elaborated: " ^ Elaborate.Core.term_to_string elaborated);

  (* Verify the structure contains controlled gates *)
  let result_str = Elaborate.Core.term_to_string elaborated in
  if String.length result_str > 0 &&
     (String.sub result_str 0 1 = "X" ||
      (String.length result_str > 2 && String.sub result_str 0 2 = "CH") ||
      (String.length result_str > 2 && String.sub result_str 0 2 = "CS"))
  then
    print_endline "  ✓ Elaboration contains controlled gates"
  else
    print_endline ("  Result starts with: " ^ (if String.length result_str > 10 then String.sub result_str 0 10 else result_str));

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
  test_errors ();

  print_endline "All tests completed!"
