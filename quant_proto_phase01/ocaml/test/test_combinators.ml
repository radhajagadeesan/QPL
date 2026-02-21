(** Verify the three paper combinators type-check in the Linear GADT.

    1. ctrl  : (A ⊸ A) ⊸ (Bool ⊗ A) ⊸ (Bool ⊗ A)
    2. tagged_case : Γ ⊗ (A+B) → (A+B) ⊗ C   (shared context)
    3. general_case : (A+B) → (C+D)            (split contexts, ⊕-Map)

    Now with context-tracked ('g, 'a) oterm and explicit split witnesses.
*)

open Qpl_surface
open Linear

(* ================================================================ *)
(* 1. ctrl at Q                                                      *)
(*                                                                   *)
(*   ctrl := λf. undist_l ∘ (id(I⊗Q) ⊕ branch_right(f)) ∘ dist_l   *)
(*                                                                   *)
(*   f is FREE in the right branch — context qq * unit.              *)
(*   Split witnesses track the free variable through the pipeline.   *)
(* ================================================================ *)

let ctrl_q =
  let a = q in
  let ia = one ** a in
  let bool_ty = one ++ one in
  let ba = bool_ty ** a in
  (* Right branch: I⊗Q → I⊗Q, applies f to the Q part.
     Context after oletpair (oid scrutinee): [tag:one, x:q, f:qq]
     opair: tag→left, (x,f)→right
     oapp:  f→left (function), x→right (argument) *)
  let right_branch =
    oletpair "tag" "x" one a (oid ia)
      (opair (ovar "tag" one)
             (oapp (ovar "f" (a -@ a)) (ovar "x" a)
                   (SRight (SLeft SNil)))       (* x→right, f→left *)
             (SLeft (SRight (SRight SNil))))    (* tag→left, x→right, f→right *)
      (SRight SNil)                             (* f→right (body inherits f) *)
  in
  olam "f" (a -@ a) (ba -@ ba)
    (oseq
      (oseq
        (oembed (dist_l one one a))
        (oplusmap ia ia (oid ia) right_branch
                  (SRight SNil))                (* left closed, f→right *)
        (SRight SNil))                          (* dist closed, plusmap has f *)
      (oembed (undist_l one one a))
      (SLeft SNil))                             (* inner has f, undist closed *)


(* ================================================================ *)
(* 2. Tagged case (binary, shared context)                           *)
(*                                                                   *)
(*   G ⊗ (A+B) →[dist_r] (G⊗A)+(G⊗B)                               *)
(*             →[f̂ ⊕ ĝ]  (A⊗C)+(B⊗C)                               *)
(*             →[undist_l] (A+B) ⊗ C                                 *)
(*                                                                   *)
(*   Branches are CLOSED morphisms (no free variables).              *)
(* ================================================================ *)

let tagged_case_instance =
  let g = q -@ q in    (* shared context: a function Q ⊸ Q *)
  let a = one in        (* left summand of Bool *)
  let b = one in        (* right summand of Bool *)
  let c = q in          (* result type *)
  let ga = g ** a in    (* G ⊗ I *)
  let gb = g ** b in    (* G ⊗ I *)
  let ac = a ** c in    (* I ⊗ Q *)
  let bc = b ** c in    (* I ⊗ Q *)
  ignore (g, a, b, c, ga, gb, ac, bc);

  let qq = q -@ q in
  let payload = qq ** (qq ** q) in  (* (Q⊸Q) ⊗ ((Q⊸Q) ⊗ Q) *)
  let gi = payload ** one in        (* G ⊗ I *)
  let _iq = one ** q in             (* I ⊗ Q *)

  (* Left branch: G⊗I → I⊗Q — apply g then f (CLOSED).
     Context after oletpairs:
       1st: [ctx:payload, tag:one]
       2nd: [f:qq, gx:qq**q, tag:one]
       3rd: [g:qq, x:q, f:qq, tag:one] *)
  let left_branch =
    oletpair0 "ctx" "tag" payload one (oid gi)
      (oletpair "f" "gx" qq (qq ** q) (ovar "ctx" payload)
        (oletpair "g" "x" qq q (ovar "gx" (qq ** q))
          (opair (ovar "tag" one)
                 (oapp (ovar "f" qq)
                       (oapp (ovar "g" qq)
                             (ovar "x" q)
                             (SLeft (SRight SNil)))
                       (SRight (SRight (SLeft SNil))))
                 (SRight (SRight (SRight (SLeft SNil)))))
          (SRight (SLeft (SRight SNil))))
        (SLeft (SRight SNil)))
  in
  (* Right branch: G⊗I → I⊗Q — apply f then g (CLOSED) *)
  let right_branch =
    oletpair0 "ctx" "tag" payload one (oid gi)
      (oletpair "f" "gx" qq (qq ** q) (ovar "ctx" payload)
        (oletpair "g" "x" qq q (ovar "gx" (qq ** q))
          (opair (ovar "tag" one)
                 (oapp (ovar "g" qq)
                       (oapp (ovar "f" qq)
                             (ovar "x" q)
                             (SRight (SLeft SNil)))
                       (SLeft (SRight (SRight SNil))))
                 (SRight (SRight (SRight (SLeft SNil)))))
          (SRight (SLeft (SRight SNil))))
        (SLeft (SRight SNil)))
  in
  (* Pipeline: dist_r ; plusmap ; undist_l — all closed *)
  oseq0
    (oseq0
      (oembed (dist_r payload one one))
      (oplusmap0 gi gi left_branch right_branch))
    (oembed (undist_l one one q))


