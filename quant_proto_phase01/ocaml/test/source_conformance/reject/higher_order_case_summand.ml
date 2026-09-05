open Qpl_surface
module Src = Source

let bad =
  Src.case
    ~left:(Src.S.lolli Src.q Src.q)
    ~right:Src.P.q
    ~result:Src.P.q
