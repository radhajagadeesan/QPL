open Qpl_surface

module Src = Source

let qq_arrow = Src.S.lolli Src.q Src.q
let result = Src.S.tensor Src.qbool Src.q

let apply_shared f x post =
  Src.Op.apply post
    (Src.app
       (Src.use f)
       (Src.use x)
       (Src.UR (Src.UL Src.U0)))

let select :
    (Src.empty,
     (Src.qbool,
      ((Src.q, Src.q) Src.lolli,
       (Src.q, (Src.qbool, Src.q) Src.tensor) Src.lolli)
        Src.lolli)
       Src.lolli)
      Src.term =
  Src.lam Src.qbool
    (Src.S.lolli qq_arrow (Src.S.lolli Src.q result))
    { Src.run_lam =
        fun b ->
          Src.lam qq_arrow (Src.S.lolli Src.q result)
            { Src.run_lam =
                fun f ->
                  Src.lam Src.q result
                    { Src.run_lam =
                        fun x ->
                          Src.case_bool
                            ~result:Src.P.q
                            ~scrutinee:(Src.use b)
                            ~zero:(apply_shared f x Src.Op.h)
                            ~one_:(apply_shared f x Src.Op.s)
                            ~using:
                              (Src.UR (Src.UR (Src.UL Src.U0)))
                    }
            }
    }

let () = ignore (Src.emit select)
