(* a permutation lists each constructor exactly once *)

open Qpl_surface.Source

type m3 = M0 | M1 | M2 [@@source.datatype]

let bad = M3.permute [ M1; M1; M0 ]

let _ = bad
