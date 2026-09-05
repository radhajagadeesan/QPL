open Qpl_surface

module Src = Source

let result = Src.S.tensor Src.qbool Src.q

let select :
    (Src.empty,
     (Src.qbool, (Src.q, (Src.qbool, Src.q) Src.tensor) Src.lolli)
       Src.lolli)
      Src.term =
  Src.lam Src.qbool (Src.S.lolli Src.q result)
    { Src.run_lam =
        fun b ->
          Src.lam Src.q result
            { Src.run_lam =
                fun x ->
                  Src.case_bool
                    ~result:Src.P.q
                    ~scrutinee:(Src.use b)
                    ~zero:(Src.Op.apply Src.Op.h (Src.use x))
                    ~one_:(Src.Op.apply Src.Op.s (Src.use x))
                    ~using:(Src.UR (Src.UL Src.U0))
            }
    }

let () = ignore (Src.emit select)
