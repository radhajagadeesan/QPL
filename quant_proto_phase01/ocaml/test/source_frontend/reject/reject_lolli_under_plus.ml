(* The first-order sum restriction: no function space beneath plus. *)

open Qpl_surface.Source

let%source bad (p : ((q, q) lolli, q) plus) = p

let _ = bad
