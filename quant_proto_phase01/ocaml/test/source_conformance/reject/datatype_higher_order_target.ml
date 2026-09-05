open Qpl_surface
module Src = Source
module D = Src.Datatype

module Spec = struct
  type tail = D.n1
  let name = "Two"
  let labels = D.("A" @: "B" @: VNil)
end

module Two = D.Make (Spec) ()

let bad =
  Two.select
    ~target:(Src.S.lolli Src.q Src.q)
    D.(Src.Op.h @: Src.Op.s @: VNil)
