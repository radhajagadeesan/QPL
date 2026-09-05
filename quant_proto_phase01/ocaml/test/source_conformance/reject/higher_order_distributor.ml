open Qpl_surface
module Src = Source

let bad =
  Src.Op.dist_left
    Src.P.q
    (Src.S.lolli Src.q Src.q)
    Src.P.q
