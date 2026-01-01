(** Elaborate: Transform surface language to core IR.

    The elaboration phase:
    1. Checks variable binding and scope
    2. Eliminates λ-abstraction (macro-only)
    3. Eliminates let bindings (macro expansion)
    4. Transforms case expressions to structural rewiring

    After elaboration, we have only:
    - Sequential composition (;)
    - Tensor composition (⊗)
    - Structural primitives (Id, Twist, Assoc)
    - Gate primitives (H, S, CX, etc.)
    - ExpI for certified involutions
*)

(** Elaboration errors *)
type error =
  | UnboundVariable of string
  | UnboundTypeVariable of string
  | UnknownConstructor of string
  | TypeMismatch of { expected : Ast.ty; actual : Ast.ty }
  | ArityMismatch of { name : string; expected : int; actual : int }
  | NonLinearUse of string  (* Linear variables must be used exactly once *)
  | UnusedVariable of string
  | PatternMismatch of string

exception ElaborateError of error

let error_to_string = function
  | UnboundVariable v -> Printf.sprintf "Unbound variable: %s" v
  | UnboundTypeVariable v -> Printf.sprintf "Unbound type variable: %s" v
  | UnknownConstructor c -> Printf.sprintf "Unknown constructor: %s" c
  | TypeMismatch { expected; actual } ->
    Printf.sprintf "Type mismatch: expected %s, got %s"
      (Ast.ty_to_string expected) (Ast.ty_to_string actual)
  | ArityMismatch { name; expected; actual } ->
    Printf.sprintf "Arity mismatch for %s: expected %d, got %d" name expected actual
  | NonLinearUse v -> Printf.sprintf "Non-linear use of variable: %s" v
  | UnusedVariable v -> Printf.sprintf "Unused variable: %s" v
  | PatternMismatch msg -> Printf.sprintf "Pattern mismatch: %s" msg

(** Type environment: maps variables to their types *)
module TyEnv = struct
  type t = (Ast.var * Ast.ty) list

  let empty : t = []

  let extend env x ty = (x, ty) :: env

  let lookup env x =
    List.assoc_opt x env

  let remove env x =
    List.filter (fun (y, _) -> y <> x) env

  let domain env = List.map fst env
end

(** Type variable environment *)
module TyVarEnv = struct
  type t = Ast.tyvar list

  let empty : t = []

  let extend env v = v :: env

  let mem env v = List.mem v env
end

(** Datatype environment: maps type names to their info *)
module DtEnv = struct
  type ctor_info = {
    ctor_name : string;
    payload : Ast.ty;
    index : int;
  }

  type dt_info = {
    name : string;
    arity : int;
    tyvars : Ast.tyvar list;
    constructors : ctor_info list;
    rep : Ast.ty;  (* The underlying Plus type *)
  }

  type t = dt_info list

  let empty : t = []

  let register dt env = dt :: env

  let lookup env name =
    List.find_opt (fun dt -> dt.name = name) env

  let lookup_ctor env ctor_name =
    List.find_map (fun dt ->
      match List.find_opt (fun c -> c.ctor_name = ctor_name) dt.constructors with
      | Some c -> Some (dt, c)
      | None -> None
    ) env
end

