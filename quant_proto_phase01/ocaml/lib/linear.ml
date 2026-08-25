(** Linear: Sealed staging DSL with GADT-enforced linear contexts.

    Implementation of the sealed interface.
    The GADT representation is private; only the .mli exports are visible.
*)

(* ========== Operation Type Signatures ========== *)

(** Type expressions for operation signatures.
    Includes [Self] for self-referential types in datatype declarations. *)
type op_ty =
  | Self
  | TyRef of Rep.t
  | TyOne
  | TyQ
  | TyTensor of op_ty * op_ty
  | TyPlus of op_ty * op_ty
  | TyLolli of op_ty * op_ty

(** Smart constructors for op_ty *)
let self = Self
let ty_one = TyOne
let ty_q = TyQ
let ( **. ) a b = TyTensor (a, b)
let ( ++. ) a b = TyPlus (a, b)
let lolli a b = TyLolli (a, b)
let of_ty t = TyRef t

(** Resolve op_ty to Rep.t by substituting self_rep for Self *)
let rec resolve_op_ty ~self_rep = function
  | Self -> self_rep
  | TyRef t -> t
  | TyOne -> Rep.Unit
  | TyQ -> Rep.var 0
  | TyTensor (a, b) -> Rep.Tensor (resolve_op_ty ~self_rep a, resolve_op_ty ~self_rep b)
  | TyPlus (a, b) -> Rep.Plus (resolve_op_ty ~self_rep a, resolve_op_ty ~self_rep b)
  | TyLolli (a, b) -> Rep.Lolli (resolve_op_ty ~self_rep a, resolve_op_ty ~self_rep b)

(* ========== Types ========== *)

type 'a ty = Rep.t

let q = Rep.var 0
let one = Rep.Unit
let ( ** ) a b = Rep.Tensor (a, b)
let ( ++ ) a b = Rep.Plus (a, b)
let ( -@ ) a b = Rep.Lolli (a, b)  (* Linear implication A ⊸ B *)

