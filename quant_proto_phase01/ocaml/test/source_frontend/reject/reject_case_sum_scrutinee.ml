(* E1: ~left_:/~right_: scrutinize a first-order sum, nothing else. *)

open Qpl_surface.Source

let%source bad (y : q) (w : q) =
  case y
    ~left_:(h w)
    ~right_:(z w)

let _ = bad
