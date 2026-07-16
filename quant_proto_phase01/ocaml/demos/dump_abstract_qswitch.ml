(** Dump the abstract QSwitch's Bridge JSON for external verification. *)
open Qpl_surface
open Linear

let bool_ty = one ++ one
let qq_ty = q -@ q
let bq_ty = bool_ty ** q
let input_ty = qq_ty ** (qq_ty ** bq_ty)

let abstract_qswitch : (unit, [`Lolli of _ * _]) oterm =
  let gx_ty = qq_ty ** q in
  let payload_ty = qq_ty ** gx_ty in
  let gi_ty = payload_ty ** one in
  let rearrange =
    let swap_inner =
      seq0 (assoc_tensor_r qq_ty bool_ty q)
        (seq0 (par0 (twist_tensor qq_ty bool_ty) (id q))
              (assoc_tensor_l bool_ty qq_ty q)) in
    let step1 = par0 (id qq_ty) swap_inner in
    let swap_outer =
      seq0 (assoc_tensor_r qq_ty bool_ty gx_ty)
        (seq0 (par0 (twist_tensor qq_ty bool_ty) (id gx_ty))
              (assoc_tensor_l bool_ty qq_ty gx_ty)) in
    seq0 step1 swap_outer
  in
  let left_branch =
    oletpair0 "payload" "tag" payload_ty one (oid gi_ty)
      (oletpair "f" "gx" qq_ty gx_ty (ovar "payload" payload_ty)
        (oletpair "g" "x" qq_ty q (ovar "gx" gx_ty)
          (opair (ovar "tag" one)
                 (oapp (ovar "f" qq_ty)
                       (oapp (ovar "g" qq_ty) (ovar "x" q) (SLeft (SRight SNil)))
                       (SRight (SRight (SLeft SNil))))
                 (SRight (SRight (SRight (SLeft SNil)))))
          (SRight (SLeft (SRight SNil))))
        (SLeft (SRight SNil)))
  in
  let right_branch =
    oletpair0 "payload" "tag" payload_ty one (oid gi_ty)
      (oletpair "f" "gx" qq_ty gx_ty (ovar "payload" payload_ty)
        (oletpair "g" "x" qq_ty q (ovar "gx" gx_ty)
          (opair (ovar "tag" one)
                 (oapp (ovar "g" qq_ty)
                       (oapp (ovar "f" qq_ty) (ovar "x" q) (SRight (SLeft SNil)))
                       (SLeft (SRight (SRight SNil))))
                 (SRight (SRight (SRight (SLeft SNil)))))
          (SRight (SLeft (SRight SNil))))
        (SLeft (SRight SNil)))
  in
  let pipeline =
    oseq0 (oembed (seq0 rearrange (twist_tensor bool_ty payload_ty)))
          (ocase_hom one one payload_ty q left_branch right_branch)
  in
  olam "input" input_ty bq_ty
    (oapp pipeline (ovar "input" input_ty) (SRight SNil))

let () =
  let json = Bridge.term_to_json (emit_oterm abstract_qswitch) in
  print_endline json