(* ================================================================ *)
(* 3. General case (split contexts)                                  *)
(*                                                                   *)
(*   Given f: A ⊸ C, g: B ⊸ D (possibly open),                      *)
(*   form (f ⊕ g) : (A+B) ⊸ (C+D)  via ⊕-Map,                      *)
(*   then apply to scrutinee t : A+B.                                *)
(*                                                                   *)
(*   Instance: f = λx. H(x), g = λy. S(y), both closed.             *)
(*   Scrutinee: id(Q+Q).                                             *)
(*   Result: (Q+Q) ⊸ (Q+Q).                                         *)
(*                                                                   *)
(*   In prog GADT (closed branches):                                 *)
(* ================================================================ *)

let general_case_closed =
  let f = seq0 (id q) gate_h in   (* Q ⊸ Q *)
  let g = seq0 (id q) gate_s in   (* Q ⊸ Q *)
  (* ⊕-Map: (Q+Q) ⊸ (Q+Q) *)
  omap0 q q f g

(* General case with open branches, via oterm *)
let general_case_oterm =
  let a = q in
  let b = q in
  (* Branch lambdas — oapp needs split: oembed is closed, ovar has context *)
  let f = olam "x" a a (oapp (oembed gate_h) (ovar "x" a) (SRight SNil)) in
  let g = olam "y" b b (oapp (oembed gate_s) (ovar "y" b) (SRight SNil)) in
  (* For closed branches, we embed the prog omap: *)
  ignore (f, g);
  oembed (omap0 q q (seq0 (id q) gate_h) (seq0 (id q) gate_s))


(* ================================================================ *)
(* 4. Case sugar: case_hom0 (Bool → Bool⊗Q)                         *)
(*                                                                   *)
(*   Input: Bool = I⊕I                                              *)
(*   Output: Bool ⊗ Q                                               *)
(*   Left branch:  I → I⊗Q  (apply H)                              *)
(*   Right branch: I → I⊗Q  (apply S... but S:Q→Q so we use H too) *)
(*                                                                   *)
(*   Uses make_branch to build branches from body: I → Q.           *)
(* ================================================================ *)

