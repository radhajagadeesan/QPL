(** Generic QSwitch: qswitch works at every first-order payload type A.

    The idea. The canonical `qswitch` in qswitch_instantiated_e2e.ml is
    fixed at payload Q. But the same combinator works at ANY first-order
    payload A — Q, Q ⊗ Q, Bool, Bool ⊗ Q, etc. — because f and g
    (the function arguments to `qswitch`) are implicitly eta-expanded
    into wire-level operations on the payload. The payload never has to
    be Q; it just has to be first-order.

    Signature:
      qswitch_generic : 'a ty
                     -> (unit, Lolli(a, a)) prog     (* f : A ⊸ A *)
                     -> (unit, Lolli(a, a)) prog     (* g : A ⊸ A *)
                     -> (unit, Lolli(Bool ⊗ a, Bool ⊗ a)) prog

    Semantics (unchanged from the Q-payload version):
      |0⟩ ⊗ |ψ⟩ → |0⟩ ⊗ f(g(|ψ⟩))    (apply g then f)
      |1⟩ ⊗ |ψ⟩ → |1⟩ ⊗ g(f(|ψ⟩))    (apply f then g)

    The eta-expansion happens INSIDE `case_hom` / `make_branch`: `f` and
    `g` are spliced as operations on the payload wires — they never
    appear as function VALUES in a sum payload. So the first-order
    restriction is satisfied on the payload `A`; nothing else needs
    to change to move from Q to any other first-order A.

    Instantiations demonstrated below:
      qswitch_generic q                — the classical Q payload
      qswitch_generic (q ** q)         — 2-qubit payload
      qswitch_generic bool_ty          — Bool payload
      qswitch_generic (bool_ty ** q)   — mixed payload

    All four use the SAME combinator. The only thing that changes is A.
*)

open Qpl_surface
open Linear

let banner title =
  print_endline "";
  print_endline (String.make 74 '=');
  Printf.printf "  %s\n" title;
  print_endline (String.make 74 '=')

let bool_ty = one ++ one

(* ========================================================================= *)
(*  qswitch_generic : any first-order payload A                              *)
(* ========================================================================= *)

let qswitch_generic (a_ty : 'a ty)
    (f : (unit, [`Lolli of 'a * 'a]) prog)
    (g : (unit, [`Lolli of 'a * 'a]) prog)
    : (unit, [`Lolli of [`Tensor of [`Plus of [`One] * [`One]] * 'a]
                      * [`Tensor of [`Plus of [`One] * [`One]] * 'a]]) prog =
  let left  = make_branch a_ty one (seq0 g f) in   (* ctrl=0: apply g then f *)
  let right = make_branch a_ty one (seq0 f g) in   (* ctrl=1: apply f then g *)
  seq0
    (twist_tensor bool_ty a_ty)
    (case_hom one one a_ty a_ty left right)

(* ========================================================================= *)
(*  Sanity: (f = g = id_A)  ⇒  qswitch = id_(Bool ⊗ A)                       *)
(*         (f = g)           ⇒  qswitch = id_Bool ⊗ (f ; f)                  *)
(* ========================================================================= *)

let check_trivial name a_ty =
  let ida = id a_ty in
  let sw  = qswitch_generic a_ty ida ida in
  let ref_id = id (bool_ty ** a_ty) in
  match Bridge.eq_circ (emit sw) (emit ref_id) with
  | Bridge.EqCircOk (true, fid) ->
      Printf.printf "  PASS  qswitch_generic %-14s id id = id  fidelity=%.6f\n" name fid
  | Bridge.EqCircOk (false, fid) ->
      Printf.printf "  FAIL  qswitch_generic %-14s id id != id  fidelity=%.6f\n" name fid
  | Bridge.EqCircError err ->
      Printf.printf "  ERROR %s: %s\n" name err

let check_equal_fg name a_ty f =
  let sw = qswitch_generic a_ty f f in
  let ref_fg = par0 (id bool_ty) (seq0 f f) in
  match Bridge.eq_circ (emit sw) (emit ref_fg) with
  | Bridge.EqCircOk (true, fid) ->
      Printf.printf "  PASS  qswitch_generic %-14s f f = id_Bool ⊗ (f;f)  fidelity=%.6f\n" name fid
  | Bridge.EqCircOk (false, fid) ->
      Printf.printf "  FAIL  qswitch_generic %-14s f f != id_Bool ⊗ (f;f)  fidelity=%.6f\n" name fid
  | Bridge.EqCircError err ->
      Printf.printf "  ERROR %s: %s\n" name err

(* ========================================================================= *)
(*  Main                                                                     *)
(* ========================================================================= *)

let () =
  banner "GENERIC QSwitch — same combinator, every first-order payload A";

  print_endline "";
  print_endline "  qswitch_generic A f g : Bool ⊗ A ⊸ Bool ⊗ A";
  print_endline "";
  print_endline "  A ranges over first-order payloads. f, g : A ⊸ A can be";
  print_endline "  arbitrary endomorphisms; they are implicitly eta-expanded";
  print_endline "  into wire-level operations on the A payload by case_hom.";

  banner "PART 1: A = Q  (classical single-qubit)";
  print_endline "";
  check_trivial "Q            " q;
  check_equal_fg "Q            " q gate_h;

  banner "PART 2: A = Q ⊗ Q  (multi-qubit)";
  print_endline "";
  let qq = q ** q in
  check_trivial "(Q ⊗ Q)      " qq;
  check_equal_fg "(Q ⊗ Q)      " qq gate_cx;

  banner "PART 3: A = Bool  (sum-typed payload)";
  print_endline "";
  check_trivial "Bool         " bool_ty;
  check_equal_fg "Bool         " bool_ty (twist_plus one one);

  banner "PART 4: A = Bool ⊗ Q  (mixed)";
  print_endline "";
  let bq = bool_ty ** q in
  check_trivial "(Bool ⊗ Q)   " bq;
  check_equal_fg "(Bool ⊗ Q)   " bq (par0 (twist_plus one one) gate_x);

  banner "PART 5: sample compilation — qswitch_generic (Q ⊗ Q) CX SWAP";
  let sw = qswitch_generic qq gate_cx (twist_tensor q q) in
  (match Bridge.compile_show (emit sw) with
   | Bridge.CompileOk (_, size) ->
       Printf.printf "\n  Compiled successfully. Circuit size: %d gates.\n" size
   | Bridge.CompileError err ->
       Printf.printf "\n  Compile error: %s\n" err);

  banner "SUMMARY";
  print_endline "";
  print_endline "  qswitch_generic works UNCHANGED at every first-order payload A.";
  print_endline "  The combinator is Q-agnostic; the payload only needs to satisfy";
  print_endline "  first_order (no Lolli anywhere). f and g are eta-expanded as";
  print_endline "  operations on A's wires by case_hom — the payload never sees";
  print_endline "  a function value, so the first-order guard is trivially met."
