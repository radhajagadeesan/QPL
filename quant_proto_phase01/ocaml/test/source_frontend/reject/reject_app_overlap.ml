(* Function and argument positions of an application must consume disjoint
   contexts: f cannot appear on both sides of  f (f x). *)

open Qpl_surface.Source

let%source bad (f : (q, q) lolli) (x : q) =
  f (f x)

let _ = bad
