(** Comprehensive test suite for the surface language.
    Follows the specification in RadhaMSG/NEWTESTS.md.

    Tests are organized by section:
    - §2: Basic typing + linearity
    - §3: β/η equations (via eq_circ)
    - §4: Structural coherence
    - §5: Sum-case tag correctness
    - §6: Rigorous nesting
    - §7: Tensor × sum interaction
    - §8: Bool→Bool unitaries
    - §9: Property-based fuzz suite (PROP-TAG-01, PROP-TAG-02)
*)

open Qpl_surface

(* ================================================================ *)
(* Test harness infrastructure                                       *)
(* ================================================================ *)

(* Project root is auto-detected by Bridge.get_project_root *)

let tests_run = ref 0
let tests_passed = ref 0
let tests_failed = ref 0
let tests_skipped = ref 0

(** Standard empty environments for elaboration *)
let tyvar_env = []
let dt_env = []

(** Build a type environment from (name, type) pairs *)
let make_ty_env (bindings : (string * Ast.ty) list) : Elaborate.TyEnv.t =
  List.fold_left (fun env (x, ty) ->
    Elaborate.TyEnv.extend env x ty
  ) Elaborate.TyEnv.empty bindings

(** Elaborate a surface term to a Bridge term, with optional type env *)
let elaborate_to_bridge ?(ty_env=Elaborate.TyEnv.empty) term =
  let core = Elaborate.elaborate tyvar_env ty_env dt_env term in
  Elaborate.core_to_bridge core

(** Elaborate a surface term to Core, with optional type env *)
let elaborate_to_core ?(ty_env=Elaborate.TyEnv.empty) term =
  Elaborate.elaborate tyvar_env ty_env dt_env term

(** String contains substring check *)
let string_contains haystack needle =
  if String.length needle > String.length haystack then false
  else begin
    let found = ref false in
    for i = 0 to String.length haystack - String.length needle do
      if String.sub haystack i (String.length needle) = needle then
        found := true
    done;
    !found
  end

(** Test that a surface term elaborates and compiles successfully.
    Returns the Bridge compile result on success. *)
let expect_compile_ok ?(ty_env=Elaborate.TyEnv.empty)
    (name : string) (term : Ast.term) : Bridge.compile_result option =
  Printf.printf "  %s ... " name;
  try
    let bridge_term = elaborate_to_bridge ~ty_env term in
    match Bridge.compile bridge_term with
    | Bridge.CompileOk (perm, size) as result ->
      Printf.printf "OK (gates=%d, wires=%d)\n" size perm.n;
      incr tests_run; incr tests_passed;
      Some result
    | Bridge.CompileError err ->
      Printf.printf "FAIL (compile error: %s)\n" err;
      incr tests_run; incr tests_failed;
      None
  with e ->
    Printf.printf "FAIL (exception: %s)\n" (Printexc.to_string e);
    incr tests_run; incr tests_failed;
    None

(** Test that a surface term fails to elaborate/compile, with error containing substring. *)
let expect_error_contains ?(ty_env=Elaborate.TyEnv.empty)
    (name : string) (term : Ast.term) (substring : string) : unit =
  Printf.printf "  %s ... " name;
  try
    let bridge_term = elaborate_to_bridge ~ty_env term in
    (match Bridge.compile bridge_term with
     | Bridge.CompileOk _ ->
       Printf.printf "FAIL (expected error containing '%s', but compiled OK)\n" substring;
       incr tests_run; incr tests_failed
     | Bridge.CompileError err ->
       if string_contains err substring then begin
         Printf.printf "OK (compile error contains '%s')\n" substring;
         incr tests_run; incr tests_passed
       end else begin
         Printf.printf "FAIL (error '%s' doesn't contain '%s')\n" err substring;
         incr tests_run; incr tests_failed
       end)
  with e ->
    let msg = Printexc.to_string e in
    if string_contains msg substring then begin
      Printf.printf "OK (elaboration error contains '%s')\n" substring;
      incr tests_run; incr tests_passed
    end else begin
      Printf.printf "FAIL (exception '%s' doesn't contain '%s')\n" msg substring;
      incr tests_run; incr tests_failed
    end

(** Test that two surface terms compile to equal circuits (up to global phase). *)
let expect_eq_circ ?(ty_env=Elaborate.TyEnv.empty)
    (name : string) (term1 : Ast.term) (term2 : Ast.term) : unit =
  Printf.printf "  %s ... " name;
  try
    let bridge1 = elaborate_to_bridge ~ty_env term1 in
    let bridge2 = elaborate_to_bridge ~ty_env term2 in
    match Bridge.eq_circ bridge1 bridge2 with
    | Bridge.EqCircOk (true, fidelity) ->
      Printf.printf "OK (equal, fidelity=%.6f)\n" fidelity;
      incr tests_run; incr tests_passed
    | Bridge.EqCircOk (false, fidelity) ->
      Printf.printf "FAIL (not equal, fidelity=%.6f)\n" fidelity;
      incr tests_run; incr tests_failed
    | Bridge.EqCircError err ->
      Printf.printf "FAIL (eq_circ error: %s)\n" err;
      incr tests_run; incr tests_failed
  with e ->
    Printf.printf "FAIL (exception: %s)\n" (Printexc.to_string e);
    incr tests_run; incr tests_failed

(** Test that two Bridge terms (already elaborated) are equal circuits. *)
let expect_eq_circ_bridge (name : string) (bt1 : Bridge.term) (bt2 : Bridge.term) : unit =
  Printf.printf "  %s ... " name;
  match Bridge.eq_circ bt1 bt2 with
  | Bridge.EqCircOk (true, fidelity) ->
    Printf.printf "OK (equal, fidelity=%.6f)\n" fidelity;
    incr tests_run; incr tests_passed
  | Bridge.EqCircOk (false, fidelity) ->
    Printf.printf "FAIL (not equal, fidelity=%.6f)\n" fidelity;
    incr tests_run; incr tests_failed
  | Bridge.EqCircError err ->
    Printf.printf "FAIL (eq_circ error: %s)\n" err;
    incr tests_run; incr tests_failed

