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

  (** Gate names for the universal gate representation *)
  type gate_name =
    | GH | GS | GSdg | GX | GY | GZ | GT | GTdg
    | GRz of float | GRx of float | GRy of float
    | GCX  (* CNOT - has 2 targets, no separate control *)

  (** Universal gate representation with stackable controls.
      This avoids an infinite family of CCH, CCCH, ... constructors. *)
  type gate = {
    name : gate_name;
    targets : int list;      (* target wire(s) *)
    controls : int list;     (* control wires - can be empty or multiple *)
  }

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
    | DistL of ty * ty * ty   (* A ⊗ (B + C) → (A ⊗ B) + (A ⊗ C) *)
    | DistR of ty * ty * ty   (* (A + B) ⊗ C → (A ⊗ C) + (B ⊗ C) *)
    | Gate of gate
    | ExpI of float * term

  (** Smart constructors for gates (backward compatibility) *)
  let gate_h i = Gate { name = GH; targets = [i]; controls = [] }
  let gate_s i = Gate { name = GS; targets = [i]; controls = [] }
  let gate_sdg i = Gate { name = GSdg; targets = [i]; controls = [] }
  let gate_x i = Gate { name = GX; targets = [i]; controls = [] }
  let gate_y i = Gate { name = GY; targets = [i]; controls = [] }
  let gate_z i = Gate { name = GZ; targets = [i]; controls = [] }
  let gate_t i = Gate { name = GT; targets = [i]; controls = [] }
  let gate_tdg i = Gate { name = GTdg; targets = [i]; controls = [] }
  let gate_rz theta i = Gate { name = GRz theta; targets = [i]; controls = [] }
  let gate_rx theta i = Gate { name = GRx theta; targets = [i]; controls = [] }
  let gate_ry theta i = Gate { name = GRy theta; targets = [i]; controls = [] }
  let gate_cx i j = Gate { name = GCX; targets = [i; j]; controls = [] }

  (** Controlled gate constructors *)
  let gate_ch ctrl tgt = Gate { name = GH; targets = [tgt]; controls = [ctrl] }
  let gate_cs ctrl tgt = Gate { name = GS; targets = [tgt]; controls = [ctrl] }
  let gate_csdg ctrl tgt = Gate { name = GSdg; targets = [tgt]; controls = [ctrl] }

  (** Add a control to a gate (stacking for nested cases) *)
  let add_control ctrl g =
    { g with controls = ctrl :: g.controls }

  (** Pretty-print gate name *)
  let gate_name_to_string = function
    | GH -> "H" | GS -> "S" | GSdg -> "Sdg"
    | GX -> "X" | GY -> "Y" | GZ -> "Z"
    | GT -> "T" | GTdg -> "Tdg"
    | GRz theta -> Printf.sprintf "Rz(%.4f)" theta
    | GRx theta -> Printf.sprintf "Rx(%.4f)" theta
    | GRy theta -> Printf.sprintf "Ry(%.4f)" theta
    | GCX -> "CX"

  (** Pretty-print a gate *)
  let gate_to_string g =
    let ctrl_prefix = match g.controls with
      | [] -> ""
      | ctrls -> String.concat "" (List.map (fun c -> Printf.sprintf "C%d-" c) ctrls)
    in
    let targets_str = String.concat "," (List.map string_of_int g.targets) in
    Printf.sprintf "%s%s[%s]" ctrl_prefix (gate_name_to_string g.name) targets_str

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
    | DistL _ -> "distL"
    | DistR _ -> "distR"
    | Gate g -> gate_to_string g
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
  | Ast.DistL _ | Ast.DistR _
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
    - case e of ...  =>  controlled gates for quantum case expressions

    The ~base parameter is the wire offset for the current term's layout.
    For nested sums, the tag wire is at base+0, payload starts at base+1.
