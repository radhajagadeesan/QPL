open Qpl_surface
open Source

let () =
  let term =
    Op.value (Op.exp_i (Float.pi /. 4.0) Op.involution_x)
  in
  match Bridge.compile_show (emit term) with
  | Bridge.CompileOk (perm, size) ->
      Printf.printf "OK: size=%d perm_n=%d\n" size perm.n
  | Bridge.CompileError e ->
      Printf.eprintf "FAIL: %s\n" e;
      exit 1
