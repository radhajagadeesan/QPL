(** Verify nested controls produce correct unitaries.

    For each gate G in {H, S, Z, T} and k = 1..4 controls, compile
    ctrl^k(G) via the standard pipeline and compare against a
    mathematically constructed reference unitary:

      ref = I_{2^(k+1)}
      ref[-2:, -2:] = G    (apply G only when all controls = |1>)

    This is independent of the compiler -- pure linear algebra.

    Full pipeline: OCaml Linear DSL -> Bridge -> Python compile -> pytket
*)

open Qpl_surface
open Linear

let banner title =
  print_endline "";
  print_endline (String.make 74 '=');
  Printf.printf "  %s\n" title;
  print_endline (String.make 74 '=')

(** Bool = I + I *)
let bool_ty = one ++ one

(** Type aliases for iterated Bool * ... * Q *)
let bq   = bool_ty ** q
let bbq  = bool_ty ** bq
let bbbq = bool_ty ** bbq

(** 1/sqrt(2) *)
let s2 = 1.0 /. sqrt 2.0

(** Gate matrices: 2x2 real and imaginary parts *)

(* H = (1/sqrt2) [[1, 1], [1, -1]] *)
let h_re = [[s2; s2]; [s2; -.s2]]
let h_im = [[0.0; 0.0]; [0.0; 0.0]]

(* S = [[1, 0], [0, i]] *)
let s_re = [[1.0; 0.0]; [0.0; 0.0]]
let s_im = [[0.0; 0.0]; [0.0; 1.0]]

(* Z = [[1, 0], [0, -1]] *)
let z_re = [[1.0; 0.0]; [0.0; -.1.0]]
let z_im = [[0.0; 0.0]; [0.0; 0.0]]

(* T = [[1, 0], [0, e^{i pi/4}]] = [[1, 0], [0, 1/sqrt2 + i/sqrt2]] *)
let t_re = [[1.0; 0.0]; [0.0; s2]]
let t_im = [[0.0; 0.0]; [0.0; s2]]

(** Counters *)
let n_pass = ref 0
let n_fail = ref 0

(** Verify a single ctrl^k(G) against mathematical reference. *)
let verify name gate_re gate_im bridge_term k =
  match Bridge.verify_ctrl_unitary bridge_term gate_re gate_im k with
  | Bridge.EqCircOk (equal, fidelity) ->
    if equal then begin
      Printf.printf "  PASS  ctrl^%d(%s)  fidelity=%.10f\n" k name fidelity;
      incr n_pass
    end else begin
      Printf.printf "  FAIL  ctrl^%d(%s)  fidelity=%.10f\n" k name fidelity;
      incr n_fail
    end
  | Bridge.EqCircError err ->
    Printf.printf "  ERROR ctrl^%d(%s): %s\n" k name err;
    incr n_fail


(* ========================================================================= *)
(* Build ctrl^k(G) for each gate and each k = 1..4                          *)
(* ========================================================================= *)

(** ctrl combinator (same as ctrl_lambda_e2e.ml) *)
let ctrl (a_ty : 'a ty) (f : (unit, [`Lolli of 'a * 'a]) prog)
    : (unit, [`Lolli of [`Tensor of [`Plus of [`One] * [`One]] * 'a]
                       * [`Tensor of [`Plus of [`One] * [`One]] * 'a]]) prog =
  let ia_ty = one ** a_ty in
  let distribute = dist_l one one a_ty in
  let left_branch  = id ia_ty in
  let right_branch = par0 (id one) f in
  let apply_branches = omap0 ia_ty ia_ty left_branch right_branch in
  let undistribute = undist_l one one a_ty in
  seq0 distribute (seq0 apply_branches undistribute)


(* ========================================================================= *)
(* Main                                                                      *)
(* ========================================================================= *)

let () =
  let project_root = Filename.dirname (Sys.getcwd ()) in
  Bridge.set_project_root project_root;

  banner "VERIFY NESTED CONTROLS: Mathematical Ground Truth";
  print_endline "";
  print_endline "  Compares compiled ctrl^k(G) against mathematically constructed";
  print_endline "  reference unitary: I_{2^n} with bottom-right 2x2 block = G.";
  print_endline "  Independent of the compiler -- pure linear algebra.";
  print_endline "";
  print_endline "  Gates: H, S, Z, T    Controls: k = 1..4    Total: 16 tests";

  (* --- H --- *)
  banner "Gate: H";
  let c1_h = ctrl q gate_h in
  verify "H" h_re h_im (emit c1_h) 1;
  let c2_h = ctrl bq c1_h in
  verify "H" h_re h_im (emit c2_h) 2;
  let c3_h = ctrl bbq c2_h in
  verify "H" h_re h_im (emit c3_h) 3;
  let c4_h = ctrl bbbq c3_h in
  verify "H" h_re h_im (emit c4_h) 4;

  (* --- S --- *)
  banner "Gate: S";
  let c1_s = ctrl q gate_s in
  verify "S" s_re s_im (emit c1_s) 1;
  let c2_s = ctrl bq c1_s in
  verify "S" s_re s_im (emit c2_s) 2;
  let c3_s = ctrl bbq c2_s in
  verify "S" s_re s_im (emit c3_s) 3;
  let c4_s = ctrl bbbq c3_s in
  verify "S" s_re s_im (emit c4_s) 4;

  (* --- Z --- *)
  banner "Gate: Z";
  let c1_z = ctrl q gate_z in
  verify "Z" z_re z_im (emit c1_z) 1;
  let c2_z = ctrl bq c1_z in
  verify "Z" z_re z_im (emit c2_z) 2;
  let c3_z = ctrl bbq c2_z in
  verify "Z" z_re z_im (emit c3_z) 3;
  let c4_z = ctrl bbbq c3_z in
  verify "Z" z_re z_im (emit c4_z) 4;

  (* --- T --- *)
  banner "Gate: T";
  let c1_t = ctrl q gate_t in
  verify "T" t_re t_im (emit c1_t) 1;
  let c2_t = ctrl bq c1_t in
  verify "T" t_re t_im (emit c2_t) 2;
  let c3_t = ctrl bbq c2_t in
  verify "T" t_re t_im (emit c3_t) 3;
  let c4_t = ctrl bbbq c3_t in
  verify "T" t_re t_im (emit c4_t) 4;

  (* --- Summary --- *)
  banner "SUMMARY";
  Printf.printf "\n  %d passed, %d failed out of 16 tests\n\n" !n_pass !n_fail;

  if !n_fail > 0 then begin
    print_endline "  VERIFICATION FAILED";
    exit 1
  end else
    print_endline "  ALL VERIFICATIONS PASSED";

  banner "DEMO COMPLETE"