(** Core IR: the target of elaboration *)
module Core = struct
  (** Core types (same structure, but validated) *)
  type ty = Ast.ty

  (** Core terms: no λ, let, or case *)
  type term =
    | Seq of term * term
    | Ten of term * term
    | Id of ty
    | TwistT of ty * ty
    | TwistP of ty * ty
    | AssocTL of ty * ty * ty
    | AssocTR of ty * ty * ty
    | AssocPL of ty * ty * ty
    | AssocPR of ty * ty * ty
    | GateH of int
    | GateS of int
    | GateCX of int * int
    | GateX of int
    | GateY of int
    | GateZ of int
    | GateT of int
    | GateRz of float * int
    | ExpI of float * term

  let rec term_to_string = function
    | Seq (f, g) -> Printf.sprintf "%s ; %s" (term_to_string f) (term_to_string g)
    | Ten (f, g) -> Printf.sprintf "%s ⊗ %s" (term_to_string f) (term_to_string g)
    | Id ty -> Printf.sprintf "id[%s]" (Ast.ty_to_string ty)
    | TwistT (a, b) -> Printf.sprintf "twist⊗[%s, %s]" (Ast.ty_to_string a) (Ast.ty_to_string b)
    | TwistP (a, b) -> Printf.sprintf "twist+[%s, %s]" (Ast.ty_to_string a) (Ast.ty_to_string b)
    | AssocTL _ -> "assoc⊗L"
    | AssocTR _ -> "assoc⊗R"
    | AssocPL _ -> "assoc+L"
    | AssocPR _ -> "assoc+R"
    | GateH i -> Printf.sprintf "H[%d]" i
    | GateS i -> Printf.sprintf "S[%d]" i
    | GateCX (i, j) -> Printf.sprintf "CX[%d,%d]" i j
    | GateX i -> Printf.sprintf "X[%d]" i
    | GateY i -> Printf.sprintf "Y[%d]" i
    | GateZ i -> Printf.sprintf "Z[%d]" i
    | GateT i -> Printf.sprintf "T[%d]" i
    | GateRz (theta, i) -> Printf.sprintf "Rz[%.4f,%d]" theta i
    | ExpI (theta, j) -> Printf.sprintf "exp_i(%.4f, %s)" theta (term_to_string j)
end

(** Check that a type is well-formed (all type variables bound) *)
let rec check_ty tyvar_env = function
  | Ast.TyVar v ->
    if not (TyVarEnv.mem tyvar_env v) then
      raise (ElaborateError (UnboundTypeVariable v))
  | Ast.TyQ | Ast.TyUnit -> ()
  | Ast.TyTensor (a, b) | Ast.TyPlus (a, b) ->
    check_ty tyvar_env a;
    check_ty tyvar_env b
  | Ast.TyNamed (_, args) ->
    List.iter (check_ty tyvar_env) args

(** Collect free variables in a term *)
let rec free_vars = function
  | Ast.Var x -> [x]
  | Ast.Lam (x, _, body) ->
    List.filter (fun v -> v <> x) (free_vars body)
  | Ast.App (f, e) -> free_vars f @ free_vars e
  | Ast.Let (x, e1, e2) ->
    free_vars e1 @ List.filter (fun v -> v <> x) (free_vars e2)
  | Ast.Case (e, branches) ->
    free_vars e @ List.concat_map (fun (pat, body) ->
      let bound = match pat with
        | Ast.PatCtor (_, v) -> [v]
        | Ast.PatWild -> []
      in
      List.filter (fun v -> not (List.mem v bound)) (free_vars body)
    ) branches
  | Ast.Ctor (_, e) -> free_vars e
  | Ast.Seq (f, g) | Ast.Ten (f, g) -> free_vars f @ free_vars g
  | Ast.Id _ | Ast.TwistT _ | Ast.TwistP _
  | Ast.AssocTL _ | Ast.AssocTR _ | Ast.AssocPL _ | Ast.AssocPR _
  | Ast.GateH _ | Ast.GateS _ | Ast.GateCX _
  | Ast.GateX _ | Ast.GateY _ | Ast.GateZ _ | Ast.GateT _
  | Ast.GateRz _ -> []
  | Ast.ExpI (_, j) -> free_vars j

(** Check that all variables in a term are bound *)
let check_scope env term =
  let fvs = free_vars term in
  let unbound = List.filter (fun v -> TyEnv.lookup env v = None) fvs in
  match unbound with
  | [] -> ()
  | v :: _ -> raise (ElaborateError (UnboundVariable v))

