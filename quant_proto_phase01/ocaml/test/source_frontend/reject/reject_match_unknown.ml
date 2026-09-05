(* arms name constructors of the scrutinee's datatype *)

open Qpl_surface.Source

type m3 = M0 | M1 | M2 [@@source.datatype]

let%source bad (d : M3.t) (y : q) =
  match d with
  | M0 -> h y
  | M1 -> s y
  | Q7 -> t y

let _ = bad
