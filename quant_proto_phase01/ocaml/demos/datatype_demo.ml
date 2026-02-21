(** Datatype Demo: Surface-level datatype declarations.

    Demonstrates the datatype declaration system following the spec:
    - Finite datatypes with compile-time fixed arity k
    - No constructors, case analysis, or observation
    - Operations as primitive constants
    - Elaborates to I^{⊕k}
*)

open Qpl_surface
open Linear

(* ============================================================ *)
(* Example 1: Bool datatype (arity 2)                           *)
(* ============================================================ *)

let bool = datatype
  ~name:"Bool"
  ~arity:2
  ~labels:["false"; "true"]
  ~ops:[
    ("H", lolli self self);
    ("X", lolli self self);
  ]

(* bool.rep is I ⊕ I *)
(* bool.op "H" : (unit, [`Lolli of Bool * Bool]) prog *)
(* bool.op "X" : (unit, [`Lolli of Bool * Bool]) prog *)

(* Compose operations *)
let hx = seq0 (op bool "H") (op bool "X")

(* ============================================================ *)
(* Example 2: Group G[8] datatype (arity 8)                     *)
(* ============================================================ *)

let g8 = datatype
  ~name:"G"
  ~arity:8
  ~labels:["e"; "g1"; "g2"; "g3"; "g4"; "g5"; "g6"; "g7"]
  ~ops:[
    ("mul", lolli (self **. self) (self **. self));
    ("inv", lolli self self);
  ]

(* g8.rep is I ⊕ (I ⊕ (I ⊕ (I ⊕ (I ⊕ (I ⊕ (I ⊕ I)))))) *)

(* ============================================================ *)
(* Example 3: Using rep_ty in other operations                  *)
(* ============================================================ *)

(* Once a datatype is declared, its rep_ty can be used in other ops *)
let _bool_ty = rep_ty bool
let _g8_ty = rep_ty g8

(* ============================================================ *)
(* Example 4: Control combinator                                *)
(* ============================================================ *)

(* Coherent control: apply different operations based on datatype value *)
let controlled_hx = control bool q [| gate_h; gate_x |]
(* Type: Bool ⊗ Q ⊸ Bool ⊗ Q *)
(* Applies H when false, X when true - coherently *)

(* ============================================================ *)
(* Example 5: Finite cyclic group Z_n                           *)
(*                                                              *)
(* G = Z_n with:                                                *)
(*   mul : G ⊗ G ⊸ G ⊗ G                                        *)
(*   inv : G ⊸ G                                                *)
(*                                                              *)
(* For each g ∈ Z_n, define P_g : A ⊸ A as phase rotation       *)
(* by angle 2πg/n (i.e., Rz(2πg/n)).                            *)
(*                                                              *)
(* The coherent selector:                                       *)
(*   λg. case g of 0 => P_0 | 1 => P_1 | ... | (n-1) => P_{n-1} *)
(*                                                              *)
(* is NOT observational - it specifies coherent selection of    *)
(* programs indexed by the group element.                       *)
(*                                                              *)
(* The control combinator assembles this into:                  *)
(*   A ⊗ G ⊸ A ⊗ G                                              *)
(* ============================================================ *)

(** Create Z_n datatype for a given n *)
let z_n n =
  let labels = List.init n (fun i -> string_of_int i) in
  datatype
    ~name:(Printf.sprintf "Z%d" n)
    ~arity:n
    ~labels
    ~ops:[
      ("mul", lolli (self **. self) (self **. self));
      ("inv", lolli self self);
    ]

(** Phase rotation P_g = Rz(2πg/n) for g ∈ Z_n *)
let phase_rotation n g =
  let theta = 2.0 *. Float.pi *. (float_of_int g) /. (float_of_int n) in
  gate_rz theta

(** Build array of phase rotations [P_0; P_1; ...; P_{n-1}] *)
let phase_rotations n =
  Array.init n (phase_rotation n)

(* Concrete example: Z_4 *)
let z4 = z_n 4

(* The coherent selector: g ↦ P_g
   This is the "case" that specifies coherent selection without observation *)
let z4_phases = phase_rotations 4

(* The control combinator: A ⊗ Z_4 ⊸ A ⊗ Z_4
   Applies P_g when the control register holds |g⟩, coherently *)
let z4_controlled_phase = control z4 q z4_phases

(* Larger example: Z_8 *)
let z8 = z_n 8
let z8_phases = phase_rotations 8
let z8_controlled_phase = control z8 q z8_phases

(* ============================================================ *)
(* Helpers                                                      *)
(* ============================================================ *)

let compile_and_report name term =
  Printf.printf "\n%s:\n" name;
  match Bridge.compile_show term with
  | Bridge.CompileOk _ -> ()
  | Bridge.CompileError err ->
      Printf.printf "  FAILED: %s\n" err

(* ============================================================ *)
(* Main: Print demo output + E2E compile                        *)
(* ============================================================ *)

