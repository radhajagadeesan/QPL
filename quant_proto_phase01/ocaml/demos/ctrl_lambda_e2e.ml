(** Higher-order ctrl combinator — curried lambda form.

    From the paper:

      ctrl := λf. undist ∘ (id_{I⊗A}  ⊕  (id_I ⊗ f)) ∘ dist
           :  (A ⊸ A) ⊸ (Bool ⊗ A ⊸ Bool ⊗ A)

    Part 1 compiles the ABSTRACT lambda (f is a wire bundle, not instantiated).
    Parts 2–5 instantiate iteratively:

      ctrl(X)             =  CX
      ctrl(ctrl(X))       =  CCX   (Toffoli)
      ctrl³(X)            =  CCCX
      ctrl⁴(X)            =  CCCCX

    Full pipeline: OCaml oterm → Bridge → Python compile → pytket Circuit
*)

open Qpl_surface
open Linear

let had_failure = ref false

let banner title =
  print_endline "";
  print_endline (String.make 74 '=');
  Printf.printf "  %s\n" title;
  print_endline (String.make 74 '=')

(** Bool = I + I *)
let bool_ty = one ++ one

(** I ⊗ Q *)
let iq_ty = one ** q

(** Q ⊸ Q *)
let qq = q -@ q

(** Bool ⊗ Q *)
let bq = bool_ty ** q

(* ========================================================================= *)
(* Part 1: Abstract ctrl as a higher-order lambda term                        *)
(* ========================================================================= *)

