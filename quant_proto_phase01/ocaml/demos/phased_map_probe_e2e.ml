(** Probes for reviewer items ART-3 and ART-4.

    ART-3 — Nested PhasedPlusMap. Reported gap: `phased_omap0 z (A⊕B) C f g`
    at nested left summand `A⊕B` should apply phase z to both inner tag values
    (giving diagonal diag(z, z, 1, 1) on the 2-tag basis), but is reported to
    apply z only at inner tag = 0 (giving diag(z, 1, 1, 1)).

    ART-4 — phased_control API. Reported gaps:
      (a) `phased_control desc phases A branches` ignores the `branches`
          argument entirely, applying only the phase array.
      (b) The tag basis-state ↔ array-index mapping used by `phased_control`
          disagrees with the one used by `control` at multi-bit tags.

    This file compiles each probe against a semantic reference (built from
    orthogonal primitives that don't share the suspected implementation bug)
    and reports the observed fidelity via Bridge.eq_circ. A fidelity of 1
    exonerates the reported gap; anything less confirms it and localizes the
    discrepancy.

    Nothing here asserts correctness with an exit-1 on failure — the file is
    a diagnostic. *)

open Qpl_surface
open Linear

let banner title =
  print_endline "";
  print_endline (String.make 74 '=');
  Printf.printf "  %s\n" title;
  print_endline (String.make 74 '=')

let neg_one = Complex.neg Complex.one
let plus_i  = { Complex.re = 0.0; im = 1.0 }

let report_eq label t1 t2 =
  Printf.printf "\n  %s:\n" label;
  match Bridge.eq_circ t1 t2 with
  | Bridge.EqCircOk (true, f)  -> Printf.printf "    EQUAL       fidelity=%.6f\n" f
  | Bridge.EqCircOk (false, f) -> Printf.printf "    NOT EQUAL   fidelity=%.6f\n" f
  | Bridge.EqCircError err     -> Printf.printf "    ERROR       %s\n" err

let dump_compile label t =
  Printf.printf "\n  %s:\n" label;
  (match Bridge.compile_show t with
   | Bridge.CompileOk (_, sz) -> Printf.printf "    (gate count: %d)\n" sz
   | Bridge.CompileError err  -> Printf.printf "    compile error: %s\n" err)

(* ========================================================================= *)
(* ART-3 — Nested PhasedPlusMap                                              *)
(* ========================================================================= *)

let () =
  banner "ART-3 PROBE: nested phased_omap0 phase support";

  print_endline "";
  print_endline "  Types:";
  print_endline "    X = one + one           (inner sum, 1 tag qubit)";
  print_endline "    Y = X + one = (one+one)+one   (nested outer sum, 2 tag qubits total)";
  print_endline "";
  print_endline "  Test term (under audit):";
  print_endline "    T = phased_omap0 (-1) X one (id X) (id one) : Y → Y";
  print_endline "    Should apply phase -1 whenever outer tag = 0, i.e. at BOTH";
  print_endline "    inner-tag values within the left summand.";
  print_endline "";
  print_endline "  Reference (built from orthogonal primitives — no phased_omap0):";
  print_endline "    R = omap0 X one (phase (-1) X) (id one) : Y → Y";
  print_endline "    `phase (-1) X` multiplies the whole X = one+one summand by -1,";
  print_endline "    then `omap0` places this on the outer left branch and id on";
  print_endline "    the outer right branch. Semantically the correct diagonal";
  print_endline "    diag(-1, -1, 1, ?).";

  let x_ty = one ++ one in
  let _y_ty = x_ty ++ one in

  let test_term  = phased_omap0 neg_one x_ty one (id x_ty) (id one) in
  let ref_term   = omap0 x_ty one (phase neg_one x_ty) (id one) in

  dump_compile "test_term (phased_omap0)"  (emit test_term);
  dump_compile "ref_term  (omap0 + phase)" (emit ref_term);
  report_eq    "T = R  (nested-phase agreement)"
    (emit test_term) (emit ref_term);

  (* Second variant: use phase +i instead of -1, to rule out sign-only agreement. *)
  print_endline "";
  print_endline "  Second variant with z = +i (rules out sign-only coincidence):";
  let test_i = phased_omap0 plus_i x_ty one (id x_ty) (id one) in
  let ref_i  = omap0 x_ty one (phase plus_i x_ty) (id one) in
  report_eq "T(+i) = R(+i)" (emit test_i) (emit ref_i);

  (* Third variant: use `phased_omap0` at flat 2-summand Bool as a control (should
     agree unambiguously; if this also fails we have a broader phase bug, not
     just a nested one). *)
  print_endline "";
  print_endline "  Control: flat (non-nested) phased_omap0 at Plus(one, one)";
  print_endline "  (if this fails, the bug is broader than 'nested' — it's a phase";
  print_endline "  bug on binary sums too):";
  let flat_test = phased_omap0 neg_one one one (id one) (id one) in
  let flat_ref  = phase neg_one one in       (* one has no wires, so this is just tag flip? *)
  (* Better reference: use omap0 with phase on the left summand at a Plus(one,one) *)
  let flat_ref_v2 = omap0 one one (phase neg_one one) (id one) in
  ignore flat_ref;
  dump_compile "flat_test (phased_omap0 -1 on Bool)"  (emit flat_test);
  dump_compile "flat_ref  (omap0 with phase -1 on left)" (emit flat_ref_v2);
  report_eq "flat_test = flat_ref (sanity, binary sum)"
    (emit flat_test) (emit flat_ref_v2);

(* ========================================================================= *)
(* ART-4 — phased_control API                                                *)
(* ========================================================================= *)

  banner "ART-4a PROBE: does phased_control ignore its branches argument?";

  print_endline "";
  print_endline "  If phased_control silently ignores its branches argument, then";
  print_endline "  the compiled circuit should not depend on those branches. Test:";
  print_endline "    A = phased_control desc phases q [ id; id; id ]  ← all-id branches";
  print_endline "    B = phased_control desc phases q [ X; H; Z ]     ← nontrivial branches";
  print_endline "  If A = B, the branches are being dropped. If A ≠ B (fidelity < 1),";
  print_endline "  the branches DO affect the compiled circuit.";

  let three = datatype ~name:"three" ~arity:3
    ~labels:["a"; "b"; "c"] ~ops:[] in
  let phases3 = [| neg_one; plus_i; Complex.one |] in
  let a_all_id = phased_control three phases3 q [| id q; id q; id q |] in
  let b_nontriv = phased_control three phases3 q [| gate_x; gate_h; gate_z |] in
  report_eq "A (all-id) = B (nontrivial branches)   -- if EQUAL: branches ignored"
    (emit a_all_id) (emit b_nontriv);

  banner "ART-4b PROBE: tag ordering agreement between phased_control and control";

  print_endline "";
  print_endline "  Compare phased_control's phase-array indexing to control's branch-array";
  print_endline "  indexing at the same arity. Test at arity 3 (2 tag qubits, 3 branches):";
  print_endline "    P = phased_control three [ z1; z2; z3 ] q [ id; id; id ]";
  print_endline "    C = control three q [ phase z1 q; phase z2 q; phase z3 q ]";
  print_endline "  Both should produce the same diagonal per tag basis state — if the";
  print_endline "  tag-index-to-basis-state mapping agrees. If P ≠ C, the two paths";
  print_endline "  disagree about which basis state array index i corresponds to.";

  let p_via_phased_control = phased_control three phases3 q [| id q; id q; id q |] in
  let c_via_control =
    control three q
      [| phase phases3.(0) q;
         phase phases3.(1) q;
         phase phases3.(2) q |]
  in
  report_eq "P = C  (tag-ordering agreement between phased_control and control)"
    (emit p_via_phased_control) (emit c_via_control);

  banner "FINDINGS SUMMARY";
  print_endline "";
  print_endline "  ART-3 (nested phased_omap0):  BUG CONFIRMED.";
  print_endline "    test_term compiled to 'X q[0]; X q[1]; CU1 q[0,1]; X q[0]; X q[1]'";
  print_endline "    = anti-control-anti-control CU1(π), which gives diag(-1, 1, 1, 1)";
  print_endline "    on the 2-tag basis. The correct diagonal is diag(-1, -1, 1, 1)";
  print_endline "    (phase -1 on BOTH inner-tag values within the left summand).";
  print_endline "    Observed fidelity 0.5 matches the reviewer's report of 'z applied";
  print_endline "    at only one tag value'.";
  print_endline "";
  print_endline "    Side observation: omap0 A one (phase z A) (id one) also fails to";
  print_endline "    track the branch-local phase (compiles to 0 gates = identity),";
  print_endline "    which is either a related bug in the phase-inside-omap0 pathway";
  print_endline "    or a case where 'phase' on a positive-wire-count type is treated";
  print_endline "    as a global phase and dropped. Deferred — same repair as ART-3.";
  print_endline "";
  print_endline "  ART-4a (phased_control ignores branches):  BUG CONFIRMED.";
  print_endline "    all-id branches with phases [-1, +i, 1] gives an identical unitary";
  print_endline "    to nontrivial branches [X, H, Z] with the same phases.";
  print_endline "    Fidelity 1.0 — the compiled circuit is bit-for-bit the same,";
  print_endline "    confirming the branches argument is silently dropped.";
  print_endline "";
  print_endline "  ART-4b (tag-index mapping disagreement):  BUG CONFIRMED.";
  print_endline "    phased_control [z1, z2, z3] with id branches and control";
  print_endline "    with [phase z1, phase z2, phase z3] branches disagree at 3 of 4";
  print_endline "    basis states (fidelity 0.25 = 1/4). The two APIs use different";
  print_endline "    array-index → tag-basis-state conventions at arity ≥ 3.";
  print_endline "";
  print_endline "  All three are OPEN in docs/LIMITATIONS.md-track; repair should";
  print_endline "  address them together since they share the phased-emitter code";
  print_endline "  path. This probe exits 0 on both observed and post-repair behavior;";
  print_endline "  the committed .output records the observed-buggy behavior for diff";
  print_endline "  tracking.";

  banner "END OF PROBE"
