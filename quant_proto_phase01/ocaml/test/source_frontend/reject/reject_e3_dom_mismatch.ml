(* E3: the annotated domain must match the argument's type, checked at
   the argument's own location. *)

open Qpl_surface.Source

let dl = Op.dist_left P.q P.q P.q

let%source bad (y : q) =
  (dl : ((((q, q) plus, q) tensor,
          ((q, q) tensor, (q, q) tensor) plus) lolli)) y

let _ = bad
