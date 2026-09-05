(* a constructor of one nominal datatype cannot match another *)

open Qpl_surface.Source

type m3 = M0 | M1 | M2 [@@source.datatype]
type k3 = K0 | K1 | K2 [@@source.datatype]

let%source bad (d : M3.t) (y : q) =
  match d with
  | M0 -> h y
  | M1 -> s y
  | K2 -> t y

let _ = bad
