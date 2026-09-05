open Qpl_surface
module Src = Source

(** This is the forbidden [a | b] shape: the two alternatives have the
    same logical type but are supported by distinct nominal resources. *)
let bad
    (type tag_id a_id b_id)
    (tag :
       ((tag_id, Src.qbool, Src.empty) Src.cons, Src.qbool) Src.term)
    (a :
       ((a_id, Src.qbool, Src.empty) Src.cons, Src.qbool) Src.term)
    (b :
       ((b_id, Src.qbool, Src.empty) Src.cons, Src.qbool) Src.term) =
  Src.case_bool
    ~result:Src.P.qbool
    ~scrutinee:tag
    ~zero:a
    ~one_:b
    ~using:(Src.UL (Src.UR Src.U0))
