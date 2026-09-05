(* The two case branches must consume the same nominal linear context. *)

open Qpl_surface.Source

let%source bad (b : qbool) (u : q) (v : q) =
  case b
    ~zero:(h u)
    ~one_:(h v)

let _ = bad
