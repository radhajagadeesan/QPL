type one = |
type q = |
type ('a, 'b) tensor = |
type ('a, 'b) plus = |
type ('a, 'b) lolli = |
type qbool = (one, one) plus
type !'tag nominal = |

type _ pty =
  | POne : one pty
  | PQ : q pty
  | PQBool : qbool pty
  | PTensor : 'a pty * 'b pty -> ('a, 'b) tensor pty
  | PPlus : 'a pty * 'b pty -> ('a, 'b) plus pty
  | PNominal : string * Rep.t -> 'tag nominal pty

type _ sty =
  | SData : 'a pty -> 'a sty
  | STensor : 'a sty * 'b sty -> ('a, 'b) tensor sty
  | SLolli : 'a sty * 'b sty -> ('a, 'b) lolli sty

module P = struct
  type 'a t = 'a pty

  let q = PQ
  let qbool = PQBool
  let tensor a b = PTensor (a, b)
  let plus a b = PPlus (a, b)
  let ( ** ) = tensor
  let ( ++ ) = plus
end

module S = struct
  type 'a t = 'a sty

  let data p = SData p
  let tensor a b = STensor (a, b)
  let lolli a b = SLolli (a, b)
  let ( ** ) = tensor
  let ( -@ ) = lolli
end

let q = SData PQ
let qbool = SData PQBool

let rec raw_p : type a. a pty -> Rep.t = function
  | POne -> Rep.Unit
  | PQ -> Rep.var 0
  | PQBool -> Rep.Plus (Rep.Unit, Rep.Unit)
  | PTensor (a, b) -> Rep.Tensor (raw_p a, raw_p b)
  | PPlus (a, b) -> Rep.Plus (raw_p a, raw_p b)
  | PNominal (_, rep) -> rep

let rec raw_s : type a. a sty -> Rep.t = function
  | SData p -> raw_p p
  | STensor (a, b) -> Rep.Tensor (raw_s a, raw_s b)
  | SLolli (a, b) -> Rep.Lolli (raw_s a, raw_s b)

let require_finite_angle site theta =
  match classify_float theta with
  | FP_nan | FP_infinite ->
      invalid_arg (site ^ ": expected a finite angle")
  | FP_normal | FP_subnormal | FP_zero ->
      ()

let same_rep a b = a = b

