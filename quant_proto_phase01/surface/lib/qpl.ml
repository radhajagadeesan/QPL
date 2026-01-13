(** Qpl: Main entry point for the QPL surface language.

    This module re-exports the core functionality and provides
    convenience functions for common operations.
*)

module Rep = Rep
module Datatype = Datatype
module Emit = Emit
module Bridge = Bridge
module Staging = Staging

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

(** Result of involution certification *)
type involution_check =
  | Involutive of Bridge.wire_perm
  | NotInvolutive of Bridge.wire_perm
  | CheckError of string

(** Check if a structural term is involutive.

    This compiles the term through the Python Phase 0-4C pipeline
    and checks if the resulting permutation satisfies p ∘ p = id.
*)
let check_involution term =
  match Bridge.check_involution term with
  | Bridge.InvolutionOk (true, perm) -> Involutive perm
  | Bridge.InvolutionOk (false, perm) -> NotInvolutive perm
  | Bridge.InvolutionError err -> CheckError err

(** Certify and emit exp_i for an involution.

    Returns Error if the term is not involutive.
*)
let exp_i ~theta ~j_term ~j_name =
  match check_involution j_term with
  | Involutive perm ->
    (* Compute hash from the permutation *)
    let j_hash = Printf.sprintf "perm_%d_%s"
      perm.n
      (String.concat "_" (List.map string_of_int perm.new_to_old))
    in
    Ok (Emit.exp_i_to_python ~theta ~j_name ~j_hash)
  | NotInvolutive _ ->
    Error (Printf.sprintf "%s is not involutive (p ∘ p ≠ id)" j_name)
  | CheckError err ->
    Error (Printf.sprintf "Failed to check involution: %s" err)

(** Create a swap term for a 2-constructor datatype.
    For Bool[A,B] = F of A | T of B, swap : Bool[A,B] -> Bool[B,A].
*)
let swap_term () =
  Bridge.TTwistPlus (Rep.var 0, Rep.var 1)

(** Print library info *)
let info () =
  print_endline "QPL Surface Language v0.1.0";
  print_endline "Embedded OCaml DSL for quantum programming";
  print_endline "";
  print_endline "Available modules:";
  print_endline "  Rep      - Type representations (⊗, +)";
  print_endline "  Datatype - Datatype registration functors";
  print_endline "  Emit     - Python code generation";
  print_endline "  Bridge   - Python compiler integration";
  print_endline "  Staging  - Meta-level combinators (iterate, fold, pow2)"
