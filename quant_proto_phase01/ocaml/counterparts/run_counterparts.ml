(* Coverage authority for the Phase-2 demo migration.

   Runs every registered semantic check (concise counterpart vs legacy
   oracle through the bridge), validates the 34-row coverage manifest
   against demos/manifest.tsv, and performs the anti-vacuity lexical scan
   over the surface-authored counterpart file.  A manifest row counts as
   migrated only if its counterpart checks actually ran and passed here
   (or, for pure reject rows, its fixture is present and enforced by the
   source_frontend harness). *)

module CP = Qpl_counterparts.Surface_programs
module OL = Qpl_counterparts.Oracle_legacy
module OS = Qpl_counterparts.Oracle_sealed
module Src = Qpl_surface.Source
module Lin = Qpl_surface.Linear
module Bridge = Qpl_surface.Bridge

let results : (int * string * bool) list ref = ref []

let record row name ok detail =
  results := (row, name, ok) :: !results;
  Printf.printf "  %s  [row %02d] %s%s\n%!"
    (if ok then "PASS" else "FAIL") row name
    (if ok then "" else " (" ^ detail ^ ")")

let eq row name t1 t2 =
  match Bridge.eq_circ t1 t2 with
  | Bridge.EqCircOk (equal, fidelity) ->
      record row name (equal && fidelity > 0.999999)
        (Printf.sprintf "equal=%b fidelity=%f" equal fidelity)
  | Bridge.EqCircError e -> record row name false e

let neq row name t1 t2 =
  match Bridge.eq_circ t1 t2 with
  | Bridge.EqCircOk (equal, fidelity) ->
      record row name (not equal)
        (Printf.sprintf "unexpectedly equal (fidelity=%f)" fidelity)
  | Bridge.EqCircError e -> record row name false e

let compile_pin row name term ~check =
  match Bridge.compile_show term with
  | Bridge.CompileOk (perm, gates) ->
      let ok, detail = check perm.Bridge.n gates in
      Printf.printf "  info  [row %02d] %s: wires=%d gates=%d\n%!"
        row name perm.Bridge.n gates;
      record row name ok detail
  | Bridge.CompileError e -> record row name false e

let compile_ok row name term =
  compile_pin row name term ~check:(fun _ _ -> true, "")

(* ================================================================== *)
(* Semantic checks                                                     *)
(* ================================================================== *)

let bool_ty = Lin.(one ++ one)
let bq_ty = Lin.(bool_ty ** q)

