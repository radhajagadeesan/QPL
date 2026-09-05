open Qpl_surface
module Src = Source

let bad :
    (Src.empty,
     (Src.q, (Src.q, Src.q) Src.lolli) Src.lolli) Src.term =
  Src.lam Src.q (Src.S.lolli Src.q Src.q)
    { Src.run_lam = fun _x -> Src.Op.value Src.Op.h }
