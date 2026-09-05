(* Concise Source counterparts for the demo manifest (Phase 2).

   This file holds ONLY object programs: [let%source] bindings,
   [@@source.datatype] declarations, and certified host operations
   assembled from the sealed [Op] combinators.  Everything here is
   surface-authored: no context routing, no explicit witness plumbing,
   no legacy-layer construction, no bridge-term construction.  The
   anti-vacuity scan in [run_counterparts] enforces that lexically.

   Verification lives in [run_counterparts.ml]; legacy oracles live in
   [oracle_legacy.ml] / [oracle_sealed.ml]. *)

module P = Qpl_surface.Source.P
module S = Qpl_surface.Source.S
module Op = Qpl_surface.Source.Op

let s_q = Qpl_surface.Source.q
let s_qbool = Qpl_surface.Source.qbool

(* ================================================================== *)
(* Nominal datatypes (the Qudit(n) abstraction)                        *)
(* ================================================================== *)

type b2 = B0 | B1 [@@source.datatype]
type t3 = T0 | T1 | T2 [@@source.datatype]
type f4 = F0 | F1 | F2 | F3 [@@source.datatype]
type v5 = V0 | V1 | V2 | V3 | V4 [@@source.datatype]
type w8 = W0 | W1 | W2 | W3 | W4 | W5 | W6 | W7 [@@source.datatype]
type bool2 = Bfalse | Btrue [@@source.datatype]
type g8 = Ge | Gg1 | Gg2 | Gg3 | Gg4 | Gg5 | Gg6 | Gg7 [@@source.datatype]
type s8 = Sid | Ssw12 | Ssw13 | Ssw23 | Scyc123 | Scyc132 | SpadA | SpadB
[@@source.datatype]

(* The concrete short-circuit witness type: Qudit(3) with one auxiliary
   label and the two boolean-associated labels.  Its toggle and control
   operations are certified label permutations below.  This is the
   CONCRETE three-state instance; the paper's general Aux + QBool with a
   nontrivial Aux is broader and not claimed here. *)
type w3 = Wsc | Wfalse | Wtrue [@@source.datatype]

(* ================================================================== *)
(* Row 30 — source_quickstart                                          *)
(* ================================================================== *)

let%source cp_quickstart (p : (q, q) tensor) =
  let (l, r) = split p in
  (h l, s r)

(* ================================================================== *)
(* Row 29 — source_fixed_control                                       *)
(* ================================================================== *)

let%source cp_fixed_control (p : (qbool, q) tensor) =
  let (c, tg) = split p in
  case c
    ~zero:(h tg)
    ~one_:(s tg)

(* ================================================================== *)
(* Row 27 — source_datatype (three-way selector)                       *)
(* ================================================================== *)

let three_gate = T3.select ~target:P.q [ Op.h; Op.s; Op.t ]

let%source cp_three (p : (T3.t, q) tensor) = three_gate p

(* ================================================================== *)
(* Rows 28 / 14 / 31 — certified exponentials                          *)
(* ================================================================== *)

let exp_twist_op = Op.exp_i (Float.pi /. 4.0) (Op.involution_twist P.q)

let%source cp_exp_twist (p : (q, q) tensor) = exp_twist_op p

let%source cp_exp_twist_sq (p : (q, q) tensor) =
  exp_twist_op (exp_twist_op p)

let exp_x_op = Op.exp_i (Float.pi /. 4.0) Op.involution_x

let%source cp_exp_x (w : q) = exp_x_op w

(* ================================================================== *)
(* Rows 1 / 11 / 23 — the polymorphic qswitch (visible witness)        *)
(* ================================================================== *)

