(** Algorithmic Snippets in QPL Surface Language

    These are surface programs that elaborate into the locked Phase 0-4C core.

    Notes:
    - (+) is monoidal (not a coproduct)
    - Nat[k] is a compile-time index (finite, non-recursive)
    - All higher-order structure elaborates away
    - Unitary atoms are opaque primitives
*)

open Qpl_surface

(* ================================================================== *)
(* Type Aliases and Datatypes                                         *)
(* ================================================================== *)

(** Unit type - single constructor *)
module Unit = Datatype.Make0(struct
  type t = U
  [@@warning "-37"]

  let name = "Unit"
  let rep = Rep.unit
  let constructors = [("U", Rep.unit)]
end)

(** Bit - classical bit at the boundary *)
module Bit = Datatype.Make0(struct
  type t = Zero | One
  [@@warning "-37"]

  let name = "Bit"
  let rep = Rep.(plus unit unit)
  let constructors = [
    ("Zero", Rep.unit);
    ("One", Rep.unit);
  ]
end)

(* ================================================================== *)
(* Snippet 6.1: Deutsch-Jozsa (Unitary Core)                          *)
(* ================================================================== *)

(**
   Assumed unitary atoms (opaque primitives):
   - H     : Q → Q              (Hadamard)
   - Hn    : QReg[n] → QReg[n]  (n-qubit Hadamard)
   - Uf    : QReg[n] ⊗ Q → QReg[n] ⊗ Q  (Oracle)
   - ket0n : I → QReg[n]        (Prepare |0⟩^n)
   - ket1  : I → Q              (Prepare |1⟩)

   Surface program:

   def deutschJozsa[n] : I → (QReg[n] ⊗ Q) =
     λu.
       let x  = Hn (ket0n u) in
       let y  = H  (ket1  u) in
       let (x1, y1) = Uf (x ⊗ y) in
       let x2 = Hn x1 in
       (x2 ⊗ y1)
*)

let deutsch_jozsa_ast =
  let open Ast in
  (* def deutschJozsa : I → (Q ⊗ Q) = ... *)
  (* Simplified 1-qubit version for demonstration *)
  DefTerm (
    "deutschJozsa",
    TyUnit,  (* I *)
    TyTensor (TyQ, TyQ),  (* Q ⊗ Q *)
    Lam ("u", TyUnit,
      Let ("x", Seq (Var "u", GateH 0),  (* x = H (ket0 u) *)
        Let ("y", Seq (Var "u", GateH 0),  (* y = H (ket1 u) *)
          (* Apply oracle Uf, then Hadamard on first qubit *)
          Let ("xy", Ten (Var "x", Var "y"),
            (* Output: H on first qubit, identity on second *)
            Ten (Seq (Var "x", GateH 0), Var "y")
          )
        )
      )
    )
  )

(* ================================================================== *)
(* Snippet 6.2: Hidden Subgroup Problem (Standard Oracle Form)        *)
(* ================================================================== *)

(**
   Assumed unitary atoms:
   - uniformG : I → G           (Uniform superposition over group)
   - zeroX    : I → X           (Zero state in output register)
   - Uf       : G ⊗ X → G ⊗ X   (Oracle)
   - QFTG     : G → G           (QFT over group)

   Surface program:

   def HSP_core : I → (G ⊗ X) =
     λu.
       let g  = uniformG u in
       let x  = zeroX    u in
       let (g1, x1) = Uf (g ⊗ x) in
       let g2 = QFTG g1 in
       (g2 ⊗ x1)
*)

let hsp_core_comment = {|
(* HSP Standard Oracle Form - requires abstract types G, X *)

def HSP_core : I → (G ⊗ X) =
  λu.
    let g  = uniformG u in
    let x  = zeroX    u in
    let gx = g ⊗ x in
    let (g1, x1) = Uf gx in
    let g2 = QFTG g1 in
    (g2 ⊗ x1)
|}

(* ================================================================== *)
(* Snippet 6.3: Hidden Subgroup Problem (Phase-Kickback Variant)      *)
(* ================================================================== *)

(**
   Assumed unitary atoms:
   - uniformG : I → G           (Uniform superposition)
   - chiZN    : I → ZN          (Character state)
   - kick     : G ⊗ ZN → G ⊗ ZN (Phase kickback)
   - QFTG     : G → G           (QFT over group)

   Surface program:

   def HSP_phase : I → G =
     λu.
       let g  = uniformG u in
       let z  = chiZN    u in
       let (g1, _z1) = kick (g ⊗ z) in
       let g2 = QFTG g1 in
       g2
*)