(** Elaborate a surface term to core IR.

    Key transformations:
    - λx:A. e  =>  error (should be applied, not standalone)
    - App(λx:A. e, v)  =>  [v/x]e (substitution, then elaborate)
    - let x = e1 in e2  =>  elaborate to sequential composition
    - case e of ...  =>  structural rewiring via TwistPlus/Assoc
*)
let rec elaborate tyvar_env ty_env dt_env term : Core.term =
  check_scope ty_env term;
  match term with
  | Ast.Var _ ->
    (* Variables should have been substituted away *)
    failwith "elaborate: unexpected variable (should be eliminated by substitution)"

  | Ast.Lam _ ->
    failwith "elaborate: standalone λ (should be applied)"

  | Ast.App (Ast.Lam (x, ty, body), arg) ->
    (* β-reduction: substitute and elaborate *)
    check_ty tyvar_env ty;
    let body' = subst x arg body in
    elaborate tyvar_env ty_env dt_env body'

  | Ast.App (f, _) ->
    failwith (Printf.sprintf "elaborate: non-λ application: %s" (Ast.term_to_string f))

  | Ast.Let (x, e1, e2) ->
    (* Let is just substitution at the surface level *)
    let e2' = subst x e1 e2 in
    elaborate tyvar_env ty_env dt_env e2'

  | Ast.Case (scrutinee, branches) ->
    (* Case elaboration: scrutinee must elaborate to identity,
       branches become structural permutation *)
    elaborate_case tyvar_env ty_env dt_env scrutinee branches

  | Ast.Ctor (_name, payload) ->
    (* Constructor application: elaborate payload, compose with injection *)
    let payload' = elaborate tyvar_env ty_env dt_env payload in
    (* For now, constructors are identity (payload already in position) *)
    payload'

  | Ast.Seq (f, g) ->
    Core.Seq (elaborate tyvar_env ty_env dt_env f,
              elaborate tyvar_env ty_env dt_env g)

  | Ast.Ten (f, g) ->
    Core.Ten (elaborate tyvar_env ty_env dt_env f,
              elaborate tyvar_env ty_env dt_env g)

  | Ast.Id ty -> Core.Id ty
  | Ast.TwistT (a, b) -> Core.TwistT (a, b)
  | Ast.TwistP (a, b) -> Core.TwistP (a, b)
  | Ast.AssocTL (a, b, c) -> Core.AssocTL (a, b, c)
  | Ast.AssocTR (a, b, c) -> Core.AssocTR (a, b, c)
  | Ast.AssocPL (a, b, c) -> Core.AssocPL (a, b, c)
  | Ast.AssocPR (a, b, c) -> Core.AssocPR (a, b, c)
  | Ast.GateH i -> Core.GateH i
  | Ast.GateS i -> Core.GateS i
  | Ast.GateCX (i, j) -> Core.GateCX (i, j)
  | Ast.GateX i -> Core.GateX i
  | Ast.GateY i -> Core.GateY i
  | Ast.GateZ i -> Core.GateZ i
  | Ast.GateT i -> Core.GateT i
  | Ast.GateRz (theta, i) -> Core.GateRz (theta, i)
  | Ast.ExpI (theta, j) ->
    Core.ExpI (theta, elaborate tyvar_env ty_env dt_env j)

