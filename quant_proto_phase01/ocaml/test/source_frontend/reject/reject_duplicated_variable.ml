(* A variable consumed by both components of a pair must be rejected. *)

open Qpl_surface.Source

let%source bad (x : q) =
  (h x, s x)

let _ = bad
