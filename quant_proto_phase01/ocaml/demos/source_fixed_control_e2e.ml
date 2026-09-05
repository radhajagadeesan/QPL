open Qpl_surface
open Source

let controlled_qubit = S.tensor qbool q

let program =
  lam ~name:"input" controlled_qubit controlled_qubit
    { run_lam =
        fun input ->
          let_tensor ~left_name:"control" ~right_name:"target"
            qbool q (use input)
            { run_split =
                fun control target ->
                  case_bool ~result:P.q
                    ~scrutinee:(use control)
                    ~zero:(Op.apply Op.h (use target))
                    ~one_:(Op.apply Op.s (use target))
                    ~using:(UL (UR U0)) }
            (UL U0) }

let () =
  match Bridge.compile_show (emit program) with
  | Bridge.CompileOk (permutation, gates) ->
      Printf.printf
        "Source fixed control: OK gates=%d wires=%d\n"
        gates permutation.n
  | Bridge.CompileError error ->
      Printf.eprintf "Source fixed control: FAIL: %s\n" error;
      exit 1
