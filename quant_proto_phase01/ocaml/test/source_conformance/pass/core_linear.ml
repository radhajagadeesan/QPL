open Qpl_surface

module Src = Source

let qq = Src.S.tensor Src.q Src.q

let id_q : (Src.empty, (Src.q, Src.q) Src.lolli) Src.term =
  Src.lam Src.q Src.q
    { Src.run_lam = fun x -> Src.use x }

let applied_h : (Src.empty, (Src.q, Src.q) Src.lolli) Src.term =
  Src.lam Src.q Src.q
    { Src.run_lam =
        fun x ->
          Src.app
            (Src.Op.value Src.Op.h)
            (Src.use x)
            (Src.UR Src.U0)
    }

let curried_pair :
    (Src.empty,
     (Src.q, (Src.q, (Src.q, Src.q) Src.tensor) Src.lolli) Src.lolli)
      Src.term =
  Src.lam Src.q (Src.S.lolli Src.q qq)
    { Src.run_lam =
        fun x ->
          Src.lam Src.q qq
            { Src.run_lam =
                fun y ->
                  Src.pair
                    (Src.use x)
                    (Src.use y)
                    (Src.UR (Src.UL Src.U0))
            }
    }

let tensor_swap :
    (Src.empty,
     ((Src.q, Src.q) Src.tensor, (Src.q, Src.q) Src.tensor) Src.lolli)
      Src.term =
  Src.lam qq qq
    { Src.run_lam =
        fun p ->
          Src.let_pair Src.q Src.q (Src.use p)
            { Src.run_split =
                fun x y ->
                  Src.pair
                    (Src.use y)
                    (Src.use x)
                    (Src.UR (Src.UL Src.U0))
            }
            (Src.UL Src.U0)
    }

let hs : (Src.empty, (Src.q, Src.q) Src.lolli) Src.term =
  Src.seq (Src.Op.value Src.Op.h) (Src.Op.value Src.Op.s) Src.U0

let () =
  ignore (Src.emit id_q);
  ignore (Src.emit applied_h);
  ignore (Src.emit curried_pair);
  ignore (Src.emit tensor_swap);
  ignore (Src.emit hs)
