(* Phase-2 frontend extensions, verified the same way as the vertical
   slice: each concise program is compared against a HANDWRITTEN sealed
   oracle through the bridge's circuit-equality check, with pinned facts.

   E1: general first-order sum case  (case s ~left_:… ~right_:…)
       targeting the sealed tag-preserving [case]/[case0].
   E3: annotation-directed host operations
       ((op : (dom, cod) lolli) argument)
       for certified non-endomorphisms such as distributors. *)

open Qpl_surface
open Source

let failures = ref 0

let check name condition detail =
  if condition then Printf.printf "  PASS  %s\n%!" name
  else begin
    incr failures;
    Printf.printf "  FAIL  %s (%s)\n%!" name detail
  end

let show name term =
  match Bridge.compile_show term with
  | Bridge.CompileOk (perm, gates) ->
      Printf.printf "%s: gates=%d wires=%d perm=[%s]\n%!" name gates perm.n
        (String.concat ","
           (List.map string_of_int perm.Bridge.new_to_old));
      Some (perm, gates)
  | Bridge.CompileError e ->
      incr failures;
      Printf.printf "  FAIL  %s did not compile: %s\n%!" name e;
      None

let equal_circuits name a b =
  match Bridge.eq_circ a b with
  | Bridge.EqCircOk (eq, fidelity) ->
      check name (eq && fidelity > 0.999999)
        (Printf.sprintf "equal=%b fidelity=%f" eq fidelity)
  | Bridge.EqCircError e -> check name false e

(* ================================================================== *)
(* E1. general first-order sum case                                    *)
(* ================================================================== *)

let%source sum_case_sugar (s : (q, q) plus) (y : q) =
  case s
    ~left_:(h y)
    ~right_:(z y)

let sum_case_oracle =
  let pqq = P.plus P.q P.q in
  lam ~name:"s" (S.data pqq)
    (S.lolli q (S.tensor (S.data pqq) q))
    { run_lam =
        fun s ->
          lam ~name:"y" q (S.tensor (S.data pqq) q)
            { run_lam =
                fun y ->
                  case ~left:P.q ~right:P.q ~result:P.q
                    ~scrutinee:(use s)
                    ~left_branch:(Op.apply Op.h (use y))
                    ~right_branch:(Op.apply Op.z (use y))
                    ~using:(UR (UL U0)) } }

(* the same sum case at a compound first-order summand type, so the E1
   rule is exercised at asymmetric widths too *)
let%source sum_case_wide (w : ((q, q) tensor, q) plus) (y : q) =
  case w
    ~left_:(s y)
    ~right_:(t y)

let sum_case_wide_oracle =
  let pw = P.plus (P.tensor P.q P.q) P.q in
  lam ~name:"s" (S.data pw)
    (S.lolli q (S.tensor (S.data pw) q))
    { run_lam =
        fun sv ->
          lam ~name:"y" q (S.tensor (S.data pw) q)
            { run_lam =
                fun y ->
                  case ~left:(P.tensor P.q P.q) ~right:P.q ~result:P.q
                    ~scrutinee:(use sv)
                    ~left_branch:(Op.apply Op.s (use y))
                    ~right_branch:(Op.apply Op.t (use y))
                    ~using:(UR (UL U0)) } }

(* ================================================================== *)
(* E3. annotation-directed non-endomorphism host operations            *)
(* ================================================================== *)

let dl_qqq = Op.dist_left P.q P.q P.q

let%source dist_sugar (p : (((q, q) plus, q) tensor)) =
  (dl_qqq : ((((q, q) plus, q) tensor,
              ((q, q) tensor, (q, q) tensor) plus) lolli)) p

let dist_oracle = Op.value dl_qqq

(* E3 composes with the rest of the surface: distribute, then act on the
   still-tagged payload with a second annotated host operation *)
let undl_qqq = Op.undist_left P.q P.q P.q

let%source dist_roundtrip (p : (((q, q) plus, q) tensor)) =
  (undl_qqq : ((((q, q) tensor, (q, q) tensor) plus,
                ((q, q) plus, q) tensor) lolli))
    ((dl_qqq : ((((q, q) plus, q) tensor,
                 ((q, q) tensor, (q, q) tensor) plus) lolli)) p)

let dist_roundtrip_oracle =
  Op.value (Op.compose dl_qqq undl_qqq)

(* ================================================================== *)
(* Datatype layer: exhaustive match, certified permutations            *)
(* ================================================================== *)

type rot3 = P0 | P1 | P2 [@@source.datatype]

(* constructor-name permutation sugar: position i names the destination
   of constructor i (forward) *)
let rot3_shift = Rot3.permute [ P1; P2; P0 ]
let rot3_swap01_inv = Rot3.involution_permute [ P1; P0; P2 ]
let exp_swap01 = Op.exp_i (Float.pi /. 4.0) rot3_swap01_inv
let exp_swap01_half = Op.exp_i (Float.pi /. 2.0) rot3_swap01_inv