(** Test that a surface term elaborates successfully (no Python). *)
let expect_typecheck_ok ?(ty_env=Elaborate.TyEnv.empty)
    (name : string) (term : Ast.term) : unit =
  Printf.printf "  %s ... " name;
  try
    let _core = elaborate_to_core ~ty_env term in
    Printf.printf "OK\n";
    incr tests_run; incr tests_passed
  with e ->
    Printf.printf "FAIL (exception: %s)\n" (Printexc.to_string e);
    incr tests_run; incr tests_failed

(** Test that a surface term fails elaboration with error containing substring. *)
let expect_typecheck_error ?(ty_env=Elaborate.TyEnv.empty)
    (name : string) (term : Ast.term) (substring : string) : unit =
  Printf.printf "  %s ... " name;
  try
    let _core = elaborate_to_core ~ty_env term in
    Printf.printf "FAIL (expected error containing '%s', but typechecked OK)\n" substring;
    incr tests_run; incr tests_failed
  with e ->
    let msg = Printexc.to_string e in
    if string_contains msg substring then begin
      Printf.printf "OK (error contains '%s')\n" substring;
      incr tests_run; incr tests_passed
    end else begin
      Printf.printf "FAIL (exception '%s' doesn't contain '%s')\n" msg substring;
      incr tests_run; incr tests_failed
    end

(* ================================================================ *)
(* Type abbreviations used throughout                                *)
(* ================================================================ *)

(** Bool = Q + Q *)
let bool_ty = Ast.TyPlus (Ast.TyQ, Ast.TyQ)

(** Q ⊗ Q *)
let qq_ty = Ast.TyTensor (Ast.TyQ, Ast.TyQ)

(* ================================================================ *)
(* §0: Infrastructure verification (trivial sanity check)            *)
(* ================================================================ *)

let test_infra () =
  print_endline "§0. Infrastructure verification";

  (* id[Bool] == id[Bool] via eq_circ *)
  expect_eq_circ_bridge "INFRA-EQ-01: id == id"
    (Bridge.TId (Rep.plus (Rep.var 0) (Rep.var 1)))
    (Bridge.TId (Rep.plus (Rep.var 0) (Rep.var 1)));

  (* id[Q] compiles *)
  ignore (expect_compile_ok "INFRA-COMPILE-01: id[Q]" (Ast.Id Ast.TyQ));

  (* swap⊗ != id (sanity: eq_circ can distinguish) *)
  Printf.printf "  INFRA-NEQ-01: swap⊗ != id[Q⊗Q] ... ";
  let swap_bridge = Bridge.TTwistTen (Rep.var 0, Rep.var 1) in
  let id_bridge = Bridge.TId (Rep.tensor (Rep.var 0) (Rep.var 1)) in
  (match Bridge.eq_circ swap_bridge id_bridge with
   | Bridge.EqCircOk (false, _) ->
     Printf.printf "OK (correctly distinct)\n";
     incr tests_run; incr tests_passed
   | Bridge.EqCircOk (true, fidelity) ->
     Printf.printf "FAIL (should be distinct, fidelity=%.6f)\n" fidelity;
     incr tests_run; incr tests_failed
   | Bridge.EqCircError err ->
     Printf.printf "FAIL (error: %s)\n" err;
     incr tests_run; incr tests_failed);

  print_endline ""

(* ================================================================ *)
(* §2: Basic typing + linearity tests                                *)
(* ================================================================ *)

let test_section_2 () =
  print_endline "§2. Basic typing + linearity";

  (* T-LIN-OK-01: λx:Bool. x typechecks
     Express as App(Lam(x, Bool, x), Id Bool) — the beta-reduction is the check. *)
  let lam_id = Ast.App (
    Ast.Lam ("x", bool_ty, Ast.Var "x"),
    Ast.Id bool_ty) in
  expect_typecheck_ok "T-LIN-OK-01: (λx:Bool. x) id[Bool]" lam_id;

  (* T-LIN-ERR-UNUSED-01: let (x,y) : Q⊗Q = id[Q⊗Q] in x — y unused
     LetTen checks both variables are used. *)
  let unused_var = Ast.LetTen ("x", "y", Ast.TyQ, Ast.TyQ,
    Ast.Id qq_ty,
    Ast.Var "x") in
  expect_typecheck_error "T-LIN-ERR-UNUSED-01: let (x,y) = id in x (y unused)"
    unused_var "Unused";

  (* T-LIN-ERR-DUP-01: let (x,y) : Q⊗Q = id[Q⊗Q] in x ⊗ x — x used twice
     LetTen checks linearity of both variables in body. *)
  let dup_var = Ast.LetTen ("x", "y", Ast.TyQ, Ast.TyQ,
    Ast.Id qq_ty,
    Ast.Ten (Ast.Var "x", Ast.Var "x")) in
  expect_typecheck_error "T-LIN-ERR-DUP-01: let (x,y) = id in x ⊗ x (x duplicated)"
    dup_var "Non-linear";

  (* T-CTX-OK-01: context splitting across tensor
     let (x,y) : Q⊗Q = id[Q⊗Q] in x ⊗ y *)
  let ctx_split = Ast.LetTen ("x", "y", Ast.TyQ, Ast.TyQ,
    Ast.Id qq_ty,
    Ast.Ten (Ast.Var "x", Ast.Var "y")) in
  expect_typecheck_ok "T-CTX-OK-01: let (x,y) = id[Q⊗Q] in (x ⊗ y)" ctx_split;

  (* T-CTX-ERR-01: x used twice across tensor components *)
  let ctx_dup = Ast.LetTen ("x", "y", Ast.TyQ, Ast.TyQ,
    Ast.Id qq_ty,
    Ast.Ten (Ast.Var "x", Ast.Var "x")) in
  expect_typecheck_error "T-CTX-ERR-01: let (x,y) = id[Q⊗Q] in (x ⊗ x)"
    ctx_dup "Non-linear use";

  (* T-SUM-OK-01: case x of Left(a) => Left(a) | Right(b) => Right(b) — identity case
     Need x in ty_env with Bool type *)
  let env_s = make_ty_env [("s", bool_ty)] in
  let case_id = Ast.Case (Ast.Var "s", [
    (Ast.PatCtor ("Left", "a"), Ast.Ctor ("Left", Ast.Var "a"));
    (Ast.PatCtor ("Right", "b"), Ast.Ctor ("Right", Ast.Var "b"));
  ]) in
  expect_typecheck_ok ~ty_env:env_s "T-SUM-OK-01: case s of L a => L a | R b => R b"
    case_id;

  print_endline ""

