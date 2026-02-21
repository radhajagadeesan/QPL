(** Algorithmic Snippets using the Linear GADT Module

    All examples use the GADT-enforced Linear DSL:
    - Linearity checked at OCaml compile time
    - Full E2E compilation via Bridge -> Python -> Circuit
    - No Ast module -- everything is verified, real code
*)

open Qpl_surface
open Linear

let compile_and_report name term =
  Printf.printf "\n%s:\n" name;
  match Bridge.compile_show term with
  | Bridge.CompileOk _ -> ()
  | Bridge.CompileError err ->
      Printf.printf "  FAILED: %s\n" err

(* ================================================================== *)
(* Bell State: (H tensor id) ; CX                                     *)
(* ================================================================== *)

let bell = seq0 (par0 gate_h (id q)) gate_cx

(* ================================================================== *)
(* GHZ State (3 qubits): H on q0, CX on (q0,q1), CX on (q0,q2)      *)
(* ================================================================== *)

let ghz =
  let qq = q ** q in
  let step1 = par0 gate_h (id qq) in
  let step2 =
    seq0 (assoc_tensor_r q q q)
      (seq0 (par0 gate_cx (id q))
         (assoc_tensor_l q q q))
  in
  let step3 =
    seq0 (par0 (id q) (twist_tensor q q))
      (seq0 (assoc_tensor_r q q q)
        (seq0 (par0 gate_cx (id q))
          (seq0 (assoc_tensor_l q q q)
            (par0 (id q) (twist_tensor q q)))))
  in
  seq0 step1 (seq0 step2 step3)

(* ================================================================== *)
(* Deutsch-Jozsa: parameterized on oracle                             *)
(* ================================================================== *)

let deutsch_core uf =
  seq0 (par0 gate_h (id q)) (seq0 uf (par0 gate_h (id q)))

let dj_constant = deutsch_core (id (q ** q))
let dj_balanced = deutsch_core gate_cx

(* ================================================================== *)
(* HSP Standard Form (functor)                                        *)
(* ================================================================== *)

module type HSP_PARAMS = sig
  type g
  type x
  val g_ty : g ty
  val x_ty : x ty
  val uf    : (unit, [`Lolli of [`Tensor of g * x] * [`Tensor of g * x]]) prog
  val qft_g : (unit, [`Lolli of g * g]) prog
end

module HSP_Core (P : HSP_PARAMS) = struct
  let circuit = seq0 P.uf (par0 P.qft_g (id P.x_ty))
  let _input_ty = P.g_ty ** P.x_ty
end

module DJ_as_HSP = HSP_Core(struct
  type g = [`Q]
  type x = [`Q]
  let g_ty = q
  let x_ty = q
  let uf = gate_cx
  let qft_g = gate_h
end)

(* ================================================================== *)
(* Simon's Algorithm (functor)                                        *)
(* ================================================================== *)

module type SIMON_PARAMS = sig
  type z
  type y
  val z_ty  : z ty
  val y_ty  : y ty
  val uf    : (unit, [`Lolli of [`Tensor of z * y] * [`Tensor of z * y]]) prog
  val qft_z : (unit, [`Lolli of z * z]) prog
end

module Simon_Core (S : SIMON_PARAMS) = struct
  let circuit = seq0 S.uf (par0 S.qft_z (id S.y_ty))
  let _input_ty = S.z_ty ** S.y_ty
end

module Simon_1q = Simon_Core(struct
  type z = [`Q]
  type y = [`Q]
  let z_ty = q
  let y_ty = q
  let uf = gate_cx
  let qft_z = gate_h
end)

(* ================================================================== *)
(* Swap via structural isomorphism (Bool = I + I)                      *)
(* ================================================================== *)

let swap_bool = twist_plus one one

(* ================================================================== *)
(* Main: Print and compile all snippets                                *)
(* ================================================================== *)

let () =
  let project_root = Filename.dirname (Sys.getcwd ()) in
  Bridge.set_project_root project_root;

  print_endline "=== Algorithmic Snippets (Linear GADT) ===\n";

  print_endline "All examples verified by OCaml's type system (linearity)";
  print_endline "and compiled E2E via Bridge -> Python -> pytket.\n";

  compile_and_report "Bell state: (H || id) ; CX" (emit bell);
  compile_and_report "GHZ state (3 qubits)" (emit ghz);
  compile_and_report "DJ constant (oracle = id)" (emit dj_constant);
  compile_and_report "DJ balanced (oracle = CX)" (emit dj_balanced);
  compile_and_report "HSP (G=Q, X=Q) = DJ" (emit DJ_as_HSP.circuit);
  compile_and_report "Simon (Z=Q, Y=Q)" (emit Simon_1q.circuit);
  compile_and_report "Swap Bool (twist_plus)" (emit swap_bool);

  print_endline "\n=== End of Snippets ==="
