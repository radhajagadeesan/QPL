open Qpl_surface
module D = Source.Datatype

module Bad_spec : D.SPEC = struct
  type tail = D.zero
  let name = "Empty"
  let labels = D.VNil
end
