(** Regression tests for the first-order sum-payload restriction.

    Soundness fix: sum-typed payloads must be first-order — no Lolli
    may appear inside the target type of ⊕-Map / case / datatype control.
    See linear.ml : first_order + assert_first_order, and
    python/src/compile/to_pytket.py : _assert_first_order_sum_payloads.

    Structure:
      Section 1 — MUST FAIL: negative tests. Each construction is
                  well-formed under linearity but violates the first-order
                  restriction, so it must be rejected either at OCaml
                  smart-constructor time (Invalid_argument) or at
                  compile time (CompileError containing "first-order").
      Section 2 — MUST PASS: positive controls. Standard constructions
                  that continue to work. If any of these fails, the
                  restriction is landing in the wrong place.
*)

open Qpl_surface
open Linear

let bool_ty = one ++ one
let endo_ty = bool_ty -@ bool_ty
let wire_ty = bool_ty ** bool_ty

let n_pass = ref 0
let n_fail = ref 0

let must_fail_ocaml name (build : unit -> _) =
  try
    let _ = build () in
    Printf.printf "  FAIL [OCaml] %s — expected Invalid_argument, got success\n" name;
    incr n_fail
  with
  | Invalid_argument msg
    when (try let _ = Str.search_forward (Str.regexp_string "first-order") msg 0 in true
          with Not_found -> false) ->
      Printf.printf "  PASS [OCaml] %s rejected: %s\n"
        name (String.sub msg 0 (min 80 (String.length msg)));
      incr n_pass
  | e ->
      Printf.printf "  FAIL [OCaml] %s — wrong exception: %s\n" name (Printexc.to_string e);
      incr n_fail

let must_fail_compile name term =
  match Bridge.compile term with
  | Bridge.CompileOk _ ->
      Printf.printf "  FAIL [compile] %s — expected first-order error, got success\n" name;
      incr n_fail
  | Bridge.CompileError err ->
      let is_first_order =
        try let _ = Str.search_forward (Str.regexp_string "first-order") err 0 in true
        with Not_found -> false
      in
      if is_first_order then begin
        Printf.printf "  PASS [compile] %s rejected with first-order error\n" name;
        incr n_pass
      end else begin
        Printf.printf "  FAIL [compile] %s — rejected but not with first-order error:\n    %s\n"
          name err;
        incr n_fail
      end

let must_pass_compile name term =
  match Bridge.compile term with
  | Bridge.CompileOk _ ->
      Printf.printf "  PASS [compile] %s compiles cleanly\n" name;
      incr n_pass
  | Bridge.CompileError err ->
      Printf.printf "  FAIL [compile] %s — expected success, got:\n    %s\n" name err;
      incr n_fail

let () =
  print_endline "";
  print_endline "==============================================================";
  print_endline "  Regression: first-order sum-payload restriction";
  print_endline "==============================================================";

  print_endline "";
  print_endline "-- Section 1: MUST FAIL (negative tests) --";
  print_endline "";

  (* ocase_hom0 at function-typed shared result — must fail at OCaml level.
     ocase_hom0 accepts branches as bare oterms of the target output type
     ("A ⊗ C" for the left summand), so we can construct dummy branches of
     the appropriate Tensor type without needing to synthesize a Bool→endo
     function. The oterm oid on a Tensor type is enough to satisfy OCaml. *)
  must_fail_ocaml
    "ocase_hom0 with ty_c = endo (Q ⊸ Q)"
    (fun () ->
      let dummy = oid (one ** endo_ty) in
      ocase_hom0 one one endo_ty dummy dummy
    );

  (* datatype `control` at function-typed payload — must fail at OCaml level.
     Uses the datatype `control` combinator whose payload type is explicit
     and directly checked. *)
  must_fail_ocaml
    "datatype control with a_ty = endo (Q ⊸ Q)"
    (fun () ->
      let bool_dt = datatype ~name:"Bool2" ~arity:2 ~labels:["0"; "1"] ~ops:[] in
      let dummy = id endo_ty in
      control bool_dt endo_ty [| dummy; dummy |]
    );

  (* Reader's oplusmap0-based construction — caught at compile time. *)
  must_fail_compile
    "reader-style oplusmap0 with endo-payload branches"
    (let x_lam =
       olam "z" bool_ty bool_ty
         (oapp (oembed (twist_plus one one))
               (ovar "z" bool_ty)
               (SRight SNil))
     in
     let branch = opair0 (oid one) x_lam in
     let pm = oplusmap0 one one branch branch in
     let qif = oseq0 pm (oembed (undist_l one one endo_ty)) in
     emit_oterm qif);

  print_endline "";
  print_endline "-- Section 2: MUST PASS (positive controls) --";
  print_endline "";

  (* Eta-expanded QSwitch on wire-encoded payload — should work. *)
  must_pass_compile
    "case_hom with ty_c = Q ⊗ Q (eta-expanded)"
    (emit
       (case_hom one one wire_ty wire_ty
          (make_branch wire_ty one (id wire_ty))
          (make_branch wire_ty one (id wire_ty))));

  (* Ordinary QSwitch on Q payload — the everyday case. *)
  must_pass_compile
    "case_hom with ty_c = Q (ordinary payload)"
    (emit
       (case_hom one one q q
          (make_branch q one (id q))
          (make_branch q one gate_x)));

  (* Bool payload — a Bool-controlled Bool operation. *)
  must_pass_compile
    "case_hom with ty_c = Bool"
    (emit
       (case_hom one one bool_ty bool_ty
          (make_branch bool_ty one (id bool_ty))
          (make_branch bool_ty one (twist_plus one one))));

  (* datatype control at first-order payload — the everyday case. *)
  must_pass_compile
    "datatype control with a_ty = Q (first-order)"
    (let z2 = datatype ~name:"Z2ctrl" ~arity:2 ~labels:["0";"1"] ~ops:[] in
     emit (control z2 q [| id q; gate_x |]));

  Printf.printf "\n============================\n";
  Printf.printf "  Passed: %d\n" !n_pass;
  Printf.printf "  Failed: %d\n" !n_fail;
  Printf.printf "============================\n";
  if !n_fail > 0 then exit 1