let%source cp_qswitch (a : 'a P.t)
    (f : ('a, 'a) lolli) (g : ('a, 'a) lolli) (p : (qbool, 'a) tensor) =
  let (b, w) = split p in
  case b
    ~zero:(f (g w))
    ~one_:(g (f w))

(* ================================================================== *)
(* Row 24 — instantiated qswitch family                                *)
(* ================================================================== *)

let%source cp_qswitch_hs (p : (qbool, q) tensor) =
  let (b, w) = split p in
  case b ~zero:(h (s w)) ~one_:(s (h w))

let%source cp_qswitch_xz (p : (qbool, q) tensor) =
  let (b, w) = split p in
  case b ~zero:(x (z w)) ~one_:(z (x w))

let%source cp_qswitch_hy (p : (qbool, q) tensor) =
  let (b, w) = split p in
  case b ~zero:(h (y w)) ~one_:(y (h w))

let%source cp_qswitch_hh (p : (qbool, q) tensor) =
  let (b, w) = split p in
  case b ~zero:(h (h w)) ~one_:(h (h w))

let rz_pi4 = Op.rz (Float.pi /. 4.0)
let rz_pi8 = Op.rz (Float.pi /. 8.0)

let%source cp_qswitch_rz (p : (qbool, q) tensor) =
  let (b, w) = split p in
  case b ~zero:(rz_pi4 (rz_pi8 w)) ~one_:(rz_pi8 (rz_pi4 w))

(* sealed sequential composition of whole qswitches *)
let bq_s = S.tensor s_qbool s_q
let qs_hs_op = Op.seal ~domain:bq_s ~codomain:bq_s cp_qswitch_hs
let qs_xz_op = Op.seal ~domain:bq_s ~codomain:bq_s cp_qswitch_xz
let qs_hy_op = Op.seal ~domain:bq_s ~codomain:bq_s cp_qswitch_hy

let%source cp_qswitch_composed (p : (qbool, q) tensor) =
  qs_xz_op (qs_hs_op p)

let%source cp_qswitch_triple (p : (qbool, q) tensor) =
  qs_hy_op (qs_xz_op (qs_hs_op p))

(* ================================================================== *)
(* Row 23 — qswitch at other first-order payloads                      *)
(* ================================================================== *)

let%source cp_qswitch_qq_cx (p : (qbool, (q, q) tensor) tensor) =
  let (b, w) = split p in
  case b ~zero:(cx (cx w)) ~one_:(cx (cx w))

let%source cp_qswitch_qbool_not (p : (qbool, qbool) tensor) =
  let (b, w) = split p in
  case b ~zero:(not_bool (not_bool w)) ~one_:(not_bool (not_bool w))

let bq_pair_op = Op.tensor Op.not_bool Op.x

let%source cp_qswitch_bq (p : (qbool, (qbool, q) tensor) tensor) =
  let (b, w) = split p in
  case b ~zero:(bq_pair_op (bq_pair_op w)) ~one_:(bq_pair_op (bq_pair_op w))

let idq_op = Op.id s_q

let%source cp_qswitch_idid (p : (qbool, q) tensor) =
  let (b, w) = split p in
  case b ~zero:(idq_op (idq_op w)) ~one_:(idq_op (idq_op w))

(* ================================================================== *)
(* Row 22 — fully η-expanded qswitch at A = Q ⊸ Q                      *)
(* ================================================================== *)

let%source cp_qswitch_eta_endoq
    (f : ((q, q) lolli, (q, q) lolli) lolli)
    (g : ((q, q) lolli, (q, q) lolli) lolli)
    (k : (q, q) lolli)
    (p : (qbool, q) tensor) =
  let (b, w) = split p in
  case b
    ~zero:(g (f k) w)
    ~one_:(f (g k) w)

(* reference shape for the f = g = identity instantiation *)
let%source cp_both_h (p : (qbool, q) tensor) =
  let (b, w) = split p in
  case b ~zero:(h w) ~one_:(h w)

(* ================================================================== *)
(* Row 16 — compose_n (nested application)                             *)
(* ================================================================== *)

let%source cp_compose2 (f1 : (q, q) lolli) (f2 : (q, q) lolli) (w : q) =
  f1 (f2 w)

let%source cp_compose3
    (f1 : (q, q) lolli) (f2 : (q, q) lolli) (f3 : (q, q) lolli) (w : q) =
  f1 (f2 (f3 w))

let%source cp_compose4
    (f1 : (q, q) lolli) (f2 : (q, q) lolli)
    (f3 : (q, q) lolli) (f4 : (q, q) lolli) (w : q) =
  f1 (f2 (f3 (f4 w)))

(* ================================================================== *)
(* Rows 19 / 4 / 5 / 32 — fixed-control family                         *)
(* ================================================================== *)

(* Reading A of the reader's qif: a genuine CNOT *)
let%source cp_qif_cnot (p : (qbool, q) tensor) =
  let (b, tg) = split p in
  case b ~zero:tg ~one_:(x tg)

let%source cp_ctrl_z (p : (qbool, q) tensor) =
  let (b, tg) = split p in
  case b ~zero:tg ~one_:(z tg)

let%source cp_ctrl_h (p : (qbool, q) tensor) =
  let (b, tg) = split p in
  case b ~zero:tg ~one_:(h tg)

let%source cp_ctrl2_x (p : (qbool, (qbool, q) tensor) tensor) =
  let (b, r) = split p in
  case b
    ~zero:r
    ~one_:(let (b2, tg) = split r in
           case b2 ~zero:tg ~one_:(x tg))

let%source cp_ctrl3_x
    (p : (qbool, (qbool, (qbool, q) tensor) tensor) tensor) =
  let (b, r) = split p in
  case b
    ~zero:r
    ~one_:(let (b2, r2) = split r in
           case b2
             ~zero:r2
             ~one_:(let (b3, tg) = split r2 in
                    case b3 ~zero:tg ~one_:(x tg)))

let%source cp_ctrl2_h (p : (qbool, (qbool, q) tensor) tensor) =
  let (b, r) = split p in
  case b
    ~zero:r
    ~one_:(let (b2, tg) = split r in
           case b2 ~zero:tg ~one_:(h tg))

let%source cp_ctrl3_h
    (p : (qbool, (qbool, (qbool, q) tensor) tensor) tensor) =
  let (b, r) = split p in
  case b
    ~zero:r
    ~one_:(let (b2, r2) = split r in
           case b2
             ~zero:r2
             ~one_:(let (b3, tg) = split r2 in
                    case b3 ~zero:tg ~one_:(h tg)))

(* ================================================================== *)
(* Rows 2 / 6 / 7 / 12 / 15 / 17 — selectors                           *)
(* ================================================================== *)

let sel2_hs = B2.select ~target:P.q [ Op.h; Op.s ]
let%source cp_select2_hs (p : (B2.t, q) tensor) = sel2_hs p

let sel3_hst = T3.select ~target:P.q [ Op.h; Op.s; Op.t ]
let%source cp_select3_hst (p : (T3.t, q) tensor) = sel3_hst p

let sel4_hstx = F4.select ~target:P.q [ Op.h; Op.s; Op.t; Op.x ]
let%source cp_select4_hstx (p : (F4.t, q) tensor) = sel4_hstx p

let sel4_xthx = F4.select ~target:P.q [ Op.x; Op.t; Op.h; Op.x ]
let%source cp_select4_xthx (p : (F4.t, q) tensor) = sel4_xthx p

let sel4_hhss = F4.select ~target:P.q [ Op.h; Op.h; Op.s; Op.s ]
let%source cp_select4_hhss (p : (F4.t, q) tensor) = sel4_hhss p

let sel5_hstxy = V5.select ~target:P.q [ Op.h; Op.s; Op.t; Op.x; Op.y ]
let%source cp_select5_hstxy (p : (V5.t, q) tensor) = sel5_hstxy p

(* ================================================================== *)
(* Row 8 — datatype declarations and controlled dispatch               *)
(* ================================================================== *)

let bool2_hx = Bool2.select ~target:P.q [ Op.h; Op.x ]
let%source cp_bool2_hx (p : (Bool2.t, q) tensor) = bool2_hx p

(* ================================================================== *)
(* Row 33 — Z_n controlled phases                                      *)
(* ================================================================== *)

let z2_phase_sel = B2.select ~target:P.q [ Op.id s_q; Op.z ]
let%source cp_z2_phase (p : (B2.t, q) tensor) = z2_phase_sel p

let z4_phase_sel =
  F4.select ~target:P.q
    [ Op.rz 0.0; Op.rz 0.5; Op.rz 1.0; Op.rz 1.5 ]
let%source cp_z4_phase (p : (F4.t, q) tensor) = z4_phase_sel p

let z4_phase_inv_sel =
  F4.select ~target:P.q
    [ Op.rz (-0.0); Op.rz (-0.5); Op.rz (-1.0); Op.rz (-1.5) ]
let%source cp_z4_phase_roundtrip (p : (F4.t, q) tensor) =
  z4_phase_inv_sel (z4_phase_sel p)

let z5_phase_sel =
  V5.select ~target:P.q
    [ Op.rz 0.0; Op.rz 0.4; Op.rz 0.8; Op.rz 1.2; Op.rz 1.6 ]
let%source cp_z5_phase (p : (V5.t, q) tensor) = z5_phase_sel p

let z8_phase_sel =
  W8.select ~target:P.q
    [ Op.rz 0.0; Op.rz 0.25; Op.rz 0.5; Op.rz 0.75;
      Op.rz 1.0; Op.rz 1.25; Op.rz 1.5; Op.rz 1.75 ]
let%source cp_z8_phase (p : (W8.t, q) tensor) = z8_phase_sel p

let z8_phase_inv_sel =
  W8.select ~target:P.q
    [ Op.rz (-0.0); Op.rz (-0.25); Op.rz (-0.5); Op.rz (-0.75);
      Op.rz (-1.0); Op.rz (-1.25); Op.rz (-1.5); Op.rz (-1.75) ]
let%source cp_z8_phase_roundtrip (p : (W8.t, q) tensor) =
  z8_phase_inv_sel (z8_phase_sel p)

(* ================================================================== *)
(* Row 34 — Z_2 group operations (the Z_n, n ≥ 3 shifts await the      *)
(* certified datatype label-permutation operation — recorded E2)       *)
(* ================================================================== *)

let%source cp_z2_shift (b : qbool) = not_bool b

let z2_add_sel = B2.select ~target:P.qbool [ Op.id s_qbool; Op.not_bool ]
let%source cp_z2_add (p : (B2.t, qbool) tensor) = z2_add_sel p
let%source cp_z2_add_sq (p : (B2.t, qbool) tensor) =
  z2_add_sel (z2_add_sel p)

(* ================================================================== *)
(* Row 3 — algorithm cores (oracles and transforms as host ops)        *)
(* ================================================================== *)

let h_on_first = Op.tensor Op.h (Op.id s_q)

let%source cp_dj_constant (p : (q, q) tensor) =
  h_on_first (h_on_first p)

let%source cp_dj_balanced (p : (q, q) tensor) =
  h_on_first (cx (h_on_first p))

let qq_s = S.tensor s_q s_q
let hsp2_uf = Op.tensor Op.cx (Op.id qq_s)
let hsp2_qft = Op.tensor (Op.tensor Op.h Op.h) (Op.id qq_s)

let%source cp_hsp_2q (p : ((q, q) tensor, (q, q) tensor) tensor) =
  hsp2_qft (hsp2_uf p)

(* ================================================================== *)
(* Row 18 — concrete phase marking (relative phase through case)       *)
(* ================================================================== *)

let phase_neg1 = Op.phase { Complex.re = -1.0; im = 0.0 } P.q
let phase_i = Op.phase { Complex.re = 0.0; im = 1.0 } P.q

let%source cp_phase_mark (p : (qbool, q) tensor) =
  let (b, tg) = split p in
  case b ~zero:(phase_neg1 tg) ~one_:tg

let phase_mark_op = Op.seal ~domain:bq_s ~codomain:bq_s cp_phase_mark

let%source cp_phase_mark_sq (p : (qbool, q) tensor) =
  phase_mark_op (phase_mark_op p)

let%source cp_phase_mark_i (p : (qbool, q) tensor) =
  let (b, tg) = split p in
  case b ~zero:(phase_i tg) ~one_:tg

let phase_mark_i_op = Op.seal ~domain:bq_s ~codomain:bq_s cp_phase_mark_i

let%source cp_phase_mark_i4 (p : (qbool, q) tensor) =
  phase_mark_i_op (phase_mark_i_op (phase_mark_i_op (phase_mark_i_op p)))

(* ================================================================== *)
(* Rows 9 / 10 — certified distributors (E3 annotations)               *)
(* ================================================================== *)

let ab_p = P.plus P.q (P.tensor P.q P.q)
let dl_unequal = Op.dist_left P.q (P.tensor P.q P.q) P.q

let%source cp_dist_unequal (p : (((q, (q, q) tensor) plus, q) tensor)) =
  (dl_unequal
    : ((((q, (q, q) tensor) plus, q) tensor,
        ((q, q) tensor, ((q, q) tensor, q) tensor) plus) lolli)) p

let idx_on_c = Op.tensor (Op.id (S.data ab_p)) Op.x

let%source cp_dist_pl (p : (((q, (q, q) tensor) plus, q) tensor)) =
  (dl_unequal
    : ((((q, (q, q) tensor) plus, q) tensor,
        ((q, q) tensor, ((q, q) tensor, q) tensor) plus) lolli))
    (idx_on_c p)

(* ================================================================== *)
(* Row 20 — QS_2 dummy-register simulator                              *)
(* ================================================================== *)

let s_d2 = S.tensor s_q s_q
let s_regs3 = S.tensor s_q s_d2

let swap_t_d1 =
  Op.compose (Op.assoc_right s_q s_q s_q)
    (Op.compose
       (Op.tensor (Op.twist s_q s_q) (Op.id s_q))
       (Op.assoc_left s_q s_q s_q))

let swap_d1_d2 = Op.tensor (Op.id s_q) (Op.twist s_q s_q)

let swap_t_d2 = Op.compose swap_d1_d2 (Op.compose swap_t_d1 swap_d1_d2)

let%source cp_qs2_r (p : (qbool, (q, (q, q) tensor) tensor) tensor) =
  let (c, r) = split p in
  case c ~zero:(swap_t_d1 r) ~one_:(swap_t_d2 r)

let f_dummies = Op.tensor (Op.id s_q) (Op.tensor Op.x Op.h)
let bregs_s = S.tensor s_qbool s_regs3
let qs2_r_op = Op.seal ~domain:bregs_s ~codomain:bregs_s cp_qs2_r
let id_and_f = Op.tensor (Op.id s_qbool) f_dummies

let%source cp_qs2_round (p : (qbool, (q, (q, q) tensor) tensor) tensor) =
  qs2_r_op (id_and_f (qs2_r_op p))

let qs2_round_op = Op.seal ~domain:bregs_s ~codomain:bregs_s cp_qs2_round

(* Inter-round routing as certified tensor coherences, mirroring the
   legacy construction structurally.  (The surface split-of-application
   form of this pipeline is refused by the relational SeqCut authority —
   a recorded Phase-2 finding.) *)
let qs2_rearr_1 =
  Op.compose (Op.assoc_left s_qbool s_qbool s_regs3)
    (Op.compose
       (Op.tensor (Op.id s_qbool) (Op.twist s_qbool s_regs3))
       (Op.assoc_right s_qbool s_regs3 s_qbool))

let qs2_round_x_id = Op.tensor qs2_round_op (Op.id s_qbool)

let qs2_rearr_2 =
  Op.compose (Op.twist (S.tensor s_qbool s_regs3) s_qbool)
    (Op.compose
       (Op.tensor (Op.id s_qbool) (Op.twist s_qbool s_regs3))
       (Op.assoc_right s_qbool s_regs3 s_qbool))

let qs2_rearr_3 =
  Op.compose (Op.assoc_left s_qbool s_regs3 s_qbool)
    (Op.compose
       (Op.tensor (Op.id s_qbool) (Op.twist s_regs3 s_qbool))
       (Op.compose
          (Op.assoc_right s_qbool s_qbool s_regs3)
          (Op.tensor (Op.twist s_qbool s_qbool) (Op.id s_regs3))))

let qs2_sim_op =
  Op.compose qs2_rearr_1
    (Op.compose qs2_round_x_id
       (Op.compose qs2_rearr_2 (Op.compose qs2_round_x_id qs2_rearr_3)))

let%source cp_qs2_sim
    (p : ((qbool, qbool) tensor, (q, (q, q) tensor) tensor) tensor) =
  qs2_sim_op p

(* ================================================================== *)
(* Row 21 — QS_3 (S_3 control as an 8-label qudit)                     *)
(* ================================================================== *)

let s_d23 = S.tensor s_q s_q
let s_regs4 = S.tensor s_q (S.tensor s_q s_d23)
let regs4_p = P.tensor P.q (P.tensor P.q (P.tensor P.q P.q))

let sw01 =
  Op.compose (Op.assoc_right s_q s_q s_d23)
    (Op.compose
       (Op.tensor (Op.twist s_q s_q) (Op.id s_d23))
       (Op.assoc_left s_q s_q s_d23))

let sw12 =
  Op.tensor (Op.id s_q)
    (Op.compose (Op.assoc_right s_q s_q s_q)
       (Op.compose
          (Op.tensor (Op.twist s_q s_q) (Op.id s_q))
          (Op.assoc_left s_q s_q s_q)))

let sw23 = Op.tensor (Op.id s_q) (Op.tensor (Op.id s_q) (Op.twist s_q s_q))

let qs3_swap1 = sw01
let qs3_swap2 = Op.compose sw01 (Op.compose sw12 sw01)
let qs3_swap3 =
  Op.compose sw01 (Op.compose sw12 (Op.compose sw23 (Op.compose sw12 sw01)))

let qs3_r1_sel =
  S8.select ~target:regs4_p
    [ qs3_swap1; qs3_swap2; qs3_swap3; qs3_swap1;
      qs3_swap2; qs3_swap3; qs3_swap1; qs3_swap1 ]

let qs3_r2_sel =
  S8.select ~target:regs4_p
    [ qs3_swap2; qs3_swap1; qs3_swap2; qs3_swap3;
      qs3_swap3; qs3_swap1; qs3_swap2; qs3_swap2 ]

let qs3_r3_sel =
  S8.select ~target:regs4_p
    [ qs3_swap3; qs3_swap3; qs3_swap1; qs3_swap2;
      qs3_swap1; qs3_swap2; qs3_swap3; qs3_swap3 ]

let qs3_f = Op.tensor (Op.id s_q) (Op.tensor Op.x (Op.tensor Op.h Op.z))
let qs3_id_f = Op.tensor (Op.id (S.data S8.p)) qs3_f

let qs3_round_of sel = Op.compose sel (Op.compose qs3_id_f sel)
let qs3_round1 = qs3_round_of qs3_r1_sel
let qs3_round2 = qs3_round_of qs3_r2_sel
let qs3_round3 = qs3_round_of qs3_r3_sel

(* rounds run 1 then 2 then 3, so round1 is innermost *)
let%source cp_qs3_sim
    (p : (S8.t, (q, (q, (q, q) tensor) tensor) tensor) tensor) =
  qs3_round3 (qs3_round2 (qs3_round1 p))

(* target-only composed dispatch (the clean-garbage reference content) *)
let tgt_of a b c = Op.compose a (Op.compose b c)
let tgt_id = tgt_of Op.x Op.h Op.z
let tgt_sw12 = tgt_of Op.h Op.x Op.z
let tgt_sw13 = tgt_of Op.z Op.h Op.x
let tgt_sw23 = tgt_of Op.x Op.z Op.h
let tgt_c123 = tgt_of Op.h Op.z Op.x
let tgt_c132 = tgt_of Op.z Op.x Op.h

let qs3_target_sel =
  S8.select ~target:P.q
    [ tgt_id; tgt_sw12; tgt_sw13; tgt_sw23;
      tgt_c123; tgt_c132; tgt_id; tgt_id ]

let%source cp_qs3_target (p : (S8.t, q) tensor) = qs3_target_sel p

(* ================================================================== *)
(* Datatype-layer closures (rows 13, 14, 18, 26, 34)                   *)
(* ================================================================== *)

type z11 = N0 | N1 | N2 | N3 | N4 | N5 | N6 | N7 | N8 | N9 | N10
[@@source.datatype]

(* ---- row 34: Z_n group operations from certified permutations ---- *)

let z3_shift1 = T3.permute [ T1; T2; T0 ]
let z3_shift2 = T3.permute [ T2; T0; T1 ]
let z3_neg = T3.permute [ T0; T2; T1 ]
let z3_add = T3.select ~target:T3.p [ Op.id T3.s; z3_shift1; z3_shift2 ]

let%source cp_z3_shift (d : T3.t) = z3_shift1 d
let%source cp_z3_neg (d : T3.t) = z3_neg d
let%source cp_z3_neg_sq (d : T3.t) = z3_neg (z3_neg d)
let%source cp_z3_add (p : (T3.t, T3.t) tensor) = z3_add p

let z4_shift1 = F4.permute [ F1; F2; F3; F0 ]
let z4_shift2 = F4.permute [ F2; F3; F0; F1 ]
let z4_shift3 = F4.permute [ F3; F0; F1; F2 ]
let z4_neg = F4.permute [ F0; F3; F2; F1 ]
let z4_add =
  F4.select ~target:F4.p [ Op.id F4.s; z4_shift1; z4_shift2; z4_shift3 ]

let%source cp_z4_shift (d : F4.t) = z4_shift1 d
let%source cp_z4_neg (d : F4.t) = z4_neg d
let%source cp_z4_add (p : (F4.t, F4.t) tensor) = z4_add p

let z5_shift1 = V5.permute [ V1; V2; V3; V4; V0 ]
let z5_shift2 = V5.permute [ V2; V3; V4; V0; V1 ]
let z5_shift3 = V5.permute [ V3; V4; V0; V1; V2 ]
let z5_shift4 = V5.permute [ V4; V0; V1; V2; V3 ]
let z5_neg = V5.permute [ V0; V4; V3; V2; V1 ]
let z5_add =
  V5.select ~target:V5.p
    [ Op.id V5.s; z5_shift1; z5_shift2; z5_shift3; z5_shift4 ]

let%source cp_z5_shift (d : V5.t) = z5_shift1 d
let%source cp_z5_neg (d : V5.t) = z5_neg d
let%source cp_z5_shift_cycle (d : V5.t) =
  z5_shift1 (z5_shift1 (z5_shift1 (z5_shift1 (z5_shift1 d))))
let%source cp_z5_add (p : (V5.t, V5.t) tensor) = z5_add p

let z8_shift1 = W8.permute [ W1; W2; W3; W4; W5; W6; W7; W0 ]
let z8_neg = W8.permute [ W0; W7; W6; W5; W4; W3; W2; W1 ]
let z8_shift_of k =
  let rec go n acc = if n = 0 then acc else go (n - 1) (Op.compose acc z8_shift1) in
  if k = 0 then Op.id W8.s else go (k - 1) z8_shift1
let z8_add =
  W8.select ~target:W8.p
    [ z8_shift_of 0; z8_shift_of 1; z8_shift_of 2; z8_shift_of 3;
      z8_shift_of 4; z8_shift_of 5; z8_shift_of 6; z8_shift_of 7 ]

let%source cp_z8_shift (d : W8.t) = z8_shift1 d
let%source cp_z8_neg (d : W8.t) = z8_neg d
let%source cp_z8_add (p : (W8.t, W8.t) tensor) = z8_add p

let z11_shift1 =
  Z11.permute [ N1; N2; N3; N4; N5; N6; N7; N8; N9; N10; N0 ]
let z11_neg =
  Z11.permute [ N0; N10; N9; N8; N7; N6; N5; N4; N3; N2; N1 ]
let z11_shift_of k =
  let rec go n acc = if n = 0 then acc else go (n - 1) (Op.compose acc z11_shift1) in
  if k = 0 then Op.id Z11.s else go (k - 1) z11_shift1
let z11_add =
  Z11.select ~target:Z11.p
    [ z11_shift_of 0; z11_shift_of 1; z11_shift_of 2; z11_shift_of 3;
      z11_shift_of 4; z11_shift_of 5; z11_shift_of 6; z11_shift_of 7;
      z11_shift_of 8; z11_shift_of 9; z11_shift_of 10 ]

let%source cp_z11_shift (d : Z11.t) = z11_shift1 d
let%source cp_z11_neg (d : Z11.t) = z11_neg d
let%source cp_z11_neg_sq (d : Z11.t) = z11_neg (z11_neg d)
let%source cp_z11_add (p : (Z11.t, Z11.t) tensor) = z11_add p

(* ---- row 13: branch-swap involutions and their exponentials ---- *)

let t3q_swap12 =
  Op.involution_tensor (T3.involution_permute [ T1; T0; T2 ])
    (Op.involution_id P.q)

let t3q_swap23 =
  Op.involution_tensor (T3.involution_permute [ T0; T2; T1 ])
    (Op.involution_id P.q)

let e12_pi4 = Op.exp_i (Float.pi /. 4.0) t3q_swap12
let e23_pi4 = Op.exp_i (Float.pi /. 4.0) t3q_swap23
let e12_pi2 = Op.exp_i (Float.pi /. 2.0) t3q_swap12
let e23_pi2 = Op.exp_i (Float.pi /. 2.0) t3q_swap23

let%source cp_exp_swap12 (p : (T3.t, q) tensor) = e12_pi4 p
let%source cp_exp_swap23 (p : (T3.t, q) tensor) = e23_pi4 p
let%source cp_exp_swap12_sq (p : (T3.t, q) tensor) = e12_pi4 (e12_pi4 p)
let%source cp_exp_swap23_sq (p : (T3.t, q) tensor) = e23_pi4 (e23_pi4 p)
let%source cp_exp_swap12_half (p : (T3.t, q) tensor) = e12_pi2 p
let%source cp_exp_swap23_half (p : (T3.t, q) tensor) = e23_pi2 p
let%source cp_exp_e12_e23 (p : (T3.t, q) tensor) = e23_pi4 (e12_pi4 p)
let%source cp_exp_e23_e12 (p : (T3.t, q) tensor) = e12_pi4 (e23_pi4 p)

(* ---- row 14 residue: the plus-swap exponential as the two-label ---- *)
(* ---- datatype involution                                        ---- *)

let exp_twist_plus_op =
  Op.exp_i (Float.pi /. 4.0) (B2.involution_permute [ B1; B0 ])

let%source cp_exp_twist_plus (b : B2.t) = exp_twist_plus_op b

(* ---- row 18 residue: per-label phased dispatch, derived from ---- *)
(* ---- Op.phase composed into select branches                  ---- *)

let c_neg1 = { Complex.re = -1.0; im = 0.0 }
let c_plusi = { Complex.re = 0.0; im = 1.0 }

let phased3_sel =
  T3.select ~target:P.q
    [ Op.compose Op.x (Op.phase c_neg1 P.q);
      Op.compose Op.h (Op.phase c_plusi P.q);
      Op.z ]

let%source cp_phased_select (p : (T3.t, q) tensor) = phased3_sel p

let phased3_single =
  T3.select ~target:P.q
    [ Op.phase c_neg1 P.q; Op.id s_q; Op.id s_q ]

let%source cp_phased_single_sq (p : (T3.t, q) tensor) =
  phased3_single (phased3_single p)

(* ---- row 26: the concrete W3 short-circuit witness (Qudit(3); ---- *)
(* ---- NOT the paper's general Aux + QBool with nontrivial Aux) ---- *)

let w3_toggle = W3.permute [ Wsc; Wtrue; Wfalse ]
let w3_s = S.data W3.p

let%source cp_w3_toggle (w : W3.t) = w3_toggle w
let%source cp_w3_toggle_sq (w : W3.t) = w3_toggle (w3_toggle w)

let w3_id = Op.id w3_s

let%source cp_ctrl_w (p : (qbool, W3.t) tensor) =
  let (b, w) = split p in
  case b
    ~zero:(w3_toggle w)
    ~one_:(w3_id w)

let bw_s = S.tensor s_qbool w3_s
let ctrl_w_op = Op.seal ~domain:bw_s ~codomain:bw_s cp_ctrl_w

let and_route_in =
  Op.compose (Op.assoc_left s_qbool s_qbool w3_s)
    (Op.compose
       (Op.tensor (Op.id s_qbool) (Op.twist s_qbool w3_s))
       (Op.assoc_right s_qbool w3_s s_qbool))

let and_mid = Op.tensor ctrl_w_op (Op.id s_qbool)

let and_route_out =
  Op.compose (Op.assoc_left s_qbool w3_s s_qbool)
    (Op.compose
       (Op.tensor (Op.id s_qbool) (Op.twist w3_s s_qbool))
       (Op.assoc_right s_qbool s_qbool w3_s))

let and_sc_op =
  Op.compose and_route_in (Op.compose and_mid and_route_out)

let%source cp_and_sc (p : ((qbool, qbool) tensor, W3.t) tensor) =
  and_sc_op p

let%source cp_and_sc_sq (p : ((qbool, qbool) tensor, W3.t) tensor) =
  and_sc_op (and_sc_op p)
