(* every arm consumes the same nominal linear context *)

open Qpl_surface.Source

type m3 = M0 | M1 | M2 [@@source.datatype]

let%source bad (d : M3.t) (u : q) (v : q) =
  match d with
  | M0 -> h u
  | M1 -> s u
  | M2 -> t v

let _ = bad