let () =
  let project_root = Filename.dirname (Sys.getcwd ()) in
  Bridge.set_project_root project_root;

  print_endline "=== Datatype Declaration Demo ===\n";

  print_endline "--- Bool datatype ---";
  print_endline (Printf.sprintf "  Name: %s" bool.name);
  print_endline (Printf.sprintf "  Arity: %d" bool.arity);
  print_endline (Printf.sprintf "  Labels: [%s]" (String.concat "; " bool.labels));
  print_endline (Printf.sprintf "  Rep (I^{⊕2}): %s" (Rep.to_string bool.rep));
  print_endline "";

  print_endline "--- G[8] datatype ---";
  print_endline (Printf.sprintf "  Name: %s" g8.name);
  print_endline (Printf.sprintf "  Arity: %d" g8.arity);
  print_endline (Printf.sprintf "  Labels: [%s]" (String.concat "; " g8.labels));
  print_endline (Printf.sprintf "  Rep (I^{⊕8}): %s" (Rep.to_string g8.rep));
  print_endline "";

  print_endline "--- Operations ---";
  print_endline "Bool.H:";
  print_endline (Printf.sprintf "  %s" (Bridge.term_to_json (emit (op bool "H"))));
  print_endline "Bool.X:";
  print_endline (Printf.sprintf "  %s" (Bridge.term_to_json (emit (op bool "X"))));
  print_endline "Bool.H ; Bool.X:";
  print_endline (Printf.sprintf "  %s" (Bridge.term_to_json (emit hx)));
  print_endline "";

  print_endline "G.mul:";
  print_endline (Printf.sprintf "  %s" (Bridge.term_to_json (emit (op g8 "mul"))));
  print_endline "G.inv:";
  print_endline (Printf.sprintf "  %s" (Bridge.term_to_json (emit (op g8 "inv"))));
  print_endline "";

  print_endline "--- Control combinator ---";
  print_endline "control Bool Q [H; X]:";
  print_endline (Printf.sprintf "  %s" (Bridge.term_to_json (emit controlled_hx)));
  print_endline "";

  print_endline "--- I^{⊕k} generation ---";
  print_endline (Printf.sprintf "  i_sum 1 = %s" (Rep.to_string (i_sum 1)));
  print_endline (Printf.sprintf "  i_sum 2 = %s" (Rep.to_string (i_sum 2)));
  print_endline (Printf.sprintf "  i_sum 3 = %s" (Rep.to_string (i_sum 3)));
  print_endline (Printf.sprintf "  i_sum 4 = %s" (Rep.to_string (i_sum 4)));
  print_endline "";

  print_endline "--- Cyclic group Z_n example ---";
  print_endline "";
  print_endline "Z_4 datatype:";
  print_endline (Printf.sprintf "  Name: %s" z4.name);
  print_endline (Printf.sprintf "  Arity: %d" z4.arity);
  print_endline (Printf.sprintf "  Labels: [%s]" (String.concat "; " z4.labels));
  print_endline (Printf.sprintf "  Rep (I^{⊕4}): %s" (Rep.to_string z4.rep));
  print_endline "";

  print_endline "Phase rotations P_g = Rz(2πg/4):";
  for g = 0 to 3 do
    let theta = 2.0 *. Float.pi *. (float_of_int g) /. 4.0 in
    print_endline (Printf.sprintf "  P_%d = Rz(%.4f) = Rz(%dπ/2)" g theta g)
  done;
  print_endline "";

  print_endline "Coherent selector (NOT observational case):";
  print_endline "  λg. case g of 0 => P_0 | 1 => P_1 | 2 => P_2 | 3 => P_3";
  print_endline "";

  print_endline "Control combinator (A ⊗ Z_4 ⊸ A ⊗ Z_4):";
  print_endline (Printf.sprintf "  %s" (Bridge.term_to_json (emit z4_controlled_phase)));
  print_endline "";

  print_endline "Z_8 datatype:";
  print_endline (Printf.sprintf "  Name: %s" z8.name);
  print_endline (Printf.sprintf "  Arity: %d" z8.arity);
  print_endline (Printf.sprintf "  Rep (I^{⊕8}): %s" (Rep.to_string z8.rep));
  print_endline "";

  print_endline "Phase rotations P_g = Rz(2πg/8):";
  for g = 0 to 7 do
    let theta = 2.0 *. Float.pi *. (float_of_int g) /. 8.0 in
    print_endline (Printf.sprintf "  P_%d = Rz(%.4f) = Rz(%dπ/4)" g theta g)
  done;
  print_endline "";

  print_endline "Control combinator (A ⊗ Z_8 ⊸ A ⊗ Z_8):";
  print_endline (Printf.sprintf "  %s" (Bridge.term_to_json (emit z8_controlled_phase)));
  print_endline "";

  print_endline "--- E2E Compilation via Bridge ---";
  print_endline "(Note: control combinator emits opaque Gate terms that require";
  print_endline " datatype-aware compilation. Only primitive ops compile E2E.)";

  compile_and_report "Bool.H ; Bool.X" (emit hx);

  print_endline "\n=== End Demo ==="
