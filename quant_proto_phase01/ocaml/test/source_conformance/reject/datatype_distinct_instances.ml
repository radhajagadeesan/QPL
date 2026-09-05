open Qpl_surface
module Src = Source
module D = Src.Datatype

module Spec = struct
  type tail = D.n1
  let name = "SameSpelling"
  let labels = D.("A" @: "B" @: VNil)
end

module First = D.Make (Spec) ()
module Second = D.Make (Spec) ()

let branches = D.(Src.Op.h @: Src.Op.s @: VNil)

let bad :
    ((First.t, Src.q) Src.tensor, (First.t, Src.q) Src.tensor) Src.op =
  Second.select ~target:Src.P.q branches
