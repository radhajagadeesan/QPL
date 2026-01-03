(** QSwitch Demo: Surface → Elaboration → Core IR → Circuit

    This demo runs the ACTUAL elaboration pipeline, showing each step.
*)

open Qpl_surface

let banner title =
  print_endline "";
  print_endline (String.make 74 '=');
  Printf.printf "  %s\n" title;
  print_endline (String.make 74 '=')

(* Build the QSwitch AST:

   def QSwitch_HS : (I + I) ⊗ Q → (I + I) ⊗ Q =
     λx. let (ctrl ⊗ tgt) : (I + I) ⊗ Q = x in
       case ctrl of
         | Left(u)  => S[1] ; H[1]    (* apply S then H to target *)
         | Right(u) => H[1] ; S[1]    (* apply H then S to target *)

   The case expression controls which gates run. The control qubit (tag)
   passes through unchanged - only the payload (target qubit) is modified.
*)
let build_qswitch_ast () =
  let open Ast in

  (* Types *)
  let bit = TyPlus (TyUnit, TyUnit) in   (* I + I *)
  let bitq = TyTensor (bit, TyQ) in      (* (I + I) ⊗ Q *)

  (* The case branches operate on the payload (target qubit at wire 1).
     The control/tag qubit at wire 0 passes through unchanged.

     - Left(u)  => S[1] ; H[1]   (* when control=0: apply S then H *)
     - Right(u) => H[1] ; S[1]   (* when control=1: apply H then S *)
  *)
  let left_body = Seq (GateS 1, GateH 1) in
  let right_body = Seq (GateH 1, GateS 1) in

  let case_expr = Case (Var "ctrl", [
    (PatCtor ("Left", "u"), left_body);
    (PatCtor ("Right", "u"), right_body);
  ]) in

  (* let (ctrl ⊗ tgt) : (I + I) ⊗ Q = x in case_expr *)
  let let_tensor = LetTen ("ctrl", "tgt", bit, TyQ,
    Var "x",
    case_expr
  ) in

  (* λx. let_tensor *)
  let lambda = Lam ("x", bitq, let_tensor) in

  (* Apply to identity to elaborate the lambda *)
  App (lambda, Id bitq)

let () =
  banner "QUANTUM SWITCH: Full Compilation Pipeline";

  (* =========================================================================
     PART 1: Source Program (AST)
     ========================================================================= *)
  banner "PART 1: Surface Program (AST)";

  print_endline {|
SOURCE SYNTAX:

  def QSwitch_HS : (I + I) ⊗ Q → (I + I) ⊗ Q =
    λx. let (ctrl ⊗ tgt) : (I + I) ⊗ Q = x in
      case ctrl of
        | Left(u)  => S[1] ; H[1]    (* when control=0: S then H *)
        | Right(u) => H[1] ; S[1]    (* when control=1: H then S *)

TYPE LAYOUT:
  Wire 0: tag qubit (control) — encodes Left vs Right
  Wire 1: target qubit — where H and S are applied

The case branches only specify what gates to apply to the target (wire 1).
The control qubit (wire 0) passes through unchanged.
|};

  let ast = build_qswitch_ast () in
  print_endline "Built AST:";
  Printf.printf "  %s\n" (Ast.term_to_string ast);

  (* =========================================================================
     PART 2: Elaboration (AST → Core IR)
     ========================================================================= *)
  banner "PART 2: Elaboration (AST → Core IR)";

  print_endline {|
ELABORATION STEPS:
  1. λ-elimination: substitute x for the identity
  2. let-tensor elimination: track wire offsets for ctrl and tgt
  3. case on quantum superposition → controlled gates

The key transformation:
  case ctrl of Left => f | Right => g
  ────────────────────────────────────
  Anti-controlled-f ; Controlled-g
|};

  let bit = Ast.TyPlus (Ast.TyUnit, Ast.TyUnit) in
  let ty_env = Elaborate.TyEnv.extend Elaborate.TyEnv.empty "ctrl" bit in
  let core = Elaborate.elaborate Elaborate.TyVarEnv.empty ty_env Elaborate.DtEnv.empty ast in

  print_endline "ELABORATED CORE IR:";
  Printf.printf "  %s\n" (Elaborate.Core.term_to_string core);

  (* =========================================================================
     PART 3: Circuit Interpretation
     ========================================================================= *)
  banner "PART 3: Circuit Interpretation";

  print_endline {|
The Core IR elaborates to:

  id[...] ; X[0] ; C0-S[1] ; C0-H[1] ; X[0] ; C0-H[1] ; C0-S[1]
           ─────────────────────────   ─────────────────────────
                Anti-controlled              Controlled
                   (S ; H)                    (H ; S)

Expanding the anti-control:

  X[0] ; CS[0,1] ; CH[0,1] ; X[0] ; CH[0,1] ; CS[0,1]
  ────   ────────────────   ────   ─────────────────
  flip   controlled S;H     flip   controlled H;S
         (fires on |1⟩)    back    (fires on |1⟩)

EXECUTION TRACE:

  When control = |0⟩ (Left):
    X[0] flips to |1⟩ → CS and CH fire → X[0] flips to |0⟩
    Result: target gets S then H ✓

  When control = |1⟩ (Right):
    X[0] flips to |0⟩ → CS and CH skip → X[0] flips to |1⟩ → CS and CH fire
    Result: target gets H then S ✓

  When control = superposition:
    Both paths execute coherently → target in superposition of (S;H)|ψ⟩ and (H;S)|ψ⟩

FINAL CIRCUIT (6 gates):

  ───X───●───●───X───●───●───
      │   │   │   │   │   │
  ─────CS─CH─────CH─CS─────
|};

  (* =========================================================================
     PART 4: Summary
     ========================================================================= *)
  banner "SUMMARY";

  print_endline {|
┌────────────────────────────────────────────────────────────────────────┐
│  STAGE              TRANSFORMATION                                     │
├────────────────────────────────────────────────────────────────────────┤
│                                                                        │
│  1. SOURCE          λx. let (ctrl ⊗ tgt) = x in                        │
│     (AST)             case ctrl of                                     │
│                         | Left(u)  => S[1] ; H[1]                      │
│                         | Right(u) => H[1] ; S[1]                      │
│                                                                        │
│        ↓ elaborate() - case on superposition → controlled gates        │
│                                                                        │
│  2. CORE IR         X[0] ; C0-S[1] ; C0-H[1] ; X[0] ; C0-H[1] ; C0-S[1]│
│     (Compositional)                                                    │
│                                                                        │
│        ↓ Bridge.compile() - emit gates, track permutation              │
│                                                                        │
│  3. CIRCUIT         pytket circuit + identity permutation              │
│     (Executable)                                                       │
│                                                                        │
└────────────────────────────────────────────────────────────────────────┘

KEY INSIGHT: case on superposition → controlled gates

  The elaborator transforms:
    case ctrl of Left => body_L | Right => body_R

  Into:
    Anti-controlled(body_L) ; Controlled(body_R)

  Where anti-control = X[ctrl] ; Controlled ; X[ctrl]
|};

  banner "DEMO COMPLETE"