*)
let rec elaborate ?(base=0) tyvar_env ty_env dt_env term : Core.term =
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
    elaborate ~base tyvar_env ty_env dt_env body'

  | Ast.App (f, _) ->
    failwith (Printf.sprintf "elaborate: non-λ application: %s" (Ast.term_to_string f))

  | Ast.Let (x, e1, e2) ->
    (* Let is just substitution at the surface level *)
    let e2' = subst x e1 e2 in
    elaborate ~base tyvar_env ty_env dt_env e2'

  | Ast.Case (scrutinee, branches) ->
    (* Case elaboration: controlled gates for quantum case expressions *)
    elaborate_case ~base tyvar_env ty_env dt_env scrutinee branches

  | Ast.Ctor (_name, payload) ->
    (* Constructor application: elaborate payload, compose with injection *)
    let payload' = elaborate ~base tyvar_env ty_env dt_env payload in
    (* For now, constructors are identity (payload already in position) *)
    payload'

  | Ast.Seq (f, g) ->
    Core.Seq (elaborate ~base tyvar_env ty_env dt_env f,
              elaborate ~base tyvar_env ty_env dt_env g)

  | Ast.Ten (f, g) ->
    Core.Ten (elaborate ~base tyvar_env ty_env dt_env f,
              elaborate ~base tyvar_env ty_env dt_env g)

  | Ast.Id ty -> Core.Id ty
  | Ast.TwistT (a, b) -> Core.TwistT (a, b)
  | Ast.TwistP (a, b) -> Core.TwistP (a, b)
  | Ast.AssocTL (a, b, c) -> Core.AssocTL (a, b, c)
  | Ast.AssocTR (a, b, c) -> Core.AssocTR (a, b, c)
  | Ast.AssocPL (a, b, c) -> Core.AssocPL (a, b, c)
  | Ast.AssocPR (a, b, c) -> Core.AssocPR (a, b, c)
  | Ast.DistL (a, b, c) -> Core.DistL (a, b, c)
  | Ast.DistR (a, b, c) -> Core.DistR (a, b, c)
  | Ast.GateH i -> Core.gate_h i
  | Ast.GateS i -> Core.gate_s i
  | Ast.GateCX (i, j) -> Core.gate_cx i j
  | Ast.GateX i -> Core.gate_x i
  | Ast.GateY i -> Core.gate_y i
  | Ast.GateZ i -> Core.gate_z i
  | Ast.GateT i -> Core.gate_t i
  | Ast.GateRz (theta, i) -> Core.gate_rz theta i
  | Ast.ExpI (theta, j) ->
    Core.ExpI (theta, elaborate ~base tyvar_env ty_env dt_env j)

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
    | Ast.DistL _ | Ast.DistR _
    | Ast.GateH _ | Ast.GateS _ | Ast.GateCX _
    | Ast.GateX _ | Ast.GateY _ | Ast.GateZ _ | Ast.GateT _
    | Ast.GateRz _) as t -> t
  | Ast.ExpI (theta, j) -> Ast.ExpI (theta, subst x v j)