let ty_to_rep (ty : 'a ty) : Rep.t = ty

(* ========== First-order predicate (soundness fix) ==========

   A type is first-order iff it contains no Lolli (⊸) anywhere.

   Used to guard sum-payload sites: ⊕-Map targets, case shared result
   types, and datatype control payloads must be first-order.

   Higher-order values (Lolli-typed things) are perfectly fine as
   Lolli hom-arguments and results — they just cannot appear as the
   payload of a sum. See docs/LIMITATIONS.md §4 and the soundness
   remark in the paper.
*)
let rec first_order (t : Rep.t) : bool =
  match t with
  | Rep.Var _ -> true
  | Rep.Unit -> true
  | Rep.Tensor (a, b) -> first_order a && first_order b
  | Rep.Plus   (a, b) -> first_order a && first_order b
  | Rep.Lolli  (_, _) -> false

let assert_first_order ~site (t : Rep.t) : unit =
  if not (first_order t) then
    invalid_arg
      (Printf.sprintf
         "%s: sum payloads must be first-order (contain no Lolli).\n\
          Function values may be consumed inside a branch, but not returned on a summand.\n\
          Offending type: %s"
         site (Rep.to_string t))

(** Generate I^{⊕k} = I ⊕ (I ⊕ (... ⊕ I)) with k copies of I.
    - i_sum 1 = I
    - i_sum 2 = I ⊕ I
    - i_sum k = I ⊕ I^{⊕(k-1)} *)
let rec i_sum k =
  if k <= 1 then Rep.Unit
  else Rep.Plus (Rep.Unit, i_sum (k - 1))

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

  (* Tensor *)
  | Pair : ('g1, 'a) prog * ('g2, 'b) prog -> ('g1 * 'g2, [`Tensor of 'a * 'b]) prog
  | LetPair : ('g1, [`Tensor of 'a * 'b]) prog * ('a * ('b * 'g2), 'c) prog
           -> ('g1 * 'g2, 'c) prog

  (* Linear implication - stores both domain AND codomain types for emission *)
  | Lam : 'a ty * 'b ty * ('a * 'g, 'b) prog -> ('g, [`Lolli of 'a * 'b]) prog
  | App : ('g1, [`Lolli of 'a * 'b]) prog * ('g2, 'a) prog -> ('g1 * 'g2, 'b) prog

  (* Sum - stores type witnesses for correct PlusMap emission *)
  | OMap : 'a ty * 'b ty * ('g1, [`Lolli of 'a * 'c]) prog * ('g2, [`Lolli of 'b * 'd]) prog
        -> ('g1 * 'g2, [`Lolli of [`Plus of 'a * 'b] * [`Plus of 'c * 'd]]) prog
  (* Case with type witnesses for emission *)
  | Case : Rep.t * Rep.t * ('g0, [`Plus of 'a * 'b]) prog * ('a * 'g1, 'c) prog * ('b * 'g2, 'd) prog
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
  | AssocPlusL : 'a ty * 'b ty * 'c ty
             -> (unit, [`Lolli of [`Plus of [`Plus of 'a * 'b] * 'c]
                                * [`Plus of 'a * [`Plus of 'b * 'c]]]) prog
  | AssocPlusR : 'a ty * 'b ty * 'c ty
             -> (unit, [`Lolli of [`Plus of 'a * [`Plus of 'b * 'c]]
                                * [`Plus of [`Plus of 'a * 'b] * 'c]]) prog
  | DistL : 'a ty * 'b ty * 'c ty
         -> (unit, [`Lolli of [`Tensor of [`Plus of 'a * 'b] * 'c]
                            * [`Plus of [`Tensor of 'a * 'c] * [`Tensor of 'b * 'c]]]) prog
  | DistR : 'a ty * 'b ty * 'c ty
         -> (unit, [`Lolli of [`Tensor of 'a * [`Plus of 'b * 'c]]
                            * [`Plus of [`Tensor of 'a * 'b] * [`Tensor of 'a * 'c]]]) prog
  | UndistL : 'a ty * 'b ty * 'c ty
           -> (unit, [`Lolli of [`Plus of [`Tensor of 'a * 'c] * [`Tensor of 'b * 'c]]
                              * [`Tensor of [`Plus of 'a * 'b] * 'c]]) prog
  | UndistR : 'a ty * 'b ty * 'c ty
           -> (unit, [`Lolli of [`Plus of [`Tensor of 'a * 'b] * [`Tensor of 'a * 'c]]
                              * [`Tensor of 'a * [`Plus of 'b * 'c]]]) prog

  (* n-ary distributivity: Z_n ⊗ A ⊸ ⊕^n (b ⊗ A) — wire-level identity.
     Both sides have the same flat n-ary encoding (log_n tag + width(A) payload),
     so this is identity at the wire level. The type system tracks the
     distinction; the compiler emits zero gates. *)
  | NDist : 'a ty array * 'b ty
         -> (unit, [`Lolli of 'in_ty * 'out_ty]) prog
  | NFactor : 'a ty array * 'b ty
           -> (unit, [`Lolli of 'in_ty * 'out_ty]) prog

  (* Wire-level basis-state permutation on a fixed-width type.
     Maps |i⟩ → |perm[i]⟩. Compiled via pytket ToffoliBox. *)
  | TagPerm : int array * 'a ty
            -> (unit, [`Lolli of 'a * 'a]) prog

  (* Unitary constants (closed endomorphisms) *)
  | GateH : (unit, [`Lolli of [`Q] * [`Q]]) prog
  | GateS : (unit, [`Lolli of [`Q] * [`Q]]) prog
  | GateX : (unit, [`Lolli of [`Q] * [`Q]]) prog
  | GateY : (unit, [`Lolli of [`Q] * [`Q]]) prog
  | GateZ : (unit, [`Lolli of [`Q] * [`Q]]) prog
  | GateT : (unit, [`Lolli of [`Q] * [`Q]]) prog
  | GateCX : (unit, [`Lolli of [`Tensor of [`Q] * [`Q]] * [`Tensor of [`Q] * [`Q]]]) prog
  | GateRz : float -> (unit, [`Lolli of [`Q] * [`Q]]) prog

  (* Scalar phase: multiply by unit complex number *)
  | Phase : float * 'a ty -> (unit, [`Lolli of 'a * 'a]) prog
      (* Stores the angle θ where z = e^{iθ}; ty is the type being scaled *)

  (* Exponential of involution: exp(iθ·P) where P² = I *)
  | ExpI : float * (unit, [`Lolli of 'a * 'a]) prog
        -> (unit, [`Lolli of 'a * 'a]) prog

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

  (* Primitive/opaque operations (from datatype declarations) *)
  | Prim : string * Rep.t * Rep.t -> (unit, [`Lolli of 'a * 'b]) prog

  (* Closed omap for datatype control - carries type witnesses for emission *)
  | OMap0 : Rep.t * Rep.t * (unit, [`Lolli of 'a * 'c]) prog * (unit, [`Lolli of 'b * 'd]) prog
         -> (unit, [`Lolli of [`Plus of 'a * 'b] * [`Plus of 'c * 'd]]) prog

  (* N-ary omap for n-ary sums *)
  | NMap : Rep.t array * (unit, [`Lolli of 'a * 'b]) prog array
        -> (unit, [`Lolli of 'c * 'd]) prog

  (* Phase-weighted omap: applies phase z to left branch *)
  | PhasedOMap0 : float * Rep.t * Rep.t * (unit, [`Lolli of 'a * 'c]) prog * (unit, [`Lolli of 'b * 'd]) prog
              -> (unit, [`Lolli of [`Plus of 'a * 'b] * [`Plus of 'c * 'd]]) prog
      (* Stores angle θ where z = e^{iθ}; ty_left and ty_right are type witnesses *)

  (* Phase-weighted n-ary control: applies phase zᵢ to branch i *)
  | PhasedCtrl : string * int * float array * Rep.t * Rep.t
              -> (unit, [`Lolli of [`Tensor of 'b * 'a] * [`Tensor of 'b * 'a]]) prog
      (* name, arity, phases (angles), dt_rep, a_ty *)

(* ========== Smart Constructors ========== *)

let var = Var

let weaken p = Weaken p

let pair e1 e2 = Pair (e1, e2)

let letpair e1 e2 = LetPair (e1, e2)

let lam dom cod body = Lam (dom, cod, body)

let app f e = App (f, e)

let omap ty_left ty_right f g = OMap (ty_left, ty_right, f, g)

let case_ ty_left ty_right scrut left right = Case (ty_left, ty_right, scrut, left, right)

let twist_tensor a b = TwistTensor (a, b)
let twist_plus a b = TwistPlus (a, b)
let assoc_tensor_l a b c = AssocTensorL (a, b, c)
let assoc_tensor_r a b c = AssocTensorR (a, b, c)
let assoc_plus_l a b c = AssocPlusL (a, b, c)
let assoc_plus_r a b c = AssocPlusR (a, b, c)
let dist_l a b c = DistL (a, b, c)
let dist_r a b c = DistR (a, b, c)
let undist_l a b c = UndistL (a, b, c)
let undist_r a b c = UndistR (a, b, c)

(** n-ary distributivity: Z_n ⊗ A ⊸ ⊕^n (b ⊗ A). Wire-level identity. *)
let n_dist summand_tys b_ty = NDist (summand_tys, b_ty)

(** n-ary inverse distributivity: ⊕^n (b ⊗ A) ⊸ Z_n ⊗ A. Wire-level identity. *)
let n_factor summand_tys b_ty = NFactor (summand_tys, b_ty)

(** Wire-level basis-state permutation: maps |i⟩ → |perm.(i)⟩.
    Compiled via pytket ToffoliBox. *)
let tag_perm perm ty = TagPerm (perm, ty)

let gate_h = GateH
let gate_s = GateS
let gate_x = GateX
let gate_y = GateY
let gate_z = GateZ
let gate_t = GateT
let gate_cx = GateCX
let gate_rz theta = GateRz theta

(* Scalar phase: multiply by unit complex number z = e^{iθ}
   Validates |z| = 1 within tolerance *)
let phase z ty =
  let tolerance = 1e-10 in
  let modulus = Complex.norm z in
  if abs_float (modulus -. 1.0) > tolerance then
    invalid_arg (Printf.sprintf "phase: complex number must have modulus 1, got |z| = %f" modulus)
  else
    let theta = Complex.arg z in
    Phase (theta, ty)

let exp_i theta body = ExpI (theta, body)

let id ty = Id ty

let seq f g = Seq (f, g)

let seq0 f g = Seq0 (f, g)

let par0 f g = Par0 (f, g)

let omap0 ty_left ty_right f g = OMap0 (ty_left, ty_right, f, g)

let omapn summand_types branches =
  if Array.length summand_types < 2 then
    invalid_arg "omapn: need at least 2 summand types";
  if Array.length summand_types <> Array.length branches then
    invalid_arg (Printf.sprintf "omapn: %d summand types but %d branches"
      (Array.length summand_types) (Array.length branches));
  NMap (summand_types, branches)

(* Phase-weighted omap: applies phase z to left branch
   Validates |z| = 1 within tolerance *)
let phased_omap0 z ty_left ty_right f g =
  let tolerance = 1e-10 in
  let modulus = Complex.norm z in
  if abs_float (modulus -. 1.0) > tolerance then
    invalid_arg (Printf.sprintf "phased_omap0: complex number must have modulus 1, got |z| = %f" modulus)
  else
    let theta = Complex.arg z in
    PhasedOMap0 (theta, ty_left, ty_right, f, g)

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

(* ========== Case Sugar ========== *)

(* Branch helper: build G⊗A → A⊗C from body: G → C.
   Useful when the branch ignores the tag arm and just processes context.
   Desugars to: twist(G,A) ; (id_A ⊗ body) *)
let make_branch (ty_g : 'g ty) (ty_a : 'a ty) (body : (unit, [`Lolli of 'g * 'c]) prog)
    : (unit, [`Lolli of [`Tensor of 'g * 'a] * [`Tensor of 'a * 'c]]) prog =
  seq0 (twist_tensor ty_g ty_a) (par0 (id ty_a) body)

(* Homogeneous case without context:
   (A⊕B) → (A⊕B) ⊗ C
   Branches f: A → A⊗C, g: B → B⊗C
   Desugars to: omap0(f, g) ; undist_l *)
let case_hom0 (ty_a : 'a ty) (ty_b : 'b ty) (ty_c : 'c ty)
    (f : (unit, [`Lolli of 'a * [`Tensor of 'a * 'c]]) prog)
    (g : (unit, [`Lolli of 'b * [`Tensor of 'b * 'c]]) prog)
    : (unit, [`Lolli of [`Plus of 'a * 'b] * [`Tensor of [`Plus of 'a * 'b] * 'c]]) prog =
  assert_first_order ~site:"case_hom0" ty_c;
  seq0 (omap0 ty_a ty_b f g) (undist_l ty_a ty_b ty_c)

(* Homogeneous case with shared context:
   G ⊗ (A⊕B) → (A⊕B) ⊗ C
   Branches f: G⊗A → A⊗C, g: G⊗B → B⊗C
   Desugars to: dist_r ; omap0(f, g) ; undist_l *)
let case_hom (ty_a : 'a ty) (ty_b : 'b ty) (ty_g : 'g ty) (ty_c : 'c ty)
    (f : (unit, [`Lolli of [`Tensor of 'g * 'a] * [`Tensor of 'a * 'c]]) prog)
    (g : (unit, [`Lolli of [`Tensor of 'g * 'b] * [`Tensor of 'b * 'c]]) prog)
    : (unit, [`Lolli of [`Tensor of 'g * [`Plus of 'a * 'b]]
                        * [`Tensor of [`Plus of 'a * 'b] * 'c]]) prog =
  assert_first_order ~site:"case_hom" ty_c;
  seq0 (seq0 (dist_r ty_g ty_a ty_b) (omap0 (ty_g ** ty_a) (ty_g ** ty_b) f g))
       (undist_l ty_a ty_b ty_c)

(* Heterogeneous case without context:
   (A⊕B) → (A⊗C) ⊕ (B⊗D)
   Branches f: A → A⊗C, g: B → B⊗D
   Alias for omap0 — provided for naming consistency. *)
let case_het0 (ty_a : 'a ty) (ty_b : 'b ty)
    (f : (unit, [`Lolli of 'a * [`Tensor of 'a * 'c]]) prog)
    (g : (unit, [`Lolli of 'b * [`Tensor of 'b * 'd]]) prog)
    : (unit, [`Lolli of [`Plus of 'a * 'b]
                        * [`Plus of [`Tensor of 'a * 'c] * [`Tensor of 'b * 'd]]]) prog =
  omap0 ty_a ty_b f g

(* Heterogeneous case with shared context:
   G ⊗ (A⊕B) → (A⊗C) ⊕ (B⊗D)
   Branches f: G⊗A → A⊗C, g: G⊗B → B⊗D
   Desugars to: dist_r ; omap0(f, g) *)
let case_het (ty_a : 'a ty) (ty_b : 'b ty) (ty_g : 'g ty)
    (f : (unit, [`Lolli of [`Tensor of 'g * 'a] * [`Tensor of 'a * 'c]]) prog)
    (g : (unit, [`Lolli of [`Tensor of 'g * 'b] * [`Tensor of 'b * 'd]]) prog)
    : (unit, [`Lolli of [`Tensor of 'g * [`Plus of 'a * 'b]]
                        * [`Plus of [`Tensor of 'a * 'c] * [`Tensor of 'b * 'd]]]) prog =
  seq0 (dist_r ty_g ty_a ty_b) (omap0 (ty_g ** ty_a) (ty_g ** ty_b) f g)

(* ========== Emission to Bridge.term ========== *)

(* Emit any program to Bridge.term.
   Variables are emitted as identity (they represent wire positions). *)
let rec emit_any : type g a. (g, a) prog -> Bridge.term = function
  | Var -> Bridge.TId (Rep.var 0)
  | Weaken p -> emit_any p

  | Pair (e1, e2) -> Bridge.TTenTerm (emit_any e1, emit_any e2)
  | LetPair (e1, body) -> Bridge.TSeq (emit_any e1, emit_any body)

  | Lam (dom, cod, body) -> Bridge.TLam ("x", dom, cod, emit_any body)
  | App (f, arg) -> Bridge.TApply (emit_any f, emit_any arg)

  | OMap (ty_left, ty_right, f, g) -> Bridge.TPlusMap (ty_left, ty_right, emit_any f, emit_any g)
  | Case (ty_left, ty_right, scrut, left, right) ->
      Bridge.TCase (ty_left, ty_right, emit_any scrut, emit_any left, emit_any right)

  | TwistTensor (a, b) -> Bridge.TTwistTen (a, b)
  | TwistPlus (a, b) -> Bridge.TTwistPlus (a, b)
  | AssocTensorL (a, b, c) -> Bridge.TAssocTenL (a, b, c)
  | AssocTensorR (a, b, c) -> Bridge.TAssocTenR (a, b, c)
  | AssocPlusL (a, b, c) -> Bridge.TAssocPlusL (a, b, c)
  | AssocPlusR (a, b, c) -> Bridge.TAssocPlusR (a, b, c)
  | DistL (a, b, c) -> Bridge.TDistL (a, b, c)
  | DistR (a, b, c) -> Bridge.TDistR (a, b, c)
  | UndistL (a, b, c) -> Bridge.TUndistL (a, b, c)
  | UndistR (a, b, c) -> Bridge.TUndistR (a, b, c)
  | NDist (summand_tys, b_ty) ->
      (* dom = (Plus^n summand_tys) ⊗ b   ;   cod = Plus^n (summand_i ⊗ b) *)
      let summand_reps = Array.map ty_to_rep summand_tys in
      let b_rep = ty_to_rep b_ty in
      let rec build_plus arr lo hi =
        if hi - lo = 1 then arr.(lo)
        else
          let mid = lo + 1 in
          Rep.Plus (arr.(lo), build_plus arr mid hi)
      in
      let n = Array.length summand_reps in
      let sum_rep = build_plus summand_reps 0 n in
      let tensored = Array.map (fun s -> Rep.Tensor (s, b_rep)) summand_reps in
      let sum_tensored_rep = build_plus tensored 0 n in
      Bridge.TWireIdentity (Rep.Tensor (sum_rep, b_rep), sum_tensored_rep)
  | NFactor (summand_tys, b_ty) ->
      let summand_reps = Array.map ty_to_rep summand_tys in
      let b_rep = ty_to_rep b_ty in
      let rec build_plus arr lo hi =
        if hi - lo = 1 then arr.(lo)
        else
          let mid = lo + 1 in
          Rep.Plus (arr.(lo), build_plus arr mid hi)
      in
      let n = Array.length summand_reps in
      let sum_rep = build_plus summand_reps 0 n in
      let tensored = Array.map (fun s -> Rep.Tensor (s, b_rep)) summand_reps in
      let sum_tensored_rep = build_plus tensored 0 n in
      Bridge.TWireIdentity (sum_tensored_rep, Rep.Tensor (sum_rep, b_rep))
  | TagPerm (perm, ty) ->
      Bridge.TTagPerm (Array.to_list perm, ty_to_rep ty)

  | GateH -> Bridge.TH 0
  | GateS -> Bridge.TS 0
  | GateX -> Bridge.TX 0
  | GateY -> Bridge.TY 0
  | GateZ -> Bridge.TZ 0
  | GateT -> Bridge.TT 0
  | GateCX -> Bridge.TCX (0, 1)
  | GateRz theta -> Bridge.TRz (theta, 0)

  (* Scalar phase: for Unit type (0 qubits), emit Id (phase tracked separately).
     For Q type, emit Rz which approximates global phase up to basis-dependent factor.
     Note: True global phase support in controlled contexts requires PlusMap-level handling. *)
  | Phase (theta, ty) ->
      let w = Rep.wire_count ty in
      if w = 0 then
        (* Unit type: no qubits, emit identity. Phase is lost in isolation
           but becomes controlled-phase in PlusMap context via tag qubits. *)
        Bridge.TId ty
      else if w = 1 then
        (* Single qubit: emit Rz(theta) as approximation *)
        Bridge.TRz (theta, 0)
      else
        (* Multi-qubit: emit Id (phase is global, unobservable in isolation) *)
        Bridge.TId ty

  | ExpI (theta, body) -> Bridge.TExpInvolution (theta, emit_any body)
  | Id ty -> Bridge.TId ty
  | Seq (f, g) -> Bridge.TSeq (emit_any f, emit_any g)
  | Seq0 (f, g) -> Bridge.TSeq (emit_any f, emit_any g)
  | Par0 (f, g) -> Bridge.TTenTerm (emit_any f, emit_any g)

  | Prim (name, _dom, _cod) -> Bridge.TGate (name, [0], [])
  | OMap0 (ty_left, ty_right, f, g) ->
      Bridge.TPlusMap (ty_left, ty_right, emit_any f, emit_any g)
  | NMap (summand_types, branches) ->
      Bridge.TNPlusMap (summand_types, Array.map emit_any branches)
  | PhasedOMap0 (theta, ty_left, ty_right, f, g) ->
      Bridge.TPhasedPlusMap (theta, ty_left, ty_right, emit_any f, emit_any g)
  | PhasedCtrl (name, arity, phases, dt_rep, a_ty) ->
      Bridge.TPhasedControl (name, arity, Array.to_list phases, dt_rep, a_ty)

(* Emit a closed program. Uses emit_any internally. *)
let emit (p : (unit, 'a) prog) : Bridge.term = emit_any p

let emit_typed p _ty = emit p

(* ========== Context Split Witnesses ========== *)

(** Context split witness: split(g1, g2, g) proves g partitions into g1 and g2.
    Each element of g is assigned to either g1 (SLeft) or g2 (SRight). *)
type (_, _, _) split =
  | SNil   : (unit, unit, unit) split
  | SLeft  : ('g1, 'g2, 'g) split -> ('a * 'g1, 'g2, 'a * 'g) split
  | SRight : ('g1, 'g2, 'g) split -> ('g1, 'a * 'g2, 'a * 'g) split

(* ========== Open Terms (Full Source Language) ========== *)

(** Open terms: GADT tracking both context ('g) and output type ('a).
    Supports the full source language including nested LetPair
    and variable references that the context-tracking [prog] cannot express.

    Context 'g is a type-level nested tuple (same as in [prog]):
    - [unit] = empty context
    - ['a * 'g] = context with variable of type A followed by rest

    Binary constructors carry split witnesses to partition the context.
    Linearity is enforced at OCaml compile time via the context type parameter.
*)
type (_, _) oterm =
  (* Variables *)
  | OHere  : string * 'a ty -> ('a * unit, 'a) oterm
  | OShift : 'b ty * ('g, 'a) oterm -> ('b * 'g, 'a) oterm

  (* Tensor *)
  | OPair : ('g1, 'a) oterm * ('g2, 'b) oterm * ('g1, 'g2, 'g) split
          -> ('g, [`Tensor of 'a * 'b]) oterm
  | OLetPair : string * string * 'a ty * 'b ty
             * ('g1, [`Tensor of 'a * 'b]) oterm
             * ('a * ('b * 'g2), 'c) oterm
             * ('g1, 'g2, 'g) split
            -> ('g, 'c) oterm

  (* Linear implication *)
  | OLam : string * 'a ty * 'b ty
         * ('a * 'g, 'b) oterm
        -> ('g, [`Lolli of 'a * 'b]) oterm
  | OApp : ('g1, [`Lolli of 'a * 'b]) oterm * ('g2, 'a) oterm
         * ('g1, 'g2, 'g) split
        -> ('g, 'b) oterm

  (* ⊕-Map: branches are bare morphism terms *)
  | OPlusMap : 'a ty * 'b ty
             * ('g1, 'c) oterm * ('g2, 'd) oterm
             * ('g1, 'g2, 'g) split
            -> ('g, [`Lolli of [`Plus of 'a * 'b] * [`Plus of 'c * 'd]]) oterm

  (* n-ary ⊕-Map: all branches share context 'g and produce homogeneous output 'c.
     This is the general primitive; binary OPlusMap is the n=2 special case.
     Linearity for n>2 cases is the user's responsibility (each var in 'g must be
     used in exactly one branch, mirroring the binary split discipline).
     The result Lolli's sum-types are existential ('sum_in, 'sum_out) — pragmatic
     loose typing mirroring the prog-level NMap. *)
  | ONPlusMap : 'a ty array * 'c ty * ('g, 'c) oterm array
             -> ('g, [`Lolli of 'sum_in * 'sum_out]) oterm

  (* Sequential composition of morphisms *)
  | OSeq : ('g1, [`Lolli of 'a * 'b]) oterm
         * ('g2, [`Lolli of 'b * 'c]) oterm
         * ('g1, 'g2, 'g) split
        -> ('g, [`Lolli of 'a * 'c]) oterm

  (* Closed terms *)
  | OId    : 'a ty -> (unit, 'a) oterm
  | OEmbed : (unit, 'a) prog -> (unit, 'a) oterm

(** Smart constructors for open terms — general (explicit split) *)
let ovar name ty = OHere (name, ty)
let oshift ty inner = OShift (ty, inner)
let opair e1 e2 sp = OPair (e1, e2, sp)
let oletpair x y ty_x ty_y pair body sp = OLetPair (x, y, ty_x, ty_y, pair, body, sp)
let olam name dom cod body = OLam (name, dom, cod, body)
let oapp f arg sp = OApp (f, arg, sp)
let oplusmap ty_l ty_r f g sp = OPlusMap (ty_l, ty_r, f, g, sp)
let o_n_plusmap summand_types output_ty branches =
  ONPlusMap (summand_types, output_ty, branches)
let oid ty = OId ty
let oembed p = OEmbed p
let oseq f g sp = OSeq (f, g, sp)

(** Closed convenience constructors (both subterms closed, split = SNil) *)
let opair0 e1 e2 = OPair (e1, e2, SNil)
let oapp0 f arg = OApp (f, arg, SNil)
let oplusmap0 ty_l ty_r f g = OPlusMap (ty_l, ty_r, f, g, SNil)
let oseq0 f g = OSeq (f, g, SNil)
let oletpair0 x y ty_x ty_y pair body = OLetPair (x, y, ty_x, ty_y, pair, body, SNil)

(* ========== Oterm Case Sugar ========== *)

(** Homogeneous case without context (oterm level).
    (A⊕B) → (A⊕B) ⊗ C
    Branches f: A→A⊗C, g: B→B⊗C (closed oterms).
    Desugars to: oplusmap0(f,g) ; undist_l *)
let ocase_hom0 ty_a ty_b ty_c left right =
  assert_first_order ~site:"ocase_hom0" ty_c;
  oseq0 (oplusmap0 ty_a ty_b left right)
        (oembed (undist_l ty_a ty_b ty_c))

(** Homogeneous case with shared context G (oterm level).
    G⊗(A+B) → (A+B)⊗C
    Branches f: G⊗A→A⊗C, g: G⊗B→B⊗C (closed oterms).
    Desugars to: dist_r(G,A,B) ; oplusmap0(f,g) ; undist_l(A,B,C) *)
let ocase_hom ty_a ty_b ty_g ty_c left right =
  assert_first_order ~site:"ocase_hom" ty_c;
  oseq0 (oembed (dist_r ty_g ty_a ty_b))
        (oseq0 (oplusmap0 (ty_g ** ty_a) (ty_g ** ty_b) left right)
               (oembed (undist_l ty_a ty_b ty_c)))

(** Heterogeneous case without context (oterm level).
    (A⊕B) → (A⊗C) ⊕ (B⊗D)
    Alias for oplusmap0 — provided for naming consistency. *)
let ocase_het0 = oplusmap0

(** Heterogeneous case with context G (oterm level).
    G⊗(A+B) → (A⊗C)+(B⊗D)
    Desugars to: dist_r(G,A,B) ; oplusmap0(f,g) *)
let ocase_het ty_a ty_b ty_g left right =
  oseq0 (oembed (dist_r ty_g ty_a ty_b))
        (oplusmap0 (ty_g ** ty_a) (ty_g ** ty_b) left right)

(** Embed prog-level make_branch into oterm.
    Only works when body is a closed prog. *)
let omake_branch ty_g ty_a body = oembed (make_branch ty_g ty_a body)

(** Compute the Rep.t representation of an oterm's context.
    For a term of type [('g, 'a) oterm], returns the Rep.t of 'g. *)
let rec context_rep : type g a. (g, a) oterm -> Rep.t = function
  | OHere (_, ty) -> Rep.Tensor (ty, Rep.Unit)
  | OShift (b_ty, inner) -> Rep.Tensor (b_ty, context_rep inner)
  | OPair (l, r, sp) -> split_rep (context_rep l) (context_rep r) sp
  | OLetPair (_, _, _, _, pair, body, sp) ->
      split_rep (context_rep pair) (strip_pair_bound (context_rep body)) sp
  | OLam (_, _, _, body) -> strip_front (context_rep body)
  | OApp (f, arg, sp) -> split_rep (context_rep f) (context_rep arg) sp
  | OPlusMap (_, _, f, g, sp) -> split_rep (context_rep f) (context_rep g) sp
  | ONPlusMap (_, _, branches) ->
      if Array.length branches = 0 then Rep.Unit
      else context_rep branches.(0)
  | OSeq (f, g, sp) -> split_rep (context_rep f) (context_rep g) sp
  | OId _ -> Rep.Unit
  | OEmbed _ -> Rep.Unit

(** Reconstruct context rep from subcontext reps and a split witness *)
and split_rep : type g1 g2 g. Rep.t -> Rep.t -> (g1, g2, g) split -> Rep.t =
  fun r1 r2 -> function
    | SNil -> Rep.Unit
    | SLeft s ->
        let (a, rest_r1) = match r1 with
          | Rep.Tensor (a, rest) -> (a, rest)
          | _ -> failwith "split_rep: expected Tensor for SLeft"
        in
        Rep.Tensor (a, split_rep rest_r1 r2 s)
    | SRight s ->
        let (a, rest_r2) = match r2 with
          | Rep.Tensor (a, rest) -> (a, rest)
          | _ -> failwith "split_rep: expected Tensor for SRight"
        in
        Rep.Tensor (a, split_rep r1 rest_r2 s)

(** Strip the first tensor component (lambda-bound variable) from a context rep *)
and strip_front = function
  | Rep.Tensor (_, rest) -> rest
  | Rep.Unit -> Rep.Unit
  | _ -> Rep.Unit

(** Strip the first two tensor components (LetPair-bound variables) from a context rep *)
and strip_pair_bound = function
  | Rep.Tensor (_, Rep.Tensor (_, rest)) -> rest
  | _ -> Rep.Unit

(** Emit an open term to Bridge.term *)
let rec emit_oterm : type g a. (g, a) oterm -> Bridge.term = function
  | OHere (name, ty) -> Bridge.TVar (name, ty)
  | OShift (_, inner) -> emit_oterm inner
  | OPair (e1, e2, _) -> Bridge.TPair (emit_oterm e1, emit_oterm e2)
  | OLetPair (x, y, ty_x, ty_y, pair, body, _) ->
      Bridge.TLetPair (x, y, ty_x, ty_y, emit_oterm pair, emit_oterm body)
  | OLam (name, dom, cod, body) ->
      Bridge.TLam (name, dom, cod, emit_oterm body)
  | OApp (f, arg, _) ->
      (* Function variables and lambdas use boundary splicing (TApply).
         Structural morphisms (embed, plusmap, seq, id) use composition (TSeq). *)
      let rec is_apply_target : type g a. (g, a) oterm -> bool = function
        | OHere _ -> true
        | OShift (_, inner) -> is_apply_target inner
        | OLam _ -> true
        | OApp _ -> true
        | _ -> false
      in
      if is_apply_target f then
        Bridge.TApply (emit_oterm f, emit_oterm arg)
      else
        Bridge.TSeq (emit_oterm arg, emit_oterm f)
  | OPlusMap (ty_l, ty_r, f, g, _) ->
      Bridge.TPlusMap (ty_l, ty_r, emit_oterm f, emit_oterm g)
  | ONPlusMap (summand_types, _output_ty, branches) ->
      let summand_reps = Array.map ty_to_rep summand_types in
      let branch_terms = Array.map emit_oterm branches in
      Bridge.TNPlusMap (summand_reps, branch_terms)
  | OSeq (f, g, _) -> Bridge.TSeq (emit_oterm f, emit_oterm g)
  | OId ty -> Bridge.TId ty
  | OEmbed p -> emit p

(* ========== Datatype Declarations ========== *)

(** Operation info: name and resolved type *)
type op_info = {
  op_name : string;
  op_dom : Rep.t;
  op_cod : Rep.t;
}

(** Datatype descriptor *)
type datatype_desc = {
  name : string;
  arity : int;
  labels : string list;
  rep : Rep.t;
  ops : op_info list;
}

(** Create a closed program for a primitive operation *)
let prim_prog (info : op_info) : (unit, [`Lolli of 'a * 'b]) prog =
  Prim (info.op_name, info.op_dom, info.op_cod)

(** Construct a datatype descriptor.

    Usage:
    {[
      let bool = datatype
        ~name:"Bool"
        ~arity:2
        ~labels:["false"; "true"]
        ~ops:[("H", lolli self self); ("X", lolli self self)]
    ]}
*)
let datatype ~name ~arity ~labels ~ops =
  (* Validate *)
  if arity < 1 then
    failwith (Printf.sprintf "Datatype %s: arity must be >= 1" name);
  if List.length labels <> arity then
    failwith (Printf.sprintf "Datatype %s: expected %d labels, got %d"
                name arity (List.length labels));

  (* Generate I^{⊕k} representation *)
  let self_rep = i_sum arity in

  (* Belt-and-suspenders: verify arity matches rep structure *)
  let expected_arity = Rep.count_summands self_rep in
  if arity <> expected_arity then
    failwith (Printf.sprintf
      "Datatype %s: declared arity %d but rep has %d summands"
      name arity expected_arity);

  (* Resolve operation types *)
  let resolved_ops = List.map (fun (op_name, op_sig) ->
    match op_sig with
    | TyLolli (dom, cod) ->
        { op_name;
          op_dom = resolve_op_ty ~self_rep dom;
          op_cod = resolve_op_ty ~self_rep cod }
    | _ ->
        failwith (Printf.sprintf "Datatype %s: operation %s must have type A ⊸ B"
                    name op_name)
  ) ops in

  { name; arity; labels; rep = self_rep; ops = resolved_ops }

(** Get the type witness for a datatype's representation *)
let rep_ty (dt : datatype_desc) : 'a ty = dt.rep

(** Look up an operation by name and return it as a closed program *)
let op (dt : datatype_desc) (name : string) : (unit, [`Lolli of 'a * 'b]) prog =
  match List.find_opt (fun o -> o.op_name = name) dt.ops with
  | Some info -> prim_prog info
  | None ->
      failwith (Printf.sprintf "Datatype %s: unknown operation %s" dt.name name)

(** Generate the control combinator for a datatype.

    control : (D ⊗ A ⊸ D ⊗ A)
    Given k branches [f0; f1; ...; f_{k-1}] each of type A ⊸ A,
    produces coherent controlled application.

    Following the spec's Option 1: emit as a library primitive that
    the backend interprets as "uniform coherent control" on a k-ary sum.

    For now, we emit the branches via omap and wrap with a control primitive.
    The backend is responsible for the actual coherent control implementation.
*)
let control (dt : datatype_desc) (a_ty : 'a ty)
            (branches : (unit, [`Lolli of 'a * 'a]) prog array)
            : (unit, [`Lolli of [`Tensor of 'b * 'a] * [`Tensor of 'b * 'a]]) prog =
  assert_first_order
    ~site:(Printf.sprintf "control (datatype %s)" dt.name) a_ty;
  if Array.length branches <> dt.arity then
    failwith (Printf.sprintf "Datatype %s: control requires %d branches, got %d"
                dt.name dt.arity (Array.length branches));

  (* For arity 1, just apply the single branch in parallel with identity on D *)
  if dt.arity = 1 then
    par0 (id dt.rep) branches.(0)
  else
    (* D = I^{⊕n}, so D ⊗ A has flat tag encoding [tag_bits | A_wires].
       Each summand of D is Unit, so summand ⊗ A = A in the payload.
       We use NMap on n copies of a_ty to apply per-branch morphisms. *)
    let summand_types = Array.make dt.arity a_ty in
    omapn summand_types branches


(** Phase-weighted coherent control over n-ary datatype.
    Applies phase zᵢ to branch i using efficient log₂(k) tag encoding. *)
let phased_control (dt : datatype_desc) (phases : Complex.t array) (a_ty : 'a ty)
                   (_branches : (unit, [`Lolli of 'a * 'a]) prog array)
                   : (unit, [`Lolli of [`Tensor of 'b * 'a] * [`Tensor of 'b * 'a]]) prog =
  assert_first_order
    ~site:(Printf.sprintf "phased_control (datatype %s)" dt.name) a_ty;
  (* Validate arity *)
  if Array.length phases <> dt.arity then
    failwith (Printf.sprintf "Datatype %s: phased_control requires %d phases, got %d"
                dt.name dt.arity (Array.length phases));

  (* Validate phases have modulus 1 and extract angles *)
  let tolerance = 1e-10 in
  let angles = Array.map (fun z ->
    let modulus = Complex.norm z in
    if abs_float (modulus -. 1.0) > tolerance then
      invalid_arg (Printf.sprintf "phased_control: phase must have modulus 1, got |z| = %f" modulus)
    else
      Complex.arg z
  ) phases in

  (* For arity 1, no control needed - just apply phase to the single branch *)
  if dt.arity = 1 then
    (* phase on the whole tensor D ⊗ A *)
    let theta = angles.(0) in
    let da = Rep.Tensor (dt.rep, a_ty) in
    Phase (theta, da)
  else
    (* Emit as PhasedCtrl for backend to handle *)
    PhasedCtrl (dt.name, dt.arity, angles, dt.rep, a_ty)
