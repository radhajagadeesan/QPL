open Qpl_surface
module Src = Source
module D = Src.Datatype

module Spec = struct
  type tail = D.n2
  let name = "Three"
  let labels = D.("A" @: "B" @: "C" @: VNil)
end

module Three = D.Make (Spec) ()

let bad =
  Three.select ~target:Src.P.q
    D.(Src.Op.h @: Src.Op.s @: VNil)
