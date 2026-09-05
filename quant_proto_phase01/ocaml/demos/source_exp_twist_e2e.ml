open Qpl_surface
open Source

let program =
  Op.value
    (Op.exp_i (Float.pi /. 4.0)
       (Op.involution_twist P.q))

let () =
  match Bridge.compile_show (emit program) with
  | Bridge.CompileOk (permutation, gates) ->
      Printf.printf
        "Source exp(i pi/4 swap): OK gates=%d wires=%d\n"
        gates permutation.n
  | Bridge.CompileError error ->
      Printf.eprintf "Source exp(i pi/4 swap): FAIL: %s\n" error;
      exit 1