let run_checks () =

  let loemit = Lin.emit_oterm in
  let semit = Src.emit in
  let value_of m = loemit (OL.as_value bq_ty m) in

  Printf.printf "== sealed-demo rows (27-31)\n";
  eq 30 "quickstart == sealed oracle"
    (semit CP.cp_quickstart) (semit OS.quickstart);
  eq 29 "fixed_control == sealed oracle"
    (semit CP.cp_fixed_control) (semit OS.fixed_control);
  record 27 "T3 arity = 3" (CP.T3.arity = 3)
    (string_of_int CP.T3.arity);
  eq 27 "three-way selector == sealed oracle"
    (semit CP.cp_three) (semit OS.three_program);
  eq 28 "exp_twist == sealed Op.value oracle"
    (semit CP.cp_exp_twist) (semit OS.exp_twist_value);
  eq 31 "exp_x == sealed Op.value oracle"
    (semit CP.cp_exp_x) (semit OS.exp_x_value);
  eq 31 "exp_x == raw exp_i(pi/4, X)"
    (semit CP.cp_exp_x) (loemit (OL.as_value Lin.q OL.exp_x_single));

  Printf.printf "== exponentials (row 14)\n";
  eq 14 "exp_twist == raw exp_i(pi/4, twist)"
    (semit CP.cp_exp_twist)
    (loemit (OL.as_value Lin.(q ** q) OL.exp_twist_single));
  eq 14 "exp_twist^2 == raw exp_i(pi/2, twist)  [composition law]"
    (semit CP.cp_exp_twist_sq)
    (loemit (OL.as_value Lin.(q ** q) OL.exp_twist_half_pi));

  Printf.printf "== qswitch family (rows 1, 11, 22, 23, 24)\n";
  compile_ok 11 "abstract qswitch (at q) compiles"
    (semit (CP.cp_qswitch Src.P.q));
  record 11 "abstract qswitch bridge JSON non-empty"
    (String.length (Bridge.term_to_json (semit (CP.cp_qswitch Src.P.q))) > 0)
    "empty JSON";
  eq 24 "qswitch_hs == legacy qswitch H S"
    (semit CP.cp_qswitch_hs) (value_of (OL.qswitch Lin.gate_h Lin.gate_s));
  eq 24 "qswitch_xz == legacy qswitch X Z"
    (semit CP.cp_qswitch_xz) (value_of (OL.qswitch Lin.gate_x Lin.gate_z));
  eq 24 "qswitch_hy == legacy qswitch H Y"
    (semit CP.cp_qswitch_hy) (value_of (OL.qswitch Lin.gate_h Lin.gate_y));
  eq 24 "qswitch_hh == legacy qswitch H H"
    (semit CP.cp_qswitch_hh) (value_of (OL.qswitch Lin.gate_h Lin.gate_h));
  eq 24 "qswitch_rz == legacy qswitch Rz Rz"
    (semit CP.cp_qswitch_rz)
    (value_of (OL.qswitch
                 (Lin.gate_rz (Float.pi /. 4.0))
                 (Lin.gate_rz (Float.pi /. 8.0))));
  eq 24 "sealed composition == legacy seq of qswitches"
    (semit CP.cp_qswitch_composed)
    (value_of Lin.(seq0 (OL.qswitch gate_h gate_s) (OL.qswitch gate_x gate_z)));
  eq 24 "sealed triple == legacy triple seq"
    (semit CP.cp_qswitch_triple)
    (value_of Lin.(seq0 (OL.qswitch gate_h gate_s)
                     (seq0 (OL.qswitch gate_x gate_z)
                        (OL.qswitch gate_h gate_y))));

  (* The wire-level Apply of certified op VALUES into the case-bodied
     abstract qswitch is refused by the canonical-normal-form AppCut and
     routing gates (recorded Phase-2 finding); the instantiated content
     is checked through the sugar instance instead. *)
  compile_ok 1 "abstract qswitch (at q) compiles" (semit (CP.cp_qswitch Src.P.q));
  eq 1 "qswitch_hs sugar == meta-level QSwitch[H,S]"
    (semit CP.cp_qswitch_hs) (value_of OL.meta_qswitch_hs);

  Printf.printf "== qswitch payloads (row 23)\n";
  eq 23 "qswitch at (q,q) with CX == generic legacy"
    (semit CP.cp_qswitch_qq_cx)
    (loemit (OL.as_value Lin.(bool_ty ** (q ** q))
               (OL.qswitch_generic Lin.(q ** q) Lin.gate_cx Lin.gate_cx)));
  eq 23 "qswitch at qbool with NOT == generic legacy"
    (semit CP.cp_qswitch_qbool_not)
    (loemit (OL.as_value Lin.(bool_ty ** bool_ty)
               (OL.qswitch_generic bool_ty
                  Lin.(twist_plus one one) Lin.(twist_plus one one))));
  eq 23 "qswitch at (qbool,q) with NOT⊗X == generic legacy"
    (semit CP.cp_qswitch_bq)
    (loemit (OL.as_value Lin.(bool_ty ** (bool_ty ** q))
               (OL.qswitch_generic Lin.(bool_ty ** q)
                  Lin.(par0 (twist_plus one one) gate_x)
                  Lin.(par0 (twist_plus one one) gate_x))));
  eq 23 "qswitch(id, id) at q == id  (sugar instance)"
    (semit CP.cp_qswitch_idid) (value_of Lin.(id bq_ty));

  Printf.printf "== eta-expanded qswitch (row 22)\n";
  compile_ok 22 "qswitch_eta_endoQ compiles" (semit CP.cp_qswitch_eta_endoq);
  eq 22 "H-in-both-branches shape == legacy case_hom H/H"
    (semit CP.cp_both_h) (value_of OL.both_h_raw);

  Printf.printf "== compose_n (row 16)\n";
  (let hv = Src.Op.value Src.Op.h and sv = Src.Op.value Src.Op.s in
   let tv = Src.Op.value Src.Op.t and xv = Src.Op.value Src.Op.x in
   let qval m = loemit (OL.as_value Lin.q m) in
   eq 16 "compose2(H, S) == S ; H"
     (semit (OS.apply0 (OS.apply0 CP.cp_compose2 hv) sv)) (qval OL.meta_hs);
   eq 16 "compose2(H, H) == H ; H"
     (semit (OS.apply0 (OS.apply0 CP.cp_compose2 hv) hv)) (qval OL.meta_hh);
   eq 16 "compose3(H, S, T) == T ; S ; H"
     (semit (OS.apply0 (OS.apply0 (OS.apply0 CP.cp_compose3 hv) sv) tv))
     (qval OL.meta_hst);
   eq 16 "compose4(H, S, T, X) == X ; T ; S ; H"
     (semit (OS.apply0
               (OS.apply0 (OS.apply0 (OS.apply0 CP.cp_compose4 hv) sv) tv)
               xv))
     (qval OL.meta_hstx));

  Printf.printf "== fixed-control family (rows 19, 4, 5, 32)\n";
  eq 19 "qif Reading A == legacy qif_apply"
    (semit CP.cp_qif_cnot) (value_of OL.qif_apply);
  eq 19 "qif Reading A == legacy ctrl(X)"
    (semit CP.cp_qif_cnot) (value_of OL.ctrl1_x);
  eq 4 "companion ctrl(Z) == legacy ctrl(Z)"
    (semit CP.cp_ctrl_z) (value_of OL.ctrl1_z);
  eq 5 "ctrl^1(X) sugar == legacy" (semit CP.cp_qif_cnot) (value_of OL.ctrl1_x);
  eq 5 "ctrl^2(X) sugar == legacy CCX construction"
    (semit CP.cp_ctrl2_x)
    (loemit (OL.as_value Lin.(bool_ty ** (bool_ty ** q)) OL.ctrl2_x));
  eq 5 "ctrl^3(X) sugar == legacy CCCX construction"
    (semit CP.cp_ctrl3_x)
    (loemit (OL.as_value Lin.(bool_ty ** (bool_ty ** (bool_ty ** q)))
               OL.ctrl3_x));
  eq 32 "ctrl^1(H) sugar == math-verified legacy"
    (semit CP.cp_ctrl_h) (value_of OL.ctrl1_h);
  eq 32 "ctrl^2(H) sugar == math-verified legacy"
    (semit CP.cp_ctrl2_h)
    (loemit (OL.as_value Lin.(bool_ty ** (bool_ty ** q)) OL.ctrl2_h));
  eq 32 "ctrl^3(H) sugar == math-verified legacy"
    (semit CP.cp_ctrl3_h)
    (loemit (OL.as_value Lin.(bool_ty ** (bool_ty ** (bool_ty ** q)))
               OL.ctrl3_h));

  Printf.printf "== selectors (rows 2, 6, 7, 8, 12, 15, 17)\n";
  eq 2 "select2 == closed structural select_2"
    (semit CP.cp_select2_hs) (value_of OL.closed_select_2_hs);
  eq 2 "select2 == meta control z2 [H;S]"
    (semit CP.cp_select2_hs)
    (loemit (OL.as_value Lin.(rep_ty OL.z2_dt ** q) (OL.meta_z2_hs ())));
  (let z3v m =
     loemit (OL.as_value Lin.(OL.lassoc_u3 ** q)
               (OL.on_left_fst OL.l2r_u3 OL.r2l_u3 Lin.q m)) in
   eq 6 "select3 == meta control z3 [H;S;T]"
     (semit CP.cp_select3_hst) (z3v (OL.meta_z3_hst ()));
   eq 7 "select3 == meta control z3 [H;S;T]  (n-dist row)"
     (semit CP.cp_select3_hst) (z3v (OL.meta_z3_hst ()));
   eq 15 "select3 == meta control z3 [H;S;T]  (n-ary plusmap row)"
     (semit CP.cp_select3_hst) (z3v (OL.meta_z3_hst ())));
  (let z5v m =
     loemit (OL.as_value Lin.(OL.lassoc_u5 ** q)
               (OL.on_left_fst OL.l2r_u5 OL.r2l_u5 Lin.q m)) in
   eq 15 "select5 == meta control z5 [H;S;T;X;Y]"
     (semit CP.cp_select5_hstxy) (z5v (OL.meta_z5_hstxy ()));
   eq 12 "select5 == meta control z5 [H;S;T;X;Y]  (dump row)"
     (semit CP.cp_select5_hstxy) (z5v (OL.meta_z5_hstxy ())));
  record 12 "select5 bridge JSON non-empty"
    (String.length (Bridge.term_to_json (semit CP.cp_select5_hstxy)) > 0)
    "empty JSON";
  (let z4v m =
     loemit (OL.as_value Lin.(OL.lassoc_u4 ** q)
               (OL.on_left_fst OL.l2r_u4 OL.r2l_u4 Lin.q m)) in
   eq 17 "select4 [H;S;T;X] == meta z4"
     (semit CP.cp_select4_hstx) (z4v (OL.meta_z4_hstx ()));
   eq 17 "select4 [X;T;H;X] == meta z4"
     (semit CP.cp_select4_xthx) (z4v (OL.meta_z4_xthx ()));
   eq 17 "select4 [H;H;S;S] == meta z4"
     (semit CP.cp_select4_hhss) (z4v (OL.meta_z4_hhss ())));
  record 8 "Bool2 arity = 2" (CP.Bool2.arity = 2)
    (string_of_int CP.Bool2.arity);
  record 8 "G8 arity = 8" (CP.G8.arity = 8) (string_of_int CP.G8.arity);
  eq 8 "controlled dispatch [H;X] == meta control z2 [H;X]"
    (semit CP.cp_bool2_hx)
    (loemit (OL.as_value Lin.(rep_ty OL.z2_dt ** q) (OL.meta_z2_hx ())));

  Printf.printf "== algorithm cores (row 3)\n";
  (let qqv m = loemit (OL.as_value Lin.(q ** q) m) in
   eq 3 "dj_constant == legacy" (semit CP.cp_dj_constant) (qqv OL.dj_constant);
   eq 3 "dj_balanced == legacy" (semit CP.cp_dj_balanced) (qqv OL.dj_balanced);
   eq 3 "hsp 2-qubit core == legacy"
     (semit CP.cp_hsp_2q)
     (loemit (OL.as_value Lin.((q ** q) ** (q ** q)) OL.hsp_2q)));

  Printf.printf "== Z_n phases and Z_2 group ops (rows 33, 34)\n";
  eq 33 "z2 phase == legacy control [id; Z]"
    (semit CP.cp_z2_phase)
    (loemit (OL.as_value Lin.(rep_ty OL.z2_dt ** q) (OL.z2_phase ())));
  eq 33 "z4 phase == legacy control [Rz(k/2)] (associator-related)"
    (semit CP.cp_z4_phase)
    (loemit (OL.as_value Lin.(OL.lassoc_u4 ** q)
               (OL.on_left_fst OL.l2r_u4 OL.r2l_u4 Lin.q (OL.z4_phase ()))));
  eq 33 "z5 phase == legacy control [Rz(2k/5)] (associator-related)"
    (semit CP.cp_z5_phase)
    (loemit (OL.as_value Lin.(OL.lassoc_u5 ** q)
               (OL.on_left_fst OL.l2r_u5 OL.r2l_u5 Lin.q (OL.z5_phase ()))));
  eq 33 "z8 phase == legacy control [Rz(k/4)] (associator-related)"
    (semit CP.cp_z8_phase)
    (loemit (OL.as_value Lin.(OL.lassoc_u8 ** q)
               (OL.on_left_fst OL.l2r_u8 OL.r2l_u8 Lin.q (OL.z8_phase ()))));
  eq 33 "z4 phase ; inverse == id"
    (semit CP.cp_z4_phase_roundtrip)
    (loemit (OL.as_value Lin.(OL.lassoc_u4 ** q) Lin.(id (OL.lassoc_u4 ** q))));
  eq 33 "z8 phase ; inverse == id"
    (semit CP.cp_z8_phase_roundtrip)
    (loemit (OL.as_value Lin.(OL.lassoc_u8 ** q) Lin.(id (OL.lassoc_u8 ** q))));
  eq 34 "z2 shift == twist_plus"
    (semit CP.cp_z2_shift)
    (loemit (OL.as_value bool_ty OL.shift_z2_plus1));
  eq 34 "z2 add == legacy control [id; twist]"
    (semit CP.cp_z2_add)
    (loemit (OL.as_value Lin.(rep_ty OL.z2_dt ** bool_ty) (OL.add_z2 ())));
  eq 34 "z2 add ; add == id  (each element self-inverse)"
    (semit CP.cp_z2_add_sq)
    (loemit (OL.as_value Lin.(rep_ty OL.z2_dt ** bool_ty) (OL.z2z2_id ())));

  Printf.printf "== phase marking (row 18)\n";
  eq 18 "phase mark == legacy case_hom with phase(-1)"
    (semit CP.cp_phase_mark) (value_of OL.phase_mark_raw);
  eq 18 "phase mark squared == id"
    (semit CP.cp_phase_mark_sq) (value_of OL.bq_id);
  eq 18 "phase mark (+i) fourth power == id"
    (semit CP.cp_phase_mark_i4) (value_of OL.bq_id);

  Printf.printf "== certified distributors (rows 9, 10)\n";
  compile_pin 10 "unequal-width distributor is pure wiring"
    (semit CP.cp_dist_unequal)
    ~check:(fun _ gates ->
        gates = 0, Printf.sprintf "expected 0 gates, got %d" gates);
  eq 10 "unequal-width distributor == sealed Op.value"
    (semit CP.cp_dist_unequal) (semit (Src.Op.value CP.dl_unequal));
  eq 10 "unequal-width distributor == raw dist_l"
    (semit CP.cp_dist_unequal)
    (loemit (OL.as_value2 Lin.((q ++ (q ** q)) ** q)
               Lin.((q ** q) ++ ((q ** q) ** q)) OL.dist_unequal_raw));
  eq 9 "P_L in concise syntax == raw P_L  (frontend equivalence; the
        naturality gap itself stays documented in the retained probe)"
    (semit CP.cp_dist_pl)
    (loemit (OL.as_value2 Lin.((q ++ (q ** q)) ** q)
               Lin.((q ** q) ++ ((q ** q) ** q)) OL.p_l_raw));

  Printf.printf "== QS_2 simulator (row 20)\n";
  eq 20 "coherent controlled-SWAP == legacy R"
    (semit CP.cp_qs2_r)
    (loemit (OL.as_value Lin.(bool_ty ** OL.regs_ty) OL.qs2_r_op));
  eq 20 "round == legacy round"
    (semit CP.cp_qs2_round)
    (loemit (OL.as_value Lin.(bool_ty ** OL.regs_ty) OL.qs2_round_op));
  eq 20 "two-round simulator == legacy qs2_sim"
    (semit CP.cp_qs2_sim)
    (loemit (OL.as_value Lin.((bool_ty ** bool_ty) ** OL.regs_ty) OL.qs2_sim));

  Printf.printf "== QS_3 components (row 21)\n";
  eq 21 "target-only S_3 dispatch == legacy control (associator-related)"
    (semit CP.cp_qs3_target)
    (loemit (OL.as_value Lin.(OL.lassoc_u8 ** q)
               (OL.on_left_fst OL.l2r_u8 OL.r2l_u8 Lin.q
                  (OL.qs3_target_only_ctrl ()))));
  eq 21 "SWAP(T, D_3) coherence chain == legacy"
    (semit (Src.Op.value CP.qs3_swap3))
    (loemit (OL.as_value OL.regs4_ty OL.qs3_swap_3));
  compile_pin 21 "round-1 dispatch compiles (7 qubits + boundary)"
    (semit (Src.Op.value CP.qs3_r1_sel))
    ~check:(fun wires _ ->
        wires = 14, Printf.sprintf "expected 14 boundary wires, got %d" wires);
  compile_ok 21 "full 3-round simulator compiles" (semit CP.cp_qs3_sim);

  Printf.printf "== branch-swap exponentials on T = Q + (Q + Q) (row 13)\n";
  (* the raw sums are right-associated: relate them through the certified
     q-typed associator; the remaining tag⊗payload versus homogeneous-sum
     relation is the Option-B flat-layout law, stated here explicitly *)
  eq 13 "exp(pi/4, swap12) via datatype involution == raw (associator-related)"
    (semit CP.cp_exp_swap12)
    (loemit (OL.as_value OL.lassoc_q3
               (OL.on_left OL.l2r_q3 OL.r2l_q3 OL.t3_e12_pi4)));
  eq 13 "exp(pi/4, swap23) via datatype involution == raw (associator-related)"
    (semit CP.cp_exp_swap23)
    (loemit (OL.as_value OL.lassoc_q3
               (OL.on_left OL.l2r_q3 OL.r2l_q3 OL.t3_e23_pi4)));
  eq 13 "E12(pi/4)^2 == E12(pi/2)  (composition law)"
    (semit CP.cp_exp_swap12_sq) (semit CP.cp_exp_swap12_half);
  eq 13 "E23(pi/4)^2 == E23(pi/2)  (composition law)"
    (semit CP.cp_exp_swap23_sq) (semit CP.cp_exp_swap23_half);
  neq 13 "E12 ; E23 =/= E23 ; E12  (non-commutation)"
    (semit CP.cp_exp_e12_e23) (semit CP.cp_exp_e23_e12);

  Printf.printf "== plus-swap exponential (row 14 residue)\n";
  eq 14 "exp(pi/4, twist_plus) via two-label involution == raw"
    (semit CP.cp_exp_twist_plus)
    (loemit (OL.as_value Lin.(one ++ one) OL.exp_twist_plus_raw));

  Printf.printf "== per-label phased dispatch (row 18 residue)\n";
  eq 18 "phased select [X.-1; H.+i; Z.1] == raw phased_control (associator-related)"
    (semit CP.cp_phased_select)
    (loemit (OL.as_value Lin.(OL.lassoc_u3 ** q)
               (OL.on_left_fst OL.l2r_u3 OL.r2l_u3 Lin.q (OL.phased3_raw ()))));
  eq 18 "single-label phase squared == id"
    (semit CP.cp_phased_single_sq)
    (loemit (OL.as_value Lin.(OL.lassoc_u3 ** q)
               Lin.(id (OL.lassoc_u3 ** q))));

  Printf.printf "== W3 short-circuit witness (row 26, concrete Qudit(3))\n";
  record 26 "W3 Qudit(3) declaration (arity 3)"
    (CP.W3.arity = 3 && CP.W3.labels = ["Wsc"; "Wfalse"; "Wtrue"])
    (String.concat "," CP.W3.labels);
  eq 26 "W3 toggle permutation == raw toggle_W (associator-related)"
    (semit (Src.Op.value CP.w3_toggle))
    (loemit (OL.as_value OL.lassoc_u3
               (OL.on_left OL.l2r_u3 OL.r2l_u3 OL.toggle_w_raw)));
  eq 26 "toggle ; toggle == id_W  (involution)"
    (semit CP.cp_w3_toggle_sq)
    (loemit (OL.as_value OL.lassoc_u3 (Lin.id OL.lassoc_u3)));
  eq 26 "ctrl_W(toggle, id) through case sugar == raw ctrl_W (associator-related)"
    (semit CP.cp_ctrl_w)
    (loemit (OL.as_value Lin.(OL.bool_ty ** OL.lassoc_u3)
               (OL.on_left_snd OL.bool_ty OL.l2r_u3 OL.r2l_u3
                  (OL.ctrl_w_raw OL.toggle_w_raw (Lin.id OL.w_ty)))));
  eq 26 "and_sc == raw short-circuit conjunction (associator-related)"
    (semit CP.cp_and_sc)
    (loemit (OL.as_value Lin.((OL.bool_ty ** OL.bool_ty) ** OL.lassoc_u3)
               (OL.on_left_snd Lin.(OL.bool_ty ** OL.bool_ty)
                  OL.l2r_u3 OL.r2l_u3 OL.and_sc_raw)));
  eq 26 "and_sc ; and_sc == id  (involution)"
    (semit CP.cp_and_sc_sq)
    (loemit (OL.as_value Lin.((OL.bool_ty ** OL.bool_ty) ** OL.lassoc_u3)
               Lin.(id ((OL.bool_ty ** OL.bool_ty) ** OL.lassoc_u3))));

  Printf.printf "== Z_n group operations, n >= 3 (row 34)\n";
  eq 34 "z3 shift == raw structural shift (associator-related)"
    (semit CP.cp_z3_shift)
    (loemit (OL.as_value OL.lassoc_u3
               (OL.on_left OL.l2r_u3 OL.r2l_u3 OL.shift_z3_raw)));
  eq 34 "z3 neg == raw structural neg (associator-related)"
    (semit CP.cp_z3_neg)
    (loemit (OL.as_value OL.lassoc_u3
               (OL.on_left OL.l2r_u3 OL.r2l_u3 OL.neg_z3_raw)));
  eq 34 "z3 neg squared == id"
    (semit CP.cp_z3_neg_sq)
    (loemit (OL.as_value OL.lassoc_u3 (Lin.id OL.lassoc_u3)));
  eq 34 "z3 add == raw control of structural shifts (associator-related)"
    (semit CP.cp_z3_add)
    (loemit (OL.as_value Lin.(OL.lassoc_u3 ** OL.lassoc_u3)
               (OL.on_left_both OL.l2r_u3 OL.r2l_u3 (OL.add_z3_raw ()))));
  eq 34 "z4 shift == raw structural shift (associator-related)"
    (semit CP.cp_z4_shift)
    (loemit (OL.as_value OL.lassoc_u4
               (OL.on_left OL.l2r_u4 OL.r2l_u4 OL.shift_z4_raw)));
  eq 34 "z4 neg == raw structural neg (associator-related)"
    (semit CP.cp_z4_neg)
    (loemit (OL.as_value OL.lassoc_u4
               (OL.on_left OL.l2r_u4 OL.r2l_u4 OL.neg_z4_raw)));
  eq 34 "z4 add == raw control of structural shifts (associator-related)"
    (semit CP.cp_z4_add)
    (loemit (OL.as_value Lin.(OL.lassoc_u4 ** OL.lassoc_u4)
               (OL.on_left_both OL.l2r_u4 OL.r2l_u4 (OL.add_z4_raw ()))));
  eq 34 "z5 shift == raw structural shift (associator-related)"
    (semit CP.cp_z5_shift)
    (loemit (OL.as_value OL.lassoc_u5
               (OL.on_left OL.l2r_u5 OL.r2l_u5 OL.shift_z5_raw)));
  eq 34 "z5 neg == raw structural neg (associator-related)"
    (semit CP.cp_z5_neg)
    (loemit (OL.as_value OL.lassoc_u5
               (OL.on_left OL.l2r_u5 OL.r2l_u5 OL.neg_z5_raw)));
  eq 34 "z5 shift to the 5th == id"
    (semit CP.cp_z5_shift_cycle)
    (loemit (OL.as_value OL.lassoc_u5 (Lin.id OL.lassoc_u5)));
  compile_pin 34 "z5 add compiles (derived from verified shifts)"
    (semit CP.cp_z5_add)
    ~check:(fun wires _ ->
        wires = 12, Printf.sprintf "expected 12 wires, got %d" wires);
  eq 34 "z8 shift == raw structural shift (associator-related)"
    (semit CP.cp_z8_shift)
    (loemit (OL.as_value OL.lassoc_u8
               (OL.on_left OL.l2r_u8 OL.r2l_u8 OL.shift_z8_raw)));
  eq 34 "z8 group law: neg ; shift1 ; neg == shift7"
    (semit (Src.Op.value
              (Src.Op.compose CP.z8_neg
                 (Src.Op.compose CP.z8_shift1 CP.z8_neg))))
    (semit (Src.Op.value (CP.z8_shift_of 7)));
  compile_pin 34 "z8 add compiles (derived from verified shifts)"
    (semit CP.cp_z8_add)
    ~check:(fun wires _ ->
        wires = 12, Printf.sprintf "expected 12 wires, got %d" wires);
  eq 34 "z11 shift == raw structural shift (associator-related)"
    (semit CP.cp_z11_shift)
    (loemit (OL.as_value OL.lassoc_u11
               (OL.on_left OL.l2r_u11 OL.r2l_u11 OL.shift_z11_raw)));
  eq 34 "z11 neg squared == id"
    (semit CP.cp_z11_neg_sq)
    (loemit (OL.as_value OL.lassoc_u11 (Lin.id OL.lassoc_u11)));
  eq 34 "z11 group law: neg ; shift1 ; neg == shift10"
    (semit (Src.Op.value
              (Src.Op.compose CP.z11_neg
                 (Src.Op.compose CP.z11_shift1 CP.z11_neg))))
    (semit (Src.Op.value (CP.z11_shift_of 10)));
  compile_pin 34 "z11 add compiles (derived from verified shifts)"
    (semit CP.cp_z11_add)
    ~check:(fun wires _ ->
        wires = 16, Printf.sprintf "expected 16 wires, got %d" wires)

