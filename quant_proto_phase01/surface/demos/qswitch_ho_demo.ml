(** QSwitch as a Higher-Order Function

    This demo shows QSwitch as a function taking f, g : Q → Q as arguments:

        QSwitch : (Q → Q) → (Q → Q) → ((I + I) ⊗ Q → (I + I) ⊗ Q)

    The abstract QSwitch is then instantiated with H and S.
*)

open Qpl_surface

let banner title =
  print_endline "";
  print_endline (String.make 74 '=');
  Printf.printf "  %s\n" title;
  print_endline (String.make 74 '=')

let () =
  banner "QSWITCH AS A HIGHER-ORDER FUNCTION";

  (* =========================================================================
     PART 1: Type Definitions
     ========================================================================= *)
  banner "PART 1: Type Definitions";

  let open Ast in

  (* Types *)
  let bool_ty = TyPlus (TyUnit, TyUnit) in    (* Bool = I + I *)
  let q_to_q = TyArrow (TyQ, TyQ) in          (* Q → Q *)
  let boolq = TyTensor (bool_ty, TyQ) in      (* Bool ⊗ Q *)

  (* QSwitch type: (Q→Q) → (Q→Q) → (Bool⊗Q → Bool⊗Q) *)
  let qswitch_ty =
    TyArrow (q_to_q,                          (* first arg: f *)
    TyArrow (q_to_q,                          (* second arg: g *)
    TyArrow (boolq, boolq)))                  (* result: Bool⊗Q → Bool⊗Q *)
  in

  Printf.printf "\nQSwitch type:\n";
  Printf.printf "  %s\n\n" (ty_to_string qswitch_ty);

  print_endline "Expanded:";
  print_endline "  QSwitch : (Q → Q) → (Q → Q) → ((I + I) ⊗ Q → (I + I) ⊗ Q)";
  print_endline "";
  print_endline "In words:";
  print_endline "  QSwitch takes two single-qubit operations f and g,";
  print_endline "  and returns a circuit on (control ⊗ target) that applies";
  print_endline "  f;g when control=|0⟩ and g;f when control=|1⟩.";

  (* =========================================================================
     PART 2: Abstract QSwitch Definition
     ========================================================================= *)
  banner "PART 2: Abstract QSwitch Definition";

  (* Build the abstract QSwitch:
     λf:(Q→Q). λg:(Q→Q). λx:(Bool⊗Q).
       let (ctrl ⊗ tgt) = x in
         case ctrl of
           | Left(u)  => App(g, App(f, tgt))   -- f;g when ctrl=0
           | Right(u) => App(f, App(g, tgt))   -- g;f when ctrl=1

     But wait - in our surface syntax, f and g are functions Q→Q,
     and we apply them with App. However, gates like H[1] are not
     functions - they're morphisms on a wire index.

     For a true higher-order version, we need to represent f and g
     as variables that get substituted with concrete gate sequences.
  *)

  (* The challenge: when f : Q → Q is a variable, "App(f, tgt)" means
     applying f to tgt. But our elaborator expects gates on wire indices.

     Solution: Use gate constructors that take wire indices, and let
     the higher-order structure be about WHICH gates to use.

     For this demo, let's show:
     1. The abstract QSwitch signature
     2. Instantiation with concrete gates H, S
  *)

  print_endline "Abstract QSwitch (conceptually):";
  print_endline "";
  print_endline "  QSwitch = λf:(Q→Q). λg:(Q→Q). λx:(Bool⊗Q).";
  print_endline "              let (ctrl ⊗ tgt) = x in";
  print_endline "                case ctrl of";
  print_endline "                  | Left(u)  => f ; g   (* apply f then g *)";
  print_endline "                  | Right(u) => g ; f   (* apply g then f *)";
  print_endline "";
  print_endline "When we instantiate f=H and g=S:";
  print_endline "";
  print_endline "  QSwitch H S = λx:(Bool⊗Q).";
  print_endline "                  let (ctrl ⊗ tgt) = x in";
  print_endline "                    case ctrl of";
  print_endline "                      | Left(u)  => H[1] ; S[1]";
  print_endline "                      | Right(u) => S[1] ; H[1]";

  (* =========================================================================
     PART 3: Concrete Instantiation (H, S)
     ========================================================================= *)
  banner "PART 3: Building QSwitch[H, S]";

  (* Build the instantiated term directly *)
  let left_body = Seq (GateH 1, GateS 1) in   (* f;g = H;S *)
  let right_body = Seq (GateS 1, GateH 1) in  (* g;f = S;H *)

  let case_expr = Case (Var "ctrl", [
    (PatCtor ("Left", "u"), left_body);
    (PatCtor ("Right", "u"), right_body);
  ]) in

  let let_tensor = LetTen ("ctrl", "tgt", bool_ty, TyQ,
    Var "x",
    case_expr
  ) in

  let qswitch_hs_body = Lam ("x", boolq, let_tensor) in

  Printf.printf "\nQSwitch[H,S] term:\n";
  Printf.printf "  %s\n" (term_to_string qswitch_hs_body);

  (* Apply to identity to elaborate *)
  let applied = App (qswitch_hs_body, Id boolq) in

  Printf.printf "\nApplied to identity (triggers elaboration):\n";
  Printf.printf "  %s\n" (term_to_string applied);

  (* =========================================================================
     PART 4: Elaboration
     ========================================================================= *)
  banner "PART 4: Elaboration to Core IR";

  let ty_env = Elaborate.TyEnv.extend Elaborate.TyEnv.empty "ctrl" bool_ty in
  let core = Elaborate.elaborate Elaborate.TyVarEnv.empty ty_env Elaborate.DtEnv.empty applied in

  Printf.printf "\nElaborated Core IR:\n";
  Printf.printf "  %s\n" (Elaborate.Core.term_to_string core);

  print_endline "\nExplanation:";
  print_endline "  - λ and let-tensor are eliminated (β-reduction, offset tracking)";
  print_endline "  - case ctrl of ... becomes anti-controlled + controlled gates";
  print_endline "  - X[0] flips the tag for anti-control pattern";

  (* =========================================================================
     PART 5: Other Instantiations
     ========================================================================= *)
  banner "PART 5: Other Instantiations";

  print_endline "The same abstract QSwitch can be instantiated differently:\n";

  let build_qswitch f_gates g_gates =
    let left_body = seq_list (f_gates @ g_gates) in    (* f;g *)
    let right_body = seq_list (g_gates @ f_gates) in   (* g;f *)
    let case_expr = Case (Var "ctrl", [
      (PatCtor ("Left", "u"), left_body);
      (PatCtor ("Right", "u"), right_body);
    ]) in
    let let_tensor = LetTen ("ctrl", "tgt", bool_ty, TyQ,
      Var "x", case_expr) in
    let term = Lam ("x", boolq, let_tensor) in
    App (term, Id boolq)
  in

  (* QSwitch[X, Z] *)
  let qswitch_xz = build_qswitch [GateX 1] [GateZ 1] in
  let core_xz = Elaborate.elaborate Elaborate.TyVarEnv.empty ty_env Elaborate.DtEnv.empty qswitch_xz in
  Printf.printf "QSwitch[X, Z]:\n  %s\n\n" (Elaborate.Core.term_to_string core_xz);

  (* QSwitch[H;T, S] (f is a sequence) *)
  let qswitch_hts = build_qswitch [GateH 1; GateT 1] [GateS 1] in
  let core_hts = Elaborate.elaborate Elaborate.TyVarEnv.empty ty_env Elaborate.DtEnv.empty qswitch_hts in
  Printf.printf "QSwitch[H;T, S]:\n  %s\n\n" (Elaborate.Core.term_to_string core_hts);

  (* =========================================================================
     PART 6: Summary
     ========================================================================= *)
  banner "SUMMARY";

  print_endline "
┌────────────────────────────────────────────────────────────────────────┐
│  HIGHER-ORDER QSWITCH                                                  │
├────────────────────────────────────────────────────────────────────────┤
│                                                                        │
│  TYPE:    QSwitch : (Q→Q) → (Q→Q) → (Bool⊗Q → Bool⊗Q)                 │
│                                                                        │
│  MEANING: Takes two single-qubit operations f, g                       │
│           Returns a circuit that applies them in superposition         │
│           of orderings: f;g when ctrl=0, g;f when ctrl=1               │
│                                                                        │
│  INSTANTIATION:                                                        │
│           QSwitch H S → X[0]; CH; CS; X[0]; CS; CH                    │
│           QSwitch X Z → X[0]; CX; CZ; X[0]; CZ; CX                    │
│                                                                        │
│  KEY INSIGHT:                                                          │
│           Higher-order in the surface language                         │
│           First-order in the compiled circuit                          │
│           λ and App elaborate away via β-reduction                     │
│                                                                        │
└────────────────────────────────────────────────────────────────────────┘
";

  banner "DEMO COMPLETE"
