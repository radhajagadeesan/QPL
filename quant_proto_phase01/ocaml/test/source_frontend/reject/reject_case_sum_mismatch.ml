(* E1: the two sum-case branches must consume the same nominal context. *)

open Qpl_surface.Source

let%source bad (s : (q, q) plus) (u : q) (v : q) =
  case s
    ~left_:(h u)
    ~right_:(h v)

let _ = bad