type empty = |
type ('id, 'a, 'tail) cons = |

type ('id, 'a) var = {
  uid : int;
  label : string;
  ty : 'a sty;
}

type _ context =
  | CEmpty : empty context
  | CCons : ('id, 'a) var * 'g context ->
      ('id, 'a, 'g) cons context

type presentation =
  | Neutral
  | Structural

type (_, _) term =
  | Term : 'g context * 'a sty * presentation * Bridge.term -> ('g, 'a) term

type (_, _, _) uses =
  | U0 : (empty, empty, empty) uses
  | UL : ('l, 'r, 'all) uses ->
      (('id, 'a, 'l) cons, 'r, ('id, 'a, 'all) cons) uses
  | UR : ('l, 'r, 'all) uses ->
      ('l, ('id, 'a, 'r) cons, ('id, 'a, 'all) cons) uses

let rec merge :
  type l r all.
  (l, r, all) uses -> l context -> r context -> all context =
  fun route left right ->
    match route, left, right with
    | U0, CEmpty, CEmpty -> CEmpty
    | UL rest, CCons (v, left_tail), right_ctx ->
        CCons (v, merge rest left_tail right_ctx)
    | UR rest, left_ctx, CCons (v, right_tail) ->
        CCons (v, merge rest left_ctx right_tail)

let next_uid = ref 0

let fresh_label stem =
  incr next_uid;
  let safe = if stem = "" then "v" else stem in
  (!next_uid, Printf.sprintf "__source_%s_%d" safe !next_uid)

let make_var ?name ty =
  let stem = match name with Some x -> x | None -> "v" in
  let uid, label = fresh_label stem in
  { uid; label; ty }

let require_same_type site expected actual =
  let expected_rep = raw_s expected in
  let actual_rep = raw_s actual in
  if not (same_rep expected_rep actual_rep) then
    invalid_arg
      (Printf.sprintf "%s: logical types disagree (%s versus %s)"
         site (Rep.to_string expected_rep) (Rep.to_string actual_rep))

let use v =
  Term
    (CCons (v, CEmpty), v.ty, Neutral,
     Bridge.TVar (v.label, raw_s v.ty))

let pair
    (type g1 g2 g a b)
    (Term (left_ctx, left_ty, _, left_raw) : (g1, a) term)
    (Term (right_ctx, right_ty, _, right_raw) : (g2, b) term)
    (route : (g1, g2, g) uses) : (g, (a, b) tensor) term =
  Term
    (merge route left_ctx right_ctx,
     STensor (left_ty, right_ty),
     Structural,
     Bridge.TPair (left_raw, right_raw))

let apply_raw presentation fn argument =
  match presentation with
  | Neutral -> Bridge.TApply (fn, argument)
  | Structural -> Bridge.TSeq (argument, fn)

let app
    (type g1 g2 g a b)
    (Term (fn_ctx, fn_ty, fn_presentation, fn_raw) :
       (g1, (a, b) lolli) term)
    (Term (arg_ctx, arg_ty, _, arg_raw) : (g2, a) term)
    (route : (g1, g2, g) uses) : (g, b) term =
  match fn_ty with
  | SLolli (domain, codomain) ->
      require_same_type "Source.app domain" domain arg_ty;
      Term
        (merge route fn_ctx arg_ctx, codomain, Neutral,
         apply_raw fn_presentation fn_raw arg_raw)

let seq
    (type g1 g2 g a b c)
    (Term (left_ctx, left_ty, left_presentation, left_raw) :
       (g1, (a, b) lolli) term)
    (Term (right_ctx, right_ty, right_presentation, right_raw) :
       (g2, (b, c) lolli) term)
    (route : (g1, g2, g) uses) : (g, (a, c) lolli) term =
  match left_ty, right_ty with
  | SLolli (domain, middle_left), SLolli (middle_right, codomain) ->
      require_same_type "Source.seq cut" middle_left middle_right;
      let context = merge route left_ctx right_ctx in
      (match left_presentation, right_presentation with
       | Structural, Structural ->
           Term
             (context, SLolli (domain, codomain), Structural,
              Bridge.TSeq (left_raw, right_raw))
       | _ ->
           let _, x = fresh_label "seq_arg" in
           let argument = Bridge.TVar (x, raw_s domain) in
           let body =
             apply_raw right_presentation right_raw
               (apply_raw left_presentation left_raw argument)
           in
           Term
             (context, SLolli (domain, codomain), Neutral,
              Bridge.TLam
                (x, raw_s domain, raw_s codomain, body)))

type ('a, 'g, 'b) abstraction = {
  run_lam : 'id. ('id, 'a) var -> (('id, 'a, 'g) cons, 'b) term;
}

let lam :
  type a g b.
  ?name:string -> a sty -> b sty -> (a, g, b) abstraction ->
  (g, (a, b) lolli) term =
  fun ?name domain codomain body ->
    let module Fresh = struct type id end in
    let bound : (Fresh.id, a) var = make_var ?name domain in
    let Term (body_ctx, body_ty, _, body_raw) = body.run_lam bound in
    require_same_type "Source.lam codomain" codomain body_ty;
    match body_ctx with
    | CCons (used, outer_ctx) ->
        if used.uid <> bound.uid then
          invalid_arg
            "Source.lam: the body did not consume the nominal binder it was given";
        Term
          (outer_ctx, SLolli (domain, codomain), Neutral,
           Bridge.TLam
             (bound.label, raw_s domain, raw_s codomain, body_raw))

type ('a, 'b, 'g, 'c) tensor_body = {
  run_split :
    'x 'y.
    ('x, 'a) var ->
    ('y, 'b) var ->
    (('x, 'a, ('y, 'b, 'g) cons) cons, 'c) term;
}

let let_tensor :
  type a b g1 g2 g c.
  ?left_name:string -> ?right_name:string ->
  a sty -> b sty ->
  (g1, (a, b) tensor) term ->
  (a, b, g2, c) tensor_body ->
  (g1, g2, g) uses ->
  (g, c) term =
  fun ?left_name ?right_name left_ty right_ty
      (Term (pair_ctx, pair_ty, _, pair_raw)) body route ->
    (match pair_ty with
     | STensor (actual_left, actual_right) ->
         require_same_type "Source.let_tensor left" left_ty actual_left;
         require_same_type "Source.let_tensor right" right_ty actual_right
     | SData (PTensor (actual_left, actual_right)) ->
         require_same_type "Source.let_tensor left"
           left_ty (SData actual_left);
         require_same_type "Source.let_tensor right"
           right_ty (SData actual_right));
    let module X = struct type id end in
    let module Y = struct type id end in
    let x : (X.id, a) var = make_var ?name:left_name left_ty in
    let y : (Y.id, b) var = make_var ?name:right_name right_ty in
    let Term (body_ctx, body_ty, body_presentation, body_raw) =
      body.run_split x y
    in
    match body_ctx with
    | CCons (used_x, CCons (used_y, outer_ctx)) ->
        if used_x.uid <> x.uid || used_y.uid <> y.uid then
          invalid_arg
            "Source.let_tensor: the body did not consume both issued binders";
        let context = merge route pair_ctx outer_ctx in
        let eliminate body =
          Bridge.TLetPair
            (x.label, y.label, raw_s left_ty, raw_s right_ty,
             pair_raw, body)
        in
        match body_ty with
        | SLolli (domain, codomain) ->
            (* A tensor eliminator returning a function is a value, not a
               circuit action.  Commute an existing lambda through the
               elimination directly.  Other neutral forms are eta-expanded,
               so the emitted Raw head remains a canonical lambda. *)
            let neutral_raw =
              match body_presentation, body_raw with
              | Neutral, Bridge.TLam
                  (argument_name, raw_domain, raw_codomain, lambda_body) ->
                  Bridge.TLam
                    (argument_name, raw_domain, raw_codomain,
                     eliminate lambda_body)
              | _ ->
                  let _, argument_name = fresh_label "split_arg" in
                  let argument =
                    Bridge.TVar (argument_name, raw_s domain)
                  in
                  Bridge.TLam
                    (argument_name, raw_s domain, raw_s codomain,
                     eliminate
                       (apply_raw body_presentation body_raw argument))
            in
            Term (context, body_ty, Neutral, neutral_raw)
        | SData _ | STensor _ ->
            Term
              (context, body_ty, Structural, eliminate body_raw)

let split = let_tensor
let let_pair = let_tensor

type binding = Binding : ('id, 'a) var -> binding

let binding_uid (Binding v) = v.uid
let binding_label (Binding v) = v.label
let binding_rep (Binding v) = raw_s v.ty

let rec bindings : type g. g context -> binding list = function
  | CEmpty -> []
  | CCons (v, tail) -> Binding v :: bindings tail

let same_binding a b =
  binding_uid a = binding_uid b
  && binding_label a = binding_label b
  && same_rep (binding_rep a) (binding_rep b)

let same_bindings left right =
  List.length left = List.length right
  && List.for_all2 same_binding left right

type pack_tree =
  | Leaf of binding
  | Fork of pack_tree * pack_tree

let rec tree_rep = function
  | Leaf b -> binding_rep b
  | Fork (left, right) -> Rep.Tensor (tree_rep left, tree_rep right)

let rec tree_value = function
  | Leaf b -> Bridge.TVar (binding_label b, binding_rep b)
  | Fork (left, right) ->
      Bridge.TPair (tree_value left, tree_value right)

let tree_of_nonempty = function
  | [] -> invalid_arg "Source.case: empty shared context must use Source.case0"
  | first :: rest ->
      List.fold_left (fun tree b -> Fork (tree, Leaf b)) (Leaf first) rest

let child_name stem = function
  | Leaf b -> binding_label b
  | Fork _ -> snd (fresh_label stem)

let rec unpack_tree tree source_name body =
  match tree with
  | Leaf b ->
      if source_name <> binding_label b then
        invalid_arg "Source.case: malformed context-pack leaf";
      body
  | Fork (left, right) ->
      let left_name = child_name "case_left" left in
      let right_name = child_name "case_right" right in
      let inner =
        unpack_tree left left_name
          (unpack_tree right right_name body)
      in
      Bridge.TLetPair
        (left_name, right_name, tree_rep left, tree_rep right,
         Bridge.TVar (source_name, tree_rep tree), inner)

type op_impl =
  | Action of Bridge.term
  | Value of presentation * Bridge.term

type ('a, 'b) op = {
  domain : 'a sty;
  codomain : 'b sty;
  implementation : op_impl;
}

let eta_raw_action domain codomain action =
  let _, x = fresh_label "op_arg" in
  Bridge.TLam
    (x, domain, codomain,
     Bridge.TSeq (Bridge.TVar (x, domain), action))

let eta_action domain codomain action =
  eta_raw_action (raw_s domain) (raw_s codomain) action

let op_value_raw op =
  match op.implementation with
  | Value (presentation, raw) -> (presentation, raw)
  | Action raw -> (Neutral, eta_action op.domain op.codomain raw)

let op_apply_raw op argument =
  match op.implementation with
  | Action raw -> Bridge.TSeq (argument, raw)
  | Value (presentation, raw) -> apply_raw presentation raw argument

module Op = struct
  let seal
      (type a b)
      ~(domain : a sty)
      ~(codomain : b sty)
      (Term (CEmpty, term_ty, presentation, raw) :
         (empty, (a, b) lolli) term) :
      (a, b) op =
    (match term_ty with
     | SLolli (actual_domain, actual_codomain) ->
         require_same_type "Source.Op.seal domain" domain actual_domain;
         require_same_type "Source.Op.seal codomain" codomain actual_codomain);
    { domain; codomain; implementation = Value (presentation, raw) }

  let value op =
    let presentation, raw = op_value_raw op in
    Term (CEmpty, SLolli (op.domain, op.codomain), presentation, raw)

  let apply op (Term (ctx, arg_ty, _, arg_raw)) =
    require_same_type "Source.Op.apply domain" op.domain arg_ty;
    Term (ctx, op.codomain, Neutral, op_apply_raw op arg_raw)

  let action domain codomain raw =
    { domain; codomain; implementation = Action raw }

  let id : type a. a sty -> (a, a) op =
    fun ty ->
    match ty with
    | SLolli _ ->
        let _, name = fresh_label "id_function" in
        let rep = raw_s ty in
        { domain = ty;
          codomain = ty;
          implementation =
            Value (Neutral, Bridge.TLam (name, rep, rep,
                                         Bridge.TVar (name, rep))) }
    | SData _ -> action ty ty (Bridge.TId (raw_s ty))
    | STensor _ -> action ty ty (Bridge.TId (raw_s ty))

  let compose first second =
    require_same_type "Source.Op.compose cut" first.codomain second.domain;
    match first.implementation, second.implementation with
    | Action left, Action right ->
        action first.domain second.codomain (Bridge.TSeq (left, right))
    | _ ->
        let _, x = fresh_label "compose_arg" in
        let body =
          op_apply_raw second
            (op_apply_raw first (Bridge.TVar (x, raw_s first.domain)))
        in
        { domain = first.domain;
          codomain = second.codomain;
          implementation =
            Value
              (Neutral,
               Bridge.TLam
                 (x, raw_s first.domain, raw_s second.codomain, body)) }

  let tensor first second =
    let domain = STensor (first.domain, second.domain) in
    let codomain = STensor (first.codomain, second.codomain) in
    match first.implementation, second.implementation with
    | Action left, Action right ->
        action domain codomain (Bridge.TTenTerm (left, right))
    | _ ->
        let _, p = fresh_label "tensor_arg" in
        let _, x = fresh_label "tensor_left" in
        let _, y = fresh_label "tensor_right" in
        let body =
          Bridge.TPair
            (op_apply_raw first (Bridge.TVar (x, raw_s first.domain)),
             op_apply_raw second (Bridge.TVar (y, raw_s second.domain)))
        in
        { domain; codomain;
          implementation =
            Value
              (Neutral,
               Bridge.TLam
                 (p, raw_s domain, raw_s codomain,
                  Bridge.TLetPair
                    (x, y, raw_s first.domain, raw_s second.domain,
                     Bridge.TVar (p, raw_s domain), body))) }

  let twist a b =
    action (STensor (a, b)) (STensor (b, a))
      (Bridge.TTwistTen (raw_s a, raw_s b))

  let assoc_left a b c =
    action
      (STensor (STensor (a, b), c))
      (STensor (a, STensor (b, c)))
      (Bridge.TAssocTenL (raw_s a, raw_s b, raw_s c))

  let assoc_right a b c =
    action
      (STensor (a, STensor (b, c)))
      (STensor (STensor (a, b), c))
      (Bridge.TAssocTenR (raw_s a, raw_s b, raw_s c))

  let p_data p = SData p

  let twist_plus a b =
    action
      (p_data (PPlus (a, b)))
      (p_data (PPlus (b, a)))
      (Bridge.TTwistPlus (raw_p a, raw_p b))

  let assoc_plus_left a b c =
    action
      (p_data (PPlus (PPlus (a, b), c)))
      (p_data (PPlus (a, PPlus (b, c))))
      (Bridge.TAssocPlusL (raw_p a, raw_p b, raw_p c))

  let assoc_plus_right a b c =
    action
      (p_data (PPlus (a, PPlus (b, c))))
      (p_data (PPlus (PPlus (a, b), c)))
      (Bridge.TAssocPlusR (raw_p a, raw_p b, raw_p c))

  let dist_left a b c =
    action
      (p_data (PTensor (PPlus (a, b), c)))
      (p_data (PPlus (PTensor (a, c), PTensor (b, c))))
      (Bridge.TDistL (raw_p a, raw_p b, raw_p c))

  let dist_right a b c =
    action
      (p_data (PTensor (a, PPlus (b, c))))
      (p_data (PPlus (PTensor (a, b), PTensor (a, c))))
      (Bridge.TDistR (raw_p a, raw_p b, raw_p c))

  let undist_left a b c =
    action
      (p_data (PPlus (PTensor (a, c), PTensor (b, c))))
      (p_data (PTensor (PPlus (a, b), c)))
      (Bridge.TUndistL (raw_p a, raw_p b, raw_p c))

  let undist_right a b c =
    action
      (p_data (PPlus (PTensor (a, b), PTensor (a, c))))
      (p_data (PTensor (a, PPlus (b, c))))
      (Bridge.TUndistR (raw_p a, raw_p b, raw_p c))

  let h = action q q (Bridge.TH 0)
  let s = action q q (Bridge.TS 0)
  let t = action q q (Bridge.TT 0)
  let x = action q q (Bridge.TX 0)
  let y = action q q (Bridge.TY 0)
  let z = action q q (Bridge.TZ 0)
  let not_bool =
    action qbool qbool (Bridge.TTwistPlus (Rep.Unit, Rep.Unit))

  let qq = STensor (q, q)
  let cx = action qq qq (Bridge.TCX (0, 1))
  let rz theta =
    require_finite_angle "Source.Op.rz" theta;
    action q q (Bridge.TRz (theta, 0))

  let phase z p =
    let modulus = Complex.norm z in
    (match classify_float modulus with
     | FP_nan | FP_infinite ->
         invalid_arg
           "Source.Op.phase: expected a finite unit-modulus scalar"
     | FP_normal | FP_subnormal | FP_zero -> ());
    if abs_float (modulus -. 1.0) > 1e-10 then
      invalid_arg
        (Printf.sprintf
           "Source.Op.phase: expected a unit-modulus scalar, got |z|=%g"
           modulus);
    let ty = p_data p in
    action ty ty (Bridge.TGlobalPhase (Complex.arg z, raw_p p))

  type 'a involution = {
    involution_type : 'a pty;
    involution_raw : Bridge.term;
  }

  let involution_id p =
    { involution_type = p; involution_raw = Bridge.TId (raw_p p) }

  let involution_h =
    { involution_type = PQ; involution_raw = Bridge.TH 0 }

  let involution_x =
    { involution_type = PQ; involution_raw = Bridge.TX 0 }

  let involution_y =
    { involution_type = PQ; involution_raw = Bridge.TY 0 }

  let involution_z =
    { involution_type = PQ; involution_raw = Bridge.TZ 0 }

  let involution_cx =
    { involution_type = PTensor (PQ, PQ);
      involution_raw = Bridge.TCX (0, 1) }

  let involution_twist p =
    { involution_type = PTensor (p, p);
      involution_raw = Bridge.TTwistTen (raw_p p, raw_p p) }

  let involution_tensor left right =
    { involution_type =
        PTensor (left.involution_type, right.involution_type);
      involution_raw =
        Bridge.TTenTerm (left.involution_raw, right.involution_raw) }

  let involution_plus left right =
    { involution_type =
        PPlus (left.involution_type, right.involution_type);
      involution_raw =
        Bridge.TPlusMap
          (raw_p left.involution_type, raw_p right.involution_type,
           left.involution_raw, right.involution_raw) }

  let exp_i theta involution =
    require_finite_angle "Source.Op.exp_i" theta;
    let ty = p_data involution.involution_type in
    action ty ty
      (Bridge.TExpInvolution (theta, involution.involution_raw))
end

let make_branch tree gamma_rep arm_rep body =
  let gamma = child_name "case_context" tree in
  let _, arm = fresh_label "case_branch_arm" in
  let domain = Rep.Tensor (gamma_rep, arm_rep) in
  let result =
    unpack_tree tree gamma
      (Bridge.TPair (Bridge.TVar (arm, arm_rep), body))
  in
  Bridge.TLetPair
    (gamma, arm, gamma_rep, arm_rep,
     Bridge.TId domain, result)

let require_result site expected actual =
  require_same_type site (SData expected) actual


module Datatype = struct
  type zero = |
  type !'n succ = |

  type (!'n, !'a) vector =
    | VNil : (zero, 'a) vector
    | VCons : 'a * ('n, 'a) vector -> ('n succ, 'a) vector

  let ( @: ) value rest = VCons (value, rest)

  type n1 = zero succ
  type n2 = n1 succ
  type n3 = n2 succ
  type n4 = n3 succ
  type n5 = n4 succ
  type n6 = n5 succ
  type n7 = n6 succ
  type n8 = n7 succ

  module type SPEC = sig
    type tail
    val name : string
    val labels : (tail succ, string) vector
  end

  let rec to_list : type n a. (n, a) vector -> a list = function
    | VNil -> []
    | VCons (head, tail) -> head :: to_list tail

  (* The clean Source calculus (accompanying paper) fixes the
     LEFT-associated expansion bigplus_{i<=n} A_i := (bigplus_{i<n}) ⊕ A_n
     and defines Q_n as that expansion at base = I.  Flat tag
     codes are the left-to-right leaf order under either association, so
     this choice is structural, and it is pinned structurally — not just
     behaviorally — by test_source_datatype_ops. *)
  let rec unit_sum = function
    | 1 -> Rep.Unit
    | n when n > 1 -> Rep.Plus (unit_sum (n - 1), Rep.Unit)
    | _ -> invalid_arg "Source.Datatype: a datatype must be nonempty"

  let require_nonblank site value =
    if String.trim value = "" then
      invalid_arg (site ^ ": names must be nonblank")

  let require_distinct labels =
    let sorted = List.sort String.compare labels in
    let rec loop = function
      | left :: (right :: _ as rest) ->
          if String.equal left right then
            invalid_arg
              ("Source.Datatype: duplicate constructor label " ^ left);
          loop rest
      | _ -> ()
    in
    loop sorted

  module Make (D : SPEC) () = struct
    type tag
    type t = tag nominal
    type arity = D.tail succ

    let name =
      require_nonblank "Source.Datatype" D.name;
      D.name

    let labels =
      let values = to_list D.labels in
      List.iter (require_nonblank "Source.Datatype constructor") values;
      require_distinct values;
      values

    let arity = List.length labels
    let representation = unit_sum arity
    let p : t pty = PNominal (name, representation)
    let s : t sty = SData p

    let select
        (type a)
        ~(target : a pty)
        (branches : (arity, (a, a) op) vector) :
        ((t, a) tensor, (t, a) tensor) op =
      let branch_array =
        branches
        |> to_list
        |> List.map
             (fun op ->
               op_apply_raw op (Bridge.TId (raw_p target)))
        |> Array.of_list
      in
      if Array.length branch_array <> arity then
        invalid_arg
          "Source.Datatype.select: impossible arity witness mismatch";
      let target_ty = SData target in
      let object_ty = STensor (s, target_ty) in
      { domain = object_ty;
        codomain = object_ty;
        implementation =
          Action
            (Bridge.TDatatypeControl
               (name, arity, representation, raw_p target, branch_array)) }

    (* -------------------------------------------------------------- *)
    (* Exhaustive tag-preserving datatype case.                        *)
    (*                                                                *)
    (* The pipeline is a single flat dispatch over the canonical       *)
    (* LEFT-associated representation fixed by the clean calculus       *)
    (* (accompanying paper: bigplus_{i<=n} := (bigplus_{i<n}) ⊕ A_n);   *)
    (* branch order is declaration order, the tag survives, and every  *)
    (* branch consumes the identical complete nominal linear context.  *)
    (* -------------------------------------------------------------- *)

    let cases
        (type c g1 gamma g)
        ~(result : c pty)
        ~(scrutinee : (g1, t) term)
        ~(branches : (arity, (gamma, c) term) vector)
        ~(using : (g1, gamma, g) uses) :
        (g, (t, c) tensor) term =
      let Term (scrut_ctx, scrut_ty, _, scrut_raw) = scrutinee in
      require_same_type "Source.Datatype.cases scrutinee" s scrut_ty;
      let branch_terms = to_list branches in
      let branch_raws =
        List.mapi
          (fun i (Term (ctx, branch_result, _, raw)) ->
            require_result
              (Printf.sprintf "Source.Datatype.cases branch %d result" i)
              result branch_result;
            (bindings ctx, raw))
          branch_terms
      in
      let first_bindings =
        match branch_raws with
        | (b, _) :: _ -> b
        | [] ->
            invalid_arg "Source.Datatype.cases: impossible empty arity"
      in
      List.iteri
        (fun i (b, _) ->
          if not (same_bindings first_bindings b) then
            invalid_arg
              (Printf.sprintf
                 "Source.Datatype.cases: branch %d does not use the \
                  identical complete nominal context" i))
        branch_raws;
      let tree = tree_of_nonempty first_bindings in
      let gamma_rep = tree_rep tree in
      let result_rep = raw_p result in
      (* Flat n-ary pipeline in the canonical LEFT-associated encoding
         (the n_dist / n_factor law: for unit summands, both distributed
         forms share the flat layout, so the boundary conversions are
         wire-level identities and dispatch is a single flat NPlusMap):

           t ⊗ Γ  ==  ⊕ᵢ (I ⊗ Γ)  --NPlusMap[mᵢ]-->  ⊕ᵢ (I ⊗ c)  ==  t ⊗ c

         with each mᵢ : I ⊗ Γ → I ⊗ c destructuring the packed context.
         The distributed sums mirror [unit_sum]'s left association. *)
      let branch_map raw =
        let _, arm = fresh_label "cases_arm" in
        let gname = child_name "cases_context" tree in
        let body =
          unpack_tree tree gname
            (Bridge.TPair (Bridge.TVar (arm, Rep.Unit), raw))
        in
        Bridge.TLetPair
          (arm, gname, Rep.Unit, gamma_rep,
           Bridge.TId (Rep.Tensor (Rep.Unit, gamma_rep)), body)
      in
      let left_assoc_sum_of leaf =
        let rec go k =
          if k = 1 then leaf else Rep.Plus (go (k - 1), leaf)
        in
        go arity
      in
      let build_plus () = left_assoc_sum_of (Rep.Tensor (Rep.Unit, gamma_rep)) in
      let build_plus_out () =
        left_assoc_sum_of (Rep.Tensor (Rep.Unit, result_rep))
      in
      let summand_domains =
        Array.make arity (Rep.Tensor (Rep.Unit, gamma_rep))
      in
      let maps =
        Array.of_list (List.map (fun (_, raw) -> branch_map raw) branch_raws)
      in
      let pipeline =
        Bridge.TSeq
          (Bridge.TWireIdentity
             (Rep.Tensor (representation, gamma_rep), build_plus ()),
           Bridge.TSeq
             (Bridge.TNPlusMap (summand_domains, maps),
              Bridge.TWireIdentity
                (build_plus_out (),
                 Rep.Tensor (representation, result_rep))))
      in
      let pipeline_value =
        eta_raw_action
          (Rep.Tensor (representation, gamma_rep))
          (Rep.Tensor (representation, result_rep))
          pipeline
      in
      let input = Bridge.TPair (scrut_raw, tree_value tree) in
      let first_ctx =
        match branch_terms with
        | Term (ctx, _, _, _) :: _ -> ctx
        | [] -> assert false
      in
      Term
        (merge using scrut_ctx first_ctx,
         STensor (s, SData result), Structural,
         Bridge.TApply (pipeline_value, input))

    let cases0
        (type c g)
        ~(result : c pty)
        ~(scrutinee : (g, t) term)
        ~(branches : (arity, (empty, c) term) vector) :
        (g, (t, c) tensor) term =
      let Term (ctx, scrut_ty, _, scrut_raw) = scrutinee in
      require_same_type "Source.Datatype.cases0 scrutinee" s scrut_ty;
      let branch_raws =
        List.mapi
          (fun i (Term (CEmpty, branch_result, _, raw)) ->
            require_result
              (Printf.sprintf "Source.Datatype.cases0 branch %d result" i)
              result branch_result;
            raw)
          (to_list branches)
      in
      let result_rep = raw_p result in
      let build_plus_out () =
        let leaf = Rep.Tensor (Rep.Unit, result_rep) in
        let rec go k = if k = 1 then leaf else Rep.Plus (go (k - 1), leaf) in
        go arity
      in
      let summand_domains = Array.make arity Rep.Unit in
      let maps =
        Array.of_list
          (List.map
             (fun raw -> Bridge.TPair (Bridge.TId Rep.Unit, raw))
             branch_raws)
      in
      let pipeline =
        Bridge.TSeq
          (Bridge.TNPlusMap (summand_domains, maps),
           Bridge.TWireIdentity
             (build_plus_out (), Rep.Tensor (representation, result_rep)))
      in
      let pipeline_value =
        eta_raw_action representation
          (Rep.Tensor (representation, result_rep))
          pipeline
      in
      Term
        (ctx, STensor (s, SData result), Structural,
         Bridge.TApply (pipeline_value, scrut_raw))

    (* -------------------------------------------------------------- *)
    (* Certified label permutations.  Position i carries the           *)
    (* destination of constructor i (forward: |i⟩ ↦ |p(i)⟩), lowering  *)
    (* through the trusted TagPerm machinery, which fixes every        *)
    (* padding state of a non-power-of-two arity by construction.      *)
    (* -------------------------------------------------------------- *)

    let permutation_array site (vec : (arity, int) vector) : int array =
      let images = Array.of_list (to_list vec) in
      if Array.length images <> arity then
        invalid_arg (site ^ ": impossible arity witness mismatch");
      Array.iteri
        (fun i image ->
          if image < 0 || image >= arity then
            invalid_arg
              (Printf.sprintf
                 "%s: constructor %d maps to %d, outside 0..%d"
                 site i image (arity - 1)))
        images;
      let seen = Array.make arity false in
      Array.iteri
        (fun i image ->
          if seen.(image) then
            invalid_arg
              (Printf.sprintf
                 "%s: not a bijection (image %d repeated at constructor %d)"
                 site image i);
          seen.(image) <- true)
        images;
      images

    let permute (vec : (arity, int) vector) : (t, t) op =
      let images =
        permutation_array "Source.Datatype.permute" vec
      in
      { domain = s;
        codomain = s;
        implementation =
          Action
            (Bridge.TTagPerm (Array.to_list images, representation)) }

    let involution_permute (vec : (arity, int) vector) : t Op.involution =
      let images =
        permutation_array "Source.Datatype.involution_permute" vec
      in
      Array.iteri
        (fun i image ->
          if images.(image) <> i then
            invalid_arg
              (Printf.sprintf
                 "Source.Datatype.involution_permute: not an involution \
                  (constructor %d maps to %d, which maps to %d)"
                 i image images.(image)))
        images;
      { Op.involution_type = p;
        involution_raw =
          Bridge.TTagPerm (Array.to_list images, representation) }
  end
end

let case
    (type a b c g1 gamma g)
    ~(left : a pty)
    ~(right : b pty)
    ~(result : c pty)
    ~(scrutinee : (g1, (a, b) plus) term)
    ~(left_branch : (gamma, c) term)
    ~(right_branch : (gamma, c) term)
    ~(using : (g1, gamma, g) uses) :
    (g, ((a, b) plus, c) tensor) term =
  let Term (scrut_ctx, scrut_ty, _, scrut_raw) = scrutinee in
  let Term (left_ctx, left_result, _, left_raw) = left_branch in
  let Term (right_ctx, right_result, _, right_raw) = right_branch in
  require_same_type "Source.case scrutinee"
    (SData (PPlus (left, right))) scrut_ty;
  require_result "Source.case left result" result left_result;
  require_result "Source.case right result" result right_result;
  let left_bindings = bindings left_ctx in
  let right_bindings = bindings right_ctx in
  if not (same_bindings left_bindings right_bindings) then
    invalid_arg
      "Source.case: both branches must use the identical complete nominal context";
  let tree = tree_of_nonempty left_bindings in
  let gamma_rep = tree_rep tree in
  let left_rep = raw_p left in
  let right_rep = raw_p right in
  let result_rep = raw_p result in
  let left_map =
    make_branch tree gamma_rep left_rep left_raw
  in
  let right_map =
    make_branch tree gamma_rep right_rep right_raw
  in
  let pipeline =
    Bridge.TSeq
      (Bridge.TDistR (gamma_rep, left_rep, right_rep),
       Bridge.TSeq
         (Bridge.TPlusMap
            (Rep.Tensor (gamma_rep, left_rep),
             Rep.Tensor (gamma_rep, right_rep),
             left_map, right_map),
          Bridge.TUndistL (left_rep, right_rep, result_rep)))
  in
  let input = Bridge.TPair (tree_value tree, scrut_raw) in
  let pipeline_domain =
    Rep.Tensor (gamma_rep, Rep.Plus (left_rep, right_rep))
  in
  let pipeline_codomain =
    Rep.Tensor (Rep.Plus (left_rep, right_rep), result_rep)
  in
  let pipeline_value =
    eta_raw_action pipeline_domain pipeline_codomain pipeline
  in
  Term
    (merge using scrut_ctx left_ctx,
     STensor (SData (PPlus (left, right)), SData result), Structural,
     Bridge.TApply (pipeline_value, input))

let case0
    (type a b c g)
    ~(left : a pty)
    ~(right : b pty)
    ~(result : c pty)
    ~(scrutinee : (g, (a, b) plus) term)
    ~(left_branch : (empty, c) term)
    ~(right_branch : (empty, c) term) :
    (g, ((a, b) plus, c) tensor) term =
  let Term (ctx, scrut_ty, _, scrut_raw) = scrutinee in
  let Term (CEmpty, left_result, _, left_raw) = left_branch in
  let Term (CEmpty, right_result, _, right_raw) = right_branch in
  require_same_type "Source.case0 scrutinee"
    (SData (PPlus (left, right))) scrut_ty;
  require_result "Source.case0 left result" result left_result;
  require_result "Source.case0 right result" result right_result;
  let left_rep = raw_p left in
  let right_rep = raw_p right in
  let result_rep = raw_p result in
  let left_map =
    Bridge.TPair (Bridge.TId left_rep, left_raw)
  in
  let right_map =
    Bridge.TPair (Bridge.TId right_rep, right_raw)
  in
  let pipeline =
    Bridge.TSeq
      (Bridge.TPlusMap (left_rep, right_rep, left_map, right_map),
       Bridge.TUndistL (left_rep, right_rep, result_rep))
  in
  let pipeline_domain = Rep.Plus (left_rep, right_rep) in
  let pipeline_codomain =
    Rep.Tensor (Rep.Plus (left_rep, right_rep), result_rep)
  in
  let pipeline_value =
    eta_raw_action pipeline_domain pipeline_codomain pipeline
  in
  Term
    (ctx,
     STensor (SData (PPlus (left, right)), SData result), Structural,
     Bridge.TApply (pipeline_value, scrut_raw))

let case_bool ~result ~scrutinee ~zero ~one_ ~using =
  case ~left:POne ~right:POne ~result ~scrutinee
    ~left_branch:zero ~right_branch:one_ ~using

let case_bool0 ~result ~scrutinee ~zero ~one_ =
  case0 ~left:POne ~right:POne ~result ~scrutinee
    ~left_branch:zero ~right_branch:one_

let emit (Term (CEmpty, _, _, raw)) = raw