(* ================================================================ *)
(* §3: β/η-style equations (checked by circuit identity)             *)
(* ================================================================ *)

let test_section_3 () =
  print_endline "§3. β/η equations (via eq_circ)";

  (* EQ-ARR-BETA-01: (λx:Q. x;H) id == id;H
     App(Lam(x, Q, Seq(Var x, H[0])), Id Q) == Seq(Id Q, H[0])
     After beta: Seq(Id Q, H[0]) == Seq(Id Q, H[0]) *)
  let app_h = Ast.App (
    Ast.Lam ("x", Ast.TyQ, Ast.Seq (Ast.Var "x", Ast.GateH 0)),
    Ast.Id Ast.TyQ) in
  let just_h = Ast.Seq (Ast.Id Ast.TyQ, Ast.GateH 0) in
  expect_eq_circ "EQ-ARR-BETA-01: (λx. x;H) id == id;H"
    app_h just_h;

  (* EQ-ARR-ETA-01: λx:Q. f(x) == f where f = H[0]
     App(Lam(x, Q, App(H[0], Var x)), Id Q) == H[0]
     But App(H[0], Var x) doesn't work — H[0] is not a lambda.
     In our system, function application is for lambdas only.
     Eta: Let(x, id[Q], Seq(Var x, H[0])) == Seq(id[Q], H[0]) == H[0] *)
  let eta_lhs = Ast.Let ("x", Ast.Id Ast.TyQ, Ast.Seq (Ast.Var "x", Ast.GateH 0)) in
  let eta_rhs = Ast.GateH 0 in
  expect_eq_circ "EQ-ARR-ETA-01: let x = id in x;H == H"
    eta_lhs eta_rhs;

  (* EQ-TEN-BETA-01: let (x,y) = (H ⊗ S) in (x ⊗ y) == H ⊗ S *)
  let ten_beta_lhs = Ast.LetTen ("x", "y", Ast.TyQ, Ast.TyQ,
    Ast.Ten (Ast.GateH 0, Ast.GateS 0),
    Ast.Ten (Ast.Var "x", Ast.Var "y")) in
  let ten_beta_rhs = Ast.Ten (Ast.GateH 0, Ast.GateS 0) in
  expect_eq_circ "EQ-TEN-BETA-01: let (x,y) = (H ⊗ S) in (x ⊗ y) == H ⊗ S"
    ten_beta_lhs ten_beta_rhs;

  (* EQ-TEN-ETA-01: let (x,y) = id[Q⊗Q] in (x ⊗ y) == id[Q⊗Q] *)
  let ten_eta_lhs = Ast.LetTen ("x", "y", Ast.TyQ, Ast.TyQ,
    Ast.Id qq_ty,
    Ast.Ten (Ast.Var "x", Ast.Var "y")) in
  let ten_eta_rhs = Ast.Id qq_ty in
  expect_eq_circ "EQ-TEN-ETA-01: let (x,y) = id[Q⊗Q] in (x ⊗ y) == id[Q⊗Q]"
    ten_eta_lhs ten_eta_rhs;

  (* EQ-SUM-BETA-L-01: case (Left u) of Left a -> a;S | Right b -> b;X == u;S
     Ctor("Left", H[0]) as scrutinee — classical case reduces to left branch *)
  let sum_beta_l_lhs = Ast.Case (
    Ast.Ctor ("Left", Ast.GateH 0),
    [
      (Ast.PatCtor ("Left", "a"), Ast.Seq (Ast.Var "a", Ast.GateS 0));
      (Ast.PatCtor ("Right", "b"), Ast.Seq (Ast.Var "b", Ast.GateX 0));
    ]) in
  let sum_beta_l_rhs = Ast.Seq (Ast.GateH 0, Ast.GateS 0) in
  expect_eq_circ "EQ-SUM-BETA-L-01: case (Left(H)) of L a => a;S | R b => b;X == H;S"
    sum_beta_l_lhs sum_beta_l_rhs;

  (* EQ-SUM-BETA-R-01: case (Right v) of Left x -> w | Right y -> z == z[y:=v] *)
  let sum_beta_r_lhs = Ast.Case (
    Ast.Ctor ("Right", Ast.GateS 0),
    [
      (Ast.PatCtor ("Left", "a"), Ast.Seq (Ast.Var "a", Ast.GateH 0));
      (Ast.PatCtor ("Right", "b"), Ast.Seq (Ast.Var "b", Ast.GateX 0));
    ]) in
  let sum_beta_r_rhs = Ast.Seq (Ast.GateS 0, Ast.GateX 0) in
  expect_eq_circ "EQ-SUM-BETA-R-01: case (Right(S)) of L a => a;H | R b => b;X == S;X"
    sum_beta_r_lhs sum_beta_r_rhs;

  (* EQ-SUM-ETA-01: case s of Left x -> Left x | Right y -> Right y == id[Bool]
     Quantum case: identity case equals identity morphism *)
  let env_s = make_ty_env [("s", bool_ty)] in
  let sum_eta_lhs = Ast.Case (Ast.Var "s", [
    (Ast.PatCtor ("Left", "a"), Ast.Ctor ("Left", Ast.Var "a"));
    (Ast.PatCtor ("Right", "b"), Ast.Ctor ("Right", Ast.Var "b"));
  ]) in
  let sum_eta_rhs = Ast.Id bool_ty in
  expect_eq_circ ~ty_env:env_s "EQ-SUM-ETA-01: case s of L a => L a | R b => R b == id[Bool]"
    sum_eta_lhs sum_eta_rhs;

  print_endline ""

