(** Abstract QSwitch — curried lambda form, show compiled circuit.

    qswitch : (Q⊸Q) ⊸ (Q⊸Q) ⊸ (Bool⊗Q ⊸ Bool⊗Q)
    qswitch = λf. λg. λbx.
      let (b, x) = bx in
      (dist_l ; plusmap(left, right) ; undist_l) (b, (f, (g, x)))

    left  : I⊗Γ → I⊗Q = let (tag, (f, (g, x))) = ... in (tag, f(g(x)))
    right : I⊗Γ → I⊗Q = let (tag, (f, (g, x))) = ... in (tag, g(f(x)))
*)

open Qpl_surface
open Linear

let () =
  let project_root = Filename.dirname (Sys.getcwd ()) in
  Bridge.set_project_root project_root;

  let qq = q -@ q in
  let bool_ty = one ++ one in
  let bq = bool_ty ** q in
  let gx_ty = qq ** q in
  let payload_ty = qq ** gx_ty in    (* (Q⊸Q) ⊗ ((Q⊸Q) ⊗ Q) *)
  let ip_ty = one ** payload_ty in   (* I ⊗ payload *)

  (* Left branch (b=0): CLOSED morphism I⊗Γ → I⊗Q, apply g then f *)
  let left_branch =
    oletpair0 "tag" "payload" one payload_ty (oid ip_ty)
      (oletpair "f" "gx" qq gx_ty (ovar "payload" payload_ty)
        (oletpair "g" "x" qq q (ovar "gx" gx_ty)
          (opair (ovar "tag" one)
                 (oapp (ovar "f" qq)
                       (oapp (ovar "g" qq)
                             (ovar "x" q)
                             (SLeft (SRight SNil)))
                       (SRight (SRight (SLeft SNil))))
                 (SRight (SRight (SRight (SLeft SNil)))))
          (SRight (SLeft (SRight SNil))))
        (SRight (SLeft SNil)))
  in
  (* Right branch (b=1): CLOSED morphism I⊗Γ → I⊗Q, apply f then g *)
  let right_branch =
    oletpair0 "tag" "payload" one payload_ty (oid ip_ty)
      (oletpair "f" "gx" qq gx_ty (ovar "payload" payload_ty)
        (oletpair "g" "x" qq q (ovar "gx" gx_ty)
          (opair (ovar "tag" one)
                 (oapp (ovar "g" qq)
                       (oapp (ovar "f" qq)
                             (ovar "x" q)
                             (SRight (SLeft SNil)))
                       (SLeft (SRight (SRight SNil))))
                 (SRight (SRight (SRight (SLeft SNil)))))
          (SRight (SLeft (SRight SNil))))
        (SRight (SLeft SNil)))
  in
  (* Pipeline: dist_l ; plusmap ; undist_l — all closed *)
  let pipeline =
    oseq0 (oembed (dist_l one one payload_ty))
      (oseq0 (oplusmap0 ip_ty ip_ty left_branch right_branch)
             (oembed (undist_l one one q)))
  in
  (* Curried abstract QSwitch.
     Inner body context after lambdas: [bx:bq, g:qq, f:qq]
     oletpair: bx→left (scrutinee), (g,f)→right
     After oletpair: [b:bool_ty, x:q, g:qq, f:qq]
     repaired pairs all variables; pipeline is closed. *)
  let qswitch =
    olam "f" qq (qq -@ (bq -@ bq))
      (olam "g" qq (bq -@ bq)
        (olam "bx" bq bq
          (oletpair "b" "x" bool_ty q (ovar "bx" bq)
            (oapp pipeline
              (opair (ovar "b" bool_ty)
                     (opair (ovar "f" qq)
                            (opair (ovar "g" qq)
                                   (ovar "x" q)
                                   (SRight (SLeft SNil)))
                            (SRight (SRight (SLeft SNil))))
                     (SLeft (SRight (SRight (SRight SNil)))))
              (SRight (SRight (SRight (SRight SNil)))))
            (SLeft (SRight (SRight SNil))))))
  in
  Printf.printf "Abstract QSwitch: (Q⊸Q) ⊸ (Q⊸Q) ⊸ (Bool⊗Q ⊸ Bool⊗Q)\n\n";
  Printf.printf "Circuit:\n";
  ignore (Bridge.compile_show (emit_oterm qswitch))
