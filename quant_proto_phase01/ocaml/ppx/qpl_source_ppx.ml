(* Ergonomic frontend for the sealed Source calculus.

   [let%source] bindings written in ordinary OCaml syntax elaborate into the
   sealed [Qpl_surface.Source] combinators.  The rewriter is a SEMANTIC
   compiler component: the sealed GADT re-checks typing, linearity, context
   partitioning and the first-order sum restriction, but it cannot know the
   user's intent, so this frontend is validated by positive expansion and
   circuit-equivalence tests against handwritten sealed oracles.

   TYPE/WITNESS ACQUISITION RULE (explicit; nothing is deferred to OCaml
   inference, which runs after this rewriter):

   - every Source parameter carries an annotation in the sealed type
     grammar: [q], [qbool], [('a,'b) tensor], [('a,'b) plus],
     [('a,'b) lolli], a datatype path [M.t], or a type variable ['v];
   - every type variable used in Source annotations must be introduced by
     an explicit leading witness parameter [(a : 'v P.t)].  It is emitted
     as an ordinary, visible OCaml parameter of the generated value; there
     are no hidden arguments;
   - result types are computed bottom-up by the Source typing rules from
     those annotations (application peels [lolli], tuples build [tensor],
     [split] projects a [tensor], [case] yields [(qbool, branch) tensor]).
     An explicit [: ty] result annotation is accepted and checked; it is
     REQUIRED whenever the walker cannot determine a leaf type;
   - host operations: the primitive gate names [h s t x y z cx not_bool]
     have built-in types; any other host identifier applied inside a
     source body must denote a certified endomorphism [('a,'a) op] and its
     result type is its argument's type.  A non-endomorphism host operation
     must be wrapped at the call site with an annotation.

   The rewriter never writes files; use [dune describe pp] to display the
   expansion. *)

open Ppxlib
module Ab = Ast_builder.Default

let src_mod = ["Qpl_surface"; "Source"]

let lid_of_path path last =
  match path @ [last] with
  | [] -> assert false
  | first :: rest ->
      List.fold_left (fun acc x -> Ldot (acc, x)) (Lident first) rest

let src_ident ~loc names last =
  Ab.pexp_ident ~loc { txt = lid_of_path (src_mod @ names) last; loc }

let err ~loc fmt = Location.raise_errorf ~loc fmt

(* ------------------------------------------------------------------ *)
(* The sealed type grammar, as parsed from annotations                  *)
(* ------------------------------------------------------------------ *)

type sty =
  | TQ
  | TQBool
  | TTensor of sty * sty
  | TPlus of sty * sty
  | TLolli of sty * sty
  | TVar of string
  | TData of Longident.t * Location.t   (* module path M, from M.t *)

let rec first_order = function
  | TQ | TQBool | TVar _ | TData _ -> true
  | TTensor (a, b) | TPlus (a, b) -> first_order a && first_order b
  | TLolli _ -> false

let rec sty_equal a b =
  match a, b with
  | TQ, TQ | TQBool, TQBool -> true
  | TTensor (a1, a2), TTensor (b1, b2)
  | TPlus (a1, a2), TPlus (b1, b2)
  | TLolli (a1, a2), TLolli (b1, b2) ->
      sty_equal a1 b1 && sty_equal a2 b2
  | TVar v, TVar w -> String.equal v w
  | TData (m, _), TData (n, _) ->
      String.equal (Longident.name m) (Longident.name n)
  | _ -> false

let rec sty_to_string = function
  | TQ -> "q"
  | TQBool -> "qbool"
  | TTensor (a, b) ->
      Printf.sprintf "(%s, %s) tensor" (sty_to_string a) (sty_to_string b)
  | TPlus (a, b) ->
      Printf.sprintf "(%s, %s) plus" (sty_to_string a) (sty_to_string b)
  | TLolli (a, b) ->
      Printf.sprintf "(%s, %s) lolli" (sty_to_string a) (sty_to_string b)
  | TVar v -> "'" ^ v
  | TData (m, _) -> Longident.name m ^ ".t"

let tail_ident = function
  | Lident name -> name
  | Ldot (_, name) -> name
  | Lapply _ -> ""

let rec parse_ty (ct : core_type) : sty =
  let loc = ct.ptyp_loc in
  match ct.ptyp_desc with
  | Ptyp_var v -> TVar v
  | Ptyp_constr ({ txt; _ }, args) -> (
      match tail_ident txt, args with
      | "q", [] -> TQ
      | "qbool", [] -> TQBool
      | "tensor", [a; b] -> TTensor (parse_ty a, parse_ty b)
      | "plus", [a; b] ->
          let a' = parse_ty a and b' = parse_ty b in
          if not (first_order a') then
            err ~loc:a.ptyp_loc
              "Source: a sum admits only first-order data; %s contains a \
               function space beneath plus"
              (sty_to_string a');
          if not (first_order b') then
            err ~loc:b.ptyp_loc
              "Source: a sum admits only first-order data; %s contains a \
               function space beneath plus"
              (sty_to_string b');
          TPlus (a', b')
      | "lolli", [a; b] -> TLolli (parse_ty a, parse_ty b)
      | "t", [] -> (
          match txt with
          | Ldot (m, _) -> TData (m, loc)
          | _ ->
              err ~loc
                "Source: a datatype annotation must be a module path M.t")
      | _ ->
          err ~loc
            "Source: unknown type %s; the sealed grammar is q, qbool, \
             ('a,'b) tensor, ('a,'b) plus, ('a,'b) lolli, a datatype M.t, \
             or a witness type variable"
            (tail_ident txt))
  | _ -> err ~loc "Source: unsupported type syntax in a Source annotation"

(* witness environment: type variable -> OCaml identifier of its P.t *)
type wenv = (string * string) list

let module_ident ~loc m last =
  Ab.pexp_ident ~loc { txt = Ldot (m, last); loc }

let rec p_wit ~loc (wenv : wenv) = function
  | TQ -> src_ident ~loc ["P"] "q"
  | TQBool -> src_ident ~loc ["P"] "qbool"
  | TTensor (a, b) ->
      [%expr
        [%e src_ident ~loc ["P"] "tensor"]
          [%e p_wit ~loc wenv a] [%e p_wit ~loc wenv b]]
  | TPlus (a, b) ->
      [%expr
        [%e src_ident ~loc ["P"] "plus"]
          [%e p_wit ~loc wenv a] [%e p_wit ~loc wenv b]]
  | TVar v -> (
      match List.assoc_opt v wenv with
      | Some name -> Ab.evar ~loc name
      | None ->
          err ~loc
            "Source: type variable '%s needs an explicit witness parameter \
             (name : '%s P.t) before the Source parameters"
            v v)
  | TData (m, _) -> module_ident ~loc m "p"
  | TLolli _ as t ->
      err ~loc
        "Source: %s is not first-order, so it has no P witness"
        (sty_to_string t)

let rec s_wit ~loc (wenv : wenv) = function
  | TQ -> src_ident ~loc [] "q"
  | TQBool -> src_ident ~loc [] "qbool"
  | TTensor (a, b) ->
      [%expr
        [%e src_ident ~loc ["S"] "tensor"]
          [%e s_wit ~loc wenv a] [%e s_wit ~loc wenv b]]
  | TLolli (a, b) ->
      [%expr
        [%e src_ident ~loc ["S"] "lolli"]
          [%e s_wit ~loc wenv a] [%e s_wit ~loc wenv b]]
  | (TPlus _ | TVar _ | TData _) as t ->
      [%expr [%e src_ident ~loc ["S"] "data"] [%e p_wit ~loc wenv t]]

(* ------------------------------------------------------------------ *)
(* Binders, contexts, and uses-witness synthesis                        *)
(* ------------------------------------------------------------------ *)

type binder = {
  stamp : int;
  ml_name : string;
  bty : sty;
  bloc : Location.t;
}

(* a context is a binder list, innermost (highest stamp) first *)
type ctx = binder list

let counter = ref 0

let fresh_stamp () =
  incr counter;
  !counter

(* deterministic ordered interleaving of two disjoint stamped contexts;
   returns the UL/UR/U0 evidence and the merged context *)
let route ~loc (left : ctx) (right : ctx) : expression * ctx =
  let ctor name arg =
    Ab.pexp_construct ~loc { txt = lid_of_path src_mod name; loc } arg
  in
  let u0 = ctor "U0" None in
  let ul e = ctor "UL" (Some e) in
  let ur e = ctor "UR" (Some e) in
  let rec go l r =
    match l, r with
    | [], [] -> u0, []
    | lb :: _ltl, rb :: _ when lb.stamp = rb.stamp ->
        err ~loc
          "Source: variable %s is used on both sides here; a linear \
           variable is consumed exactly once"
          lb.ml_name
    | lb :: ltl, (rb :: _ as r) when lb.stamp > rb.stamp ->
        let rest, merged = go ltl r in
        ul rest, lb :: merged
    | lb :: ltl, [] ->
        let rest, merged = go ltl [] in
        ul rest, lb :: merged
    | l, rb :: rtl ->
        let rest, merged = go l rtl in
        ur rest, rb :: merged
  in
  go left right

let ctx_names ctx = String.concat ", " (List.map (fun b -> b.ml_name) ctx)

(* ------------------------------------------------------------------ *)
(* Host operations                                                      *)
(* ------------------------------------------------------------------ *)

let builtin_ops =
  [
    "h", ("h", TLolli (TQ, TQ));
    "s", ("s", TLolli (TQ, TQ));
    "t", ("t", TLolli (TQ, TQ));
    "x", ("x", TLolli (TQ, TQ));
    "y", ("y", TLolli (TQ, TQ));
    "z", ("z", TLolli (TQ, TQ));
    "cx", ("cx", TLolli (TTensor (TQ, TQ), TTensor (TQ, TQ)));
    "not_bool", ("not_bool", TLolli (TQBool, TQBool));
  ]

(* ------------------------------------------------------------------ *)
(* Elaboration                                                          *)
(* ------------------------------------------------------------------ *)

type env = (string * binder) list

let op_apply ~loc op_expr arg =
  [%expr [%e src_ident ~loc ["Op"] "apply"] [%e op_expr] [%e arg]]

let rec elab (wenv : wenv) (env : env) (e : expression) :
    expression * ctx * sty =
  let loc = e.pexp_loc in
  match e.pexp_desc with
  | Pexp_ident { txt = Lident name; _ } -> (
      match List.assoc_opt name env with
      | Some b ->
          let use = src_ident ~loc [] "use" in
          [%expr [%e use] [%e Ab.evar ~loc b.ml_name]], [b], b.bty
      | None ->
          err ~loc
            "Source: %s is not bound in this source expression; host \
             operations are used in application position"
            name)
  | Pexp_constraint (inner, ct) ->
      let annotated = parse_ty ct in
      let inner', ctx, ty = elab wenv env inner in
      if not (sty_equal annotated ty) then
        err ~loc
          "Source: this expression has type %s but is annotated %s"
          (sty_to_string ty) (sty_to_string annotated);
      inner', ctx, ty
  | Pexp_tuple [ e1; e2 ] ->
      let e1', c1, t1 = elab wenv env e1 in
      let e2', c2, t2 = elab wenv env e2 in
      let uses, merged = route ~loc c1 c2 in
      ( [%expr [%e src_ident ~loc [] "pair"] [%e e1'] [%e e2'] [%e uses]],
        merged,
        TTensor (t1, t2) )
  | Pexp_tuple _ ->
      err ~loc "Source: tensors are binary; nest pairs explicitly"
  | Pexp_let
      ( Nonrecursive,
        [ { pvb_pat = { ppat_desc = Ppat_tuple [ lp; rp ]; _ };
            pvb_expr = producer_call; _ } ],
        body ) ->
      elab_split wenv env ~loc lp rp producer_call body
  | Pexp_apply ({ pexp_desc = Pexp_ident { txt = Lident "case"; _ }; _ }, args)
    ->
      elab_case wenv env ~loc args
  | Pexp_apply (fn, [ (Nolabel, arg) ]) -> (
      let arg', arg_ctx, arg_ty = elab wenv env arg in
      match fn.pexp_desc with
      | Pexp_ident { txt = Lident name; _ }
        when (not (List.mem_assoc name env))
             && List.mem_assoc name builtin_ops ->
          let op_name, op_ty = List.assoc name builtin_ops in
          let dom, cod =
            match op_ty with TLolli (d, c) -> d, c | _ -> assert false
          in
          if not (sty_equal dom arg_ty) then
            err ~loc:arg.pexp_loc
              "Source: %s expects %s but the argument has type %s"
              name (sty_to_string dom) (sty_to_string arg_ty);
          ( op_apply ~loc
              (src_ident ~loc:fn.pexp_loc ["Op"] op_name)
              arg',
            arg_ctx, cod )
      | Pexp_ident { txt = (Lident name as txt); _ }
        when not (List.mem_assoc name env) ->
          (* host endomorphism rule: a certified ('a,'a) op *)
          ( op_apply ~loc
              (Ab.pexp_ident ~loc:fn.pexp_loc { txt; loc = fn.pexp_loc })
              arg',
            arg_ctx, arg_ty )
      | Pexp_ident { txt = (Ldot _ as txt); _ } ->
          (* qualified host operation, endomorphism rule *)
          ( op_apply ~loc
              (Ab.pexp_ident ~loc:fn.pexp_loc { txt; loc = fn.pexp_loc })
              arg',
            arg_ctx, arg_ty )
      | _ ->
          let fn', fn_ctx, fn_ty = elab wenv env fn in
          let dom, cod =
            match fn_ty with
            | TLolli (d, c) -> d, c
            | other ->
                err ~loc:fn.pexp_loc
                  "Source: this expression has type %s and cannot be \
                   applied"
                  (sty_to_string other)
          in
          if not (sty_equal dom arg_ty) then
            err ~loc:arg.pexp_loc
              "Source: this function expects %s but the argument has type \
               %s"
              (sty_to_string dom) (sty_to_string arg_ty);
          let uses, merged = route ~loc fn_ctx arg_ctx in
          ( [%expr [%e src_ident ~loc [] "app"] [%e fn'] [%e arg'] [%e uses]],
            merged, cod ))
  | Pexp_apply (fn, (Nolabel, first) :: rest) ->
      (* curried application: associate to the left *)
      let inner =
        { e with pexp_desc = Pexp_apply (fn, [ (Nolabel, first) ]) }
      in
      elab wenv env { e with pexp_desc = Pexp_apply (inner, rest) }
  | _ ->
      err ~loc
        "Source: unsupported syntax in a source expression (expected a \
         variable, application, pair, let (a,b) = split ..., or case ... \
         ~zero: ... ~one_: ...)"

and elab_split wenv env ~loc lp rp producer_call body =
  let producer =
    match producer_call.pexp_desc with
    | Pexp_apply
        ( { pexp_desc =
              Pexp_ident
                { txt = Lident ("split" | "let_tensor" | "let_pair"); _ };
            _ },
          [ (Nolabel, producer) ] ) ->
        producer
    | _ ->
        err ~loc:producer_call.pexp_loc
          "Source: tensor elimination is written let (a, b) = split \
           producer in ..."
  in
  let binder_name p =
    match p.ppat_desc with
    | Ppat_var { txt; _ } -> txt
    | _ -> err ~loc:p.ppat_loc "Source: split binders must be variables"
  in
  let lname = binder_name lp and rname = binder_name rp in
  let producer', p_ctx, p_ty = elab wenv env producer in
  let lty, rty =
    match p_ty with
    | TTensor (a, b) -> a, b
    | other ->
        err ~loc:producer.pexp_loc
          "Source: split expects a tensor, but this expression has type %s"
          (sty_to_string other)
  in
  (* the sealed API requires body context = left :: right :: outer, so the
     left binder is stamped above the right one *)
  let rb = { stamp = fresh_stamp (); ml_name = rname; bty = rty;
             bloc = rp.ppat_loc } in
  let lb = { stamp = fresh_stamp (); ml_name = lname; bty = lty;
             bloc = lp.ppat_loc } in
  let env' = (lname, lb) :: (rname, rb) :: env in
  let body', body_ctx, body_ty = elab wenv env' body in
  let outer =
    match body_ctx with
    | b1 :: b2 :: rest when b1.stamp = lb.stamp && b2.stamp = rb.stamp ->
        rest
    | _ ->
        let missing =
          List.filter
            (fun b -> not (List.exists (fun c -> c.stamp = b.stamp) body_ctx))
            [ lb; rb ]
        in
        (match missing with
        | b :: _ ->
            err ~loc:b.bloc
              "Source: %s is bound here but never used; both tensor \
               components must be consumed exactly once"
              b.ml_name
        | [] ->
            err ~loc "Source: internal context-ordering error at split")
  in
  let uses, merged = route ~loc p_ctx outer in
  let lpat = Ab.pvar ~loc:lp.ppat_loc lname in
  let rpat = Ab.pvar ~loc:rp.ppat_loc rname in
  let record =
    Ab.pexp_record ~loc
      [ ( { txt = lid_of_path src_mod "run_split"; loc },
          Ab.eabstract ~loc [ lpat; rpat ] body' ) ]
      None
  in
  ( [%expr
      [%e src_ident ~loc [] "let_tensor"]
        ~left_name:[%e Ab.estring ~loc lname]
        ~right_name:[%e Ab.estring ~loc rname]
        [%e s_wit ~loc wenv lty] [%e s_wit ~loc wenv rty]
        [%e producer'] [%e record] [%e uses]],
    merged, body_ty )

and elab_case wenv env ~loc args =
  let scrutinee = ref None and zero = ref None and one_ = ref None in
  List.iter
    (fun (label, value) ->
      match label with
      | Nolabel when !scrutinee = None -> scrutinee := Some value
      | Labelled "zero" when !zero = None -> zero := Some value
      | Labelled "one_" when !one_ = None -> one_ := Some value
      | _ ->
          err ~loc:value.pexp_loc
            "Source: case takes one scrutinee and ~zero:/~one_: branches")
    args;
  let need what = function
    | Some v -> v
    | None -> err ~loc "Source: case is missing its %s" what
  in
  let scrutinee = need "scrutinee" !scrutinee in
  let zero = need "~zero: branch" !zero in
  let one_ = need "~one_: branch" !one_ in
  let scrut', scrut_ctx, scrut_ty = elab wenv env scrutinee in
  (match scrut_ty with
  | TQBool -> ()
  | other ->
      err ~loc:scrutinee.pexp_loc
        "Source: this case form scrutinizes qbool, but the scrutinee has \
         type %s"
        (sty_to_string other));
  let zero', z_ctx, z_ty = elab wenv env zero in
  let one', o_ctx, o_ty = elab wenv env one_ in
  if not (sty_equal z_ty o_ty) then
    err ~loc
      "Source: the two branches have different types (%s versus %s)"
      (sty_to_string z_ty) (sty_to_string o_ty);
  if not (first_order z_ty) then
    err ~loc
      "Source: a case result must be first-order data, but the branches \
       have type %s"
      (sty_to_string z_ty);
  let same_ctx =
    List.length z_ctx = List.length o_ctx
    && List.for_all2 (fun a b -> a.stamp = b.stamp) z_ctx o_ctx
  in
  if not same_ctx then
    err ~loc
      "Source: both case branches must consume the same nominal linear \
       context; ~zero: uses [%s] but ~one_: uses [%s]"
      (ctx_names z_ctx) (ctx_names o_ctx);
  let result_wit = p_wit ~loc wenv z_ty in
  if z_ctx = [] then
    ( [%expr
        [%e src_ident ~loc [] "case_bool0"]
          ~result:[%e result_wit] ~scrutinee:[%e scrut'] ~zero:[%e zero']
          ~one_:[%e one']],
      scrut_ctx,
      TTensor (TQBool, z_ty) )
  else
    let uses, merged = route ~loc scrut_ctx z_ctx in
    ( [%expr
        [%e src_ident ~loc [] "case_bool"]
          ~result:[%e result_wit] ~scrutinee:[%e scrut'] ~zero:[%e zero']
          ~one_:[%e one'] ~using:[%e uses]],
      merged,
      TTensor (TQBool, z_ty) )

(* ------------------------------------------------------------------ *)
(* let%source binding assembly                                          *)
(* ------------------------------------------------------------------ *)

type param =
  | Witness of string * string * Location.t   (* ml name, type variable *)
  | Src of string * sty * Location.t

let is_p_t_path txt =
  match txt with
  | Ldot (Lident "P", "t")
  | Ldot (Ldot (Lident "Source", "P"), "t")
  | Ldot (Ldot (Ldot (Lident "Qpl_surface", "Source"), "P"), "t") -> true
  | _ -> false

let parse_param pat =
  let loc = pat.ppat_loc in
  match pat.ppat_desc with
  | Ppat_constraint ({ ppat_desc = Ppat_var { txt = name; _ }; _ }, ct) -> (
      match ct.ptyp_desc with
      | Ptyp_constr ({ txt; _ }, [ { ptyp_desc = Ptyp_var v; _ } ])
        when is_p_t_path txt ->
          Witness (name, v, loc)
      | _ -> Src (name, parse_ty ct, loc))
  | Ppat_var _ ->
      err ~loc
        "Source: every parameter needs a sealed-type annotation, for \
         example (p : (qbool, q) tensor) or a witness (a : 'a P.t)"
  | _ -> err ~loc "Source: unsupported parameter pattern"

let collect_params e =
  match e.pexp_desc with
  | Pexp_function (params, constr, Pfunction_body body) ->
      let parsed =
        List.map
          (fun p ->
            match p.pparam_desc with
            | Pparam_val (Nolabel, None, pat) -> parse_param pat
            | Pparam_val _ ->
                err ~loc:p.pparam_loc
                  "Source: parameters are plain annotated patterns without \
                   labels or defaults"
            | Pparam_newtype _ ->
                err ~loc:p.pparam_loc
                  "Source: newtype parameters are not part of the Source \
                   surface; use a witness parameter (a : 'a P.t)")
          params
      in
      let annotation =
        match constr with
        | Some (Pconstraint ct) -> Some (parse_ty ct)
        | Some (Pcoerce _) ->
            err ~loc:e.pexp_loc "Source: coercions are not Source syntax"
        | None -> None
      in
      parsed, annotation, body
  | Pexp_function (_, _, Pfunction_cases (_, loc, _)) ->
      err ~loc "Source: function-case syntax is not Source syntax"
  | _ -> [], None, e

let expand_source_binding ~loc (vb : value_binding) : structure_item =
  let name =
    match vb.pvb_pat.ppat_desc with
    | Ppat_var { txt; _ } -> txt
    | _ ->
        err ~loc:vb.pvb_pat.ppat_loc
          "Source: let%%source binds one value name"
  in
  let params, header_annotation, inner = collect_params vb.pvb_expr in
  let body, result_annotation =
    match inner.pexp_desc with
    | Pexp_constraint (b, ct) -> b, Some (parse_ty ct)
    | _ -> inner, header_annotation
  in
  (* witnesses lead; Source parameters follow *)
  let rec split_params seen_src = function
    | [] -> [], []
    | Witness (n, v, l) :: rest ->
        if seen_src then
          err ~loc:l
            "Source: witness parameters must precede the Source parameters";
        let ws, ss = split_params seen_src rest in
        (n, v, l) :: ws, ss
    | Src (n, t, l) :: rest ->
        let ws, ss = split_params true rest in
        ws, (n, t, l) :: ss
  in
  let witnesses, sources = split_params false params in
  let wenv = List.map (fun (n, v, _) -> v, n) witnesses in
  (* stamp parameters so the outermost lambda binder is outermost in the
     context order: inner binders receive higher stamps *)
  let stamped =
    List.map
      (fun (n, t, l) ->
        n, { stamp = fresh_stamp (); ml_name = n; bty = t; bloc = l })
      sources
  in
  let env = List.rev stamped in
  let body', body_ctx, body_ty = elab wenv env body in
  (match result_annotation with
  | Some annotated when not (sty_equal annotated body_ty) ->
      err ~loc
        "Source: the body has type %s but the binding is annotated %s"
        (sty_to_string body_ty) (sty_to_string annotated)
  | _ -> ());
  (* wrap the Source parameters in sealed lambdas, innermost first *)
  let wrapped, _final_ctx, _final_ty =
    List.fold_left
      (fun (acc_body, acc_ctx, acc_ty) (n, b) ->
        match acc_ctx with
        | head :: rest when head.stamp = b.stamp ->
            let pat = Ab.pvar ~loc:b.bloc n in
            let record =
              Ab.pexp_record ~loc
                [ ( { txt = lid_of_path src_mod "run_lam"; loc },
                    Ab.eabstract ~loc [ pat ] acc_body ) ]
                None
            in
            ( [%expr
                [%e src_ident ~loc [] "lam"]
                  ~name:[%e Ab.estring ~loc n]
                  [%e s_wit ~loc wenv b.bty]
                  [%e s_wit ~loc wenv acc_ty] [%e record]],
              rest,
              TLolli (b.bty, acc_ty) )
        | _ ->
            err ~loc:b.bloc
              "Source: parameter %s is never used; a linear parameter is \
               consumed exactly once"
              n)
      (body', body_ctx, body_ty)
      (List.rev stamped)
  in
  (match _final_ctx with
  | [] -> ()
  | b :: _ ->
      err ~loc:b.bloc "Source: internal error, %s escaped its scope"
        b.ml_name);
  let witness_pats =
    List.map
      (fun (n, v, l) ->
        Ab.ppat_constraint ~loc:l (Ab.pvar ~loc:l n)
          (Ab.ptyp_constr ~loc:l
             { txt = Ldot (Ldot (Ldot (Lident "Qpl_surface", "Source"),
                                 "P"), "t");
               loc = l }
             [ Ab.ptyp_var ~loc:l v ]))
      witnesses
  in
  let with_witnesses =
    match witness_pats with
    | [] -> wrapped
    | pats -> Ab.eabstract ~loc pats wrapped
  in
  Ab.pstr_value ~loc Nonrecursive
    [ Ab.value_binding ~loc ~pat:(Ab.pvar ~loc name) ~expr:with_witnesses ]

(* ------------------------------------------------------------------ *)
(* [@@source.datatype]                                                  *)
(* ------------------------------------------------------------------ *)

let has_datatype_attr (td : type_declaration) =
  List.exists
    (fun a -> String.equal a.attr_name.txt "source.datatype")
    td.ptype_attributes

let expand_datatype ~loc (td : type_declaration) : structure_item list =
  let name = td.ptype_name.txt in
  let constructors =
    match td.ptype_kind with
    | Ptype_variant cds when cds <> [] ->
        List.map
          (fun cd ->
            (match cd.pcd_args with
            | Pcstr_tuple [] -> ()
            | _ ->
                err ~loc:cd.pcd_loc
                  "Source: datatype constructors carry no arguments");
            cd.pcd_name.txt)
          cds
    | _ ->
        err ~loc
          "Source: [@@source.datatype] annotates a variant type with at \
           least one nullary constructor"
  in
  let module_name = String.capitalize_ascii name in
  let dt path = Ldot (Ldot (Ldot (Lident "Qpl_surface", "Source"),
                            "Datatype"), path) in
  let rec peano n =
    if n = 0 then Ab.ptyp_constr ~loc { txt = dt "zero"; loc } []
    else Ab.ptyp_constr ~loc { txt = dt "succ"; loc } [ peano (n - 1) ]
  in
  let rec vector = function
    | [] -> Ab.pexp_construct ~loc { txt = dt "VNil"; loc } None
    | label :: rest ->
        Ab.pexp_construct ~loc { txt = dt "VCons"; loc }
          (Some
             (Ab.pexp_tuple ~loc [ Ab.estring ~loc label; vector rest ]))
  in
  let spec =
    Ab.pmod_structure ~loc
      [
        Ab.pstr_type ~loc Recursive
          [
            Ab.type_declaration ~loc ~name:{ txt = "tail"; loc }
              ~params:[] ~cstrs:[] ~kind:Ptype_abstract ~private_:Public
              ~manifest:(Some (peano (List.length constructors - 1)));
          ];
        [%stri let name = [%e Ab.estring ~loc name]];
        [%stri let labels = [%e vector constructors]];
      ]
  in
  let make =
    Ab.pmod_apply ~loc
      (Ab.pmod_apply ~loc
         (Ab.pmod_ident ~loc { txt = dt "Make"; loc })
         spec)
      (Ab.pmod_structure ~loc [])
  in
  [
    Ab.pstr_module ~loc
      (Ab.module_binding ~loc
         ~name:{ txt = Some module_name; loc }
         ~expr:make);
    (let alias =
       Ab.type_declaration ~loc ~name:{ txt = name; loc } ~params:[]
         ~cstrs:[] ~kind:Ptype_abstract ~private_:Public
         ~manifest:
           (Some
              (Ab.ptyp_constr ~loc
                 { txt = Ldot (Lident module_name, "t"); loc }
                 []))
     in
     let alias =
       { alias with
         ptype_attributes =
           [ Ab.attribute ~loc ~name:{ txt = "warning"; loc }
               ~payload:(PStr [ Ab.pstr_eval ~loc
                                  (Ab.estring ~loc "-34") [] ]) ] }
     in
     Ab.pstr_type ~loc Recursive [ alias ]);
  ]

(* ------------------------------------------------------------------ *)
(* M.select ~target:_ [op1; ...; opN]  literal-list vectors             *)
(* ------------------------------------------------------------------ *)

let rec as_literal_list e =
  match e.pexp_desc with
  | Pexp_construct ({ txt = Lident "[]"; _ }, None) -> Some []
  | Pexp_construct
      ({ txt = Lident "::"; _ },
       Some { pexp_desc = Pexp_tuple [ head; tail ]; _ }) -> (
      match as_literal_list tail with
      | Some rest -> Some (head :: rest)
      | None -> None)
  | _ -> None

let select_mapper =
  object
    inherit Ast_traverse.map as super

    method! expression e =
      let e = super#expression e in
      match e.pexp_desc with
      | Pexp_apply
          (({ pexp_desc = Pexp_ident { txt = Ldot (_, "select"); _ }; _ } as
            fn),
           args) ->
          let loc = e.pexp_loc in
          let rewritten =
            List.map
              (fun (label, value) ->
                match label, as_literal_list value with
                | Nolabel, Some ops ->
                    let dt path =
                      Ldot (Ldot (Ldot (Lident "Qpl_surface", "Source"),
                                  "Datatype"), path)
                    in
                    let rec vec = function
                      | [] ->
                          Ab.pexp_construct ~loc { txt = dt "VNil"; loc }
                            None
                      | op :: rest ->
                          Ab.pexp_construct ~loc { txt = dt "VCons"; loc }
                            (Some (Ab.pexp_tuple ~loc [ op; vec rest ]))
                    in
                    label, vec ops
                | _ -> label, value)
              args
          in
          { e with pexp_desc = Pexp_apply (fn, rewritten) }
      | _ -> e
  end

(* ------------------------------------------------------------------ *)
(* Driver                                                               *)
(* ------------------------------------------------------------------ *)

let expand_item (item : structure_item) : structure_item list =
  match item.pstr_desc with
  | Pstr_extension
      (({ txt = "source"; _ },
        PStr [ { pstr_desc = Pstr_value (Nonrecursive, [ vb ]); _ } ]),
       _) ->
      [ expand_source_binding ~loc:item.pstr_loc vb ]
  | Pstr_extension (({ txt = "source"; loc }, _), _) ->
      err ~loc "Source: let%%source expects a single nonrecursive binding"
  | Pstr_type (rec_flag, tds)
    when List.exists has_datatype_attr tds -> (
      match tds with
      | [ td ] when has_datatype_attr td ->
          ignore rec_flag;
          expand_datatype ~loc:item.pstr_loc td
      | _ ->
          err ~loc:item.pstr_loc
            "Source: [@@source.datatype] annotates a single type \
             declaration")
  | _ -> [ item ]

let impl (str : structure) : structure =
  let expanded = List.concat_map expand_item str in
  select_mapper#structure expanded

let () = Driver.register_transformation ~impl "qpl_source"