(* ================================================================ *)
(* §4: Structural coherence tests                                    *)
(* ================================================================ *)

let test_section_4 () =
  print_endline "§4. Structural coherence";

  (* COH-SWAP-TEN-01: swap⊗ ; swap⊗ == id *)
  let swap_ten_sq = Ast.Seq (
    Ast.TwistT (Ast.TyQ, Ast.TyQ),
    Ast.TwistT (Ast.TyQ, Ast.TyQ)) in
  expect_eq_circ "COH-SWAP-TEN-01: swap⊗;swap⊗ == id[Q⊗Q]"
    swap_ten_sq (Ast.Id qq_ty);

  (* COH-SWAP-SUM-01: swap⊕ ; swap⊕ == id *)
  let swap_sum_sq = Ast.Seq (
    Ast.TwistP (Ast.TyQ, Ast.TyQ),
    Ast.TwistP (Ast.TyQ, Ast.TyQ)) in
  expect_eq_circ "COH-SWAP-SUM-01: swap⊕;swap⊕ == id[Bool]"
    swap_sum_sq (Ast.Id bool_ty);

  (* COH-ASSOC-TEN-01: assocTL ; assocTR == id *)
  let assoc_ten_roundtrip = Ast.Seq (
    Ast.AssocTL (Ast.TyQ, Ast.TyQ, Ast.TyQ),
    Ast.AssocTR (Ast.TyQ, Ast.TyQ, Ast.TyQ)) in
  let id_qqq = Ast.Id (Ast.TyTensor (Ast.TyTensor (Ast.TyQ, Ast.TyQ), Ast.TyQ)) in
  expect_eq_circ "COH-ASSOC-TEN-01: assocTL;assocTR == id[(Q⊗Q)⊗Q]"
    assoc_ten_roundtrip id_qqq;

  (* COH-ASSOC-SUM-01: assocPL ; assocPR == id *)
  let assoc_sum_roundtrip = Ast.Seq (
    Ast.AssocPL (Ast.TyQ, Ast.TyQ, Ast.TyQ),
    Ast.AssocPR (Ast.TyQ, Ast.TyQ, Ast.TyQ)) in
  let id_qqq_sum = Ast.Id (Ast.TyPlus (Ast.TyPlus (Ast.TyQ, Ast.TyQ), Ast.TyQ)) in
  expect_eq_circ "COH-ASSOC-SUM-01: assocPL;assocPR == id[(Q+Q)+Q]"
    assoc_sum_roundtrip id_qqq_sum;

  (* COH-MIX-01: Hexagon identity for tensor
     Two paths (A⊗B)⊗C → B⊗(C⊗A):
     LHS: assocTL ; swap⊗(A, B⊗C) ; assocTL(B,C,A)
     RHS: (swap⊗(A,B) ⊗ id_C) ; assocTL(B,A,C) ; (id_B ⊗ swap⊗(A,C)) *)
  let a = Ast.TyQ and b = Ast.TyQ and c = Ast.TyQ in
  let bc = Ast.TyTensor (b, c) in
  let ca = Ast.TyTensor (c, a) in

  let lhs_hex = Ast.Seq (
    Ast.Seq (
      Ast.AssocTL (a, b, c),
      Ast.TwistT (a, bc)),
    Ast.AssocTL (b, c, a)) in

  let rhs_hex = Ast.Seq (
    Ast.Seq (
      Ast.Ten (Ast.TwistT (a, b), Ast.Id c),
      Ast.AssocTL (b, a, c)),
    Ast.Ten (Ast.Id b, Ast.TwistT (a, c))) in

  let _target_ty = Ast.TyTensor (b, ca) in
  expect_eq_circ "COH-MIX-01: hexagon ⊗: assocTL;swap;assocTL == (swap⊗id);assocTL;(id⊗swap)"
    lhs_hex rhs_hex;

  (* COH-MIX-02: ⊕-hexagon — two canonical maps (A⊕B)⊕C → B⊕(C⊕A) agree.
     Analogous to COH-MIX-01 (⊗-hexagon) but for sums with PlusMap.
     LHS: assocPL(A,B,C) ; swap⊕(A, B⊕C) ; assocPL(B,C,A)
     RHS: PlusMap(swap⊕(A,B), id_C) ; assocPL(B,A,C) ; PlusMap(id_B, swap⊕(A,C))
     Uses Bridge terms directly since PlusMap requires the Python compiler. *)
  let q_rep = Rep.var 0 in
  let qq_rep = Rep.plus q_rep q_rep in
  let bc_rep = Rep.plus q_rep q_rep in
  let ca_rep = Rep.plus q_rep q_rep in

  (* LHS: assocPL(A,B,C) ; swap⊕(A, B⊕C) ; assocPL(B,C,A) *)
  let lhs_sum_hex = Bridge.TSeq (
    Bridge.TSeq (
      Bridge.TAssocPlusL (q_rep, q_rep, q_rep),
      Bridge.TTwistPlus (q_rep, bc_rep)),
    Bridge.TAssocPlusL (q_rep, q_rep, q_rep)) in

  (* RHS: PlusMap(swap⊕(A,B), id_C) ; assocPL(B,A,C) ; PlusMap(id_B, swap⊕(A,C)) *)
  let rhs_sum_hex = Bridge.TSeq (
    Bridge.TSeq (
      Bridge.TPlusMap (qq_rep, q_rep,
        Bridge.TTwistPlus (q_rep, q_rep),
        Bridge.TId q_rep),
      Bridge.TAssocPlusL (q_rep, q_rep, q_rep)),
    Bridge.TPlusMap (q_rep, ca_rep,
      Bridge.TId q_rep,
      Bridge.TTwistPlus (q_rep, q_rep))) in

  expect_eq_circ_bridge "COH-MIX-02: hexagon ⊕: assocPL;swap;assocPL == PlusMap(swap,id);assocPL;PlusMap(id,swap)"
    lhs_sum_hex rhs_sum_hex;

  print_endline ""

