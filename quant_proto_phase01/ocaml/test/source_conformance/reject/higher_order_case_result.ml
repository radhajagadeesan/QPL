open Qpl_surface
module Src = Source

let bad =
  Src.case
    ~left:Src.P.q
    ~right:Src.P.q
    ~result:(Src.S.lolli Src.q Src.q)
