open Qpl_surface
open Linear
let () =
  let term = exp_i (Float.pi /. 4.0) gate_x in
  match Bridge.compile_show (emit term) with
  | Bridge.CompileOk (perm, size) ->
      Printf.printf "OK: size=%d perm_n=%d\n" size perm.n
  | Bridge.CompileError e -> Printf.printf "FAIL: %s\n" e