(* ================================================================ *)
(* §5: Sum-case tag correctness                                      *)
(* ================================================================ *)

let test_section_5 () =
  print_endline "§5. Sum-case tag correctness";

  let env_s = make_ty_env [("s", bool_ty)] in

  (* CASE-TAG-ID-01: identity case — preserves tag *)
  let case_id = Ast.Case (Ast.Var "s", [
    (Ast.PatCtor ("Left", "a"), Ast.Ctor ("Left", Ast.Var "a"));
    (Ast.PatCtor ("Right", "b"), Ast.Ctor ("Right", Ast.Var "b"));
  ]) in
  expect_eq_circ ~ty_env:env_s "CASE-TAG-ID-01: identity case == id[Bool]"
    case_id (Ast.Id bool_ty);

  (* CASE-TAG-FLIP-01: unconditional flip == twist⊕ *)
  let case_flip = Ast.Case (Ast.Var "s", [
    (Ast.PatCtor ("Left", "a"), Ast.Ctor ("Right", Ast.Var "a"));
    (Ast.PatCtor ("Right", "b"), Ast.Ctor ("Left", Ast.Var "b"));
  ]) in
  expect_eq_circ ~ty_env:env_s "CASE-TAG-FLIP-01: flip case == twist⊕"
    case_flip (Ast.TwistP (Ast.TyQ, Ast.TyQ));

  (* CASE-TAG-PARTIAL-01: both produce Left — reject *)
  let case_partial1 = Ast.Case (Ast.Var "s", [
    (Ast.PatCtor ("Left", "a"), Ast.Ctor ("Left", Ast.Var "a"));
    (Ast.PatCtor ("Right", "b"), Ast.Ctor ("Left", Ast.Var "b"));
  ]) in
  expect_error_contains ~ty_env:env_s "CASE-TAG-PARTIAL-01: both Left (reject)"
    case_partial1 "partial constructor flip";

  (* CASE-TAG-PARTIAL-02: both produce Right — reject *)
  let case_partial2 = Ast.Case (Ast.Var "s", [
    (Ast.PatCtor ("Left", "a"), Ast.Ctor ("Right", Ast.Var "a"));
    (Ast.PatCtor ("Right", "b"), Ast.Ctor ("Right", Ast.Var "b"));
  ]) in
  expect_error_contains ~ty_env:env_s "CASE-TAG-PARTIAL-02: both Right (reject)"
    case_partial2 "partial constructor flip";

  print_endline ""

(* ================================================================ *)
(* §6: Rigorous nesting tests                                        *)
(* ================================================================ *)

