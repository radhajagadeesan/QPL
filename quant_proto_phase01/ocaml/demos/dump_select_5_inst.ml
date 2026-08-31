(** Dump the bridge JSON for select_5 instantiated with H, S, T, X, Y. *)
open Qpl_surface
open Linear

let qq_ty = q -@ q
let ia_ty = one ** q
let sum_3_ty = ia_ty ++ (ia_ty ++ ia_ty)
let _ = sum_3_ty
let sum_5_ty = ia_ty ++ (ia_ty ++ (ia_ty ++ (ia_ty ++ ia_ty)))

let h_value = olam "hx" q q (oapp (oembed gate_h) (ovar "hx" q) (SRight SNil))
let s_value = olam "sy" q q (oapp (oembed gate_s) (ovar "sy" q) (SRight SNil))
let t_value = olam "tz" q q (oapp (oembed gate_t) (ovar "tz" q) (SRight SNil))
let x_value = olam "xw" q q (oapp (oembed gate_x) (ovar "xw" q) (SRight SNil))
let y_value = olam "yw" q q (oapp (oembed gate_y) (ovar "yw" q) (SRight SNil))

let apply_f_branch f_name =
  oletpair "i" "a" one q (oid ia_ty)
    (opair (ovar "i" one)
           (oapp (ovar f_name qq_ty) (ovar "a" q) (SRight (SLeft SNil)))
           (SLeft (SRight (SRight SNil))))
    (SRight SNil)

let select_5_pm =
  let branches =
    BCons (ia_ty, apply_f_branch "g0",
    BCons (ia_ty, apply_f_branch "g1",
    BCons (ia_ty, apply_f_branch "g2",
    BCons (ia_ty, apply_f_branch "g3",
    BCons (ia_ty, apply_f_branch "g4", BNil))))) in
  let part5 =
    PCons (SLeft (SRight (SRight (SRight (SRight SNil)))),
    PCons (SLeft (SRight (SRight (SRight SNil))),
    PCons (SLeft (SRight (SRight SNil)),
    PCons (SLeft (SRight SNil),
    PLast))))
  in
  o_n_plusmap ia_ty branches part5

let abstract_select_5 =
  let input_ty5 = qq_ty ** (qq_ty ** (qq_ty ** (qq_ty ** (qq_ty ** sum_5_ty)))) in
  let body =
    oletpair "g0" "r1" qq_ty (qq_ty ** (qq_ty ** (qq_ty ** (qq_ty ** sum_5_ty))))
      (ovar "input" input_ty5)
      (oletpair "g1" "r2" qq_ty (qq_ty ** (qq_ty ** (qq_ty ** sum_5_ty)))
         (ovar "r1" (qq_ty ** (qq_ty ** (qq_ty ** (qq_ty ** sum_5_ty)))))
         (oletpair "g2" "r3" qq_ty (qq_ty ** (qq_ty ** sum_5_ty))
            (ovar "r2" (qq_ty ** (qq_ty ** (qq_ty ** sum_5_ty))))
            (oletpair "g3" "r4" qq_ty (qq_ty ** sum_5_ty)
               (ovar "r3" (qq_ty ** (qq_ty ** sum_5_ty)))
               (oletpair "g4" "s" qq_ty sum_5_ty
                  (ovar "r4" (qq_ty ** sum_5_ty))
                  (oapp select_5_pm (ovar "s" sum_5_ty)
                        (SLeft (SRight (SLeft (SLeft (SLeft (SLeft SNil)))))))
                  (SRight (SLeft (SRight (SRight (SRight SNil))))))
               (SRight (SLeft (SRight (SRight SNil)))))
            (SRight (SLeft (SRight SNil))))
         (SRight (SLeft SNil)))
      (SLeft SNil)
  in
  olam "input" input_ty5 sum_5_ty body

let () =
  let arg_5 = opair0 h_value
                (opair0 s_value
                   (opair0 t_value
                      (opair0 x_value
                         (opair0 y_value (oid sum_5_ty))))) in
  let applied_5 = Bridge.TApply (emit_oterm abstract_select_5, emit_oterm arg_5) in
  print_endline (Bridge.term_to_json applied_5)
