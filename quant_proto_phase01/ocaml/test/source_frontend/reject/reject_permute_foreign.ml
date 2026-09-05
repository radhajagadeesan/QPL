(* permutation entries belong to the permuted datatype *)

open Qpl_surface.Source

type m3 = M0 | M1 | M2 [@@source.datatype]
type k3 = K0 | K1 | K2 [@@source.datatype]

let bad = M3.permute [ M1; K1; M0 ]

let _ = bad