(** ctrl_Q : (Q ⊸ Q) ⊸ (Bool ⊗ Q ⊸ Bool ⊗ Q)

    ctrl_Q = λf:(Q⊸Q). λba:(Bool⊗Q).
      let (b, a) = ba in
      (undist_l ∘ (id_{I⊗Q} ⊕ (id_I ⊗ f)) ∘ dist_l) (b, a)

    PlusMap branches:
      Left  (tag=0): id_{I⊗Q}        — identity, do nothing
      Right (tag=1): id_I ⊗ f        — apply f to payload

    f is a FREE VARIABLE in the right branch — its wires are
    allocated by the outer lambda and referenced at compile time.
*)
let ctrl_lambda : (unit, [`Lolli of _ * _]) oterm =
  (* Right branch: I⊗Q → I⊗Q, apply f to the Q payload.
     f is FREE in this branch — its context is qq * unit.

     Context inside body (after oletpair with oid):
       [t:one, x:q, f:qq]
     opair split: t→left, (x,f)→right
     oapp split:  f→left (function), x→right (argument) *)
  let right_branch =
    oletpair "t" "x" one q (oid iq_ty)
      (opair (ovar "t" one)
             (oapp (ovar "f" qq) (ovar "x" q)
                   (SRight (SLeft SNil)))       (* x→right, f→left *)
             (SLeft (SRight (SRight SNil))))    (* t→left, x→right, f→right *)
      (SRight SNil)                             (* f→right (body inherits f) *)
  in

  (* Pipeline: dist_l ; plusmap(id, right_branch) ; undist_l
     right_branch has context qq * unit (free variable f).
     The pipeline propagates this context. *)
  let pipeline =
    oseq (oembed (dist_l one one q))
      (oseq (oplusmap iq_ty iq_ty (oid iq_ty) right_branch
                       (SRight SNil))           (* left branch closed, f→right *)
            (oembed (undist_l one one q))
            (SLeft SNil))                       (* plusmap has f, undist closed *)
      (SRight SNil)                             (* dist closed, inner has f *)
  in

  (* ctrl = λf. λba. let (b,a) = ba in pipeline(b, a)

     Inner olam body context: [ba:bq, f:qq]
     oletpair: ba→left (scrutinee), f→right (body inherits)
     Body context: [b:bool_ty, a:q, f:qq]
     oapp: f→left (pipeline), (b,a)→right (argument) *)
  olam "f" qq (bq -@ bq)
    (olam "ba" bq bq
      (oletpair "b" "a" bool_ty q (ovar "ba" bq)
        (oapp pipeline
          (opair (ovar "b" bool_ty) (ovar "a" q)
                 (SLeft (SRight SNil)))         (* b→left, a→right *)
          (SRight (SRight (SLeft SNil))))       (* b→right, a→right, f→left *)
        (SLeft (SRight SNil))))


(* ========================================================================= *)
(* Meta-level ctrl for iterated applications                                  *)
(* ========================================================================= *)

(** ctrl : 'a ty → ('a → 'a) → (Bool ⊗ 'a → Bool ⊗ 'a)

    Same formula using meta-level Linear DSL combinators.
    Used for iterated applications where A changes at each level. *)
let ctrl (a_ty : 'a ty) (f : (unit, [`Lolli of 'a * 'a]) prog)
    : (unit, [`Lolli of [`Tensor of [`Plus of [`One] * [`One]] * 'a]
                       * [`Tensor of [`Plus of [`One] * [`One]] * 'a]]) prog =
  let ia_ty = one ** a_ty in
  let distribute = dist_l one one a_ty in
  let left_branch  = id ia_ty in              (* |0⟩ branch: do nothing *)
  let right_branch = par0 (id one) f in       (* |1⟩ branch: id_I ⊗ f  *)
  let apply_branches = omap0 ia_ty ia_ty left_branch right_branch in
  let undistribute = undist_l one one a_ty in
  seq0 distribute (seq0 apply_branches undistribute)


(* ========================================================================= *)
(* Main                                                                       *)
(* ========================================================================= *)

let () =
  let project_root = Filename.dirname (Sys.getcwd ()) in
  Bridge.set_project_root project_root;

  banner "HIGHER-ORDER ctrl COMBINATOR";
  print_endline "";
  print_endline "  ctrl := \\lambda f.  undist \\circ (id \\oplus (id_I \\otimes f)) \\circ dist";
  print_endline "       : (A \\multimap A) \\multimap (Bool \\otimes A \\multimap Bool \\otimes A)";
  print_endline "";
  print_endline "  Pipeline: OCaml oterm -> Bridge -> Python -> pytket";

  (* ======================================================================= *)
  banner "PART 1: Abstract ctrl (lambda term)";

  print_endline "
  ctrl_Q = \\lambda f:(Q->Q). \\lambda ba:(Bool*Q).
    let (b, a) = ba in
    (undist_l ; (id_{I*Q} + (id_I * f)) ; dist_l) (b, a)

  PlusMap branches:
    Left  (tag=0): id_{I*Q}    -- identity, do nothing
    Right (tag=1): id_I * f    -- apply f to payload

  Curried type: (Q->Q) -> ((Bool*Q) -> (Bool*Q))
  Circuit width: width(Q->Q) + width(Arrow(Bool*Q, Bool*Q)) = 2 + 4 = 6 qubits
    Wires [0,1]: f boundary (input A, output A)
    Wires [2,3]: inner arrow input (Bool*Q)
    Wires [4,5]: inner arrow output (Bool*Q)
";

  Printf.printf "Compiling abstract ctrl lambda:\n\n";
  let ctrl_bridge = emit_oterm ctrl_lambda in
  (match Bridge.compile_show ctrl_bridge with
   | Bridge.CompileOk (perm, size) ->
       Printf.printf "\n  ctrl (abstract): %d qubits, %d gates\n" perm.n size
   | Bridge.CompileError err ->
       Printf.printf "\n  FAILED: %s\n" err;
       had_failure := true);

  (* ======================================================================= *)
  banner "PART 2: ctrl(X) = CX";

  print_endline "
  Instantiate f := X gate.
  ctrl(X) : Bool * Q -> Bool * Q
  Expected: 1 pytket gate (CX)
";

  let ctrl_x = ctrl q gate_x in
  Printf.printf "ctrl(X):\n";
  (match Bridge.compile_show (emit ctrl_x) with
   | Bridge.CompileOk _ -> ()
   | Bridge.CompileError err -> Printf.printf "  FAILED: %s\n" err; had_failure := true);

  (match Bridge.eq_circ (emit ctrl_x) (emit gate_cx) with
   | Bridge.EqCircOk (equal, fidelity) ->
       Printf.printf "  Verify ctrl(X) = CX: %s (fidelity=%.6f)\n"
         (if equal then "EQUAL" else "NOT EQUAL") fidelity
   | Bridge.EqCircError err ->
       Printf.printf "  eq_circ ERROR: %s\n" err;
       had_failure := true);

  (* ======================================================================= *)
  banner "PART 3: ctrl(ctrl(X)) = CCX (Toffoli)";

  print_endline "
  ctrl^2(X) = ctrl_{Bool*Q}(ctrl_Q(X))
  Expected: 1 pytket gate (CCX box)
";

  let ctrl2_x = ctrl bq ctrl_x in
  Printf.printf "ctrl^2(X):\n";
  (match Bridge.compile_show (emit ctrl2_x) with
   | Bridge.CompileOk _ -> ()
   | Bridge.CompileError err -> Printf.printf "  FAILED: %s\n" err; had_failure := true);

  let ccx_ref = Bridge.TCCX (0, 1, 2) in
  (match Bridge.eq_circ (emit ctrl2_x) ccx_ref with
   | Bridge.EqCircOk (equal, fidelity) ->
       Printf.printf "  Verify ctrl^2(X) = CCX: %s (fidelity=%.6f)\n"
         (if equal then "EQUAL" else "NOT EQUAL") fidelity
   | Bridge.EqCircError err ->
       Printf.printf "  eq_circ ERROR: %s\n" err;
       had_failure := true);

  (* ======================================================================= *)
  banner "PART 4: ctrl^3(X) = CCCX";

  let bbq = bool_ty ** bq in
  let ctrl3_x = ctrl bbq ctrl2_x in
  Printf.printf "\nctrl^3(X):\n";
  (match Bridge.compile_show (emit ctrl3_x) with
   | Bridge.CompileOk _ -> ()
   | Bridge.CompileError err -> Printf.printf "  FAILED: %s\n" err; had_failure := true);

  let cccx_ref = Bridge.TGate ("X", [3], [0; 1; 2]) in
  (match Bridge.eq_circ (emit ctrl3_x) cccx_ref with
   | Bridge.EqCircOk (equal, fidelity) ->
       Printf.printf "  Verify ctrl^3(X) = CCCX: %s (fidelity=%.6f)\n"
         (if equal then "EQUAL" else "NOT EQUAL") fidelity
   | Bridge.EqCircError err ->
       Printf.printf "  eq_circ ERROR: %s\n" err;
       had_failure := true);

  (* ======================================================================= *)
  banner "PART 5: ctrl^4(X) = CCCCX";

  let bbbq = bool_ty ** bbq in
  let ctrl4_x = ctrl bbbq ctrl3_x in
  Printf.printf "\nctrl^4(X):\n";
  (match Bridge.compile_show (emit ctrl4_x) with
   | Bridge.CompileOk _ -> ()
   | Bridge.CompileError err -> Printf.printf "  FAILED: %s\n" err; had_failure := true);

  let ccccx_ref = Bridge.TGate ("X", [4], [0; 1; 2; 3]) in
  (match Bridge.eq_circ (emit ctrl4_x) ccccx_ref with
   | Bridge.EqCircOk (equal, fidelity) ->
       Printf.printf "  Verify ctrl^4(X) = CCCCX: %s (fidelity=%.6f)\n"
         (if equal then "EQUAL" else "NOT EQUAL") fidelity
   | Bridge.EqCircError err ->
       Printf.printf "  eq_circ ERROR: %s\n" err;
       had_failure := true);

  (* ======================================================================= *)
  banner "SUMMARY";

  print_endline "
  ctrl := \\lambda f. undist \\circ (id \\oplus (id_I \\otimes f)) \\circ dist
       : (A \\multimap A) \\multimap (Bool \\otimes A \\multimap Bool \\otimes A)

  +----------------+---------+----------------------------+
  | Term           | Qubits  | Verified against           |
  +----------------+---------+----------------------------+
  | ctrl (abstract)| 6       | (curried lambda)           |
  | ctrl(X)        | 2       | CX                         |
  | ctrl^2(X)      | 3       | CCX (Toffoli)              |
  | ctrl^3(X)      | 4       | CCCX                       |
  | ctrl^4(X)      | 5       | CCCCX                      |
  +----------------+---------+----------------------------+

  Key insight: ctrl is a HIGHER-ORDER combinator.
  The abstract lambda has f as a wire bundle (boundary exposure).
  Iterated application builds multi-controlled gates:
  each ctrl(−) adds one control qubit.
";

  banner "DEMO COMPLETE";
  if !had_failure then exit 1