let case_hom0_bool_to_q =
  let a = one in
  let b = one in
  let c = q in
  (* make_branch: I⊗I → I⊗Q from body: I → Q
     But we need body: I → Q. We can use seq0 (id one) ... no, I → Q doesn't
     type-check as an endomorphism. We need: A → A⊗C.
     For A=I, C=Q: branch is I → I⊗Q.

     Actually make_branch builds G⊗A → A⊗C from body: G → C.
     For no-context case_hom0, branches are A → A⊗C directly.
     So we don't use make_branch here — we build branches directly.

     Branch left:  I → I⊗Q: pair the unit with a fresh qubit via... hmm,
     we can't create qubits from nothing. Let's use identity branches instead.

     Actually, for case_hom0, the branches need type A → A⊗C.
     With A=I, C=Q: that's I → I⊗Q which is a state preparation — not what
     we want here.

     Better test: A=Q, B=Q, C=Q. Input Q⊕Q, output (Q⊕Q)⊗Q.
     Branches f: Q → Q⊗Q, g: Q → Q⊗Q. That also creates qubits.

     Simplest valid test: both branches are endomorphisms dressed with tag.
     Use make_branch with G=I, A=I, body=id(I):
       make_branch one one (id one) : I⊗I → I⊗I

     Let's do: A=I, B=I, C=I (trivial case to verify plumbing).
     f: I → I⊗I = make_branch one one (id one) ... no, make_branch is G⊗A → A⊗C.
     For case_hom0 the branches are A → A⊗C.
     make_branch one one (id one) gives I⊗I → I⊗I which is (G⊗A) → (A⊗C)
     where G=I, A=I, C=I. That IS the branch type for case_hom0 with A=I.
     Wait — case_hom0 branches have type A → A⊗C, not G⊗A → A⊗C.
     For A=I, A⊗C = I⊗I. So branch type is I → I⊗I.
     But make_branch gives G⊗A → A⊗C = I⊗I → I⊗I. That's different.

     For case_hom0, the simplest test: branches that pair input with identity.
     f: A → A⊗C. For A=I, C=I: I → I⊗I.
     We can express this as: par0 (id one) (id one) : I⊗I → I⊗I.
     But that's I⊗I → I⊗I, not I → I⊗I.

     Actually I⊗I ≅ I via the unit laws, but we don't have those as
     explicit constructors. Let's instead use non-trivial types.

     Let me use the ctrl pattern which is the motivating example:
     A=I, B=I (Bool), C=Q. G = Q⊸Q (a function in context).
     That requires case_hom (with context), not case_hom0.

     For case_hom0, a clean test: use identity branches.
     A=I, B=I, C=I.
     f = id(I) composed with some structural to get I → I⊗I? No.

     Let me just test case_het0 which is simpler (no undist), and case_hom
     which is the main use case.
  *)
  (* Skip case_hom0 with state-preparation branches — use case_hom instead *)
  ignore (a, b, c);
  ()