let test_section_6 () =
  print_endline "§6. Rigorous nesting";

  (* T4 := ((Q + Q) + Q) + Q *)
  let t2 = Ast.TyPlus (Ast.TyQ, Ast.TyQ) in
  let t3 = Ast.TyPlus (t2, Ast.TyQ) in
  let t4 = Ast.TyPlus (t3, Ast.TyQ) in

  let env_x = make_ty_env [("x", t4)] in

  (* NEST-OK-01: triple-nested identity case on T4 — must compile
     Outer: case x of
       Left(mid) => Left(case mid of
         Left(inner) => Left(case inner of
           Left(a) => Left(a) | Right(b) => Right(b))
       | Right(c) => Right(c))
     | Right(d) => Right(d) *)
  let nest_ok_01 = Ast.Case (Ast.Var "x", [
    (Ast.PatCtor ("Left", "mid"),
      Ast.Ctor ("Left",
        Ast.Case (Ast.Var "mid", [
          (Ast.PatCtor ("Left", "inner"),
            Ast.Ctor ("Left",
              Ast.Case (Ast.Var "inner", [
                (Ast.PatCtor ("Left", "a"), Ast.Ctor ("Left", Ast.Var "a"));
                (Ast.PatCtor ("Right", "b"), Ast.Ctor ("Right", Ast.Var "b"));
              ])));
          (Ast.PatCtor ("Right", "c"), Ast.Ctor ("Right", Ast.Var "c"));
        ])));
    (Ast.PatCtor ("Right", "d"), Ast.Ctor ("Right", Ast.Var "d"));
  ]) in
  ignore (expect_compile_ok ~ty_env:env_x "NEST-OK-01: triple-nested identity on T4"
    nest_ok_01);

  (* NEST-EQ-01: nested identity == id[T4] *)
  expect_eq_circ ~ty_env:env_x "NEST-EQ-01: nested identity case == id[T4]"
    nest_ok_01 (Ast.Id t4);

  (* NEST-ERR-01: partial flip at innermost level — reject *)
  let nest_err = Ast.Case (Ast.Var "x", [
    (Ast.PatCtor ("Left", "mid"),
      Ast.Ctor ("Left",
        Ast.Case (Ast.Var "mid", [
          (Ast.PatCtor ("Left", "inner"),
            Ast.Ctor ("Left",
              Ast.Case (Ast.Var "inner", [
                (Ast.PatCtor ("Left", "a"), Ast.Ctor ("Left", Ast.Var "a"));
                (* Partial flip: Right branch also produces Left *)
                (Ast.PatCtor ("Right", "b"), Ast.Ctor ("Left", Ast.Var "b"));
              ])));
          (Ast.PatCtor ("Right", "c"), Ast.Ctor ("Right", Ast.Var "c"));
        ])));
    (Ast.PatCtor ("Right", "d"), Ast.Ctor ("Right", Ast.Var "d"));
  ]) in
  expect_error_contains ~ty_env:env_x "NEST-ERR-01: partial flip at depth 3 (reject)"
    nest_err "partial constructor flip";

  (* NEST-EQ-02: transport roundtrip via assocPL;assocPR == id on T4 *)
  let roundtrip = Ast.Seq (
    Ast.AssocPL (t2, Ast.TyQ, Ast.TyQ),
    Ast.AssocPR (t2, Ast.TyQ, Ast.TyQ)) in
  expect_eq_circ "NEST-EQ-02: assocPL;assocPR == id on T4"
    roundtrip (Ast.Id t4);

  (* NEST-STRESS-01: 5-level deep nesting
     T5 = (((Q+Q)+Q)+Q)+Q *)
  let t5 = Ast.TyPlus (t4, Ast.TyQ) in
  let env_x5 = make_ty_env [("x", t5)] in

  (* Identity case at all levels *)
  let nest_stress = Ast.Case (Ast.Var "x", [
    (Ast.PatCtor ("Left", "inner4"),
      Ast.Ctor ("Left",
        Ast.Case (Ast.Var "inner4", [
          (Ast.PatCtor ("Left", "inner3"),
            Ast.Ctor ("Left",
              Ast.Case (Ast.Var "inner3", [
                (Ast.PatCtor ("Left", "inner2"),
                  Ast.Ctor ("Left",
                    Ast.Case (Ast.Var "inner2", [
                      (Ast.PatCtor ("Left", "a"), Ast.Ctor ("Left", Ast.Var "a"));
                      (Ast.PatCtor ("Right", "b"), Ast.Ctor ("Right", Ast.Var "b"));
                    ])));
                (Ast.PatCtor ("Right", "c"), Ast.Ctor ("Right", Ast.Var "c"));
              ])));
          (Ast.PatCtor ("Right", "d"), Ast.Ctor ("Right", Ast.Var "d"));
        ])));
    (Ast.PatCtor ("Right", "e"), Ast.Ctor ("Right", Ast.Var "e"));
  ]) in
  ignore (expect_compile_ok ~ty_env:env_x5 "NEST-STRESS-01: 5-level deep identity"
    nest_stress);

  expect_eq_circ ~ty_env:env_x5 "NEST-STRESS-01-eq: 5-level identity == id[T5]"
    nest_stress (Ast.Id t5);

  (* NEST-STRESS-02: partial flip at depth 4 in 5-level sum — reject
     Same as NEST-STRESS-01 but the innermost case has both branches
     producing Left (partial flip). Depth 4 ≥ 3. *)
  let nest_stress_02 = Ast.Case (Ast.Var "x", [
    (Ast.PatCtor ("Left", "inner4"),
      Ast.Ctor ("Left",
        Ast.Case (Ast.Var "inner4", [
          (Ast.PatCtor ("Left", "inner3"),
            Ast.Ctor ("Left",
              Ast.Case (Ast.Var "inner3", [
                (Ast.PatCtor ("Left", "inner2"),
                  Ast.Ctor ("Left",
                    Ast.Case (Ast.Var "inner2", [
                      (Ast.PatCtor ("Left", "a"), Ast.Ctor ("Left", Ast.Var "a"));
                      (* Partial flip: Right branch also produces Left *)
                      (Ast.PatCtor ("Right", "b"), Ast.Ctor ("Left", Ast.Var "b"));
                    ])));
                (Ast.PatCtor ("Right", "c"), Ast.Ctor ("Right", Ast.Var "c"));
              ])));
          (Ast.PatCtor ("Right", "d"), Ast.Ctor ("Right", Ast.Var "d"));
        ])));
    (Ast.PatCtor ("Right", "e"), Ast.Ctor ("Right", Ast.Var "e"));
  ]) in
  expect_error_contains ~ty_env:env_x5
    "NEST-STRESS-02: partial flip at depth 4 in 5-level sum (reject)"
    nest_stress_02 "partial constructor flip";

  print_endline ""

(* ================================================================ *)
(* §7: Interaction tests: ⊗ with nested ⊕ cases                     *)
(* ================================================================ *)

