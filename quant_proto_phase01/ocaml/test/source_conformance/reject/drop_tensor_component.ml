open Qpl_surface
module Src = Source

let qq = Src.S.tensor Src.q Src.q

let bad :
    (Src.empty, ((Src.q, Src.q) Src.tensor, Src.q) Src.lolli) Src.term =
  Src.lam qq Src.q
    { Src.run_lam =
        fun p ->
          Src.let_tensor Src.q Src.q (Src.use p)
            { Src.run_split = fun x _y -> Src.use x }
            (Src.UL Src.U0)
    }
