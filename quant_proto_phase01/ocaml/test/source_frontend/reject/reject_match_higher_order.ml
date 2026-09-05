(* a match result must be first-order data *)

open Qpl_surface.Source

type m3 = M0 | M1 | M2 [@@source.datatype]

let%source bad (d : M3.t) (f : (q, q) lolli) =
  match d with
  | M0 -> f
  | M1 -> f
  | M2 -> f

let _ = bad