let test_section_7 () =
  print_endline "§7. Tensor × sum interaction";

  (* TEN-SUM-OK-01: let (a,s) = id[Q⊗Bool] in (a ⊗ case s ...) == id[Q⊗Bool]
     Type: Q ⊗ (Q+Q) → Q ⊗ (Q+Q) *)
  let ten_sum_ty = Ast.TyTensor (Ast.TyQ, bool_ty) in
  let ten_sum_ok = Ast.LetTen ("a", "s", Ast.TyQ, bool_ty,
    Ast.Id ten_sum_ty,
    Ast.Ten (
      Ast.Var "a",
      Ast.Case (Ast.Var "s", [
        (Ast.PatCtor ("Left", "b"), Ast.Ctor ("Left", Ast.Var "b"));
        (Ast.PatCtor ("Right", "c"), Ast.Ctor ("Right", Ast.Var "c"));
      ]))) in
  expect_eq_circ "TEN-SUM-OK-01: destructure⊗ + identity case == id[Q⊗Bool]"
    ten_sum_ok (Ast.Id ten_sum_ty);

  (* TEN-SUM-OK-02: case on tag preserving constructor, H on payload
     Type: (Q+Q) ⊗ Q → (Q+Q) ⊗ Q
     let (tag,payload) = id[(Q+Q)⊗Q] in
       case tag of L a => L a | R b => R b    ⊗    (payload ; H) *)
  let bool_q_ty = Ast.TyTensor (bool_ty, Ast.TyQ) in
  let ten_sum_ok_02 = Ast.LetTen ("tag", "payload", bool_ty, Ast.TyQ,
    Ast.Id bool_q_ty,
    Ast.Ten (
      Ast.Case (Ast.Var "tag", [
        (Ast.PatCtor ("Left", "a"), Ast.Ctor ("Left", Ast.Var "a"));
        (Ast.PatCtor ("Right", "b"), Ast.Ctor ("Right", Ast.Var "b"));
      ]),
      Ast.Seq (Ast.Var "payload", Ast.GateH 0))) in
  ignore (expect_compile_ok "TEN-SUM-OK-02: identity case on tag + H on payload"
    ten_sum_ok_02);

  (* The tag-preserving case is identity, so the whole thing == id⊗H *)
  let id_tensor_h = Ast.Ten (Ast.Id bool_ty, Ast.GateH 0) in
  expect_eq_circ "TEN-SUM-OK-02-eq: identity case⊗H == id[Bool]⊗H"
    ten_sum_ok_02 id_tensor_h;

  (* TEN-SUM-EQ-01: Nested sum inside tensor with reassociation.
     f : Bool⊗Q → Bool⊗Q applies H inside both branches + S on Q:
       let (s,q) = id[Bool⊗Q] in
         (case s of L a => L(a;H) | R b => R(b;H)) ⊗ (q;S)
     g : Q⊗Bool → Q⊗Bool does the same with swapped tensor order:
       let (q,s) = id[Q⊗Bool] in
         (q;S) ⊗ (case s of L a => L(a;H) | R b => R(b;H))
     Transport: swap⊗(Q,Bool) ; f ; swap⊗(Bool,Q) == g *)
  let q_bool_ty = Ast.TyTensor (Ast.TyQ, bool_ty) in

  (* f on Bool⊗Q *)
  let f_bool_q = Ast.LetTen ("s", "q", bool_ty, Ast.TyQ,
    Ast.Id bool_q_ty,
    Ast.Ten (
      Ast.Case (Ast.Var "s", [
        (Ast.PatCtor ("Left", "a"),
          Ast.Ctor ("Left", Ast.Seq (Ast.Var "a", Ast.GateH 0)));
        (Ast.PatCtor ("Right", "b"),
          Ast.Ctor ("Right", Ast.Seq (Ast.Var "b", Ast.GateH 0)));
      ]),
      Ast.Seq (Ast.Var "q", Ast.GateS 0))) in

  (* g on Q⊗Bool *)
  let g_q_bool = Ast.LetTen ("q", "s", Ast.TyQ, bool_ty,
    Ast.Id q_bool_ty,
    Ast.Ten (
      Ast.Seq (Ast.Var "q", Ast.GateS 0),
      Ast.Case (Ast.Var "s", [
        (Ast.PatCtor ("Left", "a"),
          Ast.Ctor ("Left", Ast.Seq (Ast.Var "a", Ast.GateH 0)));
        (Ast.PatCtor ("Right", "b"),
          Ast.Ctor ("Right", Ast.Seq (Ast.Var "b", Ast.GateH 0)));
      ]))) in

  (* Transport: swap⊗(Q,Bool) ; f ; swap⊗(Bool,Q) == g *)
  let transported_f = Ast.Seq (
    Ast.Seq (
      Ast.TwistT (Ast.TyQ, bool_ty),
      f_bool_q),
    Ast.TwistT (bool_ty, Ast.TyQ)) in
  expect_eq_circ "TEN-SUM-EQ-01: swap⊗;f;swap⊗ == g (nested sum in tensor transport)"
    transported_f g_q_bool;

  print_endline ""

(* ================================================================ *)
(* §8: Bool→Bool unitary constants                                   *)
(* ================================================================ *)

let test_section_8 () =
  print_endline "§8. Bool→Bool unitary constants";

  let env_b = make_ty_env [("b", bool_ty)] in

  (* BOOL-U2-OK-01: basic gate compilation *)
  ignore (expect_compile_ok "BOOL-U2-OK-01a: H[0]" (Ast.GateH 0));
  ignore (expect_compile_ok "BOOL-U2-OK-01b: S[0]" (Ast.GateS 0));
  ignore (expect_compile_ok "BOOL-U2-OK-01c: X[0]" (Ast.GateX 0));
  ignore (expect_compile_ok "BOOL-U2-OK-01d: T[0]" (Ast.GateT 0));

  (* BOOL-U2-OK-02: H under both branches (branch-local payload op)
     case b of Left(u) => Left(u;H) | Right(v) => Right(v;H)
     This should equal: id[tag] ⊗ H[payload] — i.e., H on payload regardless of tag. *)
  let case_h_both = Ast.Case (Ast.Var "b", [
    (Ast.PatCtor ("Left", "u"),
      Ast.Ctor ("Left", Ast.Seq (Ast.Var "u", Ast.GateH 0)));
    (Ast.PatCtor ("Right", "v"),
      Ast.Ctor ("Right", Ast.Seq (Ast.Var "v", Ast.GateH 0)));
  ]) in
  ignore (expect_compile_ok ~ty_env:env_b "BOOL-U2-OK-02: H under both branches"
    case_h_both);

  (* BOOL-U2-OK-03: H with tag flip
     case b of Left(u) => Right(u;H) | Right(v) => Left(v;H)
     == twist⊕ followed by H on payload *)
  let case_h_flip = Ast.Case (Ast.Var "b", [
    (Ast.PatCtor ("Left", "u"),
      Ast.Ctor ("Right", Ast.Seq (Ast.Var "u", Ast.GateH 0)));
    (Ast.PatCtor ("Right", "v"),
      Ast.Ctor ("Left", Ast.Seq (Ast.Var "v", Ast.GateH 0)));
  ]) in
  ignore (expect_compile_ok ~ty_env:env_b "BOOL-U2-OK-03: H with tag flip (compiles)"
    case_h_flip);

  print_endline ""

