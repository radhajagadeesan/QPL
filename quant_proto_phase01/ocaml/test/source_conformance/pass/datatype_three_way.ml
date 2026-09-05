open Qpl_surface

module Src = Source
module D = Src.Datatype

module Three_spec = struct
  type tail = D.n2
  let name = "Three"
  let labels = D.("A" @: "B" @: "C" @: VNil)
end

module Three = D.Make (Three_spec) ()

let branches =
  D.(Src.Op.id Src.q @: Src.Op.h @: Src.Op.x @: VNil)

let selector :
    ((Three.t, Src.q) Src.tensor, (Three.t, Src.q) Src.tensor) Src.op =
  Three.select ~target:Src.P.q branches

let same_instance :
    ((Three.t, Src.q) Src.tensor, (Three.t, Src.q) Src.tensor) Src.op =
  Three.select ~target:Src.P.q
    D.(Src.Op.s @: Src.Op.t @: Src.Op.z @: VNil)

let () =
  ignore Three.p;
  ignore Three.s;
  ignore Three.name;
  ignore Three.labels;
  ignore Three.arity;
  ignore selector;
  ignore same_instance
