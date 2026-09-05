open Qpl_surface

module Src = Source

(** Direct binary case requires a nonempty, identical nominal context. *)
let direct
    (type scrut_id shared_id)
    (scrutinee :
       ((scrut_id, (Src.q, Src.q) Src.plus, Src.empty) Src.cons,
        (Src.q, Src.q) Src.plus)
         Src.term)
    (left_branch :
       ((shared_id, Src.q, Src.empty) Src.cons, Src.q) Src.term)
    (right_branch :
       ((shared_id, Src.q, Src.empty) Src.cons, Src.q) Src.term) =
  Src.case
    ~left:Src.P.q
    ~right:Src.P.q
    ~result:Src.P.q
    ~scrutinee
    ~left_branch
    ~right_branch
    ~using:(Src.UL (Src.UR Src.U0))