(* ================================================================ *)
(* §9: Property-based fuzz suite (PROP-TAG-01, PROP-TAG-02)          *)
(* ================================================================ *)

let test_section_9 () =
  print_endline "§9. Property-based fuzz suite";

  Random.init 42;

  (* Symmetric sum tree:
     depth 0: Q
     depth 1: Q + Q              (width 2)
     depth 2: (Q+Q) + (Q+Q)      (width 3)
     depth 3: nested further      (width 4)
     Both summands at each level are the same type, so partial flip
     is well-typed but semantically non-unitary (must be rejected). *)
  let rec make_sym_sum d =
    if d <= 0 then Ast.TyQ
    else let sub = make_sym_sum (d - 1) in Ast.TyPlus (sub, sub)
  in

  (* Build a nested case on a symmetric sum type.
     mode_fn : int -> (string * string) maps each depth level to the
     output constructor pair (out_for_left_branch, out_for_right_branch).
     Identity:  ("Left", "Right")
     Flip:      ("Right", "Left")
     Partial-L: ("Left", "Left")
     Partial-R: ("Right", "Right") *)
  let rec make_nested_case scrutinee depth mode_fn =
    if depth <= 0 then scrutinee
    else
      let vl = "l" ^ string_of_int depth in
      let vr = "r" ^ string_of_int depth in
      let (out_l, out_r) = mode_fn depth in
      Ast.Case (scrutinee, [
        (Ast.PatCtor ("Left", vl),
          Ast.Ctor (out_l, make_nested_case (Ast.Var vl) (depth - 1) mode_fn));
        (Ast.PatCtor ("Right", vr),
          Ast.Ctor (out_r, make_nested_case (Ast.Var vr) (depth - 1) mode_fn));
      ])
  in

  (* PROP-TAG-01: partial flip cases must be rejected.
     At a randomly chosen level, both branches output the same constructor. *)
  let num_tag_tests = 20 in
  for trial = 0 to num_tag_tests - 1 do
    let depth = 1 + Random.int 3 in (* 1, 2, or 3 *)
    let partial_level = 1 + Random.int depth in
    let partial_side = if Random.bool () then "Left" else "Right" in

    let ty = make_sym_sum depth in
    let env = make_ty_env [("x", ty)] in

    let mode_fn d =
      if d = partial_level then (partial_side, partial_side)
      else ("Left", "Right")
    in

    let term = make_nested_case (Ast.Var "x") depth mode_fn in

    expect_error_contains ~ty_env:env
      (Printf.sprintf "PROP-TAG-01[%d]: partial '%s' at level %d, depth %d"
        trial partial_side partial_level depth)
      term "partial constructor flip"
  done;

  (* PROP-TAG-02: safe nesting must not be rejected.
     At each level, randomly choose identity or full flip.
     Cap depth at 2 to avoid QControlBox limitation at depth 3. *)
  for trial = 0 to num_tag_tests - 1 do
    let depth = 1 + Random.int 2 in

    let ty = make_sym_sum depth in
    let env = make_ty_env [("x", ty)] in

    (* Randomly assign identity or flip to each level *)
    let level_modes = Array.init (depth + 1) (fun _ ->
      if Random.bool () then ("Left", "Right")  (* identity *)
      else ("Right", "Left")                     (* full flip *)
    ) in

    let mode_fn d =
      if d >= 0 && d < Array.length level_modes then level_modes.(d)
      else ("Left", "Right")
    in

    let term = make_nested_case (Ast.Var "x") depth mode_fn in

    (* Apply a gate inside the leaves to make the test non-trivial *)
    let term_with_gate =
      let rec add_leaf_gate t =
        match t with
        | Ast.Case (scrut, branches) ->
          Ast.Case (scrut, List.map (fun (pat, body) ->
            (pat, add_leaf_gate body)
          ) branches)
        | Ast.Ctor (name, payload) ->
          Ast.Ctor (name, add_leaf_gate payload)
        | Ast.Var v ->
          Ast.Seq (Ast.Var v, Ast.GateH 0)
        | other -> other
      in
      add_leaf_gate term
    in

    ignore (expect_compile_ok ~ty_env:env
      (Printf.sprintf "PROP-TAG-02[%d]: safe case (depth %d, random id/flip + H)"
        trial depth)
      term_with_gate)
  done;

  print_endline ""

(* ================================================================ *)
(* Main: Run all sections                                            *)
(* ================================================================ *)

let () =
  print_endline "================================================================";
  print_endline "NEWTESTS: Comprehensive test suite for the source language";
  print_endline "  (specification: RadhaMSG/NEWTESTS.md)";
  print_endline "================================================================";
  print_endline "";

  test_infra ();
  test_section_2 ();
  test_section_3 ();
  test_section_4 ();
  test_section_5 ();
  test_section_6 ();
  test_section_7 ();
  test_section_8 ();
  test_section_9 ();

  print_endline "================================================================";
  Printf.printf "Results: %d/%d passed, %d failed, %d skipped\n"
    !tests_passed !tests_run !tests_failed !tests_skipped;
  print_endline "================================================================";

  if !tests_failed > 0 then
    exit 1