(** Lift a Core.term to use controlled gates, with control on wire ctrl.

    For quantum case expressions, we need to transform gates in a branch
    to their controlled versions. The control wire is the tag qubit.

    If anti=true, we wrap with X gates: X[ctrl] ; controlled-term ; X[ctrl]
    This implements anti-control (control on |0⟩ rather than |1⟩).

    With the universal gate representation, this simply adds ctrl to the
    controls list - allowing arbitrary nesting of cases to stack controls.
*)
and lift_to_controlled ~anti ctrl term =
  if anti then
    (* Anti-control: X[ctrl] ; controlled-term ; X[ctrl] *)
    Core.Seq (Core.gate_x ctrl,
              Core.Seq (lift_to_controlled ~anti:false ctrl term,
                        Core.gate_x ctrl))
  else
    match term with
    (* Gates: add ctrl to the controls list (stacking for nested cases) *)
    | Core.Gate g -> Core.Gate (Core.add_control ctrl g)

    (* Composition: lift each part *)
    | Core.Seq (f, g) ->
        Core.Seq (lift_to_controlled ~anti:false ctrl f,
                  lift_to_controlled ~anti:false ctrl g)
    | Core.Ten (f, g) ->
        Core.Ten (lift_to_controlled ~anti:false ctrl f,
                  lift_to_controlled ~anti:false ctrl g)

    (* Identity doesn't need control *)
    | Core.Id ty -> Core.Id ty

    (* Structural ops are permutations - they don't emit gates,
       so they pass through unchanged *)
    | Core.TwistT (a, b) -> Core.TwistT (a, b)
    | Core.TwistP (a, b) -> Core.TwistP (a, b)
    | Core.AssocTL (a, b, c) -> Core.AssocTL (a, b, c)
    | Core.AssocTR (a, b, c) -> Core.AssocTR (a, b, c)
    | Core.AssocPL (a, b, c) -> Core.AssocPL (a, b, c)
    | Core.AssocPR (a, b, c) -> Core.AssocPR (a, b, c)
    | Core.DistL (a, b, c) -> Core.DistL (a, b, c)
    | Core.DistR (a, b, c) -> Core.DistR (a, b, c)

    (* ExpI: lift the body *)
    | Core.ExpI (theta, j) -> Core.ExpI (theta, lift_to_controlled ~anti:false ctrl j)

(** Elaborate case expression.

    For a case like:
      case e of Left(a) => f | Right(b) => g

    There are two modes:
    1. Classical case: scrutinee is a known constructor -> compile-time selection
    2. Quantum case: scrutinee is a superposition -> controlled gates

    For quantum case with 2 constructors:
      Elaborates to: Anti-controlled-left ; Controlled-right

    The ~base parameter is the wire offset for the current layout:
    - Tag wire is at base + 0
    - Payload wires start at base + 1
*)
and elaborate_case ~base tyvar_env ty_env dt_env scrutinee branches =
  let n = List.length branches in

  (* Check if this is a classical case (known constructor) *)
  let is_classical = match scrutinee with
    | Ast.Ctor _ -> true
    | _ -> false
  in

  if is_classical then
    (* Classical case: compile-time selection *)
    elaborate_classical_case ~base tyvar_env ty_env dt_env scrutinee branches
  else if n = 2 then
    (* Quantum case with 2 constructors *)
    elaborate_quantum_case_2 ~base tyvar_env ty_env dt_env scrutinee branches
  else
    (* n > 2: general quantum case (TODO) *)
    failwith (Printf.sprintf "elaborate_case: %d-constructor quantum case not yet implemented" n)

(** Classical case: scrutinee is a known constructor.
    Select the matching branch at compile time. *)
and elaborate_classical_case ~base tyvar_env ty_env dt_env scrutinee branches =
  (* For classical case, payload starts at base + 1 (after tag) *)
  let payload_base = base + 1 in
  match scrutinee with
  | Ast.Ctor (ctor_name, payload) ->
    (* Find matching branch *)
    let matching_branch = List.find_opt (fun (pat, _) ->
      match pat with
      | Ast.PatCtor (name, _) -> name = ctor_name
      | Ast.PatWild -> true
    ) branches in
    (match matching_branch with
     | Some (Ast.PatCtor (_, var), body) ->
       (* Substitute payload for pattern variable and elaborate at payload_base *)
       let body' = subst var payload body in
       elaborate ~base:payload_base tyvar_env ty_env dt_env body'
     | Some (Ast.PatWild, body) ->
       elaborate ~base:payload_base tyvar_env ty_env dt_env body
     | None ->
       failwith (Printf.sprintf "No matching branch for constructor %s" ctor_name))
  | _ ->
    failwith "elaborate_classical_case: expected constructor scrutinee"

(** Quantum case with 2 constructors.

    case x of Left(a) => f | Right(b) => g

    Elaborates to: Anti-controlled-left ; Controlled-right

    The tag qubit (at base) controls which branch is active.
    - Left branch (tag=0): left gates are anti-controlled
    - Right branch (tag=1): right gates are controlled

    For nested cases, the base parameter ensures each level uses the
    correct tag wire, and branch bodies are elaborated at payload_base.
*)
and elaborate_quantum_case_2 ~base tyvar_env ty_env dt_env scrutinee branches =
  (* Tag wire is at base, payload starts at base + 1 *)
  let tag_wire = base in
  let payload_base = base + 1 in

  (* Get the scrutinee type to determine payload types *)
  let (left_payload_ty, right_payload_ty) = match scrutinee with
    | Ast.Var x ->
      (match TyEnv.lookup ty_env x with
       | Some (Ast.TyPlus (a, b)) -> (a, b)
       | Some ty -> failwith (Printf.sprintf "elaborate_quantum_case_2: scrutinee %s has non-sum type %s" x (Ast.ty_to_string ty))
       | None -> (Ast.TyUnit, Ast.TyUnit))  (* Default if type unknown *)
    | _ -> (Ast.TyUnit, Ast.TyUnit)  (* Default for complex scrutinees *)
  in

  (* Get the two branches *)
  let (left_pat, left_body), (right_pat, right_body) = match branches with
    | [b0; b1] -> (b0, b1)
    | _ -> failwith "elaborate_quantum_case_2: expected exactly 2 branches"
  in

  (* Extract pattern variables and substitute with Id(payload_type).
     In a quantum case, the pattern variable represents "the payload that's there",
     which elaborates to identity on the payload wires. *)
  let left_var = match left_pat with
    | Ast.PatCtor (_, v) -> v
    | Ast.PatWild -> "_"
  in
  let right_var = match right_pat with
    | Ast.PatCtor (_, v) -> v
    | Ast.PatWild -> "_"
  in

  (* Detect if a branch body is a constructor wrapping the pattern variable.
     Returns (output_ctor_name option, inner_body) *)
  let unwrap_ctor body var =
    match body with
    | Ast.Ctor (name, Ast.Var v) when v = var -> (Some name, Ast.Id Ast.TyUnit)
    | Ast.Ctor (name, inner) -> (Some name, inner)
    | _ -> (None, body)
  in

  (* Detect constructor changes for tag handling *)
  let left_ctor_name = match left_pat with Ast.PatCtor (n, _) -> n | _ -> "Left" in
  let right_ctor_name = match right_pat with Ast.PatCtor (n, _) -> n | _ -> "Right" in

  let (left_output_ctor, left_inner) = unwrap_ctor left_body left_var in
  let (right_output_ctor, right_inner) = unwrap_ctor right_body right_var in

  (* Determine if each branch flips the tag *)
  let left_flips = match left_output_ctor with
    | Some name -> name <> left_ctor_name
    | None -> false
  in
  let right_flips = match right_output_ctor with
    | Some name -> name <> right_ctor_name
    | None -> false
  in

  (* Substitute pattern vars with Id before elaborating *)
  let left_body' = subst left_var (Ast.Id left_payload_ty) left_inner in
  let right_body' = subst right_var (Ast.Id right_payload_ty) right_inner in

  (* Elaborate the branch bodies at payload_base.
     For nested sums, this ensures inner cases use the correct wire offsets. *)
  let left_elaborated = elaborate ~base:payload_base tyvar_env ty_env dt_env left_body' in
  let right_elaborated = elaborate ~base:payload_base tyvar_env ty_env dt_env right_body' in

  (* Quantum case decomposition:
     Anti-controlled-right ; left ; Controlled-right

     This works because:
     - On |0⟩ (Left): anti-controlled-right fires, then left fires, then controlled-right does nothing
       = right⁻¹ ; left (but since right ; right⁻¹ = id, this gives left)
     - On |1⟩ (Right): anti-controlled-right does nothing, left fires, then controlled-right fires
       = left ; right

     Wait, this isn't quite right for the quantum switch. Let me reconsider.

     For QSwitch(f, g):
     - On |0⟩ (Zero): apply g then f
     - On |1⟩ (One): apply f then g

     The correct decomposition is:
     - Anti-C[right] ; left ; C[right]

     But we need to be careful about what "left" and "right" mean here.
     For QSwitch, if left = (g;f) and right = (f;g), then:
     - The difference is the ORDER of f and g.

     Actually, for the quantum switch, the correct decomposition uses the
     commutator structure. Let me use a simpler approach:

     For case q of Left => f | Right => g:
     - Apply f unconditionally (it's the "default" path)
     - Apply controlled-g†-then-g = controlled-(f†;g;f) to get the difference

     This is getting complicated. Let me use the direct approach from the plan:
     Anti-controlled-right ; left ; Controlled-right

     For this to work, we need f and g to be the DIFFERENCES from identity,
     not the full branch bodies. But in QSwitch, the branches ARE the operations.

     Let me simplify: for now, just emit the controlled gates directly.
     The QSwitch(H,S) example has:
     - Left branch: S ; H
     - Right branch: H ; S

     The correct circuit is: X[0] ; CS[0,1] ; X[0] ; H[1] ; CS[0,1]

     Wait, that's for control qubit at 0 and target at 1. But the branches
     operate on the PAYLOAD, which is at wire 1 (wire 0 is the tag).

     Let me think again:
     - Wire 0: tag qubit (control)
     - Wire 1: payload qubit (target for gates in branches)

     Left branch (S;H on wire 1 when tag=0):
     - Anti-controlled-S ; Anti-controlled-H
     - = X[0] ; CS[0,1] ; X[0] ; X[0] ; CH[0,1] ; X[0]
     - = X[0] ; CS[0,1] ; CH[0,1] ; X[0]  (X;X cancels)

     Right branch (H;S on wire 1 when tag=1):
     - Controlled-H ; Controlled-S
     - = CH[0,1] ; CS[0,1]

     Combined for superposition:
     - (Anti-controlled-left) ; (Controlled-right)
     - But this gives BOTH branches running, not one OR the other.

     Actually, the quantum switch is SUPPOSED to have both branches running
     in superposition! That's the whole point. So:

     - Controlled-right runs on the |1⟩ component
     - Anti-controlled-left runs on the |0⟩ component

     So the circuit is:
     - Anti-controlled-(S;H) ; Controlled-(H;S)
     - = X[0] ; CS[0,1] ; CH[0,1] ; X[0] ; CH[0,1] ; CS[0,1]

     Hmm, but this can be simplified. Let me think...

     Actually, the simpler decomposition is:
     - X[0] ; (controlled-difference) ; X[0] ; (common-part) ; (controlled-difference)

     For QSwitch(H,S):
     - Left = S;H = S·H
     - Right = H;S = H·S
     - difference = S (since H·S·S = H, and S·H·H = S)

     Wait no, that's for commuting gates. H and S don't commute.

     The correct approach: Since this is a CONTROLLED swap of order, we use:
     - For |0⟩: apply S then H
     - For |1⟩: apply H then S

     A controlled-SWAP-order can be done with controlled gates:
     1. Controlled-S (only fires on |1⟩, giving H·S → H after we apply S)
     2. Apply H unconditionally
     3. Anti-controlled-S (only fires on |0⟩, giving H·S on |1⟩ and S·H on |0⟩)

     Wait, I'm overcomplicating this. Let me just use the direct decomposition
     that we already know works:

     X[0] ; CS[0,1] ; X[0] ; H[1] ; CS[0,1]

     This is: anti-controlled-S ; H ; controlled-S

     So the pattern is:
     - If left = S;H and right = H;S
     - Decomposition = anti-C[S] ; H ; C[S]
     - = X[0];CS;X[0] ; H ; CS

     This works because:
     - On |0⟩: CS doesn't fire (control=0), H fires, anti-CS fires = S;H ✓
     - On |1⟩: CS doesn't fire in anti mode, H fires, CS fires = H;S ✓

     But how do we COMPUTE this decomposition from the branch bodies?

     The answer: we look for common operations and factor them out.
     - left = S ; H = S·H
     - right = H ; S = H·S
     - Common: H (but in different positions)

     Actually, for the general case, we'd need symbolic manipulation.
     For now, let me just emit the direct controlled version of each branch:

     Full circuit = anti-controlled-left ; controlled-right

     This gives:
     - On |0⟩: left fires, right is blocked = left ✓
     - On |1⟩: left is blocked, right fires = right ✓

     So the correct decomposition is:
     anti-controlled-left + controlled-right (in parallel, not sequential!)

     But wait, we can't do parallel in the term language. They need to be sequential
     because they operate on the SAME wire. Let me reconsider...

     Actually, for the SAME target wire, we can use:
     anti-controlled-left ; controlled-right

     On |0⟩:
     - anti-controlled-left fires (applies left)
     - controlled-right doesn't fire
     - Result: left ✓

     On |1⟩:
     - anti-controlled-left doesn't fire
     - controlled-right fires (applies right)
     - Result: right ✓

     OK so the decomposition is simply:
     anti-controlled-left ; controlled-right

     For QSwitch(H,S):
     - left = S;H
     - right = H;S
     - anti-C[left] = X[0];CS;CH;X[0]
     - C[right] = CH;CS
     - Full = X[0];CS;CH;X[0];CH;CS

     Hmm, that's 6 gates. But the known circuit is 5 gates:
     X[0] ; CS[0,1] ; X[0] ; H[1] ; CS[0,1]

     The 5-gate version uses the fact that CH;X[0];CH = X[0] (up to global phase).
     Actually wait, that's not right either.

     Let me just implement the straightforward version for now:
     anti-controlled-left ; controlled-right
  *)

  (* Lift left branch to anti-controlled (control on |0⟩) *)
  let anti_controlled_left = lift_to_controlled ~anti:true tag_wire left_elaborated in

  (* Lift right branch to controlled (control on |1⟩) *)
  let controlled_right = lift_to_controlled ~anti:false tag_wire right_elaborated in

  (* Compose: anti-controlled-left ; controlled-right *)
  let base_circuit = Core.Seq (anti_controlled_left, controlled_right) in

  (* Handle tag flips from constructor changes.
     The tag flip is SEPARATE from the controlled ops because it affects
     the tag wire itself, not the payload.

     - Both flip → unconditional X[tag] (like eta-expanded twist)
     - Neither flips → no tag change (like identity)
     - Partial flips are NOT unitary and should be rejected

     Note: partial flips (only one branch changes constructor) would map
     both |0⟩ and |1⟩ to the same output, breaking unitarity.
  *)
  match (left_flips, right_flips) with
  | (true, true) ->
      (* Both branches flip: unconditional X[tag] (structural swap) *)
      Core.Seq (base_circuit, Core.gate_x tag_wire)
  | (false, false) ->
      (* Neither flips: no tag change *)
      base_circuit
  | (true, false) | (false, true) ->
      (* Partial flip: not unitary!
         This would mean both |0⟩ and |1⟩ map to the same constructor,
         which is measurement/collapse, not a unitary operation. *)
      failwith "elaborate_quantum_case_2: partial constructor flip is not unitary"

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
