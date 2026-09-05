(* Canary: the -ppx wiring must accept a valid concise program, so a
   broken driver cannot make the reject cases pass vacuously. *)

open Qpl_surface.Source

let%source quickstart (p : (q, q) tensor) =
  let (l, r) = split p in
  (h l, s r)

let _ = quickstart
