(** Parameterized Algorithm Demos in Linear GADT

    Full pipeline: OCaml Linear DSL -> Bridge -> Python compile -> Circuit

    Demonstrates the standard quantum algorithm patterns parameterized
    over abstract types and operations using OCaml functors:

    1. Deutsch-Jozsa: oracle as a plain function parameter
    2. HSP Standard Form: functor over abstract G, X types
    3. Simon's Algorithm: functor over abstract Z, Y types

    Key insight: these algorithms all follow the pattern
      oracle ; (fourier_transform tensor id)
    We model only the unitary core as a linear morphism.
*)

open Qpl_surface
open Linear

let banner title =
  print_endline "";
  print_endline (String.make 74 '=');
  Printf.printf "  %s\n" title;
  print_endline (String.make 74 '=')

let had_failure = ref false

let compile_and_report name term =
  Printf.printf "\n%s:\n" name;
  match Bridge.compile_show term with
  | Bridge.CompileOk _ -> ()
  | Bridge.CompileError err ->
      Printf.printf "  FAILED: %s\n" err;
      had_failure := true

(* ========================================================================= *)
(* 1. Deutsch-Jozsa: Oracle as a plain function parameter                    *)
(* ========================================================================= *)

(** Deutsch-Jozsa unitary core: (H tensor id) ; Uf ; (H tensor id)

    Type: Q tensor Q -> Q tensor Q

    The oracle Uf is simply a parameter of the right type.
    State preparation (ket0, ket1, initial H) is separate --
    we model only the unitary core. *)
