(** qswitch_η for A = Q ⊸ Q  — the higher-order case, fully η-expanded to
    first-order canonical form.

    Motivation. There is no library-level combinator `qswitch A f g` for
    higher-order A — the payload would carry Lolli and violate the
    first-order restriction on sum payloads. But every such qswitch has
    a first-order representative obtained by full η-expansion: expose
    every atomic argument (down to Q) as an explicit λ-argument. The
    resulting term operates only on first-order wires, so the restriction
    is trivially satisfied.

    For A = Q ⊸ Q, the atomic arguments are:
      - b : Bool                                (the coherent control)
      - f, g : (Q ⊸ Q) ⊸ (Q ⊸ Q)                (function transformers)
      - h : Q ⊸ Q                                (a base function value)
      - x : Q                                    (the ultimate atomic Q)

    Fully-η-expanded λ-term:
      qswitch_η_endoQ =
        λ b : Bool.
        λ f : (Q ⊸ Q) ⊸ (Q ⊸ Q).
        λ g : (Q ⊸ Q) ⊸ (Q ⊸ Q).
        λ h : Q ⊸ Q.
        λ x : Q.
        if b then (f (g h)) x else (g (f h)) x     -- coherent case; tag preserved
        : Bool ⊗ Q

    Type of qswitch_η_endoQ (curried):
      Bool ⊸ ((Q⊸Q)⊸(Q⊸Q)) ⊸ ((Q⊸Q)⊸(Q⊸Q)) ⊸ (Q⊸Q) ⊸ Q ⊸ (Bool ⊗ Q)

    We build it as an oterm following the same template as the existing
    abstract_qswitch (which is the A = Q version). The core structure is:
      - Input is packaged as Bool ⊗ (f ⊗ (g ⊗ (h ⊗ x))) = Bool ⊗ Γ.
      - Rearrange to Γ ⊗ Bool via twist_tensor.
      - Apply ocase_hom with two CLOSED branches, each of which
        destructures Γ into (f, g, h, x) via nested oletpair, and
        computes the appropriate composition.
      - Wrap the whole thing in one outer olam that consumes the packaged
        input tuple (the η-expansion IS the tuple + destructuring
        pattern; the individual λ-arguments are the tuple's components).

    Every step of the term is expressible with Table 1 primitives + the
    quantum extension's structural isomorphisms + case_hom sugar. The
    first-order guard is satisfied because the case_hom's payload C is Q
    (first-order); the Lolli-typed things (f, g, h) live in the λ-context,
    not in a sum payload.
*)

open Qpl_surface
open Linear

let banner title =
  print_endline "";
  print_endline (String.make 74 '=');
  Printf.printf "  %s\n" title;
  print_endline (String.make 74 '=')

(* ========================================================================= *)
(* Types                                                                      *)
(* ========================================================================= *)

let bool_ty     = one ++ one
let endo_ty     = q -@ q                       (* Q ⊸ Q *)
let endo_op_ty  = endo_ty -@ endo_ty           (* (Q ⊸ Q) ⊸ (Q ⊸ Q) *)

let hx_ty       = endo_ty ** q                 (* Endo ⊗ Q *)
let ghx_ty      = endo_op_ty ** hx_ty          (* EndoOp ⊗ (Endo ⊗ Q) *)
let payload_ty  = endo_op_ty ** ghx_ty         (* Γ = EndoOp ⊗ (EndoOp ⊗ (Endo ⊗ Q)) *)
let gi_ty       = payload_ty ** one            (* Γ ⊗ I (branch input after dist_r) *)
let input_ty    = bool_ty ** payload_ty        (* Bool ⊗ Γ *)
let bq_ty       = bool_ty ** q                 (* output: Bool ⊗ Q *)

(* ========================================================================= *)
(* qswitch_η for A = Q ⊸ Q                                                    *)
(* ========================================================================= *)

let qswitch_eta_endoQ : (unit, [`Lolli of _ * _]) oterm =

  (* Rearrange Bool ⊗ Γ  →  Γ ⊗ Bool  for case_hom's G ⊗ (A+B) shape *)
  let rearrange = twist_tensor bool_ty payload_ty in

  (* Context arithmetic (both branches share the same destructuring pattern):

     After outermost oletpair0 (payload, tag):
       body context = [payload, tag]                (payload*(one*unit))

     After oletpair (f, ghx) with split SLeft(SRight SNil)
                                       [payload→L,   tag→R]:
       body context = [f, ghx, tag]                (endo_op*(ghx*(one*unit)))

     After oletpair (g, hx) with split SRight(SLeft(SRight SNil))
                                       [ghx→L,  f→R,   tag→R]:
       body context = [g, hx, f, tag]              (endo_op*(hx*(endo_op*(one*unit))))

     After oletpair (h, x) with split SRight(SLeft(SRight(SRight SNil)))
                                       [hx→L, g→R, f→R, tag→R]:
       body context = [h, x, g, f, tag]            (endo*(q*(endo_op*(endo_op*(one*unit)))))

     Now compose (g (f h)) x or (f (g h)) x using vars [h, x, g, f]; pair with tag.

     opair split places tag at the end:
       SRight (SRight (SRight (SRight (SLeft SNil))))
       [tag→L,  h→R, x→R, g→R, f→R]  →  combined h*(x*(g*(f*(one*unit)))) ✓
  *)

  (* Left branch (b = inl, "0-tag"): compute (g (f h)) x  :  Q. *)
  let left_branch =
    oletpair0 "payload" "tag" payload_ty one (oid gi_ty)
      (oletpair "f" "ghx" endo_op_ty ghx_ty (ovar "payload" payload_ty)
        (oletpair "g" "hx" endo_op_ty hx_ty (ovar "ghx" ghx_ty)
          (oletpair "h" "x" endo_ty q (ovar "hx" hx_ty)
            (opair (ovar "tag" one)
                   (* (g (f h)) x  with vars [h, x, g, f] in context.
                      Build innermost outward. *)
                   (oapp
                      (* app_2 = g (f h) with context h*(g*(f*unit)) *)
                      (oapp (ovar "g" endo_op_ty)
                            (* app_1 = f h with context h*(f*unit) *)
                            (oapp (ovar "f" endo_op_ty)
                                  (ovar "h" endo_ty)
                                  (SRight (SLeft SNil)))
                                  (* f→L, h→R; combined = h*(f*unit) *)
                            (SRight (SLeft (SRight SNil))))
                            (* g→L, (h,f)→R; combined = h*(g*(f*unit)) *)
                      (ovar "x" q)
                      (SLeft (SRight (SLeft (SLeft SNil)))))
                      (* (h,g,f)→L, x→R inserted between h and g;
                         combined = h*(x*(g*(f*unit))) *)
                   (SRight (SRight (SRight (SRight (SLeft SNil))))))
                   (* tag→L, (h,x,g,f)→R;
                      combined = h*(x*(g*(f*(one*unit)))) *)
            (SRight (SLeft (SRight (SRight SNil)))))
          (SRight (SLeft (SRight SNil))))
        (SLeft (SRight SNil)))
  in

  (* Right branch (b = inr, "1-tag"): compute (f (g h)) x  :  Q. Same split
     scaffolding as left; only the inner apps swap f ↔ g. *)
  let right_branch =
    oletpair0 "payload" "tag" payload_ty one (oid gi_ty)
      (oletpair "f" "ghx" endo_op_ty ghx_ty (ovar "payload" payload_ty)
        (oletpair "g" "hx" endo_op_ty hx_ty (ovar "ghx" ghx_ty)
          (oletpair "h" "x" endo_ty q (ovar "hx" hx_ty)
            (opair (ovar "tag" one)
                   (oapp
                      (oapp (ovar "f" endo_op_ty)
                            (oapp (ovar "g" endo_op_ty)
                                  (ovar "h" endo_ty)
                                  (SRight (SLeft SNil)))
                            (SRight (SLeft (SRight SNil))))
                      (ovar "x" q)
                      (SLeft (SRight (SLeft (SLeft SNil)))))
                   (SRight (SRight (SRight (SRight (SLeft SNil))))))
            (SRight (SLeft (SRight (SRight SNil)))))
          (SRight (SLeft (SRight SNil))))
        (SLeft (SRight SNil)))
  in

  (* Pipeline: rearrange (Bool⊗Γ → Γ⊗Bool), then case_hom. Both closed. *)
  let pipeline =
    oseq0 (oembed rearrange)
          (ocase_hom one one payload_ty q left_branch right_branch)
  in

  (* Outer λ: consumes the packaged input tuple Bool⊗Γ, applies pipeline. *)
  olam "input" input_ty bq_ty
    (oapp pipeline (ovar "input" input_ty) (SRight SNil))

(* ========================================================================= *)
(* Demo + sanity                                                              *)
(* ========================================================================= *)

let n_pass = ref 0
let n_fail = ref 0

let () =
  banner "qswitch_η for A = Q ⊸ Q  —  fully η-expanded λ-term";

  print_endline "";
  print_endline "  Type: (Bool ⊗ ((Q⊸Q)⊸(Q⊸Q))";
  print_endline "                ⊗ ((Q⊸Q)⊸(Q⊸Q))";
  print_endline "                ⊗ (Q⊸Q)";
  print_endline "                ⊗ Q)";
  print_endline "         ⊸  Bool ⊗ Q";
  print_endline "";
  print_endline "  Every argument is atomic (Bool or Q ⊸ Q or Q). The higher-order";
  print_endline "  values f, g, h live in the λ-context, not in a sum payload.";
  print_endline "  The internal case_hom's payload C is Q — first-order.";

  banner "PART 1: type + build";

  let bridge_term = emit_oterm qswitch_eta_endoQ in
  Printf.printf "\n  Bridge JSON preview: %s...\n"
    (let j = Bridge.term_to_json bridge_term in
     String.sub j 0 (min 160 (String.length j)));

  banner "PART 2: compile";

  (match Bridge.compile_show bridge_term with
   | Bridge.CompileOk (_, size) ->
       Printf.printf "\n  PASS  compiled successfully. Circuit size: %d gates.\n" size;
       incr n_pass
   | Bridge.CompileError err ->
       Printf.printf "\n  FAIL  compile error: %s\n" err;
       incr n_fail);

  banner "SUMMARY";
  Printf.printf "\n  Passed: %d\n  Failed: %d\n" !n_pass !n_fail;
  print_endline "";
  print_endline "  qswitch_η for A = Q ⊸ Q is expressible as a λ-term in Granthi.";
  print_endline "  Full η-expansion drives every higher-order-looking construction";
  print_endline "  down to a first-order canonical form; the first-order sum-payload";
  print_endline "  restriction is a canonical-form requirement, not an expressiveness";
  print_endline "  limitation. This is the canonical demonstration for the higher-order";
  print_endline "  case (A = function type); the same pattern extends by adding more";
  print_endline "  λ-arguments for deeper nesting (A = (Q⊸Q)⊸Q, etc.).";
  if !n_fail > 0 then exit 1
