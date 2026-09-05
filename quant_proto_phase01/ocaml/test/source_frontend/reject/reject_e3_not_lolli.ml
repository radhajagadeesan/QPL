(* E3: an annotation in function position must be a lolli. *)

open Qpl_surface.Source

let dl = Op.dist_left P.q P.q P.q

let%source bad (p : (((q, q) plus, q) tensor)) =
  (dl : ((q, q) tensor)) p

let _ = bad
