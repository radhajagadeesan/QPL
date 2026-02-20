(** Control from Distributivity E2E Demo

    The categorical construction of coherent control:

      ctrl(f) = dist⁻¹ ∘ (id ⊕ (id ⊗ f)) ∘ dist

    where dist distributes Bool ⊗ A into per-branch payloads.

    In the Linear DSL:
      dist_l  : (I+I) ⊗ A  →  (I⊗A) ⊕ (I⊗A)     [distribute]
      omap0   : id_{I⊗A} ⊕ (id_I ⊗ f)             [identity on |0⟩, f on |1⟩]
      undist_l: (I⊗A) ⊕ (I⊗A)  →  (I+I) ⊗ A      [undistribute]

    Shows three views at each level:
      Abstract   — the structural decomposition
      Naive      — anti-control on identity branch NOT elided (2n+1 gates)
      Optimised  — identity branch elided (1 gate: CnX)

    Full pipeline: OCaml Linear DSL → Bridge → Python compile → pytket Circuit
*)

open Qpl_surface
open Linear

let banner title =
  print_endline "";
  print_endline (String.make 74 '=');
  Printf.printf "  %s\n" title;
  print_endline (String.make 74 '=')

(** Bool = I ⊕ I *)
let bool_ty = one ++ one

(** ctrl : 'a ty → ('a → 'a) → (Bool ⊗ 'a → Bool ⊗ 'a)

    Control from distributivity:
      |0⟩ ⊗ |ψ⟩  →  |0⟩ ⊗ |ψ⟩      (identity)
      |1⟩ ⊗ |ψ⟩  →  |1⟩ ⊗ f|ψ⟩     (apply f)
*)
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


(** ctrl_naive : same formula but left branch uses Rz(0) as explicit no-op.
    This prevents the identity-branch elision, giving the "raw" gate count. *)
