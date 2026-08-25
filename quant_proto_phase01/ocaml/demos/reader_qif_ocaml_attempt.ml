(** Regression test: reader's higher-order qif term is rejected

    Origin: this is the term reported externally as a soundness concern
    (LICS 2026 quantum-control paper author). It has the shape

      let (x', f) = (qif x then X else I) in f x'

    and can be built in Granthi via oplusmap0 + undist_l + oletpair + oapp,
    all Table 1 primitives. Under the naïve typing rule this term is
    derivable and denotes the non-unitary map [[0,0],[1,1]].

    The first-order sum-payload restriction (implemented in
    linear.ml : first_order + guards, and in
    python/src/compile/to_pytket.py : _assert_first_order_sum_payloads)
    closes this pathology. The term still BUILDS at the OCaml surface
    (linearity is satisfied — each variable is used once), but the
    compiler rejects it because the ⊕-Map output type
      (Unit ⊗ (QBool ⊸ QBool)) ⊕ (Unit ⊗ (QBool ⊸ QBool))
    is a sum whose summands contain Lolli.

    This test PASSES when compilation of the reader's term rejects it
    with the expected first-order error.
*)

open Qpl_surface
open Linear

let bool_ty = one ++ one
let endo_ty = bool_ty -@ bool_ty

(* Lam value: X on Bool = λz. twist_plus z *)
let x_lam_o : (unit, [`Lolli of [`Plus of [`One] * [`One]]
                              * [`Plus of [`One] * [`One]]]) oterm =
  olam "z_x" bool_ty bool_ty
    (oapp (oembed (twist_plus one one))
          (ovar "z_x" bool_ty)
          (SRight SNil))

(* Lam value: identity on Bool = λz. z *)
let id_lam_o : (unit, [`Lolli of [`Plus of [`One] * [`One]]
                                * [`Plus of [`One] * [`One]]]) oterm =
  olam "z_i" bool_ty bool_ty (ovar "z_i" bool_ty)

(* Branches: values of type Unit ⊗ endo *)
let else_branch_o = opair0 (oid one) x_lam_o
let then_branch_o = opair0 (oid one) id_lam_o

(* PlusMap: Bool ⊸ (Unit ⊗ endo) ⊕ (Unit ⊗ endo)
   Under the first-order restriction, this ⊕-Map output type contains
   Lolli in its sum payload — compilation must reject. *)
let plusmap_o = oplusmap0 one one else_branch_o then_branch_o

(* Full term: undist_l repackages to Bool ⊗ endo, then destructure + apply *)
let qif_o = oseq0 plusmap_o (oembed (undist_l one one endo_ty))
let x_var = ovar "x" bool_ty
let pair_term = oapp qif_o x_var (SRight SNil)

let body =
  oletpair "x_prime" "f" bool_ty endo_ty
    pair_term
    (oapp (ovar "f" endo_ty)
          (ovar "x_prime" bool_ty)
          (SRight (SLeft SNil)))
    (SLeft SNil)

let program = olam "x" bool_ty bool_ty body

let () =
  print_endline "==============================================================";
  print_endline "  Regression: reader's higher-order qif term must be REJECTED";
  print_endline "==============================================================";
  print_endline "";
  print_endline "The term builds at the OCaml surface (linearity is satisfied):";
  print_endline "";
  Printf.printf "  program : Bool ⊸ Bool  (via oplusmap0 + undist_l + oletpair + oapp)\n";
  print_endline "";
  print_endline "Attempting to compile through Bridge → Python:";
  print_endline "";
  match Bridge.compile_show (emit_oterm program) with
  | Bridge.CompileOk _ ->
      print_endline "";
      print_endline "  FAIL: term compiled successfully — the first-order guard";
      print_endline "        did NOT fire. This is a soundness regression.";
      exit 1
  | Bridge.CompileError err ->
      let is_first_order_err =
        try
          let _ = Str.search_forward (Str.regexp_string "first-order") err 0 in
          true
        with Not_found -> false
      in
      if is_first_order_err then begin
        print_endline "";
        print_endline "  PASS: compilation rejected with the expected first-order error.";
        print_endline "  This is the intended behavior of the soundness fix.";
        print_endline ""
      end else begin
        print_endline "";
        Printf.printf "  FAIL: compilation rejected, but not with a first-order error.\n";
        Printf.printf "  Got: %s\n" err;
        exit 1
      end
