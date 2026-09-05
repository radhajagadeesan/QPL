open Qpl_surface
module D = Source.Datatype

module Bad_spec : D.SPEC = struct
  type tail = D.n2
  let name = "BadArity"
  let labels = D.("A" @: "B" @: VNil)
end