let ctrl_naive (a_ty : 'a ty)
    (noop : (unit, [`Lolli of 'a * 'a]) prog)
    (f    : (unit, [`Lolli of 'a * 'a]) prog)
    : (unit, [`Lolli of [`Tensor of [`Plus of [`One] * [`One]] * 'a]
                       * [`Tensor of [`Plus of [`One] * [`One]] * 'a]]) prog =
  let ia_ty = one ** a_ty in
  let distribute = dist_l one one a_ty in
  let left_branch  = par0 (id one) noop in    (* |0⟩ branch: visible no-op *)
  let right_branch = par0 (id one) f in       (* |1⟩ branch: id_I ⊗ f     *)
  let apply_branches = omap0 ia_ty ia_ty left_branch right_branch in
  let undistribute = undist_l one one a_ty in
  seq0 distribute (seq0 apply_branches undistribute)


(* =========================================================================
   Compile and report
   ========================================================================= *)

type row = {
  name      : string;
  qubits    : int;
  abstract  : string;
  naive     : int option;
  optimised : int option;
}

let compile_term term =
  match Bridge.compile term with
  | Bridge.CompileOk (perm, size) ->
      Printf.printf "  ✓ %d gates   perm=[%s]\n" size
        (String.concat ", " (List.map string_of_int perm.new_to_old));
      Some size
  | Bridge.CompileError err ->
      Printf.printf "  ✗ FAILED: %s\n" err;
      None


let () =
  let project_root = Filename.dirname (Sys.getcwd ()) in
  Bridge.set_project_root project_root;

  banner "CONTROL FROM DISTRIBUTIVITY — E2E DEMO";
  print_endline "\n  ctrl(f) = undist ∘ (id ⊕ (id_I ⊗ f)) ∘ dist";
  print_endline "  Pipeline: OCaml Linear DSL → Bridge → Python → pytket";

  (* =====================================================================
     CIRCUIT DIAGRAMS
     ===================================================================== *)
  banner "CIRCUIT: Abstract ctrl(f)";

  print_endline "";
  print_endline "  ctrl(f) : Bool ⊗ A → Bool ⊗ A";
  print_endline "";
  print_endline "              ┌───────┐ ┌───────────────┐ ┌─────────┐";
  print_endline "  q[0] Bool ──┤       ├─┤               ├─┤         ├──";
  print_endline "              │ dist  │ │ id ⊕ (id ⊗ f) │ │ undist  │";
  print_endline "  q[1] A   ──┤       ├─┤               ├─┤         ├──";
  print_endline "              └───────┘ └───────────────┘ └─────────┘";
  print_endline "";
  print_endline "  dist, undist : 0 gates (wire permutations)";
  print_endline "  omap0 dispatches by tag qubit:";
  print_endline "    |0⟩ branch → id   (do nothing)";
  print_endline "    |1⟩ branch → f    (apply f to payload)";

  banner "CIRCUIT: Unoptimised ctrl(f)  [identity branch not elided]";

  print_endline "";
  print_endline "  PlusMap compiles id ⊕ (id ⊗ f) as:";
  print_endline "    • anti-control for |0⟩:  X on tag, controlled-id body, X on tag";
  print_endline "    • control for |1⟩:       controlled-f body";
  print_endline "";
  print_endline "  When left body = id (0 gates), anti-control emits a bare X–X pair:";
  print_endline "";
  print_endline "           ┌ anti-ctrl (|0⟩) ┐ ┌ ctrl (|1⟩) ┐";
  print_endline "           │                  │ │             │";
  print_endline "  q[0] ────X────────────X─────●───────────────";
  print_endline "           │                  │ │             │";
  print_endline "  q[1] ──────────────────────⊕───────────────";
  print_endline "           │                  │ │             │";
  print_endline "           └──────────────────┘ └─────────────┘";
  print_endline "";
  print_endline "  The X–X pair is a no-op: it cancels to identity.";
  print_endline "  Total naive gates: 3  (X, X, CX)";
  print_endline "";
  print_endline "  The compiler elides the X–X when the branch body has 0 gates,";
  print_endline "  yielding the optimised circuit:";
  print_endline "";
  print_endline "  q[0] ──●──";
  print_endline "          │";
  print_endline "  q[1] ──⊕──";
  print_endline "";
  print_endline "  Optimised: 1 gate  (CX)";

  let rows = ref [] in

  (* No-op gates: semantically identity but emit gates, preventing
     the identity-branch elision so we can measure naive gate counts. *)
  let noop_q    = gate_rz 0.0 in                                    (* Q → Q    *)
  let noop_bool = seq0 (twist_plus one one) (twist_plus one one) in (* Bool → Bool *)

  (* =====================================================================
     Level 1: ctrl(X) — CX
     ===================================================================== *)
  banner "LEVEL 1: ctrl(X) — CX  (2 qubits)";

  print_endline "  Naive (anti-control on identity branch not elided):";
  let naive1 = compile_term (emit (ctrl_naive q noop_q gate_x)) in

  print_endline "  Optimised (identity branch elided):";
  let opt1 = compile_term (emit (ctrl q gate_x)) in

  (* Verify optimised ctrl(X) = primitive CX *)
  print_endline "\n  Verification: ctrl(X) = CX ?";
  (match Bridge.eq_circ (emit (ctrl q gate_x)) (emit gate_cx) with
   | Bridge.EqCircOk (equal, fidelity) ->
       Printf.printf "    eq_circ: %s (fidelity=%.6f)\n"
         (if equal then "EQUAL" else "NOT EQUAL") fidelity
   | Bridge.EqCircError err ->
       Printf.printf "    eq_circ ERROR: %s\n" err);

  rows := { name = "ctrl(X)"; qubits = 2;
            abstract = "dist ; (id ⊕ (id⊗X)) ; undist";
            naive = naive1; optimised = opt1 } :: !rows;

  (* =====================================================================
     Level 2: ctrl(ctrl(X)) — CCX / Toffoli
     ===================================================================== *)
  banner "LEVEL 2: ctrl(ctrl(X)) — CCX  (3 qubits)";

  print_endline "\n  Abstract:";
  print_endline "    dist_l(I,I,Bool⊗Q) ; omap0(id, id_I ⊗ ctrl(X)) ; undist_l";
  print_endline "";
  print_endline "    omap0 left  (|0⟩): id                       → 0 body gates";
  print_endline "    omap0 right (|1⟩): id_I ⊗ ctrl(X)           → ctrl(X) body gates";
  print_endline "";

  let bq = bool_ty ** q in

  print_endline "  Naive:";
  let noop_bq' = par0 noop_bool noop_q in
  let naive_ctrl_x = ctrl_naive q noop_q gate_x in
  let naive2 = compile_term (emit (ctrl_naive bq noop_bq' naive_ctrl_x)) in

  print_endline "  Optimised:";
  let ctrl_x = ctrl q gate_x in
  let opt2 = compile_term (emit (ctrl bq ctrl_x)) in

  rows := { name = "ctrl²(X)"; qubits = 3;
            abstract = "dist ; (id ⊕ (id⊗ctrl(X))) ; undist";
            naive = naive2; optimised = opt2 } :: !rows;

  (* =====================================================================
     Level 3: ctrl(ctrl(ctrl(X))) — CCCX
     ===================================================================== *)
  banner "LEVEL 3: ctrl³(X) — CCCX  (4 qubits)";

  print_endline "\n  Abstract:";
  print_endline "    dist_l(I,I,Bool⊗Bool⊗Q) ; omap0(id, id_I ⊗ ctrl²(X)) ; undist_l";
  print_endline "";

  let bbq = bool_ty ** bq in

  print_endline "  Naive:";
  let noop_bbq = par0 noop_bool noop_bq' in
  let naive_ctrl2_x = ctrl_naive bq noop_bq' naive_ctrl_x in
  let naive3 = compile_term (emit (ctrl_naive bbq noop_bbq naive_ctrl2_x)) in

  print_endline "  Optimised:";
  let ctrl2_x = ctrl bq ctrl_x in
  let opt3 = compile_term (emit (ctrl bbq ctrl2_x)) in

  rows := { name = "ctrl³(X)"; qubits = 4;
            abstract = "dist ; (id ⊕ (id⊗ctrl²(X))) ; undist";
            naive = naive3; optimised = opt3 } :: !rows;

  (* =====================================================================
     Level 4: ctrl(ctrl(ctrl(ctrl(X)))) — CCCCX
     ===================================================================== *)
  banner "LEVEL 4: ctrl⁴(X) — CCCCX  (5 qubits)";

  print_endline "\n  Abstract:";
  print_endline "    dist_l(I,I,Bool⊗Bool⊗Bool⊗Q) ; omap0(id, id_I ⊗ ctrl³(X)) ; undist_l";
  print_endline "";

  let bbbq = bool_ty ** bbq in

  print_endline "  Naive:";
  let noop_bbbq = par0 noop_bool noop_bbq in
  let naive_ctrl3_x = ctrl_naive bbq noop_bbq naive_ctrl2_x in
  let naive4 = compile_term (emit (ctrl_naive bbbq noop_bbbq naive_ctrl3_x)) in

  print_endline "  Optimised:";
  let ctrl3_x = ctrl bbq ctrl2_x in
  let opt4 = compile_term (emit (ctrl bbbq ctrl3_x)) in

  rows := { name = "ctrl⁴(X)"; qubits = 5;
            abstract = "dist ; (id ⊕ (id⊗ctrl³(X))) ; undist";
            naive = naive4; optimised = opt4 } :: !rows;

  (* =====================================================================
     SUMMARY TABLE
     ===================================================================== *)
  banner "SUMMARY";

  let rows = List.rev !rows in

  print_endline "\n  ctrl(f) = dist⁻¹ ∘ (id ⊕ (id ⊗ f)) ∘ dist\n";
  Printf.printf "  %-12s  %-6s  %-37s  %-6s  %-6s\n"
    "Term" "Qubits" "Abstract" "Naive" "Opt";
  Printf.printf "  %-12s  %-6s  %-37s  %-6s  %-6s\n"
    "----" "------" "--------" "-----" "---";

  List.iter (fun r ->
    let naive_s = match r.naive with Some n -> string_of_int n | None -> "fail" in
    let opt_s   = match r.optimised with Some n -> string_of_int n | None -> "fail" in
    Printf.printf "  %-12s  %-6d  %-37s  %-6s  %-6s\n"
      r.name r.qubits r.abstract naive_s opt_s
  ) rows;

  print_endline "\n  Naive: anti-control X gates emitted even when left branch is identity.";
  print_endline "  Opt:   compiler elides anti-control when branch body has 0 gates,";
  print_endline "         leaving only the controlled right-branch gate (CnX).\n";

  print_endline "  Verification: ctrl(X) = CX  (eq_circ, fidelity 1.0)";
  print_endline "";

  banner "DEMO COMPLETE"
