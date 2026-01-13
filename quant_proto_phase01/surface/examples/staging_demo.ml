(** Staging Demo: Meta-Level Combinators for Generating Quantum Programs

    This demonstrates OCaml as a staging language for the linear λ-calculus.
    OCaml provides:
    - Unrestricted iteration (iterate, fold)
    - Free copying/discarding of code values
    - Program generators that produce well-typed object terms

    The generated programs live in a linear λ-calculus with proper
    resource tracking - linearity is enforced at the object level,
    not the meta (OCaml) level.
*)

open Qpl_surface
open Staging

(* ================================================================== *)
(* Example 1: iterate - Apply a morphism n times                      *)
(* ================================================================== *)

(**
   iterate n ty f = f ; f ; ... ; f   (n times)

   This is a META-LEVEL combinator: the iteration happens in OCaml,
   producing an OBJECT-LEVEL term (sequence of f's).

   Usage: iterate 3 q (h 0 q) produces H ; H ; H
*)

let iterate_demo () =
  (* Apply Hadamard 3 times *)
  let h3 = iterate 3 q (h 0 q) in
  print_endline "iterate 3 q (H[0]) = H ; H ; H";
  print_endline ("  Term: " ^ Bridge.term_to_json (to_bridge h3));
  print_endline ""

(* ================================================================== *)
(* Example 2: fold - Compose a list of morphisms                      *)
(* ================================================================== *)

(**
   fold [f1; f2; f3] = f1 ; f2 ; f3

   Useful when you have a list of stages to compose.
*)

let fold_demo () =
  (* Compose H, S, T on a single qubit *)
  let hst = fold q [h 0 q; s 0 q; t 0 q] in
  print_endline "fold [H; S; T] = H ; S ; T";
  print_endline ("  Term: " ^ Bridge.term_to_json (to_bridge hst));
  print_endline ""

(* ================================================================== *)
(* Example 3: indexed_fold - Stage-dependent generation               *)
(* ================================================================== *)

(**
   indexed_fold n gen = gen(0) ; gen(1) ; ... ; gen(n-1)

   The generator `gen` is called at the meta-level with each index,
   producing different stages for different indices.

   This is the key combinator for phase estimation and QFT:
   the rotation angle depends on the stage index.
*)

let indexed_fold_demo () =
  (* Generate a sequence of Rz gates with increasing angles *)
  let pi = Float.pi in
  let rz_sequence = indexed_fold 4 q (fun k ->
    (* Rz by π/2^k *)
    rz (pi /. Float.pow 2.0 (Float.of_int k)) 0 q
  ) in
  print_endline "indexed_fold 4 (k -> Rz[π/2^k, 0])";
  print_endline "  = Rz[π/1] ; Rz[π/2] ; Rz[π/4] ; Rz[π/8]";
  print_endline ("  Term: " ^ Bridge.term_to_json (to_bridge rz_sequence));
  print_endline ""

(* ================================================================== *)
(* Example 4: power_of_2 - Efficient exponentiation                   *)
(* ================================================================== *)

(**
   power_of_2 n f = f^(2^n)

   Uses repeated squaring at the meta-level:
   - power_of_2 0 f = f
   - power_of_2 1 f = f ; f
   - power_of_2 2 f = f ; f ; f ; f
   - power_of_2 3 f = f ; f ; f ; f ; f ; f ; f ; f

   More efficient term size than iterate (2^n) for large n
   when combined with evaluation.
*)

let power_of_2_demo () =
  (* H^4 via repeated squaring *)
  let h4 = power_of_2 2 (h 0 q) in
  print_endline "power_of_2 2 (H[0]) = H ; H ; H ; H";
  print_endline ("  Term: " ^ Bridge.term_to_json (to_bridge h4));
  print_endline ""

(* ================================================================== *)
(* Example 5: exp_i on involutions                                    *)
(* ================================================================== *)

(**
   exp_i θ P = cos(θ)·id + i·sin(θ)·P   where P² = id

   For structural involutions (twist, etc.), this compiles to
   ExpSwap gates on the transpositions.
*)

let exp_i_demo () =
  (* TwistTen(Q,Q) is an involution: swap ; swap = id *)
  let _qq = tensor q q in
  let swap_invol = invol_twist_ten q q in
  let exp_swap = exp_i (Float.pi /. 4.0) swap_invol in
  print_endline "exp_i(π/4, twist⊗[Q,Q])";
  print_endline "  = cos(π/4)·id + i·sin(π/4)·SWAP";
  print_endline ("  Term: " ^ Bridge.term_to_json (to_bridge exp_swap));
  print_endline ""

(* ================================================================== *)
(* Example 6: Combining staging with structural operations            *)
(* ================================================================== *)

(**
   The real power is combining meta-level iteration with
   structural (free) operations.

   Example: Phase estimation prep requires indexed controlled rotations.
*)

let combined_demo () =
  let _pi = Float.pi in
  let qq = tensor q q in

  (* Build: H[0] ; CRz[π/2, 0, 1] ; CRz[π/4, 0, 2] ; ... *)
  let phase_est_prep n =
    let initial = h 0 qq in
    let rotations = indexed_fold n qq (fun k ->
      (* CRz by π/2^k - but we don't have crz in simple API yet *)
      (* For demo, use simpler gates *)
      h k qq
    ) in
    seq initial rotations
  in

  let prep3 = phase_est_prep 2 in
  print_endline "Phase estimation prep (simplified):";
  print_endline "  H[0] ; H[0] ; H[1]";
  print_endline ("  Term: " ^ Bridge.term_to_json (to_bridge prep3));
  print_endline ""

(* ================================================================== *)
(* Main: Run all demos                                                *)
(* ================================================================== *)

let () =
  print_endline "=== Staging Demo: Meta-Level Combinators ===\n";

  print_endline "Key insight: OCaml iteration produces object terms.";
  print_endline "Linearity is enforced at the object level, not meta level.\n";
  print_endline (String.make 60 '-');
  print_endline "";

  iterate_demo ();
  fold_demo ();
  indexed_fold_demo ();
  power_of_2_demo ();
  exp_i_demo ();
  combined_demo ();

  print_endline "=== End of Staging Demo ==="
