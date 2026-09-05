open Qpl_surface

module Src = Source

let sum = Src.P.plus Src.P.q (Src.P.tensor Src.P.q Src.P.q)
let _ = Src.Op.twist_plus Src.P.q Src.P.qbool
let _ = Src.Op.assoc_plus_left Src.P.q Src.P.q Src.P.qbool
let _ = Src.Op.assoc_plus_right Src.P.q Src.P.q Src.P.qbool
let _ = Src.Op.dist_left Src.P.q Src.P.q Src.P.qbool
let _ = Src.Op.dist_right Src.P.q Src.P.q Src.P.qbool
let _ = Src.Op.undist_left Src.P.q Src.P.q Src.P.qbool
let _ = Src.Op.undist_right Src.P.q Src.P.q Src.P.qbool
let _ = Src.Op.phase Complex.one sum

let arrow = Src.S.lolli Src.q Src.q
let _ = Src.Op.twist arrow Src.q
let _ = Src.Op.assoc_left arrow Src.q Src.qbool

let _ = Src.Op.compose Src.Op.h Src.Op.s
let _ = Src.Op.tensor Src.Op.h Src.Op.not_bool

let xx =
  Src.Op.involution_tensor Src.Op.involution_x Src.Op.involution_x

let _ = Src.Op.exp_i (Float.pi /. 4.0) xx
let _ = Src.Op.involution_plus Src.Op.involution_h Src.Op.involution_x

let sealed =
  Src.Op.seal
    ~domain:Src.q
    ~codomain:Src.q
    (Src.lam Src.q Src.q
       { Src.run_lam = fun x -> Src.use x })

let () = ignore (Src.emit (Src.Op.value sealed))