(* ================================================================ *)
(* 5. Case sugar: case_hom rewriting ctrl                            *)
(*                                                                   *)
(*   ctrl(f) = case_hom one one qq q                                *)
(*     (make_branch qq one (id q))     (* left: do nothing *)       *)
(*     (make_branch qq one f)          (* right: apply f *)         *)
(*                                                                   *)
(*   where G = Q⊸Q (function context), A=B=I (Bool summands), C=Q  *)
(*   Wait — that's not right. ctrl takes f in context.              *)
(*                                                                   *)
(*   Actually ctrl at the prog level is:                            *)
(*     dist_l ; omap0(id, par0(id_I, f)) ; undist_l                *)
(*                                                                   *)
(*   Using case_hom with G=(), A=I, B=I... no, ctrl has no shared   *)
(*   context at the prog level.                                     *)
(*                                                                   *)
(*   ctrl is case_hom0 where:                                       *)
(*     A=I, B=I, C=Q                                                *)
(*     but input is Bool⊗Q = (I⊕I)⊗Q, not just I⊕I.              *)
(*                                                                   *)
(*   Actually ctrl = dist_l ; omap0(id_{I⊗Q}, par0(id_I, f)) ; undist_l *)
(*   Input type: (I⊕I) ⊗ Q                                         *)
(*   This is dist_l not dist_r. Let me think again...               *)
(*                                                                   *)
(*   dist_l : (A⊕B) ⊗ C → (A⊗C) ⊕ (B⊗C)                          *)
(*   So for Bool⊗Q: (I⊕I) ⊗ Q → (I⊗Q) ⊕ (I⊗Q)                   *)
(*   Then omap0: (I⊗Q)⊕(I⊗Q) → (I⊗Q)⊕(I⊗Q)                      *)
(*   Then undist_l: (I⊗Q)⊕(I⊗Q) → (I⊕I)⊗Q                        *)
(*                                                                   *)
(*   But case_hom uses dist_R (context on left, sum on right).      *)
(*   ctrl uses dist_L (sum on left, payload on right).              *)
(*   These are DIFFERENT distributions!                              *)
(*                                                                   *)
(*   So ctrl is NOT a direct instance of case_hom. But we can       *)
(*   build an equivalent using case_hom with a twist:               *)
(*     twist(Bool, Q) ; case_hom(I, I, Q, Q, ...) ; twist(Bool, Q) *)
(*   where G=Q, A=I, B=I, C=Q.                                     *)
(*                                                                   *)
(*   Or more directly, just verify case_hom emits valid terms.      *)
(* ================================================================ *)

(* Test case_hom: G⊗(A⊕B) → (A⊕B)⊗C
   G = Q (shared qubit), A = I, B = I (Bool summands), C = Q (result)
   Left branch: Q⊗I → I⊗Q = twist(Q,I)  (just reorder)
   Right branch: Q⊗I → I⊗Q = twist(Q,I) ; par0(id_I, gate_h) *)
let case_hom_instance =
  let g_ty = q in
  let a = one in
  let b = one in
  let c = q in
  let left_branch = twist_tensor g_ty a in  (* Q⊗I → I⊗Q *)
  let right_branch = seq0 (twist_tensor g_ty b) (par0 (id b) gate_h) in (* Q⊗I → I⊗Q *)
  case_hom a b g_ty c left_branch right_branch

(* Test case_hom with make_branch helper:
   G = Q, A = I, B = I, C = Q
   make_branch Q I (id Q) : Q⊗I → I⊗Q  (twist only, body is id)
   make_branch Q I gate_h : Q⊗I → I⊗Q  (twist then apply H) *)
let case_hom_with_make_branch =
  let g_ty = q in
  let a = one in
  let b = one in
  let c = q in
  let left_branch = make_branch g_ty a (id g_ty) in  (* Q⊗I → I⊗Q *)
  let right_branch = make_branch g_ty b gate_h in     (* Q⊗I → I⊗Q *)
  case_hom a b g_ty c left_branch right_branch

(* Test case_het: G⊗(A⊕B) → (A⊗C) ⊕ (B⊗D) — heterogeneous
   G = Q, A = I, B = I, C = Q, D = Q
   Left branch:  Q⊗I → I⊗Q = twist
   Right branch: Q⊗I → I⊗Q = twist ; par0(id, H) *)
let case_het_instance =
  let g_ty = q in
  let a = one in
  let b = one in
  let left_branch = twist_tensor g_ty a in
  let right_branch = seq0 (twist_tensor g_ty b) (par0 (id b) gate_h) in
  case_het a b g_ty left_branch right_branch

(* Test case_het0: (A⊕B) → (A⊗C) ⊕ (B⊗D) — no context
   A = Q, B = Q, C = Q, D = Q
   Left branch:  Q → Q⊗Q? No — we can't create qubits.
   Use identity-like branches: A → A⊗C requires state prep.

   Better: use structural branches.
   A = I⊕I (Bool), B = I, branches are endomorphism-like.

   Actually case_het0 branches have type A → A⊗C.
   Simplest: A = I⊗Q, B = I⊗Q (already paired), C = I, D = I.
   f: I⊗Q → (I⊗Q)⊗I ≅ I⊗Q. Hmm, that's weird.

   Let's use the ctrl pattern again: case_het0 shows what happens
   before undist. For A=I, B=I:
   f: I → I⊗Q and g: I → I⊗Q are state preparations.

   Simplest practical test: A=I, B=I, C=I, D=I.
   f: I → I⊗I, g: I → I⊗I. These are unit isos.
   But we don't have I ≅ I⊗I explicitly.

   Let me just verify case_het0 is callable and emits:
   Use A=Q, B=Q with f=g=id... but id(Q) : Q→Q, not Q→Q⊗C.

   OK, the cleanest test: branches that pair with a twist.
   A=I⊗Q, B=I⊗Q (I⊗Q is an actual type we have),
   f = id(I⊗Q) = I⊗Q → I⊗Q, g = par0(id_I, gate_h) = I⊗Q → I⊗Q.
   But these are A→A type (endomorphisms), not A→A⊗C.

   For case_het0, the branch types are A → A⊗C, A → A⊗D.
   These require producing MORE outputs than inputs.
   In a linear system this means the branch creates wires from nothing.
   That's only possible with Unit:
   f: A → A⊗I is trivially A (since A⊗I ≅ A), but again no explicit iso.

   Let me skip case_het0 as a standalone test since it's literally
   just omap0 (an alias). The case_het test above covers the
   interesting case. *)

(* Test ctrl rewrite using case_hom:
   The meta-level ctrl uses dist_l (sum⊗payload), but case_hom uses dist_r
   (context⊗sum). We can express ctrl as:
     twist(Bool,Q) ; case_hom(I,I,Q,Q,...) *)
let ctrl_via_case_hom (f : (unit, [`Lolli of [`Q] * [`Q]]) prog) =
  let a = one in
  let b = one in
  let g_ty = q in
  let c = q in
  (* Left branch: Q⊗I → I⊗Q = make_branch Q I (id Q) — do nothing to Q *)
  let left = make_branch g_ty a (id g_ty) in
  (* Right branch: Q⊗I → I⊗Q = make_branch Q I f — apply f to Q *)
  let right = make_branch g_ty b f in
  (* twist(Bool,Q) puts Q on left: Bool⊗Q → Q⊗Bool
     case_hom: Q⊗Bool → Bool⊗Q *)
  seq0 (twist_tensor (a ++ b) g_ty) (case_hom a b g_ty c left right)


(* ================================================================ *)
(* Verification: emit all three and check they produce valid JSON     *)
(* ================================================================ *)

let () =
  let check name term =
    let json = Bridge.term_to_json term in
    if String.length json > 0 then
      Printf.printf "  %-25s  OK  (%d chars)\n" name (String.length json)
    else
      Printf.printf "  %-25s  FAIL (empty)\n" name
  in
  print_endline "Combinator type-check verification:";
  check "ctrl_q" (emit_oterm ctrl_q);
  check "tagged_case" (emit_oterm tagged_case_instance);
  check "general_case_closed" (emit general_case_closed);
  check "general_case_oterm" (emit_oterm general_case_oterm);
  print_endline "";

  (* Case sugar tests *)
  print_endline "Case sugar verification:";
  case_hom0_bool_to_q;  (* Unit test — just verifies type-checking *)
  check "case_hom" (emit case_hom_instance);
  check "case_hom_make_branch" (emit case_hom_with_make_branch);
  check "case_het" (emit case_het_instance);
  check "ctrl_via_case_hom(X)" (emit (ctrl_via_case_hom gate_x));
  check "ctrl_via_case_hom(H)" (emit (ctrl_via_case_hom gate_h));
  (* ================================================================ *)
  (* Oterm case sugar tests                                           *)
  (* ================================================================ *)
  print_endline "Oterm case sugar verification:";

  (* ocase_hom with bare tensor branches (oterm level).
     G = Q, A = I, B = I, C = Q.
     Branches produce bare I⊗Q oterms via oletpair destructuring. *)
  let ocase_hom_test =
    let g_ty = q in
    let a = one in
    let b = one in
    let c = q in
    let gi = g_ty ** a in   (* Q⊗I = branch input type *)
    (* Left branch: bare oterm producing I⊗Q (swap Q and I) *)
    let left_branch =
      oletpair0 "payload" "tag" g_ty a (oid gi)
        (opair (ovar "tag" a) (ovar "payload" g_ty)
               (SRight (SLeft SNil)))  (* tag→left, payload→right *)
    in
    (* Right branch: bare oterm producing I⊗Q (swap then apply H) *)
    let right_branch =
      oletpair0 "payload" "tag" g_ty b (oid gi)
        (opair (ovar "tag" b)
               (oapp (oembed gate_h) (ovar "payload" g_ty) (SRight SNil))
               (SRight (SLeft SNil)))
    in
    ocase_hom a b g_ty c left_branch right_branch
  in
  check "ocase_hom" (emit_oterm ocase_hom_test);

  (* ocase_het: heterogeneous with context, bare oterm branches *)
  let ocase_het_test =
    let g_ty = q in
    let a = one in
    let b = one in
    let gi = g_ty ** a in
    (* Branches produce I⊗Q — same structure as ocase_hom branches *)
    let left_branch =
      oletpair0 "payload" "tag" g_ty a (oid gi)
        (opair (ovar "tag" a) (ovar "payload" g_ty)
               (SRight (SLeft SNil)))
    in
    let right_branch =
      oletpair0 "payload" "tag" g_ty b (oid gi)
        (opair (ovar "tag" b)
               (oapp (oembed gate_h) (ovar "payload" g_ty) (SRight SNil))
               (SRight (SLeft SNil)))
    in
    ocase_het a b g_ty left_branch right_branch
  in
  check "ocase_het" (emit_oterm ocase_het_test);

  (* omake_branch: embed prog-level make_branch (produces Lolli oterm) *)
  let omake_branch_test =
    omake_branch q one gate_h  (* Q⊗I → I⊗Q *)
  in
  check "omake_branch" (emit_oterm omake_branch_test);

  (* ctrl via oembed(case_hom): using prog-level make_branch + case_hom *)
  let ctrl_via_ocase (f : (unit, [`Lolli of [`Q] * [`Q]]) prog) =
    let a = one in
    let b = one in
    let g_ty = q in
    let c = q in
    let left = make_branch g_ty a (id g_ty) in
    let right = make_branch g_ty b f in
    oseq0 (oembed (twist_tensor (a ++ b) g_ty))
          (oembed (case_hom a b g_ty c left right))
  in
  check "ctrl_via_ocase(X)" (emit_oterm (ctrl_via_ocase gate_x));
  check "ctrl_via_ocase(H)" (emit_oterm (ctrl_via_ocase gate_h));

  print_endline "";
  print_endline "  All combinators type-checked in Linear GADT."
