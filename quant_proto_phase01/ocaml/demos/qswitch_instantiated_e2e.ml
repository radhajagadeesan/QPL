(** Instantiated QSwitch E2E Demo - Using Case Sugar Combinators

    Full pipeline: OCaml Linear DSL -> Bridge -> Python compile -> Circuit

    This demonstrates compositional use of abstract QSwitch:
    - Define QSwitch as a reusable Linear DSL combinator
    - Instantiate with different gate pairs
    - Compose multiple QSwitch applications
    - Uses case_hom + make_branch sugar (no manual dist/omap/undist)
*)

open Qpl_surface
open Linear

let banner title =
  print_endline "";
  print_endline (String.make 74 '=');
  Printf.printf "  %s\n" title;
  print_endline (String.make 74 '=')

(** Bool = I + I (the 2-element type) *)
let bool_ty = one ++ one

(** QSwitch[f, g] : Bool ⊗ Q → Bool ⊗ Q

    Built using case_hom + make_branch sugar.

    case_hom desugars to: dist_r ; omap0(left, right) ; undist_l
    make_branch desugars to: twist(G,A) ; par0(id_A, body)

    The twist at the front converts Bool⊗Q → Q⊗Bool for case_hom's
    G⊗(A⊕B) input shape (where G=Q, A=B=I).

    Semantics:
      |0⟩ ⊗ |ψ⟩ → |0⟩ ⊗ f(g(|ψ⟩))   (apply g then f)
      |1⟩ ⊗ |ψ⟩ → |1⟩ ⊗ g(f(|ψ⟩))   (apply f then g)
*)
let qswitch
    (f : (unit, [`Lolli of [`Q] * [`Q]]) prog)
    (g : (unit, [`Lolli of [`Q] * [`Q]]) prog)
    : (unit, [`Lolli of [`Tensor of [`Plus of [`One] * [`One]] * [`Q]]
                      * [`Tensor of [`Plus of [`One] * [`One]] * [`Q]]]) prog =
  (* Branches: Q⊗I → I⊗Q via make_branch (twist + par0(id, body)) *)
  let left  = make_branch q one (seq0 g f) in  (* ctrl=0: apply g then f *)
  let right = make_branch q one (seq0 f g) in  (* ctrl=1: apply f then g *)
  (* twist Bool⊗Q → Q⊗Bool, then case_hom handles dist_r ; omap0 ; undist_l *)
  seq0 (twist_tensor bool_ty q) (case_hom one one q q left right)

(** Original QSwitch for equivalence verification (manual dist/omap/undist) *)
let qswitch_manual
    (f : (unit, [`Lolli of [`Q] * [`Q]]) prog)
    (g : (unit, [`Lolli of [`Q] * [`Q]]) prog)
    : (unit, [`Lolli of [`Tensor of [`Plus of [`One] * [`One]] * [`Q]]
                      * [`Tensor of [`Plus of [`One] * [`One]] * [`Q]]]) prog =
  let iq_ty = one ** q in
  let distribute = dist_l one one q in
  let left_branch = par0 (id one) (seq0 g f) in
  let right_branch = par0 (id one) (seq0 f g) in
  let apply_branches = omap0 iq_ty iq_ty left_branch right_branch in
  let undistribute = undist_l one one q in
  seq0 distribute (seq0 apply_branches undistribute)


(** Compile a QSwitch term and report results *)
let had_failure = ref false

let compile_and_report name term =
  Printf.printf "\n%s:\n" name;
  match Bridge.compile_show term with
  | Bridge.CompileOk _ -> ()
  | Bridge.CompileError err ->
      Printf.printf "  ✗ FAILED: %s\n" err;
      had_failure := true


let () =
  (* Set project root for bridge.py *)
  let project_root = Filename.dirname (Sys.getcwd ()) in
  Bridge.set_project_root project_root;

  banner "INSTANTIATED QSWITCH E2E DEMO (Case Sugar)";
  print_endline "\nDemonstrating compositional use of abstract QSwitch\n";
  print_endline "All QSwitch instances use case sugar combinators:";
  print_endline "  twist(Bool, Q) ; case_hom(I, I, Q, Q, make_branch(...), make_branch(...))\n";

  (* =========================================================================
     PART 1: Basic Instantiations
     ========================================================================= *)
  banner "PART 1: Basic QSwitch Instantiations";

  (* QSwitch[H, S] *)
  print_endline "\nQSwitch[H, S]:";
  print_endline "  ctrl=0 → H(S(x)) = S ; H";
  print_endline "  ctrl=1 → S(H(x)) = H ; S";
  compile_and_report "QSwitch[H, S]" (emit (qswitch gate_h gate_s));

  (* QSwitch[X, Z] - Pauli gates *)
  print_endline "\nQSwitch[X, Z] (Pauli gates):";
  print_endline "  ctrl=0 → X(Z(x)) = Z ; X";
  print_endline "  ctrl=1 → Z(X(x)) = X ; Z";
  compile_and_report "QSwitch[X, Z]" (emit (qswitch gate_x gate_z));

  (* QSwitch[H, Y] *)
  print_endline "\nQSwitch[H, Y]:";
  print_endline "  ctrl=0 → H(Y(x)) = Y ; H";
  print_endline "  ctrl=1 → Y(H(x)) = H ; Y";
  compile_and_report "QSwitch[H, Y]" (emit (qswitch gate_h gate_y));

  (* =========================================================================
     PART 2: Composed QSwitch Applications
     ========================================================================= *)
  banner "PART 2: Composed QSwitch Applications";

  print_endline "
Composing multiple QSwitch applications demonstrates:
  - The same control qubit sequences multiple operations
  - Each QSwitch contributes gates coherently
  - Types ensure composition is valid
";

  (* QSwitch[H,S] ; QSwitch[X,Z] - sequential composition *)
  let qs_hs = qswitch gate_h gate_s in
  let qs_xz = qswitch gate_x gate_z in
  let composed = seq0 qs_hs qs_xz in

  print_endline "QSwitch[H,S] ; QSwitch[X,Z]:";
  print_endline "  Type: (Bool ⊗ Q) → (Bool ⊗ Q) → (Bool ⊗ Q)";
  compile_and_report "Composed" (emit composed);

  (* Three QSwitch in sequence *)
  let qs_hy = qswitch gate_h gate_y in
  let triple = seq0 qs_hs (seq0 qs_xz qs_hy) in

  print_endline "\nQSwitch[H,S] ; QSwitch[X,Z] ; QSwitch[H,Y]:";
  compile_and_report "Triple composed" (emit triple);

  (* =========================================================================
     PART 3: Self-Inverse QSwitch
     ========================================================================= *)
  banner "PART 3: Self-Inverse QSwitch (f = g)";

  print_endline "
When f = g, QSwitch[f, f] applies f;f in both branches:
  - Both orderings are the same!
  - This is a uniform operation regardless of control state

For involutive f (f;f = id), this becomes identity on Q!
";

  compile_and_report "QSwitch[H, H]" (emit (qswitch gate_h gate_h));
  compile_and_report "QSwitch[S, S]" (emit (qswitch gate_s gate_s));
  compile_and_report "QSwitch[X, X]" (emit (qswitch gate_x gate_x));

  (* =========================================================================
     PART 4: QSwitch with Rz Rotations
     ========================================================================= *)
  banner "PART 4: QSwitch with Parameterized Rotations";

  print_endline "
QSwitch can be parameterized with any Q → Q morphism.
Using Rz rotations:
";

  (* Build Rz rotation gates *)
  let rz_pi4 = gate_rz (Float.pi /. 4.0) in
  let rz_pi8 = gate_rz (Float.pi /. 8.0) in
  let rz_neg_pi4 = gate_rz (-. Float.pi /. 4.0) in

  compile_and_report "QSwitch[Rz(π/4), Rz(π/8)]" (emit (qswitch rz_pi4 rz_pi8));
  compile_and_report "QSwitch[Rz(π/4), Rz(-π/4)]" (emit (qswitch rz_pi4 rz_neg_pi4));

  (* =========================================================================
     PART 5: Verify Case Sugar ≡ Manual (eq_circ)
     ========================================================================= *)
  banner "PART 5: Verify Case Sugar = Manual (eq_circ)";

  print_endline "
Verifying that case-sugar QSwitch produces the same unitary
as the manual dist_l ; omap0 ; undist_l version.
";

  let verify_equiv name f g =
    let sugar_term = emit (qswitch f g) in
    let manual_term = emit (qswitch_manual f g) in
    match Bridge.eq_circ sugar_term manual_term with
    | Bridge.EqCircOk (equal, fidelity) ->
        Printf.printf "  %-25s %s (fidelity=%.6f)\n"
          name (if equal then "EQUAL" else "NOT EQUAL") fidelity;
        if not equal then had_failure := true
    | Bridge.EqCircError err ->
        Printf.printf "  %-25s ERROR: %s\n" name err;
        had_failure := true
  in
  verify_equiv "QSwitch[H, S]" gate_h gate_s;
  verify_equiv "QSwitch[X, Z]" gate_x gate_z;
  verify_equiv "QSwitch[H, Y]" gate_h gate_y;
  verify_equiv "QSwitch[H, H]" gate_h gate_h;
  verify_equiv "QSwitch[Rz(pi/4), Rz(pi/8)]"
    (gate_rz (Float.pi /. 4.0)) (gate_rz (Float.pi /. 8.0));

  (* =========================================================================
     SUMMARY
     ========================================================================= *)
  banner "SUMMARY";

  print_endline "
Demonstrated compositional use of abstract QSwitch:

1. BASIC INSTANTIATION
   qswitch gate_h gate_s - creates QSwitch for any gate pair

2. SEQUENTIAL COMPOSITION
   seq0 qswitch1 qswitch2 - chains multiple QSwitch ops
   Types ensure composition is valid

3. PARAMETERIZED CONSTRUCTION
   qswitch (gate_rz theta) (gate_rz phi) - factory function

4. SELF-INVERSE CASE
   qswitch gate_h gate_h - when both gates are the same

5. CASE SUGAR = MANUAL
   eq_circ verification: case-sugar and manual versions produce
   identical unitaries for all tested gate pairs.

QSwitch definition using case sugar:

  let qswitch f g =
    let left  = make_branch q one (seq0 g f) in
    let right = make_branch q one (seq0 f g) in
    seq0 (twist_tensor bool_ty q) (case_hom one one q q left right)

Compare with manual version (8 lines of dist/omap/undist plumbing):

  let qswitch_manual f g =
    let distribute = dist_l one one q in
    let left_branch = par0 (id one) (seq0 g f) in
    let right_branch = par0 (id one) (seq0 f g) in
    let apply_branches = omap0 iq_ty iq_ty left_branch right_branch in
    let undistribute = undist_l one one q in
    seq0 distribute (seq0 apply_branches undistribute)
";

  banner "DEMO COMPLETE";
  if !had_failure then exit 1
