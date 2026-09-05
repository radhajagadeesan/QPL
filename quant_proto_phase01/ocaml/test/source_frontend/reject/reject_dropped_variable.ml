(* A split binder that is never consumed must be rejected at the binder's
   own location. *)

open Qpl_surface.Source

let%source bad (p : (q, q) tensor) =
  let (l, r) = split p in
  h l

let _ = bad
