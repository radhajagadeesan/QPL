open Qpl_surface
open Source

let two_qubits = S.tensor q q

let program =
  lam ~name:"pair" two_qubits two_qubits
    { run_lam =
        fun pair_value ->
          let_tensor ~left_name:"left" ~right_name:"right"
            q q (use pair_value)
            { run_split =
                fun left right ->
                  pair
                    (Op.apply Op.h (use left))
                    (Op.apply Op.s (use right))
                    (UL (UR U0)) }
            (UL U0) }

let () =
  match Bridge.compile_show (emit program) with
  | Bridge.CompileOk (permutation, gates) ->
      Printf.printf
        "Source quickstart: OK gates=%d wires=%d\n"
        gates permutation.n
  | Bridge.CompileError error ->
      Printf.eprintf "Source quickstart: FAIL: %s\n" error;
      exit 1