let%source match_hst_sugar (d : Rot3.t) (y : q) =
  match d with
  | P0 -> h y
  | P1 -> s y
  | P2 -> t y

(* arm order in the source is free; declaration order is the authority *)
let%source match_hst_shuffled (d : Rot3.t) (y : q) =
  match d with
  | P2 -> t y
  | P0 -> h y
  | P1 -> s y

let%source rot3_shift_sugar (d : Rot3.t) = rot3_shift d
let%source exp_swap01_sugar (d : Rot3.t) = exp_swap01 d
let%source exp_swap01_sq_sugar (d : Rot3.t) = exp_swap01 (exp_swap01 d)
let%source exp_swap01_half_sugar (d : Rot3.t) = exp_swap01_half d

(* handwritten sealed oracles *)
let match_hst_oracle =
  lam ~name:"d" (S.data Rot3.p) (S.lolli q (S.tensor (S.data Rot3.p) q))
    { run_lam =
        fun d ->
          lam ~name:"y" q (S.tensor (S.data Rot3.p) q)
            { run_lam =
                fun y ->
                  Rot3.cases ~result:P.q ~scrutinee:(use d)
                    ~branches:
                      Datatype.(
                        Op.apply Op.h (use y)
                        @: Op.apply Op.s (use y)
                        @: Op.apply Op.t (use y)
                        @: VNil)
                    ~using:(UR (UL U0)) } }

let rot3_shift_raw =
  Linear.(seq0 (assoc_plus_r one one one) (twist_plus (one ++ one) one))

let raw_value_z3 m =
  Linear.(
    emit_oterm
      (olam "p" (one ++ (one ++ one)) (one ++ (one ++ one))
         (oapp (oembed m) (ovar "p" (one ++ (one ++ one))) (SRight SNil))))

(* ================================================================== *)

let () =
  Printf.printf "== E1. general first-order sum case\n";
  (match show "sum_case_sugar" (emit sum_case_sugar) with
  | Some (_, _) -> ()
  | None -> ());
  equal_circuits "sum_case == handwritten sealed case oracle"
    (emit sum_case_sugar) (emit sum_case_oracle);
  (match show "sum_case_wide" (emit sum_case_wide) with
  | Some (_, _) -> ()
  | None -> ());
  equal_circuits "sum_case_wide == handwritten sealed case oracle"
    (emit sum_case_wide) (emit sum_case_wide_oracle);

  Printf.printf "== E3. annotated host operations\n";
  (match show "dist_sugar" (emit dist_sugar) with
  | Some (_, gates) ->
      check "dist_sugar is pure wiring" (gates = 0)
        (Printf.sprintf "gates=%d" gates)
  | None -> ());
  equal_circuits "dist_sugar == Op.value dist_left"
    (emit dist_sugar) (emit dist_oracle);
  (match show "dist_roundtrip" (emit dist_roundtrip) with
  | Some (_, gates) ->
      check "dist_roundtrip is pure wiring" (gates = 0)
        (Printf.sprintf "gates=%d" gates)
  | None -> ());
  equal_circuits "dist_roundtrip == Op.value (dist ; undist)"
    (emit dist_roundtrip) (emit dist_roundtrip_oracle);

  Printf.printf "== datatype match and certified permutations\n";
  (match show "match_hst_sugar" (emit match_hst_sugar) with
  | Some _ -> ()
  | None -> ());
  equal_circuits "match sugar == handwritten sealed cases oracle"
    (emit match_hst_sugar) (emit match_hst_oracle);
  equal_circuits "shuffled arm order == declaration order"
    (emit match_hst_shuffled) (emit match_hst_sugar);
  equal_circuits "Rot3.permute [P1;P2;P0] == raw shift_z3_+1 (forward pin)"
    (emit rot3_shift_sugar)
    (Linear.emit_oterm
       Linear.(
         olam "d" (one ++ (one ++ one)) (one ++ (one ++ one))
           (oapp (oembed rot3_shift_raw)
              (ovar "d" (one ++ (one ++ one)))
              (SRight SNil))));
  ignore raw_value_z3;
  (match show "exp_swap01_sugar" (emit exp_swap01_sugar) with
  | Some _ -> ()
  | None -> ());
  equal_circuits
    "exp_i(pi/4, swap01)^2 == exp_i(pi/2, swap01)  (involution sugar)"
    (emit exp_swap01_sq_sugar) (emit exp_swap01_half_sugar);

  if !failures = 0 then Printf.printf "ALL EXTENSION CHECKS PASSED\n%!"
  else begin
    Printf.printf "%d extension checks FAILED\n%!" !failures;
    exit 1
  end
