(** Ast: Surface language abstract syntax tree.

    The surface language provides ML-style syntax that elaborates
    to the Phase 0-4C core IR. Key features:

    - λ-abstraction: macro only, elaborates away
    - case expressions: structural rewiring, not runtime branching
    - let bindings: macro expansion
    - datatypes: monoidal (+), not coproducts

    All higher-order structure is eliminated during elaboration.
*)

(** Type variable names *)
type tyvar = string

(** Surface types *)
type ty =
  | TyVar of tyvar                (* Type variable: 'a *)
  | TyQ                           (* Qubit type: Q *)
  | TyTensor of ty * ty           (* Tensor: A ⊗ B *)
  | TyPlus of ty * ty             (* Sum: A + B *)
  | TyUnit                        (* Unit type *)
  | TyNamed of string * ty list   (* Named type: Bool['a, 'b] *)

(** Variable names *)
type var = string

(** Pattern for case branches *)
type pattern =
  | PatCtor of string * var       (* Constructor pattern: F(x) *)
  | PatWild                       (* Wildcard: _ *)

(** Surface terms *)
type term =
  (* Variables and binding *)
  | Var of var                              (* Variable reference *)
  | Lam of var * ty * term                  (* λx:A. e *)
  | App of term * term                      (* Application: f e *)
  | Let of var * term * term                (* let x = e1 in e2 *)

  (* Case expressions *)
  | Case of term * (pattern * term) list    (* case e of ... *)

  (* Constructors *)
  | Ctor of string * term                   (* Constructor: F(e) *)

  (* Composition *)
  | Seq of term * term                      (* Sequential: f ; g *)
  | Ten of term * term                      (* Tensor: f ⊗ g *)

  (* Structural primitives *)
  | Id of ty                                (* Identity *)
  | TwistT of ty * ty                       (* Tensor twist *)
  | TwistP of ty * ty                       (* Plus twist *)
  | AssocTL of ty * ty * ty                 (* Tensor assoc left *)
  | AssocTR of ty * ty * ty                 (* Tensor assoc right *)
  | AssocPL of ty * ty * ty                 (* Plus assoc left *)
  | AssocPR of ty * ty * ty                 (* Plus assoc right *)
  | DistL of ty * ty * ty                   (* Left distributivity: A ⊗ (B + C) → (A ⊗ B) + (A ⊗ C) *)
  | DistR of ty * ty * ty                   (* Right distributivity: (A + B) ⊗ C → (A ⊗ C) + (B ⊗ C) *)

  (* Gates (unitary primitives) *)
  | GateH of int                            (* Hadamard on wire i *)
  | GateS of int                            (* S gate on wire i *)
  | GateCX of int * int                     (* CNOT on wires i, j *)
  | GateX of int                            (* Pauli-X *)
  | GateY of int                            (* Pauli-Y *)
  | GateZ of int                            (* Pauli-Z *)
  | GateT of int                            (* T gate *)
  | GateRz of float * int                   (* Rz(θ) rotation *)

  (* Exponential of involution *)
  | ExpI of float * term                    (* exp_i(θ, J) *)

(** Top-level definitions *)
type def =
  | DefType of string * tyvar list * (string * ty) list
      (* datatype Bool['a,'b] = F of 'a | T of 'b *)
  | DefTerm of var * ty * ty * term
      (* f : A -> B = e *)

(** A complete surface program *)
type program = {
  defs : def list;
  main : term option;
}

(** Pretty-printing *)

let rec ty_to_string = function
  | TyVar v -> "'" ^ v
  | TyQ -> "Q"
  | TyTensor (a, b) -> Printf.sprintf "(%s ⊗ %s)" (ty_to_string a) (ty_to_string b)
  | TyPlus (a, b) -> Printf.sprintf "(%s + %s)" (ty_to_string a) (ty_to_string b)
  | TyUnit -> "I"
  | TyNamed (name, args) ->
    if args = [] then name
    else Printf.sprintf "%s[%s]" name (String.concat ", " (List.map ty_to_string args))

let pattern_to_string = function
  | PatCtor (ctor, var) -> Printf.sprintf "%s(%s)" ctor var
  | PatWild -> "_"

let rec term_to_string = function
  | Var v -> v
  | Lam (x, ty, body) ->
    Printf.sprintf "λ%s:%s. %s" x (ty_to_string ty) (term_to_string body)
  | App (f, e) ->
    Printf.sprintf "(%s %s)" (term_to_string f) (term_to_string e)
  | Let (x, e1, e2) ->
    Printf.sprintf "let %s = %s in %s" x (term_to_string e1) (term_to_string e2)
  | Case (e, branches) ->
    let branch_strs = List.map (fun (p, t) ->
      Printf.sprintf "%s => %s" (pattern_to_string p) (term_to_string t)
    ) branches in
    Printf.sprintf "case %s of %s" (term_to_string e) (String.concat " | " branch_strs)
  | Ctor (name, e) ->
    Printf.sprintf "%s(%s)" name (term_to_string e)
  | Seq (f, g) ->
    Printf.sprintf "%s ; %s" (term_to_string f) (term_to_string g)
  | Ten (f, g) ->
    Printf.sprintf "%s ⊗ %s" (term_to_string f) (term_to_string g)
  | Id ty -> Printf.sprintf "id[%s]" (ty_to_string ty)
  | TwistT (a, b) -> Printf.sprintf "twist⊗[%s, %s]" (ty_to_string a) (ty_to_string b)
  | TwistP (a, b) -> Printf.sprintf "twist+[%s, %s]" (ty_to_string a) (ty_to_string b)
  | AssocTL _ -> "assoc⊗L"
  | AssocTR _ -> "assoc⊗R"
  | AssocPL _ -> "assoc+L"
  | AssocPR _ -> "assoc+R"
  | DistL _ -> "distL"
  | DistR _ -> "distR"
  | GateH i -> Printf.sprintf "H[%d]" i
  | GateS i -> Printf.sprintf "S[%d]" i
  | GateCX (i, j) -> Printf.sprintf "CX[%d,%d]" i j
  | GateX i -> Printf.sprintf "X[%d]" i
  | GateY i -> Printf.sprintf "Y[%d]" i
  | GateZ i -> Printf.sprintf "Z[%d]" i
  | GateT i -> Printf.sprintf "T[%d]" i
  | GateRz (theta, i) -> Printf.sprintf "Rz[%.4f,%d]" theta i
  | ExpI (theta, j) -> Printf.sprintf "exp_i(%.4f, %s)" theta (term_to_string j)

let def_to_string = function
  | DefType (name, tyvars, ctors) ->
    let tyvar_str = if tyvars = [] then "" else
      Printf.sprintf "[%s]" (String.concat ", " (List.map (fun v -> "'" ^ v) tyvars))
    in
    let ctor_strs = List.map (fun (c, ty) ->
      Printf.sprintf "%s of %s" c (ty_to_string ty)
    ) ctors in
    Printf.sprintf "datatype %s%s = %s" name tyvar_str (String.concat " | " ctor_strs)
  | DefTerm (name, dom, cod, body) ->
    Printf.sprintf "%s : %s → %s = %s"
      name (ty_to_string dom) (ty_to_string cod) (term_to_string body)

(** Smart constructors *)

let var x = Var x
let lam x ty body = Lam (x, ty, body)
let app f e = App (f, e)
let let_ x e1 e2 = Let (x, e1, e2)
let case_ e branches = Case (e, branches)
let ctor name e = Ctor (name, e)
let seq f g = Seq (f, g)
let ten f g = Ten (f, g)
let id ty = Id ty
let twist_t a b = TwistT (a, b)
let twist_p a b = TwistP (a, b)

(** Helper to build multi-argument lambdas *)
let lam_n args body =
  List.fold_right (fun (x, ty) acc -> Lam (x, ty, acc)) args body

(** Helper to build sequential composition of multiple terms *)
let seq_list = function
  | [] -> failwith "seq_list: empty list"
  | [t] -> t
  | t :: ts -> List.fold_left (fun acc t -> Seq (acc, t)) t ts