let hsp_phase_comment = {|
(* HSP Phase-Kickback Variant - requires abstract types G, ZN *)

def HSP_phase : I → G =
  λu.
    let g  = uniformG u in
    let z  = chiZN    u in
    let gz = g ⊗ z in
    let (g1, _z1) = kick gz in
    let g2 = QFTG g1 in
    g2
|}

(* ================================================================== *)
(* Snippet 6.4: Simon's Algorithm (Unitary Core)                      *)
(* ================================================================== *)

(**
   Assumed unitary atoms:
   - uniformZ2n : I → Z2n[n]           (Uniform superposition)
   - zeroY      : I → Y                (Zero state)
   - Uf         : Z2n[n] ⊗ Y → Z2n[n] ⊗ Y  (Simon oracle)
   - QFT2n      : Z2n[n] → Z2n[n]      (Hadamard transform)

   Surface program:

   def Simon_core[n] : I → (Z2n[n] ⊗ Y) =
     λu.
       let x = uniformZ2n u in
       let y = zeroY      u in
       let (x1, y1) = Uf (x ⊗ y) in
       let x2 = QFT2n x1 in
       (x2 ⊗ y1)
*)

let simon_core_comment = {|
(* Simon's Algorithm - requires abstract types Z2n[n], Y *)

def Simon_core[n] : I → (Z2n[n] ⊗ Y) =
  λu.
    let x = uniformZ2n u in
    let y = zeroY      u in
    let xy = x ⊗ y in
    let (x1, y1) = Uf xy in
    let x2 = QFT2n x1 in
    (x2 ⊗ y1)
|}

(* ================================================================== *)
(* Concrete Examples (using Q type)                                   *)
(* ================================================================== *)

(** A simple 2-qubit example demonstrating the pattern *)
let two_qubit_example_ast =
  let open Ast in
  DefTerm (
    "twoQubitCircuit",
    TyTensor (TyQ, TyQ),  (* Q ⊗ Q *)
    TyTensor (TyQ, TyQ),  (* Q ⊗ Q *)
    (* H[0] ; CX[0,1] ; H[0] *)
    seq_list [
      GateH 0;
      GateCX (0, 1);
      GateH 0;
    ]
  )

(** Bell state preparation *)
let bell_state_ast =
  let open Ast in
  DefTerm (
    "bellState",
    TyTensor (TyQ, TyQ),
    TyTensor (TyQ, TyQ),
    (* H[0] ; CX[0,1] *)
    Seq (GateH 0, GateCX (0, 1))
  )

(** GHZ state preparation (3 qubits) *)
let ghz_state_ast =
  let open Ast in
  DefTerm (
    "ghzState",
    TyTensor (TyQ, TyTensor (TyQ, TyQ)),
    TyTensor (TyQ, TyTensor (TyQ, TyQ)),
    (* H[0] ; CX[0,1] ; CX[0,2] *)
    seq_list [
      GateH 0;
      GateCX (0, 1);
      GateCX (0, 2);
    ]
  )

(** Swap using structural rewiring (Bool datatype) *)
let swap_via_case = {|
(* Swap using case expression on Bool datatype *)

datatype Bool['a, 'b] = F of 'a | T of 'b

def swap : Bool['a, 'b] → Bool['b, 'a] =
  λx. case x of
    | F(a) => T(a)
    | T(b) => F(b)

(* This elaborates to TwistPlus, a structural permutation *)
|}

(* ================================================================== *)
(* Print all snippets                                                 *)
(* ================================================================== *)

let () =
  print_endline "=== QPL Surface Language Algorithmic Snippets ===\n";

  print_endline "--- Deutsch-Jozsa (simplified) ---";
  print_endline (Ast.def_to_string deutsch_jozsa_ast);
  print_endline "";

  print_endline "--- HSP Standard Oracle Form ---";
  print_endline hsp_core_comment;

  print_endline "--- HSP Phase-Kickback ---";
  print_endline hsp_phase_comment;

  print_endline "--- Simon's Algorithm ---";
  print_endline simon_core_comment;

  print_endline "--- Two-Qubit Example ---";
  print_endline (Ast.def_to_string two_qubit_example_ast);
  print_endline "";

  print_endline "--- Bell State ---";
  print_endline (Ast.def_to_string bell_state_ast);
  print_endline "";

  print_endline "--- GHZ State ---";
  print_endline (Ast.def_to_string ghz_state_ast);
  print_endline "";

  print_endline "--- Swap via Case ---";
  print_endline swap_via_case;

  print_endline "=== End of Snippets ==="