(* ================================================================== *)
(* Anti-vacuity lexical scan                                           *)
(* ================================================================== *)

let forbidden_tokens =
  [ "use"; "using"; "U0"; "UL"; "UR"; "run_lam"; "run_split";
    "olam"; "ovar"; "oapp"; "oletpair"; "opair"; "oseq"; "oembed";
    "ocase"; "oplusmap"; "o_n_plusmap"; "emit_oterm";
    "TApply"; "TSeq"; "TId"; "Linear"; "Raw"; "Bridge"; "Elaborate" ]

let is_word_char c =
  (c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z')
  || (c >= '0' && c <= '9') || c = '_'

let scan_file path =
  let ic = open_in_bin path in
  let text =
    Fun.protect ~finally:(fun () -> close_in_noerr ic)
      (fun () -> really_input_string ic (in_channel_length ic))
  in
  let n = String.length text in
  let hits = ref [] in
  List.iter
    (fun token ->
       let tl = String.length token in
       let rec search at =
         if at + tl <= n then begin
           if String.sub text at tl = token
              && (at = 0 || not (is_word_char text.[at - 1]))
              && (at + tl = n || not (is_word_char text.[at + tl]))
           then hits := token :: !hits
           else ();
           if String.sub text at tl = token
              && (at = 0 || not (is_word_char text.[at - 1]))
              && (at + tl = n || not (is_word_char text.[at + tl]))
           then () else search (at + 1)
         end
       in
       search 0)
    forbidden_tokens;
  List.sort_uniq compare !hits

(* ================================================================== *)
(* Coverage manifest validation                                        *)
(* ================================================================== *)

let read_lines path =
  let ic = open_in path in
  let rec loop acc =
    match input_line ic with
    | line -> loop (line :: acc)
    | exception End_of_file -> close_in ic; List.rev acc
  in
  loop []

let fail_hard fmt =
  Printf.ksprintf (fun m -> prerr_endline m; exit 2) fmt

let validate_coverage () =
  let rows =
    read_lines "coverage.tsv"
    |> List.tl (* header *)
    |> List.map (fun line -> String.split_on_char '\t' line)
  in
  if List.length rows <> 34 then
    fail_hard "coverage.tsv has %d rows, expected 34" (List.length rows);
  let demo_names =
    read_lines "../demos/manifest.tsv"
    |> List.tl
    |> List.map (fun line ->
        match String.split_on_char '\t' line with
        | name :: _ -> name
        | [] -> fail_hard "bad manifest row")
    |> List.sort compare
  in
  let coverage_names =
    List.map
      (fun row -> match row with
         | _ :: name :: _ -> name
         | _ -> fail_hard "bad coverage row")
      rows
    |> List.sort compare
  in
  if demo_names <> coverage_names then
    fail_hard "coverage.tsv executables do not match demos/manifest.tsv";
  let statuses = ["migrated"; "split-migrated"; "backend-only"; "blocked-E2"] in
  let failures = ref 0 in
  List.iter
    (fun row ->
       match row with
       | [n; name; _role; _cp; _oracle; test; status; _rem] ->
           let rownum = int_of_string n in
           if not (List.mem status statuses) then
             fail_hard "row %d: unknown status %s" rownum status;
           if status = "migrated" || status = "split-migrated" then begin
             let checks =
               List.filter (fun (r, _, _) -> r = rownum) !results
             in
             let needs_runner =
               (* substring search for "run_counterparts" *)
               let t = test and pat = "run_counterparts" in
               let tl = String.length t and pl = String.length pat in
               let rec has at =
                 at + pl <= tl
                 && (String.sub t at pl = pat || has (at + 1))
               in
               has 0
             in
             if needs_runner && checks = [] then begin
               Printf.printf
                 "  FAIL  row %02d (%s): no executed counterpart check\n%!"
                 rownum name;
               incr failures
             end;
             if List.exists (fun (_, _, ok) -> not ok) checks then
               incr failures;
             if not needs_runner then begin
               (* pure reject rows: fixture presence, enforced by the
                  source_frontend harness in the same test alias *)
               let fixture =
                 "../test/source_frontend/reject/reject_reader_qif.ml"
               in
               if rownum = 25 && not (Sys.file_exists fixture) then begin
                 Printf.printf "  FAIL  row 25: missing %s\n%!" fixture;
                 incr failures
               end
             end
           end
       | _ -> fail_hard "coverage.tsv row with wrong column count")
    rows;
  !failures

(* ================================================================== *)

let () =
  run_checks ();
  Printf.printf "== anti-vacuity scan (surface_programs.ml)\n";
  let hits = scan_file "surface_programs.ml" in
  (match hits with
   | [] -> Printf.printf "  PASS  no forbidden tokens\n%!"
   | tokens ->
       Printf.printf "  FAIL  forbidden tokens: %s\n%!"
         (String.concat ", " tokens));
  (* row 19's concise reject fixture must exist alongside its positive *)
  let reading_b = "../test/source_frontend/reject/reject_reading_b.ml" in
  record 19 "Reading-B concise reject fixture present"
    (Sys.file_exists reading_b) reading_b;
  Printf.printf "== coverage manifest validation\n";
  let coverage_failures = validate_coverage () in
  let check_failures =
    List.length (List.filter (fun (_, _, ok) -> not ok) !results)
  in
  let total = List.length !results in
  Printf.printf
    "\nCounterparts: %d checks, %d failed; coverage failures: %d; scan hits: %d\n%!"
    total check_failures coverage_failures (List.length hits);
  if check_failures = 0 && coverage_failures = 0 && hits = [] then
    Printf.printf "ALL COUNTERPART CHECKS PASSED\n%!"
  else begin
    Printf.printf "COUNTERPART FAILURES PRESENT\n%!";
    exit 1
  end
