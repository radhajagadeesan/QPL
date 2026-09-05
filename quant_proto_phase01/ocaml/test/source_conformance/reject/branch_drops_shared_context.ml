open Qpl_surface
module Src = Source

let bad
    (type scrut_id shared_id)
    (scrutinee :
       ((scrut_id, Src.qbool, Src.empty) Src.cons, Src.qbool) Src.term)
    (left_branch :
       ((shared_id, Src.q, Src.empty) Src.cons, Src.q) Src.term)
    (right_branch : (Src.empty, Src.q) Src.term) =
  Src.case_bool
    ~result:Src.P.q
    ~scrutinee
    ~zero:left_branch
    ~one_:right_branch
    ~using:(Src.UL (Src.UR Src.U0))
