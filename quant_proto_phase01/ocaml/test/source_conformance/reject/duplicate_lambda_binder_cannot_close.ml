open Qpl_surface
module Src = Source

let bad :
    (Src.empty,
     (Src.q, (Src.q, Src.q) Src.tensor) Src.lolli) Src.term =
  Src.lam Src.q (Src.S.tensor Src.q Src.q)
    { Src.run_lam =
        fun x ->
          Src.pair
            (Src.use x)
            (Src.use x)
            (Src.UL (Src.UR Src.U0))
    }