(** Substitute v for x in term *)
and subst x v = function
  | Ast.Var y -> if y = x then v else Ast.Var y
  | Ast.Lam (y, ty, body) ->
    if y = x then Ast.Lam (y, ty, body)  (* x is shadowed *)
    else Ast.Lam (y, ty, subst x v body)
  | Ast.App (f, e) -> Ast.App (subst x v f, subst x v e)
  | Ast.Let (y, e1, e2) ->
    let e1' = subst x v e1 in
    if y = x then Ast.Let (y, e1', e2)  (* x is shadowed *)
    else Ast.Let (y, e1', subst x v e2)
  | Ast.Case (e, branches) ->
    Ast.Case (subst x v e,
              List.map (fun (pat, body) ->
                let shadowed = match pat with
                  | Ast.PatCtor (_, y) -> y = x
                  | Ast.PatWild -> false
                in
                if shadowed then (pat, body)
                else (pat, subst x v body)
              ) branches)
  | Ast.Ctor (name, e) -> Ast.Ctor (name, subst x v e)
  | Ast.Seq (f, g) -> Ast.Seq (subst x v f, subst x v g)
  | Ast.Ten (f, g) -> Ast.Ten (subst x v f, subst x v g)
  | (Ast.Id _ | Ast.TwistT _ | Ast.TwistP _
    | Ast.AssocTL _ | Ast.AssocTR _ | Ast.AssocPL _ | Ast.AssocPR _
    | Ast.GateH _ | Ast.GateS _ | Ast.GateCX _
    | Ast.GateX _ | Ast.GateY _ | Ast.GateZ _ | Ast.GateT _
    | Ast.GateRz _) as t -> t
  | Ast.ExpI (theta, j) -> Ast.ExpI (theta, subst x v j)

(** Elaborate case expression to structural rewiring.

    For a case like:
      case e of F(a) => T(a) | T(b) => F(b)

    We generate TwistPlus to permute constructors.
*)
and elaborate_case _tyvar_env _ty_env _dt_env scrutinee branches =
  (* For now, a simplified elaboration:
     - The scrutinee should be a variable (structural position)
     - The branches define a permutation of constructors

     This will be connected to the existing Perm_gen module. *)
  let n = List.length branches in

  (* Extract constructor names from patterns *)
  let branch_ctors = List.map (fun (pat, _) ->
    match pat with
    | Ast.PatCtor (name, _) -> name
    | Ast.PatWild -> "_"
  ) branches in

  if n = 2 then begin
    (* Two-constructor case: use TwistPlus if swapped *)
    match scrutinee with
    | Ast.Var _ ->
      (* Check if this is a swap *)
      let c0 = List.nth branch_ctors 0 in
      let c1 = List.nth branch_ctors 1 in
      if c0 = "T" && c1 = "F" then
        (* This is swap: F,T -> T,F *)
        Core.TwistP (Ast.TyQ, Ast.TyQ)  (* Placeholder types *)
      else
        Core.Id Ast.TyUnit  (* Identity permutation *)
    | _ ->
      (* Complex scrutinee: elaborate it first *)
      Core.Id Ast.TyUnit  (* Placeholder *)
  end
  else begin
    (* n > 2: need general permutation *)
    (* For now, just return identity as placeholder *)
    Core.Id Ast.TyUnit
  end

(** Elaborate a definition *)
let elaborate_def tyvar_env ty_env dt_env = function
  | Ast.DefType (name, tyvars, ctors) ->
    (* Register the datatype *)
    let tyvar_env' = List.fold_left TyVarEnv.extend tyvar_env tyvars in
    List.iter (fun (_, ty) -> check_ty tyvar_env' ty) ctors;

    let ctor_infos = List.mapi (fun i (cname, payload) ->
      DtEnv.{ ctor_name = cname; payload; index = i }
    ) ctors in

    (* Build representation type (left-associated Plus) *)
    let rep = match ctors with
      | [] -> Ast.TyUnit
      | [(_, ty)] -> ty
      | (_, ty0) :: rest ->
        List.fold_left (fun acc (_, ty) -> Ast.TyPlus (acc, ty)) ty0 rest
    in

    let dt_info = DtEnv.{
      name;
      arity = List.length tyvars;
      tyvars;
      constructors = ctor_infos;
      rep;
    } in
    (tyvar_env, ty_env, DtEnv.register dt_info dt_env, None)

  | Ast.DefTerm (name, dom, cod, body) ->
    check_ty tyvar_env dom;
    check_ty tyvar_env cod;
    let ty_env' = TyEnv.extend ty_env name (Ast.TyTensor (dom, cod)) in
    let core = elaborate tyvar_env ty_env dt_env body in
    (tyvar_env, ty_env', dt_env, Some (name, dom, cod, core))

(** Elaborate a complete program *)
let elaborate_program (program : Ast.program) =
  let tyvar_env = TyVarEnv.empty in
  let ty_env = TyEnv.empty in
  let dt_env = DtEnv.empty in

  let _tyvar_env, _ty_env, _dt_env, defs =
    List.fold_left (fun (tv, te, dt, acc) def ->
      let tv', te', dt', result = elaborate_def tv te dt def in
      let acc' = match result with
        | Some d -> d :: acc
        | None -> acc
      in
      (tv', te', dt', acc')
    ) (tyvar_env, ty_env, dt_env, []) program.defs
  in

  let main = match program.main with
    | Some m -> Some (elaborate tyvar_env ty_env dt_env m)
    | None -> None
  in

  (List.rev defs, main)
