(* A selector literal list must supply exactly one operation per label:
   three labels demand three operations, two are a type error against the
   length-indexed vector. *)

open Qpl_surface.Source

type z3 = A0 | A1 | A2 [@@source.datatype]

let bad = Z3.select ~target:P.q [ Op.h; Op.s ]

let _ = bad
