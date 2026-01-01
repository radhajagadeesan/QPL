(** Qpl: Main entry point for the QPL surface language.

    This module re-exports the core functionality and provides
    convenience functions for common operations.
*)

module Rep = Rep
module Datatype = Datatype
module Emit = Emit

(** Example: Bool datatype registration *)
module Bool = Datatype.Make2(struct
  type ('a, 'b) t = F of 'a | T of 'b
  [@@warning "-37"]  (* Constructors used for type definition, not runtime *)

  let name = "Bool"

  (* Canonical representation: A (+) B *)
  let rep = Rep.(plus (var 0) (var 1))

  let constructors = [
    ("F", Rep.var 0);
    ("T", Rep.var 1);
  ]
end)

(** Check if a structural term is involutive.

    This is done by:
    1. Emitting Python code for the term
    2. Compiling with materialize=False to get WirePerm
    3. Checking p o p = id

    For now, we provide a placeholder that will call the Python compiler.
*)
let check_involution _term =
  (* TODO: Call Python compiler and check p o p = id *)
  failwith "check_involution: not yet implemented - requires Python integration"

(** Emit exp_i for a certified involution. *)
let exp_i ~theta ~j =
  (* First, verify J is involutive *)
  (* check_involution j; *)
  let j_hash = "todo_hash" in  (* TODO: compute canonical hash *)
  Emit.exp_i_to_python ~theta ~j_name:j ~j_hash

(** Print library info *)
let info () =
  print_endline "QPL Surface Language v0.1.0";
  print_endline "Embedded OCaml DSL for quantum programming";
  print_endline "";
  print_endline "Available modules:";
  print_endline "  Rep      - Type representations (⊗, +)";
  print_endline "  Datatype - Datatype registration functors";
  print_endline "  Emit     - Python code generation"