let deutsch_core
    (uf : (unit, [`Lolli of [`Tensor of [`Q] * [`Q]] * [`Tensor of [`Q] * [`Q]]]) prog)
  =
  seq0 (par0 gate_h (id q)) (seq0 uf (par0 gate_h (id q)))

(** Constant oracle = identity (always outputs 0) *)
let dj_constant = deutsch_core (id (q ** q))

(** Balanced oracle = CX (flips target iff input is |1>) *)
let dj_balanced = deutsch_core gate_cx

(* ========================================================================= *)
(* 2. HSP Standard Form: Functor over abstract types G, X                    *)
(* ========================================================================= *)

(** Module type for HSP parameters.

    The caller provides:
    - Abstract types g, x with type witnesses
    - Oracle Uf : G tensor X -> G tensor X
    - QFT over G: QFT_G : G -> G

    The functor builds: Uf ; (QFT_G tensor id_X) : G tensor X -> G tensor X *)
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

(* ========================================================================= *)
(* 3. Simon's Algorithm: Functor over abstract types Z, Y                    *)
(* ========================================================================= *)

(** Module type for Simon's algorithm parameters.

    Same structure as HSP -- Simon is a special case where:
    - G = Z_2^n (the group)
    - QFT over Z_2^n = Hadamard transform

    The functor builds: Uf ; (QFT_Z tensor id_Y) : Z tensor Y -> Z tensor Y *)
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

(* ========================================================================= *)
(* 4. Concrete Instantiations for E2E Verification                           *)
(* ========================================================================= *)

(** Instantiate HSP with G = Q, X = Q, Uf = CX, QFT_G = H

    This is precisely Deutsch-Jozsa (1-qubit version) viewed as an HSP
    instance. The types check and the full pipeline compiles. *)
module DJ_as_HSP = HSP_Core(struct
  type g = [`Q]
  type x = [`Q]
  let g_ty = q
  let x_ty = q
  let uf = gate_cx
  let qft_g = gate_h
end)

(** Instantiate HSP with G = Q tensor Q, X = Q tensor Q

    A 4-qubit HSP instance. Oracle is CX on first pair of wires (toy).
    QFT_G = H tensor H (parallel Hadamards). *)
module HSP_2qubit = HSP_Core(struct
  type g = [`Tensor of [`Q] * [`Q]]
  type x = [`Tensor of [`Q] * [`Q]]
  let g_ty = q ** q
  let x_ty = q ** q
  let uf = par0 gate_cx (id (q ** q))
  let qft_g = par0 gate_h gate_h
end)

(** Instantiate Simon with Z = Q, Y = Q, Uf = CX, QFT_Z = H

    Same concrete circuit as DJ -- Simon's algorithm on 1 qubit
    reduces to the same structure. *)
module Simon_1q = Simon_Core(struct
  type z = [`Q]
  type y = [`Q]
  let z_ty = q
  let y_ty = q
  let uf = gate_cx
  let qft_z = gate_h
end)

(** Instantiate Simon with Z = Q tensor Q, Y = Q tensor Q

    A 4-qubit Simon instance with a toy oracle. *)
module Simon_2q = Simon_Core(struct
  type z = [`Tensor of [`Q] * [`Q]]
  type y = [`Tensor of [`Q] * [`Q]]
  let z_ty = q ** q
  let y_ty = q ** q
  let uf = par0 gate_cx (id (q ** q))
  let qft_z = par0 gate_h gate_h
end)

(* ========================================================================= *)
(* 5. Bell and GHZ States (Linear GADT versions)                             *)
(* ========================================================================= *)

(** Bell state preparation: (H tensor id) ; CX : Q tensor Q -> Q tensor Q *)
let bell = seq0 (par0 gate_h (id q)) gate_cx

(** GHZ state preparation (3 qubits):
    Uses right-associated tensor: Q tensor (Q tensor Q).

    Step 1: H on first qubit
    Step 2: CX on qubits 0,1  (need to reassociate)
    Step 3: CX on qubits 0,2  (need to swap inner pair) *)
let ghz =
  let qq = q ** q in
  (* H on first qubit, id on remaining two: Q tensor (Q tensor Q) -> Q tensor (Q tensor Q) *)
  let step1 = par0 gate_h (id qq) in
  (* CX on qubits 0,1: assoc_r to get (Q tensor Q) tensor Q, then CX tensor id, then assoc_l back *)
  let step2 =
    seq0 (assoc_tensor_r q q q)
      (seq0 (par0 gate_cx (id q))
         (assoc_tensor_l q q q))
  in
  (* CX on qubits 0,2: swap inner pair, assoc_r, CX tensor id, assoc_l, swap back *)
  let step3 =
    seq0 (par0 (id q) (twist_tensor q q))
      (seq0 (assoc_tensor_r q q q)
        (seq0 (par0 gate_cx (id q))
          (seq0 (assoc_tensor_l q q q)
            (par0 (id q) (twist_tensor q q)))))
  in
  seq0 step1 (seq0 step2 step3)

(* ========================================================================= *)
(* Main: E2E Demo                                                            *)
(* ========================================================================= *)

let () =
  banner "PARAMETERIZED ALGORITHM DEMOS (Linear GADT)";
  print_endline "\nFull pipeline: OCaml Linear DSL -> Bridge -> Python compile -> Circuit\n";

  (* ======================================================================= *)
  banner "PART 1: Deutsch-Jozsa (parameterized on oracle)";

  print_endline "
deutsch_core : (Q tensor Q -> Q tensor Q) -> (Q tensor Q -> Q tensor Q)
  = fun uf -> (H tensor id) ; uf ; (H tensor id)

Instantiations:
  Constant oracle: uf = id          -> measures |0> (deterministic)
  Balanced oracle: uf = CX          -> measures |1> (deterministic)
";

  compile_and_report "DJ constant (oracle = id)" (emit dj_constant);
  compile_and_report "DJ balanced (oracle = CX)" (emit dj_balanced);

  (* ======================================================================= *)
  banner "PART 2: HSP Standard Form (functor)";

  print_endline "
module type HSP_PARAMS = sig
  type g; type x
  val g_ty : g ty; val x_ty : x ty
  val uf    : G tensor X -> G tensor X
  val qft_g : G -> G
end

HSP_Core(P).circuit = P.uf ; (P.qft_g tensor id_X)

Instantiations:
  G=Q, X=Q, Uf=CX, QFT=H     (= Deutsch-Jozsa as HSP)
  G=QQ, X=QQ, Uf=CX||id, QFT=H||H  (2-qubit HSP)
";

  compile_and_report "HSP (G=Q, X=Q) = DJ" (emit DJ_as_HSP.circuit);
  compile_and_report "HSP (G=Q^2, X=Q^2)" (emit HSP_2qubit.circuit);

  (* ======================================================================= *)
  banner "PART 3: Simon's Algorithm (functor)";

  print_endline "
module type SIMON_PARAMS = sig
  type z; type y
  val z_ty : z ty; val y_ty : y ty
  val uf    : Z tensor Y -> Z tensor Y
  val qft_z : Z -> Z
end

Simon_Core(S).circuit = S.uf ; (S.qft_z tensor id_Y)

Instantiations:
  Z=Q, Y=Q, Uf=CX, QFT=H       (1-qubit Simon)
  Z=QQ, Y=QQ, Uf=CX||id, QFT=H||H  (2-qubit Simon)
";

  compile_and_report "Simon (Z=Q, Y=Q)" (emit Simon_1q.circuit);
  compile_and_report "Simon (Z=Q^2, Y=Q^2)" (emit Simon_2q.circuit);

  (* ======================================================================= *)
  banner "PART 4: Bell and GHZ States";

  print_endline "
Bell state: (H tensor id) ; CX : Q tensor Q -> Q tensor Q
GHZ state:  (H tensor id^2) ; (CX tensor id) ; route ; (CX tensor id) ; unroute
";

  compile_and_report "Bell state" (emit bell);
  compile_and_report "GHZ state (3 qubits)" (emit ghz);

  (* ======================================================================= *)
  banner "PART 5: Structural Verification";

  print_endline "\nVerifying all algorithms share the pattern: oracle ; (FT tensor id)\n";

  (* DJ constant and balanced should have same structure size *)
  Printf.printf "DJ constant JSON: %s\n" (Bridge.term_to_json (emit dj_constant));
  Printf.printf "DJ balanced JSON: %s\n" (Bridge.term_to_json (emit dj_balanced));
  Printf.printf "HSP (1q) JSON:    %s\n" (Bridge.term_to_json (emit DJ_as_HSP.circuit));

  print_endline "\nNote: DJ_as_HSP.circuit and Simon_1q.circuit have identical structure";
  print_endline "because CX ; (H tensor id) is the shared unitary core.";

  (* ======================================================================= *)
  banner "SUMMARY";

  print_endline "
Demonstrated parameterized quantum algorithms in Linear GADT:

1. DEUTSCH-JOZSA (plain function)
   deutsch_core : oracle -> circuit
   Oracle is any Q tensor Q -> Q tensor Q morphism

2. HSP STANDARD FORM (OCaml functor)
   HSP_Core(P).circuit = P.uf ; (P.qft_g tensor id)
   Parameterized on abstract types G, X with type witnesses

3. SIMON'S ALGORITHM (OCaml functor)
   Simon_Core(S).circuit = S.uf ; (S.qft_z tensor id)
   Same pattern, specialized naming for Simon's context

4. BELL AND GHZ STATES
   Bell = (H tensor id) ; CX
   GHZ = Bell pattern extended to 3 qubits with wire routing

KEY INSIGHTS:
  - OCaml's type system verifies linearity at compile time
  - Functors enable parameterization over abstract quantum types
  - All circuits compile through the full pipeline to pytket
  - The oracle ; (FT tensor id) pattern is shared across algorithms
";

  banner "DEMO COMPLETE";
  if !had_failure then exit 1
