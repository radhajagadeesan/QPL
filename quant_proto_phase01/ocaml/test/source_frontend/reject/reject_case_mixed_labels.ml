(* The qbool branch labels and the sum branch labels cannot be mixed. *)

open Qpl_surface.Source

let%source bad (b : qbool) (y : q) =
  case b
    ~zero:(h y)
    ~right_:(z y)

let _ = bad
