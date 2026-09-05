(* Legacy Raw/Linear oracle constructions, copied from the retained demos.

   These are ORACLES ONLY: each is the demo's own construction (or the
   demo's own mathematical reference), kept so the concise counterparts in
   [surface_programs.ml] can be compared against the legacy implementation
   through the bridge.  This file is explicitly excluded from the
   anti-vacuity lexical scan. *)

open Qpl_surface
open Linear

let bool_ty = one ++ one

(** Wrap an A → A hom as the equivalent function value λp. m(p), so its
    compiled boundary matches a sealed lam of the same type. *)
let as_value (ty : 'a ty) (m : (unit, [`Lolli of 'a * 'a]) prog) =
  olam "p" ty ty (oapp (oembed m) (ovar "p" ty) (SRight SNil))

(* ------------------------------------------------------------------ *)
(* qswitch family (qswitch_instantiated_e2e.ml)                        *)
(* ------------------------------------------------------------------ *)

let qswitch f g =
  let left = make_branch q one (seq0 g f) in
  let right = make_branch q one (seq0 f g) in
  seq0 (twist_tensor bool_ty q) (case_hom one one q q left right)

(* generic payload version (qswitch_eta_expansion_e2e.ml) *)
let qswitch_generic (a_ty : 'a ty) f g =
  let left = make_branch a_ty one (seq0 g f) in
  let right = make_branch a_ty one (seq0 f g) in
  seq0 (twist_tensor bool_ty a_ty) (case_hom one one a_ty a_ty left right)

(* meta-level QSwitch[H,S] (abstract_qswitch_oterm_e2e.ml Part 3) *)
let meta_qswitch_hs =
  let left = make_branch q one (seq0 gate_s gate_h) in
  let right = make_branch q one (seq0 gate_h gate_s) in
  seq0 (twist_tensor bool_ty q) (case_hom one one q q left right)

(* ------------------------------------------------------------------ *)
(* ctrl combinator (verify_nested_ctrl_e2e.ml / ctrl_lambda_e2e.ml)    *)
(* ------------------------------------------------------------------ *)

let ctrl (a_ty : 'a ty) (f : (unit, [`Lolli of 'a * 'a]) prog) =
  let ia_ty = one ** a_ty in
  let distribute = dist_l one one a_ty in
  let left_branch = id ia_ty in
  let right_branch = par0 (id one) f in
  let apply_branches = omap0 ia_ty ia_ty left_branch right_branch in
  let undistribute = undist_l one one a_ty in
  seq0 distribute (seq0 apply_branches undistribute)

let bq = bool_ty ** q
let bbq = bool_ty ** bq

let ctrl1_x = ctrl q gate_x
let ctrl2_x = ctrl bq ctrl1_x
let ctrl3_x = ctrl bbq ctrl2_x
let ctrl1_h = ctrl q gate_h
let ctrl2_h = ctrl bq ctrl1_h
let ctrl3_h = ctrl bbq ctrl2_h
let ctrl1_z = ctrl q gate_z

(* apply H in both branches — reference for the eta-qswitch shape *)
let both_h_raw =
  let branch_l = make_branch q one gate_h in
  let branch_r = make_branch q one gate_h in
  seq0 (twist_tensor bool_ty q) (case_hom one one q q branch_l branch_r)

(* qif Reading A elaboration (qif_cnot_verify_e2e.ml) *)
let qif_apply =
  let else_branch = make_branch q one (id q) in
  let then_branch = make_branch q one gate_x in
  seq0 (twist_tensor bool_ty q) (case_hom one one q q else_branch then_branch)

(* ------------------------------------------------------------------ *)
(* Meta controls over declared datatypes                                *)
(* ------------------------------------------------------------------ *)

let z2_dt = datatype ~name:"Z2o" ~arity:2 ~labels:["0"; "1"] ~ops:[]
let z3_dt = datatype ~name:"Z3o" ~arity:3 ~labels:["0"; "1"; "2"] ~ops:[]
let z4_dt = datatype ~name:"Z4o" ~arity:4 ~labels:["0"; "1"; "2"; "3"] ~ops:[]
let z5_dt = datatype ~name:"Z5o" ~arity:5
    ~labels:["0"; "1"; "2"; "3"; "4"] ~ops:[]
let z8_dt = datatype ~name:"Z8o" ~arity:8
    ~labels:["0"; "1"; "2"; "3"; "4"; "5"; "6"; "7"] ~ops:[]

let meta_z2_hs () = control z2_dt q [| gate_h; gate_s |]
let meta_z2_hx () = control z2_dt q [| gate_h; gate_x |]
let meta_z3_hst () = control z3_dt q [| gate_h; gate_s; gate_t |]
let meta_z4_hstx () = control z4_dt q [| gate_h; gate_s; gate_t; gate_x |]
let meta_z4_xthx () = control z4_dt q [| gate_x; gate_t; gate_h; gate_x |]
let meta_z4_hhss () = control z4_dt q [| gate_h; gate_h; gate_s; gate_s |]
let meta_z5_hstxy () = control z5_dt q [| gate_h; gate_s; gate_t; gate_x; gate_y |]

(* Z_n controlled phases (zn_controlled_phase_e2e.ml) *)
let z2_phase () = control z2_dt q [| id q; gate_z |]
let z4_phase () =
  control z4_dt q (Array.init 4 (fun m -> gate_rz (float_of_int m *. 0.5)))
let z5_phase () =
  control z5_dt q (Array.init 5 (fun m -> gate_rz (2.0 *. float_of_int m /. 5.0)))
let z8_phase () =
  control z8_dt q (Array.init 8 (fun m -> gate_rz (float_of_int m *. 0.25)))

let z2q_id () = id (rep_ty z2_dt ** q)
let z4q_id () = id (rep_ty z4_dt ** q)
let z8q_id () = id (rep_ty z8_dt ** q)

(* Z_2 group operations (zn_group_ops_e2e.ml) *)
let shift_z2_plus1 = twist_plus one one
let add_z2 () = control z2_dt (one ++ one) [| id (one ++ one); shift_z2_plus1 |]
let z2z2_id () = id (rep_ty z2_dt ** (one ++ one))

(* ------------------------------------------------------------------ *)
(* Algorithm cores (algorithms_e2e.ml)                                  *)
(* ------------------------------------------------------------------ *)

let dj_core uf = seq0 (par0 gate_h (id q)) (seq0 uf (par0 gate_h (id q)))
let dj_constant = dj_core (id (q ** q))
let dj_balanced = dj_core gate_cx

let hsp_2q =
  let uf = par0 gate_cx (id (q ** q)) in
  let qft_g = par0 gate_h gate_h in
  seq0 uf (par0 qft_g (id (q ** q)))

(* ------------------------------------------------------------------ *)
(* Exponentials (exp_twist_e2e.ml)                                      *)
(* ------------------------------------------------------------------ *)

let exp_twist_single = exp_i (Float.pi /. 4.0) (twist_tensor q q)
let exp_twist_half_pi = exp_i (Float.pi /. 2.0) (twist_tensor q q)
let exp_x_single = exp_i (Float.pi /. 4.0) gate_x

(* ------------------------------------------------------------------ *)
(* Relative phase marking (raw reference for row 18)                    *)
(* ------------------------------------------------------------------ *)

let neg_one = Complex.neg Complex.one

(* phase (-1) on the payload when tag = 0, identity when tag = 1 *)
let phase_mark_raw =
  let zero_branch = make_branch q one (phase neg_one q) in
  let one_branch = make_branch q one (id q) in
  seq0 (twist_tensor bool_ty q) (case_hom one one q q zero_branch one_branch)

let bq_id = id (bool_ty ** q)

(* ------------------------------------------------------------------ *)
(* Distributors (dist probes)                                           *)
(* ------------------------------------------------------------------ *)

let dist_unequal_raw = dist_l q (q ** q) q

let p_l_raw = seq0 (par0 (id (q ++ (q ** q))) gate_x) (dist_l q (q ** q) q)

(** hom with distinct domain/codomain wrapped as a function value *)
let as_value2 (dom : 'a ty) (cod : 'b ty)
    (m : (unit, [`Lolli of 'a * 'b]) prog) =
  olam "p" dom cod (oapp (oembed m) (ovar "p" dom) (SRight SNil))

(* ------------------------------------------------------------------ *)
(* QS_2 dummy-register simulator (qs2_dummy_sim_e2e.ml)                 *)
(* ------------------------------------------------------------------ *)

let regs_ty = q ** (q ** q)

let swap_T_D1 =
  seq0 (assoc_tensor_r q q q)
    (seq0 (par0 (twist_tensor q q) (id q)) (assoc_tensor_l q q q))

let swap_T_D2 =
  let s12 = par0 (id q) (twist_tensor q q) in
  seq0 s12 (seq0 swap_T_D1 s12)

let qs2_r_op =
  let branch_L =
    seq0 (par0 swap_T_D1 (id one)) (twist_tensor regs_ty one)
  in
  let branch_R =
    seq0 (par0 swap_T_D2 (id one)) (twist_tensor regs_ty one)
  in
  seq0 (twist_tensor bool_ty regs_ty)
    (case_hom one one regs_ty regs_ty branch_L branch_R)

let qs2_f_op = par0 (id q) (par0 gate_x gate_h)

let qs2_round_op =
  let id_bool_and_f = par0 (id bool_ty) qs2_f_op in
  seq0 qs2_r_op (seq0 id_bool_and_f qs2_r_op)

let qs2_sim =
  let rearr_1 =
    seq0 (assoc_tensor_l bool_ty bool_ty regs_ty)
      (seq0 (par0 (id bool_ty) (twist_tensor bool_ty regs_ty))
         (assoc_tensor_r bool_ty regs_ty bool_ty))
  in
  let round_1 = par0 qs2_round_op (id bool_ty) in
  let rearr_2 =
    seq0 (twist_tensor (bool_ty ** regs_ty) bool_ty)
      (seq0 (par0 (id bool_ty) (twist_tensor bool_ty regs_ty))
         (assoc_tensor_r bool_ty regs_ty bool_ty))
  in
  let round_2 = par0 qs2_round_op (id bool_ty) in
  let rearr_3 =
    seq0 (assoc_tensor_l bool_ty regs_ty bool_ty)
      (seq0 (par0 (id bool_ty) (twist_tensor regs_ty bool_ty))
         (seq0 (assoc_tensor_r bool_ty bool_ty regs_ty)
            (par0 (twist_tensor bool_ty bool_ty) (id regs_ty))))
  in
  seq0 rearr_1 (seq0 round_1 (seq0 rearr_2 (seq0 round_2 rearr_3)))

(* ------------------------------------------------------------------ *)
(* QS_3 components (qs3_pn_dummy_sim_e2e.ml)                            *)
(* ------------------------------------------------------------------ *)

let dummies3_ty = q ** (q ** q)
let regs4_ty = q ** dummies3_ty

let s3_datatype =
  datatype ~name:"S3paddedO" ~arity:8
    ~labels:["id"; "swap_12"; "swap_13"; "swap_23"; "cyc_123"; "cyc_132";
             "pad_id_a"; "pad_id_b"]
    ~ops:[]

let qs3_swap_wires_0_1 =
  let d23 = q ** q in
  seq0 (assoc_tensor_r q q d23)
    (seq0 (par0 (twist_tensor q q) (id d23)) (assoc_tensor_l q q d23))

let qs3_swap_wires_1_2 =
  par0 (id q)
    (seq0 (assoc_tensor_r q q q)
       (seq0 (par0 (twist_tensor q q) (id q)) (assoc_tensor_l q q q)))

let qs3_swap_wires_2_3 = par0 (id q) (par0 (id q) (twist_tensor q q))

let qs3_swap_1 = qs3_swap_wires_0_1
let qs3_swap_2 = seq0 qs3_swap_wires_0_1 (seq0 qs3_swap_wires_1_2 qs3_swap_wires_0_1)
let qs3_swap_3 =
  seq0 qs3_swap_wires_0_1
    (seq0 qs3_swap_wires_1_2
       (seq0 qs3_swap_wires_2_3 (seq0 qs3_swap_wires_1_2 qs3_swap_wires_0_1)))

let qs3_compose_seq gates =
  List.fold_left (fun acc g -> seq0 acc g) (id q) gates

let qs3_target_id = qs3_compose_seq [gate_x; gate_h; gate_z]
let qs3_target_swap_12 = qs3_compose_seq [gate_h; gate_x; gate_z]
let qs3_target_swap_13 = qs3_compose_seq [gate_z; gate_h; gate_x]
let qs3_target_swap_23 = qs3_compose_seq [gate_x; gate_z; gate_h]
let qs3_target_cyc_123 = qs3_compose_seq [gate_h; gate_z; gate_x]
let qs3_target_cyc_132 = qs3_compose_seq [gate_z; gate_x; gate_h]

let qs3_target_only_ctrl () =
  control s3_datatype q
    [| qs3_target_id; qs3_target_swap_12; qs3_target_swap_13;
       qs3_target_swap_23; qs3_target_cyc_123; qs3_target_cyc_132;
       qs3_target_id; qs3_target_id |]

let qs3_r_round_1 () =
  control s3_datatype regs4_ty
    [| qs3_swap_1; qs3_swap_2; qs3_swap_3; qs3_swap_1;
       qs3_swap_2; qs3_swap_3; qs3_swap_1; qs3_swap_1 |]

(* ------------------------------------------------------------------ *)
(* Nested-apply meta compositions (nested_apply_e2e.ml)                 *)
(* ------------------------------------------------------------------ *)

let meta_hs = seq0 gate_s gate_h        (* compose_2 (H, S) = S ; H *)
let meta_hh = seq0 gate_h gate_h
let meta_hst = seq0 gate_t (seq0 gate_s gate_h)
let meta_hstx = seq0 gate_x (seq0 gate_t (seq0 gate_s gate_h))

(* select_2 closed structural form (abstract_select_2_e2e.ml Part 3.5) *)
let closed_select_2_hs =
  let ia_ty = one ** q in
  let l = par0 (id one) gate_h in
  let r = par0 (id one) gate_s in
  let pm = omap0 ia_ty ia_ty l r in
  seq0 (seq0 (dist_l one one q) pm) (undist_l one one q)

(* ------------------------------------------------------------------ *)
(* Branch-swap exponentials on T = Q + (Q + Q)  (exp_swap_T3_e2e.ml)    *)
(* ------------------------------------------------------------------ *)

let t3_sum_ty = q ++ (q ++ q)

let t3_swap_12 =
  seq0 (assoc_plus_r q q q)
    (seq0 (omap0 (q ++ q) q (twist_plus q q) (id q)) (assoc_plus_l q q q))

let t3_swap_23 = omap0 q (q ++ q) (id q) (twist_plus q q)

let t3_e12_pi4 = exp_i (Float.pi /. 4.0) t3_swap_12
let t3_e23_pi4 = exp_i (Float.pi /. 4.0) t3_swap_23
let t3_e12_pi2 = exp_i (Float.pi /. 2.0) t3_swap_12
let t3_e23_pi2 = exp_i (Float.pi /. 2.0) t3_swap_23

(* plus-swap exponential (exp_twist_e2e.ml Part 5) *)
let exp_twist_plus_raw = exp_i (Float.pi /. 4.0) (twist_plus one one)

(* ------------------------------------------------------------------ *)
(* Per-label phased dispatch (phased_map_probe_e2e.ml ART-4)            *)
(* ------------------------------------------------------------------ *)

let plus_i = { Complex.re = 0.0; im = 1.0 }

let three_dt =
  datatype ~name:"threeO" ~arity:3 ~labels:["a"; "b"; "c"] ~ops:[]

let phased3_raw () =
  phased_control three_dt [| neg_one; plus_i; Complex.one |] q
    [| gate_x; gate_h; gate_z |]

let phased3_single_raw () =
  phased_control three_dt [| neg_one; Complex.one; Complex.one |] q
    [| id q; id q; id q |]

let three_q_id () = id (rep_ty three_dt ** q)

(* ------------------------------------------------------------------ *)
(* Short-circuit witness operations (short_circuit_e2e.ml)              *)
(* ------------------------------------------------------------------ *)

let w_ty = one ++ (one ++ one)

let toggle_w_raw = omap0 one (one ++ one) (id one) (twist_plus one one)

let ctrl_w_raw m0 m1 =
  let iw = one ** w_ty in
  seq0 (dist_l one one w_ty)
    (seq0 (omap0 iw iw (par0 (id one) m0) (par0 (id one) m1))
       (undist_l one one w_ty))

let and_sc_raw =
  let b = one ++ one in
  let w = w_ty in
  let route_in =
    seq0 (assoc_tensor_l b b w)
      (seq0 (par0 (id b) (twist_tensor b w)) (assoc_tensor_r b w b))
  in
  let apply_ctrl = par0 (ctrl_w_raw toggle_w_raw (id w)) (id b) in
  let route_out =
    seq0 (assoc_tensor_l b w b)
      (seq0 (par0 (id b) (twist_tensor w b)) (assoc_tensor_r b b w))
  in
  seq0 route_in (seq0 apply_ctrl route_out)

let w_id = id w_ty
let bw_id = id ((one ++ one) ** w_ty)
let bbw_id = id (((one ++ one) ** (one ++ one)) ** w_ty)

(* ------------------------------------------------------------------ *)
(* Z_n structural shifts / negations / additions (zn_group_ops_e2e.ml)  *)
(* ------------------------------------------------------------------ *)

let z3u_ty = one ++ (one ++ one)
let z4u_ty = one ++ (one ++ (one ++ one))
let z5u_ty = one ++ (one ++ (one ++ (one ++ one)))

let shift_z3_raw =
  seq0 (assoc_plus_r one one one) (twist_plus (one ++ one) one)

let neg_z3_raw = omap0 one (one ++ one) (id one) (twist_plus one one)

let add_z3_raw () =
  control z3_dt z3u_ty
    [| id z3u_ty; shift_z3_raw; seq0 shift_z3_raw shift_z3_raw |]

let shift_z4_raw =
  seq0 (assoc_plus_r one one (one ++ one))
    (seq0 (assoc_plus_r (one ++ one) one one)
       (seq0 (twist_plus ((one ++ one) ++ one) one)
          (omap0 one ((one ++ one) ++ one)
             (id one)
             (assoc_plus_l one one one))))

let swap_1_2_on_z3 =
  seq0 (assoc_plus_r one one one)
    (seq0 (omap0 (one ++ one) one (twist_plus one one) (id one))
       (assoc_plus_l one one one))

let swap_2_3_on_z3 = omap0 one (one ++ one) (id one) (twist_plus one one)

let neg_z3_inner = seq0 swap_1_2_on_z3 (seq0 swap_2_3_on_z3 swap_1_2_on_z3)

let neg_z4_raw = omap0 one (one ++ (one ++ one)) (id one) neg_z3_inner

let add_z4_raw () =
  let s1 = shift_z4_raw in
  let s2 = seq0 s1 s1 in
  let s3 = seq0 s2 s1 in
  control z4_dt z4u_ty [| id z4u_ty; s1; s2; s3 |]

let shift_z5_raw =
  seq0 (assoc_plus_r one one (one ++ (one ++ one)))
    (seq0 (assoc_plus_r (one ++ one) one (one ++ one))
       (seq0 (assoc_plus_r ((one ++ one) ++ one) one one)
          (seq0 (twist_plus (((one ++ one) ++ one) ++ one) one)
             (omap0 one (((one ++ one) ++ one) ++ one)
                (id one)
                (seq0 (assoc_plus_l (one ++ one) one one)
                   (assoc_plus_l one one (one ++ one)))))))

let swap_0_1_on_z4 =
  seq0 (assoc_plus_r one one (one ++ one))
    (seq0 (omap0 (one ++ one) (one ++ one) (twist_plus one one)
             (id (one ++ one)))
       (assoc_plus_l one one (one ++ one)))

let swap_2_3_on_z4 =
  omap0 one (one ++ (one ++ one))
    (id one)
    (omap0 one (one ++ one) (id one) (twist_plus one one))

let neg_z5_raw =
  let shift_z4_plus2 = seq0 shift_z4_raw shift_z4_raw in
  let inner = seq0 (seq0 shift_z4_plus2 swap_0_1_on_z4) swap_2_3_on_z4 in
  omap0 one z4u_ty (id one) inner

let z8u_ty =
  one ++ (one ++ (one ++ (one ++ (one ++ (one ++ (one ++ one))))))

let shift_z8_raw =
  let z2 = one ++ one in
  let z3 = one ++ z2 in
  let z4 = one ++ z3 in
  let z5 = one ++ z4 in
  let z6 = one ++ z5 in
  let lassoc_2 = one ++ one in
  let lassoc_3 = lassoc_2 ++ one in
  let lassoc_4 = lassoc_3 ++ one in
  let lassoc_5 = lassoc_4 ++ one in
  let lassoc_6 = lassoc_5 ++ one in
  let lassoc_7 = lassoc_6 ++ one in
  seq0 (assoc_plus_r one one z6)
    (seq0 (assoc_plus_r lassoc_2 one z5)
       (seq0 (assoc_plus_r lassoc_3 one z4)
          (seq0 (assoc_plus_r lassoc_4 one z3)
             (seq0 (assoc_plus_r lassoc_5 one z2)
                (seq0 (assoc_plus_r lassoc_6 one one)
                   (seq0 (twist_plus lassoc_7 one)
                      (omap0 one lassoc_7
                         (id one)
                         (seq0 (assoc_plus_l lassoc_5 one one)
                            (seq0 (assoc_plus_l lassoc_4 one z2)
                               (seq0 (assoc_plus_l lassoc_3 one z3)
                                  (seq0 (assoc_plus_l lassoc_2 one z4)
                                     (assoc_plus_l one one z5))))))))))))

let z11u_ty =
  let z2 = one ++ one in
  let z3 = one ++ z2 in
  let z4 = one ++ z3 in
  let z5 = one ++ z4 in
  let z6 = one ++ z5 in
  let z7 = one ++ z6 in
  let z8 = one ++ z7 in
  let z9 = one ++ z8 in
  let z10 = one ++ z9 in
  one ++ z10

let shift_z11_raw =
  let z2 = one ++ one in
  let z3 = one ++ z2 in
  let z4 = one ++ z3 in
  let z5 = one ++ z4 in
  let z6 = one ++ z5 in
  let z7 = one ++ z6 in
  let z8 = one ++ z7 in
  let z9 = one ++ z8 in
  let lassoc_2 = one ++ one in
  let lassoc_3 = lassoc_2 ++ one in
  let lassoc_4 = lassoc_3 ++ one in
  let lassoc_5 = lassoc_4 ++ one in
  let lassoc_6 = lassoc_5 ++ one in
  let lassoc_7 = lassoc_6 ++ one in
  let lassoc_8 = lassoc_7 ++ one in
  let lassoc_9 = lassoc_8 ++ one in
  let lassoc_10 = lassoc_9 ++ one in
  seq0 (assoc_plus_r one one z9)
    (seq0 (assoc_plus_r lassoc_2 one z8)
       (seq0 (assoc_plus_r lassoc_3 one z7)
          (seq0 (assoc_plus_r lassoc_4 one z6)
             (seq0 (assoc_plus_r lassoc_5 one z5)
                (seq0 (assoc_plus_r lassoc_6 one z4)
                   (seq0 (assoc_plus_r lassoc_7 one z3)
                      (seq0 (assoc_plus_r lassoc_8 one z2)
                         (seq0 (assoc_plus_r lassoc_9 one one)
                            (seq0 (twist_plus lassoc_10 one)
                               (omap0 one lassoc_10
                                  (id one)
                                  (seq0 (assoc_plus_l lassoc_8 one one)
                                     (seq0 (assoc_plus_l lassoc_7 one z2)
                                        (seq0 (assoc_plus_l lassoc_6 one z3)
                                           (seq0 (assoc_plus_l lassoc_5 one z4)
                                              (seq0 (assoc_plus_l lassoc_4 one z5)
                                                 (seq0 (assoc_plus_l lassoc_3 one z6)
                                                    (seq0 (assoc_plus_l lassoc_2 one z7)
                                                       (assoc_plus_l one one z8))))))))))))))))))

(* ------------------------------------------------------------------ *)
(* Certified sum associators relating the clean LEFT-associated Q_n     *)
(* to the legacy right-associated unit sums.  A right-associated        *)
(* oracle is never silently retyped: it is conjugated by these chains.  *)
(* ------------------------------------------------------------------ *)

let lassoc_u2 = one ++ one
let lassoc_u3 = (one ++ one) ++ one
let lassoc_u4 = ((one ++ one) ++ one) ++ one
let lassoc_u5 = (((one ++ one) ++ one) ++ one) ++ one
let lassoc_u6 = lassoc_u5 ++ one
let lassoc_u7 = lassoc_u6 ++ one
let lassoc_u8 = lassoc_u7 ++ one
let lassoc_u9 = lassoc_u8 ++ one
let lassoc_u10 = lassoc_u9 ++ one
let lassoc_u11 = lassoc_u10 ++ one

let rassoc_u2 = one ++ one
let rassoc_u3 = one ++ rassoc_u2
let rassoc_u4 = one ++ rassoc_u3
let rassoc_u5 = one ++ rassoc_u4
let rassoc_u6 = one ++ rassoc_u5
let rassoc_u7 = one ++ rassoc_u6
let rassoc_u8 = one ++ rassoc_u7
let rassoc_u9 = one ++ rassoc_u8
let rassoc_u10 = one ++ rassoc_u9

(* left → right *)
let l2r_u3 = assoc_plus_l one one one
let r2l_u3 = assoc_plus_r one one one

let l2r_u4 =
  seq0 (assoc_plus_l (one ++ one) one one)
    (assoc_plus_l one one (one ++ one))
let r2l_u4 =
  seq0 (assoc_plus_r one one (one ++ one))
    (assoc_plus_r (one ++ one) one one)

let l2r_u5 =
  seq0 (assoc_plus_l lassoc_u3 one one)
    (seq0 (assoc_plus_l (one ++ one) one rassoc_u2)
       (assoc_plus_l one one rassoc_u3))
let r2l_u5 =
  seq0 (assoc_plus_r one one rassoc_u3)
    (seq0 (assoc_plus_r (one ++ one) one rassoc_u2)
       (assoc_plus_r lassoc_u3 one one))

let l2r_u8 =
  seq0 (assoc_plus_l lassoc_u6 one one)
    (seq0 (assoc_plus_l lassoc_u5 one rassoc_u2)
       (seq0 (assoc_plus_l lassoc_u4 one rassoc_u3)
          (seq0 (assoc_plus_l lassoc_u3 one rassoc_u4)
             (seq0 (assoc_plus_l (one ++ one) one rassoc_u5)
                (assoc_plus_l one one rassoc_u6)))))
let r2l_u8 =
  seq0 (assoc_plus_r one one rassoc_u6)
    (seq0 (assoc_plus_r (one ++ one) one rassoc_u5)
       (seq0 (assoc_plus_r lassoc_u3 one rassoc_u4)
          (seq0 (assoc_plus_r lassoc_u4 one rassoc_u3)
             (seq0 (assoc_plus_r lassoc_u5 one rassoc_u2)
                (assoc_plus_r lassoc_u6 one one)))))

let l2r_u11 =
  seq0 (assoc_plus_l lassoc_u9 one one)
    (seq0 (assoc_plus_l lassoc_u8 one rassoc_u2)
       (seq0 (assoc_plus_l lassoc_u7 one rassoc_u3)
          (seq0 (assoc_plus_l lassoc_u6 one rassoc_u4)
             (seq0 (assoc_plus_l lassoc_u5 one rassoc_u5)
                (seq0 (assoc_plus_l lassoc_u4 one rassoc_u6)
                   (seq0 (assoc_plus_l lassoc_u3 one rassoc_u7)
                      (seq0 (assoc_plus_l (one ++ one) one rassoc_u8)
                         (assoc_plus_l one one rassoc_u9))))))))
let r2l_u11 =
  seq0 (assoc_plus_r one one rassoc_u9)
    (seq0 (assoc_plus_r (one ++ one) one rassoc_u8)
       (seq0 (assoc_plus_r lassoc_u3 one rassoc_u7)
          (seq0 (assoc_plus_r lassoc_u4 one rassoc_u6)
             (seq0 (assoc_plus_r lassoc_u5 one rassoc_u5)
                (seq0 (assoc_plus_r lassoc_u6 one rassoc_u4)
                   (seq0 (assoc_plus_r lassoc_u7 one rassoc_u3)
                      (seq0 (assoc_plus_r lassoc_u8 one rassoc_u2)
                         (assoc_plus_r lassoc_u9 one one))))))))

(* q-typed 3-summand associator (row 13's branch-swap sum) *)
let lassoc_q3 = (q ++ q) ++ q
let l2r_q3 = assoc_plus_l q q q
let r2l_q3 = assoc_plus_r q q q

(** Conjugate a right-associated endo onto the left-associated type. *)
let on_left l2r r2l m = seq0 l2r (seq0 m r2l)

(** Same, for a control-style endo on (sum ⊗ target). *)
let on_left_fst l2r r2l target m =
  seq0 (par0 l2r (id target)) (seq0 m (par0 r2l (id target)))

(** Same, for an endo whose SECOND factor is the sum (row 26's Bool ⊗ W). *)
let on_left_snd prefix l2r r2l m =
  seq0 (par0 (id prefix) l2r) (seq0 m (par0 (id prefix) r2l))

(** Conjugate an endo on (sum ⊗ sum) — both factors right-associated. *)
let on_left_both l2r r2l m =
  seq0 (par0 l2r l2r) (seq0 m (par0 r2l r2l))
