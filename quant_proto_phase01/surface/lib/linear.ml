(** Linear: Sealed staging DSL with GADT-enforced linear contexts.

    Implementation of the sealed interface.
    The GADT representation is private; only the .mli exports are visible.
*)

(* ========== Types ========== *)

type 'a ty = Rep.t

let q = Rep.var 0
let one = Rep.Unit
let ( ** ) a b = Rep.Tensor (a, b)
let ( ++ ) a b = Rep.Plus (a, b)
let ( -@ ) a b = Rep.Tensor (a, b)  (* Int construction: A ⊸ B ≅ A ⊗ B *)

(* ========== Programs (GADT) ========== *)

(* The context 'g is a type-level nested tuple:
   - unit = empty context ∅
   - 'a * 'g = context with x:A followed by Γ

   The GADT constructors enforce that context splitting is valid.
*)

type (_, _) prog =
  (* Variables *)
  | Var : ('a * unit, 'a) prog
  | Weaken : ('g, 'a) prog -> ('b * 'g, 'a) prog

  (* Unit *)
  | Unit : (unit, [`One]) prog
  | LetUnit : ('g1, [`One]) prog * ('g2, 'c) prog -> ('g1 * 'g2, 'c) prog

  (* Tensor *)
  | Pair : ('g1, 'a) prog * ('g2, 'b) prog -> ('g1 * 'g2, [`Tensor of 'a * 'b]) prog
  | LetPair : ('g1, [`Tensor of 'a * 'b]) prog * ('a * ('b * 'g2), 'c) prog
           -> ('g1 * 'g2, 'c) prog

  (* Linear implication *)
  | Lam : 'a ty * ('a * 'g, 'b) prog -> ('g, [`Lolli of 'a * 'b]) prog
  | App : ('g1, [`Lolli of 'a * 'b]) prog * ('g2, 'a) prog -> ('g1 * 'g2, 'b) prog

  (* Sum *)
  | OMap : ('g1, [`Lolli of 'a * 'c]) prog * ('g2, [`Lolli of 'b * 'd]) prog
        -> ('g1 * 'g2, [`Lolli of [`Plus of 'a * 'b] * [`Plus of 'c * 'd]]) prog
  | Case : ('g0, [`Plus of 'a * 'b]) prog * ('a * 'g1, 'c) prog * ('b * 'g2, 'd) prog
        -> ('g0 * ('g1 * 'g2), [`Plus of 'c * 'd]) prog

  (* Structural isomorphisms (closed) *)
  | TwistTensor : 'a ty * 'b ty
               -> (unit, [`Lolli of [`Tensor of 'a * 'b] * [`Tensor of 'b * 'a]]) prog
  | TwistPlus : 'a ty * 'b ty
             -> (unit, [`Lolli of [`Plus of 'a * 'b] * [`Plus of 'b * 'a]]) prog
  | AssocTensorL : 'a ty * 'b ty * 'c ty
                -> (unit, [`Lolli of [`Tensor of [`Tensor of 'a * 'b] * 'c]
                                   * [`Tensor of 'a * [`Tensor of 'b * 'c]]]) prog
  | AssocTensorR : 'a ty * 'b ty * 'c ty
                -> (unit, [`Lolli of [`Tensor of 'a * [`Tensor of 'b * 'c]]
                                   * [`Tensor of [`Tensor of 'a * 'b] * 'c]]) prog
  | DistL : 'a ty * 'b ty * 'c ty
         -> (unit, [`Lolli of [`Tensor of [`Plus of 'a * 'b] * 'c]
                            * [`Plus of [`Tensor of 'a * 'c] * [`Tensor of 'b * 'c]]]) prog
  | DistR : 'a ty * 'b ty * 'c ty
         -> (unit, [`Lolli of [`Tensor of 'a * [`Plus of 'b * 'c]]
                            * [`Plus of [`Tensor of 'a * 'b] * [`Tensor of 'a * 'c]]]) prog

  (* Unitary constants (closed endomorphisms) *)
  | GateH : (unit, [`Lolli of [`Q] * [`Q]]) prog
  | GateS : (unit, [`Lolli of [`Q] * [`Q]]) prog
  | GateX : (unit, [`Lolli of [`Q] * [`Q]]) prog
  | GateY : (unit, [`Lolli of [`Q] * [`Q]]) prog
  | GateZ : (unit, [`Lolli of [`Q] * [`Q]]) prog
  | GateT : (unit, [`Lolli of [`Q] * [`Q]]) prog
  | GateCX : (unit, [`Lolli of [`Tensor of [`Q] * [`Q]] * [`Tensor of [`Q] * [`Q]]]) prog
  | GateRz : float -> (unit, [`Lolli of [`Q] * [`Q]]) prog

  (* Identity *)
  | Id : 'a ty -> (unit, [`Lolli of 'a * 'a]) prog

  (* Composition *)
  | Seq : ('g1, [`Lolli of 'a * 'b]) prog * ('g2, [`Lolli of 'b * 'c]) prog
       -> ('g1 * 'g2, [`Lolli of 'a * 'c]) prog

  (* Closed composition (context stays unit) *)
  | Seq0 : (unit, [`Lolli of 'a * 'b]) prog * (unit, [`Lolli of 'b * 'c]) prog
        -> (unit, [`Lolli of 'a * 'c]) prog
  | Par0 : (unit, [`Lolli of 'a * 'b]) prog * (unit, [`Lolli of 'c * 'd]) prog
        -> (unit, [`Lolli of [`Tensor of 'a * 'c] * [`Tensor of 'b * 'd]]) prog

(* ========== Smart Constructors ========== *)

let var = Var

let weaken p = Weaken p

let unit = Unit

let letunit e1 e2 = LetUnit (e1, e2)

let pair e1 e2 = Pair (e1, e2)

let letpair e1 e2 = LetPair (e1, e2)

let lam ty body = Lam (ty, body)

let app f e = App (f, e)

let omap f g = OMap (f, g)

let case_ scrut left right = Case (scrut, left, right)

let twist_tensor a b = TwistTensor (a, b)
let twist_plus a b = TwistPlus (a, b)
let assoc_tensor_l a b c = AssocTensorL (a, b, c)
let assoc_tensor_r a b c = AssocTensorR (a, b, c)
let dist_l a b c = DistL (a, b, c)
let dist_r a b c = DistR (a, b, c)

let gate_h = GateH
let gate_s = GateS
let gate_x = GateX
let gate_y = GateY
let gate_z = GateZ
let gate_t = GateT
let gate_cx = GateCX
let gate_rz theta = GateRz theta

let id ty = Id ty

let seq f g = Seq (f, g)

let seq0 f g = Seq0 (f, g)

let par0 f g = Par0 (f, g)

(* ========== Meta-level Combinators ========== *)

(* iterate n ty f = f ; f ; ... ; f (n times)
   Returns id when n <= 0. *)
let rec iterate n ty f =
  if n <= 0 then id ty
  else if n = 1 then f
  else seq0 f (iterate (n - 1) ty f)

(* fold ty [f1; f2; ...; fn] = f1 ; f2 ; ... ; fn
   Returns id when list is empty. *)
let fold ty fs =
  match fs with
  | [] -> id ty
  | f :: rest -> List.fold_left seq0 f rest

(* pow2 n ty f = f^(2^n)
   More efficient than iterate (1 lsl n) ty f. *)
let rec pow2 n ty f =
  if n <= 0 then f
  else pow2 (n - 1) ty (seq0 f f)

(* indexed_fold n ty gen = gen(0) ; gen(1) ; ... ; gen(n-1) *)
let indexed_fold n ty gen =
  let stages = List.init n gen in
  fold ty stages

(* ========== Emission to Bridge.term ========== *)

(* Emit any program to Bridge.term.
   Variables are emitted as identity (they represent wire positions). *)
let rec emit_any : type g a. (g, a) prog -> Bridge.term = function
  | Var -> Bridge.TId (Rep.var 0)
  | Weaken p -> emit_any p

  | Unit -> Bridge.TId Rep.Unit
  | LetUnit (e1, e2) -> Bridge.TSeq (emit_any e1, emit_any e2)

  | Pair (e1, e2) -> Bridge.TTenTerm (emit_any e1, emit_any e2)
  | LetPair (e1, body) -> Bridge.TSeq (emit_any e1, emit_any body)

  | Lam (ty, body) -> Bridge.TLam ("x", ty, ty, emit_any body)
  | App (f, arg) -> Bridge.TApply (emit_any f, emit_any arg)

  | OMap (f, g) -> Bridge.TTenTerm (emit_any f, emit_any g)
  | Case (scrut, left, right) ->
      Bridge.TSeq (emit_any scrut, Bridge.TTenTerm (emit_any left, emit_any right))

  | TwistTensor (a, b) -> Bridge.TTwistTen (a, b)
  | TwistPlus (a, b) -> Bridge.TTwistPlus (a, b)
  | AssocTensorL (a, b, c) -> Bridge.TAssocTenL (a, b, c)
  | AssocTensorR (a, b, c) -> Bridge.TAssocTenR (a, b, c)
  | DistL (a, b, c) -> Bridge.TDistL (a, b, c)
  | DistR (a, b, c) -> Bridge.TDistR (a, b, c)

  | GateH -> Bridge.TH 0
  | GateS -> Bridge.TS 0
  | GateX -> Bridge.TX 0
  | GateY -> Bridge.TY 0
  | GateZ -> Bridge.TZ 0
  | GateT -> Bridge.TT 0
  | GateCX -> Bridge.TCX (0, 1)
  | GateRz theta -> Bridge.TRz (theta, 0)

  | Id ty -> Bridge.TId ty
  | Seq (f, g) -> Bridge.TSeq (emit_any f, emit_any g)
  | Seq0 (f, g) -> Bridge.TSeq (emit_any f, emit_any g)
  | Par0 (f, g) -> Bridge.TTenTerm (emit_any f, emit_any g)

(* Emit a closed program. Uses emit_any internally. *)
let emit (p : (unit, 'a) prog) : Bridge.term = emit_any p

let emit_typed p _ty = emit p
