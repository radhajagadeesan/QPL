(** Linear DSL Demo: GADT-enforced linear contexts.

    This demonstrates that OCaml's type system enforces linearity.
*)

open Qpl_surface
open Linear

(* ============================================================ *)
(* Example 1: Closed terms (context = unit)                     *)
(* ============================================================ *)

(* Hadamard is closed: Prog(∅, Q ⊸ Q) *)
let _ : (unit, _) prog = gate_h

(* Identity is closed *)
let _ : (unit, _) prog = id q

(* Composition of closed terms is closed - must use seq0 *)
let hh : (unit, _) prog = seq0 gate_h gate_h

(* Structural isos are closed *)
let swap_qq : (unit, _) prog = twist_tensor q q

(* ============================================================ *)
(* Example 2: Context splitting                                 *)
(* ============================================================ *)

(* Pair splits context: Prog(Γ1, A) -> Prog(Γ2, B) -> Prog(Γ1 * Γ2, A ⊗ B) *)

(* Two closed terms: unit * unit context *)
let _closed_pair : (unit * unit, _) prog = pair gate_h gate_s

(* ============================================================ *)
(* Example 3: Variables and Lambda                              *)
(* ============================================================ *)

(* A variable in singleton context *)
let _x_var : ([`Q] * unit, [`Q]) prog = var

(* Lambda removes variable from context *)
(* lam : 'a ty -> 'b ty -> ('a * 'g, 'b) prog -> ('g, 'a ⊸ 'b) prog *)
let id_lam : (unit, _) prog = lam q q var

(* Apply closed gate to a variable: app splits context *)
(* app : Prog(Γ1, A ⊸ B) -> Prog(Γ2, A) -> Prog(Γ1 * Γ2, B) *)
(* Here: H is closed (unit), var is in (Q * unit), result is (unit * (Q * unit), Q) *)
let _h_applied : (unit * ([`Q] * unit), [`Q]) prog = app gate_h var

(* Parallel composition of closed terms *)
let h_par_s : (unit, _) prog = par0 gate_h gate_s

(* ============================================================ *)
(* Example 4: Meta-level combinators (iterate, fold)            *)
(* ============================================================ *)

(* iterate 3 q gate_h = H ; H ; H *)
let h3 : (unit, _) prog = iterate 3 q gate_h

(* iterate 0 returns identity - type is preserved! *)
let id_from_iterate : (unit, [`Lolli of [`Q] * [`Q]]) prog = iterate 0 q gate_h

(* fold composes a list of gates *)
let hsh : (unit, _) prog = fold q [gate_h; gate_s; gate_h]

(* pow2 generates f^(2^n) efficiently *)
let h8 : (unit, _) prog = pow2 3 q gate_h  (* H^8 *)

(* indexed_fold for parameterized sequences *)
let _rz_sequence : (unit, _) prog =
  indexed_fold 4 q (fun i -> gate_rz (Float.pi /. float_of_int (i + 1)))

(* ============================================================ *)
(* Example 5: What DOESN'T compile (linearity violations)       *)
(* ============================================================ *)

(* UNCOMMENT TO SEE TYPE ERRORS:

(* Can't use a variable twice - context is consumed *)
let bad_dup : _ prog = pair var var
(* Error: var has context ('a * unit), but pair needs disjoint contexts *)

(* Note: Unit intro/elim (unit, letunit) are not in the source language.
   Unit exists only as a type for sum payloads like Bool = I + I. *)

*)

(* ============================================================ *)
(* Example 5: Emit to Bridge.term                               *)
(* ============================================================ *)

let () =
  print_endline "=== Linear DSL Demo ===\n";

  print_endline "Closed H gate:";
  print_endline ("  " ^ Bridge.term_to_json (emit gate_h));
  print_endline "";

  print_endline "H ; H composition:";
  print_endline ("  " ^ Bridge.term_to_json (emit hh));
  print_endline "";

  print_endline "Twist(Q,Q):";
  print_endline ("  " ^ Bridge.term_to_json (emit swap_qq));
  print_endline "";

  print_endline "Lambda (identity):";
  print_endline ("  " ^ Bridge.term_to_json (emit id_lam));
  print_endline "";

  print_endline "H || S (parallel composition):";
  print_endline ("  " ^ Bridge.term_to_json (emit h_par_s));
  print_endline "";

  print_endline "iterate 3 q H (= H ; H ; H):";
  print_endline ("  " ^ Bridge.term_to_json (emit h3));
  print_endline "";

  print_endline "iterate 0 q H (= id):";
  print_endline ("  " ^ Bridge.term_to_json (emit id_from_iterate));
  print_endline "";

  print_endline "fold q [H; S; H]:";
  print_endline ("  " ^ Bridge.term_to_json (emit hsh));
  print_endline "";

  print_endline "pow2 3 q H (= H^8):";
  print_endline ("  " ^ Bridge.term_to_json (emit h8));
  print_endline "";

  print_endline "=== End Demo ==="
