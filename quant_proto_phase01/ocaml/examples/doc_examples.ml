(* Compiled documentation examples.

   Every Source program advertised in README.md and
   docs/PROGRAMMING_GUIDE.md is DEFINED HERE, verbatim.  This file is
   built with the real PPX and executed by `dune test`, so the public
   documentation cannot drift from what the compiler accepts.  Markers
   like [--8<-- guide:qswitch] delimit the regions the guide copies. *)

module P = Qpl_surface.Source.P
module Op = Qpl_surface.Source.Op

(* --8<-- guide:minimal *)
let%source hello (x : q) = h x
(* --8<-- end *)

(* --8<-- guide:tensor-split *)
let%source quickstart (p : (q, q) tensor) =
  let (l, r) = split p in
  (h l, s r)
(* --8<-- end *)

(* --8<-- guide:qswitch *)
let%source qswitch (a : 'a P.t)
    (f : ('a, 'a) lolli) (g : ('a, 'a) lolli) (p : (qbool, 'a) tensor) =
  let (b, x) = split p in
  case b
    ~zero:(f (g x))
    ~one_:(g (f x))

let%source qswitch_hs (p : (qbool, q) tensor) =
  let (b, x) = split p in
  case b
    ~zero:(h (s x))
    ~one_:(s (h x))
(* --8<-- end *)

(* --8<-- guide:compose *)
let%source compose2 (f : (q, q) lolli) (g : (q, q) lolli) (x : q) =
  f (g x)
(* --8<-- end *)

(* --8<-- guide:qbool-case *)
let%source fixed_control (p : (qbool, q) tensor) =
  let (c, target) = split p in
  case c
    ~zero:(h target)
    ~one_:(s target)
(* --8<-- end *)

(* --8<-- guide:sum-case *)
let%source sum_case (s : (q, q) plus) (y : q) =
  case s
    ~left_:(h y)
    ~right_:(z y)
(* --8<-- end *)

(* --8<-- guide:datatype *)
type traffic = Red | Amber | Green [@@source.datatype]

let traffic_gate = Traffic.select ~target:P.q [ Op.h; Op.s; Op.t ]

let%source dispatch (p : (Traffic.t, q) tensor) = traffic_gate p
(* --8<-- end *)

(* --8<-- guide:match *)
let%source signal (d : Traffic.t) (y : q) =
  match d with
  | Red -> h y
  | Amber -> s y
  | Green -> t y
(* --8<-- end *)

(* --8<-- guide:permute *)
let rotate = Traffic.permute [ Amber; Green; Red ]

let swap_red_amber = Traffic.involution_permute [ Amber; Red; Green ]

let partial_swap =
  Op.exp_i (Float.pi /. 4.0) swap_red_amber

let%source rotated (d : Traffic.t) = rotate d
let%source blended (d : Traffic.t) = partial_swap d
(* --8<-- end *)

(* --8<-- guide:host-op *)
let partial_twist = Op.exp_i (Float.pi /. 4.0) (Op.involution_twist P.q)

let%source blend (p : (q, q) tensor) = partial_twist p
(* --8<-- end *)

(* --8<-- guide:annotated-host-op *)
let dl = Op.dist_left P.q P.q P.q

let%source distribute (p : (((q, q) plus, q) tensor)) =
  (dl : ((((q, q) plus, q) tensor,
          ((q, q) tensor, (q, q) tensor) plus) lolli)) p
(* --8<-- end *)

(* ------------------------------------------------------------------ *)
(* Runner: emit and compile each example through the real pipeline.    *)
(* ------------------------------------------------------------------ *)

open Qpl_surface

let failures = ref 0

let check name term =
  match Bridge.compile_show (Source.emit term) with
  | Bridge.CompileOk (perm, gates) ->
      Printf.printf "  PASS  %-16s wires=%d gates=%d\n%!" name
        perm.Bridge.n gates
  | Bridge.CompileError e ->
      incr failures;
      Printf.printf "  FAIL  %-16s %s\n%!" name e

let () =
  Printf.printf "== documentation examples compile end-to-end\n";
  check "hello" hello;
  check "quickstart" quickstart;
  check "qswitch" (qswitch P.q);
  check "qswitch_hs" qswitch_hs;
  check "fixed_control" fixed_control;
  check "sum_case" sum_case;
  check "dispatch" dispatch;
  check "signal" signal;
  check "rotated" rotated;
  check "blended" blended;
  check "compose2" compose2;
  check "blend" blend;
  check "distribute" distribute;
  if !failures = 0 then Printf.printf "ALL DOC EXAMPLES COMPILE\n%!"
  else begin
    Printf.printf "%d doc examples FAILED\n%!" !failures;
    exit 1
  end
