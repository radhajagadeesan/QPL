open Qpl_surface

module Src = Source

(** Signature-level coverage.  The sealed API intentionally exposes no
    closed first-order state constructor, so these arguments are postulated
    rather than fabricated through Raw or Obj.magic. *)
let binary
    (type g)
    (scrutinee : (g, (Src.q, Src.q) Src.plus) Src.term)
    (left_branch : (Src.empty, Src.q) Src.term)
    (right_branch : (Src.empty, Src.q) Src.term) =
  Src.case0
    ~left:Src.P.q
    ~right:Src.P.q
    ~result:Src.P.q
    ~scrutinee
    ~left_branch
    ~right_branch

let boolean
    (type g)
    (scrutinee : (g, Src.qbool) Src.term)
    (zero : (Src.empty, Src.q) Src.term)
    (one_ : (Src.empty, Src.q) Src.term) =
  Src.case_bool0 ~result:Src.P.q ~scrutinee ~zero ~one_
