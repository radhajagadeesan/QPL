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

  print_endline "All tests completed!"
