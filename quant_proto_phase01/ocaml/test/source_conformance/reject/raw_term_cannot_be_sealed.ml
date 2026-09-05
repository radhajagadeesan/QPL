open Qpl_surface
module Src = Source

let bad =
  Src.Op.seal
    ~domain:Src.q
    ~codomain:Src.q
    (Bridge.TId (Rep.var 0))
