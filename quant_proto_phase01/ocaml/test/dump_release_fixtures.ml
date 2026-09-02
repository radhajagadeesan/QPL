(** Fixture generator for the Zenodo release-safety witnesses.

    Terms are DEFINED IN OCaml -- copied verbatim from the demos -- and
    serialized once, so the release gates exercise the terms the demos
    actually compile rather than convenient Python reconstructions. *)

open Qpl_surface
open Linear

(* ---- verbatim from demos/ctrl_ho_eta_e2e.ml ---- *)
let endo_ty     = q -@ q                       (* Q ⊸ Q *)
let _endo_op_ty = endo_ty -@ endo_ty           (* (Q⊸Q) ⊸ (Q⊸Q) *)

let hy_ty       = endo_ty ** q                 (* Endo ⊗ Q *)
let sum_in_ty   = one ** hy_ty                 (* I ⊗ (Endo ⊗ Q) — each summand of distL output *)
let _sum_out_ty = one ** q                     (* I ⊗ Q — each summand after u0/u1 *)

let banner s =
  print_endline "";
  print_endline (String.make 74 '=');
  Printf.printf "  %s\n" s;
  print_endline (String.make 74 '=')

(* ========================================================================= *)
(* u0 — closed branch. Doesn't use f.                                        *)
(* ========================================================================= *)
(*
   Type: (unit, one ** q) oterm  — a value-typed oterm producing (I ⊗ Q)
   from the summand input (I ⊗ (Endo ⊗ Q)) via oid + destructure + compute.

   Context progression:
     start (via oid sum_in_ty): [in_] where in_ : sum_in_ty
     after oletpair "t" "hy":    [t, hy]
     after oletpair "h" "y":     [h, y, t]
     inside opair: uses ovar t, and computes (h y) via oapp.
*)
(* u0 closed:
   - outer oletpair "t" "hy" pair source = oid sum_in_ty : (unit, sum_in_ty) oterm
     g1 = unit; body ctx t * (hy * g2); overall = g1 * g2 = g2 must = unit (closed)
     ⇒ g2 = unit, split = SNil
     ⇒ body ctx = [t, hy] = one * (hy_ty * unit)

   - inner oletpair "h" "y" pair source = ovar "hy" : (hy_ty*unit, hy_ty) oterm
     g1 = hy_ty*unit; body ctx = h * (y * g2); overall must = one * (hy_ty * unit)
     Split combines (hy_ty*unit) and g2 into (one*(hy_ty*unit)):
       SRight (SLeft SNil): (hy_ty*unit, one*unit, one*(hy_ty*unit)) ✓
     ⇒ g2 = one*unit = [t], body ctx = endo_ty * (q * (one * unit)) = [h, y, t]

   - opair (ovar "t" one) (h y) : overall ctx = [h, y, t] = endo*(q*(one*unit))
     fst = ovar t : g1_pair = one*unit
     snd = oapp h y : g2_pair = endo*(q*unit) = [h, y]
     Split places t at position 2: SRight (SRight (SLeft SNil))
       SNil : (unit, unit, unit)
       SLeft SNil : (one*unit, unit, one*unit)  ← t left
       SRight (SLeft SNil) : (one*unit, X*unit, X*(one*unit))
       SRight (SRight (SLeft SNil)) : (one*unit, Y*(X*unit), Y*(X*(one*unit)))
       g1 = one*unit ✓, g2 = Y*(X*unit), overall = Y*(X*(one*unit))
       Want overall = endo*(q*(one*unit)) ⇒ Y = endo, X = q
       g2 = endo*(q*unit) = [h, y] ✓

   - oapp (ovar h endo) (ovar y q) : overall ctx = endo*(q*unit) = [h, y]
     fn g1 = endo*unit; arg g2 = q*unit
     Split: SLeft (SRight SNil): (endo*unit, q*unit, endo*(q*unit)) ✓
*)
let u0 : (unit, [`Tensor of [`One] * [`Q]]) oterm =
  oletpair "t" "hy" one hy_ty (oid sum_in_ty)
    (oletpair "h" "y" endo_ty q (ovar "hy" hy_ty)
      (opair (ovar "t" one)
             (oapp (ovar "h" endo_ty) (ovar "y" q)
                   (SLeft (SRight SNil)))
             (SRight (SRight (SLeft SNil))))
      (SRight (SLeft SNil)))
    SNil

(* ========================================================================= *)
(* Split analysis of u0 (verify by hand)                                    *)
(* ========================================================================= *)
(*
   Outer oletpair "t" "hy" (pair source = oid sum_in_ty, closed):
     pair source g1 = sum_in_ty * unit
     body must produce (one ** q); body context = t * (hy * g2)
     overall context must be unit (u0 is closed)
     split combines (sum_in_ty * unit) and g2 into unit -- IMPOSSIBLE!

   Wait — oid sum_in_ty : (unit, sum_in_ty) oterm — its context is unit,
   not sum_in_ty * unit. So g1 = unit.

   Let me recheck: oid ty : (unit, ty) oterm. Its context is unit.
   Body must have context t * (hy * g2) and produce (one ** q).
   overall = g1 * g2 combined via split = unit combined with g2 = g2.
   For u0 closed, overall = unit, so g2 = unit.

   Split: SNil satisfies (unit, unit, unit). OK.

   Body context after outer letpair = one * (hy_ty * unit) = [t, hy].
*)

(* ========================================================================= *)
(* Given the split confusion, let me rewrite u0 more carefully               *)
(* ========================================================================= *)

(* ========================================================================= *)
(* u1 — open branch. Uses f from outer Granthi λ-context.                    *)
(* ========================================================================= *)
(*
   Type: (endo_op*unit, one ** q) oterm  — open, context = {f}

   Splits (derived carefully):

   - outer oletpair "t" "hy":
       pair source = oid sum_in_ty : (unit, ...) — g1 = unit
       overall for u1 = endo_op*unit (just {f})
       g2 = endo_op*unit ⇒ split = SRight SNil
       body ctx = one*(hy_ty*(endo_op*unit)) = [t, hy, f]

   - inner oletpair "h" "y":
       pair source = ovar "hy" hy_ty : (hy_ty*unit, hy_ty) — g1 = hy_ty*unit
       overall = one*(hy_ty*(endo_op*unit)) = [t, hy, f]
       split = SRight (SLeft (SRight SNil))
         builds : (hy_ty*unit, one*(endo_op*unit), one*(hy_ty*(endo_op*unit)))
       g2 = one*(endo_op*unit) = [t, f]
       body ctx = endo*(q*(one*(endo_op*unit))) = [h, y, t, f]

   - inner opair (ovar "t") (compute (f h) y):
       overall = [h, y, t, f] = endo*(q*(one*(endo_op*unit)))
       fst = ovar "t" : one*unit — g1_pair = [t]
       snd = (f h) y : must have g2_pair = [h, y, f] = endo*(q*(endo_op*unit))
       split = SRight (SRight (SLeft (SRight SNil)))
         builds : (one*unit, endo*(q*(endo_op*unit)), endo*(q*(one*(endo_op*unit))))

   - app_2 = oapp app_1 (ovar "y"):
       overall = endo*(q*(endo_op*unit)) = [h, y, f]
       fn = app_1 : g1_app2 must be endo*(endo_op*unit) = [h, f]
       arg = ovar "y" : q*unit — g2_app2 = [y]
       split = SLeft (SRight (SLeft SNil))
         builds : (endo*(endo_op*unit), q*unit, endo*(q*(endo_op*unit)))

   - app_1 = oapp (ovar "f") (ovar "h"):
       overall = endo*(endo_op*unit) = [h, f]
       fn = ovar "f" : endo_op*unit — g1_app1 = [f]
       arg = ovar "h" : endo*unit — g2_app1 = [h]
       split = SRight (SLeft SNil)
         builds : (endo_op*unit, endo*unit, endo*(endo_op*unit))
*)
let u1 : ([`Lolli of [`Lolli of [`Q] * [`Q]] * [`Lolli of [`Q] * [`Q]]] * unit,
          [`Tensor of [`One] * [`Q]]) oterm =
  oletpair "t" "hy" one hy_ty (oid sum_in_ty)
    (oletpair "h" "y" endo_ty q (ovar "hy" hy_ty)
      (opair (ovar "t" one)
             (oapp
                (oapp (ovar "f" _endo_op_ty) (ovar "h" endo_ty)
                      (SRight (SLeft SNil)))
                (ovar "y" q)
                (SLeft (SRight (SLeft SNil))))
             (SRight (SRight (SLeft (SRight SNil)))))
      (SRight (SLeft (SRight SNil))))
    (SRight SNil)

(* ========================================================================= *)
(* Main                                                                       *)
(* ========================================================================= *)

(* ========================================================================= *)
(* plus_map — the raw open split-context ⊕-map combining u0 and u1.          *)
(* ========================================================================= *)
(*
   oplusmap takes 'a ty (left summand of input sum), 'b ty (right summand),
   two branches, and a split combining their contexts.

   u0 : (unit, one ** q) oterm — g1 = unit
   u1 : (endo_op * unit, one ** q) oterm — g2 = endo_op * unit

   Split: SRight SNil : (unit, endo_op*unit, endo_op*unit). Combined ctx = {f}.

   Input summand types for oplusmap: sum_in_ty (each summand of the distL
   output). Result Lolli-typed oterm: Lolli(Plus(sum_in_ty, sum_in_ty),
   Plus(one⊗q, one⊗q)), context {f}.

   TARGETS = Plus(one⊗q, one⊗q) — FIRST-ORDER (no Lolli in summands).
   SOURCES = Plus(sum_in_ty, sum_in_ty) where sum_in_ty = one ⊗ (endo ⊗ q)
             — contains Lolli via endo. HIGHER-ORDER.

   Guard 2 target-only: TARGET is first-order → PASSES.
   If Guard 2 accidentally checked sources, this would REJECT.
*)
let plus_map =
  oplusmap sum_in_ty sum_in_ty u0 u1 (SRight SNil)


let ctrl_ho_closed_plus_map =
  let plus_map_cod =
    let inp = sum_in_ty ++ sum_in_ty in
    let outp = (one ** q) ++ (one ** q) in
    inp -@ outp
  in
  olam "f" _endo_op_ty plus_map_cod plus_map

(* ---- verbatim from demos/qswitch_eta_endoQ_e2e.ml ---- *)
let bool_ty     = one ++ one
let endo_ty     = q -@ q                       (* Q ⊸ Q *)
let endo_op_ty  = endo_ty -@ endo_ty           (* (Q ⊸ Q) ⊸ (Q ⊸ Q) *)

let hx_ty       = endo_ty ** q                 (* Endo ⊗ Q *)
let ghx_ty      = endo_op_ty ** hx_ty          (* EndoOp ⊗ (Endo ⊗ Q) *)
let payload_ty  = endo_op_ty ** ghx_ty         (* Γ = EndoOp ⊗ (EndoOp ⊗ (Endo ⊗ Q)) *)
let gi_ty       = payload_ty ** one            (* Γ ⊗ I (branch input after dist_r) *)
let input_ty    = bool_ty ** payload_ty        (* Bool ⊗ Γ *)
let bq_ty       = bool_ty ** q                 (* output: Bool ⊗ Q *)

(* ========================================================================= *)
(* qswitch_η for A = Q ⊸ Q                                                    *)
(* ========================================================================= *)

let qswitch_eta_endoQ : (unit, [`Lolli of _ * _]) oterm =

  (* Rearrange Bool ⊗ Γ  →  Γ ⊗ Bool  for case_hom's G ⊗ (A+B) shape *)
  let rearrange = twist_tensor bool_ty payload_ty in

  (* Context arithmetic (both branches share the same destructuring pattern):

     After outermost oletpair0 (payload, tag):
       body context = [payload, tag]                (payload*(one*unit))

     After oletpair (f, ghx) with split SLeft(SRight SNil)
                                       [payload→L,   tag→R]:
       body context = [f, ghx, tag]                (endo_op*(ghx*(one*unit)))

     After oletpair (g, hx) with split SRight(SLeft(SRight SNil))
                                       [ghx→L,  f→R,   tag→R]:
       body context = [g, hx, f, tag]              (endo_op*(hx*(endo_op*(one*unit))))

     After oletpair (h, x) with split SRight(SLeft(SRight(SRight SNil)))
                                       [hx→L, g→R, f→R, tag→R]:
       body context = [h, x, g, f, tag]            (endo*(q*(endo_op*(endo_op*(one*unit)))))

     Now compose (g (f h)) x or (f (g h)) x using vars [h, x, g, f]; pair with tag.

     opair split places tag at the end:
       SRight (SRight (SRight (SRight (SLeft SNil))))
       [tag→L,  h→R, x→R, g→R, f→R]  →  combined h*(x*(g*(f*(one*unit)))) ✓
  *)

  (* Left branch (b = inl, "0-tag"): compute (g (f h)) x  :  Q. *)
  let left_branch =
    oletpair0 "payload" "tag" payload_ty one (oid gi_ty)
      (oletpair "f" "ghx" endo_op_ty ghx_ty (ovar "payload" payload_ty)
        (oletpair "g" "hx" endo_op_ty hx_ty (ovar "ghx" ghx_ty)
          (oletpair "h" "x" endo_ty q (ovar "hx" hx_ty)
            (opair (ovar "tag" one)
                   (* (g (f h)) x  with vars [h, x, g, f] in context.
                      Build innermost outward. *)
                   (oapp
                      (* app_2 = g (f h) with context h*(g*(f*unit)) *)
                      (oapp (ovar "g" endo_op_ty)
                            (* app_1 = f h with context h*(f*unit) *)
                            (oapp (ovar "f" endo_op_ty)
                                  (ovar "h" endo_ty)
                                  (SRight (SLeft SNil)))
                                  (* f→L, h→R; combined = h*(f*unit) *)
                            (SRight (SLeft (SRight SNil))))
                            (* g→L, (h,f)→R; combined = h*(g*(f*unit)) *)
                      (ovar "x" q)
                      (SLeft (SRight (SLeft (SLeft SNil)))))
                      (* (h,g,f)→L, x→R inserted between h and g;
                         combined = h*(x*(g*(f*unit))) *)
                   (SRight (SRight (SRight (SRight (SLeft SNil))))))
                   (* tag→L, (h,x,g,f)→R;
                      combined = h*(x*(g*(f*(one*unit)))) *)
            (SRight (SLeft (SRight (SRight SNil)))))
          (SRight (SLeft (SRight SNil))))
        (SLeft (SRight SNil)))
  in

  (* Right branch (b = inr, "1-tag"): compute (f (g h)) x  :  Q. Same split
     scaffolding as left; only the inner apps swap f ↔ g. *)
  let right_branch =
    oletpair0 "payload" "tag" payload_ty one (oid gi_ty)
      (oletpair "f" "ghx" endo_op_ty ghx_ty (ovar "payload" payload_ty)
        (oletpair "g" "hx" endo_op_ty hx_ty (ovar "ghx" ghx_ty)
          (oletpair "h" "x" endo_ty q (ovar "hx" hx_ty)
            (opair (ovar "tag" one)
                   (oapp
                      (oapp (ovar "f" endo_op_ty)
                            (oapp (ovar "g" endo_op_ty)
                                  (ovar "h" endo_ty)
                                  (SRight (SLeft SNil)))
                            (SRight (SLeft (SRight SNil))))
                      (ovar "x" q)
                      (SLeft (SRight (SLeft (SLeft SNil)))))
                   (SRight (SRight (SRight (SRight (SLeft SNil))))))
            (SRight (SLeft (SRight (SRight SNil)))))
          (SRight (SLeft (SRight SNil))))
        (SLeft (SRight SNil)))
  in

  (* Pipeline: rearrange (Bool⊗Γ → Γ⊗Bool), then case_hom. Both closed. *)
  let pipeline =
    oseq0 (oembed rearrange)
          (ocase_hom one one payload_ty q left_branch right_branch)
  in

  (* Outer λ: consumes the packaged input tuple Bool⊗Γ, applies pipeline. *)
  olam "input" input_ty bq_ty
    (oapp pipeline (ovar "input" input_ty) (SRight SNil))

(* ========================================================================= *)
(* Demo + sanity                                                              *)
(* ========================================================================= *)

let n_pass = ref 0
let n_fail = ref 0



(* ---- verbatim from demos/curried_select_3_e2e.ml ---- *)
let qq_ty = q -@ q
let ia_ty = one ** q                    (* I ⊗ Q (one branch input) *)
let bool_ty = one ++ one                (* I + I *)
let z3_ty = one ++ (one ++ one)         (* I + (I + I) = Z_3 *)
let z3a_ty = z3_ty ** q                 (* Z_3 ⊗ Q *)
let bi_a_ty = bool_ty ** q              (* (I+I) ⊗ Q (intermediate after outer dist) *)
let _sum_3_ty = ia_ty ++ (ia_ty ++ ia_ty)
let inner_sum_ty = ia_ty ++ ia_ty       (* (I⊗Q) + (I⊗Q) *)

(* Function values *)
let h_value = olam "hx" q q (oapp (oembed gate_h) (ovar "hx" q) (SRight SNil))
let s_value = olam "sy" q q (oapp (oembed gate_s) (ovar "sy" q) (SRight SNil))
let t_value = olam "tz" q q (oapp (oembed gate_t) (ovar "tz" q) (SRight SNil))

(** dist_3 : Z_3 ⊗ Q ⊸ sum_3.
    Decomposed as outer dist_l, then omap(id, inner dist_l) on the right summand. *)
let dist_3 =
  let outer = dist_l one (one ++ one) q in
  (* After outer dist_l: Plus(I⊗Q, (I+I)⊗Q) *)
  let inner = dist_l one one q in
  (* inner : (I+I)⊗Q ⊸ Plus(I⊗Q, I⊗Q) *)
  let inner_map = omap0 ia_ty bi_a_ty (id ia_ty) inner in
  (* inner_map : Plus(I⊗Q, (I+I)⊗Q) ⊸ Plus(I⊗Q, Plus(I⊗Q, I⊗Q)) *)
  seq0 outer inner_map

(** factor_3 : sum_3 ⊸ Z_3 ⊗ Q. Inverse of dist_3. *)
let factor_3 =
  let inner = undist_l one one q in
  let inner_map = omap0 ia_ty inner_sum_ty (id ia_ty) inner in
  let outer = undist_l one (one ++ one) q in
  seq0 inner_map outer

(** Branch i : receive I⊗Q via oid, apply f_i (named var), repackage.
    Each branch is typed at its own one-slot context holding just f_i. *)
let apply_f_branch f_name =
  oletpair "i" "a" one q (oid ia_ty)
    (opair (ovar "i" one)
           (oapp (ovar f_name qq_ty) (ovar "a" q) (SRight (SLeft SNil)))
           (SLeft (SRight (SRight SNil))))
    (SRight SNil)

(** The n-ary plusmap: ⊕_{i=0}^{2}(id_b ⊗ f_i). Uses o_n_plusmap.
    Each branch is typed at its own one-slot context; the partition witness
    covers the 3-slot conclusion context exactly. *)
let nary_plusmap_3 =
  let branches =
    BCons (ia_ty, apply_f_branch "f0",
    BCons (ia_ty, apply_f_branch "f1",
    BCons (ia_ty, apply_f_branch "f2", BNil))) in
  let part3 =
    PCons (SLeft (SRight (SRight SNil)),
    PCons (SLeft (SRight SNil),
    PLast))
  in
  o_n_plusmap ia_ty branches part3

(** Fully curried select_3: λf_0. λf_1. λf_2. λp. factor_3(plusmap(dist_3(p))).

    Body context inside innermost lambda: [p, f_2, f_1, f_0]. *)
let abstract_select_3 =
  let body =
    (* Build the morphism pipeline: dist_3 ; nary_plusmap_3 ; factor_3.
       Apply it to p. *)
    let pipeline =
      let dist = oembed dist_3 in     (* closed *)
      let factor = oembed factor_3 in  (* closed *)
      let dist_then_pm =
        oseq dist nary_plusmap_3 (SRight (SRight (SRight SNil)))
        (* dist context unit; pm context [f_2, f_1, f_0]. combined = [f_2, f_1, f_0].
           split = all SRight (3 vars → right). *)
      in
      oseq dist_then_pm factor (SLeft (SLeft (SLeft SNil)))
      (* dist_then_pm context [f_2, f_1, f_0]; factor unit.
         split = all SLeft. *)
    in
    (* Apply pipeline to p. pipeline ctx [f_2, f_1, f_0]; p ctx [p].
       Combined inner-body context = [p, f_2, f_1, f_0].
       Split: p → arg (R), f_2 → func (L), f_1 → func (L), f_0 → func (L). *)
    oapp pipeline (ovar "p" z3a_ty) (SRight (SLeft (SLeft (SLeft SNil))))
  in
  olam "f0" qq_ty (qq_ty -@ (qq_ty -@ (z3a_ty -@ z3a_ty)))
    (olam "f1" qq_ty (qq_ty -@ (z3a_ty -@ z3a_ty))
       (olam "f2" qq_ty (z3a_ty -@ z3a_ty)
          (olam "p" z3a_ty z3a_ty body)))




let dump path json =
  let oc = open_out path in
  output_string oc json; close_out oc;
  Printf.printf "wrote %s (%d bytes)\n" path (String.length json)

let () =
  let dir = "../python/tests/fixtures" in
  dump (Filename.concat dir "ctrl_ho_closed_plus_map.json")
    (Bridge.term_to_json (emit_oterm ctrl_ho_closed_plus_map));
  dump (Filename.concat dir "qswitch_eta_endoQ.json")
    (Bridge.term_to_json (emit_oterm qswitch_eta_endoQ));
  let abs_t = emit_oterm abstract_select_3 in
  dump (Filename.concat dir "curried_select_3_applied_hst.json")
    (Bridge.term_to_json
       (Bridge.TApply
          (Bridge.TApply
             (Bridge.TApply (abs_t, emit_oterm h_value), emit_oterm s_value),
           emit_oterm t_value)))
